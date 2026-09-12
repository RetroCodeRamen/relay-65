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
        return bytes([b0, b1, b2, b3, self.const & 0xFF, self.p_or & 0xFF, 0, 0])

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
        )


JAM_WORD = bytes([0xFF] * 8)


def xfer(src: Src, dst: Dst, const: int = 0, p_or: int = 0) -> CW:
    return CW(src=src, dst=dst, const=const, p_or=p_or)


def alu(op: AluOp, flags: int = 0, cin: Cin = Cin.ZERO, invert_b: bool = False) -> CW:
    return CW(alu=op, flags=flags, cin=cin, invert_b=invert_b)


def END() -> CW:
    return CW(end=True)
