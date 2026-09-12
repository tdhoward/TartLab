"""Pixel outcomes and resource boundaries for the actual shipped artwork."""

from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

from tests.grid_puzzle_support import ENGINE as g, room, prepare_art
from tests.image_support import IMAGE_MODULES, sprites
from tools import build_grid_puzzle_sprites as builder


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "src/files/assets/grid_puzzle.ts16"


class PixelCanvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.pixels = [[0] * width for unused in range(height)]

    def fill_rect(self, x, y, width, height, color):
        for row in range(max(0, y), min(self.height, y + height)):
            for column in range(max(0, x), min(self.width, x + width)):
                self.pixels[row][column] = color

    def hline(self, x, y, width, color):
        self.fill_rect(x, y, width, 1, color)


class GridPuzzleSpriteTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", IMAGE_MODULES))

    def test_canonical_sheet_rebuild_matches_shipped_asset_and_index(self):
        with Image.open(builder.ART / "sheet.png") as sheet:
            payload, index = builder.products(sheet)
        self.assertEqual(ATLAS.read_bytes(), payload)
        self.assertEqual((builder.ART / "index.json").read_text(encoding="utf-8"), index)
        self.assertEqual(len(payload), 8232)
        with Image.open(builder.ART / "source.png") as source:
            normalized = builder.import_source(source)
        with Image.open(builder.ART / "sheet.png") as sheet:
            self.assertEqual(normalized.tobytes(), sheet.tobytes())

    def test_builder_rejects_size_alpha_palette_missing_variant_and_water_land(self):
        with Image.open(builder.ART / "sheet.png") as original:
            for failure in ("size", "alpha", "palette", "missing", "water"):
                sheet = original.convert("RGBA")
                if failure == "size":
                    sheet = sheet.crop((0, 0, 127, 128))
                elif failure == "alpha":
                    sheet.putpixel((0, 0), (21, 39, 53, 100))
                elif failure == "palette":
                    for i in range(16):
                        sheet.putpixel((i, 0), (i, 0, 0, 255))
                elif failure == "missing":
                    sheet.paste((0, 0, 0, 0), (0, 16, 16, 32))
                else:
                    sheet.putpixel((16, 96), (*builder.PALETTE[6], 255))
                with self.subTest(failure=failure), self.assertRaises(ValueError):
                    builder.validate_sheet(sheet)

    def test_all_59_sprites_match_encoded_pixels_at_integer_scales(self):
        sheet = sprites.SpriteSheet(str(ATLAS))
        for scale in (1, 2, 3):
            for index in range(len(builder.NAMES)):
                x, y = index % 8 * 16, index // 8 * 16
                canvas = PixelCanvas(16 * scale, 16 * scale)
                sprite = sheet.sprite(x, y, 16, 16, scale=scale)
                sprite.draw(canvas, 0, 0, (0, 0, canvas.width, canvas.height))
                for cy, row in enumerate(canvas.pixels):
                    for cx, color in enumerate(row):
                        palette_index = sheet.index_at(x + cx // scale, y + cy // scale)
                        expected = sheet.palette[palette_index] if palette_index else 0
                        self.assertEqual(color, expected)

    def test_scaled_transparency_and_clipping_keep_surrounding_pixels(self):
        sheet = sprites.SpriteSheet(str(ATLAS))
        sprite = sheet.sprite(32, 48, 16, 16, scale=2)
        reference, cropped = PixelCanvas(32, 32), PixelCanvas(13, 17)
        reference.fill_rect(0, 0, 32, 32, 123)
        cropped.fill_rect(0, 0, 13, 17, 123)
        sprite.draw(reference, 0, 0, (0, 0, 32, 32))
        sprite.draw(cropped, 0, 0, (8, 9, 13, 17), 8, 9)
        self.assertEqual(cropped.pixels, [row[8:21] for row in reference.pixels[9:26]])
        self.assertTrue(any(color == 123 for row in reference.pixels for color in row))

    def test_every_hidden_wall_variant_and_pad_is_pixel_identical_normally(self):
        hidden_cells = {(i, 3): "F%s" % i for i in range(10)}
        visible_cells = {(i, 3): "#%s" % i for i in range(10)}
        hidden_cells.update({(3, 4): "T0", (5, 4): "T0"})
        for dimensions in ((480, 222), (800, 480)):
            layout = g.choose_layout(*dimensions)
            canvases = []
            for cells in (hidden_cells, visible_cells):
                session = g.Session({"levels": [g.validate_level(room(cells))]})
                art = prepare_art(session, layout.scale)
                canvas = PixelCanvas(layout.width, layout.height)
                g.draw_board(canvas, session.state, layout, art)
                canvases.append(canvas)
            self.assertEqual(canvases[0].pixels, canvases[1].pixels)

    def test_cleared_dirt_wall_water_and_old_player_cells_restore_floor_pixels(self):
        session = g.Session({"levels": [g.validate_level(room({
            (1, 0): "d7", (2, 0): "F3", (3, 0): "O.", (4, 0): "W4"}))]})
        art = prepare_art(session)
        layout = g.choose_layout(480, 222)
        canvas = PixelCanvas(layout.width, layout.height)
        g.draw_board(canvas, session.state, layout, art)
        session.direction = g.EAST
        session.advance(50)
        g.draw_board(canvas, session.state, layout, art)
        # Player has passed all changed cells. A fresh empty room with the same
        # actor position is the reference; this comparison covers every pixel.
        fresh = g.Session({"levels": [g.validate_level(room({(0, 0): "..", (5, 0): "P."}))]})
        fresh.state.player.heading = g.EAST
        reference = PixelCanvas(layout.width, layout.height)
        g.draw_board(reference, fresh.state, layout, prepare_art(fresh))
        self.assertEqual(canvas.pixels, reference.pixels)

    def test_active_room_cache_reuses_restarts_and_replaces_old_room_resources(self):
        first = g.validate_level(room({(1, 0): "d1", (2, 0): "F4", (3, 0): "D."}))
        second = g.validate_level(room({(1, 0): "W8"}))
        art = g.PuzzleArt(str(ATLAS), 1)
        with patch.object(sprites, "SpriteSheet", wraps=sprites.SpriteSheet) as decoder:
            art.prepare(first)
            before = dict(art.sprites)
            for unused in range(25):
                art.prepare(g.create_state(first).definition)
            self.assertEqual(decoder.call_count, 1)
            self.assertTrue(all(art.sprites[key] is value for key, value in before.items()))
            art.prepare(second)
            self.assertEqual(decoder.call_count, 2)
            self.assertNotIn(g.ART_DIRT + 1, art.sprites)
            self.assertNotIn(g.ART_DIAMOND, art.sprites)
            self.assertIn(g.ART_WATER[8], art.sprites)
        art.close()
        self.assertEqual(art.sprites, {})


if __name__ == "__main__":
    unittest.main()
