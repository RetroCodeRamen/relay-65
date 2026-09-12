"""Relay coil timing for the emulator oscillator.

Datasheet (user parts): 6 ms operate, 4 ms release. Each microstep is two
coil changes (Φ0 release previous SRC, Φ1 operate new SRC). Φ2 is a
semiconductor latch and does not add relay time.

Default clock pads each change to 10 ms so bounce and lag have room.
That is 20 ms per microstep — near the real machine, not host speed.

`--overclock` / the GUI OVERCLOCK switch skip the wait.
"""

from __future__ import annotations

import time

RELAY_OPERATE_MS = 6.0
RELAY_RELEASE_MS = 4.0
PHASE_LEWAY_MS = 10.0


def microstep_period_s(*, overclock: bool = False, datasheet: bool = False, phase_ms: float | None = None) -> float:
    if overclock:
        return 0.0
    if datasheet:
        return (RELAY_RELEASE_MS + RELAY_OPERATE_MS) / 1000.0
    phase = PHASE_LEWAY_MS if phase_ms is None else float(phase_ms)
    return 2.0 * (phase / 1000.0)


class WallClock:
    """Maps microsteps to wall time. CPU.step() stays instantaneous for tests."""

    def __init__(self) -> None:
        self.overclock = False
        self._datasheet = False
        self._phase_ms: float | None = None
        self.period_s = microstep_period_s()
        self._t0 = time.perf_counter()
        self._steps = 0

    def configure(self, *, overclock: bool = False, datasheet: bool = False, phase_ms: float | None = None) -> None:
        self._datasheet = datasheet
        self._phase_ms = phase_ms
        self.set_overclock(overclock)

    def set_overclock(self, on: bool) -> None:
        self.overclock = on
        self.period_s = microstep_period_s(
            overclock=on, datasheet=self._datasheet, phase_ms=self._phase_ms
        )
        self.sync()

    def sync(self) -> None:
        """Call when RUN starts so we do not burst to catch up on paused time."""
        self._t0 = time.perf_counter()
        self._steps = 0

    def account(self, n: int = 1) -> None:
        self._steps += n

    def due_steps(self, cap: int = 32) -> int:
        if self.overclock or self.period_s <= 0:
            return 0
        elapsed = time.perf_counter() - self._t0
        due = int(elapsed / self.period_s) - self._steps
        if due < 0:
            return 0
        return min(due, cap)

    def sleep_until_due(self) -> None:
        if self.overclock or self.period_s <= 0:
            return
        target = self._t0 + self._steps * self.period_s
        delay = target - time.perf_counter()
        if delay > 0.0002:
            time.sleep(delay)

    def label(self) -> str:
        if self.overclock or self.period_s <= 0:
            return "WARP"
        ms = self.period_s * 1000.0
        return f"REAL {ms:.0f}ms/µstep"
