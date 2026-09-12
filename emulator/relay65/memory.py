"""Memory/System card: SRAM, ROM, decode, bank latch.

The CPU never indexes this array by PC. It only presents MAR plus R/W.
"""

from __future__ import annotations

from . import mmap
from .esp32 import Esp32Nic
from .ide import CompactFlash
from .timer import TickTimer
from .uart import Uart


class MemoryCard:
    def __init__(self, uart: Uart) -> None:
        self.sram = bytearray(mmap.SRAM_SIZE)
        self.rom = bytearray(mmap.ROM_SIZE)
        self.bank = 0
        self.pages = [0, 1, 2, 3]
        self.rom_enable = True
        self.boot_jumper = False
        self.uart = uart
        self.timer = TickTimer()
        self.ide = CompactFlash()
        self.esp32 = Esp32Nic()

    def load_rom(self, origin: int, data: bytes) -> None:
        """EEPROM programmer, not a CPU write."""
        if origin < mmap.ROM_BASE:
            raise ValueError("ROM image origin must be in $E000-$FFFF")
        off = origin - mmap.ROM_BASE
        end = off + len(data)
        if end > mmap.ROM_SIZE:
            raise ValueError("ROM image extends past $FFFF")
        self.rom[off:end] = data

    def load_ram(self, addr: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.write((addr + i) & 0xFFFF, b, force_ram=True)

    def phys_ram(self, addr: int) -> int | None:
        addr &= 0xFFFF
        if mmap.IO_BASE <= addr <= mmap.IO_END:
            return None
        if mmap.SLOT0 <= addr < mmap.SLOT2:
            return None
        page = self.pages[addr >> mmap.PAGE_SHIFT] & mmap.MAX_PAGE
        return (page << mmap.PAGE_SHIFT) | (addr & (mmap.WINDOW_SIZE - 1))

    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if mmap.UART_DATA <= addr <= mmap.UART_CONTROL:
            return self.uart.read(addr)
        if mmap.TICK_LO <= addr <= mmap.TICK_IFR:
            return self.timer.read(addr)
        if addr == mmap.BANK_REG:
            return self.bank
        if addr == mmap.ROM_CTRL:
            return mmap.ROM_ENABLE if self.rom_enable else 0
        if addr == mmap.BOOT_JUMPER:
            return 0x01 if self.boot_jumper else 0
        if mmap.PAGE0 <= addr <= mmap.PAGE3:
            return self.pages[addr - mmap.PAGE0]
        if mmap.IDE_BASE <= addr <= mmap.IDE_END:
            return self.ide.read(addr - mmap.IDE_BASE)
        if mmap.ESP32_BASE <= addr <= mmap.ESP32_END:
            return self.esp32.read(addr - mmap.ESP32_BASE)
        if self.rom_enable and mmap.ROM_BASE <= addr <= mmap.ROM_END:
            return self.rom[addr - mmap.ROM_BASE]
        phys = self.phys_ram(addr)
        if phys is None:
            return 0xFF
        return self.sram[phys]

    def write(self, addr: int, value: int, force_ram: bool = False) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if not force_ram:
            if mmap.UART_DATA <= addr <= mmap.UART_CONTROL:
                self.uart.write(addr, value)
                return
            if mmap.TICK_LO <= addr <= mmap.TICK_IFR:
                self.timer.write(addr, value)
                return
            if addr == mmap.BANK_REG:
                self.bank = value
                self.pages[2] = mmap.contiki_bank_to_page(value)
                return
            if addr == mmap.ROM_CTRL:
                self.rom_enable = bool(value & mmap.ROM_ENABLE)
                return
            if mmap.PAGE0 <= addr <= mmap.PAGE3:
                self.pages[addr - mmap.PAGE0] = value & mmap.MAX_PAGE
                return
            if mmap.IDE_BASE <= addr <= mmap.IDE_END:
                self.ide.write(addr - mmap.IDE_BASE, value)
                return
            if mmap.ESP32_BASE <= addr <= mmap.ESP32_END:
                self.esp32.write(addr - mmap.ESP32_BASE, value)
                return
            # ROM overlay is read-only on the EEPROM. SRAM under it is always
            # writable (write-through) so a ROM loader can shadow $E000–$FFFF.
            if addr == mmap.BOOT_JUMPER:
                return
        phys = self.phys_ram(addr)
        if phys is None:
            return
        self.sram[phys] = value
