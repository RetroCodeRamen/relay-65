"""ESP32 network card in slot 1 ($C200).

The 6502 never speaks TCP. It pokes a mailbox; the ESP32 talks to the
network. Frozen 6502 API: listen / accept / read / write / close.

This Python class is a stub for bring-up: canned HTTP body, always-up
link, no listen/accept. Replace it with real ESP32 firmware that implements
the same registers — do not grow a TCP stack on the 6502 to paper over it.
"""

from __future__ import annotations

ID_E = 0x45  # 'E'
ID_2 = 0x32  # '2'

ST_RX = 0x01
ST_TX_READY = 0x02
ST_LINK = 0x04
ST_ERR = 0x80

CMD_NOP = 0x00
CMD_TX = 0x01
CMD_RX = 0x02  # consume RX into DATA stream
CMD_HTTP = 0x10  # buffer is a host-relative path; ESP32 does the GET

REG_ID = 0
REG_MAGIC = 1
REG_STATUS = 2
REG_CMD = 3
REG_DATA = 4
REG_LENL = 5
REG_LENH = 6
REG_CTRL = 7

CANNED_HTTP = (
    b"HTTP/1.0 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 19\r\n"
    b"\r\n"
    b"Relay-65 click-click"
)


class Esp32Nic:
    def __init__(self) -> None:
        self.tx = bytearray()
        self.rx = bytearray(CANNED_HTTP)
        self.tx_log: list[bytes] = []
        self.len_lo = 0
        self.len_hi = 0
        self.ctrl = 0
        self.stream = bytearray()
        self.si = 0
        self.writing = False

    @property
    def length(self) -> int:
        return self.len_lo | (self.len_hi << 8)

    def status(self) -> int:
        st = ST_TX_READY | ST_LINK
        if self.rx:
            st |= ST_RX
        return st

    def read(self, offset: int) -> int:
        offset &= 0x0F
        if offset == REG_ID:
            return ID_E
        if offset == REG_MAGIC:
            return ID_2
        if offset == REG_STATUS:
            return self.status()
        if offset == REG_CMD:
            return 0
        if offset == REG_DATA:
            if self.si < len(self.stream):
                v = self.stream[self.si]
                self.si += 1
                return v
            return 0
        if offset == REG_LENL:
            return self.len_lo
        if offset == REG_LENH:
            return self.len_hi
        if offset == REG_CTRL:
            return self.ctrl
        return 0xFF

    def write(self, offset: int, value: int) -> None:
        offset &= 0x0F
        value &= 0xFF
        if offset == REG_CMD:
            self._command(value)
            return
        if offset == REG_DATA:
            if self.writing:
                self.stream.append(value)
                if self.length and len(self.stream) >= self.length:
                    self.writing = False
                    self._finish_tx()
            return
        if offset == REG_LENL:
            self.len_lo = value
            return
        if offset == REG_LENH:
            self.len_hi = value
            return
        if offset == REG_CTRL:
            self.ctrl = value

    def _command(self, cmd: int) -> None:
        if cmd == CMD_NOP:
            return
        if cmd == CMD_TX:
            self.stream = bytearray()
            self.si = 0
            self.writing = True
            if self.length == 0:
                self.writing = False
            return
        if cmd == CMD_RX:
            self.stream = bytearray(self.rx)
            self.si = 0
            self.len_lo = len(self.stream) & 0xFF
            self.len_hi = (len(self.stream) >> 8) & 0xFF
            self.writing = False
            return
        if cmd == CMD_HTTP:
            self.writing = True
            self.stream = bytearray()
            self.si = 0
            if self.length == 0:
                self.writing = False
                self._http(b"/")

    def _finish_tx(self) -> None:
        payload = bytes(self.stream)
        self.tx_log.append(payload)
        self.tx = bytearray(payload)
        # Offload: any TX is treated as an HTTP path or raw GET.
        if payload.upper().startswith(b"GET ") or payload.startswith(b"/"):
            self._http(payload)
        else:
            self.rx = bytearray(CANNED_HTTP)

    def _http(self, req: bytes) -> None:
        self.rx = bytearray(CANNED_HTTP)
        self.tx_log.append(b"HTTP " + req)
