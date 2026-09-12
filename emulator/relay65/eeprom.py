"""Packed control-store images the Control card EEPROMs will hold.

Authoring stays in isa.py as lists of CW. This module is the bit layout
the hardware burns. Unused execute rows are JAM (0xFF…), not NOP.
"""

from __future__ import annotations

from . import isa
from .signals import CW, JAM_WORD

WORD = 8
USTEPS = 64
N_OPCODES = 256


def pack_page(cws: list[CW], slots: int) -> bytes:
    if len(cws) > slots:
        raise ValueError(f"microprogram length {len(cws)} exceeds {slots} EEPROM rows")
    out = bytearray(slots * WORD)
    for i in range(slots):
        off = i * WORD
        if i < len(cws):
            out[off : off + WORD] = cws[i].pack()
        else:
            out[off : off + WORD] = JAM_WORD
    return bytes(out)


def pack_execute(rom: list[list[CW] | None]) -> bytes:
    out = bytearray(N_OPCODES * USTEPS * WORD)
    for ir, prog in enumerate(rom):
        base = ir * USTEPS * WORD
        if prog is None:
            out[base : base + USTEPS * WORD] = JAM_WORD * USTEPS
            continue
        if len(prog) > USTEPS:
            raise ValueError(f"opcode ${ir:02X} needs {len(prog)} rows (max {USTEPS})")
        page = pack_page(prog, USTEPS)
        out[base : base + len(page)] = page
    return bytes(out)


class ControlStore:
    """Four EEPROM regions: FETCH, RESET, IRQ, NMI, plus execute {IR,uStep}."""

    def __init__(self, fetch: bytes, reset: bytes, irq: bytes, nmi: bytes, execute: bytes) -> None:
        self.fetch = fetch
        self.reset = reset
        self.irq = irq
        self.nmi = nmi
        self.execute = execute

    @classmethod
    def from_isa(cls) -> ControlStore:
        return cls(
            pack_page(isa.FETCH(), USTEPS),
            pack_page(isa.RESET(), USTEPS),
            pack_page(isa.irq(), USTEPS),
            pack_page(isa.nmi(), USTEPS),
            pack_execute(isa.build_execute_rom()),
        )

    def word(self, page: bytes, ustep: int) -> bytes | None:
        off = ustep * WORD
        raw = page[off : off + WORD]
        if len(raw) < WORD or raw == JAM_WORD:
            return None
        return raw

    def execute_word(self, ir: int, ustep: int) -> bytes | None:
        off = ((ir & 0xFF) * USTEPS + (ustep & (USTEPS - 1))) * WORD
        raw = self.execute[off : off + WORD]
        if raw == JAM_WORD:
            return None
        return raw
