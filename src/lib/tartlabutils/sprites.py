"""Small indexed sprite sheets with clipped, color-keyed span drawing.

TS16 stores a little-endian width/height, sixteen RGB565_BE palette entries,
then two pixels per byte (high nibble first). Palette index zero is transparent.
Only requested sprites are decoded; packed spans work on any hline canvas.
"""

from array import array
import struct


class Sprite:
    __slots__ = ("width", "height", "spans")

    def __init__(self, width, height, spans):
        self.width = width
        self.height = height
        self.spans = spans

    def draw(self, target, x, y, clip, x_offset=0, y_offset=0):
        left, top, width, height = clip
        right, bottom = left + width, top + height
        spans = self.spans
        hline = target.hline
        if (x >= left and y >= top and
                x + self.width <= right and y + self.height <= bottom):
            x -= x_offset
            y -= y_offset
            for index in range(0, len(spans), 4):
                hline(x + spans[index + 1], y + spans[index],
                      spans[index + 2], spans[index + 3])
            return
        for index in range(0, len(spans), 4):
            row = y + spans[index]
            if row < top or row >= bottom:
                continue
            start = x + spans[index + 1]
            end = min(right, start + spans[index + 2])
            start = max(left, start)
            if end > start:
                hline(start - x_offset, row - y_offset,
                      end - start, spans[index + 3])


class SpriteSheet:
    def __init__(self, path):
        with open(path, "rb") as stream:
            header = stream.read(8)
            if len(header) != 8 or header[:4] != b"TS16":
                raise ValueError("invalid TS16 sprite sheet")
            self.width, self.height = struct.unpack("<HH", header[4:])
            palette = stream.read(32)
            if not self.width or not self.height or len(palette) != 32:
                raise ValueError("invalid sprite sheet dimensions or palette")
            # RGB565_BE bytes interpreted as framebuffer-native integers.
            self.palette = struct.unpack("<16H", palette)
            self.pixels = stream.read()
        if len(self.pixels) != (self.width * self.height + 1) // 2:
            raise ValueError("invalid sprite sheet pixel length")

    def index_at(self, x, y):
        position = y * self.width + x
        value = self.pixels[position // 2]
        return value & 15 if position & 1 else value >> 4

    def color_at(self, x, y):
        return self.palette[self.index_at(x, y)]

    def sprite(self, x, y, width, height, scale=1, flip_x=False):
        if not isinstance(scale, int) or scale < 1:
            raise ValueError("sprite scale must be a positive integer")
        if (x < 0 or y < 0 or width <= 0 or height <= 0 or
                x + width > self.width or y + height > self.height):
            raise ValueError("sprite lies outside sheet")
        spans = array("H")
        for row in range(height):
            column = 0
            while column < width:
                color = self.index_at(x + column, y + row)
                start = column
                column += 1
                while (column < width and
                       self.index_at(x + column, y + row) == color):
                    column += 1
                if color:
                    output_x = width - column if flip_x else start
                    for repeat in range(scale):
                        spans.extend((row * scale + repeat, output_x * scale,
                                      (column - start) * scale,
                                      self.palette[color]))
        return Sprite(width * scale, height * scale, spans)
