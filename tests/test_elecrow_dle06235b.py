"""Hardware-free checks for the experimental DLE06235B adapter."""

from pathlib import Path
import importlib.util
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


_MODULE_NAMES = (
    "tartlabutils",
    "tartlabutils.modern",
    "tartlabutils.elecrow_dle06235b",
)
_SAVED_MODULES = {name: sys.modules.get(name) for name in _MODULE_NAMES}
try:
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    sys.modules["tartlabutils"] = package
    load_source(
        "tartlabutils.modern",
        ROOT / "src/lib/tartlabutils/modern.py",
    )
    module = load_source(
        "tartlabutils.elecrow_dle06235b",
        ROOT / "src/lib/tartlabutils/elecrow_dle06235b.py",
    )
finally:
    for name, saved in _SAVED_MODULES.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


class FakeController:
    rotation = 0

    def __init__(self):
        self.pending = False
        self.starts = 0

    def begin_direct_transfer(self):
        if self.pending:
            raise RuntimeError("transfer already pending")
        self.pending = True
        self.starts += 1

    def cancel_direct_transfer(self):
        self.pending = False

    def wait_for_transfer(self, timeout_ms=1000):
        self.pending = False

    @property
    def transfer_pending(self):
        return self.pending


class FakeBus:
    def __init__(self):
        self.transfers = []

    def tx_color(self, *args):
        command, buffer, x1, y1, x2, y2, rotation, last = args
        self.transfers.append(
            (command, bytes(buffer), x1, y1, x2, y2, rotation, last))


class FakePanel:
    def __init__(self):
        self.params = []

    def set_params(self, command, params):
        self.params.append((command, bytes(params)))


class ElecrowDirectSurfaceTests(unittest.TestCase):
    def prepare(self):
        controller = FakeController()
        bus = FakeBus()
        panel = FakePanel()
        freed = []

        def allocate(size, unused_flags):
            return bytearray(size)

        surface = module.ST77922DirectRGB565Surface(
            controller, bus, panel, 8, 2, 3, allocate, freed.append, 4)
        return controller, bus, panel, freed, surface

    def test_partial_write_requires_full_frame_seed(self):
        unused_controller, unused_bus, unused_panel, unused_freed, surface = (
            self.prepare())
        with self.assertRaisesRegex(RuntimeError, "full-frame seed"):
            surface.write(b"\x00\x01", 0, 0, 1, 1)

    def test_unaligned_write_preserves_neighbors_from_shadow(self):
        controller, bus, panel, unused_freed, surface = self.prepare()
        seed = bytes(range(32))
        surface.write(seed, 0, 0, 8, 2)
        bus.transfers.clear()
        panel.params.clear()

        surface.write(b"\x64\x65\x66\x67", 1, 0, 2, 1)

        self.assertEqual(panel.params, [
            (0x2A, b"\x00\x00\x00\x03"),
            (0x2B, b"\x00\x00\x00\x00"),
        ])
        self.assertEqual(bus.transfers, [(
            0x32002C00,
            b"\x00\x01\x64\x65\x66\x67\x06\x07",
            0, 0, 3, 0, 0, True,
        )])
        self.assertEqual(controller.starts, 2)

    def test_unaligned_async_rejection_does_not_mutate_shadow(self):
        unused_controller, bus, unused_panel, unused_freed, surface = (
            self.prepare())
        seed = bytes(range(32))
        surface.write(seed, 0, 0, 8, 2)
        before = bytes(surface._shadow)
        bus.transfers.clear()

        with self.assertRaisesRegex(ValueError, "wait=True"):
            surface.write(b"\xaa\xbb", 1, 0, 1, 1, wait=False)

        self.assertEqual(bytes(surface._shadow), before)
        self.assertEqual(bus.transfers, [])

    def test_new_game_ownership_invalidates_shadow(self):
        unused_controller, unused_bus, unused_panel, unused_freed, surface = (
            self.prepare())
        surface.write(bytes(32), 0, 0, 8, 2)
        self.assertTrue(surface.shadow_valid)
        surface.invalidate_shadow()
        self.assertFalse(surface.shadow_valid)

    def test_direct_resources_are_freed_once(self):
        unused_controller, unused_bus, unused_panel, freed, surface = (
            self.prepare())
        scratch = surface._scratch
        shadow = surface._shadow
        surface.free_resources()
        surface.free_resources()
        self.assertEqual(freed, [scratch, shadow])


class ElecrowControllerTests(unittest.TestCase):
    def test_callback_error_is_contained_until_main_thread_wait(self):
        controller = module.ElecrowDisplayController.__new__(
            module.ElecrowDisplayController)
        controller._transfer_pending = True
        controller._owner = module.UI_OWNER
        controller._callback_failed = False
        controller.surface = types.SimpleNamespace(
            shadow_valid=True,
            invalidate_shadow=lambda: setattr(
                controller.surface, "shadow_valid", False),
        )

        class Display:
            def flush_ready(self):
                raise RuntimeError("synthetic ISR callback failure")

        controller._lv_display = Display()
        controller._transfer_complete()
        self.assertFalse(controller._transfer_pending)
        self.assertTrue(controller._callback_failed)
        with self.assertRaisesRegex(RuntimeError, "completion callback failed"):
            controller.wait_for_transfer()
        self.assertFalse(controller._callback_failed)
        self.assertFalse(controller.surface.shadow_valid)

    def test_portrait_progress_bar_fits_the_display(self):
        class Widget:
            def set_style_bg_color(self, *unused):
                pass

            def set_style_border_width(self, *unused):
                pass

            def set_style_border_color(self, *unused):
                pass

            def set_text(self, *unused):
                pass

            def align(self, *unused):
                pass

        class Bar(Widget):
            def __init__(self):
                self.sizes = []

            def set_range(self, *unused):
                pass

            def set_size(self, width, height):
                self.sizes.append((width, height))

        bar = Bar()
        lvgl = types.SimpleNamespace(
            ALIGN=types.SimpleNamespace(
                BOTTOM_MID=1, TOP_MID=2, CENTER=3),
            obj=Widget,
            label=lambda unused_parent: Widget(),
            bar=lambda unused_parent: bar,
            color_hex=lambda value: value,
            screen_load=lambda unused_screen: None,
        )
        controller = types.SimpleNamespace(
            acquire_ui=lambda: None,
            surface=types.SimpleNamespace(width=320),
        )
        module.ElecrowIDEView(controller, lvgl)
        self.assertEqual(bar.sizes, [(420, 20), (296, 20)])


class ElecrowDriverSourceTests(unittest.TestCase):
    def test_hardware_driver_uses_async_completion_and_frees_scratch(self):
        source = (ROOT / "firmware/lvgl-modern/drivers/st77922.py").read_text(
            encoding="utf-8")
        self.assertNotIn("register_callback(None)", source)
        self.assertNotIn("self._disp_drv.flush_ready()", source)
        self.assertIn("lcd_bus.free_buffer(rotation_buffer)", source)


if __name__ == "__main__":
    unittest.main()
