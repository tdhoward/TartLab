import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.modules.setdefault("ujson", json)
sys.modules.setdefault("uhashlib", hashlib)
sys.modules.setdefault("urequests", types.SimpleNamespace(get=None))

import release
from release_utils import file_inventory
from tests.virtual_device import VirtualDeviceFS, VirtualPowerLoss


PROTECTED_CONTENT = (
    "/app.py",
    "/hdwconfig.py",
    "/settings.json",
    "/repos.json",
    "/logs",
    "/files/user",
    "/device",
    "/state/settings.json",
    "/state/logs",
    "/state/selected_app.json",
)


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

    # The generated web tree is ignored. The regular Phase 2 tests use the
    # same deterministic stand-ins while CI separately exercises npm.
    baseline = json.loads(
        (ROOT / "tests/fixtures/legacy_mp123/inventory.json").read_text())
    for item in baseline:
        relative = item.get("path", "")
        if item.get("ownership") != "update-managed" or not relative.startswith(
                "ide/www/"):
            continue
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("virtual-device-web-placeholder:" + relative).encode())


class VirtualFilesystemTests(unittest.TestCase):
    def test_mutations_are_journaled_and_can_cut_power(self):
        with tempfile.TemporaryDirectory() as temp:
            device = VirtualDeviceFS(Path(temp))
            device.os.mkdir("/state")
            device.arm_power_loss(
                lambda mutation: mutation.operation == "open_write" and
                mutation.path == "/state/update.json")

            with self.assertRaises(VirtualPowerLoss) as raised:
                device.open("/state/update.json", "w")

            self.assertEqual(raised.exception.mutation.path, "/state/update.json")
            self.assertEqual(device.host_path("/state/update.json").read_bytes(), b"")
            self.assertEqual(
                [item.operation for item in device.mutations],
                ["mkdir", "open_write"],
            )

    def test_paths_cannot_escape_the_virtual_device(self):
        with tempfile.TemporaryDirectory() as temp:
            device = VirtualDeviceFS(Path(temp))
            with self.assertRaises(ValueError):
                device.host_path("/state/../../outside")


class VirtualRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.build_root = Path(cls.build.name)
        cls.dist = cls.build_root / "dist"
        cls.release_dir = cls.build_root / "release"
        copy_source_dist(cls.dist)

        profile = json.loads((ROOT / "profiles/legacy-mp123.json").read_text())
        for key in profile["size_budgets"]:
            profile["size_budgets"][key] = 5_000_000
        profile_path = cls.build_root / "profile.json"
        profile_path.write_text(json.dumps(profile))
        release.build_release(
            cls.dist, cls.release_dir, "virtual-candidate",
            profile_path=profile_path, source_epoch=123456789,
            allow_dirty=True, allow_toolchain_mismatch=True)
        cls.manifest = json.loads(
            (cls.release_dir / "manifest.json").read_text())
        cls.runtime_number = 0

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def runtime_name(self, prefix):
        type(self).runtime_number += 1
        return "%s_%s" % (prefix, type(self).runtime_number)

    def load_state_runtime(self, device):
        package_name = self.runtime_name("virtual_runtime")
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package
        state = load_module(
            package_name + ".state", ROOT / "src/lib/tartlabutils/state.py")
        state.os = device.os
        state.open = device.open
        bootstate = load_module(
            package_name + ".bootstate",
            ROOT / "src/lib/tartlabutils/bootstate.py")
        bootstate.os = device.os
        return state, bootstate

    def load_recovery_updater(self, device):
        updater = load_module(
            self.runtime_name("virtual_recovery"),
            ROOT / "src/recovery/recovery_update.py")
        updater.os = device.os
        updater.open = device.open
        return updater

    def boot_recovery_reason(self, device):
        source = (ROOT / "src/boot.py").read_text()
        definitions = source.split("_reason = _recovery_reason", 1)[0]
        namespace = {}
        exec(compile(definitions, "boot.py", "exec"), namespace)
        namespace["os"] = device.os
        namespace["open"] = device.open
        return namespace["_recovery_reason"](namespace["_start_boot"]())

    def prepare_device(self, root):
        fixture = ROOT / "tests/fixtures/legacy_mp123/layout"
        shutil.copytree(
            fixture, root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        (root / "boot.py").write_text("# preserved legacy recovery gate\n")
        (root / "recovery").mkdir()
        for name in ("recovery.py", "recovery_update.py"):
            shutil.copy2(ROOT / "src/recovery" / name, root / "recovery" / name)

        device = VirtualDeviceFS(root)
        state, bootstate = self.load_state_runtime(device)
        state.ensure_layout()

        staging = device.host_path("/tmp/recovery")
        staging.mkdir(parents=True)
        shutil.copy2(self.release_dir / "manifest.json", staging / "manifest.json")
        for package in self.manifest:
            shutil.copy2(
                self.release_dir / package["file_name"],
                staging / package["file_name"])
        device.clear_journal()
        return device, state, bootstate

    def tartlab_repo(self, state):
        repos = state.read_json(state.REPOS_FILE)
        return next(item for item in repos["list"] if item["name"] == "TartLab")

    def first_extracted_path(self, package):
        paths = release.archive_paths(
            self.release_dir / package["file_name"], package["target"])
        # Once the layout migration marker exists, recovery intentionally keeps
        # the already-working early boot gate instead of replacing /boot.py.
        return next(path for path in paths if path != "/boot.py")

    def assert_candidate_payload_installed(self, device):
        for item in file_inventory(self.dist):
            logical = "/" + item["path"]
            if release.is_protected_path(logical) or logical == "/boot.py" or \
                    logical.startswith("/recovery/"):
                continue
            self.assertEqual(
                device.host_path(logical).read_bytes(),
                (self.dist / item["path"]).read_bytes(),
                logical,
            )

    def test_candidate_install_preserves_state_and_commits_once_after_health(self):
        with tempfile.TemporaryDirectory() as temp:
            device, state, bootstate = self.prepare_device(Path(temp) / "device")
            protected_before = device.snapshot(PROTECTED_CONTENT)
            recovery = self.load_recovery_updater(device)
            repo = self.tartlab_repo(state)

            result = recovery._install_verified_packages(
                repo, "virtual-candidate", self.manifest, lambda message: None)

            self.assertEqual(result, "virtual-candidate")
            self.assertEqual(state.get_update_state()["status"], "pending_health")
            self.assertEqual(self.tartlab_repo(state)["installed_version"], "v0.13")
            self.assertEqual(device.snapshot(PROTECTED_CONTENT), protected_before)
            self.assert_candidate_payload_installed(device)
            self.assertEqual(
                device.host_path("/boot.py").read_text(),
                "# preserved legacy recovery gate\n")

            self.assertTrue(bootstate.mark_boot_healthy("IDE"))
            committed = self.tartlab_repo(state)
            self.assertEqual(committed["installed_version"], "virtual-candidate")
            self.assertEqual(committed["repo"], "tdhoward/tartlab")
            self.assertIsNone(state.get_update_state())

            self.assertFalse(bootstate.mark_boot_healthy("IDE"))
            self.assertEqual(
                self.tartlab_repo(state)["installed_version"],
                "virtual-candidate")

    def test_each_candidate_package_resumes_after_clear_and_extraction_faults(self):
        installable = [
            package for package in self.manifest
            if package["target"].rstrip("/") != "/recovery"
        ]
        self.assertGreater(len(installable), 1)

        for package in installable:
            faults = [("extract", "open_write", self.first_extracted_path(package))]
            if package["clear_first"]:
                stale_path = package["target"].rstrip("/") + "/virtual-stale.txt"
                faults.insert(0, ("clear", "remove", stale_path))

            for boundary, operation, fault_path in faults:
                with self.subTest(
                        package=package["file_name"], boundary=boundary), \
                        tempfile.TemporaryDirectory() as temp:
                    device, state, unused_bootstate = self.prepare_device(
                        Path(temp) / "device")
                    if package["clear_first"]:
                        stale = device.host_path(
                            package["target"].rstrip("/") + "/virtual-stale.txt")
                        stale.parent.mkdir(parents=True, exist_ok=True)
                        stale.write_text("old managed payload\n")
                    protected_before = device.snapshot(PROTECTED_CONTENT)
                    device.arm_power_loss(
                        lambda mutation, expected_operation=operation,
                        expected_path=fault_path:
                        mutation.operation == expected_operation and
                        mutation.path == expected_path)
                    recovery = self.load_recovery_updater(device)

                    with self.assertRaises(VirtualPowerLoss) as raised:
                        recovery._install_verified_packages(
                            self.tartlab_repo(state), "virtual-candidate",
                            self.manifest, lambda message: None)

                    self.assertEqual(raised.exception.mutation.path, fault_path)
                    self.assertEqual(
                        self.boot_recovery_reason(device), "update_installing")
                    self.assertEqual(
                        self.tartlab_repo(state)["installed_version"], "v0.13")

                    # Reloading the independent recovery module models a fresh
                    # interpreter after reset; progress comes from device files.
                    recovery = self.load_recovery_updater(device)
                    result = recovery.resume_staged_update(lambda message: None)
                    self.assertEqual(result, "virtual-candidate")
                    self.assertEqual(
                        state.get_update_state()["status"], "pending_health")
                    self.assertEqual(
                        self.tartlab_repo(state)["installed_version"], "v0.13")
                    self.assertEqual(
                        device.snapshot(PROTECTED_CONTENT), protected_before)
                    first_path = self.first_extracted_path(package)
                    self.assertEqual(
                        device.host_path(first_path).read_bytes(),
                        (self.dist / first_path.lstrip("/")).read_bytes())


if __name__ == "__main__":
    unittest.main()
