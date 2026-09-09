"""Pixel-level checks of the shipped atlas in both Racer render paths."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_racer_entities import RACER, ROOT
from tests.test_racer_rendering import PixelCanvas
from tests.image_support import IMAGE_MODULES, sprites as SPRITES


ATLAS = ROOT / "src/files/assets/racer.ts16"


def load_art():
    with patch.dict("sys.modules", IMAGE_MODULES):
        return RACER.RacerArt(str(ATLAS))


def renderer(canvas, game, art):
    return RACER.RoadRenderer(canvas, game, canvas.width, 48, 4,
                              art.grass, art.asphalt, "marker", "car", art)


class SpriteTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", IMAGE_MODULES))

    def test_atlas_decoding_matches_palette_pixels_and_transparency(self):
        sheet = SPRITES.SpriteSheet(str(ATLAS))
        self.assertLess(ATLAS.stat().st_size, 8 * 1024)
        for cell in range(7):
            with self.subTest(cell=cell):
                canvas = PixelCanvas(32, 32)
                sprite = sheet.sprite(cell * 32, 0, 32, 32)
                sprite.draw(canvas, 0, 0, (0, 0, 32, 32))
                for y in range(32):
                    for x in range(32):
                        index = sheet.index_at(cell * 32 + x, y)
                        expected = sheet.palette[index] if index else 0
                        self.assertEqual(canvas.pixels[y][x], expected)

    def test_scaled_sprite_clips_all_edges_and_target_offset(self):
        sheet = SPRITES.SpriteSheet(str(ATLAS))
        sprite = sheet.sprite(0, 0, 32, 32, scale=2)
        reference = PixelCanvas(64, 64)
        sprite.draw(reference, 0, 0, (0, 0, 64, 64))
        canvas = PixelCanvas(12, 18)
        sprite.draw(canvas, 0, 0, (20, 15, 12, 18), 20, 15)
        self.assertEqual(canvas.pixels,
                         [row[20:32] for row in reference.pixels[15:33]])

    def test_rejects_corrupt_sheets_and_out_of_bounds_crops(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.ts16"
            for contents in (b"bad", ATLAS.read_bytes()[:-1]):
                path.write_bytes(contents)
                with self.assertRaises(ValueError):
                    SPRITES.SpriteSheet(str(path))
        sheet = SPRITES.SpriteSheet(str(ATLAS))
        with self.assertRaises(ValueError):
            sheet.sprite(sheet.width - 1, 0, 2, 1)

    def test_flipped_animal_matches_horizontal_mirror(self):
        sheet = SPRITES.SpriteSheet(str(ATLAS))
        for cell in (5, 6):
            right, left = PixelCanvas(32, 32), PixelCanvas(32, 32)
            sheet.sprite(cell * 32, 0, 32, 32).draw(right, 0, 0, (0, 0, 32, 32))
            sheet.sprite(cell * 32, 0, 32, 32, flip_x=True).draw(
                left, 0, 0, (0, 0, 32, 32))
            self.assertEqual(left.pixels, [row[::-1] for row in right.pixels])


class RacerSpriteTests(unittest.TestCase):
    def test_stationary_hazards_coins_and_crash_freeze(self):
        game = RACER.create_race(320, 480)
        kinds = {kind.name: kind for kind in game.entity_kinds}
        self.assertEqual(set(kinds), {"coin", "cow", "pylon", "oil"})
        for kind in kinds.values():
            game.entities.clear()
            entity = game.spawn_entity(kind, 80)
            x, y = entity.x, entity.y
            entity.advance(50, 4, game.road_left, game.road_right)
            self.assertEqual((entity.x, entity.y), (x, y + 4))
        game.entities.clear()
        game.spawn_entity(kinds["coin"], game.player_y).x_milli = game.player_x * 1000
        game.step(0)
        self.assertEqual(game.score, 1)
        self.assertFalse(game.entities)
        for name in ("cow", "pylon", "oil"):
            game.crashed = False
            game.entities.clear()
            game.spawn_entity(kinds[name], game.player_y).x_milli = game.player_x * 1000
            game.step(0)
            self.assertTrue(game.crashed)
            before = game.road.distance
            self.assertEqual(game.step(50), 0)
            self.assertEqual(game.road.distance, before)

    def test_both_animators_match_full_redraw_through_contacts_and_steering(self):
        art = load_art()
        for scanout in (False, True):
            with self.subTest(scanout=scanout):
                game = RACER.create_race(240, 320)
                game.entities.clear()
                canvas = PixelCanvas(240, 320)
                road_renderer = renderer(canvas, game, art)
                coin = game.entity_kinds[0]
                # Overlap the player: collection must clear transparent edges too.
                game.add_entity(RACER.Entity(coin, game.player_x, game.player_y))
                game.add_entity(RACER.Entity(coin, 70, 49))
                road_renderer.rebuild((0, 48, 240, 272))
                if scanout:
                    bands = RACER.RoadBandCache(canvas, road_renderer, 4, 12,
                                               PixelCanvas)
                    animator = RACER.ScanoutAnimator(game, road_renderer, bands)
                else:
                    animator = RACER.DirtyRegionAnimator(game, road_renderer)
                for frame in range(18):
                    animator.begin_frame()
                    game.begin_frame()
                    if frame % 3 == 0:
                        game.move_player(18 if frame % 2 else -18)
                    for unused in range(2):
                        animator.record_step(game.step(50))
                    animator.present()
                    reference = PixelCanvas(240, 320)
                    renderer(reference, game, art).rebuild((0, 48, 240, 272))
                    self.assertEqual(canvas.pixels, reference.pixels)
                self.assertEqual(game.score, 1)

    def test_hud_only_updates_on_change_and_never_writes_track(self):
        art = load_art()
        game = RACER.create_race(240, 320)
        canvas = PixelCanvas(240, 320)
        hud = RACER.RacerHUD(canvas, game, art)
        self.assertTrue(hud.draw())
        self.assertFalse(hud.draw())
        original = [row[:] for row in canvas.pixels[:48]]
        game.score += 1
        self.assertTrue(hud.draw())
        self.assertNotEqual(original, canvas.pixels[:48])
        game.crashed = True
        self.assertTrue(hud.draw())
        self.assertTrue(all(area == (0, 0, 240, 48) for area in canvas.shows))
        self.assertTrue(all(not any(row) for row in canvas.pixels[48:]))


if __name__ == "__main__":
    unittest.main()
