"""Direct-drawing helpers for TartLab's modern student applications.

Use :class:`DirectCanvas` for framebuffer primitives and explicit refreshes,
or :func:`game_surface` when an image is already packed as RGB565_BE.  Both
target the public exclusive surface without exposing the native display bus.
"""

import time

from .platform import get_platform

from framebuf import FrameBuffer, MONO_HLSB, RGB565


TRANSFER_ROWS = 16


def _ticks_ms():
    ticks_ms = getattr(time, "ticks_ms", None)
    if ticks_ms is not None:
        return ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(new, old):
    ticks_diff = getattr(time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(new, old)
    return new - old


def framebuffer_color(color):
    """Convert native RGB565 to the direct framebuffer's stored byte order."""
    return ((color & 0xFF) << 8) | ((color >> 8) & 0xFF)


def rgb565(red, green, blue):
    """Create a direct-framebuffer color from 8-bit RGB components."""
    native = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return framebuffer_color(native)


def swap565_buffer(buffer):
    """Swap every RGB565 byte pair in a writable buffer, in place."""
    view = memoryview(buffer)
    if len(view) & 1:
        raise ValueError("an RGB565 buffer must contain an even byte count")
    for offset in range(0, len(view), 2):
        view[offset], view[offset + 1] = view[offset + 1], view[offset]
    return buffer


def game_surface():
    """Acquire exclusive modern display ownership and return its surface."""
    platform = get_platform()
    surface = platform.enter_game_mode()
    if getattr(surface, "color_format", None) != "RGB565_BE":
        raise RuntimeError("modern examples require an RGB565_BE game surface")
    return surface


def fill_surface(surface, color):
    """Fill a direct surface with a standard 16-bit RGB565 color."""
    rows = min(TRANSFER_ROWS, surface.height)
    buffer = surface.allocate_buffer(surface.width, rows)
    view = memoryview(buffer)
    high = (color >> 8) & 0xFF
    low = color & 0xFF
    for offset in range(0, len(view), 2):
        view[offset] = high
        view[offset + 1] = low
    try:
        y = 0
        while y < surface.height:
            height = min(rows, surface.height - y)
            size = surface.width * height * 2
            surface.write(view[:size], 0, y, surface.width, height)
            y += height
    finally:
        surface.free_buffer(buffer)


class DirectCanvas(FrameBuffer):
    """A PSRAM-friendly framebuffer flushed through a small DMA bounce tile."""

    def __init__(self, surface=None, transfer_rows=TRANSFER_ROWS):
        self.surface = surface or game_surface()
        width = self.surface.width
        height = self.surface.height
        self._width = width
        self._height = height
        self.buffer = bytearray(width * height * 2)
        self._buffer_view = memoryview(self.buffer)
        self._transfer_rows = min(max(1, transfer_rows), height)
        self._transfer = self.surface.allocate_buffer(
            width, self._transfer_rows)
        self._transfer_view = memoryview(self._transfer)
        self._closed = False
        super().__init__(self.buffer, width, height, RGB565)

    @staticmethod
    def _area_values(area, width, height):
        if area is None:
            return 0, 0, width, height
        if hasattr(area, "x"):
            return area.x, area.y, area.w, area.h
        return area

    def show(self, area=None):
        """Flush all or part of the framebuffer to the modern surface."""
        if self._closed:
            raise RuntimeError("canvas is closed")
        x, y, width, height = self._area_values(
            area, self._width, self._height)
        x = max(0, int(x))
        y = max(0, int(y))
        width = min(int(width), self._width - x)
        height = min(int(height), self._height - y)
        if width <= 0 or height <= 0:
            return

        source = self._buffer_view
        target = self._transfer_view
        row_bytes = width * 2
        sent_rows = 0
        while sent_rows < height:
            rows = min(self._transfer_rows, height - sent_rows)
            for row in range(rows):
                source_start = (
                    (y + sent_rows + row) * self._width + x) * 2
                target_start = row * row_bytes
                target[target_start:target_start + row_bytes] = \
                    source[source_start:source_start + row_bytes]
            size = row_bytes * rows
            self.surface.write(
                target[:size], x, y + sent_rows, width, rows)
            sent_rows += rows

    def close(self):
        if not self._closed:
            self.surface.free_buffer(self._transfer)
            self._closed = True


class PortraitCanvas:
    """Direct canvas with portrait coordinates over any surface orientation.

    A landscape surface is treated as a clockwise-rotated portrait panel. The
    primitive coordinates are mapped into the underlying framebuffer, so
    rectangles and dirty refreshes remain fast and require no second buffer.
    """

    def __init__(self, surface=None, transfer_rows=TRANSFER_ROWS):
        self._canvas = DirectCanvas(surface, transfer_rows)
        self.surface = self._canvas.surface
        self._rotated = self.surface.width > self.surface.height
        if self._rotated:
            self.width = self.surface.height
            self.height = self.surface.width
        else:
            self.width = self.surface.width
            self.height = self.surface.height

    def _point(self, x, y):
        if not self._rotated:
            return x, y
        return y, self.width - 1 - x

    def _area(self, x, y, width, height):
        if not self._rotated:
            return x, y, width, height
        return y, self.width - x - width, height, width

    def fill(self, color):
        return self._canvas.fill(color)

    def pixel(self, x, y, color=None):
        target_x, target_y = self._point(x, y)
        if color is None:
            return self._canvas.pixel(target_x, target_y)
        return self._canvas.pixel(target_x, target_y, color)

    def fill_rect(self, x, y, width, height, color):
        x, y, width, height = self._area(x, y, width, height)
        return self._canvas.fill_rect(x, y, width, height, color)

    def rect(self, x, y, width, height, color):
        x, y, width, height = self._area(x, y, width, height)
        return self._canvas.rect(x, y, width, height, color)

    def hline(self, x, y, width, color):
        if not self._rotated:
            return self._canvas.hline(x, y, width, color)
        return self._canvas.vline(y, self.width - x - width, width, color)

    def vline(self, x, y, height, color):
        if not self._rotated:
            return self._canvas.vline(x, y, height, color)
        return self._canvas.hline(y, self.width - 1 - x, height, color)

    def line(self, x1, y1, x2, y2, color):
        x1, y1 = self._point(x1, y1)
        x2, y2 = self._point(x2, y2)
        return self._canvas.line(x1, y1, x2, y2, color)

    def text(self, value, x, y, color):
        """Draw the built-in 8-pixel font in logical portrait orientation."""
        if not value:
            return
        width = len(value) * 8
        if not self._rotated:
            return self._canvas.text(value, x, y, color)
        mask = bytearray(((width + 7) // 8) * 8)
        glyphs = FrameBuffer(mask, width, 8, MONO_HLSB)
        glyphs.text(value, 0, 0, 1)
        for glyph_y in range(8):
            for glyph_x in range(width):
                if glyphs.pixel(glyph_x, glyph_y):
                    self.pixel(x + glyph_x, y + glyph_y, color)

    def show(self, area=None):
        if area is None or not self._rotated:
            return self._canvas.show(area)
        x, y, width, height = DirectCanvas._area_values(
            area, self.width, self.height)
        return self._canvas.show(self._area(x, y, width, height))

    def close(self):
        self._canvas.close()


class TouchGrid:
    """Edge-triggered grid input for an exclusive direct-rendering app."""

    def __init__(self, keys, cols, rows, x=0, y=0, width=None, height=None):
        self._platform = get_platform()
        if self._platform.input is None:
            raise RuntimeError("the modern platform has no touch input")
        self._keys = keys
        self.cols = cols
        self.rows = rows
        self.x = x
        self.y = y
        self.width = width if width is not None else self._platform.width
        self.height = height if height is not None else self._platform.height
        self._down = False
        self._last_keep_awake = None
        self._keep_awake()

    def _keep_awake(self):
        keep_awake = getattr(self._platform, "keep_touch_awake", None)
        if keep_awake is not None:
            keep_awake()
        self._last_keep_awake = _ticks_ms()

    def _logical_point(self, point):
        return point

    def read(self):
        now = _ticks_ms()
        if _ticks_diff(now, self._last_keep_awake) >= 5000:
            self._keep_awake()
        point = self._platform.read_game_touch()
        if point is None:
            self._down = False
            return None
        if self._down:
            return None
        self._down = True
        x, y = self._logical_point(point)
        if not (self.x <= x < self.x + self.width and
                self.y <= y < self.y + self.height):
            return None
        col = int((x - self.x) * self.cols / self.width)
        row = int((y - self.y) * self.rows / self.height)
        index = row * self.cols + col
        return self._keys[index] if index < len(self._keys) else None


class PortraitTouchGrid(TouchGrid):
    """Touch grid using the same portrait coordinates as PortraitCanvas."""

    def __init__(self, keys, cols, rows, x=0, y=0,
                 width=None, height=None):
        platform = get_platform()
        self._portrait_rotated = platform.width > platform.height
        logical_width = platform.height if self._portrait_rotated \
            else platform.width
        logical_height = platform.width if self._portrait_rotated \
            else platform.height
        super().__init__(
            keys, cols, rows, x, y,
            logical_width if width is None else width,
            logical_height if height is None else height)

    def _logical_point(self, point):
        if not self._portrait_rotated:
            return point
        x, y = point
        return self._platform.height - 1 - y, x
