import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from modern_firmware import check_lock, docker_command, validate_lock


class FakePointerDriver:
    PRESSED = 1
    RELEASED = 0

    def __init__(self, **kwargs):
        self.pointer_options = kwargs


class FakeI2CDevice:
    def __init__(self, chip_id=0x00A8):
        self.chip_id = chip_id
        self.status = bytearray(28)
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def write_readinto(self, write_data, read_data):
        command = bytes(write_data)
        if command == b"\xD2\x04":
            read_data[:] = bytes((0, 0, self.chip_id & 0xFF,
                                  self.chip_id >> 8))
        elif command == b"\x00":
            read_data[:] = self.status
        else:
            raise AssertionError(f"unexpected I2C command: {command!r}")


def load_cst226_driver():
    pointer = types.ModuleType("pointer_framework")
    pointer.PointerDriver = FakePointerDriver
    pointer.lv = types.SimpleNamespace(
        DISPLAY_ROTATION=types.SimpleNamespace(_0=0))
    micropython = types.ModuleType("micropython")
    micropython.const = lambda value: value
    machine = types.ModuleType("machine")
    machine.Pin = types.SimpleNamespace(OUT=1, IN=2, PULL_UP=3)
    fake_time = types.ModuleType("time")
    fake_time.sleep_ms = lambda milliseconds: None
    path = ROOT / "firmware/lvgl-modern/drivers/cst226.py"
    spec = importlib.util.spec_from_file_location("phase5_cst226", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {
        "pointer_framework": pointer,
        "micropython": micropython,
        "machine": machine,
        "time": fake_time,
    }):
        spec.loader.exec_module(module)
    return module


class ModernFirmwareReferenceLockTests(unittest.TestCase):
    def test_reference_pins_complete_source_and_toolchain(self):
        lock = check_lock()
        submodules = {
            item["path"]: item for item in lock["source"]["submodules"]
        }
        self.assertEqual(set(submodules), {
            "lib/SDL",
            "lib/esp-idf",
            "lib/lvgl",
            "lib/micropython",
            "lib/pycparser",
        })
        self.assertEqual(submodules["lib/micropython"]["version"], "1.27.0")
        self.assertEqual(submodules["lib/lvgl"]["version"], "9.4.0")
        self.assertEqual(submodules["lib/esp-idf"]["version"], "5.5.1")
        container = lock["toolchain"]["container"]
        self.assertEqual(container["platform"], "linux/amd64")
        self.assertTrue(container["manifest_digest"].startswith("sha256:"))

    def test_reference_remains_unqualified_and_explicit_about_missing_gates(self):
        lock = check_lock()
        self.assertEqual(
            lock["status"], "research-only-reproducible-unqualified")
        missing = lock["capability_gate"][
            "required_before_hardware_qualification"]
        present = lock["capability_gate"]["present_in_reference"]
        self.assertIn("cst226-input-driver", present)
        self.assertIn("public-direct-surface-api", missing)
        self.assertIn("hardware-benchmark-results", missing)
        result = lock["result"]
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["independent_clean_builds"], 2)
        self.assertEqual(
            result["sha256"],
            "172fb43b08c046e8a90b03caa9ecb1c15af6360f5f589d9b9ef86f31972be6f6",
        )

    def test_lock_rejects_a_moving_source_ref(self):
        lock = check_lock()
        invalid = copy.deepcopy(lock)
        invalid["source"]["commit"] = "main"
        with self.assertRaisesRegex(ValueError, "full lowercase Git commit"):
            validate_lock(invalid)

    def test_lock_rejects_a_changed_submodule_pin(self):
        lock = check_lock()
        invalid = copy.deepcopy(lock)
        invalid["source"]["submodules"][0]["commit"] = "0" * 39
        with self.assertRaisesRegex(ValueError, "full lowercase Git commit"):
            validate_lock(invalid)

    def test_build_command_is_digest_pinned_and_cannot_flash(self):
        lock = check_lock()
        command = docker_command(lock, ROOT / "build/phase5/reference-source")
        image = next(item for item in command if item.startswith("espressif/idf@"))
        self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")
        self.assertIn("--platform", command)
        self.assertIn("IDF_GIT_SAFE_DIR=/project", command)
        self.assertIn("SOURCE_DATE_EPOCH=1782211759", command)
        self.assertIn("DISPLAY=st7796", command)
        self.assertIn("--partition-size=4194304", command)
        self.assertIn(
            "INDEV=/tartlab/firmware/lvgl-modern/drivers/cst226.py", command)
        self.assertIn(
            "/tartlab/firmware/lvgl-modern/container_prepare.py", command)
        self.assertNotIn("deploy", command)
        self.assertNotIn("--octal-flash", command)
        self.assertFalse(any(item.startswith("PORT=") for item in command))

    def test_checked_in_phase5_json_has_stable_format(self):
        paths = [
            ROOT / "firmware/lvgl-modern/reference.lock.json",
            ROOT / "firmware/lvgl-modern/reference/provenance.json",
            ROOT / "profiles/lvgl-modern.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                rendered = json.dumps(data, indent=2, sort_keys=False) + "\n"
                self.assertEqual(path.read_text(encoding="utf-8"), rendered)


class CST226ReferenceDriverTests(unittest.TestCase):
    def test_initialization_checks_identity_and_configures_polling(self):
        module = load_cst226_driver()
        device = FakeI2CDevice()
        driver = module.CST226(device)
        self.assertEqual(driver.pointer_options["startup_rotation"], 0)
        self.assertEqual(device.writes, [
            b"\xD1\x0E",
            b"\xFE\x01",
            b"\xFA\x00",
            b"\xEC\x00",
        ])

    def test_first_contact_is_reported_to_pointer_framework(self):
        module = load_cst226_driver()
        device = FakeI2CDevice()
        driver = module.CST226(device)
        device.status[1] = 0x12
        device.status[2] = 0x45
        device.status[3] = 0x36
        device.status[5] = 1
        self.assertEqual(driver._get_coords(), (driver.PRESSED, 0x123, 0x456))
        device.status[0] = 0xAB
        self.assertIsNone(driver._get_coords())

    def test_wrong_controller_identity_is_rejected(self):
        module = load_cst226_driver()
        with self.assertRaisesRegex(RuntimeError, "CST226 not detected"):
            module.CST226(FakeI2CDevice(chip_id=0x1234))


if __name__ == "__main__":
    unittest.main()
