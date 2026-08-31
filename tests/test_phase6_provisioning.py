"""Host transaction tests for Phase 6 adult modern provisioning."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_modern_release import build_release  # noqa: E402
from provision_modern import (  # noqa: E402
    CommandTransport, FIRMWARE_SHA256, LEGACY_FIRMWARE,
    LEGACY_IDENTITY_REGIONS, LEGACY_READ_CHUNK_SIZE, MODERN_REPOSITORY,
    _verify_attestations, provision,
)


class DirectoryTransport:
    """A USB transport double whose device is a normal host directory."""

    def __init__(self, device: Path):
        self.device = device
        self.device.mkdir(parents=True, exist_ok=True)
        self.capture_count = 0
        self.source_validation_count = 0
        self.install_count = 0
        self.reuse_matching_firmware = []
        self.fail_install_once = False
        self.fail_source_validation_once = False

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
        if self.fail_source_validation_once:
            self.fail_source_validation_once = False
            raise RuntimeError("simulated ROM loader transition")

    def install(self, firmware, offset, image, expected_sha256, *,
                reuse_matching_firmware=False):
        self.install_count += 1
        self.reuse_matching_firmware.append(reuse_matching_firmware)
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
    def test_provisioning_accepts_exactly_one_bound_attestation_purpose(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary)
            with self.assertRaisesRegex(ValueError, "exactly one"):
                _verify_attestations(release, "refs/tags/modern-v1.2.3")

            qualification = release / "qualification-attestation.sigstore.json"
            qualification.write_text("{}\n", encoding="utf-8")
            with mock.patch("provision_modern.subprocess.run") as run:
                _verify_attestations(release, "refs/tags/modern-v1.2.3")
            self.assertIn("qualification", run.call_args.args[0])

            qualification.unlink()
            (release / "release-attestation.sigstore.json").write_text(
                "{}\n", encoding="utf-8")
            with mock.patch("provision_modern.subprocess.run") as run:
                _verify_attestations(release, "refs/tags/modern-v1.2.3")
            self.assertIn("release", run.call_args.args[0])

            qualification.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                _verify_attestations(release, "refs/tags/modern-v1.2.3")

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
        (cls.dist / "defaults/user").mkdir(parents=True)
        (cls.dist / "defaults/user/hello.py").write_text(
            "print('clean hello')\n", encoding="utf-8")
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
            {
                "name": "defaults",
                "source": "dist/defaults",
                "target": "/defaults",
                "clear_first": True,
                "ownership": "system",
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
            self.assertEqual(result["board_id"], "lilygo_t_display_s3_pro")
            self.assertEqual(transport.capture_count, 0)
            self.assertEqual(transport.asserted_firmware, (
                "tartlab-modern-v1.2.3.bin", "0x0", FIRMWARE_SHA256))
            self.assertEqual(transport.reuse_matching_firmware, [False])
            self.assertIn(
                "from t_display_s3_pro_modern import *",
                (device / "device/hdwconfig.py").read_text(encoding="utf-8"))
            self.assertEqual(json.loads(
                (device / "device/board.json").read_text(encoding="utf-8")), {
                    "schema": 1,
                    "board_id": "lilygo_t_display_s3_pro",
                })
            self.assertEqual(
                (device / "files/user/hello.py").read_text(encoding="utf-8"),
                "print('clean hello')\n")
            marker = json.loads(
                (device / "state/update.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["status"], "pending_health")
            self.assertEqual(marker["source_profile"], "clean")
            repos = json.loads(
                (device / "state/repos.json").read_text(encoding="utf-8"))
            tartlab = next(
                item for item in repos["list"] if item["name"] == "TartLab")
            self.assertEqual(tartlab["repo"], MODERN_REPOSITORY)
            self.assertEqual(tartlab["firmware_sha256"], FIRMWARE_SHA256)
            self.assertEqual(
                tartlab["board_id"], "lilygo_t_display_s3_pro")
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
            original_app = (device / "app.py").read_bytes()
            original_selector = (device / "hdwconfig.py").read_bytes()
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
            self.assertEqual((device / "app.py").read_bytes(), original_app)
            self.assertEqual(
                (device / "hdwconfig.py").read_bytes(), original_selector)
            self.assertFalse((device / "settings.json").exists())
            repos = json.loads(
                (device / "state/repos.json").read_text(encoding="utf-8"))
            tartlab = next(
                item for item in repos["list"] if item["name"] == "TartLab")
            self.assertEqual(tartlab["installed_version"], "v0.13")
            self.assertEqual(tartlab["repo"], MODERN_REPOSITORY)
            self.assertEqual(tartlab["firmware_sha256"], FIRMWARE_SHA256)
            self.assertEqual(
                tartlab["board_id"], "lilygo_t_display_s3_pro")
            journal_text = (workspace / "provisioning-journal.json").read_text(
                encoding="utf-8")
            self.assertNotIn("not-a-real-password", journal_text)
            self.assertTrue((workspace / "device-backup/settings.json").is_file())

    def test_unqualified_board_is_rejected_before_workspace_or_device_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            device.mkdir()
            sentinel = device / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            workspace = root / "workspace"
            with self.assertRaisesRegex(ValueError, "not qualified"):
                provision(
                    self.release, workspace, "clean",
                    DirectoryTransport(device),
                    board_id="elecrow_dle06235b")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertFalse(workspace.exists())

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
                transport.reuse_matching_firmware, [False, True])
            self.assertEqual(
                (workspace / "device-backup/settings.json").read_bytes(),
                backup_settings)
            self.assertFalse((device / "partial-upload.txt").exists())
            self.assertTrue((device / "recovery/recovery.py").is_file())

    def test_rom_transition_reuses_complete_content_addressed_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            transport = DirectoryTransport(device)
            transport.fail_source_validation_once = True
            workspace = root / "workspace"

            with self.assertRaisesRegex(
                    RuntimeError, "simulated ROM loader transition"):
                provision(self.release, workspace, "migrate", transport)

            journal = json.loads(
                (workspace / "provisioning-journal.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(journal["stage"], "backup_captured")
            self.assertTrue((workspace / "device-backup/settings.json").is_file())
            self.assertEqual(transport.capture_count, 1)

            resumed = provision(
                self.release, workspace, "migrate", transport, resume=True)
            self.assertEqual(resumed["stage"], "awaiting_health")
            self.assertEqual(transport.capture_count, 1)
            self.assertEqual(transport.source_validation_count, 2)

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

    def test_source_below_v013_floor_stops_before_erasure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            repos_path = device / "repos.json"
            repos = json.loads(repos_path.read_text(encoding="utf-8"))
            repos["list"][0]["installed_version"] = "v0.12"
            repos_path.write_text(json.dumps(repos), encoding="utf-8")
            transport = DirectoryTransport(device)

            with self.assertRaisesRegex(ValueError, "older than the v0.13"):
                provision(
                    self.release, root / "workspace", "migrate", transport)
            self.assertEqual(transport.install_count, 0)
            journal = json.loads((
                root / "workspace/provisioning-journal.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(journal["stage"], "verified")

    def test_canonical_legacy_layout_at_newer_stable_version_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "device"
            shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
            (device / "state").mkdir()
            (device / "device").mkdir()
            repos = json.loads((device / "repos.json").read_text(encoding="utf-8"))
            repos["list"][0]["installed_version"] = "v0.14"
            (device / "state/repos.json").write_text(
                json.dumps(repos), encoding="utf-8")
            shutil.copy2(
                device / "hdwconfig.py", device / "device/hdwconfig.py")
            transport = DirectoryTransport(device)
            workspace = root / "workspace"

            result = provision(
                self.release, workspace, "migrate", transport)

            self.assertEqual(result["stage"], "awaiting_health")
            journal = json.loads((
                workspace / "provisioning-journal.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(journal["source"]["layout"], "canonical-v1")
            self.assertEqual(journal["source"]["installed_version"], "v0.14")

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

            def readback_from(image, command):
                commands.append(command)
                offset = int(command[-3], 0)
                size = int(command[-2])
                with image.open("rb") as stream:
                    stream.seek(offset)
                    Path(command[-1]).write_bytes(stream.read(size))
                return types.SimpleNamespace(stdout="")

            def exact_readback(command):
                return readback_from(LEGACY_FIRMWARE, command)

            transport._run = exact_readback
            transport.validate_source("migrate", root)
            self.assertTrue(commands)
            self.assertTrue(all("read-flash" in command for command in commands))
            self.assertTrue(all("--no-stub" in command for command in commands))
            self.assertTrue(all(
                command[command.index("--before") + 1] == "no-reset"
                and command[command.index("--after") + 1] == "no-reset"
                for command in commands))
            self.assertTrue(all(
                int(command[-2]) <= LEGACY_READ_CHUNK_SIZE
                for command in commands))
            self.assertEqual(
                sum(int(command[-2]) for command in commands),
                sum(region["size"] for region in LEGACY_IDENTITY_REGIONS))
            self.assertFalse(list(root.glob("legacy-firmware-readback-*.bin")))

            mutable_firmware = root / "mutable-runtime.bin"
            shutil.copy2(LEGACY_FIRMWARE, mutable_firmware)
            with mutable_firmware.open("r+b") as stream:
                stream.seek(0x9000)
                stream.write(b"runtime NVS may differ")

            def mutable_runtime_readback(command):
                return readback_from(mutable_firmware, command)

            transport._run = mutable_runtime_readback
            transport.validate_source("migrate", root)

            def wrong_readback(command):
                Path(command[-1]).write_bytes(b"\0" * int(command[-2]))
                return types.SimpleNamespace(stdout="")

            transport._run = wrong_readback
            with self.assertRaisesRegex(ValueError, "supported exact legacy"):
                transport.validate_source("migrate", root)
            self.assertFalse(list(root.glob("legacy-firmware-readback-*.bin")))

    @mock.patch("provision_modern.RawRepl")
    def test_physical_capture_uses_one_session_without_soft_resets(self, repl):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = CommandTransport("COM6")
            instance = repl.return_value
            instance.exec.side_effect = (
                b'PHASE1_INVENTORY=[["/device/hdwconfig.py",4],'
                b'["/settings.json",3],["/unprotected.txt",5]]\r\n',
                base64.b64encode(b"test") + b"\r\n",
                base64.b64encode(b"{}\n") + b"\r\n",
            )
            transport.capture(
                ("/device", "/settings.json", "/missing"), root)

            repl.assert_called_once_with("COM6", timeout=20)
            instance.enter.assert_called_once_with()
            instance.close.assert_called_once_with()
            self.assertEqual(instance.exec.call_count, 3)
            self.assertEqual((root / "device/hdwconfig.py").read_bytes(), b"test")
            self.assertEqual((root / "settings.json").read_bytes(), b"{}\n")
            self.assertFalse((root / "unprotected.txt").exists())

    @mock.patch("provision_modern.time.sleep")
    def test_physical_transport_activates_boot_files_only_after_full_upload(
            self, sleep):
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
            transport._run = lambda command, check=True: (
                commands.append(command) or types.SimpleNamespace(
                    stdout="", returncode=0))

            transport.install(firmware, "0x0", image, FIRMWARE_SHA256)

            self.assertIn("verify-flash", commands[0])
            self.assertIn("erase-flash", commands[1])
            self.assertIn("write-flash", commands[2])
            self.assertIn("verify-flash", commands[3])
            self.assertIn("watchdog-reset", commands[4])
            sleep.assert_called_once_with(3)
            mpremote = commands[5:]
            self.assertLess(mpremote[0].index("--force"), mpremote[0].index("cp"))
            self.assertTrue(mpremote[0][-1].endswith(":/boot.py"))
            self.assertIn("provisioning-placeholder.py", mpremote[0][-2])
            self.assertTrue(mpremote[1][-1].endswith(":/main.py"))
            state_upload = next(
                index for index, command in enumerate(mpremote)
                if command[-2].endswith("state"))
            self.assertEqual(mpremote[state_upload][-1], ":/")
            self.assertLess(
                mpremote[state_upload].index("--recursive"),
                mpremote[state_upload].index("cp"))
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

    @mock.patch("provision_modern.time.sleep")
    def test_physical_transport_reuses_verified_firmware_on_resume(self, sleep):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "image"
            image.mkdir()
            (image / "boot.py").write_text("# boot\n", encoding="utf-8")
            (image / "main.py").write_text("# main\n", encoding="utf-8")
            firmware = self.release / "tartlab-modern-v1.2.3.bin"
            transport = CommandTransport("COM_TEST")
            transport._check_tools = lambda: None
            commands = []
            transport._run = lambda command, check=True: (
                commands.append(command) or
                types.SimpleNamespace(stdout="", returncode=0))

            transport.install(
                firmware, "0x0", image, FIRMWARE_SHA256,
                reuse_matching_firmware=True)

            flattened = [part for command in commands for part in command]
            self.assertNotIn("erase-flash", flattened)
            self.assertNotIn("write-flash", flattened)
            self.assertIn("verify-flash", commands[0])
            self.assertIn("watchdog-reset", commands[1])
            sleep.assert_called_once_with(3)
            self.assertEqual(commands[2][-1], ":/boot.py")

    @mock.patch("provision_modern.time.sleep")
    @mock.patch("provision_modern.RawRepl")
    def test_physical_health_check_brackets_raw_state_read_with_safe_boots(
            self, repl, sleep):
        transport = CommandTransport("COM_TEST")
        commands = []
        transport._run = lambda command, check=True: (
            commands.append(command) or
            types.SimpleNamespace(stdout="", returncode=0))
        instance = repl.return_value
        instance.exec.side_effect = (
            b'TARTLAB_HEALTH={"version":"modern-v1.2.3",'
            b'"update":null}\r\n',
            b"",
        )

        self.assertTrue(transport.release_is_healthy("modern-v1.2.3"))

        self.assertEqual(len(commands), 2)
        self.assertIn("watchdog-reset", commands[0])
        self.assertEqual(commands[0], commands[1])
        repl.assert_called_once_with("COM_TEST", timeout=20)
        instance.enter.assert_called_once_with()
        instance.close.assert_called_once_with()
        self.assertEqual(instance.exec.call_count, 2)
        self.assertIn("recovery._retry()", instance.exec.call_args_list[1].args[0])
        sleep.assert_called_once_with(3)

    @mock.patch("provision_modern.time.sleep")
    @mock.patch("provision_modern.RawRepl")
    def test_physical_health_check_waits_for_native_usb_reenumeration(
            self, repl, sleep):
        transport = CommandTransport("COM_TEST")
        transport._run = lambda command, check=True: types.SimpleNamespace(
            stdout="", returncode=0)
        instance = mock.Mock()
        instance.exec.side_effect = (
            b'TARTLAB_HEALTH={"version":"modern-v1.2.3",'
            b'"update":null}\r\n',
            b"",
        )
        repl.side_effect = (OSError("port absent"), instance)

        self.assertTrue(transport.release_is_healthy("modern-v1.2.3"))

        self.assertEqual(repl.call_count, 2)
        self.assertEqual(
            sleep.call_args_list, [mock.call(3), mock.call(0.2)])
        instance.enter.assert_called_once_with()
        instance.close.assert_called_once_with()

    @mock.patch("provision_modern.time.sleep")
    @mock.patch("provision_modern.RawRepl")
    def test_physical_health_check_retries_early_unwritable_usb_handle(
            self, repl, sleep):
        transport = CommandTransport("COM_TEST")
        transport._run = lambda command, check=True: types.SimpleNamespace(
            stdout="", returncode=0)
        early = mock.Mock()
        early.enter.side_effect = OSError("endpoint not writable")
        ready = mock.Mock()
        ready.exec.side_effect = (
            b'TARTLAB_HEALTH={"version":"modern-v1.2.3",'
            b'"update":null}\r\n',
            b"",
        )
        repl.side_effect = (early, ready)

        self.assertTrue(transport.release_is_healthy("modern-v1.2.3"))

        early.close.assert_called_once_with()
        ready.enter.assert_called_once_with()
        ready.close.assert_called_once_with()
        self.assertEqual(
            sleep.call_args_list, [mock.call(3), mock.call(0.2)])


if __name__ == "__main__":
    unittest.main()
