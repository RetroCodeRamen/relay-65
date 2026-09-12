from __future__ import annotations

from collections import deque
from typing import Callable

from .mmap import UART_CONTROL, UART_DATA, UART_RX_READY, UART_STATUS, UART_TX_READY


class Uart:
    """I/O card UART at $C000. Same registers the real console card should decode."""

    def __init__(self, on_tx: Callable[[int], None] | None = None) -> None:
        self.rx: deque[int] = deque()
        self.control = 0
        self.on_tx = on_tx
        self.tx_log = bytearray()

    def push_rx(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("ascii", errors="replace")
        self.rx.extend(data)

    def clear(self) -> None:
        """Front-panel RESET / CLR TTY: empty UART FIFOs. Does not affect RAM."""
        self.rx.clear()
        self.tx_log.clear()

    def read(self, addr: int) -> int:
        if addr == UART_DATA:
            if not self.rx:
                return 0
            return self.rx.popleft()
        if addr == UART_STATUS:
            status = UART_TX_READY
            if self.rx:
                status |= UART_RX_READY
            return status
        if addr == UART_CONTROL:
            return self.control
        return 0

    def write(self, addr: int, value: int) -> None:
        value &= 0xFF
        if addr == UART_DATA:
            self.tx_log.append(value)
            if self.on_tx:
                self.on_tx(value)
        elif addr == UART_CONTROL:
            self.control = value
