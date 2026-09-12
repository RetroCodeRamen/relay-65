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
        self.running = True  # front-panel RUN/STOP; STOP is WAIT lamps on
        self.clock = WallClock()
        self.entry: int | None = None

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
        self.running = True

    def restart_loaded(self) -> None:
        """RESET after --load: ROM reset, then PC back at the loaded program."""
        self.reset()
        if self.entry is None:
            return
        self.cpu.pc = self.entry & 0xFFFF
        self.cpu.state = "FETCH"
        self.cpu.ustep = 0
        self.cpu.halted = False

    def step(self) -> None:
        if not self.running:
            return
        self.cpu.step()

    def step_instruction(self) -> None:
        self.cpu.step_instruction()
