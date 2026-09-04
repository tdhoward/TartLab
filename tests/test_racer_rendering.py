import unittest

from tests.test_racer_entities import RACER, kind, state


WIDTH = 60
HEIGHT = 80
TRACK_TOP = 8
GRASS = 1
ASPHALT = 2
MARKER = 3
PLAYER = 4


class PixelCanvas:
    def __init__(self, width=WIDTH, height=HEIGHT):
        self.width = width
        self.height = height
        self.pixels = [[0] * width for unused in range(height)]
        self.shows = []
        self.drawing_after_show = False

    def _changed(self):
        if self.shows:
            self.drawing_after_show = True

    def fill_rect(self, x, y, width, height, color):
        self._changed()
        for target_y in range(max(0, y), min(self.height, y + height)):
            row = self.pixels[target_y]
            for target_x in range(max(0, x), min(self.width, x + width)):
                row[target_x] = color

    def hline(self, x, y, width, color):
        self.fill_rect(x, y, width, 1, color)

    def show(self, area=None):
        self.shows.append(tuple(area) if area is not None else None)

    def prepare_sprite(self, framebuffer, width, height):
        self.assert_size = (framebuffer.width, framebuffer.height)
        if self.assert_size != (width, height):
            raise ValueError("sprite dimensions do not match")
        return framebuffer

    def scroll_region(self, area, dx=0, dy=0, fill=0, exposed=None):
        left, top, width, height = area
        before = [row[:] for row in self.pixels]
        for y in range(top, top + height):
            for x in range(left, left + width):
                source_x = x - dx
                source_y = y - dy
                if (left <= source_x < left + width and
                        top <= source_y < top + height):
                    self.pixels[y][x] = before[source_y][source_x]
                elif exposed is None:
                    self.pixels[y][x] = fill
                else:
                    exposed_x = x - left if dx == 0 else None
                    exposed_y = y - top if dy > 0 else y - (top + height + dy)
                    self.pixels[y][x] = exposed.pixels[exposed_y][exposed_x]
        if dy > 0:
            self.show((left, top, width, dy))
        elif dy < 0:
            self.show((left, top + height + dy, width, -dy))

    def scroll_capabilities(self):
        return {
            "axes": ("y",),
            "fixed_areas": True,
            "wraps": True,
            "full_orthogonal_axis": True,
        }


def make_scene(entity_kinds=()):
    road = RACER.RoadState(((0, 80),), 1, 16)
    game = RACER.GameState(
        road, 10, 50, TRACK_TOP, HEIGHT, 30, 66, 3,
        entity_kinds, spawn_gap=10000)
    canvas = PixelCanvas()
    renderer = RACER.RoadRenderer(
        canvas, game, WIDTH, 16, 2,
        GRASS, ASPHALT, MARKER, PLAYER)
    animator = RACER.DirtyRegionAnimator(
        game, renderer, capacity=12, merge_overhead=8)
    renderer.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))
    return game, canvas, renderer, animator


def full_reference(game, renderer):
    canvas = PixelCanvas()
    reference = RACER.RoadRenderer(
        canvas, game, WIDTH, 16, 2,
        GRASS, ASPHALT, MARKER, PLAYER)
    reference.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))
    return canvas.pixels


class RacerRenderingTests(unittest.TestCase):
    def assert_matches_full_redraw(self, game, canvas, renderer):
        self.assertEqual(canvas.pixels, full_reference(game, renderer))

    def test_layer_order_and_player_last_for_overlapping_entities(self):
        high = kind("high", 5)
        high.visual = 8
        high.draw_layer = 2
        low = kind("low", 5)
        low.visual = 7
        low.draw_layer = -1
        game, canvas, renderer, unused = make_scene((high, low))
        game.add_entity(RACER.Entity(high, 30, 40, road_relative=False))
        game.add_entity(RACER.Entity(low, 30, 40, road_relative=False))

        renderer.rebuild((20, 30, 20, 40))

        self.assertEqual(canvas.pixels[40][30], 8)
        self.assertEqual(canvas.pixels[66][30], PLAYER)

    def test_motion_and_centerline_phase_match_a_full_redraw(self):
        moving_kind = kind("moving", 3)
        moving_kind.visual = 6
        game, canvas, renderer, animator = make_scene((moving_kind,))
        game.add_entity(RACER.Entity(
            moving_kind, 22, 25, horizontal_velocity=20,
            boundary_policy=None))
        renderer.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))

        animator.begin_frame()
        game.begin_frame()
        animator.record_step(game.step(50))
        animator.present()

        self.assert_matches_full_redraw(game, canvas, renderer)
        self.assertTrue(canvas.shows)
        self.assertFalse(canvas.drawing_after_show)

    def test_collection_and_removal_restore_overlapping_background(self):
        coin = kind("coin", 4, RACER.collect_on_contact)
        coin.visual = 9
        game, canvas, renderer, animator = make_scene((coin,))
        game.add_entity(RACER.Entity(
            coin, game.player_x, game.player_y, road_relative=False))
        renderer.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))

        animator.begin_frame()
        game.begin_frame()
        animator.record_step(game.step(0))
        animator.present()

        self.assertEqual(game.score, 1)
        self.assert_matches_full_redraw(game, canvas, renderer)

    def test_player_steering_restores_old_position(self):
        game, canvas, renderer, animator = make_scene()

        animator.begin_frame()
        game.move_player(8)
        animator.present()

        self.assert_matches_full_redraw(game, canvas, renderer)

    def test_arbitrary_damage_is_clipped_at_every_track_edge(self):
        game, canvas, renderer, animator = make_scene()
        for row in canvas.pixels:
            for index in range(len(row)):
                row[index] = 99

        animator.damage.clear()
        animator.damage.add((-5, TRACK_TOP - 5, 12, 12))
        animator.damage.add((WIDTH - 7, TRACK_TOP - 5, 12, 12))
        animator.damage.add((-5, HEIGHT - 7, 12, 12))
        animator.damage.add((WIDTH - 7, HEIGHT - 7, 12, 12))
        animator.renderer.render(animator.damage)

        reference = full_reference(game, renderer)
        for y in range(TRACK_TOP, TRACK_TOP + 7):
            self.assertEqual(canvas.pixels[y][:7], reference[y][:7])
            self.assertEqual(canvas.pixels[y][-7:], reference[y][-7:])
        for y in range(HEIGHT - 7, HEIGHT):
            self.assertEqual(canvas.pixels[y][:7], reference[y][:7])
            self.assertEqual(canvas.pixels[y][-7:], reference[y][-7:])

    def test_centerline_rebuild_is_horizontally_clipped(self):
        game, canvas, renderer, unused = make_scene()
        before = [row[:] for row in canvas.pixels]

        renderer.rebuild((renderer.center_x, TRACK_TOP, 1, HEIGHT - TRACK_TOP))

        for y in range(HEIGHT):
            for x in range(WIDTH):
                if x != renderer.center_x:
                    self.assertEqual(canvas.pixels[y][x], before[y][x])

    def test_prepared_bands_match_final_background_for_delta_and_phase(self):
        game, canvas, renderer, unused = make_scene()
        bands = RACER.RoadBandCache(
            canvas, renderer, 2, 8,
            lambda width, height: PixelCanvas(width, height))

        for delta in (2, 4, 6, 8):
            for phase in range(0, 16, 2):
                with self.subTest(delta=delta, phase=phase):
                    game.road.center_phase = phase
                    reference = PixelCanvas(WIDTH, HEIGHT)
                    reference_renderer = RACER.RoadRenderer(
                        reference, game, WIDTH, 16, 2,
                        GRASS, ASPHALT, MARKER, PLAYER)
                    reference_renderer.rebuild_background(
                        (0, TRACK_TOP, WIDTH, delta))
                    band = bands.get(delta, phase)
                    self.assertEqual(
                        band.pixels,
                        reference.pixels[TRACK_TOP:TRACK_TOP + delta])

    def test_scanout_reconstructs_fixed_and_horizontally_moving_entities(self):
        plain = kind("plain", 3)
        plain.visual = 6
        game, canvas, renderer, unused = make_scene((plain,))
        game.add_entity(RACER.Entity(
            plain, 18, 24, road_relative=True, boundary_policy=None))
        game.add_entity(RACER.Entity(
            plain, 28, 36, horizontal_velocity=20,
            road_relative=True, boundary_policy=None))
        game.add_entity(RACER.Entity(
            plain, 40, 48, horizontal_velocity=-20,
            road_relative=False, boundary_policy=None))
        game.add_entity(RACER.Entity(
            plain, 20, 58, road_relative=False, boundary_policy=None))
        renderer.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))
        bands = RACER.RoadBandCache(
            canvas, renderer, 1, 8,
            lambda width, height: PixelCanvas(width, height))
        animator = RACER.ScanoutAnimator(
            game, renderer, bands, capacity=12, merge_overhead=8)

        animator.begin_frame()
        game.begin_frame()
        animator.record_step(game.step(50))
        animator.present()

        self.assert_matches_full_redraw(game, canvas, renderer)

    def test_scanout_removal_and_spawn_leave_no_stale_pixels(self):
        coin = kind("coin", 3, RACER.collect_on_contact)
        coin.visual = 9
        game, canvas, renderer, unused = make_scene((coin,))
        game.add_entity(RACER.Entity(
            coin, game.player_x, game.player_y,
            road_relative=False, boundary_policy=None))
        game.next_spawn_distance = 4
        renderer.rebuild((0, TRACK_TOP, WIDTH, HEIGHT - TRACK_TOP))
        bands = RACER.RoadBandCache(
            canvas, renderer, 1, 8,
            lambda width, height: PixelCanvas(width, height))
        animator = RACER.ScanoutAnimator(
            game, renderer, bands, capacity=12, merge_overhead=8)

        animator.begin_frame()
        game.begin_frame()
        animator.record_step(game.step(50))
        animator.present()

        self.assertEqual(game.score, 1)
        self.assertTrue(game.spawned_entities)
        self.assert_matches_full_redraw(game, canvas, renderer)

    def test_scanout_selection_requires_all_reported_capabilities(self):
        game, canvas, unused_renderer, unused_animator = make_scene()
        self.assertTrue(RACER.supports_scanout_animation(canvas))
        for missing in (
                "fixed_areas", "wraps", "full_orthogonal_axis"):
            with self.subTest(missing=missing):
                capabilities = canvas.scroll_capabilities()
                capabilities[missing] = False
                canvas.scroll_capabilities = lambda: capabilities
                self.assertFalse(RACER.supports_scanout_animation(canvas))

        canvas.scroll_capabilities = PixelCanvas().scroll_capabilities
        plain = kind("plain", 2)
        for x in (20, 30, 40):
            game.add_entity(RACER.Entity(plain, x, 20))
        self.assertTrue(RACER.prefers_scanout_animation(canvas, game))
        game.entities[0].horizontal_velocity = 20
        self.assertFalse(RACER.prefers_scanout_animation(canvas, game))


if __name__ == "__main__":
    unittest.main()
