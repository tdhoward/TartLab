"""Pack Racer art, road swatches, lane marker and HUD font into a 7 KiB atlas.

Requires Pillow on the host only. Run from any directory; no device tools needed.
"""

from pathlib import Path
import struct

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "tools/assets/racer"
PALETTE = (
    (255, 0, 255), (12, 17, 26), (45, 52, 62), (44, 108, 58),
    (242, 244, 230), (146, 161, 167), (214, 26, 25), (255, 85, 26),
    (255, 155, 16), (255, 219, 38), (162, 91, 14), (11, 72, 151),
    (31, 175, 237), (98, 52, 158), (242, 154, 157), (114, 75, 43),
)


def build():
    source = Image.open(ART / "isometric-source.png").convert("RGBA")
    car_source = Image.open(ART / "car-topdown-source.png").convert("RGBA")
    sheet = Image.new("RGB", (224, 64), PALETTE[0])
    for index, size in enumerate(((30, 30), (30, 28), (24, 28),
                                  (30, 24), (22, 24), (30, 26), (22, 24))):
        column, row = index % 4, index // 4
        atlas = car_source if index == 0 else source
        cell = atlas.crop((column * atlas.width // 4, row * atlas.height // 2,
                           (column + 1) * atlas.width // 4,
                           (row + 1) * atlas.height // 2))
        # Accept alpha or the source sheet's magenta color key.
        mask = cell.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        mask.putdata([0 if (r > 190 and g < 100 and b > 150) else alpha
                      for (r, g, b, unused), alpha in zip(cell.getdata(), mask.getdata())])
        cell.putalpha(mask)
        cell = cell.crop(mask.getbbox())
        cell.thumbnail(size, Image.Resampling.NEAREST)
        sheet.paste(cell, (index * 32 + (32 - cell.width) // 2,
                           (32 - cell.height) // 2), cell.getchannel("A"))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((1, 32, 5, 39), fill=PALETTE[4])
    for index in range(1, 16):
        draw.point((8 + index, 32), fill=PALETTE[index])
    font = ImageFont.load_default_imagefont()
    for index in range(64):
        glyph = Image.new("RGB", (6, 11), PALETTE[0])
        ImageDraw.Draw(glyph).text((0, 0), chr(32 + index),
                                  font=font, fill=PALETTE[4])
        sheet.paste(glyph.crop((0, 2, 6, 10)),
                    ((index % 26) * 6, 40 + (index // 26) * 8))
    palette = Image.new("P", (1, 1))
    palette.putpalette([channel for rgb in PALETTE for channel in rgb] +
                       list(PALETTE[0]) * 240)
    indexed = sheet.quantize(palette=palette, dither=Image.Dither.NONE)
    pixels = [value if value < 16 else 0 for value in indexed.getdata()]
    packed = bytes((pixels[i] << 4) | pixels[i + 1]
                   for i in range(0, len(pixels), 2))
    colors = b"".join(struct.pack(">H", ((r & 248) << 8) | ((g & 252) << 3) | (b >> 3))
                      for r, g, b in PALETTE)
    destination = ROOT / "src/files/assets/racer.ts16"
    destination.write_bytes(b"TS16" + struct.pack("<HH", 224, 64) + colors + packed)
    indexed.save(ART / "sheet.png")
    print("%s: %d bytes" % (destination, destination.stat().st_size))


if __name__ == "__main__":
    build()
