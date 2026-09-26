"""RGB rectangles, byte order, and ownership against the pinned copy ABI."""
import importlib.util
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch

from tests.test_phase5 import (load_modern_rendering, load_factory,
                              FakeModernBus, FakeModernPanel, FakeLVDisplay,
                              FakeModernLVGL, FakeTaskHandler)

ROOT = Path(__file__).resolve().parents[1]


class RGBTests(unittest.TestCase):
    def setUp(self):
        self.runtime = load_modern_rendering()
        spec = importlib.util.spec_from_file_location(
            'rgb_under_test', ROOT / 'src/lib/tartlabdrivers/display/rgb.py')
        self.rgb = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'tartlabutils.runtime': self.runtime}):
            spec.loader.exec_module(self.rgb)
        self.bus = FakeModernBus()
        self.panel = FakeModernPanel()
        self.display = FakeLVDisplay(self.bus)
        self.display.rotation = 0
        self.display.set_flush_cb = Mock()
        self.display.flush_is_last = lambda: True
        self.lv = FakeModernLVGL(self.display, self.bus)
        self.controller = self.rgb.RGBDisplayController(
            self.bus, self.panel, self.display, self.lv, FakeTaskHandler(),
            None, 8, 6, None, None, None, True)

    def test_partial_full_width_and_bottom_right_copy_every_pixel(self):
        surface = self.controller.acquire_game()
        framebuffer = bytearray(8 * 6 * 2)

        def native_copy(command, data, x1, y1, x2, y2, rotation, last):
            self.assertEqual(command, -1)
            self.assertEqual(rotation, 0)
            self.assertTrue(last)
            # Match the pinned native full-width and partial-width loops.
            stop = y2 + 1 if x1 == 0 and x2 == 7 else y2
            row_bytes = (x2 - x1 + 1) * 2
            for index, y in enumerate(range(y1, stop)):
                offset = (y * 8 + x1) * 2
                framebuffer[offset:offset + row_bytes] = data[index * row_bytes:(index + 1) * row_bytes]
            self.bus.complete()

        self.bus.tx_color = native_copy
        for x, y, width, height in ((0, 0, 8, 2), (2, 2, 3, 2), (7, 5, 1, 1)):
            data = bytes([0xF8, 0x00]) * (width * height)
            before = bytes(framebuffer)
            surface.write(data, x, y, width, height)
            self.assertEqual(data, bytes([0xF8, 0x00]) * (width * height))
            for yy in range(6):
                for xx in range(8):
                    offset = (yy * 8 + xx) * 2
                    expected = b'\xf8\x00' if x <= xx < x + width and y <= yy < y + height else before[offset:offset + 2]
                    self.assertEqual(framebuffer[offset:offset + 2], expected)
        self.assertEqual(self.panel.params, [])

    def test_ui_flush_uses_same_partial_endpoint_and_source_size(self):
        data = b'\x07\xe0' * 3
        color = Mock()
        color.__dereference__ = Mock(return_value=data)
        area = types.SimpleNamespace(x1=3, y1=5, x2=5, y2=5)
        self.display.begin_flush()
        self.controller._flush(self.display, area, color)
        color.__dereference__.assert_called_once_with(6)
        self.assertEqual(self.bus.transfers[-1], (-1, data, 3, 5, 5, 6, 0, True))
        self.assertFalse(self.controller.transfer_pending)
        self.assertGreater(self.display.flush_ready_calls, 0)

    def test_source_completion_is_required_before_handover(self):
        surface = self.controller.acquire_game()
        self.bus.auto_complete = False
        surface.write(b'\x00\x1f', 0, 0, 1, 1, wait=False)
        self.assertTrue(surface.busy)
        with self.assertRaises(self.runtime.DisplayOwnershipError):
            surface.write(b'\x00\x1f', 1, 1, 1, 1)
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            self.controller.acquire_ui(timeout_ms=0)
        self.assertEqual(self.controller.owner, self.runtime.GAME_OWNER)
        self.bus.complete()
        self.bus.auto_complete = True
        self.controller.acquire_ui()
        self.assertEqual(self.controller.owner, self.runtime.UI_OWNER)
        with self.assertRaises(self.runtime.DisplayOwnershipError):
            surface.write(b'\x00\x1f', 0, 0, 1, 1)

    def test_rejected_region_never_reaches_native_bus(self):
        surface = self.controller.acquire_game()
        for data, x, y, width, height in ((b'\0\0', 8, 0, 1, 1), (b'\0', 0, 0, 1, 1)):
            with self.assertRaises(ValueError):
                surface.write(data, x, y, width, height)
        self.assertEqual(self.bus.transfers, [])

    def test_factory_rgb_transport_and_panel_use_declarative_wiring(self):
        factory, package, adapter = load_factory(self.runtime)
        board = runpy.run_path(str(ROOT / 'boards/elecrow_dis08070h/runtime/elecrow_dis08070h_modern.py'))['BOARD_CONFIG']
        factory.validate_board_config(board)
        lcd = types.SimpleNamespace(RGBBus=Mock(return_value=self.bus))
        self.assertEqual(factory._transport(board, Mock(), lcd), (None, self.bus))
        options = lcd.RGBBus.call_args.kwargs
        pins = {p['type']: p['number'] for p in board['pins']}
        self.assertEqual(options['data15'], pins['DISPLAY_DATA_15'])
        self.assertEqual(options['pclk'], pins['DISPLAY_PCLK'])
        self.assertEqual(options['freq'], board['display']['rgb']['freq'])
        module = types.ModuleType('rgb_display')
        module.STATE_LOW, module.STATE_HIGH = 0, 1
        module.STATE_PWM = -1
        panel = Mock()
        module.RGBDisplay = Mock(return_value=panel)
        lv = types.SimpleNamespace(COLOR_FORMAT=types.SimpleNamespace(RGB565_SWAPPED=19),
                                   DISPLAY_ROTATION=types.SimpleNamespace(_0=0))
        with patch.dict(sys.modules, {'rgb_display': module}):
            factory._panel(board, self.bus, (b'1', b'2'), lv)
        options = module.RGBDisplay.call_args.kwargs
        self.assertIsNone(options['reset_pin'])
        self.assertEqual(options['color_space'], 19)
        self.assertTrue(options['rgb565_byte_swap'])
        # Native 16-bit RGB handles this by swapping pin lanes, not the buffer.
        self.assertEqual(options['backlight_on_state'], module.STATE_PWM)

    def test_touch_selects_responding_alternate_and_rejects_false_acks(self):
        factory, package, adapter = load_factory(self.runtime)
        board = runpy.run_path(str(ROOT / 'boards/elecrow_dis08070h/runtime/elecrow_dis08070h_modern.py'))['BOARD_CONFIG']
        bus, device, driver = Mock(), Mock(), Mock()
        i2c = types.SimpleNamespace(I2C=types.SimpleNamespace(Bus=Mock(return_value=bus), Device=device))
        gt = types.ModuleType('gt911')
        gt.GT911, gt.BITS = driver, 16
        lv = types.SimpleNamespace(DISPLAY_ROTATION=types.SimpleNamespace(_0=0))
        with patch.dict(sys.modules, {'i2c': i2c, 'gt911': gt}):
            bus.scan.return_value = [0x14, 0x18]
            factory._touch(board, lv)
            self.assertEqual(device.call_args.kwargs['dev_id'], 0x14)
            for addresses in ([], list(range(8, 120))):
                device.reset_mock()
                bus.scan.return_value = addresses
                with self.assertRaises(RuntimeError):
                    factory._touch(board, lv)
                device.assert_not_called()


if __name__ == '__main__':
    unittest.main()
