"""PC / Address card: PCL, PCH, MAR, MDR, IR.

Design B (real relays, not a host shortcut):

- ADDR_PC is an 8 DPDT 2:1 on A[15:0]: PC vs (MAR or stack). Opcode/operand
  fetch asserts it; EA and data cycles leave it off.
- ADDR_SP is a second 8 DPDT 2:1 on the MAR side: A = $0100|SP vs MAR.
  Stack cycles assert it so PHA/JSR do not copy SP through the internal bus.
- PC+1 is a dedicated 16-bit incrementer from PC Q contacts (XOR + propagate),
  loaded into PC at Φ2. It is not the ALU and it is not free: PC_INC is a
  real LOAD. It may share Φ2 with another destination (IR/MDR/MAR) because
  the incrementer does not use the internal bus.
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

    def address_bus(self, addr_pc: bool, addr_sp: bool = False, sp: int = 0) -> int:
        """A[15:0] after ADDR_PC / ADDR_SP. SRAM decode sees this word.

        ADDR_PC wins if both bits are set (microcode must not do that).
        """
        if addr_pc:
            return self.pc
        if addr_sp:
            return 0x0100 | (sp & 0xFF)
        return self.mar

    def load_pc_plus1(self) -> None:
        """Φ2 LOAD of the dedicated incrementer into PC. Inputs are PC Q."""
        self.pc = (self.pc + 1) & 0xFFFF
