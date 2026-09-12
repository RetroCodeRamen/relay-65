"""PC / Address card: PCL, PCH, MAR, MDR, IR.

A[15:0] on the system bus is always MAR, never live PC. Memory cycles
require MAR to be loaded first (settle, then R/W). That is how the
hardware will work; the emulator does not offer a shortcut.
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
