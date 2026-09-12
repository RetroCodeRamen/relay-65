"""VIA-like tick timer on the I/O card (semiconductor).

Hardware: Φ2 from the Control card clocks an 8-bit prescaler, then a
16-bit counter the 6502 can read. Without the divide, TICK_HI would
change during `hw_ticks()` (the CPU is slower than Φ2). IRQ when the
visible low byte wraps, if `$C022` bit0 is set.
"""

from __future__ import annotations

from .mmap import TICK_CTRL, TICK_HI, TICK_IFR, TICK_LO

PRESCALE = 256


class TickTimer:
    IRQ_ENABLE = 0x01
    IFR_IRQ = 0x80

    def __init__(self) -> None:
        self.div = 0
        self.ticks = 0
        self.ctrl = 0
        self.ifr = 0

    @property
    def irq_line(self) -> bool:
        return bool(self.ifr & self.IFR_IRQ)

    def on_phi2(self) -> None:
        self.div = (self.div + 1) & 0xFF
        if self.div != 0:
            return
        self.ticks = (self.ticks + 1) & 0xFFFF
        if (self.ctrl & self.IRQ_ENABLE) and (self.ticks & 0xFF) == 0:
            self.ifr |= self.IFR_IRQ

    def read(self, addr: int) -> int:
        if addr == TICK_LO:
            return self.ticks & 0xFF
        if addr == TICK_HI:
            return (self.ticks >> 8) & 0xFF
        if addr == TICK_CTRL:
            return self.ctrl
        if addr == TICK_IFR:
            return self.ifr
        return 0

    def write(self, addr: int, value: int) -> None:
        value &= 0xFF
        if addr == TICK_LO:
            self.ticks = (self.ticks & 0xFF00) | value
        elif addr == TICK_HI:
            self.ticks = (self.ticks & 0x00FF) | (value << 8)
        elif addr == TICK_CTRL:
            self.ctrl = value
        elif addr == TICK_IFR:
            self.ifr &= ~value
