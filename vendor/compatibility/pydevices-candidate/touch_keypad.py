# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal legacy polling keypad over current PyDevices pointer events."""

import events
from graphics import Area


class Keypad:
    """Map touch/key-down events to the scalar key expected by legacy apps."""

    def __init__(
            self, poll, x, y, w, h, cols=3, rows=3, keys=None,
            translate=None):
        self._keys = keys if keys else list(range(cols * rows))
        self._poll = poll
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.cols = cols
        self.rows = rows
        self.key_width = kw = w / cols
        self.key_height = kh = h / rows
        self._translate = translate or (lambda point: point)
        self.areas = [
            Area(int(x + kw * i), int(y + kh * j), int(kw), int(kh))
            for j in range(rows)
            for i in range(cols)
        ]

    def read(self):
        event = self._poll()
        if isinstance(event, list):
            event = event[0] if event else None
        if (event and event.type == events.MOUSEBUTTONDOWN
                and event.button == 1):
            x, y = self._translate(event.pos)
            if (x < self.x or x > self.x + self.w
                    or y < self.y or y > self.y + self.h):
                return None
            col = int((x - self.x) / self.key_width)
            row = int((y - self.y) / self.key_height)
            try:
                return self._keys[row * self.cols + col]
            except IndexError:
                return None
        if event and event.type == events.KEYDOWN:
            return event.key
        return None
