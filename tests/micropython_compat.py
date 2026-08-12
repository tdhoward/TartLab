"""Hardware-free compatibility probe for the pinned MicroPython 1.23 host port.

This file intentionally uses only language and library features available in
MicroPython 1.23.  It executes selected production modules from source so the
probe tests the release code rather than a CPython translation of it.
"""

import os
import sys
import ujson


EXPECTED_VERSION = "v1.23.0"
EXPECTED_COMMIT = "a61c446"
HOST_OPEN = open
CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(message)


def expect_error(error_type, function, message):
    try:
        function()
    except error_type:
        check(True, message)
        return
    raise AssertionError(message)


class PrefixOS:
    """Map device-style absolute paths below an isolated host directory."""

    def __init__(self, root):
        self.root = root.replace("\\", "/").rstrip("/")

    def path(self, logical_path):
        normalized = str(logical_path).replace("\\", "/")
        parts = normalized.strip("/").split("/")
        if any(part in (".", "..") for part in parts):
            raise ValueError("Unsafe device path: " + normalized)
        suffix = "/".join(part for part in parts if part)
        if suffix:
            return self.root + "/" + suffix
        return self.root

    def stat(self, path):
        return os.stat(self.path(path))

    def statvfs(self, path):
        return os.statvfs(self.path(path))

    def listdir(self, path="/"):
        return os.listdir(self.path(path))

    def mkdir(self, path):
        return os.mkdir(self.path(path))

    def remove(self, path):
        return os.remove(self.path(path))

    def rmdir(self, path):
        return os.rmdir(self.path(path))

    def rename(self, source, destination):
        return os.rename(self.path(source), self.path(destination))

    def sync(self):
        sync = getattr(os, "sync", None)
        if sync is not None:
            return sync()


def mkdirs(device_os, path):
    current = ""
    for part in path.strip("/").split("/"):
        if not part:
            continue
        current += "/" + part
        try:
            device_os.stat(current)
        except OSError:
            device_os.mkdir(current)


def device_open(device_os, path, mode="r"):
    return HOST_OPEN(device_os.path(path), mode)


def write_text(device_os, path, value):
    parent = path.rsplit("/", 1)[0]
    if parent:
        mkdirs(device_os, parent)
    with device_open(device_os, path, "w") as stream:
        stream.write(value)


def write_json(device_os, path, value):
    parent = path.rsplit("/", 1)[0]
    if parent:
        mkdirs(device_os, parent)
    with device_open(device_os, path, "w") as stream:
        ujson.dump(value, stream)


def load_source(source_root, relative_path, name, trailer=None):
    path = source_root.rstrip("/") + "/" + relative_path
    with HOST_OPEN(path, "r") as stream:
        source = stream.read()
    if trailer is not None:
        source = source.split(trailer, 1)[0]
    namespace = {"__name__": name, "__file__": path}
    exec(compile(source, path, "exec"), namespace)
    return namespace


def tartlab_repo(state):
    repos = state["read_json"](state["REPOS_FILE"], {})
    for item in repos.get("list", []):
        if item.get("name") == "TartLab":
            return item
    return None


def probe_state(source_root, device_os):
    settings = {
        "dbver": 1,
        "STARTUP_MODE": "BUTTON",
        "hostname": "micropython-compat",
        "wifi_ssids": ["SYNTHETIC_NETWORK"],
        "wifi_passwords": ["not-a-real-password"],
    }
    repos = {"list": [{
        "name": "TartLab",
        "repo": "tdhoward/tartlab",
        "installed_version": "compat-candidate",
    }]}
    transition = {"legacy_installed_versions": {"TartLab": "v0.13"}}
    write_json(device_os, "/settings.json", settings)
    write_json(device_os, "/repos.json", repos)
    write_json(device_os, "/defaults/phase1_transition.json", transition)
    write_text(device_os, "/app.py", "# selected app\n# demos/hello.py\n")
    write_text(device_os, "/hdwconfig.py", "BOARD = 'synthetic'\n")
    write_text(device_os, "/logs/000000.log", "legacy log\n")

    state = load_source(
        source_root, "src/lib/tartlabutils/state.py", "compat_state")
    state["os"] = device_os
    state["open"] = lambda path, mode="r": device_open(device_os, path, mode)
    state["ensure_layout"]()

    check(state["read_json"](state["SETTINGS_FILE"])["hostname"] ==
          "micropython-compat", "legacy settings were not migrated")
    check(state["get_selected_app"]() == "demos/hello.py",
          "legacy selected app was not migrated")
    check(device_open(device_os, "/device/hdwconfig.py").read() ==
          "BOARD = 'synthetic'\n", "device configuration was not preserved")
    check(device_open(device_os, "/state/logs/000000.log").read() ==
          "legacy log\n", "legacy logs were not migrated")
    check(tartlab_repo(state)["installed_version"] == "v0.13",
          "legacy pre-health version commit was not rolled back")
    check(state["get_update_state"]()["status"] == "pending_health",
          "legacy transition did not enter pending health")
    check(state["commit_pending_update"](),
          "pending version did not commit after health")
    check(tartlab_repo(state)["installed_version"] == "compat-candidate",
          "candidate version was not committed")
    check(not state["commit_pending_update"](),
          "version commit was not exactly once")
    expect_error(
        ValueError,
        lambda: state["save_selected_app"]("../escape.py"),
        "selected app traversal was accepted",
    )
    return state


def probe_boot(source_root, device_os, state):
    boot = load_source(
        source_root, "src/boot.py", "compat_boot",
        "_reason = _recovery_reason(_start_boot())")
    boot["os"] = device_os
    boot["open"] = lambda path, mode="r": device_open(device_os, path, mode)

    first = boot["_start_boot"]()
    second = boot["_start_boot"]()
    third = boot["_start_boot"]()
    check(boot["_recovery_reason"](first) is None,
          "first unhealthy boot incorrectly entered recovery")
    check(boot["_recovery_reason"](second) is None,
          "second unhealthy boot incorrectly entered recovery")
    check(boot["_recovery_reason"](third) == "repeated_boot_failure",
          "third unhealthy boot did not enter recovery")

    state["begin_update"]("TartLab", "compat-candidate", "next-candidate")
    check(boot["_recovery_reason"](third) == "update_installing",
          "install marker did not take recovery priority")
    state["set_update_failed"]("synthetic failure")
    check(boot["_recovery_reason"](third) == "update_failed",
          "failed update did not select recovery")


def probe_recovery(source_root, device_os):
    previous_requests = sys.modules.get("urequests")
    sys.modules["urequests"] = sys
    try:
        recovery = load_source(
            source_root, "src/recovery/recovery_update.py",
            "compat_recovery")
    finally:
        if previous_requests is None:
            del sys.modules["urequests"]
        else:
            sys.modules["urequests"] = previous_requests
    recovery["os"] = device_os
    recovery["open"] = lambda path, mode="r": device_open(device_os, path, mode)

    check(recovery["_target_path"]("/", "ide/ide.py") == "/ide/ide.py",
          "root archive target was resolved incorrectly")
    expect_error(
        ValueError,
        lambda: recovery["_target_path"]("/", "../escape.py"),
        "archive traversal was accepted",
    )
    expect_error(
        ValueError,
        lambda: recovery["_target_path"]("/", "state/settings.json"),
        "protected archive path was accepted",
    )
    recovery["_validate_manifest"]([{
        "file_name": "ide.tar",
        "sha256": "0" * 64,
        "target": "/ide",
        "clear_first": True,
    }])
    expect_error(
        ValueError,
        lambda: recovery["_validate_manifest"]([{
            "file_name": "state.tar",
            "sha256": "0" * 64,
            "target": "/state",
            "clear_first": True,
        }]),
        "protected manifest target was accepted",
    )
    write_text(device_os, "/tmp/hash.bin", "abc")
    check(recovery["_sha256"]("/tmp/hash.bin") ==
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
          "recovery SHA-256 result was incorrect")
    recovery["_write_json"]("/state/recovery_probe.json", {"ok": True})
    check(recovery["_read_json"](
        "/state/recovery_probe.json", {})["ok"],
        "recovery JSON round trip failed")


class FakeDisplay:
    def __init__(self):
        self.width = 222
        self.height = 480
        self.brightness = 1.0
        self.deinitialized = False

    def deinit(self):
        self.deinitialized = True


class FakeInput:
    def __init__(self):
        self.deinitialized = False

    def deinit(self):
        self.deinitialized = True


class FakePin:
    IN = 91
    calls = []

    def __init__(self, pin, mode):
        FakePin.calls.append((pin, mode))

    def value(self):
        return 0


class FakeInterface:
    def __init__(self):
        self.enabled = False
        self.configuration = {}

    def active(self, value):
        self.enabled = bool(value)

    def config(self, **values):
        self.configuration.update(values)


class FakeNetwork:
    STA_IF = 1
    AP_IF = 2
    AUTH_OPEN = 0

    def __init__(self):
        self.hostnames = []
        self.station = FakeInterface()
        self.access_point = FakeInterface()

    def hostname(self, value):
        self.hostnames.append(value)

    def WLAN(self, kind):
        if kind == self.STA_IF:
            return self.station
        return self.access_point


def probe_platform(source_root):
    platform_module = load_source(
        source_root, "src/lib/tartlabutils/platform.py", "compat_platform")
    paths = ["/device", "/lib", "/", "/files/user", "host-library"]
    platform_module["configure_legacy_paths"](paths)
    expected = ["/device", "/lib", "/", "/files/user"] + list(
        platform_module["LEGACY_SEARCH_PATHS"]) + ["host-library"]
    check(paths == expected, "legacy paths were not ordered after core paths")
    platform_module["configure_legacy_paths"](paths)
    check(paths == expected, "legacy paths were duplicated")

    display = FakeDisplay()
    pointer = FakeInput()
    hardware = type("Hardware", (), {})()
    hardware.display_drv = display
    hardware.touch_drv = pointer
    hardware.IDE_BUTTON_PIN = 12
    network = FakeNetwork()
    adapter = platform_module["LegacyPlatform"](
        hardware=hardware, pin_factory=FakePin, network_module=network)
    check(adapter.ide_button_value() == 0,
          "platform button input was not delegated")
    check(FakePin.calls == [(12, FakePin.IN)],
          "platform did not cache the expected input pin")
    adapter.set_hostname("compat-host")
    access_point = adapter.access_point_interface()
    adapter.configure_open_access_point(access_point, "Compat-AP")
    check(network.hostnames == ["compat-host"],
          "platform hostname was not delegated")
    check(access_point.enabled and access_point.configuration == {
        "essid": "Compat-AP", "authmode": FakeNetwork.AUTH_OPEN},
        "platform open AP configuration changed")
    adapter.set_brightness(0.75)
    check(display.brightness == 0.75,
          "platform brightness was not delegated")
    check(adapter.capabilities["display"] and
          adapter.capabilities["touch"] and
          adapter.capabilities["ide_button"],
          "platform capabilities were incomplete")
    adapter.deinit()
    check(display.deinitialized and pointer.deinitialized,
          "platform resources were not deinitialized")


def main():
    check(EXPECTED_VERSION in sys.version or EXPECTED_COMMIT in sys.version,
          "expected MicroPython %s / %s, got %s" %
          (EXPECTED_VERSION, EXPECTED_COMMIT, sys.version))
    if len(sys.argv) != 3:
        raise ValueError(
            "usage: micropython micropython_compat.py SOURCE_ROOT DEVICE_ROOT")
    source_root = sys.argv[1].replace("\\", "/").rstrip("/")
    device_root = sys.argv[2].replace("\\", "/").rstrip("/")
    device_os = PrefixOS(device_root)

    state = probe_state(source_root, device_os)
    probe_boot(source_root, device_os, state)
    probe_recovery(source_root, device_os)
    probe_platform(source_root)
    print("MICROPYTHON_COMPAT_OK version=%s commit=%s checks=%s" %
          (EXPECTED_VERSION, EXPECTED_COMMIT, CHECKS))


main()
