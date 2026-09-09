"""Validation and color conversion shared by image decoders and consumers."""


def region(image, x, y, width, height):
    if width is None:
        width = image.width - x
    if height is None:
        height = image.height - y
    if (any(not isinstance(value, int) for value in (x, y, width, height)) or
            x < 0 or y < 0 or width <= 0 or height <= 0 or
            x + width > image.width or y + height > image.height):
        raise ValueError("image region lies outside image")
    return x, y, width, height


def validate_background(background):
    if background is not None and (
            not isinstance(background, (tuple, list)) or len(background) != 3 or
            any(not isinstance(c, int) or c < 0 or c > 255 for c in background)):
        raise ValueError("Background must be an RGB888 tuple")


def rgb565(red, green, blue):
    """Return a conventional RGB565 integer (high byte first on the wire)."""
    return ((red & 248) << 8) | ((green & 252) << 3) | (blue >> 3)
