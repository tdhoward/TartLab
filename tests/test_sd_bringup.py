"""Storage-pattern and non-destructive staging contracts."""

from pathlib import Path
import io
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from sd_bringup import capture_reset, expected_file, validate_files, validate_runtime, validate_soak_resume
from stage_sd_bench import check_collision


class SDBringupTests(unittest.TestCase):
    def test_known_baseline_hash(self):
        self.assertEqual(expected_file(1048576), {
            "bytes": 1048576,
            "sha256": "da8710f4848e0682b7661044aa41ef71c13496799d06e4534f80fa2258306b83"})

    def test_never_overwrites_foreign_or_subsequently_edited_files(self):
        journal = {"complete": False, "owned": ["main.py"], "verified": []}
        for path, marker in (("main.py", False), ("user.py", True)):
            with self.assertRaisesRegex(ValueError, "preserved"):
                check_collision(path, "foreign", "expected", journal, marker)
        journal["verified"] = ["main.py"]
        with self.assertRaisesRegex(ValueError, "preserved"):
            check_collision("main.py", "edited", "expected", journal, True)
        journal["verified"] = []
        journal["complete"] = True
        with self.assertRaisesRegex(ValueError, "preserved"):
            check_collision("main.py", "edited", "expected", journal, True)

    def test_resume_requires_owned_unfinished_file_and_matching_card(self):
        journal = {"complete": False, "owned": ["main.py"], "verified": []}
        check_collision("main.py", "partial", "expected", journal, True)
        check_collision("untouched.py", "expected", "expected", journal, False)
        check_collision("new.py", None, "expected", journal, False)

    def test_missing_or_extra_file_evidence_cannot_pass(self):
        expected = {"a": expected_file(511), "b": expected_file(513)}
        for actual in ({}, {"a": expected["a"]}, {**expected, "extra": expected["a"]}):
            with self.assertRaisesRegex(ValueError, "coverage"):
                validate_files(actual, expected)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            validate_files({"a": expected["b"], "b": expected["a"]}, expected)
        validate_files(expected, expected)

    def test_soft_reset_requires_one_startup_and_consistent_persisted_state(self):
        def state(count):
            return {"board_id": "fixture", "mounts": [["<VfsFat>", "/"], ["<VfsLfs2>", "/flash"]],
                    "counts": {"boot": count, "main": count},
                    "state": {"boot": count, "main": count},
                    "user_file": {"boot": count, "main": count},
                    "selector": "/device/hdwconfig.py", "library": "/lib/tartlabutils/__init__.py",
                    "board_runtime": "/board/fixture", "internal_main_bytes": 100,
                    "reset_cause": 5, "soft_reset_cause": 5}
        validate_runtime(state(3), state(2))
        for value in (state(2), state(4), {**state(3), "reset_cause": 1},
                      {**state(3), "state": {"boot": 2, "main": 2}},
                      {**state(3), "selector": "/hdwconfig.py"},
                      {**state(3), "mounts": [["<VfsLfs2>", "/"]]}):
            with self.assertRaises(ValueError):
                validate_runtime(value, state(2))

    def test_reset_failure_retains_complete_traceback(self):
        chunks = iter((b"MPY: soft reboot\r\nTraceback (most recent ca", b"ll last):\r\n",
                       b"TypeError: broken SPI\r\n>>> "))
        serial = types.SimpleNamespace(write=lambda data: None, in_waiting=1,
                                       read=lambda size: next(chunks))
        repl = types.SimpleNamespace(serial=serial, exec=lambda code: None,
                                     _read_until=lambda marker: b">>> ")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "startup.log"
            self.assertFalse(capture_reset(repl, True, path))
            self.assertIn(b"TypeError: broken SPI\r\n>>> ", path.read_bytes())

    def test_load_collision_preserves_existing_content(self):
        load = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                 "tools/device/sd_runtime_load.py"))["sd_runtime_load"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.bin"
            path.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "preserved"):
                load("unused", str(path), expected_file(511), None)
            self.assertEqual(path.read_bytes(), b"original")

    def test_reset_recovery_cannot_hide_native_panic_or_hard_reboot(self):
        for prefix, expected in ((b"MPY: soft reboot\r\n", True),
                                 (b"MPY: soft reboot\r\nGuru Meditation Error\r\n", False),
                                 (b"MPY: soft reboot\r\nESP-ROM:esp32s3\r\n", False),
                                 (b"A fatal error occurred\r\n", False)):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                output = prefix + b"SD_BENCH_READY\r\n>>> "
                serial = types.SimpleNamespace(write=lambda data: None, in_waiting=len(output),
                                               read=lambda size: output)
                repl = types.SimpleNamespace(serial=serial, exec=lambda code: None,
                                             _read_until=lambda marker: b">>> ")
                path = Path(directory) / "startup.log"
                self.assertEqual(capture_reset(repl, True, path), expected)
                self.assertEqual(path.read_bytes(), output)

    def test_soak_resume_rejects_foreign_paths_boards_and_duplicate_coverage(self):
        remote = "/.tartlab-bench/soak-" + "a" * 32
        cycle = {"path": remote + "/01.bin", **expected_file(1048576)}
        prior = {"action": "soak", "session": "baseline", "before": {"board_id": "fixture"},
                 "output_directory": remote, "requested_cycles": 8, "cycles": [cycle]}
        validate_soak_resume(prior, "baseline", {"board_id": "fixture"})
        for changed in ({**prior, "session": "different"},
                        {**prior, "before": {"board_id": "different"}},
                        {**prior, "cycles": [cycle, cycle]},
                        {**prior, "output_directory": "/flash"},
                        {**prior, "cycles": [{**cycle, "path": "/flash/main.py"}]},
                        {**prior, "cycles": [{**cycle, "sha256": "wrong"}]}):
            with self.assertRaises(ValueError):
                validate_soak_resume(changed, "baseline", {"board_id": "fixture"})

    def test_load_io_failure_stops_test_wifi_and_preserves_existing_network(self):
        load = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                 "tools/device/sd_runtime_load.py"))["sd_runtime_load"]

        class Interface:
            enabled = False

            def active(self, value=None):
                if value is not None:
                    self.enabled = value
                return self.enabled

            def config(self, **kwargs):
                pass

            def scan(self):
                return []

        ap, station = Interface(), Interface()
        network = types.SimpleNamespace(AP_IF=1, STA_IF=0, AUTH_WPA2_PSK=3,
                                        WLAN=lambda role: ap if role else station)
        missing = Mock(side_effect=FileNotFoundError(2, "absent"))
        fake_os = types.SimpleNamespace(stat=missing, sync=Mock())
        fake_time = types.SimpleNamespace(ticks_ms=lambda: 0, ticks_diff=lambda a, b: a - b)
        fake_gc = types.SimpleNamespace(collect=lambda: None, mem_free=lambda: 100000)
        writer = io.BytesIO()
        writer.write = lambda value: 0  # Simulate a short write, e.g. full media.
        namespace = {"os": fake_os, "time": fake_time, "gc": fake_gc,
                     "lv": Mock(), "status": Mock()}
        with patch.dict(load.__globals__, namespace), patch.dict(sys.modules, {"network": network}):
            with patch("builtins.open", side_effect=[io.BytesIO(b"data"), writer]):
                with self.assertRaisesRegex(OSError, "short SD write"):
                    load("source", "destination", expected_file(4), {"ssid": "test", "password": "test"})
            self.assertFalse(ap.active())
            self.assertFalse(station.active())
            fake_os.sync.assert_called_once()
            station.active(True)
            with self.assertRaisesRegex(ValueError, "existing network state preserved"):
                load("source", "destination", expected_file(4), {"ssid": "test", "password": "test"})
            self.assertTrue(station.active())
            self.assertFalse(ap.active())


if __name__ == "__main__":
    unittest.main()
