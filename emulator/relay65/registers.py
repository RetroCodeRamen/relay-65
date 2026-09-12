"""Register bank card: identical 8-bit OE/LOAD slices.

v0.1 slices: A, X, Y, SP, P, T.
PC/MAR/MDR/IR live on the address card but use the same slice schematic.
"""

from __future__ import annotations

from .signals import FU, FI


class RegisterCard:
    def __init__(self) -> None:
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0
        self.p = FU | FI
        self.t = 0

    def reset_status(self) -> None:
        """NMOS-like RESET: set I. Do not touch A,X,Y,SP."""
        self.p = (self.p | FU | FI) & 0xFF
