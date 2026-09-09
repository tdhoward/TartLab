"""Packed TS16 decoding with direct access to indexed pixels.

The header contains little-endian width/height followed by sixteen RGB565_BE
palette entries. Two pixels share each byte, high nibble first. Index zero is
transparent. The image retains packed pixels; row decoding uses reusable buffers.
"""

import struct

from ._common import region, rgb565, validate_background


class TS16Image:
    def __init__(self, path):
        with open(path, "rb") as stream:
            header = stream.read(8)
            if len(header) != 8 or header[:4] != b"TS16":
                raise ValueError("invalid TS16 sprite sheet")
            self.width, self.height = struct.unpack("<HH", header[4:])
            palette = stream.read(32)
            if not self.width or not self.height or len(palette) != 32:
                raise ValueError("invalid sprite sheet dimensions or palette")
            # Retain the historical framebuffer-native palette integer API.
            self.palette = struct.unpack("<16H", palette)
            self.pixels = stream.read()
        if len(self.pixels) != (self.width * self.height + 1) // 2:
            raise ValueError("invalid sprite sheet pixel length")

    @classmethod
    def open(cls, path):
        return cls(path)

    def index_at(self, x, y):
        region(self, x, y, 1, 1)
        position = y * self.width + x
        value = self.pixels[position // 2]
        return value & 15 if position & 1 else value >> 4

    def color_at(self, x, y):
        return self.palette[self.index_at(x, y)]

    def iter_rows(self, x=0, y=0, width=None, height=None, background=None):
        x, y, width, height = region(self, x, y, width, height)
        validate_background(background)
        background_color = rgb565(*background) if background is not None else 0
        pixels = bytearray(width * 2)
        alpha = bytearray(width)
        pixel_view, alpha_view = memoryview(pixels), memoryview(alpha)
        palette, packed = self.palette, self.pixels
        for row in range(y, y + height):
            position = row * self.width + x
            for column in range(width):
                offset = position + column
                value = packed[offset // 2]
                index = value & 15 if offset & 1 else value >> 4
                color = palette[index]
                opacity = 255 if index else 0
                if index == 0 and background is not None:
                    pixels[column * 2] = background_color >> 8
                    pixels[column * 2 + 1] = background_color & 255
                    opacity = 255
                else:
                    pixels[column * 2] = color & 255
                    pixels[column * 2 + 1] = color >> 8
                alpha[column] = opacity
            yield row, pixel_view, alpha_view
