"""Image decoding independent of displays, boards, and applications.

Decoders expose ``width``, ``height`` and
``iter_rows(x=0, y=0, width=None, height=None, background=None)``. Each row is
``(y, pixels, alpha)``: an absolute image row number, RGB565_BE bytes and one
alpha byte per pixel. Buffers are borrowed until the next iteration. Iterators
must support ``close()`` to release resources when a consumer stops early.

With no background, alpha is preserved. An RGB888 background tuple composites
in stored channel space before RGB565 conversion and makes every pixel opaque.
Decoders may seek directly or decode preceding pixels; consumers must not
assume random access. Sprite preparation lives in ``tartlabutils.sprites``.
"""


def open_image(path):
    """Detect a file's header and load only its decoder module.

    Add formats here, or pass a compatible decoder directly to SpriteSheet.
    File extensions are not used to determine the format.
    """
    with open(path, "rb") as stream:
        magic = stream.read(4)
    if magic == b"TS16":
        from .ts16 import TS16Image
        return TS16Image(path)
    if magic == b"qoif":
        from .qoi import QOIImage
        return QOIImage(path)
    raise ValueError("unsupported image format")
