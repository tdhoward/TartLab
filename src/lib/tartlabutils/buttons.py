"""Debounced physical button events with explicit ownership boundaries."""

import time


def _ticks_ms():
    fn = getattr(time, "ticks_ms", None)
    return fn() if fn else int(time.monotonic() * 1000)


def _ticks_diff(now, before):
    fn = getattr(time, "ticks_diff", None)
    return fn(now, before) if fn else now - before


class ButtonInput:
    """Poll named buttons as (name, pressed) edges; never synthesize repeats.

    A press held at construction or reset is suppressed through its release.
    Call reset at each input ownership boundary to discard partial gestures.
    """

    def __init__(self, definitions, pin_factory, debounce_ms=30,
                 ticks_ms=None, ticks_diff=None):
        if debounce_ms < 0:
            raise ValueError("debounce interval must be nonnegative")
        self._ticks_ms = ticks_ms or _ticks_ms
        self._ticks_diff = ticks_diff or _ticks_diff
        self._debounce_ms = debounce_ms
        self._buttons = []
        for definition in definitions:
            active = bool(definition.get("active_high", False))
            pull = getattr(pin_factory, "PULL_DOWN" if active else "PULL_UP")
            pin = pin_factory(definition["number"], pin_factory.IN, pull)
            self._buttons.append({"name": definition["name"], "pin": pin,
                                  "active": active})
        self.names = tuple(button["name"] for button in self._buttons)
        self.reset()

    def reset(self):
        now = self._ticks_ms()
        for button in self._buttons:
            pressed = bool(button["pin"].value()) == button["active"]
            button.update(raw=pressed, stable=pressed, changed=now,
                          blocked=True)

    def poll(self):
        now = self._ticks_ms()
        events = []
        for button in self._buttons:
            pressed = bool(button["pin"].value()) == button["active"]
            if pressed != button["raw"]:
                button["raw"] = pressed
                button["changed"] = now
            if self._ticks_diff(now, button["changed"]) < self._debounce_ms:
                continue
            if button["blocked"]:
                if not pressed:
                    button["blocked"] = False
                button["stable"] = pressed
            elif pressed != button["stable"]:
                button["stable"] = pressed
                events.append((button["name"], pressed))
        return tuple(events)
