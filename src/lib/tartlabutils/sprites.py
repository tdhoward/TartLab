"""Format-independent sprite preparation and clipped drawing on hline canvases."""

from array import array

from tartlabutils.images import open_image
from tartlabutils.images._common import region, validate_background


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
    """Prepare reusable sprites from a path or a compatible image decoder.

    Without a background, alpha below 128 is transparent and alpha of 128 or
    more is opaque. An RGB888 background tuple composites all pixels before
    preparation. Use ``sprites(regions)`` to extract several rectangles in one
    decoder pass; QOI must decode from the beginning on each extraction call.

    Prepared spans cost eight bytes per run plus object overhead. Prepare once
    outside animation loops, and release the sheet when extraction is complete.
    """

    def __init__(self, path, background=None):
        validate_background(background)
        self.image = path if hasattr(path, "iter_rows") else open_image(path)
        self.width, self.height = self.image.width, self.image.height
        self.background = background

    # Compatibility accessors for existing indexed-image callers. New code
    # should access format-specific data through sheet.image instead.
    @property
    def palette(self):
        return self.image.palette

    @property
    def pixels(self):
        return self.image.pixels

    def index_at(self, x, y):
        return self.image.index_at(x, y)

    def color_at(self, x, y):
        """Read a framebuffer-native color; transparency does not hide its RGB."""
        region(self, x, y, 1, 1)
        if self.background is None and hasattr(self.image, "color_at"):
            return self.image.color_at(x, y)
        rows = self.image.iter_rows(x, y, 1, 1, background=self.background)
        try:
            for _, pixels, _ in rows:
                color = pixels[0] | (pixels[1] << 8)
        finally:
            rows.close()
        return color

    def sprite(self, x, y, width, height, scale=1, flip_x=False):
        return self.sprites(((x, y, width, height),), scale, flip_x)[0]

    def sprites(self, regions, scale=1, flip_x=False):
        """Return sprites in input order, reading the decoder only once.

        Regions are ``(x, y, width, height)`` rectangles; they may overlap or
        arrive in any order. Scale and horizontal flip apply to every result.
        Only the bounding crop's rows and the prepared runs are expanded.
        """
        if not isinstance(scale, int) or scale < 1:
            raise ValueError("sprite scale must be a positive integer")
        crops = [region(self, *rectangle) for rectangle in regions]
        if not crops:
            return []
        if any(width * scale > 65535 or height * scale > 65535
               for _, _, width, height in crops):
            raise ValueError("scaled sprite dimensions exceed packed span limits")
        result = [Sprite(width * scale, height * scale, array("H"))
                  for _, _, width, height in crops]
        left = min(crop[0] for crop in crops)
        top = min(crop[1] for crop in crops)
        right = max(crop[0] + crop[2] for crop in crops)
        bottom = max(crop[1] + crop[3] for crop in crops)
        rows = self.image.iter_rows(
            left, top, right - left, bottom - top, background=self.background)
        try:
            for row, pixels, alpha in rows:
                for index in range(len(crops)):
                    x, y, width, height = crops[index]
                    if y <= row < y + height:
                        _append_spans(result[index].spans, pixels, alpha,
                                      x - left, row - y, width, scale, flip_x)
        finally:
            rows.close()
        return result


def _append_spans(spans, pixels, alpha, x, row, width, scale, flip_x):
    append = spans.append
    column = 0
    while column < width:
        if alpha[x + column] < 128:
            column += 1
            continue
        offset = (x + column) * 2
        low, high = pixels[offset], pixels[offset + 1]
        start = column
        column += 1
        while column < width:
            offset = (x + column) * 2
            if (alpha[x + column] < 128 or pixels[offset] != low or
                    pixels[offset + 1] != high):
                break
            column += 1
        # RGB565_BE bytes interpreted as framebuffer-native integers, matching
        # DirectCanvas.rgb565 and the existing hline rendering contract.
        color = low | (high << 8)
        output_x = width - column if flip_x else start
        for repeat in range(scale):
            append(row * scale + repeat)
            append(output_x * scale)
            append((column - start) * scale)
            append(color)
