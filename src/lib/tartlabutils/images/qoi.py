"""Streaming QOI decoding to RGB565_BE strips.

Derived from TartLab's experimental qoi_reader.py. The decoder retains only a
512-byte input window, a 64-color cache, and the requested output strip.
No display or framebuffer is allocated. QOI specification: qoiformat.org.
"""

import struct

from ._common import region, validate_background


_END = b"\x00\x00\x00\x00\x00\x00\x00\x01"


class _Reader:
    def __init__(self, stream):
        self.stream = stream
        self.buffer = b""
        self.position = 0

    def byte(self):
        if self.position == len(self.buffer):
            self.buffer = self.stream.read(512)
            self.position = 0
            if not self.buffer:
                raise ValueError("Truncated QOI stream")
        value = self.buffer[self.position]
        self.position += 1
        return value


def _header(stream):
    header = stream.read(14)
    if len(header) != 14 or header[:4] != b"qoif":
        raise ValueError("Invalid QOI header")
    width, height, channels, colorspace = struct.unpack(">IIBB", header[4:])
    if not width or not height or channels not in (3, 4) or colorspace not in (0, 1):
        raise ValueError("Invalid QOI dimensions or color format")
    return width, height, channels, colorspace


class QOIImage:
    """File-backed QOI image; opening reads only its header.

    ``iter_rgb565(rows=8, background=None)`` yields ``(y, pixels)`` strips.
    Pixels are a borrowed memoryview, reused on the next iteration. Complete
    any asynchronous transfer before advancing. Strip height is
    ``len(pixels) // (image.width * 2)``; the last strip can be shorter.

    Nonopaque pixels require an explicit RGB888 background tuple. Alpha is
    composited in the stored channel space (no gamma conversion), then reduced
    to RGB565. With no background, encountering transparency raises ValueError.
    Each iterator reopens the file and closes it on completion or ``close()``.

    ``iter_rows(...)`` implements the common image contract: cropped RGB565_BE
    rows with a separate alpha buffer. With no background it preserves alpha;
    with a background it composites before quantizing and returns opaque rows.
    Cropping still decodes the complete stream, including its end marker.
    """

    def __init__(self, path):
        with open(path, "rb") as stream:
            self.width, self.height, self.channels, self.colorspace = _header(stream)
        self.path = path

    @classmethod
    def open(cls, path):
        return cls(path)

    def iter_rgb565(self, rows=8, background=None):
        if not isinstance(rows, int) or rows < 1:
            raise ValueError("Strip rows must be a positive integer")
        validate_background(background)
        strips = self._iter_strips(
            rows, background, (0, 0, self.width, self.height), False)
        try:
            for y, pixels, _ in strips:
                yield y, pixels
        finally:
            strips.close()

    def iter_rows(self, x=0, y=0, width=None, height=None, background=None):
        crop = region(self, x, y, width, height)
        validate_background(background)
        strips = self._iter_strips(1, background, crop, True)
        try:
            for row in strips:
                yield row
        finally:
            strips.close()

    def _iter_strips(self, rows, background, crop, with_alpha):
        x, y, width, height = crop
        with open(self.path, "rb") as stream:
            if _header(stream) != (self.width, self.height, self.channels, self.colorspace):
                raise ValueError("QOI header changed after opening")
            reader = _Reader(stream)
            cache = bytearray(256)
            pixels = bytearray(width * min(rows, height) * 2)
            view = memoryview(pixels)
            alpha = bytearray(width * min(rows, height)) if with_alpha else None
            alpha_view = memoryview(alpha) if with_alpha else None
            r = g = b = 0
            a = 255
            run = 0
            total = self.width * self.height
            offset = 0
            strip_y = y
            last_pixel = (y + height - 1) * self.width + x + width - 1
            for position in range(total):
                if run:
                    run -= 1
                else:
                    opcode = reader.byte()
                    if opcode == 254:
                        r, g, b = reader.byte(), reader.byte(), reader.byte()
                    elif opcode == 255:
                        r, g, b, a = (reader.byte(), reader.byte(),
                                      reader.byte(), reader.byte())
                    elif opcode >> 6 == 0:
                        index = (opcode & 63) * 4
                        r, g, b, a = (cache[index], cache[index + 1],
                                      cache[index + 2], cache[index + 3])
                    elif opcode >> 6 == 1:
                        r = (r + ((opcode >> 4) & 3) - 2) & 255
                        g = (g + ((opcode >> 2) & 3) - 2) & 255
                        b = (b + (opcode & 3) - 2) & 255
                    elif opcode >> 6 == 2:
                        second = reader.byte()
                        dg = (opcode & 63) - 32
                        r = (r + dg + (second >> 4) - 8) & 255
                        g = (g + dg) & 255
                        b = (b + dg + (second & 15) - 8) & 255
                    else:
                        run = opcode & 63
                        if position + run >= total:
                            raise ValueError("QOI run exceeds image dimensions")
                index = ((r * 3 + g * 5 + b * 7 + a * 11) & 63) * 4
                cache[index], cache[index + 1] = r, g
                cache[index + 2], cache[index + 3] = b, a
                if position == total - 1:
                    for expected in _END:
                        if reader.byte() != expected:
                            raise ValueError("Invalid QOI end marker")
                pixel_y, pixel_x = divmod(position, self.width)
                if not (y <= pixel_y < y + height and x <= pixel_x < x + width):
                    continue
                red, green, blue = r, g, b
                if a != 255 and background is None and not with_alpha:
                    raise ValueError("Transparent QOI requires an explicit background")
                if a != 255 and background is not None:
                    inverse = 255 - a
                    red = (r * a + background[0] * inverse + 127) // 255
                    green = (g * a + background[1] * inverse + 127) // 255
                    blue = (b * a + background[2] * inverse + 127) // 255
                color = ((red & 248) << 8) | ((green & 252) << 3) | (blue >> 3)
                pixels[offset], pixels[offset + 1] = color >> 8, color & 255
                if with_alpha:
                    alpha[offset // 2] = a if background is None else 255
                offset += 2
                if offset == len(pixels) or position == last_pixel:
                    yield strip_y, view[:offset], (
                        alpha_view[:offset // 2] if with_alpha else None)
                    strip_y += offset // (width * 2)
                    offset = 0
