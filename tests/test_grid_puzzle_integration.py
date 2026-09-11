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
from tools.check_grid_puzzle_levels import check


ROOT = Path(__file__).resolve().parents[1]


def device_modules(g):
    """Adapters only: all game definitions, state, probe and drawing remain real."""
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
    package.__path__ = []
    app = types.ModuleType("tartlabutils.app")
    app.DirectCanvas = lambda *args, **kwargs: canvas
    app.game_surface = acquire
    boundary = types.ModuleType("tartlabutils.platform")
    boundary.get_platform = lambda: platform
    return platform, canvas, {"tartlabutils": package, "tartlabutils.app": app,
                              "tartlabutils.platform": boundary}


class GridPuzzleIntegrationTests(unittest.TestCase):
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
        for failure in ("json", "layout", "allocation", "drawing", "close"):
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
                if failure == "drawing":
                    self.assertTrue(canvas.closed)

    def test_probe_requires_release_and_accepts_all_direction_restart_and_pause_controls(self):
        g = load_engine()
        platform, canvas, modules = device_modules(g)
        layout = g.choose_layout(platform.width, platform.height)
        def touch(action):
            if action is None:
                return None
            x, y, _, _ = dict(layout.controls)[action]
            return x + 16, y + 16
        sequence = iter(touch(action) for action in (
            "east", "east", None, "east", "east", None, "west", None,
            "south", None, "north", None, "restart", "restart", None, "pause", None, "back"))
        platform.read_game_touch = lambda: next(sequence)
        observations = []
        def draw(canvas, state, layout, selected, action, debug):
            observations.append((selected, action, debug))
        with mock.patch.object(g, "draw_probe", draw), \
                mock.patch.object(g, "create_state", wraps=g.create_state) as create, \
                mock.patch("time.sleep_ms", create=True), redirect_stdout(io.StringIO()):
            g.run_probe(g.validate_level_pack(pack(room())), platform, canvas, layout)
        actions = [(cell, action) for cell, action, _ in observations if action]
        self.assertEqual(actions, [(1, "east"), (0, "west"), (16, "south"),
                                   (0, "north"), (0, "restart"), (0, "pause")])
        self.assertEqual(create.call_count, 2)
        self.assertTrue(observations[-1][2])

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

    def test_check_report_hashes_selected_sources_and_does_not_claim_replay(self):
        report = check()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["rooms"][0]["keys"], 1)
        self.assertEqual(len(report["engine_sha256"]), 64)
        self.assertEqual(len(report["levels_sha256"]), 64)
        self.assertIn("pending", report["solution_replay"])
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
            for profile in ("lvgl-modern", "legacy-mp123"):
                output = temporary / profile
                makedist.build_distribution(source, output, runtime_profile=profile,
                                            minify_python=True, build_web=False, epoch=0)
                expected = profile == "lvgl-modern"
                for name in ("grid_puzzle.py", "grid_puzzle_levels.json", "grid_puzzle_guide.html"):
                    target = output / "files/help" / name
                    self.assertEqual(target.exists(), expected)
                    if expected:
                        self.assertEqual(target.read_text(encoding="utf-8"),
                                         (ROOT / "src/files/help" / name).read_text(encoding="utf-8"))
                self.assertFalse(list((output / "lib").glob("*grid_puzzle*")))


if __name__ == "__main__":
    unittest.main()
