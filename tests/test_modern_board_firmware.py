from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from modern_board_firmware import (  # noqa: E402
    check_lock, docker_command, validate_lock,
)


LOCK_PATH = ROOT / "firmware/lvgl-modern/elecrow_dle06235b.lock.json"


class ModernBoardFirmwareTests(unittest.TestCase):
    def test_candidate_pins_board_target_and_all_frozen_modules(self):
        lock = check_lock(LOCK_PATH)

        self.assertEqual(lock["board_id"], "elecrow_dle06235b")
        self.assertEqual(lock["status"], "reproducible-candidate")
        self.assertEqual(lock["target"]["display_controller"], "ST77922")
        self.assertEqual(lock["target"]["touch_controller"], "ST77922 TDDI")
        frozen = lock["build"]["frozen_modules"]
        self.assertEqual(
            Path(frozen["display"]).name, "st77922.py")
        self.assertEqual(
            Path(frozen["input"]).name, "st77922_touch.py")
        self.assertEqual(
            [Path(item).name for item in frozen["additional"]],
            ["_st77922_init.py"],
        )

    def test_build_is_digest_pinned_and_cannot_flash(self):
        lock = check_lock(LOCK_PATH)
        command = docker_command(lock, ROOT / "build/board-firmware-source")

        self.assertTrue(any(
            item.startswith("espressif/idf@sha256:") for item in command))
        self.assertIn("--enable-jtag-repl=y", command)
        self.assertIn("--enable-uart-repl=n", command)
        self.assertIn("--enable-cdc-repl=n", command)
        self.assertIn(
            "DISPLAY=/tartlab/firmware/lvgl-modern/drivers/st77922.py",
            command,
        )
        self.assertIn(
            "INDEV=/tartlab/firmware/lvgl-modern/drivers/st77922_touch.py",
            command,
        )
        self.assertNotIn("deploy", command)
        self.assertFalse(any(item.startswith("PORT=") for item in command))

    def test_reproducibility_result_is_board_bound(self):
        lock = check_lock(LOCK_PATH)
        result = lock["result"]
        provenance = json.loads(
            (ROOT / result["provenance"]).read_text(encoding="utf-8"))

        self.assertEqual(result["independent_clean_builds"], 2)
        self.assertTrue(result["byte_identical"])
        self.assertEqual(provenance["board_id"], lock["board_id"])
        self.assertEqual(
            provenance["build_evidence"]["source_commit"],
            lock["source"]["commit"],
        )
        self.assertEqual(
            provenance["frozen_modules"], lock["build"]["frozen_modules"])

    def test_lock_rejects_a_moving_source_ref(self):
        invalid = copy.deepcopy(check_lock(LOCK_PATH))
        invalid["source"]["commit"] = "main"

        with self.assertRaisesRegex(ValueError, "full lowercase Git commit"):
            validate_lock(invalid)

    def test_lock_rejects_an_incomplete_transitive_pin_set(self):
        invalid = copy.deepcopy(check_lock(LOCK_PATH))
        invalid["source"]["esp32_transitive_submodules"].pop()

        with self.assertRaisesRegex(ValueError, "submodule set is incomplete"):
            validate_lock(invalid)

    def test_lock_rejects_an_unbound_additional_frozen_module(self):
        invalid = copy.deepcopy(check_lock(LOCK_PATH))
        invalid["build"]["frozen_modules"]["additional"] = [
            "/tartlab/firmware/lvgl-modern/drivers/missing.py"]

        with self.assertRaisesRegex(ValueError, "hash-bound inputs"):
            validate_lock(invalid)

    def test_lock_rejects_a_changed_local_input(self):
        invalid = copy.deepcopy(check_lock(LOCK_PATH))
        invalid["build"]["inputs"][0]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "source hash differs"):
            validate_lock(invalid)

    def test_checked_in_metadata_is_canonical_json(self):
        lock = check_lock(LOCK_PATH)
        for path in (LOCK_PATH, ROOT / lock["result"]["provenance"]):
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    json.dumps(data, indent=2, sort_keys=False) + "\n",
                )


if __name__ == "__main__":
    unittest.main()
