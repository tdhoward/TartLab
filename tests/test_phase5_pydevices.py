import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/lib"))
sys.path.insert(0, str(ROOT / "tools"))

from phase5_benchmark import validate_result
from phase5_pydevices_device import SELECTOR_PATHS, STAGED_FILES
from pydevices_modern_firmware import check_lock, docker_command


def load_adapter():
    modern_path = ROOT / "src/lib/tartlabutils/modern.py"
    modern_spec = importlib.util.spec_from_file_location(
        "phase5_pydevices_modern_dependency", modern_path)
    modern = importlib.util.module_from_spec(modern_spec)
    modern_spec.loader.exec_module(modern)
    package = types.ModuleType("tartlabutils")
    package.__path__ = []
    path = ROOT / "src/lib/tartlabutils/pydevices_modern.py"
    spec = importlib.util.spec_from_file_location("phase5_pydevices_adapter", path)
    module = importlib.util.module_from_spec(spec)
    old_package = sys.modules.get("tartlabutils")
    old_modern = sys.modules.get("tartlabutils.modern")
    sys.modules["tartlabutils"] = package
    sys.modules["tartlabutils.modern"] = modern
    try:
        spec.loader.exec_module(module)
    finally:
        if old_package is None:
            sys.modules.pop("tartlabutils", None)
        else:
            sys.modules["tartlabutils"] = old_package
        if old_modern is None:
            sys.modules.pop("tartlabutils.modern", None)
        else:
            sys.modules["tartlabutils.modern"] = old_modern
    return module


class FakeClaim:
    def __init__(self):
        self.released = 0

    def release(self):
        self.released += 1


class FakeApp:
    def __init__(self):
        self.claims = []
        self.quit_count = 0

    def pause_refresh(self):
        claim = FakeClaim()
        self.claims.append(claim)
        return claim

    def request_quit(self):
        self.quit_count += 1


class FakeDisplay:
    width = 480
    height = 222

    def __init__(self):
        self.transfers = []
        self.raise_on_blit = False
        self.brightness = 1.0

    def blit_rect(self, buffer, x, y, width, height):
        if self.raise_on_blit:
            raise RuntimeError("blit failed")
        self.transfers.append((buffer, x, y, width, height))


class FakeLoop:
    def __init__(self):
        self.disable_count = 0
        self.enable_count = 0

    def disable(self):
        self.disable_count += 1

    def enable(self):
        self.enable_count += 1


class FakeInput:
    def __init__(self):
        self.states = []

    def enable(self, value):
        self.states.append(value)


class FakeScreen:
    def __init__(self):
        self.invalidations = 0

    def invalidate(self):
        self.invalidations += 1


class FakeLVGL:
    def __init__(self):
        self.screen = FakeScreen()
        self.refreshes = []

    def refr_now(self, display):
        self.refreshes.append(display)

    def screen_active(self):
        return self.screen


class PyDevicesRenderingAdapterTests(unittest.TestCase):
    def setUp(self):
        self.module = load_adapter()
        self.app = FakeApp()
        self.display = FakeDisplay()
        self.lvgl = FakeLVGL()
        self.loop = FakeLoop()
        self.input = FakeInput()
        self.controller = self.module.PyDevicesDisplayController(
            self.app, self.display, object(), self.lvgl, self.loop,
            [self.input],
        )

    def test_direct_surface_is_exclusive_synchronous_and_big_endian(self):
        surface = self.controller.surface
        self.assertEqual(surface.color_format, "RGB565_BE")
        with self.assertRaisesRegex(
                self.module.DisplayOwnershipError, "game display ownership"):
            surface.write(bytearray(2), 0, 0, 1, 1)

        self.controller.acquire_game()
        buffer = surface.allocate_buffer(2, 2)
        surface.write(buffer, 3, 4, 2, 2, wait=False)

        self.assertFalse(surface.busy)
        self.assertEqual(self.display.transfers, [(buffer, 3, 4, 2, 2)])
        surface.wait()

    def test_surface_rejects_bad_regions_and_clears_failure_state(self):
        surface = self.controller.acquire_game()
        with self.assertRaisesRegex(ValueError, "outside"):
            surface.write(bytearray(2), 480, 0, 1, 1)
        with self.assertRaisesRegex(ValueError, "expected 8"):
            surface.write(bytearray(6), 0, 0, 2, 2)
        self.display.raise_on_blit = True
        with self.assertRaisesRegex(RuntimeError, "blit failed"):
            surface.write(bytearray(2), 0, 0, 1, 1)
        self.assertFalse(surface.busy)

    def test_ui_game_ui_transition_pauses_and_redraws(self):
        self.controller.acquire_game()
        self.assertEqual(self.loop.disable_count, 1)
        self.assertEqual(self.input.states, [False])
        self.assertEqual(len(self.app.claims), 1)
        self.assertEqual(self.controller.owner, self.module.GAME_OWNER)

        self.controller.acquire_ui()
        self.assertEqual(self.app.claims[0].released, 1)
        self.assertEqual(self.input.states, [False, True])
        self.assertEqual(self.loop.enable_count, 1)
        self.assertEqual(self.lvgl.screen.invalidations, 1)
        self.assertEqual(self.controller.owner, self.module.UI_OWNER)

    def test_platform_reports_synchronous_transport_and_deinits_once(self):
        platform = self.module.PyDevicesModernPlatform(
            self.controller, self.display, object(), self.app, lvgl=self.lvgl)
        self.assertTrue(platform.capabilities["direct_rgb565"])
        self.assertFalse(platform.capabilities["async_direct_rgb565"])
        self.assertEqual(
            platform.capabilities["phase5_benchmark_profile"], "pydevices")
        platform.set_brightness(0.5)
        self.assertEqual(self.display.brightness, 0.5)
        platform.deinit()
        platform.deinit()
        self.assertEqual(self.app.quit_count, 1)


class PyDevicesFirmwareLockTests(unittest.TestCase):
    def test_reversible_staging_covers_both_protected_selectors(self):
        self.assertEqual(
            set(SELECTOR_PATHS), {"/device/hdwconfig.py", "/hdwconfig.py"})
        self.assertEqual(set(STAGED_FILES), {
            "/lib/tartlabutils/pydevices_modern.py",
            "/configs/t_display_s3_pro_pydevices_modern.py",
        })

    def test_lock_pins_complete_minimal_research_recipe(self):
        lock = check_lock()
        self.assertEqual({item["layout"] for item in lock["sources"]}, {
            "cmods", "displayif", "lvgl-micropython", "lvgl-bindings",
            "micropython", "pydevices",
        })
        self.assertFalse(lock["build"]["whole_pydevices_repository_frozen"])
        self.assertTrue(lock["transport"]["blocking"])
        self.assertFalse(lock["transport"]["dma_completion_callback"])
        self.assertEqual(lock["production_selection"]["status"], "not-selected")
        self.assertEqual(
            lock["status"], "research-only-reproducible-candidate")
        self.assertEqual(lock["result"]["independent_clean_builds"], 2)
        self.assertTrue(lock["result"]["byte_identical"])
        self.assertEqual(lock["capability_gate"]["required_before_selection"], [
            "complete-physical-lifecycle-gate",
            "asynchronous-display-transfer",
            "render-transfer-overlap",
        ])
        self.assertEqual(
            lock["production_selection"]["comparison_outcome"],
            "lcd_bus-reference-wins",
        )

    def test_container_command_is_digest_pinned_and_non_flashing(self):
        command = docker_command(check_lock(), ROOT / "build/phase5")
        image = next(item for item in command if item.startswith("espressif/idf@"))
        self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")
        self.assertNotIn("deploy", command)
        self.assertFalse(any(item.startswith("PORT=") for item in command))
        self.assertIn("MP_AUTOSIZE=0", command)
        displayif_mount = command[command.index("--volume") + 1:]
        self.assertTrue(any(
            item.endswith("/workspace/displayif")
            for item in displayif_mount
        ))

    def test_compatibility_patch_is_narrow_and_hash_bound(self):
        lock = check_lock()
        patch_path = "firmware/lvgl-modern/pydevices/patches/displayif-mperrno.patch"
        self.assertIn(
            patch_path,
            {item["path"] for item in lock["build"]["local_inputs"]},
        )
        patch = (ROOT / patch_path).read_text(encoding="utf-8")
        self.assertEqual(patch.count("+#include \"py/mperrno.h\""), 1)
        self.assertNotIn("micropython/", patch)

    def test_minimal_manifest_does_not_freeze_whole_vendor_tree(self):
        source = (ROOT / "firmware/lvgl-modern/pydevices/manifest-user.py").read_text(
            encoding="utf-8")
        self.assertNotIn('package("lib"', source)
        self.assertIn('"displaydev/busdisplay.py"', source)
        self.assertIn('module("cst226.py"', source)

    def test_benchmark_accepts_explicit_synchronous_pydevices_profile(self):
        result = {
            "schema": 1,
            "profile": "pydevices",
            "runtime": {"configured_display_spi_hz": 60_000_000},
            "matrix": {
                "logical_width": 480,
                "logical_height": 222,
                "full_frame_bytes": 213_120,
                "color_format": "RGB565_BE_symmetric_test_assets",
                "transport_rows": 24,
                "raw_transport_buffer_count": 1,
                "pipeline_buffer_count": 2,
                "samples": 3,
                "mode_switches": 2,
                "raw_buffer_storage": "micropython-bytearray",
                "pipeline_buffer_storage": "micropython-bytearray",
                "direct_transfer_async": False,
            },
            "raw_transfers": {
                "full": {"width": 480, "height": 222,
                         "coverage_percent": 100,
                         "submission":
                         "ten-24-row-or-final-shorter-transfers"},
                "dirty_50": {"width": 240, "height": 222,
                             "coverage_percent": 50,
                             "submission":
                             "two-240x111-dirty-rectangle-transfers"},
                "dirty_25": {"width": 120, "height": 222,
                             "coverage_percent": 25,
                             "submission": "one-dirty-rectangle-transfer"},
                "dirty_10": {"width": 48, "height": 222,
                             "coverage_percent": 10,
                             "submission": "one-dirty-rectangle-transfer"},
            },
        }
        validate_result(result, "pydevices")
        invalid = copy.deepcopy(result)
        invalid["matrix"]["raw_buffer_storage"] = "native-internal-dma"
        with self.assertRaisesRegex(ValueError, "buffer storage"):
            validate_result(invalid, "pydevices")


if __name__ == "__main__":
    unittest.main()
