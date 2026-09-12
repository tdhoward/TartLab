"""Validate/rebuild the original grid puzzle atlas (host-only Pillow).

Default: encode the editable canonical sheet. --check verifies checked-in output
without writing. --from-source repeats the documented generated-art import.
"""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

try:
    from tools.convert_ts16 import encode
except ModuleNotFoundError:
    from convert_ts16 import encode


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "tools/assets/grid_puzzle"
OUTPUT = ROOT / "src/files/assets/grid_puzzle.ts16"
PALETTE = (
    (21, 39, 53), (40, 64, 78), (65, 93, 105), (126, 153, 160),
    (255, 242, 202), (169, 112, 44), (211, 155, 64), (101, 66, 34),
    (235, 133, 37), (255, 205, 85), (189, 51, 66), (0, 72, 93),
    (0, 159, 175), (109, 225, 230), (130, 83, 202),
)
NAMES = (
    ["floor"] + ["wall_%s" % i for i in range(10)] +
    ["dirt_%s" % i for i in range(10)] +
    ["key", "diamond", "boulder", "exit_locked", "exit_open"] +
    ["player_" + d for d in "NESW"] + ["snake_W", "snake_E"] +
    ["spider_" + d for d in "NESW"] + ["emitter_" + d for d in "NESW"] +
    ["water_0", "water_1", "water_2", "tip_N", "tip_E", "tip_S", "tip_W", "pad",
     "water_3", "water_4", "water_5", "shaft_NS", "shaft_EW", "blast_0", "blast_1",
     "blast_2", "water_6", "water_7", "water_8"]
)
TERRAIN = set(range(21)) | {40, 41, 42, 48, 49, 50, 56, 57, 58}


def import_source(source):
    """Fixed cell crops, nearest scaling, binary alpha and a fixed 15-color map.

    This is atlas preparation, not a runtime dependency. The original generated
    raster is retained for provenance; sheet.png is the canonical editable art.
    """
    if source.width != source.height or source.width < 128:
        raise ValueError("source must be a square 8x8 cell sheet, at least 128px")
    source = source.convert("RGBA")
    sheet = Image.new("RGBA", (128, 128))
    mapped = {}
    for index in range(len(NAMES)):
        column, row = index % 8, index // 8
        # Exclude the generated sheet's thin separator lines.
        crop = source.crop((round(column * source.width / 8) + 2,
                            round(row * source.height / 8) + 2,
                            round((column + 1) * source.width / 8) - 2,
                            round((row + 1) * source.height / 8) - 2))
        size = 16 if index in TERRAIN else 14
        crop = crop.resize((size, size), Image.Resampling.NEAREST)
        pixels = []
        for r, g, b, alpha in crop.getdata():
            if index not in TERRAIN and (alpha < 160 or (r > 180 and b > 140 and g < 100)):
                pixels.append((0, 0, 0, 0))
                continue
            rgb = (r, g, b)
            key = (rgb, index == 49)
            if key not in mapped:
                # W4 is exclusively water; outer variants keep their banks.
                palette = PALETTE[11:14] if index == 49 else PALETTE
                mapped[key] = min(palette, key=lambda color: sum(
                    (a - b) ** 2 for a, b in zip(rgb, color)))
            pixels.append((*mapped[key], 255))
        crop.putdata(pixels)
        inset = (16 - size) // 2
        sheet.paste(crop, (column * 16 + inset, row * 16 + inset))
    return sheet


def validate_sheet(sheet):
    if sheet.size != (128, 128):
        raise ValueError("atlas must be 128x128: 8x8 aligned 16x16 cells")
    sheet = sheet.convert("RGBA")
    pixels = list(sheet.getdata())
    if any(pixel[3] not in (0, 255) for pixel in pixels):
        raise ValueError("atlas alpha must be binary (0 or 255)")
    colors = {pixel[:3] for pixel in pixels if pixel[3]}
    if len(colors) > 15:
        raise ValueError("atlas supports at most 15 opaque colors")
    for index, name in enumerate(NAMES):
        x, y = index % 8 * 16, index // 8 * 16
        tile = list(sheet.crop((x, y, x + 16, y + 16)).getdata())
        if not any(pixel[3] for pixel in tile):
            raise ValueError("required sprite %s is empty" % name)
        if index in TERRAIN and any(pixel[3] != 255 for pixel in tile):
            raise ValueError("terrain %s must fill its entire cell" % name)
    water_center = list(sheet.crop((16, 96, 32, 112)).getdata())
    if any(pixel[:3] not in PALETTE[11:14] for pixel in water_center):
        raise ValueError("water_4 must contain only water palette colors")
    return sheet


def products(sheet, source_path=ART / "source.png"):
    sheet = validate_sheet(sheet)
    payload = encode(sheet)  # Use the existing repository format encoder.
    index = {
        "tile_size": 16, "columns": 8, "rows": 8,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "rgba_sha256": hashlib.sha256(sheet.tobytes()).hexdigest(),
        "ts16_sha256": hashlib.sha256(payload).hexdigest(),
        "ts16_bytes": len(payload), "palette_rgb": PALETTE,
        "tiles": {name: [i % 8 * 16, i // 8 * 16, 16, 16] for i, name in enumerate(NAMES)},
    }
    return payload, json.dumps(index, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--from-source", action="store_true")
    args = parser.parse_args()
    try:
        with Image.open(ART / ("source.png" if args.from_source else "sheet.png")) as image:
            sheet = import_source(image) if args.from_source else image.convert("RGBA")
        payload, index = products(sheet)
        if args.check:
            if OUTPUT.read_bytes() != payload or (ART / "index.json").read_text(encoding="utf-8") != index:
                raise ValueError("atlas/index out of date; run the builder")
            with Image.open(ART / "preview.png") as preview:
                expected = sheet.resize((768, 768), Image.Resampling.NEAREST)
                if preview.size != expected.size or preview.convert("RGBA").tobytes() != expected.tobytes():
                    raise ValueError("preview out of date; run the builder")
        else:
            OUTPUT.write_bytes(payload)
            sheet.save(ART / "sheet.png")
            sheet.resize((768, 768), Image.Resampling.NEAREST).save(ART / "preview.png")
            (ART / "index.json").write_text(index, encoding="utf-8")
        print("PASS: %s sprites; %s bytes; atlas/index/preview %s" %
              (len(NAMES), len(payload), "verified" if args.check else "rebuilt"))
        return 0
    except (OSError, ValueError) as error:
        print("FAIL: %s" % error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
