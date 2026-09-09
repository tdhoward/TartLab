# TartLab image assets

Modern builds ship `src/files/assets` to `/files/assets`. Legacy builds ship
`src/files/assets-legacy` to that same device path; the legacy directory contains
only the original `warrior.bmp`. Help files are selected in the same way from
`help` or `help-legacy`.

The modern runtime has no PyDevices dependency. `tartlabutils.images` detects
and decodes images; `tartlabutils.sprites` prepares reusable sprites from any
compatible image decoder. TS16 and QOI are supported by both APIs.
The historical PyDevices snapshot and its generated compatibility payload remain
available for legacy builds and research checks only.

## Loading sprite sheets

```python
from tartlabutils.sprites import SpriteSheet

sheet = SpriteSheet("files/assets/warrior.ts16")  # A QOI path works too.
frame = sheet.sprite(0, 0, 48, 64, scale=2, flip_x=True)

# Extract multiple frames in one decoding pass, in the requested order.
frames = sheet.sprites([(0, 0, 48, 64), (48, 0, 48, 64), (96, 0, 48, 64)])
del sheet
frames[0].draw(canvas, x, y, (0, 0, canvas.width, canvas.height))
```

`SpriteSheet(path, background=None)` detects the image by its header, independent
of the file extension. It can also accept an already-open image decoder.
`sprite()` and `sprites()` accept a positive integer scale and horizontal flip;
batch options apply to every requested rectangle. Batches may overlap and arrive
in any order. The example animation prepares all twelve frames in one batch.

Without a background, alpha values 0 through 127 are fully transparent and values
128 through 255 are fully opaque, retaining their source RGB color. An explicit
RGB888 background tuple, such as `background=(30, 40, 50)`, composites every pixel
against that color before RGB565 quantization; the resulting sprite is opaque.
Compositing uses `(channel * alpha + background * (255 - alpha) + 127) // 255`
in stored channel space, without gamma conversion. Fully transparent pixels
become the supplied background. This policy applies consistently to both formats.

Sprites store prepared opaque horizontal runs and draw through any canvas with
`hline`. Prepare frequently drawn frames outside the animation loop. Runs cost
eight bytes each plus object overhead, and detailed artwork can use more memory
than raw RGB565. Loading QOI does not allocate an expanded sheet: preparation
uses a cropped row of colors and alpha plus the retained runs. A batch uses the
bounding rectangle of its requested frames. Release the sheet after preparation
if further extraction is unnecessary.

`sheet.color_at(x, y)` returns the framebuffer-native RGB565 integer, including
any supplied background compositing. With no background it returns the source
color even for transparent pixels. Single-pixel reads are cheap for TS16; each
QOI extraction or color lookup decodes its stream again. Prefer batches for QOI.

## Decoder extension contract

```python
from tartlabutils.images import open_image

image = open_image("files/assets/test.qoi")
rows = image.iter_rows(x=0, y=0, width=32, height=32)
try:
    for y, pixels, alpha in rows:
        # pixels: width * 2 RGB565_BE bytes; alpha: width bytes (0..255).
        # Consume or copy both buffers before requesting the next row.
        pass
finally:
    rows.close()
```

Decoders expose `width`, `height` and
`iter_rows(x=0, y=0, width=None, height=None, background=None)`. Omitted sizes
extend to the image edge. Rows arrive top to bottom, with absolute image row
numbers and borrowed color/alpha buffers. Their iterators support `close()`.
With no background, preserve source alpha. With a background, composite before
quantization and return alpha 255 throughout. Consumers decide how to render
uncomposited alpha; sprite preparation uses the 50% cutoff described above.

New formats implement this interface and add a header case to `open_image()`.
Alternatively, pass a custom decoder directly to `SpriteSheet` without changing
the built-in format dispatch. Only the detected format is imported. No decoder
imports display drivers, allocates a framebuffer, or knows an app's frame layout.

## TS16 sprite sheets

Use TS16 for artwork that fits fifteen opaque colors and one transparent index.
The format contains an eight-byte header, 32-byte RGB565 palette, and packed
four-bit indices, so its size is `40 + ceil(width * height / 2)` bytes. There is
no partial alpha. Each sheet has its own palette. Quantizing richer artwork
changes its colors.

`tartlabutils.images.ts16.TS16Image` retains the packed pixels and decodes cropped
rows into reusable color and alpha buffers of three bytes per requested pixel.
It owns `palette`, `pixels`, `index_at()` and `color_at()`. Palette entries remain
framebuffer-native integers for compatibility. Existing `SpriteSheet.palette`,
`pixels`, and `index_at()` accessors forward to the decoder; new code should use
`sheet.image` for format-specific access. QOI has no palette or index API.

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

For the existing `iter_rgb565()` strip API, transparency with no background
raises an error because those strips have no alpha buffer. An explicit RGB888 background
composites alpha in the stored channel space before RGB565 conversion; this is
not gamma-correct blending. The decoder checks dimensions, channels, colorspace,
truncated chunks, overflowing runs, and the standard eight-byte end marker.
Earlier strips may already have been drawn when malformed later data is found.

`iter_rows()` additionally supports cropped rows and preserves alpha when no
background is supplied. Its working storage is the 512-byte input window,
256-byte color cache, and `crop_width * 3` bytes for colors and alpha, plus
interpreter overhead. It decodes the complete stream, including pixels outside
the crop, and validates the end marker. As with strips, a later error can occur
after earlier rows have been yielded; consumers must finish the iterator to
validate the complete file. Sprite preparation consumes it before returning.

QOI is useful for richer images and compact storage. Each extraction decodes
preceding pixels, so `sheet.sprites(regions)` avoids repeated passes when preparing
an animation. The original experimental QOI reader remains in the locked legacy
vendor snapshot and is not shipped on modern devices.
