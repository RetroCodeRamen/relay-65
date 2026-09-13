"""Passive backplane: wires cards together. No extra intelligence here."""

from __future__ import annotations

from .cpu import CPU
from .memory import MemoryCard
from .mmap import ROM_BASE
from .timing import WallClock
from .uart import Uart


class Machine:
    def __init__(self, on_tx=None) -> None:
        self.uart = Uart(on_tx=on_tx)
        self.memory = MemoryCard(self.uart)
        self.cpu = CPU(self.memory)
        self.clock = WallClock()
        self._running = True  # front-panel RUN/STOP; STOP is WAIT lamps on
        self.clock.set_running(True)
        self.entry: int | None = None

    @property
    def running(self) -> bool:
        return self._running

    @running.setter
    def running(self, on: bool) -> None:
        on = bool(on)
        if on == self._running:
            return
        self._running = on
        self.clock.set_running(on)

    def load_rom(self, origin: int, data: bytes) -> None:
        self.memory.load_rom(origin, data)

    def load_ram(self, addr: int, data: bytes) -> None:
        self.memory.load_ram(addr, data)

    def load_image(self, origin: int, data: bytes) -> None:
        if origin >= ROM_BASE:
            self.load_rom(origin, data)
        else:
            self.load_ram(origin, data)

    def insert_cf(self, image: bytes, *, boot_jumper: bool = False) -> None:
        """Insert a CompactFlash card. Same as plugging one into the slot."""
        self.memory.ide.load_image(image)
        self.memory.boot_jumper = boot_jumper
        self.memory.rom_enable = True
        self.entry = None

    def load_fuzix(self, data: bytes, disk: bytes | None = None) -> None:
        """Insert a CF card (kernel at LBA 1). RESET still fetches the monitor."""
        from .diskimg import FS_LBA, build_cf

        if disk is not None and len(disk) >= (FS_LBA + 1) * 512 and disk[510:512] == b"\x55\xAA":
            self.insert_cf(disk, boot_jumper=True)
            return
        self.insert_cf(build_cf(data, disk), boot_jumper=True)

    def reset(self) -> None:
        self.cpu.reset()

    def restart_loaded(self) -> None:
        """Front-panel RESET: back at the loaded program (or monitor RESET).

        RUN/STOP is unchanged: if it was running it keeps running; if it was
        stopped it stays stopped.
        """
        running = self.running
        self.reset()
        if self.entry is not None:
            self.cpu.pc = self.entry & 0xFFFF
            self.cpu.state = "FETCH"
            self.cpu.ustep = 0
            self.cpu.halted = False
        self.running = running
        if running:
            self.clock.sync()

    def step(self) -> None:
        if not self.running:
            return
        before = self.cpu.microcycles
        self.cpu.step()
        self.clock.add_usteps(self.cpu.microcycles - before)

    def step_instruction(self) -> None:
        before = self.cpu.microcycles
        self.cpu.step_instruction()
        self.clock.add_usteps(self.cpu.microcycles - before)
