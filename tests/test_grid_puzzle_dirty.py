"""Compare framebuffer AND transmitted pixels with the independent full path."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tests.grid_puzzle_support import ENGINE as g, room, prepare_art
from tests.image_support import IMAGE_MODULES

ROOT = Path(__file__).resolve().parents[1]


class DisplayCanvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.buffer = Image.new("I", (width, height))
        self.display = self.buffer.copy()
        self.pen = ImageDraw.Draw(self.buffer)
        self.transfers = []

    def fill(self, color):
        self.pen.rectangle((0, 0, self.width - 1, self.height - 1), fill=color)

    def rect(self, x, y, w, h, color, fill=False):
        self.pen.rectangle((x, y, x + w - 1, y + h - 1),
                           fill=color if fill else None, outline=color)

    def hline(self, x, y, width, color):
        self.pen.line((x, y, x + width - 1, y), fill=color)

    def line(self, x1, y1, x2, y2, color):
        self.pen.line((x1, y1, x2, y2), fill=color)

    def text(self, text, x, y, color):
        # framebuf text occupies exactly 8x8 per glyph, including descenders.
        for index, character in enumerate(text):
            mask = Image.new("1", (8, 8))
            ImageDraw.Draw(mask).text((0, -2), character, fill=1)
            self.buffer.paste(color, (x + index * 8, y, x + index * 8 + 8, y + 8), mask)

    def show(self, area=None):
        x, y, w, h = area or (0, 0, self.width, self.height)
        self.transfers.append((x, y, w, h))
        self.display.paste(self.buffer.crop((x, y, x + w, y + h)), (x, y))


class DirtyRenderingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", IMAGE_MODULES))

    def setup_room(self, definition, dimensions=(480, 222), debug=False):
        layout = g.choose_layout(*dimensions)
        session = g.Session({"levels": [definition]})
        prepare_art(session, layout.scale)
        dirty = DisplayCanvas(layout.width, layout.height)
        reference = DisplayCanvas(layout.width, layout.height)
        session.renderer = g.Renderer(dirty, layout, debug)
        return session, dirty, reference, layout

    def compare(self, setup, action=None):
        session, dirty, reference, layout = setup
        session.renderer.present(session, action)
        g.draw_full_game(reference, session, layout, action, session.renderer.inspector or False)
        self.assertEqual(dirty.buffer.tobytes(), reference.buffer.tobytes(), "framebuffer differs")
        self.assertEqual(dirty.display.tobytes(), reference.display.tobytes(), "transmitted image differs")
        self.assertLessEqual(session.renderer.damage.count, session.renderer.damage.capacity)

    def test_every_solution_frame_and_catchup_matches_at_both_scales_and_cadences(self):
        pack = g.load_level_pack(str(ROOT / "src/files/help/grid_puzzle_levels.json"))
        solutions = json.loads((ROOT / "tests/fixtures/grid_puzzle/solutions.json").read_text())["solutions"]
        for dimensions in ((222, 480), (800, 480)):
            for batch in (5, 6):
                for recording in solutions:
                    setup = self.setup_room(pack["levels"][recording["room"]], dimensions)
                    session = setup[0]
                    self.compare(setup)
                    index = 0
                    for elapsed in range(0, recording["end_ms"], 10):
                        events = recording["events"]
                        while index < len(events) and events[index]["at_ms"] <= elapsed:
                            event = events[index]
                            if event["action"] == "press":
                                session.direction = g.ACTION_DIRECTIONS[event["direction"]]
                            elif event["action"] == "release":
                                session.direction = None
                            elif event["action"] == "dismiss":
                                g.dismiss_message(session.state)
                                session.direction = None
                            index += 1
                        session.advance(1)
                        if elapsed // 10 % batch == batch - 1:
                            self.compare(setup)
                    self.compare(setup)
                    self.assertEqual(session.state.status, g.COMPLETED)

    def test_hazards_blast_frames_expiry_and_restart_match(self):
        pack = g.load_level_pack(str(ROOT / "tests/fixtures/grid_puzzle/hazards.json"))
        for definition in pack["levels"]:
            setup = self.setup_room(definition)
            self.compare(setup)
            for unused in range(18):
                setup[0].advance(5)
                self.compare(setup)
            setup[0].restart()
            self.compare(setup, "restart")
            self.compare(setup)

    def test_sparse_damage_is_bounded_and_unchanged_frame_sends_nothing(self):
        setup = self.setup_room(g.validate_level(room()))
        session, canvas, _, _ = setup
        self.compare(setup)
        canvas.transfers.clear()
        session.direction = g.EAST
        session.advance(30)  # Three moves; the last quantum alone has no change.
        self.compare(setup)
        self.assertLess(sum(w * h for x, y, w, h in canvas.transfers), 192 * 256 // 4)
        canvas.transfers.clear()
        self.compare(setup)
        self.assertEqual(canvas.transfers, [])

    def test_debug_toggle_pause_step_selection_and_trails_do_not_change_rules(self):
        definition = g.validate_level(room({(8, 8): "Xe", (4, 4): "F2", (2, 5): "T3", (7, 2): "T3", (12, 7): "RW"}))
        setup = self.setup_room(definition, debug=True)
        session = setup[0]
        expected = g.Session({"levels": [definition]})
        self.compare(setup)
        for unused in range(50):
            session.advance(5)
            expected.advance(5)
        self.assertEqual([(a.cell, a.next_due_ms) for a in session.state.actors],
                         [(a.cell, a.next_due_ms) for a in expected.state.actors])
        inspector = session.renderer.inspector
        self.assertTrue(all(len(trail) <= inspector.TRAIL_LENGTH for trail in inspector.trails.values()))
        before = copy.deepcopy(session.state.__dict__)
        self.compare(setup)
        self.assertEqual(session.state.actor_at, before["actor_at"])
        self.assertEqual(session.state.elapsed_ms, before["elapsed_ms"])
        session.state.paused = True
        inspector.select(8 * 16 + 8)
        self.compare(setup, "pause")
        now = session.state.elapsed_ms
        self.assertTrue(g.debug_step(session, g.EAST))
        self.assertEqual(session.state.elapsed_ms, now + 10)
        self.assertTrue(session.state.paused)
        self.compare(setup, "step")
        session.renderer.toggle_debug(session.state)
        self.assertIsNone(session.renderer.inspector)
        self.compare(setup)
        session.restart()
        self.compare(setup)

    def test_previews_use_live_blocker_and_move_queries(self):
        state = g.create_state(g.validate_level(room({(2, 3): "S.", (6, 3): "D.", (10, 8): "Xe"})))
        snake = next(a for a in state.actors if a.kind == g.SNAKE)
        snake.heading = g.EAST
        cells, blocker = g.ray_preview(state, snake)
        self.assertEqual(blocker, g.cell_at(6, 3))
        self.assertNotIn(blocker, cells)
        with patch.object(g, "blocks_snake_ray", return_value=False):
            self.assertEqual(g.ray_preview(state, snake)[1], -1)
        inspector = g.Inspector(state)
        spider = next(a for a in state.actors if a.kind == g.SPIDER)
        inspector.select(spider.cell)
        with patch.object(g, "next_spider_heading", return_value=g.SOUTH):
            self.assertIn("Follow L next S", inspector.lines(state, 80))

    def test_native_prepared_layers_match_spans_with_transparency_and_rotation(self):
        import types
        from tests.test_app import load_app, FakeSurface, FakeFrameBuffer, fake_lvgl
        app = load_app(types.SimpleNamespace(), fake_lvgl())
        framebuf = types.SimpleNamespace(FrameBuffer=FakeFrameBuffer, RGB565=1)
        definition = g.validate_level(room({(1, 0): "D.", (2, 0): "O.", (3, 0): "W4",
                                           (6, 5): "Xe", (8, 8): "RW"}))
        for rotation in (0, 90, 180, 270):
            session = g.Session({"levels": [definition]})
            layout = g.Layout(480, 320, rotation, 1, "side", True)
            width, height = (320, 480) if rotation % 180 else (480, 320)
            native = app.DirectCanvas(FakeSurface(width, height), rotation=rotation)
            reference = app.DirectCanvas(FakeSurface(width, height), rotation=rotation)
            art = prepare_art(session)
            with patch.dict("sys.modules", {"framebuf": framebuf}):
                art.prepare(definition, native)
            native.fill(123)
            reference.fill(123)
            for unused in range(3):
                g.draw_board(native, session.state, layout, art)
                g.draw_board(reference, session.state, layout, art)
                self.assertEqual(bytes(native.buffer), bytes(reference.buffer))
                session.direction = g.EAST
                session.advance(11)
            prepared = art.prepared
            art.prepare(definition, native)
            self.assertIs(art.prepared, prepared)
            art.close()
            self.assertFalse(art.prepared)


if __name__ == "__main__":
    unittest.main()
