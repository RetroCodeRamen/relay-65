"""6502 execute microprograms: EEPROM contents for the Control card.

FETCH lives in cpu.py (shared sequencer page). Every helper here is a
list of control words that only move bytes on the one internal bus and
the one ALU — the same reuse the relay CPU will have.
"""

from __future__ import annotations

from .signals import (
    END,
    FB,
    FU,
    AluOp,
    CW,
    Cin,
    Cond,
    Dst,
    FLG_NZ,
    FLG_NZC,
    FLG_NZCV,
    FLG_NVZ,
    Src,
    alu,
    xfer,
)


def pc_to_mar() -> list[CW]:
    return [xfer(Src.PCL, Dst.MARL), xfer(Src.PCH, Dst.MARH)]


def mem_to_mdr() -> list[CW]:
    return [CW(src=Src.MEM, dst=Dst.MDR, mem_rd=True)]


def mdr_write() -> list[CW]:
    return [CW(src=Src.MDR, dst=Dst.MEM, mem_wr=True)]


def pc_inc() -> list[CW]:
    """PC ← PC+1 using the ALU, not a dedicated incrementer."""
    return [
        xfer(Src.PCL, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 1),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.PCL),
        xfer(Src.PCH, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0),
        alu(AluOp.ADC, cin=Cin.LATCH),
        xfer(Src.ALU, Dst.PCH),
    ]


def sp_dec() -> list[CW]:
    return [
        xfer(Src.SP, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0xFF),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.SP),
    ]


def sp_inc() -> list[CW]:
    return [
        xfer(Src.SP, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 1),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.SP),
    ]


def mar_stack() -> list[CW]:
    return [xfer(Src.SP, Dst.MARL), xfer(Src.CONST, Dst.MARH, 1)]


def fetch_byte() -> list[CW]:
    return pc_to_mar() + mem_to_mdr() + pc_inc()


def pass_to(dst: Dst, flags: int = 0) -> list[CW]:
    steps = [xfer(Src.MDR, Dst.ALU_A), alu(AluOp.PASS_A, flags=flags)]
    if dst != Dst.NONE:
        steps.append(xfer(Src.ALU, dst))
    return steps


def add8(dst_hi: Dst, dst_lo: Dst, src_add: Src) -> list[CW]:
    """(dst_hi:dst_lo) ← (MDR as lo already in T?) used for abs,X style.

    Expects lo in ALU-bound sequence: T holds lo, MDR holds hi, add src_add to lo.
    """
    return [
        xfer(Src.T, Dst.ALU_A),
        xfer(src_add, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, dst_lo),
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0),
        alu(AluOp.ADC, cin=Cin.LATCH),
        xfer(Src.ALU, dst_hi),
    ]


def FETCH() -> list[CW]:
    return pc_to_mar() + mem_to_mdr() + [xfer(Src.MDR, Dst.IR)] + pc_inc()


def RESET() -> list[CW]:
    """Load PC from $FFFC; set I (done in sequencer)."""
    return [
        xfer(Src.CONST, Dst.MARL, 0xFC),
        xfer(Src.CONST, Dst.MARH, 0xFF),
    ] + mem_to_mdr() + [xfer(Src.MDR, Dst.PCL)] + [
        xfer(Src.CONST, Dst.MARL, 0xFD),
        xfer(Src.CONST, Dst.MARH, 0xFF),
    ] + mem_to_mdr() + [xfer(Src.MDR, Dst.PCH), END()]


# --- addressing: leave EA in MAR, or operand in MDR for immediate ---

def ea_imm() -> list[CW]:
    return fetch_byte()


def ea_zp() -> list[CW]:
    return fetch_byte() + [xfer(Src.MDR, Dst.MARL), xfer(Src.CONST, Dst.MARH, 0)]


def ea_zpx() -> list[CW]:
    return fetch_byte() + [
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.X, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.MARL),
        xfer(Src.CONST, Dst.MARH, 0),
    ]


def ea_zpy() -> list[CW]:
    return fetch_byte() + [
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.Y, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.MARL),
        xfer(Src.CONST, Dst.MARH, 0),
    ]


def ea_abs() -> list[CW]:
    return (
        fetch_byte()
        + [xfer(Src.MDR, Dst.T)]
        + fetch_byte()
        + [xfer(Src.T, Dst.MARL), xfer(Src.MDR, Dst.MARH)]
    )


def ea_absx() -> list[CW]:
    return fetch_byte() + [xfer(Src.MDR, Dst.T)] + fetch_byte() + add8(Dst.MARH, Dst.MARL, Src.X)


def ea_absy() -> list[CW]:
    return fetch_byte() + [xfer(Src.MDR, Dst.T)] + fetch_byte() + add8(Dst.MARH, Dst.MARL, Src.Y)


def zp_ptr_to_t_mdr() -> list[CW]:
    """Read (zp) with 6502 zp wrap: lo from zp, hi from zp+1 wrapped."""
    return [
        xfer(Src.MDR, Dst.MARL),
        xfer(Src.CONST, Dst.MARH, 0),
    ] + mem_to_mdr() + [xfer(Src.MDR, Dst.T)] + [
        xfer(Src.MARL, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 1),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.MARL),
    ] + mem_to_mdr()


def ea_indx() -> list[CW]:
    return fetch_byte() + [
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.X, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.MDR),
    ] + zp_ptr_to_t_mdr() + [xfer(Src.T, Dst.MARL), xfer(Src.MDR, Dst.MARH)]


def ea_indy() -> list[CW]:
    return fetch_byte() + zp_ptr_to_t_mdr() + [
        xfer(Src.T, Dst.ALU_A),
        xfer(Src.Y, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.MARL),
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0),
        alu(AluOp.ADC, cin=Cin.LATCH),
        xfer(Src.ALU, Dst.MARH),
    ]


EA = {
    "imm": ea_imm,
    "zp": ea_zp,
    "zpx": ea_zpx,
    "zpy": ea_zpy,
    "abs": ea_abs,
    "absx": ea_absx,
    "absy": ea_absy,
    "indx": ea_indx,
    "indy": ea_indy,
}


def ld(dst: Dst, mode: str) -> list[CW]:
    s = EA[mode]()
    if mode != "imm":
        s += mem_to_mdr()
    return s + pass_to(dst, FLG_NZ) + [END()]


def st(src: Src, mode: str) -> list[CW]:
    return EA[mode]() + [xfer(src, Dst.MDR)] + mdr_write() + [END()]


def binary(mode: str, op: AluOp, flags: int, invert_b: bool = False, cin: Cin = Cin.ZERO, write_a: bool = True) -> list[CW]:
    s = EA[mode]()
    if mode != "imm":
        s += mem_to_mdr()
    s += [
        xfer(Src.A, Dst.ALU_A),
        xfer(Src.MDR, Dst.ALU_B),
        alu(op, flags=flags, cin=cin, invert_b=invert_b),
    ]
    if write_a:
        s.append(xfer(Src.ALU, Dst.A))
    s.append(END())
    return s


def cmp_reg(src: Src, mode: str) -> list[CW]:
    s = EA[mode]()
    if mode != "imm":
        s += mem_to_mdr()
    return s + [
        xfer(src, Dst.ALU_A),
        xfer(Src.MDR, Dst.ALU_B),
        alu(AluOp.ADC, flags=FLG_NZC, cin=Cin.ONE, invert_b=True),
        END(),
    ]


def bit_mode(mode: str) -> list[CW]:
    return EA[mode]() + mem_to_mdr() + [
        xfer(Src.A, Dst.ALU_A),
        xfer(Src.MDR, Dst.ALU_B),
        alu(AluOp.BIT, flags=FLG_NVZ),
        END(),
    ]


def rmw(mode: str, op: AluOp, cin: Cin = Cin.ZERO) -> list[CW]:
    return EA[mode]() + mem_to_mdr() + [
        xfer(Src.MDR, Dst.ALU_A),
        alu(op, flags=FLG_NZC if op != AluOp.ADD else FLG_NZ, cin=cin),
        xfer(Src.ALU, Dst.MDR),
    ] + mdr_write() + [END()]


def incdec(mode: str, delta: int) -> list[CW]:
    return EA[mode]() + mem_to_mdr() + [
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, delta & 0xFF),
        alu(AluOp.ADD, flags=FLG_NZ),
        xfer(Src.ALU, Dst.MDR),
    ] + mdr_write() + [END()]


def acc_shift(op: AluOp, cin: Cin) -> list[CW]:
    return [
        xfer(Src.A, Dst.ALU_A),
        alu(op, flags=FLG_NZC, cin=cin),
        xfer(Src.ALU, Dst.A),
        END(),
    ]


def inc_reg(srcdst: Src, dst: Dst, delta: int) -> list[CW]:
    return [
        xfer(srcdst, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, delta & 0xFF),
        alu(AluOp.ADD, flags=FLG_NZ),
        xfer(Src.ALU, dst),
        END(),
    ]


def transfer(src: Src, dst: Dst, flags: bool = True) -> list[CW]:
    s = [xfer(src, Dst.ALU_A), alu(AluOp.PASS_A, flags=FLG_NZ if flags else 0), xfer(Src.ALU, dst), END()]
    return s


def p_and(mask: int) -> list[CW]:
    return [
        xfer(Src.P, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, mask),
        alu(AluOp.AND),
        xfer(Src.ALU, Dst.P),
        END(),
    ]


def p_or(mask: int) -> list[CW]:
    return [
        xfer(Src.P, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, mask),
        alu(AluOp.OR),
        xfer(Src.ALU, Dst.P),
        END(),
    ]


def push_mdr() -> list[CW]:
    return mar_stack() + mdr_write() + sp_dec()


def pop_mdr() -> list[CW]:
    return sp_inc() + mar_stack() + mem_to_mdr()


def branch(end_if: Cond) -> list[CW]:
    return fetch_byte() + [
        CW(end_if=end_if),
        xfer(Src.PCL, Dst.ALU_A),
        xfer(Src.MDR, Dst.ALU_B),
        alu(AluOp.ADD),
        xfer(Src.ALU, Dst.PCL),
        xfer(Src.PCH, Dst.ALU_A),
        xfer(Src.M7EXT, Dst.ALU_B),
        alu(AluOp.ADC, cin=Cin.LATCH),
        xfer(Src.ALU, Dst.PCH),
        END(),
    ]


def jmp_abs() -> list[CW]:
    return fetch_byte() + [xfer(Src.MDR, Dst.T)] + fetch_byte() + [
        xfer(Src.T, Dst.PCL),
        xfer(Src.MDR, Dst.PCH),
        END(),
    ]


def jmp_ind() -> list[CW]:
    """NMOS: increment MARL only, no carry into MARH."""
    return (
        ea_abs()
        + mem_to_mdr()
        + [xfer(Src.MDR, Dst.T)]
        + [
            xfer(Src.MARL, Dst.ALU_A),
            xfer(Src.CONST, Dst.ALU_B, 1),
            alu(AluOp.ADD),
            xfer(Src.ALU, Dst.MARL),
        ]
        + mem_to_mdr()
        + [xfer(Src.T, Dst.PCL), xfer(Src.MDR, Dst.PCH), END()]
    )


def jsr() -> list[CW]:
    return (
        fetch_byte()
        + [xfer(Src.MDR, Dst.T)]
        + mar_stack()
        + [xfer(Src.PCH, Dst.MDR)]
        + mdr_write()
        + sp_dec()
        + mar_stack()
        + [xfer(Src.PCL, Dst.MDR)]
        + mdr_write()
        + sp_dec()
        + fetch_byte()
        + [xfer(Src.T, Dst.PCL), xfer(Src.MDR, Dst.PCH), END()]
    )


def rts() -> list[CW]:
    return pop_mdr() + [xfer(Src.MDR, Dst.PCL)] + pop_mdr() + [xfer(Src.MDR, Dst.PCH)] + pc_inc() + [END()]


def rti() -> list[CW]:
    return (
        pop_mdr()
        + [xfer(Src.MDR, Dst.P)]
        + pop_mdr()
        + [xfer(Src.MDR, Dst.PCL)]
        + pop_mdr()
        + [xfer(Src.MDR, Dst.PCH), END()]
    )


def pha() -> list[CW]:
    return [xfer(Src.A, Dst.MDR)] + push_mdr() + [END()]


def php() -> list[CW]:
    return [xfer(Src.P, Dst.MDR, p_or=FU | FB)] + push_mdr() + [END()]


def pla() -> list[CW]:
    return pop_mdr() + pass_to(Dst.A, FLG_NZ) + [END()]


def plp() -> list[CW]:
    return pop_mdr() + [xfer(Src.MDR, Dst.P), END()]


def brk() -> list[CW]:
    return fetch_byte() + interrupt(0xFFFE, status_or=FU | FB)


def irq() -> list[CW]:
    """IRQ after instruction END. PC already points at the next opcode."""
    return interrupt(0xFFFE, status_or=FU)


def nmi() -> list[CW]:
    return interrupt(0xFFFA, status_or=FU)


def interrupt(vector: int, status_or: int) -> list[CW]:
    lo = vector & 0xFF
    hi = (vector >> 8) & 0xFF
    return (
        mar_stack()
        + [xfer(Src.PCH, Dst.MDR)]
        + mdr_write()
        + sp_dec()
        + mar_stack()
        + [xfer(Src.PCL, Dst.MDR)]
        + mdr_write()
        + sp_dec()
        + mar_stack()
        + [xfer(Src.P, Dst.MDR, p_or=status_or)]
        + mdr_write()
        + sp_dec()
        + p_or(0x04)[:-1]
        + [
            xfer(Src.CONST, Dst.MARL, lo),
            xfer(Src.CONST, Dst.MARH, hi),
        ]
        + mem_to_mdr()
        + [xfer(Src.MDR, Dst.PCL)]
        + [
            xfer(Src.CONST, Dst.MARL, (lo + 1) & 0xFF),
            xfer(Src.CONST, Dst.MARH, hi),
        ]
        + mem_to_mdr()
        + [xfer(Src.MDR, Dst.PCH), END()]
    )


def nop() -> list[CW]:
    return [END()]


def build_execute_rom() -> list[list[CW] | None]:
    rom: list[list[CW] | None] = [None] * 256
    rom[0x00] = brk()
    rom[0x08] = php()
    rom[0x18] = p_and(0xFE)  # CLC
    rom[0x28] = plp()
    rom[0x38] = p_or(0x01)  # SEC
    rom[0x40] = rti()
    rom[0x48] = pha()
    rom[0x58] = p_and(0xFB)  # CLI
    rom[0x60] = rts()
    rom[0x68] = pla()
    rom[0x78] = p_or(0x04)  # SEI
    rom[0x88] = inc_reg(Src.Y, Dst.Y, -1)
    rom[0x8A] = transfer(Src.X, Dst.A)
    rom[0x98] = transfer(Src.Y, Dst.A)
    rom[0x9A] = transfer(Src.X, Dst.SP, flags=False)
    rom[0xA8] = transfer(Src.A, Dst.Y)
    rom[0xAA] = transfer(Src.A, Dst.X)
    rom[0xB8] = p_and(0xBF)  # CLV
    rom[0xBA] = transfer(Src.SP, Dst.X)
    rom[0xC8] = inc_reg(Src.Y, Dst.Y, 1)
    rom[0xCA] = inc_reg(Src.X, Dst.X, -1)
    rom[0xD8] = p_and(0xF7)  # CLD
    rom[0xE8] = inc_reg(Src.X, Dst.X, 1)
    rom[0xEA] = nop()
    rom[0xF8] = p_or(0x08)  # SED

    rom[0x10] = branch(Cond.N)  # BPL end if N
    rom[0x30] = branch(Cond.NN)  # BMI end if not N
    rom[0x50] = branch(Cond.V)
    rom[0x70] = branch(Cond.NV)
    rom[0x90] = branch(Cond.C)  # BCC
    rom[0xB0] = branch(Cond.NC)
    rom[0xD0] = branch(Cond.Z)  # BNE
    rom[0xF0] = branch(Cond.NZ)  # BEQ

    rom[0x4C] = jmp_abs()
    rom[0x6C] = jmp_ind()
    rom[0x20] = jsr()

    for op, mode in (
        (0xA9, "imm"), (0xA5, "zp"), (0xB5, "zpx"), (0xAD, "abs"),
        (0xBD, "absx"), (0xB9, "absy"), (0xA1, "indx"), (0xB1, "indy"),
    ):
        rom[op] = ld(Dst.A, mode)
    for op, mode in (
        (0xA2, "imm"), (0xA6, "zp"), (0xB6, "zpy"), (0xAE, "abs"), (0xBE, "absy"),
    ):
        rom[op] = ld(Dst.X, mode)
    for op, mode in (
        (0xA0, "imm"), (0xA4, "zp"), (0xB4, "zpx"), (0xAC, "abs"), (0xBC, "absx"),
    ):
        rom[op] = ld(Dst.Y, mode)

    for op, mode in (
        (0x85, "zp"), (0x95, "zpx"), (0x8D, "abs"), (0x9D, "absx"),
        (0x99, "absy"), (0x81, "indx"), (0x91, "indy"),
    ):
        rom[op] = st(Src.A, mode)
    for op, mode in ((0x86, "zp"), (0x96, "zpy"), (0x8E, "abs")):
        rom[op] = st(Src.X, mode)
    for op, mode in ((0x84, "zp"), (0x94, "zpx"), (0x8C, "abs")):
        rom[op] = st(Src.Y, mode)

    for op, mode in (
        (0x69, "imm"), (0x65, "zp"), (0x75, "zpx"), (0x6D, "abs"),
        (0x7D, "absx"), (0x79, "absy"), (0x61, "indx"), (0x71, "indy"),
    ):
        rom[op] = binary(mode, AluOp.ADC, FLG_NZCV, cin=Cin.P)
    for op, mode in (
        (0xE9, "imm"), (0xE5, "zp"), (0xF5, "zpx"), (0xED, "abs"),
        (0xFD, "absx"), (0xF9, "absy"), (0xE1, "indx"), (0xF1, "indy"),
    ):
        rom[op] = binary(mode, AluOp.ADC, FLG_NZCV, invert_b=True, cin=Cin.P)
    for op, mode in (
        (0x29, "imm"), (0x25, "zp"), (0x35, "zpx"), (0x2D, "abs"),
        (0x3D, "absx"), (0x39, "absy"), (0x21, "indx"), (0x31, "indy"),
    ):
        rom[op] = binary(mode, AluOp.AND, FLG_NZ)
    for op, mode in (
        (0x09, "imm"), (0x05, "zp"), (0x15, "zpx"), (0x0D, "abs"),
        (0x1D, "absx"), (0x19, "absy"), (0x01, "indx"), (0x11, "indy"),
    ):
        rom[op] = binary(mode, AluOp.OR, FLG_NZ)
    for op, mode in (
        (0x49, "imm"), (0x45, "zp"), (0x55, "zpx"), (0x4D, "abs"),
        (0x5D, "absx"), (0x59, "absy"), (0x41, "indx"), (0x51, "indy"),
    ):
        rom[op] = binary(mode, AluOp.XOR, FLG_NZ)
    for op, mode in (
        (0xC9, "imm"), (0xC5, "zp"), (0xD5, "zpx"), (0xCD, "abs"),
        (0xDD, "absx"), (0xD9, "absy"), (0xC1, "indx"), (0xD1, "indy"),
    ):
        rom[op] = cmp_reg(Src.A, mode)
    for op, mode in ((0xE0, "imm"), (0xE4, "zp"), (0xEC, "abs")):
        rom[op] = cmp_reg(Src.X, mode)
    for op, mode in ((0xC0, "imm"), (0xC4, "zp"), (0xCC, "abs")):
        rom[op] = cmp_reg(Src.Y, mode)

    rom[0x24] = bit_mode("zp")
    rom[0x2C] = bit_mode("abs")

    rom[0x0A] = acc_shift(AluOp.ASL, Cin.ZERO)
    rom[0x4A] = acc_shift(AluOp.LSR, Cin.ZERO)
    rom[0x2A] = acc_shift(AluOp.ROL, Cin.P)
    rom[0x6A] = acc_shift(AluOp.ROR, Cin.P)

    for op, mode in ((0x06, "zp"), (0x16, "zpx"), (0x0E, "abs"), (0x1E, "absx")):
        rom[op] = rmw(mode, AluOp.ASL)
    for op, mode in ((0x46, "zp"), (0x56, "zpx"), (0x4E, "abs"), (0x5E, "absx")):
        rom[op] = rmw(mode, AluOp.LSR)
    for op, mode in ((0x26, "zp"), (0x36, "zpx"), (0x2E, "abs"), (0x3E, "absx")):
        rom[op] = rmw(mode, AluOp.ROL, Cin.P)
    for op, mode in ((0x66, "zp"), (0x76, "zpx"), (0x6E, "abs"), (0x7E, "absx")):
        rom[op] = rmw(mode, AluOp.ROR, Cin.P)
    for op, mode in ((0xE6, "zp"), (0xF6, "zpx"), (0xEE, "abs"), (0xFE, "absx")):
        rom[op] = incdec(mode, 1)
    for op, mode in ((0xC6, "zp"), (0xD6, "zpx"), (0xCE, "abs"), (0xDE, "absx")):
        rom[op] = incdec(mode, -1)

    return rom
