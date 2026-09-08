# TartLab image assets

Modern builds ship `src/files/assets` to `/files/assets`. Legacy builds ship
`src/files/assets-legacy` to that same device path; the legacy directory contains
only the original `warrior.bmp`. Help files are selected in the same way from
`help` or `help-legacy`.

The modern runtime has no PyDevices dependency. `tartlabutils.sprites` provides
TS16 sprite sheets, and `tartlabutils.images.qoi` provides general image decoding.
The historical PyDevices snapshot and its generated compatibility payload remain
available for legacy builds and research checks only.

## TS16 sprite sheets

Use TS16 for artwork that fits fifteen opaque colors and one transparent index.
The format contains an eight-byte header, 32-byte RGB565 palette, and packed
four-bit indices, so its size is `40 + ceil(width * height / 2)` bytes. There is
no partial alpha. Each sheet has its own palette. Quantizing richer artwork
changes its colors.

The loader retains the packed pixels. `sheet.sprite(x, y, width, height)` prepares
opaque horizontal runs; its result draws through any canvas with `hline`.
Prepare frequently drawn sprites once, outside the animation loop. Prepared
runs consume eight bytes each, plus object overhead, and can exceed raw RGB565
storage for detailed artwork. Release the sheet after preparing every needed
frame if further extraction is unnecessary.

Warrior keeps its original 144 by 256 geometry and twelve 48 by 64 frames. Its
top-left background color becomes transparent. The converted sheet is 18,472
bytes versus the original 73,866-byte BMP. The sprite example retains about
59,552 bytes of prepared run data and releases the packed sheet.

Rebuild it with Pillow installed on the host:

```text
python tools/convert_ts16.py src/files/assets-legacy/warrior.bmp src/files/assets/warrior.ts16 --transparent-corner
```

The converter accepts Pillow-readable images, preserves binary alpha, rejects
partial alpha, and quantizes opaque colors without dithering. The optional
corner key is appropriate for this BMP; omit it for images with actual alpha.
Normal filesystem builds copy the checked-in output and do not require Pillow.
Racer retains its separate art assembly tool, `tools/build_racer_sprites.py`.

## QOI images

```python
from tartlabutils.images.qoi import QOIImage

image = QOIImage.open("files/assets/test.qoi")
strips = image.iter_rgb565(rows=8, background=(0, 0, 0))
try:
    for y, pixels in strips:
        height = len(pixels) // (image.width * 2)
        surface.write(pixels, x, top + y, image.width, height)
finally:
    strips.close()
```

Opening reads only the header. Decoding uses a 512-byte input window, a
256-byte color cache, and an output buffer of `width * min(rows, height) * 2`
bytes, plus interpreter overhead. It does not retain the compressed file or
allocate a full RGB/RGBA image. Each iteration yields a borrowed RGB565_BE
memoryview; complete its use, including any DMA transfer, before requesting the
next strip. The final strip may have fewer rows. A new iterator reopens and
decodes the image from the start.

Display transport requirements are separate from decoder memory: the example
clears the surface first. `fill_surface` uses a temporary complete RGB565 frame
when the surface requires an initial full-frame seed; subsequent fills and
QOI decoding use strips. Ordinary direct surfaces need only the fill strip.

With no background, transparency raises an error. An explicit RGB888 background
composites alpha in the stored channel space before RGB565 conversion; this is
not gamma-correct blending. The decoder checks dimensions, channels, colorspace,
truncated chunks, overflowing runs, and the standard eight-byte end marker.
Earlier strips may already have been drawn when malformed later data is found.

QOI is useful for richer images and compact storage, but repeated random sprite
extraction would require decoding preceding pixels. The modern QOI example
demonstrates bounded-memory loading; the TS16 examples demonstrate sprite access
and reuse. The original experimental QOI reader remains in the locked legacy
vendor snapshot and is not shipped on modern devices.
