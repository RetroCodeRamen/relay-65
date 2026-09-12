"""Altair-style front-panel examine / deposit.

Address paddles select a location. Data paddles are the byte you deposit.
EXAMINE loads MAR/PC from the address paddles and shows that byte on the
data lamps. EX NEXT steps the address. DEPOSIT writes the data paddles at
the current address. DEP NEXT writes, then examines the following byte.
"""

from __future__ import annotations


def examine(machine, addr: int) -> int:
    addr &= 0xFFFF
    cpu = machine.cpu
    cpu.addr.marl = addr & 0xFF
    cpu.addr.marh = (addr >> 8) & 0xFF
    cpu.last_bus = machine.memory.read(addr)
    cpu.addr.mdr = cpu.last_bus
    cpu.pc = addr
    return addr


def examine_next(machine, addr: int) -> int:
    return examine(machine, (addr + 1) & 0xFFFF)


def deposit(machine, addr: int, data: int) -> int:
    addr &= 0xFFFF
    machine.memory.write(addr, data & 0xFF)
    return examine(machine, addr)


def deposit_next(machine, addr: int, data: int) -> int:
    deposit(machine, addr, data)
    return examine(machine, (addr + 1) & 0xFFFF)
