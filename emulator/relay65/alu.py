"""ALU card: one 8-bit function block reused for math, PC, SP, and EA.

Hardware: ALU_A/ALU_B latches (register slices), adder/logic/shift relays,
C_latch (carry between microsteps), flag relays. Decimal mode pin from P.D.
"""

from __future__ import annotations

from .signals import FC, FD, FN, FU, FV, FZ, AluOp, Cin, FLG_C, FLG_N, FLG_V, FLG_Z


class ALUCard:
    def __init__(self) -> None:
        self.a = 0
        self.b = 0
        self.result = 0
        self.c_latch = 0
        self.flag_n = 0
        self.flag_z = 1
        self.flag_c = 0
        self.flag_v = 0

    def reset_latches(self) -> None:
        self.a = 0
        self.b = 0
        self.result = 0
        self.c_latch = 0

    def _cin(self, how: Cin, p: int) -> int:
        if how == Cin.ONE:
            return 1
        if how == Cin.P:
            return 1 if p & FC else 0
        if how == Cin.LATCH:
            return self.c_latch
        return 0

    def evaluate(
        self,
        op: AluOp,
        cin: Cin,
        p: int,
        invert_b: bool,
        a: int | None = None,
        b: int | None = None,
    ) -> int:
        a = (self.a if a is None else a) & 0xFF
        b = (self.b if b is None else b) & 0xFF
        if invert_b:
            b ^= 0xFF
        c = self._cin(cin, p)
        decimal = bool(p & FD)

        if op == AluOp.NOP:
            return self.result
        if op == AluOp.PASS_A:
            r = a
            self._zn(r)
            self.result = r
            return r
        if op == AluOp.AND:
            r = a & b
            self._zn(r)
            self.result = r
            return r
        if op == AluOp.OR:
            r = a | b
            self._zn(r)
            self.result = r
            return r
        if op == AluOp.XOR:
            r = a ^ b
            self._zn(r)
            self.result = r
            return r
        if op == AluOp.BIT:
            self.flag_z = int((a & b) == 0)
            self.flag_n = int((b & 0x80) != 0)
            self.flag_v = int((b & 0x40) != 0)
            self.result = a & b
            return self.result
        if op == AluOp.ASL:
            self.flag_c = (a >> 7) & 1
            r = (a << 1) & 0xFF
            self._zn(r)
            self.c_latch = self.flag_c
            self.result = r
            return r
        if op == AluOp.LSR:
            self.flag_c = a & 1
            r = a >> 1
            self._zn(r)
            self.c_latch = self.flag_c
            self.result = r
            return r
        if op == AluOp.ROL:
            self.flag_c = (a >> 7) & 1
            r = ((a << 1) | c) & 0xFF
            self._zn(r)
            self.c_latch = self.flag_c
            self.result = r
            return r
        if op == AluOp.ROR:
            self.flag_c = a & 1
            r = (a >> 1) | (c << 7)
            self._zn(r)
            self.c_latch = self.flag_c
            self.result = r
            return r
        if op in (AluOp.ADD, AluOp.ADC):
            if op == AluOp.ADD:
                c = 0 if cin == Cin.ZERO else self._cin(cin, p)
            r, cout, v = self._adc(a, b, c, decimal)
            self.flag_c = cout
            self.flag_v = v
            self.c_latch = cout
            self._zn(r)
            self.result = r
            return r
        return self.result

    def _adc(self, a: int, b: int, cin: int, decimal: bool) -> tuple[int, int, int]:
        binary = a + b + cin
        v = int((~(a ^ b) & (a ^ binary) & 0x80) != 0)
        if not decimal:
            return binary & 0xFF, int(binary > 0xFF), v
        nl = (a & 0x0F) + (b & 0x0F) + cin
        nh = (a >> 4) + (b >> 4)
        if nl > 9:
            nl += 6
            nh += 1
        cout = 0
        if nh > 9:
            nh += 6
            cout = 1
        return ((nh << 4) | (nl & 0x0F)) & 0xFF, cout, v

    def _zn(self, r: int) -> None:
        self.flag_z = int((r & 0xFF) == 0)
        self.flag_n = int((r & 0x80) != 0)

    def apply_flags(self, p: int, mask: int) -> int:
        if mask & FLG_N:
            p = (p & ~FN) | (FN if self.flag_n else 0)
        if mask & FLG_Z:
            p = (p & ~FZ) | (FZ if self.flag_z else 0)
        if mask & FLG_C:
            p = (p & ~FC) | (FC if self.flag_c else 0)
        if mask & FLG_V:
            p = (p & ~FV) | (FV if self.flag_v else 0)
        return p | FU
