"""Hardware-free checks for the reusable ST7796 scroll adapter."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_modules():
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    modern_path = ROOT / "src/lib/tartlabutils/modern.py"
    modern_spec = importlib.util.spec_from_file_location(
        "tartlabutils.modern", modern_path)
    modern = importlib.util.module_from_spec(modern_spec)
    adapter_path = ROOT / "src/lib/tartlabutils/modern_st7796.py"
    adapter_spec = importlib.util.spec_from_file_location(
        "tartlabutils.modern_st7796", adapter_path)
    adapter = importlib.util.module_from_spec(adapter_spec)
    with mock.patch.dict(sys.modules, {
        "tartlabutils": package,
        "tartlabutils.modern": modern,
        "tartlabutils.modern_st7796": adapter,
    }):
        modern_spec.loader.exec_module(modern)
        adapter_spec.loader.exec_module(adapter)
    return modern, adapter


class FakeController:
    def __init__(self, game_owner):
        self.owner = game_owner
        self.rotation = 3
        self.transfer_pending = False
        self.waits = 0

    def begin_direct_transfer(self):
        if self.transfer_pending:
            raise RuntimeError("transfer already pending")
        self.transfer_pending = True

    def cancel_direct_transfer(self):
        self.transfer_pending = False

    def wait_for_transfer(self, timeout_ms=1000):
        self.waits += 1
        self.transfer_pending = False


class FakeBus:
    def __init__(self):
        self.transfers = []

    def tx_color(self, *values):
        self.transfers.append(
            (values[0], bytes(values[1]), *values[2:]))


class FakePanel:
    def __init__(self, fail_command=None):
        self.params = []
        self.fail_command = fail_command

    def set_params(self, command, params=None):
        self.params.append((command, bytes(params or b"")))
        if command == self.fail_command:
            self.fail_command = None
            raise RuntimeError("synthetic panel command failure")


class ST7796ScrollTests(unittest.TestCase):
    def make_surface(self, qualified=(270,), panel=None):
        modern, adapter = load_modules()
        controller = FakeController(modern.GAME_OWNER)
        bus = FakeBus()
        panel = panel or FakePanel()
        allocations = []
        frees = []

        def allocate(size, flags):
            allocations.append((size, flags))
            return bytearray(size)

        surface = adapter.ST7796DirectRGB565Surface(
            controller, bus, panel,
            width=6, height=4, offset_x=0, offset_y=2,
            transfer_rows=2, allocation_flags=3,
            buffer_allocator=allocate, buffer_free=frees.append,
            scroll_config={"qualified_rotations": qualified},
            native_height=6, panel_rotation=270)
        return modern, adapter, controller, bus, panel, surface, allocations, frees

    def test_capabilities_are_expressed_after_canvas_rotation(self):
        unused_modern, unused_adapter, unused_controller, unused_bus, \
            unused_panel, surface, unused_allocations, unused_frees = \
            self.make_surface()

        self.assertEqual(surface.scroll_capabilities(0)["axes"], ("x",))
        self.assertEqual(surface.scroll_capabilities(90)["axes"], ("y",))
        self.assertEqual(surface.scroll_capabilities(180)["axes"], ("x",))
        self.assertEqual(surface.scroll_capabilities(270)["axes"], ("y",))

    def test_unqualified_rotation_always_uses_software_fallback(self):
        unused_modern, unused_adapter, unused_controller, unused_bus, panel, \
            surface, unused_allocations, unused_frees = self.make_surface(())

        self.assertEqual(surface.scroll_capabilities()["axes"], ())
        self.assertFalse(surface.present_scroll((0, 0, 6, 4), 1, 0))
        self.assertEqual(panel.params, [])

    def test_scroll_programs_fixed_areas_and_start_address(self):
        unused_modern, unused_adapter, controller, unused_bus, panel, surface, \
            unused_allocations, unused_frees = self.make_surface()

        self.assertTrue(surface.present_scroll((1, 0, 4, 4), 1, 0))

        self.assertEqual(panel.params, [
            (0x33, b"\x00\x01\x00\x04\x00\x01"),
            (0x37, b"\x00\x04"),
        ])
        self.assertGreaterEqual(controller.waits, 1)

    def test_every_composite_canvas_rotation_reaches_surface_axis(self):
        cases = (
            (0, (1, 0, 4, 4), 1, 0),
            (90, (0, 1, 4, 4), 0, 1),
            (180, (1, 0, 4, 4), -1, 0),
            (270, (0, 1, 4, 4), 0, -1),
        )
        for rotation, area, dx, dy in cases:
            with self.subTest(rotation=rotation):
                (unused_modern, unused_adapter, unused_controller,
                 unused_bus, panel, surface, unused_allocations,
                 unused_frees) = self.make_surface()

                self.assertTrue(surface.present_scroll(
                    area, dx, dy, rotation))
                self.assertEqual(panel.params, [
                    (0x33, b"\x00\x01\x00\x04\x00\x01"),
                    (0x37, b"\x00\x04"),
                ])

    def test_reversed_panel_rotation_maps_native_direction(self):
        unused_modern, adapter = load_modules()
        controller = FakeController("game")
        panel = FakePanel()
        scroll = adapter.ST7796ScrollAdapter(
            controller, panel, surface_width=6, surface_height=4,
            panel_rotation=90, native_height=6,
            qualified_rotations=(90,))

        self.assertTrue(scroll.scroll(0, 4, 1))

        self.assertEqual(panel.params, [
            (0x33, b"\x00\x02\x00\x04\x00\x00"),
            (0x37, b"\x00\x03"),
        ])

    def test_unsupported_axis_region_and_distance_do_not_touch_panel(self):
        unused_modern, unused_adapter, unused_controller, unused_bus, panel, \
            surface, unused_allocations, unused_frees = self.make_surface()

        self.assertFalse(surface.present_scroll((0, 0, 6, 4), 0, 1))
        self.assertFalse(surface.present_scroll((0, 1, 6, 3), 1, 0))
        self.assertFalse(surface.present_scroll((1, 0, 4, 4), 4, 0))
        self.assertEqual(panel.params, [])

    def test_dirty_write_is_split_and_repacked_across_wrap_seam(self):
        unused_modern, unused_adapter, unused_controller, bus, unused_panel, \
            surface, allocations, unused_frees = self.make_surface()
        surface.present_scroll((1, 0, 4, 4), 1, 0)
        pixels = bytes(range(8))

        surface.write(pixels, 1, 0, 2, 2)

        self.assertEqual(allocations, [(24, 3)])
        self.assertEqual(bus.transfers, [
            (0x2C, b"\x00\x01\x04\x05", 4, 2, 4, 3, 3, True),
            (0x2C, b"\x02\x03\x06\x07", 1, 2, 1, 3, 3, True),
        ])

    def test_fixed_area_write_is_not_translated(self):
        unused_modern, unused_adapter, unused_controller, bus, unused_panel, \
            surface, unused_allocations, unused_frees = self.make_surface()
        surface.present_scroll((1, 0, 4, 4), -1, 0)

        surface.write(b"\x10\x11\x12\x13", 5, 1, 1, 2)

        self.assertEqual(bus.transfers, [
            (0x2C, b"\x10\x11\x12\x13", 5, 3, 5, 4, 3, True),
        ])

    def test_reset_restores_neutral_definition_and_releases_scratch(self):
        unused_modern, unused_adapter, unused_controller, bus, panel, surface, \
            unused_allocations, frees = self.make_surface()
        surface.present_scroll((1, 0, 4, 4), 1, 0)
        surface.write(bytes(range(8)), 1, 0, 2, 2)
        panel.params.clear()

        surface.free_resources()
        surface.free_resources()

        self.assertEqual(panel.params, [
            (0x37, b"\x00\x01"),
            (0x33, b"\x00\x00\x00\x06\x00\x00"),
            (0x37, b"\x00\x00"),
        ])
        self.assertEqual(len(frees), 1)
        self.assertFalse(surface._scroll.active)
        self.assertEqual(len(bus.transfers), 2)

    def test_command_failure_attempts_neutral_cleanup(self):
        panel = FakePanel(fail_command=0x37)
        unused_modern, unused_adapter, unused_controller, unused_bus, panel, \
            surface, unused_allocations, unused_frees = self.make_surface(
                panel=panel)

        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            surface.present_scroll((1, 0, 4, 4), 1, 0)

        self.assertIn(
            (0x33, b"\x00\x00\x00\x06\x00\x00"), panel.params)
        self.assertFalse(surface._scroll.active)

    def test_scroll_rejects_ui_ownership(self):
        modern, unused_adapter, controller, unused_bus, unused_panel, surface, \
            unused_allocations, unused_frees = self.make_surface()
        controller.owner = modern.UI_OWNER

        with self.assertRaisesRegex(RuntimeError, "game display ownership"):
            surface.present_scroll((1, 0, 4, 4), 1, 0)

    def test_controller_resets_scanout_before_base_ui_handoff(self):
        modern, adapter = load_modules()
        controller = adapter.ST7796DisplayController.__new__(
            adapter.ST7796DisplayController)
        controller._owner = modern.GAME_OWNER
        events = []
        controller.wait_for_transfer = lambda timeout=1000: events.append(
            ("wait", timeout))
        controller.surface = types.SimpleNamespace(
            reset_scroll=lambda: events.append(("reset",)))

        with mock.patch.object(
                modern.ModernDisplayController, "acquire_ui",
                return_value="ui") as acquire_ui:
            result = controller.acquire_ui(321)

        self.assertEqual(result, "ui")
        self.assertEqual(events, [("wait", 321), ("reset",)])
        acquire_ui.assert_called_once_with(controller, 321)


if __name__ == "__main__":
    unittest.main()
