"""Qualification-only physical provisioning interruption helper tests."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_provision_interruptions import (  # noqa: E402
    ATTESTATION_RECEIPT, CHECKPOINTS, attestation_identity,
    command_checkpoint, next_receipt_path, verify_cached_attestation,
)


class ProvisionInterruptionHelperTests(unittest.TestCase):
    def test_checkpoint_inventory_covers_every_top_level_upload(self):
        self.assertEqual(
            [name for name in CHECKPOINTS if name.startswith("upload-")],
            [
                "upload-configs", "upload-defaults", "upload-device",
                "upload-files", "upload-ide", "upload-lib",
                "upload-recovery", "upload-state",
            ])

    def test_only_post_write_verify_is_selected(self):
        command = ["esptool", "verify-flash", "0x0", "firmware.bin"]
        first, count = command_checkpoint(command)
        second, count = command_checkpoint(command, count)
        self.assertIsNone(first)
        self.assertEqual(second, "verify-flash")
        self.assertEqual(count, 2)

    def test_firmware_commands_are_classified(self):
        self.assertEqual(command_checkpoint(
            ["esptool", "erase-flash"])[0], "erase-flash")
        self.assertEqual(command_checkpoint(
            ["esptool", "write-flash", "0x0", "firmware.bin"])[0],
            "write-flash")

    def test_placeholder_and_activation_copies_are_distinct(self):
        placeholder = [
            "mpremote", "connect", "COM3", "fs", "cp",
            "C:/private/provisioning-placeholder.py", ":/boot.py",
        ]
        active = [
            "mpremote", "connect", "COM3", "fs", "cp",
            "C:/private/prepared-image/boot.py", ":/boot.py",
        ]
        self.assertEqual(
            command_checkpoint(placeholder)[0], "placeholder-boot")
        self.assertEqual(command_checkpoint(active)[0], "activate-boot")

    def test_recursive_directory_copy_uses_source_name(self):
        command = [
            "mpremote.exe", "connect", "COM3", "fs", "--force",
            "--recursive", "cp", "C:/private/prepared-image/lib", ":/",
        ]
        self.assertEqual(command_checkpoint(command)[0], "upload-lib")

    def test_receipts_do_not_replace_prior_evidence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            self.assertEqual(
                next_receipt_path(workspace).name,
                "qualification-interruption.json")
            (workspace / "qualification-interruption.json").touch()
            self.assertEqual(
                next_receipt_path(workspace).name,
                "qualification-interruption-002.json")

    def test_cached_attestation_is_bound_to_candidate_and_source_ref(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "release"
            workspace = root / "workspace"
            release.mkdir()
            workspace.mkdir()
            (release / "checksums.json").write_text("{}\n")
            (release / "qualification-attestation.sigstore.json").write_text(
                "bundle\n")
            identity = attestation_identity(release, "refs/tags/modern-v1")
            (workspace / ATTESTATION_RECEIPT).write_text(
                json.dumps(identity) + "\n")
            self.assertEqual(
                verify_cached_attestation(
                    release, workspace, "refs/tags/modern-v1"),
                identity)
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_cached_attestation(
                    release, workspace, "refs/tags/modern-v2")


if __name__ == "__main__":
    unittest.main()
