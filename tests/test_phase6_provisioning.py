"""Host transaction tests for Phase 6 adult modern provisioning."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_modern_release import build_release  # noqa: E402
from provision_modern import (  # noqa: E402
    CommandTransport, FIRMWARE_SHA256, LEGACY_FIRMWARE,
    LEGACY_IDENTITY_REGIONS, MODERN_REPOSITORY, provision,
)


class DirectoryTransport:
    """A USB transport double whose device is a normal host directory."""

    def __init__(self, device: Path):
        self.device = device
        self.device.mkdir(parents=True, exist_ok=True)
        self.capture_count = 0
        self.source_validation_count = 0
        self.install_count = 0
        self.fail_install_once = False

    def capture(self, paths, destination):
        self.capture_count += 1
        for logical in paths:
            source = self.device / logical.lstrip("/")
            target = destination / logical.lstrip("/")
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def validate_source(self, mode, workspace):
        self.source_validation_count += 1
        if mode != "migrate":
            raise AssertionError("source validation is only valid for migration")

    def install(self, firmware, offset, image, expected_sha256):
        self.install_count += 1
        self.asserted_firmware = (firmware.name, offset, expected_sha256)
        for item in list(self.device.iterdir()):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        if self.fail_install_once:
            self.fail_install_once = False
            (self.device / "partial-upload.txt").write_text("interrupted\n")
            raise RuntimeError("simulated USB loss during filesystem upload")
        shutil.copytree(image, self.device, dirs_exist_ok=True)

    def release_is_healthy(self, version):
        update = self.device / "state/update.json"
        repos = json.loads(
            (self.device / "state/repos.json").read_text(encoding="utf-8"))
        tartlab = next(
            item for item in repos["list"] if item["name"] == "TartLab")
        return not update.exists() and tartlab["installed_version"] == version


class ModernProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        root = Path(cls.build.name)
        cls.dist = root / "dist"
        cls.dist.mkdir()
        (cls.dist / "boot.py").write_text("# boot gate\n", encoding="utf-8")
        (cls.dist / "main.py").write_text("print('modern')\n", encoding="utf-8")
        (cls.dist / "recovery").mkdir()
        (cls.dist / "recovery/recovery.py").write_text(
            "print('recovery')\n", encoding="utf-8")
        packages = root / "packages.json"
        packages.write_text(json.dumps([
            {
                "name": "rootfiles",
                "source": "dist/*",
                "target": "/",
                "clear_first": False,
                "ownership": "system",
            },
            {
                "name": "recovery",
                "source": "dist/recovery",
                "target": "/recovery",
                "clear_first": False,
                "ownership": "protected-recovery",
            },
        ]), encoding="utf-8")
        cls.release = root / "release"
        build_release(
            cls.dist, cls.release, "modern-v1.2.3",
            packages_path=packages, source_epoch=1234, allow_dirty=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def _complete_health(self, device):
        repos_path = device / "state/repos.json"
        repos = json.loads(repos_path.read_text(encoding="utf-8"))
        tartlab = next(
            item for item in repos["list"] if item["name"] == "TartLab")
        tartlab["installed_version"] = "modern-v1.2.3"
        repos_path.write_text(json.dumps(repos), encoding="utf-8")
        (device / "state/update.json").unlink()

    def test_legacy_profile_locks_runtime_identity_regions(self):
        profile = json.loads(
            (ROOT / "profiles/legacy-mp123.json").read_text(encoding="utf-8"))
        self.assertEqual(
            profile["firmware_compatibility"]["runtime_identity_regions"],
            LEGACY_IDENTITY_REGIONS)

    def test_clean_provisioning_uses_modern_selector_and_health_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            transport = DirectoryTransport(device)
            workspace = root / "workspace"

            result = provision(
                self.release, workspace, "clean", transport)

            self.assertEqual(result["stage"], "awaiting_health")
            self.assertEqual(transport.capture_count, 0)
            self.assertEqual(transport.asserted_firmware, (
                "tartlab-modern-v1.2.3.bin", "0x0", FIRMWARE_SHA256))
            self.assertIn(
                "from t_display_s3_pro_modern import *",
                (device / "device/hdwconfig.py").read_text(encoding="utf-8"))
            marker = json.loads(
                (device / "state/update.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["status"], "pending_health")
            self.assertEqual(marker["source_profile"], "clean")
            repos = json.loads(
                (device / "state/repos.json").read_text(encoding="utf-8"))
            tartlab = next(
                item for item in repos["list"] if item["name"] == "TartLab")
            self.assertEqual(tartlab["repo"], MODERN_REPOSITORY)
            self.assertEqual(tartlab["installed_version"], "unprovisioned")

            self._complete_health(device)
            completed = provision(
                self.release, workspace, "clean", transport, resume=True)
            self.assertEqual(completed["stage"], "complete")
            self.assertTrue(completed["healthy"])

    def test_legacy_migration_preserves_state_and_translates_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(
                ROOT / "tests/fixtures/legacy_mp123/layout", device,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
            original_settings = (device / "settings.json").read_bytes()
            original_logs = {
                path.name: path.read_bytes() for path in (device / "logs").iterdir()
                if path.is_file()
            }
            original_users = {
                path.name: path.read_bytes()
                for path in (device / "files/user").iterdir() if path.is_file()
            }
            transport = DirectoryTransport(device)
            workspace = root / "workspace"

            result = provision(
                self.release, workspace, "migrate", transport)

            self.assertEqual(result["stage"], "awaiting_health")
            self.assertEqual(transport.capture_count, 1)
            self.assertEqual(transport.source_validation_count, 1)
            self.assertEqual(
                (device / "state/settings.json").read_bytes(), original_settings)
            self.assertEqual({
                path.name: path.read_bytes()
                for path in (device / "state/logs").iterdir() if path.is_file()
            }, original_logs)
            self.assertEqual({
                path.name: path.read_bytes()
                for path in (device / "files/user").iterdir() if path.is_file()
            }, original_users)
            self.assertEqual(json.loads(
                (device / "state/selected_app.json").read_text(
                    encoding="utf-8"))["filename"], "selected_app.py")
            self.assertIn(
                "t_display_s3_pro_modern",
                (device / "device/hdwconfig.py").read_text(encoding="utf-8"))
            self.assertFalse((device / "settings.json").exists())
            repos = json.loads(
                (device / "state/repos.json").read_text(encoding="utf-8"))
            tartlab = next(
                item for item in repos["list"] if item["name"] == "TartLab")
            self.assertEqual(tartlab["installed_version"], "v0.13")
            self.assertEqual(tartlab["repo"], MODERN_REPOSITORY)
            journal_text = (workspace / "provisioning-journal.json").read_text(
                encoding="utf-8")
            self.assertNotIn("not-a-real-password", journal_text)
            self.assertTrue((workspace / "device-backup/settings.json").is_file())

    def test_interrupted_upload_resumes_from_the_unchanged_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            transport = DirectoryTransport(device)
            transport.fail_install_once = True
            workspace = root / "workspace"

            with self.assertRaisesRegex(RuntimeError, "simulated USB loss"):
                provision(self.release, workspace, "migrate", transport)
            journal = json.loads(
                (workspace / "provisioning-journal.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(journal["stage"], "backed_up")
            backup_settings = (
                workspace / "device-backup/settings.json").read_bytes()
            self.assertTrue((device / "partial-upload.txt").is_file())

            resumed = provision(
                self.release, workspace, "migrate", transport, resume=True)
            self.assertEqual(resumed["stage"], "awaiting_health")
            self.assertEqual(transport.capture_count, 1)
            self.assertEqual(transport.source_validation_count, 1)
            self.assertEqual(transport.install_count, 2)
            self.assertEqual(
                (workspace / "device-backup/settings.json").read_bytes(),
                backup_settings)
            self.assertFalse((device / "partial-upload.txt").exists())
            self.assertTrue((device / "recovery/recovery.py").is_file())

    def test_unsupported_legacy_selector_stops_before_erasure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            (device / "hdwconfig.py").write_text(
                "from another_board import *\n", encoding="utf-8")
            before = (device / "settings.json").read_bytes()
            transport = DirectoryTransport(device)

            with self.assertRaisesRegex(ValueError, "supported T-Display"):
                provision(
                    self.release, root / "workspace", "migrate", transport)
            self.assertEqual(transport.install_count, 0)
            self.assertEqual((device / "settings.json").read_bytes(), before)

    def test_changed_backup_cannot_be_used_to_resume_after_upload_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            transport = DirectoryTransport(device)
            transport.fail_install_once = True
            workspace = root / "workspace"
            with self.assertRaises(RuntimeError):
                provision(self.release, workspace, "migrate", transport)

            backup_settings = workspace / "device-backup/settings.json"
            backup_settings.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "backup differs"):
                provision(
                    self.release, workspace, "migrate", transport,
                    resume=True)
            self.assertEqual(transport.install_count, 1)

    def test_active_legacy_update_must_be_recovered_before_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            (device / "state").mkdir()
            (device / "state/update.json").write_text(
                '{"status":"failed"}\n', encoding="utf-8")
            transport = DirectoryTransport(device)
            with self.assertRaisesRegex(ValueError, "active update"):
                provision(
                    self.release, root / "workspace", "migrate", transport)
            self.assertEqual(transport.install_count, 0)

    def test_physical_transport_read_verifies_exact_legacy_firmware(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = CommandTransport("COM_TEST")
            commands = []
            transport._check_tools = lambda: None

            def exact_readback(command):
                commands.append(command)
                shutil.copy2(LEGACY_FIRMWARE, Path(command[-1]))
                return types.SimpleNamespace(stdout="")

            transport._run = exact_readback
            transport.validate_source("migrate", root)
            self.assertIn("read-flash", commands[0])
            self.assertFalse((root / "legacy-firmware-readback.bin").exists())

            def mutable_runtime_readback(command):
                target = Path(command[-1])
                shutil.copy2(LEGACY_FIRMWARE, target)
                with target.open("r+b") as stream:
                    stream.seek(0x9000)
                    stream.write(b"runtime NVS may differ")
                return types.SimpleNamespace(stdout="")

            transport._run = mutable_runtime_readback
            transport.validate_source("migrate", root)

            def wrong_readback(command):
                Path(command[-1]).write_bytes(b"wrong firmware")
                return types.SimpleNamespace(stdout="")

            transport._run = wrong_readback
            with self.assertRaisesRegex(ValueError, "supported exact legacy"):
                transport.validate_source("migrate", root)
            self.assertFalse((root / "legacy-firmware-readback.bin").exists())

    def test_physical_transport_activates_boot_files_only_after_full_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "image"
            (image / "state").mkdir(parents=True)
            (image / "recovery").mkdir()
            (image / "boot.py").write_text("# real boot\n", encoding="utf-8")
            (image / "main.py").write_text("# real main\n", encoding="utf-8")
            (image / "state/repos.json").write_text("{}\n", encoding="utf-8")
            (image / "recovery/recovery.py").write_text(
                "# recovery\n", encoding="utf-8")
            firmware = self.release / "tartlab-modern-v1.2.3.bin"
            transport = CommandTransport("COM_TEST")
            transport._check_tools = lambda: None
            commands = []
            transport._run = lambda command: (
                commands.append(command) or types.SimpleNamespace(stdout=""))

            transport.install(firmware, "0x0", image, FIRMWARE_SHA256)

            mpremote = commands[3:]
            self.assertTrue(mpremote[0][-1].endswith(":/boot.py"))
            self.assertIn("provisioning-placeholder.py", mpremote[0][-2])
            self.assertTrue(mpremote[1][-1].endswith(":/main.py"))
            state_upload = next(
                index for index, command in enumerate(mpremote)
                if command[-1] == ":/state")
            real_boot = next(
                index for index, command in enumerate(mpremote)
                if command[-1] == ":/boot.py" and
                command[-2].endswith("boot.py"))
            real_main = next(
                index for index, command in enumerate(mpremote)
                if command[-1] == ":/main.py" and
                command[-2].endswith("main.py"))
            self.assertLess(state_upload, real_boot)
            self.assertLess(real_boot, real_main)
            self.assertEqual(real_main, len(mpremote) - 1)
            self.assertFalse((root / "provisioning-placeholder.py").exists())


if __name__ == "__main__":
    unittest.main()
