"""Reusable clocks and scheduling helpers."""

import time


def _default_ticks_ms():
    ticks_ms = getattr(time, "ticks_ms", None)
    if ticks_ms is not None:
        return ticks_ms()
    return int(time.monotonic() * 1000)


def _default_ticks_diff(new, old):
    ticks_diff = getattr(time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(new, old)
    return new - old


def _default_ticks_add(value, delta):
    ticks_add = getattr(time, "ticks_add", None)
    if ticks_add is not None:
        return ticks_add(value, delta)
    return value + delta


def _default_sleep_ms(milliseconds):
    sleep_ms = getattr(time, "sleep_ms", None)
    if sleep_ms is not None:
        sleep_ms(milliseconds)
    else:
        time.sleep(milliseconds / 1000)


class FrameClock:
    """Run fixed simulation steps against an absolute render deadline."""

    def __init__(self, frame_ms, update_ms=None, max_updates=2,
                 ticks_ms=None, ticks_diff=None, ticks_add=None,
                 sleep_ms=None):
        frame_ms = int(frame_ms)
        update_ms = frame_ms if update_ms is None else int(update_ms)
        max_updates = int(max_updates)
        if frame_ms <= 0 or update_ms <= 0:
            raise ValueError("frame and update periods must be positive")
        if max_updates <= 0:
            raise ValueError("max_updates must be positive")

        self.frame_ms = frame_ms
        self.update_ms = update_ms
        self.max_updates = max_updates
        self._ticks_ms = ticks_ms or _default_ticks_ms
        self._ticks_diff = ticks_diff or _default_ticks_diff
        self._ticks_add = ticks_add or _default_ticks_add
        self._sleep_ms = sleep_ms or _default_sleep_ms

        now = self._ticks_ms()
        self._last_update = now
        self._deadline = self._ticks_add(now, frame_ms)
        self._accumulated_ms = 0
        self.missed_deadlines = 0
        self.dropped_update_ms = 0

    def updates_due(self):
        """Return the bounded number of fixed updates due at this instant."""
        now = self._ticks_ms()
        elapsed = self._ticks_diff(now, self._last_update)
        self._last_update = now
        if elapsed < 0:
            elapsed = 0
        self._accumulated_ms += elapsed

        available = self._accumulated_ms // self.update_ms
        updates = min(available, self.max_updates)
        self._accumulated_ms -= updates * self.update_ms
        if available > self.max_updates:
            dropped = (available - self.max_updates) * self.update_ms
            self._accumulated_ms -= dropped
            self.dropped_update_ms += dropped
        return updates

    def pace(self):
        """Sleep only for the remaining budget and advance the deadline."""
        now = self._ticks_ms()
        remaining = self._ticks_diff(self._deadline, now)
        slept = 0
        if remaining > 0:
            self._sleep_ms(remaining)
            slept = remaining
            now = self._ticks_ms()
        elif remaining < 0:
            lateness = -remaining
            self.missed_deadlines += (
                lateness + self.frame_ms - 1) // self.frame_ms

        lateness = self._ticks_diff(now, self._deadline)
        periods = 1
        if lateness > 0:
            periods += lateness // self.frame_ms
        self._deadline = self._ticks_add(
            self._deadline, periods * self.frame_ms)
        return slept
