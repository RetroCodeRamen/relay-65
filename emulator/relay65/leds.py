"""Altair-style front-panel lamps.

These are the same signals lamps would tap on the real backplane:
A[15:0] from MAR, D[7:0] from the internal/system data bus, IR, and a
few status bits from the control/status cards.

On = '*'  Off = '.'   so you can read the machine with no GUI, like
the row of lamps on an Altair 8800.
"""

from __future__ import annotations

from dataclasses import dataclass

from .signals import FC, FI, FN, FV, FZ


def bits(value: int, width: int) -> str:
    chars = []
    for i in range(width - 1, -1, -1):
        chars.append("*" if value & (1 << i) else ".")
        if i and i % 8 == 0:
            chars.append(" ")
    return "".join(chars)


@dataclass
class LampState:
    addr: int
    data: int
    ir: int
    pc: int
    a: int
    running: bool
    wait: bool
    irq: bool
    flag_i: bool
    flag_n: bool
    flag_z: bool
    flag_c: bool
    flag_v: bool
    phase: str

    def lines(self) -> list[str]:
        run = "*" if self.running and not self.wait else "."
        wait = "*" if self.wait or not self.running else "."
        return [
            f"ADDR {bits(self.addr, 16)}  ${self.addr:04X}",
            f"DATA {bits(self.data, 8)}          ${self.data:02X}",
            f"IR   {bits(self.ir, 8)}          ${self.ir:02X}  PC=${self.pc:04X} A=${self.a:02X}",
            (
                f"STAT RUN{run} WAIT{wait}  I{'*' if self.flag_i else '.'} "
                f"IRQ{'*' if self.irq else '.'}  "
                f"N{'*' if self.flag_n else '.'} Z{'*' if self.flag_z else '.'} "
                f"C{'*' if self.flag_c else '.'} V{'*' if self.flag_v else '.'}  "
                f"{self.phase}"
            ),
        ]

    def text(self) -> str:
        return "\n".join(self.lines())

    def one_line(self) -> str:
        """Single-line strip for --leds (stderr), leaves serial stdout alone."""
        return (
            f"A {bits(self.addr, 16)} D {bits(self.data, 8)} "
            f"IR {bits(self.ir, 8)} "
            f"{'RUN' if self.running and not self.wait else 'STOP'} "
            f"{self.phase}"
        )


def sample(machine) -> LampState:
    cpu = machine.cpu
    p = cpu.reg.p
    return LampState(
        addr=cpu.addr.mar,
        data=cpu.last_bus,
        ir=cpu.addr.ir,
        pc=cpu.addr.pc,
        a=cpu.reg.a,
        running=machine.running,
        wait=cpu.halted,
        irq=machine.memory.timer.irq_line,
        flag_i=bool(p & FI),
        flag_n=bool(p & FN),
        flag_z=bool(p & FZ),
        flag_c=bool(p & FC),
        flag_v=bool(p & FV),
        phase=f"{cpu.state} Φ{cpu.phi}",
    )
