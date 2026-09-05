import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
import shutil
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("ujson", json)
        cls.state = load_module("phase1_state", ROOT / "src/lib/tartlabutils/state.py")

    def configure_paths(self, root):
        state = self.state
        state.STATE_DIR = (root / "state").as_posix()
        state.DEVICE_DIR = (root / "device").as_posix()
        state.SETTINGS_FILE = (root / "state/settings.json").as_posix()
        state.REPOS_FILE = (root / "state/repos.json").as_posix()
        state.LOG_DIR = (root / "state/logs").as_posix()
        state.SELECTED_APP_FILE = (root / "state/selected_app.json").as_posix()
        state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
        state.BOOT_STATE_FILE = (root / "state/boot.json").as_posix()
        state.DEVICE_CONFIG_FILE = (root / "device/hdwconfig.py").as_posix()
        state.PHASE1_MIGRATION_FILE = (root / "state/phase1_migration.json").as_posix()
        state.PHASE1_TRANSITION_FILE = (root / "defaults/phase1_transition.json").as_posix()
        state.LEGACY_SETTINGS_FILE = (root / "settings.json").as_posix()
        state.LEGACY_REPOS_FILE = (root / "repos.json").as_posix()
        state.LEGACY_LOG_DIR = (root / "logs").as_posix()
        state.LEGACY_APP_FILE = (root / "app.py").as_posix()
        state.LEGACY_DEVICE_CONFIG_FILE = (root / "hdwconfig.py").as_posix()
        state.DEFAULT_DEVICE_CONFIG_FILE = (root / "defaults/hdwconfig.py").as_posix()

    def test_migration_preserves_state_and_never_overwrites_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.configure_paths(root)
            (root / "logs").mkdir()
            (root / "settings.json").write_text('{"secret":"synthetic"}')
            (root / "repos.json").write_text('{"list":[]}')
            (root / "logs/000004.log").write_text("legacy log")
            (root / "app.py").write_text("# generated\n# games/hello.py\nimport games.hello")
            (root / "hdwconfig.py").write_text("BOARD = 'legacy'")

            self.state.ensure_layout()
            self.assertEqual(json.loads((root / "state/settings.json").read_text())["secret"], "synthetic")
            self.assertEqual(self.state.get_selected_app(), "games/hello.py")
            self.assertEqual((root / "device/hdwconfig.py").read_text(), "BOARD = 'legacy'")
            self.assertEqual((root / "state/logs/000004.log").read_text(), "legacy log")

            (root / "settings.json").write_text('{"secret":"changed legacy"}')
            (root / "hdwconfig.py").write_text("BOARD = 'changed'")
            self.state.ensure_layout()
            self.assertEqual(json.loads((root / "state/settings.json").read_text())["secret"], "synthetic")
            self.assertEqual((root / "device/hdwconfig.py").read_text(), "BOARD = 'legacy'")

    def test_version_commit_waits_for_health(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.configure_paths(root)
            (root / "state").mkdir()
            repos = {"list": [{"name": "TartLab", "installed_version": "v0.13"}]}
            self.state.write_json(self.state.REPOS_FILE, repos)
            self.state.begin_update("TartLab", "v0.13", "v0.14")
            self.assertEqual(self.state.read_json(self.state.REPOS_FILE)["list"][0]["installed_version"], "v0.13")
            self.assertFalse(self.state.commit_pending_update())
            self.state.set_update_pending_health()
            self.assertTrue(self.state.commit_pending_update())
            self.assertEqual(self.state.read_json(self.state.REPOS_FILE)["list"][0]["installed_version"], "v0.14")
            self.assertFalse((root / "state/update.json").exists())

    def test_legacy_updater_version_commit_is_rolled_back_until_health(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.configure_paths(root)
            (root / "state").mkdir()
            (root / "defaults").mkdir()
            self.state.write_json(self.state.REPOS_FILE, {
                "list": [{"name": "TartLab", "installed_version": "v0.14"}],
            })
            self.state.write_json(self.state.PHASE1_TRANSITION_FILE, {
                "legacy_installed_versions": {"TartLab": "v0.13"},
            })
            self.state._migrate_legacy_version_commit()
            self.assertEqual(
                self.state.read_json(self.state.REPOS_FILE)["list"][0]["installed_version"], "v0.13")
            self.assertEqual(self.state.get_update_state()["status"], "pending_health")
            self.assertTrue(self.state.commit_pending_update())
            self.assertEqual(
                self.state.read_json(self.state.REPOS_FILE)["list"][0]["installed_version"], "v0.14")

    def test_selected_app_rejects_traversal(self):
        for value in (
                "../main.py", "/tmp/app.py", "bad-name.py",
                "testris.original.py", "readme.txt"):
            with self.assertRaises(ValueError):
                self.state.validate_selected_app(value)

    def test_selected_app_explains_safe_python_names(self):
        with self.assertRaises(ValueError) as caught:
            self.state.validate_selected_app("testris.original.py")
        message = str(caught.exception)
        self.assertEqual(message, "App names: letters, digits, _ only.")
        self.assertLessEqual(len(message), 75)
        self.assertNotIn("\n", message)


class MultipartValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package_name = "phase1_http"
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package
        sys.modules.setdefault("uasyncio", asyncio)
        response = types.ModuleType(package_name + ".response")
        response.HTTPResponse = type("HTTPResponse", (), {})
        response.sendHTTPResponse = lambda *args, **kwargs: None
        url = types.ModuleType(package_name + ".url")
        url.HTTPRequest = type("HTTPRequest", (), {})
        url.InvalidRequest = type("InvalidRequest", (Exception,), {})
        server = types.ModuleType(package_name + ".server")
        server.HTTPServerError = type("HTTPServerError", (Exception,), {})
        sys.modules[package_name + ".response"] = response
        sys.modules[package_name + ".url"] = url
        sys.modules[package_name + ".server"] = server
        cls.multipart = load_module(
            package_name + ".multipart",
            ROOT / "src/lib/ahttpserver/multipart.py")

    def test_upload_filename_is_validated_before_file_creation(self):
        boundary = b"tartlab-boundary"
        payload = (
            b"--" + boundary +
            b'\r\nContent-Disposition: form-data; name="file"; '
            b'filename="unsafe.app.py"\r\n\r\nprint(1)\r\n--' +
            boundary + b"--\r\n")

        class Reader:
            def __init__(self, content):
                self.content = content

            async def read(self, size):
                result = self.content[:size]
                self.content = self.content[size:]
                return result

        request = types.SimpleNamespace(header={
            b"Content-Type": b"multipart/form-data; boundary=" + boundary,
            b"Content-Length": str(len(payload)).encode(),
        })
        seen = []

        def reject(filename):
            seen.append(filename)
            raise ValueError("unsafe upload")

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "unsafe upload"):
                asyncio.run(self.multipart.handleMultipartUpload(
                    Reader(payload), None, request, folder,
                    validate_filename=reject))
            self.assertEqual(seen, ["unsafe.app.py"])
            self.assertEqual(list(Path(folder).iterdir()), [])


class BootStateTests(unittest.TestCase):
    def test_app_failure_survives_ide_health_and_clears_on_healthy_app(self):
        sys.modules.setdefault("ujson", json)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "state").mkdir()
            package = types.ModuleType("phase1_app_failure_runtime")
            package.__path__ = []
            sys.modules["phase1_app_failure_runtime"] = package
            state = load_module(
                "phase1_app_failure_runtime.state",
                ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = (root / "state").as_posix()
            state.BOOT_STATE_FILE = (root / "state/boot.json").as_posix()
            state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
            state.REPOS_FILE = (root / "state/repos.json").as_posix()
            bootstate = load_module(
                "phase1_app_failure_runtime.bootstate",
                ROOT / "src/lib/tartlabutils/bootstate.py")

            bootstate.mark_boot_route_started("APP")
            bootstate.mark_app_failed("student exception")
            bootstate.mark_boot_healthy("IDE")

            self.assertEqual(bootstate.get_app_failure(), "student exception")
            self.assertEqual(
                state.read_json(state.BOOT_STATE_FILE)["health"], "healthy")

            bootstate.mark_boot_route_started("APP")
            bootstate.mark_boot_healthy("APP")

            self.assertIsNone(bootstate.get_app_failure())

    def test_app_route_clears_recovery_streak_without_marking_health(self):
        sys.modules.setdefault("ujson", json)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "state").mkdir()
            package = types.ModuleType("phase1_app_route_runtime")
            package.__path__ = []
            sys.modules["phase1_app_route_runtime"] = package
            state = load_module(
                "phase1_app_route_runtime.state",
                ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = (root / "state").as_posix()
            state.BOOT_STATE_FILE = (root / "state/boot.json").as_posix()
            state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
            state.REPOS_FILE = (root / "state/repos.json").as_posix()
            bootstate = load_module(
                "phase1_app_route_runtime.bootstate",
                ROOT / "src/lib/tartlabutils/bootstate.py")
            state.write_json(state.BOOT_STATE_FILE, {
                "health": "starting",
                "consecutive_failures": 4,
                "error": "previous protected-startup failure",
            })
            state.write_json(state.REPOS_FILE, {
                "list": [{"name": "TartLab", "installed_version": "old"}],
            })
            state.begin_update("TartLab", "old", "candidate")
            state.set_update_pending_health()

            bootstate.mark_boot_route_started("APP")

            result = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(result["health"], "starting")
            self.assertEqual(result["mode"], "APP")
            self.assertEqual(result["consecutive_failures"], 0)
            self.assertNotIn("error", result)
            self.assertEqual(
                state.get_update_state()["status"], "pending_health")
            self.assertEqual(
                state.read_json(state.REPOS_FILE)["list"][0][
                    "installed_version"],
                "old")

    def test_healthy_boot_clears_previous_error(self):
        sys.modules.setdefault("ujson", json)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "state").mkdir()
            package = types.ModuleType("phase1_runtime")
            package.__path__ = []
            sys.modules["phase1_runtime"] = package
            state = load_module(
                "phase1_runtime.state", ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = (root / "state").as_posix()
            state.BOOT_STATE_FILE = (root / "state/boot.json").as_posix()
            state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
            state.REPOS_FILE = (root / "state/repos.json").as_posix()
            bootstate = load_module(
                "phase1_runtime.bootstate", ROOT / "src/lib/tartlabutils/bootstate.py")
            state.write_json(state.BOOT_STATE_FILE, {
                "health": "failed",
                "consecutive_failures": 1,
                "error": "previous failure",
            })

            bootstate.mark_boot_healthy("IDE")

            result = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(result["health"], "healthy")
            self.assertEqual(result["consecutive_failures"], 0)
            self.assertNotIn("error", result)

    def test_corrective_update_commit_clears_legacy_staging_trigger(self):
        sys.modules.setdefault("ujson", json)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_dir = root / "state"
            staging = root / "tmp"
            state_dir.mkdir()
            staging.mkdir()
            package = types.ModuleType("phase1_corrective_runtime")
            package.__path__ = []
            sys.modules["phase1_corrective_runtime"] = package
            state = load_module(
                "phase1_corrective_runtime.state",
                ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = state_dir.as_posix()
            state.BOOT_STATE_FILE = (state_dir / "boot.json").as_posix()
            state.UPDATE_STATE_FILE = (state_dir / "update.json").as_posix()
            state.REPOS_FILE = (state_dir / "repos.json").as_posix()
            bootstate = load_module(
                "phase1_corrective_runtime.bootstate",
                ROOT / "src/lib/tartlabutils/bootstate.py")
            bootstate.LEGACY_STAGING_MANIFEST = (
                staging / "manifest.json").as_posix()
            state.write_json(state.REPOS_FILE, {
                "list": [{"name": "TartLab", "installed_version": "v0.13"}],
            })
            state.begin_update("TartLab", "v0.13", "v0.14")
            state.set_update_pending_health()
            (staging / "manifest.json").write_text("[]")
            (staging / "tartlab.tar.part").write_bytes(b"partial")

            self.assertTrue(bootstate.mark_boot_healthy("IDE"))

            repos = state.read_json(state.REPOS_FILE)
            self.assertEqual(repos["list"][0]["installed_version"], "v0.14")
            self.assertFalse((staging / "manifest.json").exists())
            self.assertTrue((staging / "tartlab.tar.part").exists())


class DefaultSettingsTests(unittest.TestCase):
    def test_missing_settings_are_created_and_returned_before_ide_import(self):
        sys.modules.setdefault("ujson", json)
        sys.modules.setdefault("uio", io)
        package = types.ModuleType("phase1_defaults")
        package.__path__ = []
        sys.modules["phase1_defaults"] = package
        load_module("phase1_defaults.state", ROOT / "src/lib/tartlabutils/state.py")
        misc = load_module(
            "phase1_defaults.miscutils", ROOT / "src/lib/tartlabutils/miscutils.py")
        saved = []
        misc.generate_ap_name = lambda: "PyTestDevice10"
        misc.save_settings = lambda settings: saved.append(dict(settings))

        result = misc.default_settings()

        self.assertEqual(result, saved[0])
        self.assertEqual(result["hostname"], "tartlab")
        self.assertEqual(result["wifi_ssids"], [])
        self.assertIn("settings = default_settings()", (ROOT / "src/ide/ide.py").read_text())
        self.assertIn("settings = default_settings()", (ROOT / "src/main.py").read_text())


class RecoveryRetryTests(unittest.TestCase):
    def test_retry_clears_legacy_interrupted_update_trigger(self):
        previous_machine = sys.modules.get("machine")
        previous_network = sys.modules.get("network")
        sys.modules["machine"] = types.ModuleType("machine")
        sys.modules["network"] = types.ModuleType("network")
        try:
            recovery = load_module(
                "phase1_recovery_retry", ROOT / "src/recovery/recovery.py")
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                state = root / "state"
                staging = root / "tmp"
                state.mkdir()
                staging.mkdir()
                recovery.STATE_DIR = state.as_posix()
                recovery.BOOT_STATE = (state / "boot.json").as_posix()
                recovery.UPDATE_STATE = (state / "update.json").as_posix()
                recovery.RECOVERY_FLAG = (state / "recovery.flag").as_posix()
                recovery.LEGACY_STAGING_MANIFEST = (
                    staging / "manifest.json").as_posix()
                (state / "boot.json").write_text(json.dumps({
                    "health": "starting",
                    "consecutive_failures": 3,
                }))
                (state / "recovery.flag").write_text("")
                (staging / "manifest.json").write_text("[]")
                (staging / "tartlab.tar.part").write_bytes(b"partial")

                recovery._retry()

                boot = json.loads((state / "boot.json").read_text())
                self.assertEqual(boot["health"], "retrying")
                self.assertEqual(boot["consecutive_failures"], 0)
                self.assertFalse((state / "recovery.flag").exists())
                self.assertFalse((staging / "manifest.json").exists())
                self.assertTrue((staging / "tartlab.tar.part").exists())
        finally:
            if previous_machine is None:
                sys.modules.pop("machine", None)
            else:
                sys.modules["machine"] = previous_machine
            if previous_network is None:
                sys.modules.pop("network", None)
            else:
                sys.modules["network"] = previous_network


class ReleaseOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load_module("phase1_release", ROOT / "release.py")

    def test_package_map_excludes_protected_root_files(self):
        packages = json.loads((ROOT / "tartlab_packages.json").read_text())
        root = next(package for package in packages if package["name"] == "rootfiles")
        self.assertEqual(set(root["exclude"]), {"app.py", "hdwconfig.py"})
        self.assertFalse(root["clear_first"])
        recovery = next(package for package in packages if package["name"] == "recovery")
        self.assertFalse(recovery["clear_first"])
        for package in packages:
            self.assertNotIn(package["target"], ("/state", "/device", "/files/user", "/logs"))

    def test_archive_inventory_lists_paths_and_rejects_protected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "dist"
            output = root / "release"
            source.mkdir()
            output.mkdir()
            for name in ("main.py", "boot.py", "app.py", "hdwconfig.py"):
                (source / name).write_text(name)
            archive = self.release.create_tarfile(
                "rootfiles", str(source), True, str(output), ["app.py", "hdwconfig.py"])
            paths = self.release.archive_paths(archive, "/")
            self.assertEqual(paths, ["/boot.py", "/main.py"])
            self.release.validate_archive_ownership(paths)
            with self.assertRaises(ValueError):
                self.release.validate_archive_ownership(["/state/settings.json"])


class UpdaterFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("ujson", json)
        sys.modules.setdefault("uasyncio", asyncio)
        sys.modules.setdefault("uhashlib", __import__("hashlib"))
        sys.modules.setdefault("uos", os)
        sys.modules.setdefault("urequests", types.SimpleNamespace(get=None))
        sys.modules.setdefault("machine", types.SimpleNamespace(reset=lambda: None))
        package = types.ModuleType("phasepkg")
        package.__path__ = []
        sys.modules["phasepkg"] = package
        state = load_module("phasepkg.state", ROOT / "src/lib/tartlabutils/state.py")
        misc = types.ModuleType("phasepkg.miscutils")
        misc.file_exists = lambda path: 0
        misc.load_settings = lambda: {}
        misc.log = lambda message: None
        misc.log_exception = lambda error: None
        misc.mkdirs = lambda path: None
        misc.rmvdir = lambda path: None
        misc.save_settings = lambda settings: None
        sys.modules["phasepkg.miscutils"] = misc
        cls.updater = load_module("phasepkg.updater", ROOT / "src/lib/tartlabutils/updater.py")

    def test_manifest_rejects_protected_targets(self):
        with self.assertRaises(ValueError):
            self.updater.validate_manifest([{
                "file_name": "bad.tar", "sha256": "0", "target": "/files/user", "clear_first": True,
            }])

    def test_extraction_failure_propagates_without_success_log(self):
        updater = self.updater
        logs = []
        old = (updater.inspect_archive, updater.file_exists, updater.untar, updater.log)
        updater.inspect_archive = lambda *args: []
        updater.file_exists = lambda path: 0

        async def fail(*args, **kwargs):
            raise OSError("synthetic extraction failure")

        updater.untar = fail
        updater.log = logs.append
        try:
            with self.assertRaises(OSError):
                asyncio.run(updater.update_folder("package.tar", "/ide", False))
        finally:
            updater.inspect_archive, updater.file_exists, updater.untar, updater.log = old
        self.assertFalse(any("Success" in line for line in logs))

    def test_truncated_archive_fails_before_target_clear(self):
        updater = self.updater
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "truncated.tar"
            archive.write_bytes(b"not a complete tar header")
            removed = []
            old = (updater.file_exists, updater.rmvdir)
            updater.file_exists = lambda path: 2
            updater.rmvdir = removed.append
            try:
                with self.assertRaisesRegex(ValueError, "Truncated tar header"):
                    asyncio.run(updater.update_folder(str(archive), "/ide", True))
            finally:
                updater.file_exists, updater.rmvdir = old
            self.assertEqual(removed, [])

    def test_board_package_inspection_selects_only_provisioned_subtree(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "boards.tar"
            with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as output:
                for name in ("board_a/platform.py", "board_b/platform.py"):
                    content = name.encode("utf-8")
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    output.addfile(info, io.BytesIO(content))
            self.assertEqual(
                self.updater.inspect_archive(
                    str(archive), "/board", "board_b/"),
                ["/board/board_b/platform.py"],
            )

    def test_board_selection_manifest_is_confined_to_board_target(self):
        self.updater.validate_manifest([{
            "file_name": "board-support.tar", "sha256": "0",
            "target": "/board", "clear_first": True,
            "selection": "board-id-subtree",
            "selected_expanded_sizes": {"board_a": 123},
        }])
        with self.assertRaisesRegex(ValueError, "selection"):
            self.updater.validate_manifest([{
                "file_name": "bad.tar", "sha256": "0",
                "target": "/lib", "clear_first": True,
                "selection": "board-id-subtree",
                "selected_expanded_sizes": {"board_a": 123},
            }])

    def test_board_package_space_uses_only_selected_subtree(self):
        identity = self.updater._modern_board_identity
        self.updater._modern_board_identity = lambda repo: ("board_b", "a" * 64)
        try:
            required = self.updater._required_install_space([{
                "selection": "board-id-subtree",
                "selected_expanded_sizes": {"board_a": 1000, "board_b": 25},
            }], {})
        finally:
            self.updater._modern_board_identity = identity
        self.assertEqual(required, self.updater.FILESYSTEM_RESERVE_BYTES + 25)

    def test_board_package_space_requires_selected_board_metadata(self):
        identity = self.updater._modern_board_identity
        self.updater._modern_board_identity = lambda repo: ("board_b", "a" * 64)
        try:
            with self.assertRaisesRegex(ValueError, "missing for board identity"):
                self.updater._required_install_space([{
                    "selection": "board-id-subtree",
                    "selected_expanded_sizes": {"board_a": 1000},
                }], {})
        finally:
            self.updater._modern_board_identity = identity

    def test_board_package_rejects_invalid_selected_size_metadata(self):
        with self.assertRaisesRegex(ValueError, "sizes are invalid"):
            self.updater.validate_manifest([{
                "file_name": "board-support.tar", "sha256": "0",
                "target": "/board", "clear_first": True,
                "selection": "board-id-subtree",
                "selected_expanded_sizes": {"../board_a": 123},
            }])
        with self.assertRaisesRegex(ValueError, "sizes are invalid"):
            self.updater.validate_manifest([{
                "file_name": "board-support.tar", "sha256": "0",
                "target": "/board", "clear_first": True,
                "selection": "board-id-subtree",
                "selected_expanded_sizes": {"board_a": -1},
            }])

    def test_modern_update_cross_checks_protected_board_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            identity = Path(temporary) / "board.json"
            identity.write_text(
                json.dumps({"schema": 1, "board_id": "board_a"}),
                encoding="utf-8")
            old = self.updater.BOARD_IDENTITY_FILE
            self.updater.BOARD_IDENTITY_FILE = str(identity)
            try:
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    self.updater._modern_board_identity({
                        "board_id": "board_b",
                        "firmware_sha256": "a" * 64,
                    })
            finally:
                self.updater.BOARD_IDENTITY_FILE = old

    def test_modern_update_never_guesses_a_board_identity(self):
        with self.assertRaisesRegex(ValueError, "no board identity"):
            self.updater._modern_board_identity({
                "firmware_sha256": "a" * 64,
            })

    def test_recovery_boot_gate_is_preserved_after_phase1_migration(self):
        updater = self.updater
        self.assertEqual(updater.PHASE1_MIGRATION_FILE, "/state/phase1_migration.json")
        source = (ROOT / "src/lib/tartlabutils/updater.py").read_text()
        self.assertIn('target_path == "/boot.py"', source)
        self.assertIn('file_exists("/recovery/recovery.py")', source)


class RecoveryUpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("ujson", json)
        sys.modules.setdefault("uhashlib", __import__("hashlib"))
        sys.modules.setdefault("urequests", types.SimpleNamespace(get=None))
        cls.recovery_update = load_module(
            "phase1_recovery_update", ROOT / "src/recovery/recovery_update.py")

    def test_recovery_extractor_rejects_protected_and_traversal_paths(self):
        with self.assertRaises(ValueError):
            self.recovery_update._target_path("/", "app.py")
        with self.assertRaises(ValueError):
            self.recovery_update._target_path("/ide", "../state/settings.json")

    def test_recovery_board_package_selects_only_matching_subtree(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "boards.tar"
            with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as output:
                for name in ("board_a/platform.py", "board_b/platform.py"):
                    content = name.encode("utf-8")
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    output.addfile(info, io.BytesIO(content))
            self.assertEqual(
                self.recovery_update._tar_members(
                    str(archive), "/board", False, "board_a/"),
                ["/board/board_a/platform.py"],
            )

    def test_recovery_cross_checks_protected_board_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            identity = Path(temporary) / "board.json"
            identity.write_text(
                json.dumps({"schema": 1, "board_id": "board_a"}),
                encoding="utf-8")
            old = self.recovery_update.BOARD_IDENTITY_FILE
            self.recovery_update.BOARD_IDENTITY_FILE = str(identity)
            try:
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    self.recovery_update._modern_board_identity({
                        "board_id": "board_b",
                        "firmware_sha256": "a" * 64,
                    })
            finally:
                self.recovery_update.BOARD_IDENTITY_FILE = old

    def test_recovery_never_guesses_a_board_identity(self):
        with self.assertRaisesRegex(ValueError, "no board identity"):
            self.recovery_update._modern_board_identity({
                "firmware_sha256": "a" * 64,
            })

    def test_recovery_extractor_reads_verified_tar_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            archive = root / "package.tar"
            source.write_text("recovery payload")
            with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as tar:
                tar.add(source, arcname="module.py")
            paths = self.recovery_update._tar_members(str(archive), "/ide", False)
            self.assertEqual(paths, ["/ide/module.py"])

    def test_recovery_repo_lookup_uses_legacy_compatible_loop(self):
        repos = {"list": [
            {"name": "Other", "installed_version": "v1"},
            {"name": "TartLab", "installed_version": "v0.13"},
        ]}
        self.assertEqual(
            self.recovery_update._tartlab_repo(repos)["installed_version"], "v0.13")
        self.assertIsNone(self.recovery_update._tartlab_repo({"list": []}))

    def test_recovery_accepts_only_profile_bound_manifest_and_feed(self):
        updater = self.recovery_update
        repo = {
            "name": "TartLab",
            "repo": "tdhoward/TartLab-modern-releases",
            "installed_version": "modern-v1",
            "runtime_profile": "lvgl-modern",
            "manifest": "modern-manifest.json",
            "board_id": "board_a",
            "firmware_sha256": "b" * 64,
        }
        package = {
            "file_name": "rootfiles.tar", "sha256": "a" * 64,
            "target": "/", "clear_first": False,
        }
        document = {
            "schema": 1,
            "version": "modern-v2",
            "channel": {
                "repository": "tdhoward/TartLab-modern-releases",
                "manifest": "modern-manifest.json",
            },
            "compatibility": {
                "runtime_profile": "lvgl-modern",
                "firmware": {"sha256": "b" * 64},
            },
            "packages": [package],
        }
        self.assertEqual(
            updater._manifest_packages(document, repo, "modern-v2"),
            [package])

        matrix_repo = dict(repo)
        matrix_repo["board_id"] = "another_board"
        matrix_repo["firmware_sha256"] = "b" * 64
        matrix_document = json.loads(json.dumps(document))
        matrix_document["compatibility"]["boards"] = {
            "another_board": {"firmware": {"sha256": "b" * 64}},
        }
        self.assertEqual(
            updater._manifest_packages(
                matrix_document, matrix_repo, "modern-v2"),
            [package])
        wrong_board = dict(matrix_repo)
        wrong_board["board_id"] = "missing_board"
        with self.assertRaisesRegex(ValueError, "firmware identity"):
            updater._manifest_packages(
                matrix_document, wrong_board, "modern-v2")

        wrong_feed = dict(repo)
        wrong_feed["repo"] = "tdhoward/TartLab"
        with self.assertRaisesRegex(ValueError, "isolated modern feed"):
            updater._release_contract(wrong_feed)

        wrong_version = json.loads(json.dumps(document))
        wrong_version["version"] = "modern-v3"
        with self.assertRaisesRegex(ValueError, "version"):
            updater._manifest_packages(wrong_version, repo, "modern-v2")

        wrong_profile = json.loads(json.dumps(document))
        wrong_profile["compatibility"]["runtime_profile"] = "legacy-mp123"
        with self.assertRaisesRegex(ValueError, "runtime profile"):
            updater._manifest_packages(wrong_profile, repo, "modern-v2")

        wrong_firmware = json.loads(json.dumps(document))
        wrong_firmware["compatibility"]["firmware"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "firmware identity"):
            updater._manifest_packages(wrong_firmware, repo, "modern-v2")

    def test_recovery_modern_update_selects_packages_not_firmware(self):
        updater = self.recovery_update
        repo = {
            "name": "TartLab",
            "repo": "tdhoward/TartLab-modern-releases",
            "installed_version": "modern-v1",
            "runtime_profile": "lvgl-modern",
            "manifest": "modern-manifest.json",
            "board_id": "board_a",
            "firmware_sha256": "b" * 64,
        }
        package = {
            "file_name": "rootfiles.tar", "sha256": "a" * 64,
            "target": "/", "clear_first": False, "expanded_size": 1,
        }
        document = {
            "schema": 1,
            "version": "modern-v2",
            "channel": {
                "repository": "tdhoward/TartLab-modern-releases",
                "manifest": "modern-manifest.json",
            },
            "compatibility": {
                "runtime_profile": "lvgl-modern",
                "firmware": {"sha256": "b" * 64},
            },
            "packages": [package],
        }
        release = {
            "tag_name": "modern-v2",
            "assets": [
                {"name": "modern-manifest.json",
                 "browser_download_url": "manifest"},
                {"name": "rootfiles.tar", "browser_download_url": "package"},
                {"name": "tartlab-modern-v2.bin",
                 "browser_download_url": "firmware"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            downloaded = []
            installed = []

            def read_json(path, default):
                if path == updater.STATE_REPOS:
                    return {"list": [repo]}
                if path.endswith("modern-manifest.json"):
                    return document
                return default

            def download(url, path, expected_sha256=None):
                downloaded.append(url)
                Path(path).write_bytes(b"package")
                return True

            def install(tartlab, version, manifest, progress):
                installed.append((tartlab, version, manifest))
                return version

            old = (
                updater.TEMP_DIR, updater._read_json, updater._release,
                updater._download_verified, updater._kind, updater._mkdirs,
                updater._tar_members, updater._required_install_space,
                updater._free_space, updater._install_verified_packages,
            )
            updater.TEMP_DIR = Path(temp).as_posix()
            updater._read_json = read_json
            updater._release = lambda unused_repo: release
            updater._download_verified = download
            updater._kind = lambda path: 1 if path == updater.STATE_REPOS else (
                2 if Path(path).is_dir() else (1 if Path(path).is_file() else 0))
            updater._mkdirs = lambda path: os.makedirs(path, exist_ok=True)
            updater._tar_members = lambda *args: ["/main.py"]
            updater._required_install_space = lambda manifest, repo=None: 1
            updater._free_space = lambda: 1_000_000
            updater._install_verified_packages = install
            try:
                result = updater.update_to_latest(lambda message: None)
            finally:
                (
                    updater.TEMP_DIR, updater._read_json, updater._release,
                    updater._download_verified, updater._kind,
                    updater._mkdirs, updater._tar_members,
                    updater._required_install_space, updater._free_space,
                    updater._install_verified_packages,
                ) = old
            self.assertEqual(result, "modern-v2")
            self.assertEqual(downloaded, ["manifest", "package"])
            self.assertEqual(installed, [(repo, "modern-v2", [package])])

    def test_recovery_download_reuses_verified_file_and_promotes_atomically(self):
        updater = self.recovery_update
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "package.tar"
            payload = b"verified recovery package"
            target.write_bytes(payload)
            expected = __import__("hashlib").sha256(payload).hexdigest()
            calls = []
            old_download = updater._download

            def download(url, path):
                calls.append(url)
                Path(path).write_bytes(payload)

            updater._download = download
            try:
                self.assertFalse(updater._download_verified("local", str(target), expected))
                self.assertEqual(calls, [])
                target.write_bytes(b"stale")
                self.assertTrue(updater._download_verified("local", str(target), expected))
                self.assertEqual(target.read_bytes(), payload)
                self.assertFalse(Path(str(target) + ".part").exists())
            finally:
                updater._download = old_download

    def test_recovery_install_resumes_after_last_completed_package(self):
        updater = self.recovery_update
        marker = {
            "source": "recovery",
            "status": "installing",
            "repos": [{"name": "TartLab", "pending_version": "corrective"}],
            "completed_packages": ["done.tar"],
        }
        manifest = [
            {"file_name": "done.tar", "target": "/ide", "clear_first": False},
            {"file_name": "next.tar", "target": "/files/help", "clear_first": False},
            {"file_name": "recovery.tar", "target": "/recovery", "clear_first": False},
        ]
        writes = []
        extracted = []
        removed = []
        old = (
            updater._read_json, updater._write_json, updater._kind,
            updater._tar_members, updater._remove_tree,
        )
        updater._read_json = lambda path, default=None: marker
        updater._write_json = lambda path, value: writes.append(
            json.loads(json.dumps(value)))
        updater._kind = lambda path: 0
        updater._tar_members = lambda path, target, extract=False, \
                member_prefix=None: extracted.append(
                    (Path(path).name, target, extract, member_prefix))
        updater._remove_tree = removed.append
        try:
            result = updater._install_verified_packages(
                {"installed_version": "old"}, "corrective", manifest, lambda message: None)
        finally:
            (updater._read_json, updater._write_json, updater._kind,
             updater._tar_members, updater._remove_tree) = old
        self.assertEqual(result, "corrective")
        self.assertEqual(extracted, [("next.tar", "/files/help", True, None)])
        self.assertEqual(writes[-1]["status"], "pending_health")
        self.assertEqual(writes[-1]["completed_packages"], ["done.tar", "next.tar"])
        self.assertEqual(removed, [updater.TEMP_DIR])


class BootRecoveryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("ujson", json)
        source = (ROOT / "src/boot.py").read_text()
        definitions = source.split("_reason = _recovery_reason", 1)[0]
        cls.namespace = {}
        exec(compile(definitions, "boot.py", "exec"), cls.namespace)

    def test_failed_or_interrupted_install_enters_recovery(self):
        namespace = self.namespace
        original_read = namespace["_read"]
        namespace["_read"] = lambda path, default: (
            {"status": "failed"} if path == namespace["UPDATE_STATE"] else default)
        try:
            reason = namespace["_recovery_reason"]({"consecutive_failures": 0})
        finally:
            namespace["_read"] = original_read
        self.assertEqual(reason, "update_failed")

    def test_configured_consecutive_unhealthy_boots_enter_recovery(self):
        failure_limit = self.namespace["FAILURE_LIMIT"]
        self.assertIsNone(self.namespace["_recovery_reason"]({
            "consecutive_failures": failure_limit - 1,
        }))
        self.assertEqual(
            self.namespace["_recovery_reason"]({
                "consecutive_failures": failure_limit,
            }),
            "repeated_boot_failure",
        )

    def test_known_modern_board_blanks_backlight_during_early_boot(self):
        namespace = self.namespace
        original_loader = namespace["_load_board_config"]
        previous_machine = sys.modules.get("machine")
        calls = []

        class Pin:
            OUT = 1

            def __init__(self, number, mode, value=None):
                calls.append((number, mode, value))

        namespace["_load_board_config"] = lambda: {
            "id": "synthetic_modern_board",
            "pins": ({
                "type": "BACKLIGHT",
                "number": 48,
                "active_high": True,
            },),
        }
        sys.modules["machine"] = types.SimpleNamespace(Pin=Pin)
        try:
            pin = namespace["_blank_retained_display"]()
        finally:
            namespace["_load_board_config"] = original_loader
            if previous_machine is None:
                sys.modules.pop("machine", None)
            else:
                sys.modules["machine"] = previous_machine

        self.assertIsInstance(pin, Pin)
        self.assertEqual(calls, [(48, Pin.OUT, 0)])


class FixtureTests(unittest.TestCase):
    def test_fixture_is_sanitized_and_release_approved(self):
        fixture = ROOT / "tests/fixtures/legacy_mp123"
        metadata = json.loads((fixture / "metadata.json").read_text())
        settings = json.loads((fixture / "layout/settings.json").read_text())
        inventory = json.loads((fixture / "inventory.json").read_text())
        self.assertTrue(metadata["sanitized"])
        self.assertTrue(metadata["release_gate_ready"])
        self.assertEqual(metadata["source_capture"], "baseline_v013")
        self.assertEqual(metadata["board"]["revision"], "v1.1")
        self.assertEqual(
            metadata["firmware"]["sha256"],
            "41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212",
        )
        self.assertEqual(metadata["filesystem"]["capacity_bytes"], 6291456)
        self.assertEqual(metadata["filesystem"]["free_bytes"], 3923968)
        self.assertEqual(settings["wifi_ssids"], ["SYNTHETIC_CLASSROOM"])
        self.assertEqual(len(inventory), metadata["source_file_count"])
        self.assertNotIn("snapshot_manifest.json", {item["path"] for item in inventory})
        protected = [item for item in inventory if item["ownership"] == "protected-state"]
        self.assertTrue(protected)
        self.assertTrue(all("sha256" not in item for item in protected))

    def test_legacy_fixture_survives_release_application_and_interruption(self):
        fixture = ROOT / "tests/fixtures/legacy_mp123/layout"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            device = root / "device_fs"
            staging = root / "dist"
            archives = root / "archives"
            shutil.copytree(fixture, device)
            staging.mkdir()
            archives.mkdir()
            for name in ("main.py", "boot.py", "app.py", "hdwconfig.py"):
                source = ROOT / "src" / name
                shutil.copy2(source, staging / name)
            protected_paths = [
                "app.py", "hdwconfig.py", "settings.json", "repos.json", "logs", "files/user",
            ]

            def snapshot():
                result = {}
                for relative in protected_paths:
                    path = device / relative
                    if path.is_file():
                        result[relative] = path.read_bytes()
                    elif path.is_dir():
                        for child in sorted(item for item in path.rglob("*") if item.is_file()):
                            result[child.relative_to(device).as_posix()] = child.read_bytes()
                return result

            before = snapshot()
            release = load_module("phase1_fixture_release", ROOT / "release.py")
            root_archive = release.create_tarfile(
                "rootfiles", str(staging), True, str(archives), ["app.py", "hdwconfig.py"])
            release.validate_archive_ownership(release.archive_paths(root_archive, "/"))
            with tarfile.open(root_archive) as archive:
                archive.extractall(device)
            shutil.copytree(ROOT / "src/recovery", device / "recovery")
            (device / "state").mkdir()
            (device / "state/update.json").write_text('{"status":"installing"}')

            self.assertEqual(snapshot(), before)
            self.assertTrue((device / "boot.py").is_file())
            self.assertTrue((device / "recovery/recovery.py").is_file())
            self.assertTrue((device / "recovery/recovery_update.py").is_file())


class PhysicalHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_module(
            "phase1_device_helper", ROOT / "tools/phase1_device.py")

    def test_raw_repl_entry_retries_a_slow_application_teardown(self):
        class Serial:
            def __init__(self):
                self.writes = []
                self.resets = 0

            def write(self, value):
                self.writes.append(value)

            def reset_input_buffer(self):
                self.resets += 1

        repl = self.helper.RawRepl.__new__(self.helper.RawRepl)
        repl.serial = Serial()
        repl.timeout = 10
        with mock.patch.object(
                repl, "_read_until",
                side_effect=[TimeoutError("slow teardown"), b"prompt"]):
            repl.enter()

        self.assertEqual(repl.serial.writes, [
            b"\r\x03\x03", b"\r\x01",
            b"\r\x03\x03", b"\r\x01",
        ])
        self.assertEqual(repl.serial.resets, 2)

    def test_ota_helper_selects_modern_object_manifest_explicitly(self):
        captured = {}

        class Repl:
            def exec(self, code, timeout):
                captured["code"] = code
                captured["timeout"] = timeout
                return b""

            def close(self):
                captured["closed"] = True

        original_connect = self.helper.connect
        original_stdout = self.helper.sys.stdout
        self.helper.connect = lambda unused_args: Repl()
        self.helper.sys.stdout = types.SimpleNamespace(buffer=io.BytesIO())
        try:
            self.helper.ota_install(types.SimpleNamespace(
                base_url="http://192.0.2.1:8765/capability/",
                version="modern-v1.2.3",
                manifest="modern-manifest.json",
                timeout=30,
            ))
        finally:
            self.helper.connect = original_connect
            self.helper.sys.stdout = original_stdout

        self.assertIn("MANIFEST_NAME = 'modern-manifest.json'", captured["code"])
        self.assertIn("document.get('packages')", captured["code"])
        self.assertIn("BASE = 'http://192.0.2.1:8765/capability'", captured["code"])
        self.assertEqual(captured["timeout"], 300)
        self.assertTrue(captured["closed"])

    def test_ota_parser_keeps_legacy_manifest_as_default(self):
        args = self.helper.parser().parse_args([
            "ota-install", "--base-url", "http://192.0.2.1:8765",
        ])
        self.assertEqual(args.manifest, "manifest.json")

    def test_recovery_power_signal_restores_runtime_import_paths(self):
        captured = {}

        class Repl:
            def exec(self, code, timeout):
                captured["code"] = code
                captured["timeout"] = timeout
                return b""

            def close(self):
                captured["closed"] = True

        original_connect = self.helper.connect
        original_stdout = self.helper.sys.stdout
        self.helper.connect = lambda unused_args: Repl()
        self.helper.sys.stdout = types.SimpleNamespace(buffer=io.BytesIO())
        try:
            self.helper.recovery_install(types.SimpleNamespace(
                base_url="http://192.0.2.1:8765/candidate/",
                version="v1.2",
                signal_package="tartlabutils.tar",
                timeout=30,
            ))
        finally:
            self.helper.connect = original_connect
            self.helper.sys.stdout = original_stdout

        code = captured["code"]
        self.assertIn("for path in ('/lib/pydevices', '/configs')", code)
        self.assertLess(
            code.index("for path in ('/lib/pydevices', '/configs')"),
            code.index("from hdwconfig import display_drv"))
        self.assertEqual(captured["timeout"], 300)
        self.assertTrue(captured["closed"])

    def test_recovery_retry_and_update_status_commands_are_explicit(self):
        retry = self.helper.parser().parse_args(["recovery-retry"])
        status = self.helper.parser().parse_args(["update-status"])
        self.assertIs(retry.func, self.helper.recovery_retry)
        self.assertIs(status.func, self.helper.update_status)

        source = (ROOT / "tools/phase1_device.py").read_text()
        self.assertIn("recovery._retry()", source)
        self.assertIn("'update': read('/state/update.json', None)", source)
        self.assertIn("'recovery_stage_kind': kind('/tmp/recovery')", source)
        self.assertIn(
            "'qualification_stage_kind': kind('/qualification/modern-update')",
            source)

    def test_recovery_browser_helper_uses_modern_candidate_adapter(self):
        args = self.helper.parser().parse_args([
            "recovery-browser",
            "--base-url", "http://192.0.2.1:8765/candidate/",
            "--version", "modern-v1.2.3",
            "--manifest", "modern-manifest.json",
            "--stage-before-browser",
        ])
        code = self.helper._recovery_browser_code(args)

        self.assertIn("BASE = 'http://192.0.2.1:8765/candidate'", code)
        self.assertIn("VERSION = 'modern-v1.2.3'", code)
        self.assertIn("MANIFEST_NAME = 'modern-manifest.json'", code)
        self.assertIn("STAGE_BEFORE_BROWSER = True", code)
        self.assertIn("packages = document.get('packages')", code)
        self.assertIn("recovery_update._release = lambda unused_repo: release", code)
        self.assertIn(
            "recovery_update.update_to_latest = recovery_update.resume_staged_update", code)
        self.assertIn("recovery.run('qualification_corrective_update')", code)
        self.assertIs(args.func, self.helper.recovery_browser)


if __name__ == "__main__":
    unittest.main()
