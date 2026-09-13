from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import makedist
from tests.grid_puzzle_support import DEFAULT_ENGINE, DEFAULT_LEVELS, load_engine, pack, room
from tests.test_grid_puzzle_rendering import RecordingCanvas
from tests.test_timing import FakeTime, make_clock
from tools.check_grid_puzzle_levels import check
from tests.image_support import IMAGE_MODULES, sprites


ROOT = Path(__file__).resolve().parents[1]


def device_modules(g):
    """Adapters only: all game rules, clock scheduling and drawing remain real."""
    canvas = RecordingCanvas()
    platform = types.SimpleNamespace(width=480, height=222,
        capabilities={"direct_rgb565": True, "touch": True}, buttons=None,
        ui_calls=0, acquisitions=0, touch_reads=0)
    layout = g.choose_layout(platform.width, platform.height)
    rect = dict(layout.controls)["back"]
    def touch():
        platform.touch_reads += 1
        return None if platform.touch_reads == 1 else (rect[0] + 16, rect[1] + 16)
    def acquire():
        platform.acquisitions += 1
        return object()
    def ui():
        platform.ui_calls += 1
    platform.read_game_touch = touch
    platform.read_button_events = lambda: ()
    platform.keep_touch_awake = lambda: None
    platform.enter_ui_mode = ui
    package = types.ModuleType("tartlabutils")
    package.__path__ = [str(ROOT / "src/lib/tartlabutils")]
    app = types.ModuleType("tartlabutils.app")
    app.DirectCanvas = lambda *args, **kwargs: canvas
    app.game_surface = acquire
    boundary = types.ModuleType("tartlabutils.platform")
    boundary.get_platform = lambda: platform
    timing = types.ModuleType("tartlabutils.timing")
    platform.fake_time = FakeTime()
    timing.FrameClock = lambda **kwargs: make_clock(platform.fake_time, **kwargs)
    sprite_module = types.ModuleType("tartlabutils.sprites")
    sprite_module.SpriteSheet = lambda path: sprites.SpriteSheet(
        str(ROOT / "src/files/assets/grid_puzzle.ts16") if path == "/files/assets/grid_puzzle.ts16" else path)
    return platform, canvas, {**IMAGE_MODULES, "tartlabutils": package, "tartlabutils.app": app,
                              "tartlabutils.sprites": sprite_module,
                              "tartlabutils.platform": boundary, "tartlabutils.timing": timing}


class GridPuzzleIntegrationTests(unittest.TestCase):
    def test_asset_loading_time_is_excluded_from_simulation_and_dropped_time(self):
        g = load_engine()
        platform, canvas, modules = device_modules(g)
        layout = g.choose_layout(platform.width, platform.height)
        x, y, unused_w, unused_h = dict(layout.controls)["back"]
        touches = iter((None, None, (x + 16, y + 16)))
        platform.read_game_touch = lambda: next(touches)
        original = g.PuzzleArt.prepare
        def prepare(art, definition, canvas=None):
            original(art, definition, canvas)
            platform.fake_time.absolute_ms += 1000
        output = io.StringIO()
        with mock.patch.dict(sys.modules, modules), mock.patch.object(g.PuzzleArt, "prepare", prepare), redirect_stdout(output):
            result = g.run(g.validate_level_pack(pack()), platform, canvas, layout)
        self.assertEqual(result.state.elapsed_ms, 50)
        self.assertIn("dropped_update_ms=0", output.getvalue())

    def test_hint_open_and_acknowledgement_require_fresh_direction_input(self):
        g = load_engine()
        platform, canvas, modules = device_modules(g)
        layout = g.choose_layout(platform.width, platform.height)
        sequence = iter((None, "east", "east", "east", None, "pause", "east", None, "east", "east", None, "back"))
        def touch():
            action = next(sequence)
            if action is None:
                return None
            x, y, unused_w, unused_h = dict(layout.controls)[action]
            return x + 16, y + 16
        platform.read_game_touch = touch
        definition = g.validate_level(room(messages=[{"loc_x": 1, "loc_y": 0, "text": "Stop and look"}]))
        observations = []
        def draw(canvas, session, layout, action, debug):
            observations.append((session.state.player.cell, session.state.paused, session.state.elapsed_ms))
        with mock.patch.dict(sys.modules, modules), mock.patch.object(g, "draw_game", draw), redirect_stdout(io.StringIO()):
            result = g.run({"levels": [definition]}, platform, canvas, layout)
        self.assertEqual([item[:2] for item in observations], [
            (0, False), (0, False), (1, True), (1, True), (1, True),
            (1, False), (1, False), (1, False), (1, False), (2, False), (2, False)])
        self.assertEqual(observations[2][2], observations[5][2])
        self.assertEqual(result.state.player.cell, 2)
        self.assertEqual(result.art.sprites, {})

    def test_main_acquires_once_and_releases_canvas_and_ui_on_return(self):
        g = load_engine()
        g.LEVEL_FILE = str(DEFAULT_LEVELS)
        platform, canvas, modules = device_modules(g)
        output = io.StringIO()
        with mock.patch.dict(sys.modules, modules), mock.patch("time.sleep_ms", create=True), redirect_stdout(output):
            g.main()
        self.assertEqual(platform.acquisitions, 1)
        self.assertTrue(canvas.closed)
        self.assertEqual(platform.ui_calls, 1)
        self.assertIn(str(DEFAULT_LEVELS), output.getvalue())

    def test_failures_before_and_after_acquisition_keep_resource_ownership_clear(self):
        for failure in ("json", "layout", "allocation", "art", "drawing", "close"):
            with self.subTest(failure=failure):
                g = load_engine()
                g.LEVEL_FILE = str(DEFAULT_LEVELS)
                platform, canvas, modules = device_modules(g)
                if failure == "json":
                    g.LEVEL_FILE = str(ROOT / "build/grid_puzzle/no_such_rooms.json")
                elif failure == "layout":
                    platform.width, platform.height = 170, 320
                elif failure == "allocation":
                    modules["tartlabutils.app"].DirectCanvas = mock.Mock(side_effect=MemoryError("canvas"))
                elif failure == "art":
                    g.ASSET_FILE = str(ROOT / "build/grid_puzzle/no_such_art.ts16")
                elif failure == "drawing":
                    canvas.show = mock.Mock(side_effect=RuntimeError("transfer failed"))
                elif failure == "close":
                    canvas.close = mock.Mock(side_effect=RuntimeError("close failed"))
                with mock.patch.dict(sys.modules, modules), mock.patch("time.sleep_ms", create=True), \
                        redirect_stdout(io.StringIO()), self.assertRaises((ValueError, MemoryError, RuntimeError)):
                    g.main()
                acquired = failure not in ("json", "layout")
                self.assertEqual(platform.acquisitions, int(acquired))
                self.assertEqual(platform.ui_calls, int(acquired))
                if failure in ("art", "drawing"):
                    self.assertTrue(canvas.closed)

    def test_play_loop_requires_release_after_start_restart_pause_and_resume(self):
        g = load_engine()
        platform, canvas, modules = device_modules(g)
        layout = g.choose_layout(platform.width, platform.height)
        def touch(action):
            if action is None:
                return None
            x, y, _, _ = dict(layout.controls)[action]
            return x + 16, y + 16
        sequence = iter(touch(action) for action in (
            "east", None, "east", "east", None, "east", "east", None, "restart",
            "east", None, "pause", None, "pause", "east", None, "south", "south", None, "back"))
        platform.read_game_touch = lambda: next(sequence)
        observations = []
        def draw(canvas, session, layout, action, debug):
            observations.append((session.state.player.cell, action, session.state.paused, session.state.elapsed_ms))
        with mock.patch.object(g, "draw_game", draw), mock.patch.dict(sys.modules, modules), \
                mock.patch.object(g, "create_state", wraps=g.create_state) as create, \
                mock.patch("time.sleep_ms", create=True), redirect_stdout(io.StringIO()):
            result = g.run(g.validate_level_pack(pack(room())), platform, canvas, layout)
        self.assertEqual([row[0] for row in observations[:7]], [0, 0, 0, 1, 1, 1, 2])
        self.assertEqual(observations[8][:3], (0, "restart", False))
        self.assertEqual([row[0] for row in observations[9:17]], [0] * 8)
        self.assertEqual(observations[11][2:], (True, 100))
        self.assertEqual(observations[12][2:], (True, 100))
        self.assertEqual(observations[13][2:], (False, 100))
        self.assertEqual(result.state.player.cell, 16)
        self.assertEqual(create.call_count, 2)

    def test_new_press_does_not_move_player_retroactively_during_stall(self):
        g = load_engine()
        platform, canvas, modules = device_modules(g)
        layout = g.choose_layout(platform.width, platform.height)
        actions = iter((None, "east", "east", "east", "back"))
        def touch():
            action = next(actions)
            if action is None:
                return None
            if platform.fake_time.absolute_ms == 50:
                platform.fake_time.advance(450)
            x, y, _, _ = dict(layout.controls)[action]
            return x + 16, y + 16
        platform.read_game_touch = touch
        # Back needs a fresh press, so use an independent named button edge.
        polls = []
        platform.read_button_events = lambda: [("back", True)] if len(polls) == 4 else ()
        def draw(canvas, session, layout, action, debug):
            polls.append((session.state.elapsed_ms, session.state.player.cell))
        output = io.StringIO()
        with mock.patch.object(g, "draw_game", draw), mock.patch.dict(sys.modules, modules), redirect_stdout(output):
            g.run(g.validate_level_pack(pack()), platform, canvas, layout)
        self.assertEqual(polls, [(0, 0), (100, 0), (100, 0), (150, 1)])
        self.assertIn("dropped_update_ms=400", output.getvalue())

    def test_renamed_source_runs_its_own_function_and_reloads_selected_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            custom = path / "my_rooms.json"
            custom.write_text(json.dumps(pack(room(name="Student room"))), encoding="utf-8")
            engine = path / "my_puzzle.py"
            original = DEFAULT_ENGINE.read_text(encoding="utf-8")
            source = original.replace('LEVEL_FILE = "/files/help/grid_puzzle_levels.json"',
                                      "LEVEL_FILE = " + repr(str(custom)))
            source = source.replace('return "(%s,%s) %s"', 'return "MY RULE (%s,%s) %s"')
            engine.write_text(source, encoding="utf-8")
            g = load_engine(engine)
            platform, canvas, modules = device_modules(g)
            namespace = {}  # IDE-style exec has no module __file__ or module cache.
            output = io.StringIO()
            with mock.patch.dict(sys.modules, modules), mock.patch("time.sleep_ms", create=True), redirect_stdout(output):
                exec(engine.read_text(encoding="utf-8"), namespace)
            self.assertIn("MY RULE", output.getvalue())
            self.assertIn("Student room", str(canvas.commands))
            custom.write_text(json.dumps(pack(room(name="Edited rooms"))), encoding="utf-8")
            engine.write_text(source.replace("MY RULE", "NEW RULE"), encoding="utf-8")
            platform.touch_reads = 0
            output = io.StringIO()
            with mock.patch.dict(sys.modules, modules), mock.patch("time.sleep_ms", create=True), redirect_stdout(output):
                exec(engine.read_text(encoding="utf-8"), namespace)
            self.assertIn("NEW RULE", output.getvalue())
            self.assertIn("Edited rooms", str(canvas.commands))
            self.assertNotIn("MY RULE", output.getvalue())
            engine.write_text(original, encoding="utf-8")
            self.assertEqual(json.loads(custom.read_text())["levels"][0]["name"], "Edited rooms")
            custom.write_bytes(DEFAULT_LEVELS.read_bytes())
            self.assertEqual(engine.read_text(encoding="utf-8"), original)

    def test_actual_selected_app_runner_triggers_import_autostart(self):
        with tempfile.TemporaryDirectory() as temporary:
            engine = Path(temporary) / "selected_grid_probe.py"
            engine.write_text(DEFAULT_ENGINE.read_text(encoding="utf-8").replace(
                'LEVEL_FILE = "/files/help/grid_puzzle_levels.json"',
                "LEVEL_FILE = " + repr(str(DEFAULT_LEVELS))), encoding="utf-8")
            g = load_engine(engine)
            platform, canvas, modules = device_modules(g)
            for name, attributes in {
                "bootstate": {"mark_boot_healthy": lambda mode: False},
                "miscutils": {"log": lambda message: None},
                "state": {"get_selected_app": lambda: engine.name},
            }.items():
                module = types.ModuleType("tartlabutils." + name)
                module.__dict__.update(attributes)
                modules[module.__name__] = module
            runner_path = ROOT / "src/lib/tartlabutils/app_runner.py"
            runner = types.ModuleType("tartlabutils.app_runner")
            runner.__package__ = "tartlabutils"
            with mock.patch.dict(sys.modules, modules), mock.patch("time.sleep_ms", create=True), \
                    mock.patch.object(sys, "path", [temporary] + sys.path), redirect_stdout(io.StringIO()):
                try:
                    exec(compile(runner_path.read_bytes(), str(runner_path), "exec"), runner.__dict__)
                    runner._arm_health_check = lambda: None
                    result = runner.launch_selected_app()
                    self.assertEqual(result.LEVEL_FILE, str(DEFAULT_LEVELS))
                    self.assertEqual(platform.acquisitions, 1)
                    self.assertTrue(canvas.closed)
                finally:
                    sys.modules.pop(engine.stem, None)

    def test_renamed_student_source_changes_actual_collection_rule(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "my_engine.py"
            path.write_text(DEFAULT_ENGINE.read_text(encoding="utf-8").replace(
                "state.score += DIAMOND_SCORE", "state.score += 37"), encoding="utf-8")
            g = load_engine(path)
            state = g.create_state(g.validate_level(room({(1, 0): "D."})))
            g.step(state, g.EAST)
            self.assertEqual(state.score, 37)

    def test_check_report_hashes_selected_sources_and_replays_bundled_room(self):
        report = check()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["rooms"][0]["keys"], 1)
        self.assertEqual(len(report["engine_sha256"]), 64)
        self.assertEqual(len(report["levels_sha256"]), 64)
        self.assertEqual(report["solution_replay"], "passed")
        self.assertEqual(report["replays"][0]["actual"],
                         {"status": "completed", "score": 100, "bonus": 498, "elapsed_ms": 2540})
        self.assertEqual(report["engine_sha256"], report["replays"][0]["engine_sha256"])
        report = check(levels_path=ROOT / "build/grid_puzzle/no_such_rooms.json")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["errors"])

    def test_production_distribution_keeps_editable_sources_modern_only(self):
        # Use the production builder, with a tiny already-built frontend fixture.
        # The separate npm production build verifies the real frontend bundle.
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            source = temporary / "src"
            for name in ("defaults", "recovery", "configs", "files/assets", "files/assets-legacy",
                         "files/user", "lib", "ide/www/dist"):
                (source / name).mkdir(parents=True, exist_ok=True)
            (source / "ide/www/dist/index.html").write_text("<html></html>", encoding="utf-8")
            for name in ("help", "help-legacy"):
                makedist.copy_tree(ROOT / "src/files" / name, source / "files" / name, False)
            (source / "files/assets/grid_puzzle.ts16").write_bytes(
                (ROOT / "src/files/assets/grid_puzzle.ts16").read_bytes())
            for profile in ("lvgl-modern", "legacy-mp123"):
                output = temporary / profile
                makedist.build_distribution(source, output, runtime_profile=profile,
                                            minify_python=True, build_web=False, epoch=0)
                expected = profile == "lvgl-modern"
                asset = output / "files/assets/grid_puzzle.ts16"
                self.assertEqual(asset.exists(), expected)
                if expected:
                    self.assertEqual(asset.read_bytes(), (ROOT / "src/files/assets/grid_puzzle.ts16").read_bytes())
                for name in ("grid_puzzle.py", "grid_puzzle_levels.json", "grid_puzzle_guide.html"):
                    target = output / "files/help" / name
                    self.assertEqual(target.exists(), expected)
                    if expected:
                        self.assertEqual(target.read_text(encoding="utf-8"),
                                         (ROOT / "src/files/help" / name).read_text(encoding="utf-8"))
                self.assertFalse(list((output / "lib").glob("*grid_puzzle*")))


if __name__ == "__main__":
    unittest.main()
