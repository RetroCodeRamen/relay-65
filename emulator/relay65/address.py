"""PC / Address card: PCL, PCH, MAR, MDR, IR.

Opcode and operand fetches put **PC** on A[15:0] (`CW.addr_pc`). Effective
address, stack, and vector cycles still load **MAR** first, then R/W.
PC+1 is a dedicated incrementer (`CW.pc_inc`), not the general ALU.
"""

from __future__ import annotations


class AddressCard:
    def __init__(self) -> None:
        self.pcl = 0
        self.pch = 0
        self.marl = 0
        self.marh = 0
        self.mdr = 0
        self.ir = 0

    @property
    def pc(self) -> int:
        return (self.pch << 8) | self.pcl

    @pc.setter
    def pc(self, value: int) -> None:
        value &= 0xFFFF
        self.pcl = value & 0xFF
        self.pch = (value >> 8) & 0xFF

    @property
    def mar(self) -> int:
        return (self.marh << 8) | self.marl
