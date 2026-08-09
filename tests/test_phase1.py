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
        for value in ("../main.py", "/tmp/app.py", "bad-name.py", "readme.txt"):
            with self.assertRaises(ValueError):
                self.state.validate_selected_app(value)


class BootStateTests(unittest.TestCase):
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
        updater.inspect_archive = lambda filename, target: []
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
        updater._tar_members = lambda path, target, extract=False: extracted.append(
            (Path(path).name, target, extract))
        updater._remove_tree = removed.append
        try:
            result = updater._install_verified_packages(
                {"installed_version": "old"}, "corrective", manifest, lambda message: None)
        finally:
            (updater._read_json, updater._write_json, updater._kind,
             updater._tar_members, updater._remove_tree) = old
        self.assertEqual(result, "corrective")
        self.assertEqual(extracted, [("next.tar", "/files/help", True)])
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

    def test_three_consecutive_unhealthy_boots_enter_recovery(self):
        self.assertEqual(
            self.namespace["_recovery_reason"]({"consecutive_failures": 3}),
            "repeated_boot_failure",
        )


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


if __name__ == "__main__":
    unittest.main()
