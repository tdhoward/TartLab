import importlib.util
import ast
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class FakeFrameBuffer:
    def __init__(self, buffer, width, height, format):
        self.buffer = buffer
        self.width = width
        self.height = height
        self.format = format


class FakeSurface:
    color_format = "RGB565_BE"

    def __init__(self, width=4, height=3):
        self.width = width
        self.height = height
        self.writes = []
        self.freed = []

    def allocate_buffer(self, width, height):
        return bytearray(width * height * 2)

    def free_buffer(self, buffer):
        self.freed.append(buffer)

    def write(self, buffer, x, y, width, height):
        self.writes.append((bytes(buffer), x, y, width, height))


def load_modern_app(platform):
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    platform_module = types.ModuleType("tartlabutils.platform")
    platform_module.get_platform = lambda: platform
    framebuf = types.ModuleType("framebuf")
    framebuf.FrameBuffer = FakeFrameBuffer
    framebuf.MONO_HLSB = 0
    framebuf.RGB565 = 1
    path = ROOT / "src/lib/tartlabutils/modern_app.py"
    spec = importlib.util.spec_from_file_location(
        "tartlabutils.modern_app", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {
            "tartlabutils": package,
            "tartlabutils.platform": platform_module,
            "framebuf": framebuf,
    }):
        spec.loader.exec_module(module)
    return module


class ModernAppDrawingTests(unittest.TestCase):
    def test_canvas_packs_dirty_rectangle_into_transfer_tiles(self):
        surface = FakeSurface()
        platform = types.SimpleNamespace(
            enter_game_mode=lambda: surface)
        module = load_modern_app(platform)
        canvas = module.DirectCanvas(surface, transfer_rows=2)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((1, 0, 2, 3))

        self.assertEqual(surface.writes, [
            (bytes((2, 3, 4, 5, 10, 11, 12, 13)), 1, 0, 2, 2),
            (bytes((18, 19, 20, 21)), 1, 2, 2, 1),
        ])
        canvas.close()
        self.assertEqual(len(surface.freed), 1)

    def test_rgb565_helpers_produce_big_endian_framebuffer_bytes(self):
        module = load_modern_app(types.SimpleNamespace())
        self.assertEqual(module.framebuffer_color(0xF800), 0x00F8)
        self.assertEqual(module.rgb565(255, 0, 0), 0x00F8)
        pixels = bytearray((0x00, 0xF8, 0xE0, 0x07))
        self.assertIs(module.swap565_buffer(pixels), pixels)
        self.assertEqual(pixels, bytearray((0xF8, 0x00, 0x07, 0xE0)))

        surface = FakeSurface(width=2, height=1)
        module.fill_surface(surface, 0xF800)
        self.assertEqual(surface.writes[0][0], b"\xF8\x00\xF8\x00")

    def test_touch_grid_uses_public_platform_poll_and_debounces(self):
        points = [(100, 201), (100, 201), None, (100, 201)]
        platform = types.SimpleNamespace(
            width=480,
            height=222,
            input=object(),
            read_game_touch=lambda: points.pop(0),
            keep_touch_awake=lambda: None,
        )
        module = load_modern_app(platform)
        keypad = module.TouchGrid(["left", "right"], 2, 1)

        self.assertEqual(keypad.read(), "left")
        self.assertIsNone(keypad.read())
        self.assertIsNone(keypad.read())
        self.assertEqual(keypad.read(), "left")

    def test_portrait_canvas_maps_primitives_and_dirty_regions(self):
        surface = FakeSurface(width=4, height=3)
        module = load_modern_app(types.SimpleNamespace())
        canvas = module.PortraitCanvas(surface, transfer_rows=2)
        calls = []
        canvas._canvas = types.SimpleNamespace(
            fill_rect=lambda *values: calls.append(("fill_rect", values)),
            pixel=lambda *values: calls.append(("pixel", values)),
            show=lambda area=None: calls.append(("show", area)),
            close=lambda: None,
        )

        canvas.fill_rect(0, 1, 2, 3, 9)
        canvas.pixel(2, 3, 7)
        canvas.show((0, 1, 2, 3))

        self.assertEqual((canvas.width, canvas.height), (3, 4))
        self.assertEqual(calls, [
            ("fill_rect", (1, 1, 3, 2, 9)),
            ("pixel", (3, 0, 7)),
            ("show", (1, 1, 3, 2)),
        ])

    def test_portrait_touch_grid_maps_landscape_points(self):
        points = [(100, 201), None, (400, 10)]
        platform = types.SimpleNamespace(
            width=480,
            height=222,
            input=object(),
            read_game_touch=lambda: points.pop(0),
            keep_touch_awake=lambda: None,
        )
        module = load_modern_app(platform)
        keypad = module.PortraitTouchGrid(
            ("top-left", "top-right", "bottom-left", "bottom-right"),
            2, 2)

        self.assertEqual(keypad.read(), "top-left")
        self.assertIsNone(keypad.read())
        self.assertEqual(keypad.read(), "bottom-right")


class ModernHelpSourceTests(unittest.TestCase):
    def test_modern_and_legacy_help_trees_have_the_same_files(self):
        modern = ROOT / "src/files/help"
        legacy = ROOT / "src/files/help-legacy"
        modern_files = {
            path.name for path in modern.iterdir() if path.is_file()}
        legacy_files = {
            path.name for path in legacy.iterdir() if path.is_file()}
        self.assertEqual(modern_files, legacy_files)

    def test_modern_examples_use_only_the_direct_display_approach(self):
        forbidden = {
            "hdwconfig", "displaybuf", "touch_keypad", "eventsys",
            "palettes", "graphics", "lvgl",
        }
        for path in sorted((ROOT / "src/files/help").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            imports = set()
            modules = set()
            attributes = set()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                    modules.add(node.module)
                elif isinstance(node, ast.Attribute):
                    attributes.add(node.attr)
            with self.subTest(path=path.name):
                self.assertNotIn("lvgl", source.lower())
                self.assertFalse(imports.intersection(forbidden))
                self.assertFalse({"lvgl", "enter_ui_mode"}.intersection(attributes))
                if path.name != "pybasics.py":
                    self.assertIn("tartlabutils.modern_app", modules)

    def test_portrait_examples_use_portrait_canvas_and_touch(self):
        for name in ("snake.py", "calculator.py", "testris.py"):
            tree = ast.parse(
                (ROOT / "src/files/help" / name).read_text(encoding="utf-8"))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and
                node.module == "tartlabutils.modern_app"
                for alias in node.names
            }
            with self.subTest(path=name):
                self.assertIn("PortraitCanvas", imports)
                self.assertIn("PortraitTouchGrid", imports)

    def test_modern_manifest_describes_direct_drawing_not_lvgl(self):
        manifest = (ROOT / "src/files/help/manifest.json").read_text()
        self.assertNotIn("LVGL", manifest.upper())

    def test_manifest_only_references_existing_modern_help_files(self):
        root = ROOT / "src/files/help"
        manifest = json.loads((root / "manifest.json").read_text())
        referenced = {
            entry["file"]
            for folder in manifest["folders"]
            for entry in folder["entries"]
        }
        self.assertTrue(referenced)
        self.assertFalse({name for name in referenced if not (root / name).is_file()})


if __name__ == "__main__":
    unittest.main()
