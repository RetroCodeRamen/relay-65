"""8-bit CompactFlash / IDE task file in slot 0 ($C100).

The 6502 only sees registers. Sector payload is 512 PIO bytes on DATA.
"""

from __future__ import annotations

IDE_DATA = 0
IDE_ERROR = 1
IDE_SEC_COUNT = 2
IDE_LBA0 = 3
IDE_LBA1 = 4
IDE_LBA2 = 5
IDE_LBA3 = 6
IDE_STATUS = 7

CMD_READ = 0x20
CMD_WRITE = 0x30
CMD_FLUSH = 0xE7
CMD_IDENTIFY = 0xEC
CMD_SET_FEATURES = 0xEF

ST_BUSY = 0x80
ST_READY = 0x40
ST_DRQ = 0x08
ST_ERR = 0x01

# Word 49 bit 9 = LBA (in IDENTIFY byte 99)
IDENTIFY_LBA_BYTE = 99
IDENTIFY_LBA_BIT = 0x02
IDENTIFY_LBA_COUNT = 120  # words 60–61, little-endian uint32


class CompactFlash:
    def __init__(self, image: bytes | None = None) -> None:
        if image is None:
            image = bytes(64 * 1024)
        self.disk = bytearray(image)
        if len(self.disk) < 512:
            self.disk.extend(b"\x00" * (512 - len(self.disk)))
        self.sectors = max(1, len(self.disk) // 512)
        self.error = 0
        self.features = 0
        self.sec_count = 1
        self.lba = [0, 0, 0, 0]
        self.status = ST_READY
        self.buf = bytearray(512)
        self.bi = 0
        self.pio_read = False
        self.pio_write = False
        self.devhead = 0xE0
        self._pending: int | None = None
        self._busy_seen = False

    def load_image(self, data: bytes) -> None:
        self.disk = bytearray(data)
        if len(self.disk) % 512:
            self.disk.extend(b"\x00" * (512 - len(self.disk) % 512))
        self.sectors = max(1, len(self.disk) // 512)

    def _lba(self) -> int:
        return (
            self.lba[0]
            | (self.lba[1] << 8)
            | (self.lba[2] << 16)
            | ((self.lba[3] & 0x0F) << 24)
        )

    def _master(self) -> bool:
        return (self.devhead & 0x10) == 0

    def read(self, offset: int) -> int:
        offset &= 7
        if not self._master() and offset != IDE_STATUS:
            return 0x00
        if offset == IDE_DATA:
            if not self.pio_read:
                return 0
            v = self.buf[self.bi]
            self.bi += 1
            if self.bi >= 512:
                self.pio_read = False
                self.status = ST_READY
                self.bi = 0
            return v
        if offset == IDE_ERROR:
            return self.error
        if offset == IDE_SEC_COUNT:
            return self.sec_count
        if offset == IDE_LBA0:
            return self.lba[0]
        if offset == IDE_LBA1:
            return self.lba[1]
        if offset == IDE_LBA2:
            return self.lba[2]
        if offset == IDE_LBA3:
            return self.lba[3]
        if offset == IDE_STATUS:
            if not self._master():
                return 0x00
            if self.status & ST_BUSY and self._pending is not None:
                if self._busy_seen:
                    self._finish(self._pending)
                    self._pending = None
                    self._busy_seen = False
                else:
                    self._busy_seen = True
            return self.status
        return 0

    def write(self, offset: int, value: int) -> None:
        offset &= 7
        value &= 0xFF
        if offset == IDE_DATA:
            if not self.pio_write:
                return
            self.buf[self.bi] = value
            self.bi += 1
            if self.bi >= 512:
                self._commit_write()
            return
        if offset == IDE_ERROR:
            self.features = value
            return
        if offset == IDE_SEC_COUNT:
            self.sec_count = value
            return
        if offset == IDE_LBA0:
            self.lba[0] = value
            return
        if offset == IDE_LBA1:
            self.lba[1] = value
            return
        if offset == IDE_LBA2:
            self.lba[2] = value
            return
        if offset == IDE_LBA3:
            self.lba[3] = value
            self.devhead = value
            return
        if offset == IDE_STATUS:
            self._command(value)

    def _command(self, cmd: int) -> None:
        if not self._master():
            return
        self.error = 0
        self._pending = cmd
        self._busy_seen = False
        self.status = ST_BUSY
        self.pio_read = False
        self.pio_write = False

    def _finish(self, cmd: int) -> None:
        if cmd == CMD_SET_FEATURES:
            self.status = ST_READY
            return
        if cmd == CMD_FLUSH:
            self.status = ST_READY
            return
        if cmd == CMD_IDENTIFY:
            self._fill_identify()
            self.bi = 0
            self.pio_read = True
            self.pio_write = False
            self.status = ST_READY | ST_DRQ
            return
        if cmd == CMD_READ:
            self._fill_sector()
            self.bi = 0
            self.pio_read = True
            self.pio_write = False
            self.status = ST_READY | ST_DRQ
            return
        if cmd == CMD_WRITE:
            self.bi = 0
            self.pio_read = False
            self.pio_write = True
            self.status = ST_READY | ST_DRQ
            return
        self.status = ST_READY | ST_ERR
        self.error = 0x04

    def _fill_identify(self) -> None:
        self.buf[:] = b"\x00" * 512
        self.buf[IDENTIFY_LBA_BYTE] = IDENTIFY_LBA_BIT
        n = self.sectors
        self.buf[IDENTIFY_LBA_COUNT] = n & 0xFF
        self.buf[IDENTIFY_LBA_COUNT + 1] = (n >> 8) & 0xFF
        self.buf[IDENTIFY_LBA_COUNT + 2] = (n >> 16) & 0xFF
        self.buf[IDENTIFY_LBA_COUNT + 3] = (n >> 24) & 0xFF

    def _fill_sector(self) -> None:
        off = self._lba() * 512
        chunk = self.disk[off : off + 512]
        self.buf[:] = b"\x00" * 512
        self.buf[: len(chunk)] = chunk

    def _commit_write(self) -> None:
        off = self._lba() * 512
        need = off + 512
        if need > len(self.disk):
            self.disk.extend(b"\x00" * (need - len(self.disk)))
            self.sectors = len(self.disk) // 512
        self.disk[off : off + 512] = self.buf
        self.pio_write = False
        self.bi = 0
        self.status = ST_READY
