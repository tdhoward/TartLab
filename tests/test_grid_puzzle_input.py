from contextlib import redirect_stdout
import io
import sys
import unittest
from unittest import mock

from tests.grid_puzzle_support import ENGINE as g, load_engine, pack
from tests.test_grid_puzzle_integration import device_modules
from tests.test_timing import FakeTime, make_clock


class GridPuzzleControlsTests(unittest.TestCase):
    def setUp(self):
        self.controls = g.Controls()
        self.layout = g.choose_layout(480, 222)

    def point(self, action):
        if action is None:
            return None
        x, y, _, _ = dict(self.layout.controls)[action]
        return x + 16, y + 16

    def poll(self, action=None, buttons=()):
        return self.controls.poll(self.point(action), buttons, self.layout)

    def test_touch_hold_slide_and_release_never_synthesize_diagonals(self):
        self.poll("east")
        self.assertIsNone(self.controls.direction())
        self.poll()
        for action, direction in g.ACTION_DIRECTIONS.items():
            self.assertIsNone(self.poll(action))
            self.assertEqual(self.controls.direction(), direction)
            self.poll(action)
            self.assertEqual(self.controls.direction(), direction)
        self.poll()
        self.assertIsNone(self.controls.direction())

    def test_touch_actions_are_fresh_edges_and_reset_requires_release(self):
        self.poll()
        self.poll("east")
        self.assertIsNone(self.poll("restart"))  # Sliding is not a fresh press.
        self.poll()
        self.assertEqual(self.poll("restart"), "restart")
        self.controls.reset()
        for action in ("restart", "south", "pause"):
            self.assertIsNone(self.poll(action))
            self.assertIsNone(self.controls.direction())
        self.poll()
        self.assertEqual(self.poll("pause"), "pause")
        self.assertIsNone(self.poll("pause"))

    def test_most_recent_button_or_touch_wins_with_release_fallback(self):
        self.poll()
        self.poll("west", (("right", True), ("up", True)))
        self.assertEqual(self.controls.direction(), g.NORTH)
        self.poll("west", (("up", True),))  # Duplicate events cannot steal priority.
        self.poll("west", (("up", False),))
        self.assertEqual(self.controls.direction(), g.EAST)
        self.poll("west", (("right", False),))
        self.assertEqual(self.controls.direction(), g.WEST)
        self.poll(None, (("down", True),))
        self.assertEqual(self.controls.direction(), g.SOUTH)
        self.poll(None, (("down", False),))
        self.assertIsNone(self.controls.direction())

    def test_initial_buttons_and_actions_require_release_and_new_press(self):
        self.assertIsNone(self.poll(None, (("restart", True), ("left", True))))
        self.poll(None, (("restart", False),))
        self.assertIsNone(self.controls.direction())
        self.poll(None, (("left", False),))
        self.assertEqual(self.poll(None, (("pause", True),)), "pause")
        self.assertIsNone(self.poll(None, (("pause", True),)))
        self.controls.reset()
        self.poll(None, (("right", True),))
        self.assertIsNone(self.controls.direction())
        self.poll(None, (("pause", False), ("right", False)))
        self.poll(None, (("right", True),))
        self.assertEqual(self.controls.direction(), g.EAST)


class GridPuzzleClockIntegrationTests(unittest.TestCase):
    def test_50_and_60_ms_frames_have_identical_simulation_traces_across_tick_wrap(self):
        traces = []
        for frame_ms in (50, 60):
            engine = load_engine()
            platform, canvas, modules = device_modules(engine)
            fake = FakeTime(modulus=1024)
            platform.read_game_touch = lambda: None
            schedule = {300: (("right", True),), 600: (("right", False), ("down", True)),
                        900: (("down", False),)}
            platform.read_button_events = lambda: (("back", True),) if fake.absolute_ms > 1200 else schedule.get(fake.absolute_ms, ())
            trace, original = [], engine.step
            def step(state, direction):
                original(state, direction)
                trace.append((state.elapsed_ms, state.player.cell, state.player.next_due_ms, state.bonus))
            with mock.patch.object(engine, "step", step), mock.patch.dict("sys.modules", modules), redirect_stdout(io.StringIO()):
                result = engine.run(engine.validate_level_pack(pack()), platform, canvas,
                    engine.choose_layout(480, 222), clock_factory=lambda: make_clock(
                        fake, frame_ms=frame_ms, update_ms=10, max_updates=10))
            self.assertEqual(result.state.elapsed_ms, 1200)
            self.assertEqual(result.state.player.cell, 51)
            traces.append(trace)
        self.assertEqual(traces[0], traces[1])


if __name__ == "__main__":
    unittest.main()
