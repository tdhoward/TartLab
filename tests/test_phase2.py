import asyncio
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.modules.setdefault("ujson", json)

import makedist
import release
from check_legacy_release import check as check_legacy_release
from release_utils import file_inventory
from vendor_lock import check_lock


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def copy_source_dist(target):
    source = ROOT / "src"
    target.mkdir()
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    for relative in ("files", "configs", "defaults", "recovery", "lib"):
        shutil.copytree(source / relative, target / relative)
    (target / "ide/www").mkdir(parents=True)
    for path in (source / "ide").iterdir():
        if path.is_file():
            shutil.copy2(path, target / "ide" / path.name)

    # Webpack output is intentionally ignored. Supply deterministic placeholders
    # for this host-side packaging fixture; CI exercises the real npm build.
    baseline = json.loads(
        (ROOT / "tests/fixtures/legacy_mp123/inventory.json").read_text())
    for item in baseline:
        relative = item.get("path", "")
        if item.get("ownership") != "update-managed" or not relative.startswith("ide/www/"):
            continue
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("phase2-web-placeholder:" + relative).encode())


class VendorProvenanceTests(unittest.TestCase):
    def test_vendor_source_and_deployed_fixture_match_content_lock(self):
        lock = check_lock()
        self.assertEqual(lock["schema"], 1)
        self.assertEqual(lock["provenance"]["status"], "incomplete-historical-snapshot")
        self.assertEqual(lock["deployed_legacy_mp123"]["file_count"], 145)
        self.assertEqual(lock["deployed_legacy_mp123"]["expanded_bytes"], 729986)


class DistributionBuildTests(unittest.TestCase):
    def test_file_inventory_uses_platform_independent_path_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("upper\n")
            (root / "a.py").write_text("lower\n")
            paths = [item["path"] for item in file_inventory(root)]
            self.assertEqual(paths, sorted(paths))

    def test_file_inventory_normalizes_extensionless_license_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "LICENSE").write_bytes(b"line\r\n")
            item = file_inventory(root, normalize_source_text=True)[0]
            self.assertEqual(item["size"], len(b"line\n"))
            self.assertEqual(
                item["sha256"], hashlib.sha256(b"line\n").hexdigest())

    def make_source(self, root):
        source = root / "src"
        for relative in (
                "files/help", "configs", "defaults", "recovery", "lib/pydevices",
                "ide/www/dist"):
            (source / relative).mkdir(parents=True)
        (source / "main.py").write_text("print('main')\n")
        (source / "files/help/help.py").write_text("VALUE = 1\n")
        (source / "configs/board.py").write_text("BOARD = 1\n")
        (source / "defaults/default.json").write_text("{}\n")
        (source / "recovery/recovery.py").write_text("def run(): pass\n")
        (source / "lib/pydevices/driver.py").write_text("VALUE = 2\n")
        (source / "ide/ide.py").write_text("def main(): pass\n")
        (source / "ide/www/dist/index.html").write_text("x" * 4096)
        return source

    def test_clean_build_rejects_stale_output_and_has_deterministic_gzip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root)
            output = root / "output"
            output.mkdir()
            (output / "stale.py").write_text("stale")
            with self.assertRaises(FileExistsError):
                makedist.build_distribution(
                    source, output, minify_python=False, build_web=False, epoch=123)
            makedist.build_distribution(
                source, output, clean=True, minify_python=False,
                build_web=False, epoch=123)
            self.assertFalse((output / "stale.py").exists())
            gzip_path = output / "ide/www/index.html.gz"
            self.assertTrue(gzip_path.is_file())
            self.assertEqual(int.from_bytes(gzip_path.read_bytes()[4:8], "little"), 123)


class ReleaseBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.dist = cls.root / "dist"
        copy_source_dist(cls.dist)
        profile = json.loads((ROOT / "profiles/legacy-mp123.json").read_text())
        for key in profile["size_budgets"]:
            profile["size_budgets"][key] = 5_000_000
        cls.profile = cls.root / "profile.json"
        cls.profile.write_text(json.dumps(profile))
        cls.first = cls.root / "first"
        cls.second = cls.root / "second"
        for output in (cls.first, cls.second):
            release.build_release(
                cls.dist, output, "phase2-test", profile_path=cls.profile,
                source_epoch=123456789, allow_dirty=True,
                allow_toolchain_mismatch=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_release_is_byte_reproducible(self):
        self.assertEqual(file_inventory(self.first), file_inventory(self.second))

    def test_release_metadata_and_archive_gate(self):
        result = check_legacy_release(self.dist, self.first)
        metadata = json.loads((self.first / "build_metadata.json").read_text())
        self.assertEqual(result["packages"], 11)
        self.assertEqual(metadata["profile"], "legacy-mp123")
        self.assertEqual(metadata["source_date_epoch"], 123456789)
        self.assertEqual(
            metadata["firmware_compatibility"]["version"], "1.23.0")
        self.assertIn("identifier", metadata["vendor_payload"])
        self.assertEqual(metadata["baseline_comparison"]["removed"], 0)

    def test_ota_packages_cover_every_non_protected_distribution_file(self):
        manifest = json.loads((self.first / "manifest.json").read_text())
        owned = set()
        for package in manifest:
            owned.update(release.archive_paths(
                self.first / package["file_name"], package["target"]))
        required = {
            "/" + item["path"] for item in file_inventory(self.dist)
            if not release.is_protected_path(item["path"])
        }
        self.assertEqual(owned, required)
        self.assertIn("/lib/tarfile/__init__.py", owned)

    def test_first_install_contains_local_defaults(self):
        device = self.root / "first-install"
        if device.exists():
            shutil.rmtree(device)
        shutil.copytree(self.dist, device)
        self.assertTrue((device / "app.py").is_file())
        self.assertTrue((device / "hdwconfig.py").is_file())
        self.assertTrue((device / "files/user/hello.py").is_file())
        self.assertTrue((device / "boot.py").is_file())

    def test_ota_from_captured_layout_preserves_device_state(self):
        fixture = ROOT / "tests/fixtures/legacy_mp123/layout"
        device = self.root / "ota-device"
        if device.exists():
            shutil.rmtree(device)
        shutil.copytree(fixture, device)
        protected = ("app.py", "hdwconfig.py", "settings.json", "repos.json", "logs", "files/user")

        def snapshot():
            result = {}
            for relative in protected:
                path = device / relative
                if path.is_file():
                    result[relative] = path.read_bytes()
                elif path.is_dir():
                    for child in sorted(item for item in path.rglob("*") if item.is_file()):
                        result[child.relative_to(device).as_posix()] = child.read_bytes()
            return result

        before = snapshot()
        manifest = json.loads((self.first / "manifest.json").read_text())
        for package in manifest:
            target = device / package["target"].strip("/")
            if package["clear_first"] and target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            with tarfile.open(self.first / package["file_name"]) as archive:
                archive.extractall(target)
        self.assertEqual(snapshot(), before)
        self.assertTrue((device / "recovery/recovery.py").is_file())
        self.assertTrue((device / "lib/tartlabutils/updater.py").is_file())


class UpdaterFailureInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("ujson", json)
        sys.modules.setdefault("uasyncio", asyncio)
        sys.modules.setdefault("uhashlib", hashlib)
        sys.modules.setdefault("uos", os)
        sys.modules.setdefault("urequests", types.SimpleNamespace(get=None))
        sys.modules.setdefault("machine", types.SimpleNamespace(reset=lambda: None))
        package = types.ModuleType("phase2pkg")
        package.__path__ = []
        sys.modules["phase2pkg"] = package
        state = load_module("phase2pkg.state", ROOT / "src/lib/tartlabutils/state.py")
        misc = types.ModuleType("phase2pkg.miscutils")
        misc.file_exists = lambda path: 0
        misc.load_settings = lambda: {}
        misc.log = lambda message: None
        misc.log_exception = lambda error: None
        misc.mkdirs = lambda path: os.makedirs(path, exist_ok=True)
        misc.rmvdir = lambda path: shutil.rmtree(path)
        misc.save_settings = lambda settings: None
        sys.modules["phase2pkg.miscutils"] = misc
        cls.updater = load_module(
            "phase2pkg.updater", ROOT / "src/lib/tartlabutils/updater.py")
        cls.state = state

    def test_interrupted_download_never_promotes_partial_file(self):
        updater = self.updater

        class InterruptedRaw:
            def __init__(self):
                self.calls = 0

            def read(self, size):
                self.calls += 1
                if self.calls == 1:
                    return b"partial"
                raise OSError("synthetic interruption")

        response = types.SimpleNamespace(
            status_code=200, raw=InterruptedRaw(), close=lambda: None)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "package.tar"
            old = (updater.urequests.get, updater.file_exists)
            updater.urequests.get = lambda *args, **kwargs: response
            updater.file_exists = lambda path: 1 if Path(path).is_file() else 0
            try:
                with self.assertRaises(OSError):
                    asyncio.run(updater.download_asset("synthetic", str(target)))
            finally:
                updater.urequests.get, updater.file_exists = old
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())

    def test_corrupted_package_fails_before_install_marker(self):
        updater = self.updater
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            manifest = [{
                "file_name": "bad.tar", "sha256": "0" * 64,
                "target": "/ide", "clear_first": True, "expanded_size": 1,
            }]
            assets = [
                {"name": "manifest.json", "size": 100, "browser_download_url": "manifest"},
                {"name": "bad.tar", "size": 10, "browser_download_url": "bad"},
            ]
            begun = []

            async def check(repo):
                return assets, "v-next"

            async def download(url, target):
                Path(target).write_text(json.dumps(manifest)) if url == "manifest" else \
                    Path(target).write_bytes(b"corrupted")
                return True

            old = (
                updater.TMP_UPDATE_FOLDER, updater.check_for_update,
                updater.download_asset, updater._free_space, updater.begin_update,
                updater.file_exists, updater.rmvdir, updater.mkdirs,
            )
            updater.TMP_UPDATE_FOLDER = temp_path.as_posix()
            updater.check_for_update = check
            updater.download_asset = download
            updater._free_space = lambda: 10_000_000
            updater.begin_update = lambda *args: begun.append(args)
            updater.file_exists = lambda path: 2 if Path(path).is_dir() else (
                1 if Path(path).is_file() else 0)
            updater.rmvdir = lambda path: shutil.rmtree(path)
            updater.mkdirs = lambda path: os.makedirs(path, exist_ok=True)
            try:
                result = asyncio.run(updater.update_packages(
                    {"name": "TartLab", "installed_version": "old"},
                    lambda *args: None))
            finally:
                (updater.TMP_UPDATE_FOLDER, updater.check_for_update,
                 updater.download_asset, updater._free_space, updater.begin_update,
                 updater.file_exists, updater.rmvdir, updater.mkdirs) = old
            self.assertEqual(result, updater.UPDATE_FAILED)
            self.assertEqual(begun, [])

    def test_low_space_refuses_before_download_or_modification(self):
        updater = self.updater
        downloaded = []
        begun = []

        async def check(repo):
            return [{
                "name": "manifest.json", "size": 100,
                "browser_download_url": "manifest",
            }], "v-next"

        async def download(*args):
            downloaded.append(args)
            return True

        old = (updater.check_for_update, updater.download_asset, updater._free_space, updater.begin_update)
        updater.check_for_update = check
        updater.download_asset = download
        updater._free_space = lambda: 0
        updater.begin_update = lambda *args: begun.append(args)
        try:
            result = asyncio.run(updater.update_packages(
                {"name": "TartLab", "installed_version": "old"},
                lambda *args: None))
        finally:
            updater.check_for_update, updater.download_asset, updater._free_space, updater.begin_update = old
        self.assertEqual(result, updater.UPDATE_FAILED)
        self.assertEqual(downloaded, [])
        self.assertEqual(begun, [])

    def test_post_staging_low_space_refuses_before_install_marker(self):
        updater = self.updater
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_file = root / "good.tar"
            content = root / "module.py"
            content.write_text("VALUE = 1\n")
            with tarfile.open(package_file, "w", format=tarfile.USTAR_FORMAT) as archive:
                archive.add(content, arcname="module.py")
            digest = hashlib.sha256(package_file.read_bytes()).hexdigest()
            manifest = [{
                "file_name": "good.tar", "sha256": digest,
                "target": "/ide", "clear_first": True,
                "expanded_size": content.stat().st_size,
            }]
            assets = [
                {"name": "manifest.json", "size": 100, "browser_download_url": "manifest"},
                {"name": "good.tar", "size": package_file.stat().st_size,
                 "browser_download_url": "package"},
            ]
            begun = []
            free_values = iter((10_000_000, 0))

            async def check(repo):
                return assets, "v-next"

            async def download(url, target):
                if url == "manifest":
                    Path(target).write_text(json.dumps(manifest))
                else:
                    shutil.copy2(package_file, target)
                return True

            old = (
                updater.TMP_UPDATE_FOLDER, updater.check_for_update,
                updater.download_asset, updater._free_space, updater.begin_update,
                updater.file_exists, updater.rmvdir, updater.mkdirs,
            )
            updater.TMP_UPDATE_FOLDER = (root / "staging").as_posix()
            updater.check_for_update = check
            updater.download_asset = download
            updater._free_space = lambda: next(free_values)
            updater.begin_update = lambda *args: begun.append(args)
            updater.file_exists = lambda path: 2 if Path(path).is_dir() else (
                1 if Path(path).is_file() else 0)
            updater.rmvdir = lambda path: shutil.rmtree(path)
            updater.mkdirs = lambda path: os.makedirs(path, exist_ok=True)
            try:
                result = asyncio.run(updater.update_packages(
                    {"name": "TartLab", "installed_version": "old"},
                    lambda *args: None))
            finally:
                (updater.TMP_UPDATE_FOLDER, updater.check_for_update,
                 updater.download_asset, updater._free_space, updater.begin_update,
                 updater.file_exists, updater.rmvdir, updater.mkdirs) = old
            self.assertEqual(result, updater.UPDATE_FAILED)
            self.assertEqual(begun, [])


class FailedHealthGateTests(unittest.TestCase):
    def test_power_loss_after_install_marker_keeps_old_version_for_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "state").mkdir()
            state = load_module(
                "phase2powerstate", ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = (root / "state").as_posix()
            state.REPOS_FILE = (root / "state/repos.json").as_posix()
            state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
            state.write_json(state.REPOS_FILE, {
                "list": [{"name": "TartLab", "installed_version": "old"}],
            })
            state.begin_update("TartLab", "old", "new")
            self.assertEqual(state.get_update_state()["status"], "installing")
            self.assertEqual(
                state.read_json(state.REPOS_FILE)["list"][0]["installed_version"],
                "old")

            source = (ROOT / "src/boot.py").read_text()
            definitions = source.split("_reason = _recovery_reason", 1)[0]
            namespace = {}
            exec(compile(definitions, "boot.py", "exec"), namespace)
            original_read = namespace["_read"]
            namespace["_read"] = lambda path, default: (
                state.get_update_state()
                if path == namespace["UPDATE_STATE"] else default)
            try:
                reason = namespace["_recovery_reason"]({"consecutive_failures": 0})
            finally:
                namespace["_read"] = original_read
            self.assertEqual(reason, "update_installing")

    def test_failed_health_never_commits_pending_version_and_enters_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "state").mkdir()
            package = types.ModuleType("phase2health")
            package.__path__ = []
            sys.modules["phase2health"] = package
            state = load_module(
                "phase2health.state", ROOT / "src/lib/tartlabutils/state.py")
            state.STATE_DIR = (root / "state").as_posix()
            state.REPOS_FILE = (root / "state/repos.json").as_posix()
            state.UPDATE_STATE_FILE = (root / "state/update.json").as_posix()
            state.BOOT_STATE_FILE = (root / "state/boot.json").as_posix()
            bootstate = load_module(
                "phase2health.bootstate", ROOT / "src/lib/tartlabutils/bootstate.py")
            state.write_json(state.REPOS_FILE, {
                "list": [{"name": "TartLab", "installed_version": "old"}],
            })
            state.begin_update("TartLab", "old", "new")
            state.set_update_pending_health()
            for attempt in range(3):
                bootstate.ensure_boot_started()
                bootstate.mark_boot_failed("synthetic health failure")
            repos = state.read_json(state.REPOS_FILE)
            boot = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(repos["list"][0]["installed_version"], "old")
            self.assertEqual(state.get_update_state()["status"], "pending_health")
            self.assertGreaterEqual(boot["consecutive_failures"], 3)


if __name__ == "__main__":
    unittest.main()
