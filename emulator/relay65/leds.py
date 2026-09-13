"""Front-panel lamps.

Machine rows tap the backplane: MAR, last bus, IR, sequencer.
6502 rows tap architectural registers (same bits the instruction set sees).
The chassis has room for both; neither replaces the other.
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
    x: int
    y: int
    sp: int
    p: int
    ustep: int
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
            f"ADDR {bits(self.addr, 16)}  ${self.addr:04X}  MAR",
            f"DATA {bits(self.data, 8)}          ${self.data:02X}",
            f"IR   {bits(self.ir, 8)}          ${self.ir:02X}  u={self.ustep} {self.phase}",
            (
                f"STAT RUN{run} WAIT{wait}  I{'*' if self.flag_i else '.'} "
                f"IRQ{'*' if self.irq else '.'}  "
                f"N{'*' if self.flag_n else '.'} Z{'*' if self.flag_z else '.'} "
                f"C{'*' if self.flag_c else '.'} V{'*' if self.flag_v else '.'}"
            ),
            f"PC   {bits(self.pc, 16)}  ${self.pc:04X}",
            (
                f"A    {bits(self.a, 8)}  ${self.a:02X}   "
                f"X {bits(self.x, 8)}  ${self.x:02X}   "
                f"Y {bits(self.y, 8)}  ${self.y:02X}"
            ),
            f"SP   {bits(self.sp, 8)}  ${self.sp:02X}   P {bits(self.p, 8)}  ${self.p:02X}",
        ]

    def text(self) -> str:
        return "\n".join(self.lines())

    def one_line(self) -> str:
        """Single-line strip for --leds (stderr), leaves serial stdout alone."""
        return (
            f"A {bits(self.addr, 16)} D {bits(self.data, 8)} "
            f"IR {bits(self.ir, 8)} PC ${self.pc:04X} "
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
        x=cpu.reg.x,
        y=cpu.reg.y,
        sp=cpu.reg.sp,
        p=p,
        ustep=cpu.ustep,
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
