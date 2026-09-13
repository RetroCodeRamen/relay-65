"""Relay coil timing for the emulator oscillator.

Datasheet (user parts): 6 ms operate, 4 ms release. Each microstep is two
coil changes (Φ0 release previous SRC, Φ1 operate new SRC). Φ2 is a
semiconductor latch and does not add relay time.

Default clock pads each change to 10 ms so bounce and lag have room.
That is 20 ms per microstep — near the real machine, not host speed.

`--overclock` / WARP skips the wait. SPEED on the panel cycles
RELAY (1:1) → 1s=1min (60×) → WARP (host max).
"""

from __future__ import annotations

import time

RELAY_OPERATE_MS = 6.0
RELAY_RELEASE_MS = 4.0
PHASE_LEWAY_MS = 10.0
SPEEDS = ("relay", "minute", "warp")
# 1 host second = 1 minute of relay-clock time.
MINUTE_FACTOR = 60.0


def microstep_period_s(*, overclock: bool = False, datasheet: bool = False, phase_ms: float | None = None) -> float:
    if overclock:
        return 0.0
    if datasheet:
        return (RELAY_RELEASE_MS + RELAY_OPERATE_MS) / 1000.0
    phase = PHASE_LEWAY_MS if phase_ms is None else float(phase_ms)
    return 2.0 * (phase / 1000.0)


def format_duration(seconds: float) -> str:
    """Compact stopwatch text: 12.3s, 4m 12s, 2h 14m 03s, 3d 04h 12m."""
    if seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    days, rem = divmod(whole, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{seconds:.1f}s"


class WallClock:
    """Maps microsteps to wall time. CPU.step() stays instantaneous for tests."""

    def __init__(self) -> None:
        self.overclock = False
        self.speed = "relay"
        self._datasheet = False
        self._phase_ms: float | None = None
        self.period_s = microstep_period_s()
        self._t0 = time.perf_counter()
        self._steps = 0
        self._usteps = 0
        self._host_acc = 0.0
        self._run_t0: float | None = None

    def configure(
        self,
        *,
        overclock: bool = False,
        datasheet: bool = False,
        phase_ms: float | None = None,
        speed: str | None = None,
    ) -> None:
        self._datasheet = datasheet
        self._phase_ms = phase_ms
        if speed is not None:
            self.set_speed(speed)
        else:
            self.set_overclock(overclock)

    def _apply_period(self) -> None:
        real = self.real_period_s()
        if self.speed == "warp":
            self.overclock = True
            self.period_s = 0.0
        elif self.speed == "minute":
            self.overclock = False
            self.period_s = real / MINUTE_FACTOR
        else:
            self.overclock = False
            self.period_s = real

    def set_speed(self, speed: str) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        self.speed = speed
        self._apply_period()
        self.sync()

    def cycle_speed(self) -> str:
        i = SPEEDS.index(self.speed)
        self.set_speed(SPEEDS[(i + 1) % len(SPEEDS)])
        return self.speed

    def set_overclock(self, on: bool) -> None:
        self.set_speed("warp" if on else "relay")

    def real_period_s(self) -> float:
        """Relay-clock seconds per microstep, even when OVERCLOCK/WARP is on."""
        return microstep_period_s(
            overclock=False, datasheet=self._datasheet, phase_ms=self._phase_ms
        )

    def add_usteps(self, n: int = 1) -> None:
        if n > 0:
            self._usteps += n

    def set_running(self, on: bool) -> None:
        """HOST stopwatch runs only while the front-panel RUN lamp is on."""
        now = time.perf_counter()
        if on:
            if self._run_t0 is None:
                self._run_t0 = now
            return
        if self._run_t0 is not None:
            self._host_acc += now - self._run_t0
            self._run_t0 = None

    def reset_runtime(self) -> None:
        self._usteps = 0
        self._host_acc = 0.0
        if self._run_t0 is not None:
            self._run_t0 = time.perf_counter()

    def host_run_s(self) -> float:
        t = self._host_acc
        if self._run_t0 is not None:
            t += time.perf_counter() - self._run_t0
        return t

    def real_run_s(self) -> float:
        return self._usteps * self.real_period_s()

    def warp_factor(self) -> float:
        host = self.host_run_s()
        real = self.real_run_s()
        if host < 0.2 or real <= 0:
            return 0.0
        return real / host

    def runtime_fields(self) -> dict:
        host = self.host_run_s()
        real = self.real_run_s()
        speed = self.warp_factor()
        if speed <= 0:
            warp = "—"
        elif speed >= 10:
            warp = f"×{speed:.0f}"
        elif speed >= 1.05:
            warp = f"×{speed:.1f}"
        else:
            warp = "×1"
        ms = self.real_period_s() * 1000.0
        return {
            "host": format_duration(host),
            "real": format_duration(real),
            "warp": warp,
            "usteps": self._usteps,
            "real_ms": ms,
        }

    def runtime_label(self) -> str:
        f = self.runtime_fields()
        return f"HOST {f['host']}  REAL {f['real']}  {f['warp']}"

    def sync(self) -> None:
        """Call when RUN starts so we do not burst to catch up on paused time."""
        self._t0 = time.perf_counter()
        self._steps = 0

    def account(self, n: int = 1) -> None:
        self._steps += n

    def due_steps(self, cap: int | None = None) -> int:
        if self.overclock or self.period_s <= 0:
            return 0
        if cap is None:
            cap = 256 if self.speed == "minute" else 32
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
        if self.speed == "warp" or self.period_s <= 0:
            return "WARP"
        if self.speed == "minute":
            return "1s=1min"
        ms = self.real_period_s() * 1000.0
        return f"RELAY {ms:.0f}ms/µstep"
