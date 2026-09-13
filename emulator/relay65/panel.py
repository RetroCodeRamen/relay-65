"""Front-panel switches + lamp display. Serial stays on a TCP port.

Keyboard (this terminal):
  Axxxx  load 16-bit address switches (hex)
  Dxx    load 8-bit data switches
  E      EXAMINE
  N      EXAMINE NEXT
  P      DEPOSIT
  O      DEPOSIT NEXT
  R      RUN
  S      STOP
  space  single-step one 6502 instruction
  T      cycle SPEED (RELAY → 1s=1min → WARP)
  Q      quit
"""

from __future__ import annotations

import select
import sys
import termios
import tty

from .leds import sample
from .panelops import deposit, deposit_next, examine, examine_next


class FrontPanel:
    def __init__(self, machine) -> None:
        self.machine = machine
        self.sw_addr = 0
        self.sw_data = 0
        self._hex = ""
        self._mode = ""  # "A" or "D" while typing hex
        self._old = None

    def enter_cbreak(self) -> None:
        if not sys.stdin.isatty():
            return
        self._old = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    def leave_cbreak(self) -> None:
        if self._old is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old)
            self._old = None

    def render(self) -> str:
        lamps = sample(self.machine)
        sw_a = f"{self.sw_addr:016b}"
        sw_d = f"{self.sw_data:08b}"
        sw_a = sw_a[:8] + " " + sw_a[8:]
        hint = ""
        if self._mode:
            hint = f"  typing {self._mode}{self._hex}_"
        return "\n".join(
            [
                "=== RELAY-65 FRONT PANEL  (* on  . off) ===",
                lamps.text(),
                self.machine.clock.runtime_label() + f"  {self.machine.clock.label()}",
                f"SW A {sw_a.replace('1', '^').replace('0', '_')}  ${self.sw_addr:04X}",
                f"SW D {sw_d.replace('1', '^').replace('0', '_')}          ${self.sw_data:02X}{hint}",
                "Axxxx Dxx  E examine  N next  P deposit  O dep-next  R run  S stop  T speed  SPACE step  I reset  Q quit",
                "Serial is the other connector (TCP --serial-port, default 6502).",
            ]
        )

    def poll_key(self) -> bool:
        """Return False to quit."""
        if not sys.stdin.isatty():
            return True
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if not r:
            return True
        ch = sys.stdin.read(1)
        return self.handle(ch)

    def handle(self, ch: str) -> bool:
        if not ch:
            return True
        if ch in "\x03\x04qQ":
            return False
        if self._mode:
            if ch in "\r\n":
                self._commit_hex()
                return True
            if ch in "\x08\x7f":
                self._hex = self._hex[:-1]
                return True
            if ch in "0123456789abcdefABCDEF":
                self._hex += ch
                need = 4 if self._mode == "A" else 2
                if len(self._hex) >= need:
                    self._commit_hex()
                return True
            self._mode = ""
            self._hex = ""
        up = ch.upper()
        if up == "A":
            self._mode = "A"
            self._hex = ""
        elif up == "D":
            self._mode = "D"
            self._hex = ""
        elif up == "E":
            self.examine()
        elif up == "N":
            self.sw_addr = examine_next(self.machine, self.sw_addr)
        elif up == "P":
            self.deposit()
        elif up == "O":
            self.sw_addr = deposit_next(self.machine, self.sw_addr, self.sw_data)
        elif up == "R":
            self.machine.running = True
        elif up == "S":
            self.machine.running = False
        elif ch == " ":
            self.machine.running = False
            self.machine.step_instruction()
        elif up == "I":
            self.machine.restart_loaded()
        elif up == "T":
            self.machine.clock.cycle_speed()
        return True

    def _commit_hex(self) -> None:
        if not self._hex:
            self._mode = ""
            return
        val = int(self._hex, 16)
        if self._mode == "A":
            self.sw_addr = val & 0xFFFF
        else:
            self.sw_data = val & 0xFF
        self._mode = ""
        self._hex = ""

    def examine(self) -> None:
        examine(self.machine, self.sw_addr)

    def deposit(self) -> None:
        deposit(self.machine, self.sw_addr, self.sw_data)
