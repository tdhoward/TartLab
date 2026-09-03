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
        self.pixels = {}
        self.blits = []

    def pixel(self, x, y, color=None):
        if color is None:
            return self.pixels.get((x, y), 0)
        self.pixels[(x, y)] = color

    def blit(self, source, x, y):
        self.blits.append((source, x, y))


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


class FakeArea:
    def __init__(self, values=None):
        values = values or {}
        self.x1 = values.get("x1", 0)
        self.y1 = values.get("y1", 0)
        self.x2 = values.get("x2", 0)
        self.y2 = values.get("y2", 0)


def fake_lvgl(initialized=True, fail_copy=False):
    module = types.ModuleType("lvgl")
    module.COLOR_FORMAT = types.SimpleNamespace(RGB565_SWAPPED=27)
    module.is_initialized = lambda: initialized
    module.draw_buffers = []

    class FakeDrawBuffer:
        def __init__(self):
            self.init_args = None
            self.reshape_args = []
            self.copy_args = []
            module.draw_buffers.append(self)

        def init(self, width, height, color_format, stride, data, data_size):
            self.width = width
            self.height = height
            self.color_format = color_format
            self.stride = stride
            self.data = data
            self.data_size = data_size
            self.init_args = (
                width, height, color_format, stride, data, data_size)
            return 1

        def reshape(self, color_format, width, height, stride):
            self.color_format = color_format
            self.width = width
            self.height = height
            self.stride = stride
            self.reshape_args.append((color_format, width, height, stride))
            return self

        def copy(self, target_area, source, source_area):
            self.copy_args.append((
                (target_area.x1, target_area.y1,
                 target_area.x2, target_area.y2),
                source,
                (source_area.x1, source_area.y1,
                 source_area.x2, source_area.y2)))
            if fail_copy and len(self.copy_args) == 1:
                raise RuntimeError("simulated LVGL copy failure")
            width = source_area.x2 - source_area.x1 + 1
            height = source_area.y2 - source_area.y1 + 1
            row_bytes = width * 2
            source_view = memoryview(source.data)
            target_view = memoryview(self.data)
            for row in range(height):
                source_start = (
                    (source_area.y1 + row) * source.stride +
                    source_area.x1 * 2)
                target_start = (
                    (target_area.y1 + row) * self.stride +
                    target_area.x1 * 2)
                target_view[target_start:target_start + row_bytes] = \
                    source_view[source_start:source_start + row_bytes]

    module.draw_buf_t = FakeDrawBuffer
    module.area_t = FakeArea
    return module


def load_modern_app(platform, lvgl=None):
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
    imports = {
            "tartlabutils": package,
            "tartlabutils.platform": platform_module,
            "framebuf": framebuf,
            "lvgl": lvgl,
    }
    with mock.patch.dict(sys.modules, imports):
        spec.loader.exec_module(module)
    return module


class ModernAppDrawingTests(unittest.TestCase):
    def test_canvas_uses_bounce_buffer_byte_capacity_for_narrow_area(self):
        surface = FakeSurface()
        platform = types.SimpleNamespace(
            enter_game_mode=lambda: surface)
        module = load_modern_app(platform)
        canvas = module.DirectCanvas(surface, transfer_rows=2)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((1, 0, 2, 3))

        self.assertEqual(surface.writes, [
            (bytes((2, 3, 4, 5, 10, 11, 12, 13,
                    18, 19, 20, 21)), 1, 0, 2, 3),
        ])
        canvas.close()
        self.assertEqual(len(surface.freed), 1)

    def test_canvas_uses_compiled_strided_copy_and_swapped_format(self):
        surface = FakeSurface()
        lvgl = fake_lvgl()
        module = load_modern_app(types.SimpleNamespace(), lvgl)
        canvas = module.DirectCanvas(surface, transfer_rows=2)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((1, 0, 2, 3))

        source, target = lvgl.draw_buffers
        self.assertEqual(source.init_args[:4], (4, 3, 27, 8))
        self.assertEqual(target.init_args[:4], (4, 2, 27, 8))
        self.assertEqual(target.reshape_args, [(27, 2, 3, 4)])
        self.assertEqual(len(target.copy_args), 1)
        self.assertEqual(surface.writes, [
            (bytes((2, 3, 4, 5, 10, 11, 12, 13,
                    18, 19, 20, 21)), 1, 0, 2, 3),
        ])

    def test_canvas_tiles_wide_area_and_clips_each_edge(self):
        surface = FakeSurface()
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        canvas = module.DirectCanvas(surface, transfer_rows=2)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((-1, -1, 5, 4))

        self.assertEqual(surface.writes, [
            (bytes(range(16)), 0, 0, 4, 2),
            (bytes(range(16, 24)), 0, 2, 4, 1),
        ])

    def test_canvas_skips_empty_and_outside_areas(self):
        surface = FakeSurface()
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        canvas = module.DirectCanvas(surface)

        for area in ((0, 0, 0, 1), (0, 0, 1, 0),
                     (-2, 0, 1, 1), (4, 0, 1, 1),
                     (0, -2, 1, 1), (0, 3, 1, 1)):
            with self.subTest(area=area):
                canvas.show(area)

        self.assertEqual(surface.writes, [])

    def test_canvas_falls_back_after_compiled_copy_error(self):
        surface = FakeSurface()
        lvgl = fake_lvgl(fail_copy=True)
        module = load_modern_app(types.SimpleNamespace(), lvgl)
        canvas = module.DirectCanvas(surface)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((1, 1, 2, 1))

        self.assertEqual(
            surface.writes, [(bytes((10, 11, 12, 13)), 1, 1, 2, 1)])
        self.assertIsNone(canvas._source_draw_buffer)

    def test_canvas_preserves_non_symmetric_rgb565_bytes(self):
        surface = FakeSurface(width=3, height=1)
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        canvas = module.DirectCanvas(surface)
        canvas.buffer[:] = bytes((0xF8, 0x00, 0x07, 0xE0, 0x00, 0x1F))

        canvas.show()

        self.assertEqual(
            surface.writes[0][0],
            bytes((0xF8, 0x00, 0x07, 0xE0, 0x00, 0x1F)))

    def test_canvas_packs_one_column_in_one_transfer(self):
        surface = FakeSurface()
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        canvas = module.DirectCanvas(surface, transfer_rows=1)
        canvas.buffer[:] = bytes(range(len(canvas.buffer)))

        canvas.show((2, 0, 1, 3))

        self.assertEqual(
            surface.writes,
            [(bytes((4, 5, 12, 13, 20, 21)), 2, 0, 1, 3)])

    def test_canvas_can_close_once_after_surface_write_error(self):
        surface = FakeSurface()
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        canvas = module.DirectCanvas(surface)
        surface.write = mock.Mock(side_effect=RuntimeError("write failed"))

        with self.assertRaisesRegex(RuntimeError, "write failed"):
            canvas.show((0, 0, 1, 1))
        canvas.close()
        canvas.close()

        self.assertEqual(surface.freed, [canvas._transfer])
        with self.assertRaisesRegex(RuntimeError, "canvas is closed"):
            canvas.show()

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

    def test_direct_canvas_draws_prepared_sprite_without_copying_it(self):
        surface = FakeSurface(width=4, height=3)
        module = load_modern_app(types.SimpleNamespace())
        canvas = module.DirectCanvas(surface)
        source = FakeFrameBuffer(bytearray(8), 2, 2, 1)

        sprite = canvas.prepare_sprite(source, 2, 2)
        canvas.draw_sprite(sprite, 1, 1)

        self.assertIs(sprite.framebuffer, source)
        self.assertEqual(canvas.blits, [(source, 1, 1)])

    def test_portrait_canvas_rotates_prepared_sprite_only_once(self):
        surface = FakeSurface(width=4, height=3)
        module = load_modern_app(types.SimpleNamespace())
        canvas = module.PortraitCanvas(surface)
        source = FakeFrameBuffer(bytearray(12), 2, 3, 1)
        for y, row in enumerate(((1, 2), (3, 4), (5, 6))):
            for x, color in enumerate(row):
                source.pixel(x, y, color)

        sprite = canvas.prepare_sprite(source, 2, 3)
        canvas.draw_sprite(sprite, 1, 0)

        self.assertEqual(
            (sprite.framebuffer.width, sprite.framebuffer.height), (3, 2))
        self.assertEqual(
            [[sprite.framebuffer.pixel(x, y) for x in range(3)]
             for y in range(2)],
            [[2, 4, 6], [1, 3, 5]])
        self.assertEqual(
            canvas._canvas.blits, [(sprite.framebuffer, 0, 0)])

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
