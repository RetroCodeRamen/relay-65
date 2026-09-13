"""Horizontal microinstruction = one EEPROM row.

Bit fields are the coil-driver / select lines on the Control card.
See docs/RELAY-CPU.md §3–§6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Src(IntEnum):
    NONE = 0
    A = 1
    X = 2
    Y = 3
    SP = 4
    P = 5
    PCL = 6
    PCH = 7
    MDR = 8
    T = 9
    MEM = 10
    ALU = 11
    CONST = 12
    M7EXT = 13  # MDR bit7 replicated to D[7:0]
    MARL = 14
    MARH = 15


class Dst(IntEnum):
    NONE = 0
    A = 1
    X = 2
    Y = 3
    SP = 4
    P = 5
    PCL = 6
    PCH = 7
    MDR = 8
    T = 9
    MARL = 10
    MARH = 11
    ALU_A = 12
    ALU_B = 13
    IR = 14
    MEM = 15  # write strobe; data already on the bus from SRC


class AluOp(IntEnum):
    NOP = 0
    PASS_A = 1
    ADD = 2
    ADC = 3
    AND = 4
    OR = 5
    XOR = 6
    ASL = 7
    LSR = 8
    ROL = 9
    ROR = 10
    BIT = 11  # Z from A&B; N,V from B


class Cin(IntEnum):
    ZERO = 0
    ONE = 1
    P = 2  # processor carry
    LATCH = 3  # ALU C_latch from previous op


class Cond(IntEnum):
    NEVER = 0
    ALWAYS = 1
    Z = 2
    NZ = 3
    C = 4
    NC = 5
    N = 6
    NN = 7
    V = 8
    NV = 9


# P register bits (stored). B is not stored; see docs.
FN = 0x80
FV = 0x40
FU = 0x20
FB = 0x10
FD = 0x08
FI = 0x04
FZ = 0x02
FC = 0x01

FLG_N = 1
FLG_Z = 2
FLG_C = 4
FLG_V = 8
FLG_NZ = FLG_N | FLG_Z
FLG_NZC = FLG_NZ | FLG_C
FLG_NZCV = FLG_NZC | FLG_V
FLG_NVZ = FLG_N | FLG_V | FLG_Z


@dataclass
class CW:
    """One microstep. Hardware: one EEPROM word."""

    src: Src = Src.NONE
    dst: Dst = Dst.NONE
    alu: AluOp = AluOp.NOP
    cin: Cin = Cin.ZERO
    flags: int = 0
    const: int = 0
    mem_rd: bool = False
    mem_wr: bool = False
    end: bool = False
    end_if: Cond = Cond.NEVER
    # When pushing P, OR this onto the bus (B+U for PHP/BRK).
    p_or: int = 0
    invert_b: bool = False  # invert ALU_B before ADD (SBC/CMP)
    # Byte 6 coil lines. Not host-only shortcuts.
    addr_pc: bool = False  # A[15:0] = PC
    pc_inc: bool = False  # Φ2 LOAD PC from 16-bit +1 (not the bus)
    addr_sp: bool = False  # A[15:0] = $0100|SP  (+8 DPDT on the address mux)
    reg_inc: bool = False  # 8-bit +1 into DST (or SP if DST is MEM/NONE)
    reg_dec: bool = False  # 8-bit −1, same helper (~10–12 DPDT, not a 2nd ALU)
    alu_a_bus: bool = False  # ALU A-input = live bus, not ALU_A latch (~4 DPDT)
    alu_b_m7ext: bool = False  # ALU B-input = MDR bit7 extended (~1–4 DPDT)
    also_alu_b: bool = False  # Φ2 also LOAD ALU_B from the bus (0 extra data relays)

    def pack(self) -> bytes:
        """Eight EEPROM bytes. Layout is frozen in docs/RELAY-CPU.md §6."""
        b0 = (int(self.src) & 0x0F) | ((int(self.dst) & 0x0F) << 4)
        b1 = (
            (int(self.alu) & 0x0F)
            | ((int(self.cin) & 0x03) << 4)
            | (int(self.mem_rd) << 6)
            | (int(self.mem_wr) << 7)
        )
        b2 = (self.flags & 0x0F) | (int(self.end) << 4) | (int(self.invert_b) << 5)
        b3 = int(self.end_if) & 0x0F
        b6 = (
            int(self.addr_pc)
            | (int(self.pc_inc) << 1)
            | (int(self.addr_sp) << 2)
            | (int(self.reg_inc) << 3)
            | (int(self.reg_dec) << 4)
            | (int(self.alu_a_bus) << 5)
            | (int(self.alu_b_m7ext) << 6)
            | (int(self.also_alu_b) << 7)
        )
        return bytes([b0, b1, b2, b3, self.const & 0xFF, self.p_or & 0xFF, b6, 0])

    @classmethod
    def unpack(cls, raw: bytes) -> CW:
        if len(raw) < 8:
            raise ValueError("control word is 8 bytes")
        return cls(
            src=Src(raw[0] & 0x0F),
            dst=Dst((raw[0] >> 4) & 0x0F),
            alu=AluOp(raw[1] & 0x0F),
            cin=Cin((raw[1] >> 4) & 0x03),
            mem_rd=bool(raw[1] & 0x40),
            mem_wr=bool(raw[1] & 0x80),
            flags=raw[2] & 0x0F,
            end=bool(raw[2] & 0x10),
            invert_b=bool(raw[2] & 0x20),
            end_if=Cond(raw[3] & 0x0F),
            const=raw[4],
            p_or=raw[5],
            addr_pc=bool(raw[6] & 0x01),
            pc_inc=bool(raw[6] & 0x02),
            addr_sp=bool(raw[6] & 0x04),
            reg_inc=bool(raw[6] & 0x08),
            reg_dec=bool(raw[6] & 0x10),
            alu_a_bus=bool(raw[6] & 0x20),
            alu_b_m7ext=bool(raw[6] & 0x40),
            also_alu_b=bool(raw[6] & 0x80),
        )


JAM_WORD = bytes([0xFF] * 8)


def xfer(
    src: Src,
    dst: Dst,
    const: int = 0,
    p_or: int = 0,
    *,
    flags: int = 0,
    end: bool = False,
    mem_wr: bool = False,
) -> CW:
    return CW(src=src, dst=dst, const=const, p_or=p_or, flags=flags, end=end, mem_wr=mem_wr)


def alu(op: AluOp, flags: int = 0, cin: Cin = Cin.ZERO, invert_b: bool = False) -> CW:
    return CW(alu=op, flags=flags, cin=cin, invert_b=invert_b)


def END() -> CW:
    return CW(end=True)
