import importlib.util
import ast
from array import array
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def trunc_division(numerator, denominator):
    quotient = abs(numerator) // abs(denominator)
    if (numerator < 0) != (denominator < 0):
        return -quotient
    return quotient


class FakeFrameBuffer:
    def __init__(self, buffer, width, height, format):
        self.buffer = buffer
        self.width = width
        self.height = height
        self._framebuf_width = width
        self._framebuf_height = height
        self.format = format
        self.pixels = {}
        self.blits = []

    def pixel(self, x, y, color=None):
        if color is None:
            if (self.format == 1 and 0 <= x < self._framebuf_width and
                    0 <= y < self._framebuf_height):
                offset = (y * self._framebuf_width + x) * 2
                return self.buffer[offset] | self.buffer[offset + 1] << 8
            if (x, y) in self.pixels:
                return self.pixels[(x, y)]
            return 0
        if not (0 <= x < self._framebuf_width and
                0 <= y < self._framebuf_height):
            return
        self.pixels[(x, y)] = color
        if self.format == 1:
            offset = (y * self._framebuf_width + x) * 2
            self.buffer[offset] = color & 0xFF
            self.buffer[offset + 1] = (color >> 8) & 0xFF

    def fill(self, color):
        for y in range(self._framebuf_height):
            for x in range(self._framebuf_width):
                FakeFrameBuffer.pixel(self, x, y, color)

    def fill_rect(self, x, y, width, height, color):
        for target_y in range(y, y + height):
            for target_x in range(x, x + width):
                FakeFrameBuffer.pixel(self, target_x, target_y, color)

    def hline(self, x, y, width, color):
        FakeFrameBuffer.fill_rect(self, x, y, width, 1, color)

    def vline(self, x, y, height, color):
        FakeFrameBuffer.fill_rect(self, x, y, 1, height, color)

    def rect(self, x, y, width, height, color, fill=False):
        if fill:
            return FakeFrameBuffer.fill_rect(
                self, x, y, width, height, color)
        FakeFrameBuffer.hline(self, x, y, width, color)
        FakeFrameBuffer.hline(self, x, y + height - 1, width, color)
        FakeFrameBuffer.vline(self, x, y, height, color)
        FakeFrameBuffer.vline(self, x + width - 1, y, height, color)

    def line(self, x1, y1, x2, y2, color):
        dx = abs(x2 - x1)
        step_x = 1 if x1 < x2 else -1
        dy = -abs(y2 - y1)
        step_y = 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            FakeFrameBuffer.pixel(self, x1, y1, color)
            if x1 == x2 and y1 == y2:
                break
            twice_error = 2 * error
            if twice_error >= dy:
                error += dy
                x1 += step_x
            if twice_error <= dx:
                error += dx
                y1 += step_y

    @staticmethod
    def _ellipse_quadrants(x, y):
        quadrants = 0
        if x >= 0 and y <= 0:
            quadrants |= 0x1
        if x <= 0 and y <= 0:
            quadrants |= 0x2
        if x <= 0 and y >= 0:
            quadrants |= 0x4
        if x >= 0 and y >= 0:
            quadrants |= 0x8
        return quadrants

    def ellipse(self, x, y, x_radius, y_radius, color,
                fill=False, mask=0xF):
        if x_radius < 1 or y_radius < 1:
            return
        x_squared = x_radius * x_radius
        y_squared = y_radius * y_radius
        limit = x_squared * y_squared
        for offset_y in range(-y_radius, y_radius + 1):
            for offset_x in range(-x_radius, x_radius + 1):
                distance = (offset_x * offset_x * y_squared +
                            offset_y * offset_y * x_squared)
                if distance > limit:
                    continue
                if not fill:
                    inner_x = max(0, x_radius - 1)
                    inner_y = max(0, y_radius - 1)
                    if inner_x and inner_y:
                        inner_limit = inner_x * inner_x * inner_y * inner_y
                        inner_distance = (
                            offset_x * offset_x * inner_y * inner_y +
                            offset_y * offset_y * inner_x * inner_x)
                        if inner_distance < inner_limit:
                            continue
                if mask & self._ellipse_quadrants(offset_x, offset_y):
                    FakeFrameBuffer.pixel(
                        self, x + offset_x, y + offset_y, color)

    def poly(self, x, y, coordinates, color, fill=False):
        length = len(coordinates) & ~1
        if not length:
            return
        if fill:
            y_values = [coordinates[index]
                        for index in range(1, length, 2)]
            for row in range(min(y_values), max(y_values) + 1):
                nodes = []
                point_x_1 = coordinates[0]
                point_y_1 = coordinates[1]
                index = length - 1
                while index >= 0:
                    point_y_2 = coordinates[index]
                    point_x_2 = coordinates[index - 1]
                    index -= 2
                    if (point_y_1 != point_y_2 and
                            ((point_y_1 > row and point_y_2 <= row) or
                             (point_y_1 <= row and point_y_2 > row))):
                        crossing = trunc_division(
                            32 * (point_x_2 - point_x_1) *
                            (row - point_y_1),
                            point_y_2 - point_y_1)
                        nodes.append(trunc_division(
                            32 * point_x_1 + crossing + 16, 32))
                    elif row == max(point_y_1, point_y_2):
                        if point_y_1 < point_y_2:
                            FakeFrameBuffer.pixel(
                                self, x + point_x_2, y + point_y_2,
                                color)
                        elif point_y_2 < point_y_1:
                            FakeFrameBuffer.pixel(
                                self, x + point_x_1, y + point_y_1,
                                color)
                        else:
                            FakeFrameBuffer.line(
                                self,
                                x + point_x_1, y + point_y_1,
                                x + point_x_2, y + point_y_2, color)
                    point_x_1 = point_x_2
                    point_y_1 = point_y_2
                nodes.sort()
                for index in range(0, len(nodes), 2):
                    FakeFrameBuffer.hline(
                        self, x + nodes[index], y + row,
                        nodes[index + 1] - nodes[index] + 1, color)
            return

        point_x_1 = coordinates[0]
        point_y_1 = coordinates[1]
        index = length - 1
        while index >= 0:
            point_y_2 = coordinates[index]
            point_x_2 = coordinates[index - 1]
            index -= 2
            FakeFrameBuffer.line(
                self, x + point_x_1, y + point_y_1,
                x + point_x_2, y + point_y_2, color)
            point_x_1 = point_x_2
            point_y_1 = point_y_2

    def scroll(self, x_step, y_step):
        original = [
            [FakeFrameBuffer.pixel(self, x, y)
             for x in range(self._framebuf_width)]
            for y in range(self._framebuf_height)
        ]
        for target_y in range(self._framebuf_height):
            source_y = target_y - y_step
            if not 0 <= source_y < self._framebuf_height:
                continue
            for target_x in range(self._framebuf_width):
                source_x = target_x - x_step
                if 0 <= source_x < self._framebuf_width:
                    FakeFrameBuffer.pixel(
                        self, target_x, target_y,
                        original[source_y][source_x])

    def text(self, value, x, y, color):
        # A small deterministic test glyph. Both optimized and reference paths
        # consume the same pixels; the production device supplies the real font.
        for index, unused_character in enumerate(value):
            glyph_x = x + index * 8
            for offset_x, offset_y in ((0, 0), (1, 2), (6, 4), (7, 7)):
                FakeFrameBuffer.pixel(
                    self, glyph_x + offset_x, y + offset_y, color)

    def blit(self, source, x, y, key=-1):
        self.blits.append((source, x, y))
        for source_y in range(source._framebuf_height):
            for source_x in range(source._framebuf_width):
                color = FakeFrameBuffer.pixel(source, source_x, source_y)
                if color != key:
                    FakeFrameBuffer.pixel(
                        self, x + source_x, y + source_y, color)


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


class FakeScrollSurface(FakeSurface):
    def __init__(self, width=4, height=3, accelerate=True):
        super().__init__(width, height)
        self.accelerate = accelerate
        self.scrolls = []
        self.resets = 0

    def present_scroll(self, area, dx, dy, rotation=0):
        self.scrolls.append((area, dx, dy, rotation))
        return self.accelerate

    def reset_scroll(self):
        self.resets += 1


class FakeArea:
    def __init__(self, values=None):
        values = values or {}
        self.x1 = values.get("x1", 0)
        self.y1 = values.get("y1", 0)
        self.x2 = values.get("x2", 0)
        self.y2 = values.get("y2", 0)


def fake_lvgl(initialized=True, fail_copy=False, fail_rotate=False):
    module = types.ModuleType("lvgl")
    module.COLOR_FORMAT = types.SimpleNamespace(
        RGB565=26, RGB565_SWAPPED=27)
    module.is_initialized = lambda: initialized
    module.draw_buffers = []
    module.rotate_calls = []

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

    def draw_sw_rotate(source, target, width, height, source_stride,
                       target_stride, rotation, color_format):
        module.rotate_calls.append((
            width, height, source_stride, target_stride,
            rotation, color_format))
        if fail_rotate:
            raise RuntimeError("simulated LVGL rotation failure")
        source_view = memoryview(source)
        target_view = memoryview(target)
        for source_y in range(height):
            for source_x in range(width):
                source_offset = source_y * source_stride + source_x * 2
                if rotation == 1:
                    target_x = source_y
                    target_y = width - 1 - source_x
                elif rotation == 2:
                    target_x = width - 1 - source_x
                    target_y = height - 1 - source_y
                elif rotation == 3:
                    target_x = height - 1 - source_y
                    target_y = source_x
                else:
                    raise ValueError("rotation must be 1, 2, or 3")
                target_offset = target_y * target_stride + target_x * 2
                target_view[target_offset:target_offset + 2] = \
                    source_view[source_offset:source_offset + 2]

    module.draw_sw_rotate = draw_sw_rotate
    return module


def load_modern_app(platform, lvgl=None, viper_swap=None, viper_copy=None):
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    platform_module = types.ModuleType("tartlabutils.platform")
    platform_module.get_platform = lambda: platform
    framebuf = types.ModuleType("framebuf")
    framebuf.FrameBuffer = FakeFrameBuffer
    framebuf.MONO_HLSB = 0
    framebuf.RGB565 = 1
    emitters = None
    if viper_swap is not None or viper_copy is not None:
        emitters = types.ModuleType("tartlabutils._modern_emitters")
        if viper_swap is not None:
            emitters.swap565 = viper_swap
        if viper_copy is not None:
            emitters.copy_rgb565_rows = viper_copy
    path = ROOT / "src/lib/tartlabutils/modern_app.py"
    spec = importlib.util.spec_from_file_location(
        "tartlabutils.modern_app", path)
    module = importlib.util.module_from_spec(spec)
    imports = {
            "tartlabutils": package,
            "tartlabutils.platform": platform_module,
            "framebuf": framebuf,
            "lvgl": lvgl,
            "tartlabutils._modern_emitters": emitters,
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

        failed_surface = FakeSurface(width=2, height=1)
        failed_surface.write = mock.Mock(
            side_effect=RuntimeError("write failed"))
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            module.fill_surface(failed_surface, 0xF800)
        self.assertEqual(len(failed_surface.freed), 1)

    def test_swap565_buffer_uses_validated_viper_helper_when_available(self):
        calls = []

        def viper_swap(buffer, size):
            calls.append((buffer, size))
            for offset in range(0, size, 2):
                buffer[offset], buffer[offset + 1] = (
                    buffer[offset + 1], buffer[offset])

        module = load_modern_app(
            types.SimpleNamespace(), viper_swap=viper_swap)
        pixels = bytearray((0x00, 0xF8, 0xE0, 0x07))

        self.assertIs(module.swap565_buffer(pixels), pixels)
        self.assertEqual(pixels, bytearray((0xF8, 0x00, 0x07, 0xE0)))
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0][0], memoryview)
        self.assertEqual(calls[0][1], 4)

        with self.assertRaises(ValueError):
            module.swap565_buffer(bytearray(3))
        with self.assertRaises(TypeError):
            module.swap565_buffer(bytes(4))
        self.assertEqual(len(calls), 1)

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

    def test_portrait_canvas_is_rotation_compatibility_layer(self):
        surface = FakeSurface(width=4, height=3)
        module = load_modern_app(types.SimpleNamespace())
        canvas = module.PortraitCanvas(surface, transfer_rows=2)

        canvas.fill_rect(0, 1, 2, 3, 9)
        canvas.pixel(2, 3, 7)
        canvas.show((0, 1, 2, 3))

        self.assertIsInstance(canvas, module.DirectCanvas)
        self.assertIs(canvas._canvas, canvas)
        self.assertEqual(canvas.rotation, 90)
        self.assertEqual((canvas.width, canvas.height), (3, 4))
        self.assertEqual(FakeFrameBuffer.pixel(canvas, 3, 0), 7)
        self.assertEqual(surface.writes[0][1:], (1, 1, 3, 2))

    def test_direct_canvas_normalizes_rotation_and_reports_logical_size(self):
        module = load_modern_app(types.SimpleNamespace())
        for value, degrees in ((0, 0), (1, 90), (2, 180), (3, 270),
                               (90, 90), (180, 180), (270, 270)):
            with self.subTest(rotation=value):
                canvas = module.DirectCanvas(
                    FakeSurface(width=5, height=3), rotation=value)
                self.assertEqual(canvas.rotation, degrees)
                expected = (3, 5) if degrees in (90, 270) else (5, 3)
                self.assertEqual((canvas.width, canvas.height), expected)

        for value in (-90, 4, 360, "90", None):
            with self.subTest(rotation=value):
                with self.assertRaisesRegex(ValueError, "rotation must be"):
                    module.DirectCanvas(FakeSurface(), rotation=value)

    def test_direct_canvas_maps_pixels_and_dirty_regions_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        point_maps = {
            0: lambda x, y: (x, y),
            90: lambda x, y: (y, 2 - x),
            180: lambda x, y: (4 - x, 2 - y),
            270: lambda x, y: (4 - y, x),
        }
        area_maps = {
            0: lambda x, y, w, h: (x, y, w, h),
            90: lambda x, y, w, h: (y, 3 - x - w, h, w),
            180: lambda x, y, w, h: (5 - x - w, 3 - y - h, w, h),
            270: lambda x, y, w, h: (5 - y - h, x, h, w),
        }
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                surface = FakeSurface(width=5, height=3)
                canvas = module.DirectCanvas(surface, rotation=rotation)
                logical_width, logical_height = canvas.width, canvas.height
                x, y = logical_width - 1, logical_height - 1
                canvas.pixel(x, y, 0x1234)
                physical = point_maps[rotation](x, y)
                self.assertEqual(
                    FakeFrameBuffer.pixel(canvas, *physical), 0x1234)
                self.assertEqual(canvas.pixel(x, y), 0x1234)

                area = (1, 1, logical_width, logical_height)
                clipped = (1, 1, logical_width - 1, logical_height - 1)
                canvas.show(area)
                self.assertEqual(
                    surface.writes[0][1:], area_maps[rotation](*clipped))

    def test_direct_canvas_primitives_clip_in_logical_space_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                canvas = module.DirectCanvas(
                    FakeSurface(width=9, height=7), rotation=rotation)
                data = bytearray(canvas.width * canvas.height * 2)
                reference = FakeFrameBuffer(
                    data, canvas.width, canvas.height, 1)
                operations = (
                    ("fill_rect", (-2, 1, 5, 4, 1)),
                    ("rect", (1, -1, 6, 5, 2)),
                    ("hline", (-1, canvas.height - 2, 6, 3)),
                    ("vline", (canvas.width - 2, -2, 6, 4)),
                    ("line", (-2, 0, canvas.width, canvas.height - 1, 5)),
                )
                for name, arguments in operations:
                    getattr(canvas, name)(*arguments)
                    getattr(reference, name)(*arguments)
                for y in range(canvas.height):
                    for x in range(canvas.width):
                        self.assertEqual(
                            canvas.pixel(x, y), reference.pixel(x, y),
                            (rotation, x, y))

    def test_direct_canvas_maps_ellipses_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        operations = (
            (4, 4, 3, 2, 1, False, 0xF),
            (1, 2, 3, 2, 2, True, 0x5),
            (7, 5, 2, 3, 3, False, 0xA),
        )
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                canvas = module.DirectCanvas(
                    FakeSurface(width=11, height=9), rotation=rotation)
                reference = FakeFrameBuffer(
                    bytearray(canvas.width * canvas.height * 2),
                    canvas.width, canvas.height, 1)
                for arguments in operations:
                    canvas.ellipse(*arguments)
                    reference.ellipse(*arguments)
                for y in range(canvas.height):
                    for x in range(canvas.width):
                        self.assertEqual(
                            canvas.pixel(x, y), reference.pixel(x, y),
                            (rotation, x, y))

    def test_direct_canvas_maps_polygons_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        coordinates = array("h", (0, 0, 5, 1, 3, 5, -1, 3))
        clipped = array("h", (0, 0, 6, -2, 8, 3, 3, 6, -2, 3))
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                canvas = module.DirectCanvas(
                    FakeSurface(width=11, height=9), rotation=rotation)
                reference = FakeFrameBuffer(
                    bytearray(canvas.width * canvas.height * 2),
                    canvas.width, canvas.height, 1)
                for fill, color in ((False, 4), (True, 5)):
                    canvas.poly(2, 1, coordinates, color, fill)
                    reference.poly(2, 1, coordinates, color, fill)
                canvas.poly(-2, -1, clipped, 6, True)
                reference.poly(-2, -1, clipped, 6, True)
                for y in range(canvas.height):
                    for x in range(canvas.width):
                        self.assertEqual(
                            canvas.pixel(x, y), reference.pixel(x, y),
                            (rotation, x, y))

    def test_direct_canvas_scrolls_in_logical_space_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        for rotation in (0, 90, 180, 270):
            for x_step, y_step in ((2, 0), (-2, 0), (0, 1), (0, -1),
                                   (2, -1), (-1, 2)):
                with self.subTest(
                        rotation=rotation, x_step=x_step, y_step=y_step):
                    surface = FakeSurface(width=7, height=5)
                    canvas = module.DirectCanvas(surface, rotation=rotation)
                    reference = FakeFrameBuffer(
                        bytearray(canvas.width * canvas.height * 2),
                        canvas.width, canvas.height, 1)
                    vectors = (
                        (x_step, y_step),
                        (canvas.width, 0),
                        (0, -canvas.height),
                    )
                    for actual_x_step, actual_y_step in vectors:
                        for y in range(canvas.height):
                            for x in range(canvas.width):
                                color = y * canvas.width + x + 1
                                canvas.pixel(x, y, color)
                                reference.pixel(x, y, color)

                        canvas.scroll(actual_x_step, actual_y_step)
                        reference.scroll(actual_x_step, actual_y_step)

                        self.assertEqual(surface.writes, [])
                        for y in range(canvas.height):
                            for x in range(canvas.width):
                                self.assertEqual(
                                    canvas.pixel(x, y),
                                    reference.pixel(x, y),
                                    (rotation, actual_x_step, actual_y_step,
                                     x, y))

    def test_scroll_region_matches_portable_reference_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace())
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                surface = FakeScrollSurface(width=7, height=5,
                                            accelerate=False)
                canvas = module.DirectCanvas(surface, rotation=rotation)
                original = []
                for y in range(canvas.height):
                    row = []
                    for x in range(canvas.width):
                        value = 1 + y * canvas.width + x
                        canvas.pixel(x, y, value)
                        row.append(value)
                    original.append(row)
                area = (1, 1, canvas.width - 2, canvas.height - 2)
                dx, dy, fill = 1, -1, 0x7ACE
                expected = [row[:] for row in original]
                ax, ay, width, height = area
                for target_y in range(ay, ay + height):
                    for target_x in range(ax, ax + width):
                        source_x = target_x - dx
                        source_y = target_y - dy
                        if (ax <= source_x < ax + width and
                                ay <= source_y < ay + height):
                            expected[target_y][target_x] = \
                                original[source_y][source_x]
                        else:
                            expected[target_y][target_x] = fill

                canvas.scroll_region(area, dx=dx, dy=dy, fill=fill)

                for y in range(canvas.height):
                    for x in range(canvas.width):
                        self.assertEqual(
                            canvas.pixel(x, y), expected[y][x],
                            (rotation, x, y))
                self.assertEqual(surface.scrolls, [])
                self.assertEqual(surface.writes[-1][1:], canvas._area(*area))

    def test_partial_region_scroll_uses_viper_copy_when_available(self):
        calls = []

        def viper_copy(buffer, source_start, target_start, row_bytes,
                       row_count, stride, reverse_rows):
            calls.append((
                source_start, target_start, row_bytes,
                row_count, stride, reverse_rows))
            view = memoryview(buffer)
            rows = range(row_count - 1, -1, -1) if reverse_rows else \
                range(row_count)
            for row in rows:
                source = source_start + row * stride
                target = target_start + row * stride
                data = bytes(view[source:source + row_bytes])
                view[target:target + row_bytes] = data

        module = load_modern_app(
            types.SimpleNamespace(), viper_copy=viper_copy)
        surface = FakeScrollSurface(width=8, height=6, accelerate=False)
        canvas = module.DirectCanvas(surface)
        for y in range(canvas.height):
            for x in range(canvas.width):
                canvas.pixel(x, y, y * canvas.width + x + 1)

        canvas.scroll_region((1, 1, 6, 4), dx=1, dy=1, fill=0xCAFE)

        self.assertEqual(calls, [(18, 36, 10, 3, 16, 1)])
        for y in range(2, 5):
            for x in range(2, 7):
                self.assertEqual(
                    canvas.pixel(x, y), (y - 1) * canvas.width + x)

    def test_scroll_region_accelerates_only_an_exposed_band(self):
        module = load_modern_app(types.SimpleNamespace())
        surface = FakeScrollSurface(width=8, height=6)
        canvas = module.DirectCanvas(surface)
        canvas.fill(0x1234)

        canvas.scroll_region((0, 1, 8, 4), dy=-1, fill=0xBEEF)

        self.assertEqual(surface.scrolls, [((0, 1, 8, 4), 0, -1, 0)])
        self.assertEqual([write[1:] for write in surface.writes], [
            (0, 4, 8, 1),
        ])
        for x in range(8):
            self.assertEqual(canvas.pixel(x, 4), 0xBEEF)

    def test_scroll_region_composes_prepared_exposed_band_before_one_show(self):
        module = load_modern_app(types.SimpleNamespace())
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                surface = FakeScrollSurface(width=7, height=5)
                canvas = module.DirectCanvas(surface, rotation=rotation)
                width = canvas.width
                band_data = bytearray(width * 2)
                band = FakeFrameBuffer(band_data, width, 1, 1)
                for x in range(width):
                    band.pixel(x, 0, 0x5000 + x)
                prepared = canvas.prepare_sprite(band, width, 1)

                canvas.fill(0x1234)
                canvas.scroll_region(
                    (0, 1, width, canvas.height - 2),
                    dy=1, fill=0xBEEF, exposed=prepared)

                for x in range(width):
                    self.assertEqual(canvas.pixel(x, 1), 0x5000 + x)
                self.assertEqual(len(surface.scrolls), 1)
                self.assertEqual(len(surface.writes), 1)
                self.assertEqual(
                    surface.writes[0][1:], canvas._area(0, 1, width, 1))

    def test_scroll_region_validates_exposed_sprite_before_moving_ram(self):
        module = load_modern_app(types.SimpleNamespace())
        surface = FakeScrollSurface(width=8, height=6)
        canvas = module.DirectCanvas(surface)
        canvas.fill(0x1234)
        original = bytes(canvas.buffer)
        wrong_size = canvas.prepare_sprite(
            FakeFrameBuffer(bytearray(4), 2, 1, 1), 2, 1)

        with self.assertRaisesRegex(ValueError, "dimensions"):
            canvas.scroll_region(
                (0, 1, 8, 4), dy=1, exposed=wrong_size)
        with self.assertRaisesRegex(TypeError, "prepare_sprite"):
            canvas.scroll_region(
                (0, 1, 8, 4), dy=1, exposed=object())

        self.assertEqual(bytes(canvas.buffer), original)
        self.assertEqual(surface.scrolls, [])
        self.assertEqual(surface.writes, [])

    def test_scroll_region_falls_back_for_overlong_and_diagonal_moves(self):
        module = load_modern_app(types.SimpleNamespace())
        surface = FakeScrollSurface(width=8, height=6)
        canvas = module.DirectCanvas(surface)

        canvas.scroll_region((1, 1, 5, 3), dx=5, fill=0x0102)
        canvas.scroll_region((1, 1, 5, 3), dx=1, dy=1, fill=0x0304)

        self.assertEqual(surface.scrolls, [])
        self.assertEqual([write[1:] for write in surface.writes], [
            (1, 1, 5, 3),
            (1, 1, 5, 3),
        ])

    def test_canvas_close_restores_surface_scroll_before_freeing(self):
        module = load_modern_app(types.SimpleNamespace())
        surface = FakeScrollSurface()
        canvas = module.DirectCanvas(surface)

        canvas.close()
        canvas.close()

        self.assertEqual(surface.resets, 1)
        self.assertEqual(surface.freed, [canvas._transfer])

    def test_scroll_command_failure_flushes_software_result_and_reraises(self):
        module = load_modern_app(types.SimpleNamespace())
        surface = FakeScrollSurface(width=8, height=6)
        canvas = module.DirectCanvas(surface)

        def fail(*unused):
            raise RuntimeError("synthetic scroll failure")

        surface.present_scroll = fail
        with self.assertRaisesRegex(RuntimeError, "synthetic scroll failure"):
            canvas.scroll_region((0, 0, 8, 6), dx=1, fill=0x1234)

        self.assertEqual([write[1:] for write in surface.writes], [
            (0, 0, 8, 6),
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

    def test_portrait_canvas_uses_compiled_rotation_for_tight_sprite(self):
        surface = FakeSurface(width=4, height=3)
        lvgl = fake_lvgl()
        module = load_modern_app(types.SimpleNamespace(), lvgl)
        canvas = module.PortraitCanvas(surface)
        source = FakeFrameBuffer(bytearray(12), 2, 3, 1)
        for y, row in enumerate(((1, 2), (3, 4), (5, 6))):
            for x, color in enumerate(row):
                source.pixel(x, y, color)

        sprite = canvas.prepare_sprite(source, 2, 3)

        self.assertEqual(lvgl.rotate_calls, [(2, 3, 4, 6, 1, 26)])
        self.assertEqual(
            [[sprite.framebuffer.pixel(x, y) for x in range(3)]
             for y in range(2)],
            [[2, 4, 6], [1, 3, 5]])

    def test_direct_canvas_prepares_sprites_at_every_rotation(self):
        module = load_modern_app(types.SimpleNamespace(), fake_lvgl())
        expected = {
            0: [[1, 2], [3, 4], [5, 6]],
            90: [[2, 4, 6], [1, 3, 5]],
            180: [[6, 5], [4, 3], [2, 1]],
            270: [[5, 3, 1], [6, 4, 2]],
        }
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                canvas = module.DirectCanvas(
                    FakeSurface(width=8, height=7), rotation=rotation)
                source = FakeFrameBuffer(bytearray(12), 2, 3, 1)
                for y, row in enumerate(((1, 2), (3, 4), (5, 6))):
                    for x, color in enumerate(row):
                        source.pixel(x, y, color)

                sprite = canvas.prepare_sprite(source, 2, 3)
                actual = [
                    [sprite.framebuffer.pixel(x, y)
                     for x in range(sprite.framebuffer._framebuf_width)]
                    for y in range(sprite.framebuffer._framebuf_height)
                ]
                self.assertEqual(actual, expected[rotation])
                canvas.draw_sprite(sprite, 1, 2)
                for source_y, row in enumerate(((1, 2), (3, 4), (5, 6))):
                    for source_x, color in enumerate(row):
                        self.assertEqual(
                            canvas.pixel(1 + source_x, 2 + source_y), color)

    def test_portrait_text_compiled_output_matches_reference_and_is_bounded(self):
        cases = (
            ("Ab", 2, 3, 0xFFFF, 0),
            ("Black", -5, 8, 0, 0xFFFF),
            ("clip-right", 17, 20, 0x1234, 0xABCD),
            ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
             -80, 0, 0x1357, 0x2468),
        )
        for value, x, y, color, background in cases:
            with self.subTest(value=value, x=x, y=y):
                lvgl = fake_lvgl()
                module = load_modern_app(types.SimpleNamespace(), lvgl)
                optimized = module.PortraitCanvas(
                    FakeSurface(width=40, height=24))
                reference = module.PortraitCanvas(
                    FakeSurface(width=40, height=24))
                reference._compiled_text = False
                optimized.fill(background)
                reference.fill(background)

                optimized.text(value, x, y, color)
                reference.text(value, x, y, color)

                self.assertEqual(
                    bytes(optimized._canvas.buffer),
                    bytes(reference._canvas.buffer))
                workspace = optimized._text_workspace
                self.assertLessEqual(
                    len(workspace.source_data) + len(workspace.rotated_data),
                    module._TEXT_CHUNK_CHARS * 8 * 8 * 4)
                self.assertTrue(lvgl.rotate_calls)

    def test_portrait_text_disables_compiled_path_after_rotation_error(self):
        surface = FakeSurface(width=40, height=24)
        module = load_modern_app(
            types.SimpleNamespace(), fake_lvgl(fail_rotate=True))
        canvas = module.PortraitCanvas(surface)
        reference = module.PortraitCanvas(FakeSurface(width=40, height=24))
        reference._compiled_text = False

        canvas.text("fallback", 1, 2, 0x4321)
        reference.text("fallback", 1, 2, 0x4321)

        self.assertFalse(canvas._compiled_text)
        self.assertIsNone(canvas._text_workspace)
        self.assertEqual(
            bytes(canvas._canvas.buffer), bytes(reference._canvas.buffer))

    def test_direct_canvas_compiled_text_matches_reference_at_every_rotation(self):
        for rotation in (90, 180, 270):
            with self.subTest(rotation=rotation):
                lvgl = fake_lvgl()
                module = load_modern_app(types.SimpleNamespace(), lvgl)
                optimized = module.DirectCanvas(
                    FakeSurface(width=40, height=24), rotation=rotation)
                reference = module.DirectCanvas(
                    FakeSurface(width=40, height=24), rotation=rotation)
                reference._compiled_text = False
                optimized.fill(0x2468)
                reference.fill(0x2468)

                optimized.text("rotate", -3, 5, 0x1357)
                reference.text("rotate", -3, 5, 0x1357)

                self.assertEqual(
                    bytes(optimized.buffer), bytes(reference.buffer))
                self.assertEqual(lvgl.rotate_calls[-1][-2], rotation // 90)

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

    def test_touch_grid_is_inverse_of_canvas_rotation(self):
        point_maps = {
            0: lambda x, y: (x, y),
            90: lambda x, y: (y, 2 - x),
            180: lambda x, y: (4 - x, 2 - y),
            270: lambda x, y: (4 - y, x),
        }
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                platform = types.SimpleNamespace(
                    width=5, height=3, input=object(),
                    read_game_touch=lambda: None,
                    keep_touch_awake=lambda: None,
                )
                module = load_modern_app(platform)
                canvas = module.DirectCanvas(
                    FakeSurface(width=5, height=3), rotation=rotation)
                grid = module.TouchGrid(
                    ("only",), 1, 1, rotation=rotation)
                logical = (canvas.width - 1, canvas.height - 1)
                physical = point_maps[rotation](*logical)
                self.assertEqual(grid._logical_point(physical), logical)
                self.assertEqual(
                    (grid.width, grid.height), (canvas.width, canvas.height))


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
        for name in (
                "snake.py", "calculator.py", "testris.py", "racer.py"):
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

    def test_racer_uses_one_dirty_region_compositor(self):
        tree = ast.parse(
            (ROOT / "src/files/help/racer.py").read_text(encoding="utf-8"))
        scroll_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and
            isinstance(node.func, ast.Attribute) and
            node.func.attr == "scroll_region"
        ]
        self.assertEqual(scroll_calls, [])

        classes = {
            node.name: node for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        self.assertIn("RoadRenderer", classes)
        self.assertIn("DirtyRegionAnimator", classes)
        render_calls = [
            node for node in ast.walk(classes["RoadRenderer"])
            if isinstance(node, ast.Call) and
            isinstance(node.func, ast.Attribute) and
            node.func.attr == "show"
        ]
        self.assertEqual(len(render_calls), 1)
        for name in ("Entity", "GameState"):
            self.assertFalse(any(
                isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == "show"
                for node in ast.walk(classes[name])))

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
