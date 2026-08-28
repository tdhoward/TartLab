"""Qualification-only modern OTA containment helper tests."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_modern_update_containment import (  # noqa: E402
    ATTESTATION_RECEIPT, CASES, INTERRUPT_PACKAGE, _asset_records, _receipt_path,
    corrupt_download_code, interrupt_download_code,
    interrupt_recovery_code, release_plan, verify_cached_plan,
)


class ModernUpdateContainmentHelperTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "version": "modern-v1",
            "assets": [
                {"name": "modern-manifest.json", "size": 10,
                 "sha256": "a" * 64},
                {"name": INTERRUPT_PACKAGE, "size": 20,
                 "sha256": "b" * 64},
            ],
        }

    def test_case_inventory_covers_corruption_and_both_power_boundaries(self):
        self.assertEqual(CASES, (
            "corrupt-download", "interrupt-download", "interrupt-recovery"))

    def test_asset_adapter_retains_authenticated_names_and_sizes(self):
        self.assertEqual(_asset_records(self.plan), [{
            "name": "modern-manifest.json", "size": 10,
            "browser_download_url": "serial://modern-manifest.json",
        }, {
            "name": INTERRUPT_PACKAGE, "size": 20,
            "browser_download_url": "serial://" + INTERRUPT_PACKAGE,
        }])

    def test_corrupt_case_changes_download_copy_before_real_validation(self):
        code = corrupt_download_code(self.plan, INTERRUPT_PACKAGE)
        self.assertIn("chunk[0] ^ 1", code)
        self.assertIn("updater.update_packages", code)
        self.assertIn("result == updater.UPDATE_FAILED", code)
        self.assertIn("CONTAIN_MARKER", code)

    def test_download_interrupt_signals_while_copy_is_in_progress(self):
        code = interrupt_download_code(self.plan, INTERRUPT_PACKAGE)
        signal = code.index("CONTAIN_POWER_SIGNAL=interrupt-download")
        delay = code.index("utime.sleep_ms(25)")
        self.assertLess(signal, delay)
        self.assertIn("from tartlabutils.platform import get_platform", code)
        self.assertIn("platform.enter_game_mode()", code)
        self.assertIn("stripe_height = 24", code)
        self.assertIn("updater.update_packages", code)

    def test_recovery_interrupt_uses_real_resumable_installer(self):
        code = interrupt_recovery_code(self.plan, INTERRUPT_PACKAGE)
        self.assertIn("_install_verified_packages", code)
        self.assertIn("CONTAIN_POWER_SIGNAL=interrupt-recovery", code)
        self.assertIn("from tartlabutils.platform import get_platform", code)
        self.assertIn("platform.enter_game_mode()", code)
        self.assertIn("stripe_height = 24", code)
        self.assertIn("TEMP = recovery_update.TEMP_DIR", code)
        self.assertIn("open(TEMP + '/' + name, 'wb')", code)
        self.assertIn("_sha256(path) != item['sha256']", code)

    def test_receipts_never_replace_prior_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            first = _receipt_path(workspace, "interrupt-download")
            first.touch()
            self.assertEqual(
                _receipt_path(workspace, "interrupt-download").name,
                "modern-containment-interrupt-download-002.json")

    @patch("qualify_modern_update_containment._release_identity")
    def test_release_plan_binds_every_staged_asset(self, identity):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary)
            manifest = {
                "version": "modern-v1",
                "packages": [{"file_name": INTERRUPT_PACKAGE}],
            }
            identity.return_value = (manifest, "c" * 64)
            (release / "modern-manifest.json").write_text("{}\n")
            (release / INTERRUPT_PACKAGE).write_bytes(b"package")
            (release / "qualification-attestation.sigstore.json").write_text(
                json.dumps({"bundle": True}) + "\n")
            plan, files = release_plan(release)
            self.assertEqual(plan["source_ref"], "refs/tags/modern-v1")
            self.assertEqual(
                [path.name for path in files],
                ["modern-manifest.json", INTERRUPT_PACKAGE])
            self.assertEqual(len(plan["assets"]), 2)

    def test_cached_attestation_is_bound_to_complete_stage_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / ATTESTATION_RECEIPT).write_text(
                json.dumps(self.plan) + "\n")
            verify_cached_plan(workspace, self.plan)
            changed = dict(self.plan, version="modern-v2")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_cached_plan(workspace, changed)


if __name__ == "__main__":
    unittest.main()
