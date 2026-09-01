"""Display an RGB565 bitmap through the modern direct surface."""

from bmp565 import BMP565
from tartlabutils.modern_app import (
    fill_surface, game_surface, swap565_buffer)


surface = game_surface()
fill_surface(surface, 0x0000)

image = BMP565("files/assets/warrior.bmp")
if image.width > surface.width or image.height > surface.height:
    raise ValueError("bitmap is larger than the display")

# BMP565 stores little-endian pixels; the modern surface documents RGB565_BE.
swap565_buffer(image.buffer)
x = (surface.width - image.width) // 2
y = (surface.height - image.height) // 2
surface.write(image.buffer, x, y, image.width, image.height)
