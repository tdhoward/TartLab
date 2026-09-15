"""Faulted buses must not be interpreted as responding touch controllers."""

from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
probe = runpy.run_path(str(ROOT / "tools/device/touch_bus_probe.py"))["touch_bus_probe"]
CONFIG = {"id": "fixture", "pins": ({"type": "TOUCH_SDA", "number": 3},
                                    {"type": "TOUCH_SCL", "number": 4}),
          "touch": {"driver": "gt911.GT911", "i2c": {"host": -1, "frequency": 10000},
                    "addresses": (0x5D, 0x14),
                    "reset_expander": {"driver": "PCA9557", "address": 0x18}}}


class TouchBusProbeTests(unittest.TestCase):
    def environment(self, levels=(1, 1), addresses=(0x18, 0x5D)):
        bus = Mock()
        bus.scan.return_value = list(addresses)
        bus.readfrom_mem.side_effect = [b"911\x00", b"\x20\x03\xe0\x01"]
        pin = Mock(side_effect=[Mock(value=Mock(return_value=value)) for value in levels])
        pin.OPEN_DRAIN, pin.PULL_UP = 7, 1
        machine = types.SimpleNamespace(Pin=pin, SoftI2C=Mock(return_value=bus),
                                        freq=lambda: 240000000)
        return bus, machine

    def inspect(self, machine):
        with patch.dict(sys.modules, {"machine": machine,
                                     "time": types.SimpleNamespace(sleep_ms=lambda ms: None)}):
            return probe(CONFIG)

    def test_low_line_skips_bus_transactions(self):
        for levels in ((0, 1), (1, 0), (0, 0)):
            bus, machine = self.environment(levels)
            result = self.inspect(machine)
            self.assertFalse(result["controller_valid"])
            self.assertIn("not idle", result["error"])
            machine.SoftI2C.assert_not_called()
            bus.readfrom_mem.assert_not_called()

    def test_all_address_ack_skips_controller_reads(self):
        bus, machine = self.environment(addresses=range(0x08, 0x78))
        result = self.inspect(machine)
        self.assertFalse(result["controller_valid"])
        self.assertIn("invalid bus", result["error"])
        bus.readfrom_mem.assert_not_called()
        bus.writeto_mem.assert_not_called()

    def test_valid_identity_is_read_without_controller_writes(self):
        bus, machine = self.environment()
        result = self.inspect(machine)
        self.assertTrue(result["controller_valid"])
        self.assertNotIn("error", result)
        self.assertEqual(result["controllers"][0]["address"], 0x5D)
        bus.writeto_mem.assert_not_called()

    def test_line_fault_during_scan_skips_controller_reads(self):
        bus, machine = self.environment()
        sda = Mock()
        sda.value.side_effect = [1, 0]
        machine.Pin.side_effect = [sda, Mock(value=Mock(return_value=1))]
        result = self.inspect(machine)
        self.assertFalse(result["controller_valid"])
        self.assertIn("after scan", result["error"])
        bus.readfrom_mem.assert_not_called()

    def test_missing_zero_or_unreadable_controller_cannot_pass(self):
        for responses in ([b"\x00" * 4, b"\x00" * 4],
                          [b"911\x00", b"\x00" * 4], [OSError(5)]):
            bus, machine = self.environment()
            bus.readfrom_mem.side_effect = responses
            result = self.inspect(machine)
            self.assertFalse(result["controller_valid"])
            self.assertIn("no valid", result["error"])
        bus, machine = self.environment(addresses=(0x18,))
        self.assertFalse(self.inspect(machine)["controller_valid"])
        bus.readfrom_mem.assert_not_called()

    def test_old_board_probe_never_resets_expander_on_false_ack(self):
        bus, machine = self.environment(addresses=range(0x08, 0x78))
        modules = {"machine": machine, "hdwconfig": types.SimpleNamespace(BOARD_CONFIG=CONFIG)}
        for name in ("lvgl", "lcd_bus", "rgb_display", "gt911", "external_root"):
            modules[name] = Mock()
        for name in ("version_major", "version_minor", "version_patch"):
            getattr(modules["lvgl"], name).return_value = 1
        with patch.dict(sys.modules, modules), patch("gc.mem_free", return_value=1, create=True), \
                patch("gc.mem_alloc", return_value=1, create=True), \
                patch("os.statvfs", return_value=(), create=True), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "Invalid I2C bus"):
                runpy.run_path(str(ROOT / "tools/device/board_probe.py"))
        bus.readfrom_mem.assert_not_called()
        bus.writeto_mem.assert_not_called()


if __name__ == "__main__":
    unittest.main()
