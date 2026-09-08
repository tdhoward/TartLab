"""Decode a QOI image and send its RGB565 output to the direct surface."""

from tartlabutils.images.qoi import QOIImage
from tartlabutils.app import fill_surface, game_surface


surface = game_surface()
fill_surface(surface, 0x0000)

image = QOIImage.open("files/assets/test.qoi")
if image.width > surface.width or image.height > surface.height:
    raise ValueError("image is larger than the display")

x = (surface.width - image.width) // 2
y = (surface.height - image.height) // 2
# Decode just eight rows at a time. Explicitly composite any alpha over black.
strips = image.iter_rgb565(rows=8, background=(0, 0, 0))
try:
    for row, pixels in strips:
        height = len(pixels) // (image.width * 2)
        # write() waits for DMA completion before the decoder reuses this buffer.
        surface.write(pixels, x, y + row, image.width, height)
finally:
    strips.close()
