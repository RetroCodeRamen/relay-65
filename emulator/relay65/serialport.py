"""UART as a second connector: TCP socket, like a serial terminal on the real box."""

from __future__ import annotations

import select
import socket


class SerialPort:
    def __init__(self, port: int, host: str = "127.0.0.1") -> None:
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1)
        self.sock.setblocking(False)
        self.client: socket.socket | None = None
        self._tx_hold = bytearray()

    def accept(self) -> None:
        if self.client is not None:
            return
        try:
            conn, _ = self.sock.accept()
        except BlockingIOError:
            return
        conn.setblocking(False)
        self.client = conn
        if self._tx_hold:
            try:
                conn.sendall(bytes(self._tx_hold))
            except OSError:
                self.client = None
                return
            self._tx_hold.clear()

    def pump_rx(self, machine) -> None:
        self.accept()
        if self.client is None:
            return
        try:
            data = self.client.recv(256)
        except (BlockingIOError, ConnectionResetError, OSError):
            return
        if data == b"":
            self.client.close()
            self.client = None
            return
        machine.uart.push_rx(data)

    def attach_tx(self, machine) -> None:
        def tx(ch: int) -> None:
            if self.client is None:
                self._tx_hold.append(ch)
                return
            try:
                self.client.sendall(bytes([ch]))
            except OSError:
                self.client = None
                self._tx_hold.append(ch)

        machine.uart.on_tx = tx

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except OSError:
                pass
        self.sock.close()
