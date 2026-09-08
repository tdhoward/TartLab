"""Convert an image to a TS16 sheet (host-only Pillow dependency).

Example: python tools/convert_ts16.py src/files/assets-legacy/warrior.bmp
    src/files/assets/warrior.ts16 --transparent-corner
"""

import argparse
from pathlib import Path
import struct

from PIL import Image


def encode(image, transparent_corner=False):
    image = image.convert("RGBA")
    width, height = image.size
    if not (0 < width <= 65535 and 0 < height <= 65535):
        raise ValueError("TS16 dimensions must fit unsigned 16-bit integers")
    pixels = list(image.getdata())
    key = pixels[0][:3] if transparent_corner else None
    pixels = [(*pixel[:3], 0) if pixel[:3] == key else pixel for pixel in pixels]
    if any(pixel[3] not in (0, 255) for pixel in pixels):
        raise ValueError("TS16 supports only opaque or transparent pixels")
    opaque = [pixel[:3] for pixel in pixels if pixel[3]]
    if opaque:
        samples = Image.new("RGB", (len(opaque), 1))
        samples.putdata(opaque)
        quantized = samples.quantize(colors=15, dither=Image.Dither.NONE)
        raw_palette = quantized.getpalette()
        colors = [tuple(raw_palette[i * 3:i * 3 + 3])
                  for i in range(len(quantized.getcolors()))]
    else:
        colors = [(0, 0, 0)]
    mapped = {}
    indices = []
    for r, g, b, alpha in pixels:
        if not alpha:
            indices.append(0)
            continue
        rgb = (r, g, b)
        if rgb not in mapped:
            mapped[rgb] = 1 + min(range(len(colors)), key=lambda index: sum(
                (left - right) ** 2 for left, right in zip(rgb, colors[index])))
        indices.append(mapped[rgb])
    palette = [(0, 0, 0)] + colors + [(0, 0, 0)] * (15 - len(colors))
    palette_bytes = b"".join(struct.pack(">H", ((r & 248) << 8) |
                                         ((g & 252) << 3) | (b >> 3))
                             for r, g, b in palette)
    packed = bytearray((len(indices) + 1) // 2)
    for position, index in enumerate(indices):
        packed[position // 2] |= index << (4 if position % 2 == 0 else 0)
    return b"TS16" + struct.pack("<HH", width, height) + palette_bytes + packed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--transparent-corner", action="store_true",
                        help="treat the top-left pixel's RGB color as transparent")
    args = parser.parse_args()
    with Image.open(args.source) as image:
        payload = encode(image, args.transparent_corner)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print("%s: %d bytes" % (args.output, len(payload)))


if __name__ == "__main__":
    main()
