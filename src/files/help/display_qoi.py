"""Decode a QOI image and send its RGB565 output to the direct surface."""

from qoi_reader import QOIImage
from tartlabutils.modern_app import fill_surface, game_surface


surface = game_surface()
fill_surface(surface, 0x0000)

image = QOIImage.open("files/assets/test.qoi")
if image.width > surface.width or image.height > surface.height:
    raise ValueError("image is larger than the display")

x = (surface.width - image.width) // 2
y = (surface.height - image.height) // 2
# as_rgb565() already returns the big-endian format promised by the surface.
surface.write(image.as_rgb565(), x, y, image.width, image.height)
