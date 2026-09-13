"""6502 execute microprograms: EEPROM contents for the Control card.

FETCH lives in cpu.py (shared sequencer page). Every helper here is a
list of control words that only move bytes on the one internal bus and
the one ALU — the same reuse the relay CPU will have.

Packing rules (real coils, fewer EEPROM rows):
- ADDR_PC + MEM→dst + PC_INC share one row: incrementer does not use the bus;
  Φ2 strobes dest LOAD and PC LOAD together (Design B dual-LOAD).
- ALU op + DST share one row: Φ1 evaluates, Φ2 loads the result.
- END is a bit on the last useful row, not an empty extra row (except NOP).
- N/Z for loads/transfers sample the internal bus; C/V still come from the ALU.
- ADDR_SP + REG_DEC share a stack write; REG_INC/DEC is an 8-bit helper, not a
  second ALU. Taken branches use ALU_A from the bus and ALU_B from M7EXT.
"""

from __future__ import annotations

from dataclasses import replace

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
    xfer,
)


def mem_to(dst: Dst, *, flags: int = 0, end: bool = False) -> CW:
    """Data cycle: MAR on A[15:0], MEM → dst."""
    return CW(src=Src.MEM, dst=dst, mem_rd=True, flags=flags, end=end)


def mem_to_mdr() -> list[CW]:
    return [mem_to(Dst.MDR)]


def alu_to(
    dst: Dst,
    op: AluOp,
    *,
    flags: int = 0,
    cin: Cin = Cin.ZERO,
    invert_b: bool = False,
    end: bool = False,
    mem_wr: bool = False,
) -> CW:
    """Φ1 ALU evaluate, Φ2 load dest from ALU OE (fused writeback, 0 extra relays)."""
    return CW(
        src=Src.ALU,
        dst=dst,
        alu=op,
        flags=flags,
        cin=cin,
        invert_b=invert_b,
        end=end,
        mem_wr=mem_wr,
    )


def pc_inc() -> list[CW]:
    """One EEPROM row: Φ2 loads PC from the dedicated +1 network.

    Not an emulator skip. Hardware still waits a coil phase for that LOAD.
    The general ALU is unused (Design B: ~16 DPDT incrementer, not a second ALU).
    """
    return [CW(pc_inc=True)]


def fetch_into(
    dst: Dst,
    *,
    flags: int = 0,
    end: bool = False,
    inc: bool = True,
    also_alu_b: bool = False,
) -> CW:
    """Opcode/operand fetch: PC on A[15:0], data → dst, optional PC+1 on the same Φ2."""
    return CW(
        src=Src.MEM,
        dst=dst,
        mem_rd=True,
        addr_pc=True,
        pc_inc=inc,
        flags=flags,
        end=end,
        also_alu_b=also_alu_b,
    )


def fetch_byte() -> list[CW]:
    """Operand fetch, Design B packed into one row.

    Φ1: ADDR_PC (8 DPDT) + memory OE; incrementer evaluates from PC Q.
    Φ2: LOAD dest from the data bus and LOAD PC from +1 (two LOADs, different
    registers; incrementer does not use the bus). Data cycles still copy EA
    into MAR.
    """
    return [fetch_into(Dst.MDR)]


def FETCH() -> list[CW]:
    """Opcode fetch, Design B packed into one row (not a host skip).

    Same coils as the two-phase Option C fetch: ADDR_PC + MEM → IR + PC←PC+1.
    Dual Φ2 LOAD is allowed in the hardware write-up; splitting IR then PC is
    only needed if the LOAD current spike is ugly.
    """
    return [fetch_into(Dst.IR)]


def RESET() -> list[CW]:
    """Load PC from $FFFC; set I (done in sequencer)."""
    return [
        xfer(Src.CONST, Dst.MARL, 0xFC),
        xfer(Src.CONST, Dst.MARH, 0xFF),
        mem_to(Dst.PCL),
        xfer(Src.CONST, Dst.MARL, 0xFD),
        xfer(Src.CONST, Dst.MARH, 0xFF),
        mem_to(Dst.PCH, end=True),
    ]


def sp_dec() -> list[CW]:
    """One row: 8-bit helper −1 into SP. Address still uses SP Q on this Φ1."""
    return [CW(dst=Dst.SP, reg_dec=True)]


def sp_inc() -> list[CW]:
    return [CW(dst=Dst.SP, reg_inc=True)]


def mar_stack() -> list[CW]:
    return [xfer(Src.SP, Dst.MARL), xfer(Src.CONST, Dst.MARH, 1)]


def with_end(rows: list[CW]) -> list[CW]:
    return [*rows[:-1], replace(rows[-1], end=True)]


def push_src(src: Src, p_or: int = 0) -> list[CW]:
    """Write SRC to $0100|SP, then SP−1, one row. ADDR_SP uses SP Q before the LOAD."""
    return [CW(src=src, dst=Dst.MEM, mem_wr=True, addr_sp=True, reg_dec=True, p_or=p_or)]


def add8(dst_hi: Dst, dst_lo: Dst, src_add: Src) -> list[CW]:
    """(dst_hi:dst_lo) ← T + src_add, MDR as high + carry.

    Expects lo in T, hi in MDR.
    """
    return [
        xfer(Src.T, Dst.ALU_A),
        xfer(src_add, Dst.ALU_B),
        alu_to(dst_lo, AluOp.ADD),
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0),
        alu_to(dst_hi, AluOp.ADC, cin=Cin.LATCH),
    ]


# --- addressing: leave EA in MAR, or operand in MDR for immediate ---

def ea_imm() -> list[CW]:
    return fetch_byte()


def ea_zp() -> list[CW]:
    return [fetch_into(Dst.MARL), xfer(Src.CONST, Dst.MARH, 0)]


def ea_zpx() -> list[CW]:
    return [
        fetch_into(Dst.ALU_A),
        xfer(Src.X, Dst.ALU_B),
        alu_to(Dst.MARL, AluOp.ADD),
        xfer(Src.CONST, Dst.MARH, 0),
    ]


def ea_zpy() -> list[CW]:
    return [
        fetch_into(Dst.ALU_A),
        xfer(Src.Y, Dst.ALU_B),
        alu_to(Dst.MARL, AluOp.ADD),
        xfer(Src.CONST, Dst.MARH, 0),
    ]


def ea_abs() -> list[CW]:
    return [fetch_into(Dst.MARL), fetch_into(Dst.MARH)]


def ea_absx() -> list[CW]:
    return [fetch_into(Dst.T), fetch_into(Dst.MDR)] + add8(Dst.MARH, Dst.MARL, Src.X)


def ea_absy() -> list[CW]:
    return [fetch_into(Dst.T), fetch_into(Dst.MDR)] + add8(Dst.MARH, Dst.MARL, Src.Y)


def zp_ptr_to_t_mdr() -> list[CW]:
    """Read (zp) with 6502 zp wrap: lo from zp, hi from zp+1 wrapped. Pointer in MDR."""
    return [
        xfer(Src.MDR, Dst.MARL),
        xfer(Src.CONST, Dst.MARH, 0),
        mem_to(Dst.T),
        CW(dst=Dst.MARL, reg_inc=True),
        mem_to(Dst.MDR),
    ]


def ea_indx() -> list[CW]:
    return [
        fetch_into(Dst.ALU_A),
        xfer(Src.X, Dst.ALU_B),
        alu_to(Dst.MDR, AluOp.ADD),
    ] + zp_ptr_to_t_mdr() + [xfer(Src.T, Dst.MARL), xfer(Src.MDR, Dst.MARH)]


def ea_indy() -> list[CW]:
    return fetch_byte() + zp_ptr_to_t_mdr() + [
        xfer(Src.T, Dst.ALU_A),
        xfer(Src.Y, Dst.ALU_B),
        alu_to(Dst.MARL, AluOp.ADD),
        xfer(Src.MDR, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, 0),
        alu_to(Dst.MARH, AluOp.ADC, cin=Cin.LATCH),
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
    if mode == "imm":
        return [fetch_into(dst, flags=FLG_NZ, end=True)]
    return EA[mode]() + [mem_to(dst, flags=FLG_NZ, end=True)]


def st(src: Src, mode: str) -> list[CW]:
    return EA[mode]() + [CW(src=src, dst=Dst.MEM, mem_wr=True, end=True)]


def binary(
    mode: str,
    op: AluOp,
    flags: int,
    invert_b: bool = False,
    cin: Cin = Cin.ZERO,
    write_a: bool = True,
) -> list[CW]:
    if mode == "imm":
        s = [fetch_into(Dst.ALU_B)]
    else:
        s = EA[mode]() + [mem_to(Dst.ALU_B)]
    s += [
        xfer(Src.A, Dst.ALU_A),
        alu_to(
            Dst.A if write_a else Dst.NONE,
            op,
            flags=flags,
            cin=cin,
            invert_b=invert_b,
            end=True,
        ),
    ]
    return s


def cmp_reg(src: Src, mode: str) -> list[CW]:
    if mode == "imm":
        s = [fetch_into(Dst.ALU_B)]
    else:
        s = EA[mode]() + [mem_to(Dst.ALU_B)]
    return s + [
        xfer(src, Dst.ALU_A),
        alu_to(Dst.NONE, AluOp.ADC, flags=FLG_NZC, cin=Cin.ONE, invert_b=True, end=True),
    ]


def bit_mode(mode: str) -> list[CW]:
    return EA[mode]() + [
        mem_to(Dst.ALU_B),
        xfer(Src.A, Dst.ALU_A),
        alu_to(Dst.NONE, AluOp.BIT, flags=FLG_NVZ, end=True),
    ]


def rmw(mode: str, op: AluOp, cin: Cin = Cin.ZERO) -> list[CW]:
    return EA[mode]() + [
        mem_to(Dst.ALU_A),
        alu_to(
            Dst.MEM,
            op,
            flags=FLG_NZC if op != AluOp.ADD else FLG_NZ,
            cin=cin,
            mem_wr=True,
            end=True,
        ),
    ]


def incdec(mode: str, delta: int) -> list[CW]:
    return EA[mode]() + [
        mem_to(Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, delta & 0xFF),
        alu_to(Dst.MEM, AluOp.ADD, flags=FLG_NZ, mem_wr=True, end=True),
    ]


def acc_shift(op: AluOp, cin: Cin) -> list[CW]:
    return [
        xfer(Src.A, Dst.ALU_A),
        alu_to(Dst.A, op, flags=FLG_NZC, cin=cin, end=True),
    ]


def inc_reg(srcdst: Src, dst: Dst, delta: int) -> list[CW]:
    return [CW(dst=dst, flags=FLG_NZ, end=True, reg_inc=delta > 0, reg_dec=delta < 0)]


def transfer(src: Src, dst: Dst, flags: bool = True) -> list[CW]:
    return [CW(src=src, dst=dst, flags=FLG_NZ if flags else 0, end=True)]


def p_and(mask: int, end: bool = True) -> list[CW]:
    return [
        xfer(Src.P, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, mask),
        alu_to(Dst.P, AluOp.AND, end=end),
    ]


def p_or(mask: int, end: bool = True) -> list[CW]:
    return [
        xfer(Src.P, Dst.ALU_A),
        xfer(Src.CONST, Dst.ALU_B, mask),
        alu_to(Dst.P, AluOp.OR, end=end),
    ]


def pop_to(dst: Dst, *, flags: int = 0, end: bool = False) -> list[CW]:
    return [
        CW(dst=Dst.SP, reg_inc=True),
        CW(src=Src.MEM, dst=dst, mem_rd=True, addr_sp=True, flags=flags, end=end),
    ]


def branch(end_if: Cond) -> list[CW]:
    return [
        fetch_into(Dst.MDR, also_alu_b=True),
        CW(end_if=end_if),
        CW(src=Src.PCL, dst=Dst.PCL, alu=AluOp.ADD, alu_a_bus=True),
        CW(
            src=Src.PCH,
            dst=Dst.PCH,
            alu=AluOp.ADC,
            cin=Cin.LATCH,
            alu_a_bus=True,
            alu_b_m7ext=True,
            end=True,
        ),
    ]


def jmp_abs() -> list[CW]:
    # Hi byte overwrites PCH; do not PC+1 on that row (Φ2 would increment the new PC).
    return [
        fetch_into(Dst.T),
        fetch_into(Dst.PCH, inc=False),
        xfer(Src.T, Dst.PCL, end=True),
    ]


def jmp_ind() -> list[CW]:
    """NMOS: increment MARL only, no carry into MARH."""
    return (
        ea_abs()
        + [
            mem_to(Dst.T),
            CW(dst=Dst.MARL, reg_inc=True),
            mem_to(Dst.PCH),
            xfer(Src.T, Dst.PCL, end=True),
        ]
    )


def jsr() -> list[CW]:
    return (
        [fetch_into(Dst.T)]
        + push_src(Src.PCH)
        + push_src(Src.PCL)
        + [
            fetch_into(Dst.PCH, inc=False),
            xfer(Src.T, Dst.PCL, end=True),
        ]
    )


def rts() -> list[CW]:
    return pop_to(Dst.PCL) + pop_to(Dst.PCH) + [CW(pc_inc=True, end=True)]


def rti() -> list[CW]:
    return pop_to(Dst.P) + pop_to(Dst.PCL) + pop_to(Dst.PCH, end=True)


def pha() -> list[CW]:
    return with_end(push_src(Src.A))


def php() -> list[CW]:
    return with_end(push_src(Src.P, p_or=FU | FB))


def pla() -> list[CW]:
    return pop_to(Dst.A, flags=FLG_NZ, end=True)


def plp() -> list[CW]:
    return pop_to(Dst.P, end=True)


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
        push_src(Src.PCH)
        + push_src(Src.PCL)
        + push_src(Src.P, p_or=status_or)
        + p_or(0x04, end=False)
        + [
            xfer(Src.CONST, Dst.MARL, lo),
            xfer(Src.CONST, Dst.MARH, hi),
            mem_to(Dst.PCL),
            xfer(Src.CONST, Dst.MARL, (lo + 1) & 0xFF),
            xfer(Src.CONST, Dst.MARH, hi),
            mem_to(Dst.PCH, end=True),
        ]
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
