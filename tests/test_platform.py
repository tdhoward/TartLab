import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("ujson", json)

from tests.headless_platform import HeadlessDisplay, HeadlessInput, HeadlessPlatform
from tests.virtual_device import VirtualDeviceFS


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PlatformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platform_module = load_module(
            "platform_contract_under_test",
            ROOT / "src/lib/tartlabutils/platform.py")

    def test_legacy_paths_follow_core_paths_without_duplicates(self):
        paths = ["/device", "/lib", "/", "/files/user", "host-library"]
        result = self.platform_module.configure_legacy_paths(paths)
        expected = [
            "/device", "/lib", "/", "/files/user",
            *self.platform_module.LEGACY_SEARCH_PATHS,
            "host-library",
        ]
        self.assertEqual(result, expected)
        self.platform_module.configure_legacy_paths(paths)
        self.assertEqual(paths, expected)

    def test_protected_board_identity_selects_an_isolated_runtime_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            identity = Path(temporary) / "board.json"
            identity.write_text(json.dumps({
                "schema": 1,
                "board_id": "lilygo_t_display_s3_pro",
            }), encoding="utf-8")
            self.assertEqual(
                self.platform_module.board_runtime_path(str(identity)),
                "/board/lilygo_t_display_s3_pro",
            )
            identity.write_text(
                json.dumps({"board_id": "../unsafe"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "board identity"):
                self.platform_module.board_runtime_path(str(identity))

    def test_board_runtime_precedes_release_root_and_student_imports(self):
        paths = ["/device", "/lib", "/", "/files/user", "host-library"]
        original = self.platform_module.board_runtime_path
        self.platform_module.board_runtime_path = (
            lambda: "/board/lilygo_t_display_s3_pro")
        try:
            self.platform_module.configure_legacy_paths(paths)
        finally:
            self.platform_module.board_runtime_path = original
        self.assertEqual(paths, [
            "/device", "/board/lilygo_t_display_s3_pro", "/lib", "/",
            "/files/user", *self.platform_module.LEGACY_SEARCH_PATHS,
            "host-library",
        ])

    def test_legacy_adapter_exposes_hardware_through_the_contract(self):
        display = HeadlessDisplay(222, 480)
        pointer = HeadlessInput()
        hardware = types.SimpleNamespace(
            display_drv=display, touch_drv=pointer, IDE_BUTTON_PIN=12)

        class PinFactory:
            IN = 91
            calls = []

            def __init__(self, pin, mode):
                self.calls.append((pin, mode))

            def value(self):
                return 0

        original = self.platform_module.configure_legacy_paths
        self.platform_module.configure_legacy_paths = lambda paths=None: paths
        try:
            platform = self.platform_module.LegacyPlatform(
                hardware=hardware, pin_factory=PinFactory)
        finally:
            self.platform_module.configure_legacy_paths = original

        self.assertIs(platform.display, display)
        self.assertIs(platform.input, pointer)
        self.assertEqual((platform.width, platform.height), (222, 480))
        self.assertEqual(platform.ide_button_value(), 0)
        self.assertEqual(PinFactory.calls, [(12, PinFactory.IN)])
        self.assertEqual(platform.capabilities, {
            "display": True,
            "touch": True,
            "ide_button": True,
            "backlight": True,
            "network": True,
        })
        platform.deinit()
        self.assertTrue(display.deinitialized)
        self.assertTrue(pointer.deinitialized)

    def test_legacy_adapter_wraps_network_and_keeps_injected_platform(self):
        interfaces = {"station": object(), "access-point": types.SimpleNamespace(
            active_values=[], configuration={})}

        def active(value):
            interfaces["access-point"].active_values.append(value)

        def config(**values):
            interfaces["access-point"].configuration.update(values)

        interfaces["access-point"].active = active
        interfaces["access-point"].config = config

        class NetworkModule:
            STA_IF = "station"
            AP_IF = "access-point"
            AUTH_OPEN = 0
            hostnames = []

            @classmethod
            def hostname(cls, value):
                cls.hostnames.append(value)

            @staticmethod
            def WLAN(kind):
                return interfaces[kind]

        hardware = types.SimpleNamespace(
            display_drv=HeadlessDisplay(), IDE_BUTTON_PIN=12)
        original = self.platform_module.configure_legacy_paths
        self.platform_module.configure_legacy_paths = lambda paths=None: paths
        try:
            platform = self.platform_module.LegacyPlatform(
                hardware=hardware, pin_factory=lambda *args: None,
                network_module=NetworkModule)
        finally:
            self.platform_module.configure_legacy_paths = original

        platform.set_hostname("headless-test")
        self.assertIs(platform.station_interface(), interfaces["station"])
        access_point = platform.access_point_interface()
        platform.configure_open_access_point(access_point, "TartLab-Test")
        self.assertEqual(NetworkModule.hostnames, ["headless-test"])
        self.assertEqual(access_point.active_values, [True])
        self.assertEqual(access_point.configuration, {
            "essid": "TartLab-Test", "authmode": 0})

        injected = HeadlessPlatform()
        self.platform_module.set_platform(injected)
        try:
            self.assertIs(self.platform_module.get_platform(), injected)
        finally:
            self.platform_module.set_platform(None)

    def test_explicit_hardware_factory_selects_modern_platform(self):
        selected = object()
        hardware = types.ModuleType("hdwconfig")
        hardware.create_platform = lambda: selected
        previous = sys.modules.get("hdwconfig")
        self.platform_module.set_platform(None)
        sys.modules["hdwconfig"] = hardware
        try:
            self.assertIs(self.platform_module.get_platform(), selected)
        finally:
            self.platform_module.set_platform(None)
            if previous is None:
                sys.modules.pop("hdwconfig", None)
            else:
                sys.modules["hdwconfig"] = previous

    def test_legacy_ide_view_preserves_rendering_operations(self):
        framebuffers = []
        gradients = []

        class FrameBuffer:
            def __init__(self, buffer, width, height, color_format):
                self.buffer = buffer
                self.width = width
                self.height = height
                self.operations = []
                framebuffers.append(self)

            def fill(self, color):
                self.operations.append(("fill", color))

            def rect(self, x, y, width, height, color):
                self.operations.append(("rect", x, y, width, height, color))

            def text(self, value, x, y, color, size):
                self.operations.append(("text", value, x, y, color, size))

            def ellipse(self, x, y, rx, ry, color, fill):
                self.operations.append(
                    ("ellipse", x, y, rx, ry, color, fill))

        graphics = types.ModuleType("graphics")
        graphics.FrameBuffer = FrameBuffer
        graphics.RGB565 = 1
        graphics.gradient_rect = lambda *args: gradients.append(args)
        previous = sys.modules.get("graphics")
        sys.modules["graphics"] = graphics

        class Display:
            width = 222
            height = 480
            color_depth = 16
            requires_byteswap = True
            rotation = 0

            def __init__(self):
                self.blits = []

            def disable_auto_byteswap(self, value):
                return value

            def blit_rect(self, *args):
                self.blits.append(args)

        display = Display()
        try:
            view = self.platform_module.LegacyIDEView(display)
            view.show_startup("candidate")
            view.show_network("Classroom", "10.0.0.42", "tartlab")
            view.show_update_progress("Installing", 1, 4)
            view.show_app_error()
        finally:
            if previous is None:
                sys.modules.pop("graphics", None)
            else:
                sys.modules["graphics"] = previous

        self.assertEqual(display.rotation, 90)
        self.assertEqual(len(framebuffers), 3)
        text_operations = [
            operation for operation in framebuffers[1].operations
            if operation[0] == "text"
        ]
        self.assertTrue(any(item[1] == "TARTLAB candidate" for item in text_operations))
        self.assertTrue(any(item[1] == "WiFi: Classroom" for item in text_operations))
        self.assertTrue(any(item[1] == "Installing" for item in text_operations))
        self.assertEqual(framebuffers[2].operations[-1][0], "ellipse")
        self.assertTrue(framebuffers[2].operations[-1][-1])
        self.assertGreaterEqual(len(display.blits), 7)
        self.assertEqual(len(gradients), 1)


class LauncherHealthTimerTests(unittest.TestCase):
    def test_esp32_hardware_timer_fallback_marks_health_and_releases_timer(self):
        package_name = "launcher_health_test"
        package = types.ModuleType(package_name)
        package.__path__ = []
        bootstate = types.ModuleType(package_name + ".bootstate")
        healthy = []
        bootstate.mark_boot_healthy = lambda mode: healthy.append(mode) or False
        miscutils = types.ModuleType(package_name + ".miscutils")
        logs = []
        miscutils.log = logs.append
        state = types.ModuleType(package_name + ".state")
        state.get_selected_app = lambda: "hello.py"

        timers = []

        class Timer:
            ONE_SHOT = 7

            def __init__(self, timer_id):
                if timer_id == -1:
                    raise ValueError("virtual timer unsupported")
                self.timer_id = timer_id
                self.deinit_calls = 0
                timers.append(self)

            def init(self, **kwargs):
                self.options = kwargs

            def deinit(self):
                self.deinit_calls += 1

        machine = types.ModuleType("machine")
        machine.Timer = Timer
        micropython = types.ModuleType("micropython")
        micropython.schedule = lambda callback, value: callback(value)
        saved = {name: sys.modules.get(name) for name in (
            package_name, package_name + ".bootstate",
            package_name + ".miscutils", package_name + ".state",
            "machine", "micropython")}
        sys.modules.update({
            package_name: package,
            package_name + ".bootstate": bootstate,
            package_name + ".miscutils": miscutils,
            package_name + ".state": state,
            "machine": machine,
            "micropython": micropython,
        })
        try:
            launcher = load_module(
                package_name + ".launcher",
                ROOT / "src/lib/tartlabutils/launcher.py")
            launcher._arm_health_check()
            self.assertEqual(timers[0].timer_id, 3)
            self.assertEqual(timers[0].options["period"], 3000)
            self.assertEqual(timers[0].options["mode"], Timer.ONE_SHOT)

            timers[0].options["callback"](timers[0])

            self.assertEqual(healthy, ["APP"])
            self.assertEqual(logs, [
                "HEALTHY mode=APP update_committed=False"])
            self.assertEqual(timers[0].deinit_calls, 1)
            self.assertIsNone(launcher._health_timer)
        finally:
            sys.modules.pop(package_name + ".launcher", None)
            for name, previous in saved.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous


class ModernTouchscreenLauncherTests(unittest.TestCase):
    def load_launcher(self):
        package_name = "modern_launcher_test"
        package = types.ModuleType(package_name)
        package.__path__ = []
        state = types.ModuleType(package_name + ".state")
        state.get_selected_app = lambda: "games/hello.py"
        state.path_kind = lambda unused: 0
        state.save_selected_app = lambda unused: None

        def validate_selected_app(filename):
            if not isinstance(filename, str) or not filename.endswith(".py"):
                raise ValueError("invalid app")
            parts = filename.replace("\\", "/").split("/")
            if any(not part or part in (".", "..") for part in parts):
                raise ValueError("invalid app")
            for index, part in enumerate(parts):
                value = part[:-3] if index == len(parts) - 1 else part
                if not value.replace("_", "a").isalnum():
                    raise ValueError("invalid app")
            return filename

        state.validate_selected_app = validate_selected_app
        saved = {
            name: sys.modules.get(name)
            for name in (package_name, package_name + ".state")
        }
        sys.modules[package_name] = package
        sys.modules[package_name + ".state"] = state
        try:
            module = load_module(
                package_name + ".modern_launcher",
                ROOT / "src/lib/tartlabutils/modern_launcher.py")
        finally:
            for name, previous in saved.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
        return module

    class Widget:
        def __init__(self, parent=None):
            self.parent = parent
            self.children = []
            if parent is not None:
                parent.children.append(self)
            self.text = None
            self.size = None
            self.position = None
            self.callback = None
            self.deleted = False

        def set_style_bg_color(self, *unused):
            pass

        def set_text(self, value):
            self.text = value

        def set_width(self, unused):
            pass

        def set_style_text_align(self, *unused):
            pass

        def align(self, *unused):
            pass

        def center(self):
            pass

        def set_size(self, width, height):
            self.size = (width, height)

        def set_pos(self, x, y):
            self.position = (x, y)

        def add_event_cb(self, callback, *unused):
            self.callback = callback

        def delete(self):
            self.deleted = True

        def click(self):
            self.callback(None)

    class LVGL:
        ALIGN = types.SimpleNamespace(TOP_MID=1)
        EVENT = types.SimpleNamespace(CLICKED=2)
        TEXT_ALIGN = types.SimpleNamespace(CENTER=3)

        def __init__(self):
            self.active = ModernTouchscreenLauncherTests.Widget()
            self.loaded = []
            self.buttons = []

        def obj(self, parent=None):
            return ModernTouchscreenLauncherTests.Widget(parent)

        def label(self, parent):
            return ModernTouchscreenLauncherTests.Widget(parent)

        def button(self, parent):
            button = ModernTouchscreenLauncherTests.Widget(parent)
            self.buttons.append(button)
            return button

        def color_hex(self, value):
            return value

        def screen_active(self):
            return self.active

        def screen_load(self, screen):
            self.active = screen
            self.loaded.append(screen)

    def find_button(self, lvgl, text):
        def is_active(widget):
            current = widget
            while current is not None:
                if current.deleted:
                    return False
                current = current.parent
            return True

        for button in reversed(lvgl.buttons):
            if is_active(button) and any(
                    child.text == text for child in button.children):
                return button
        self.fail("button not found: " + text)

    def test_layout_keeps_large_targets_inside_landscape_and_portrait(self):
        module = self.load_launcher()
        for width, height in ((480, 222), (320, 480)):
            layout = module.launcher_layout(width, height)
            self.assertEqual(len(layout["buttons"]), 3)
            for x, y, button_width, button_height in layout["buttons"]:
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertGreaterEqual(button_height, 48)
                self.assertLessEqual(x + button_width, width)
                self.assertLessEqual(y + button_height, height)

    def test_no_interaction_defaults_to_ide_and_removes_launcher_screen(self):
        module = self.load_launcher()
        lvgl = self.LVGL()
        original = lvgl.active
        clock = {"now": 0}

        launcher = module.ModernTouchscreenLauncher(
            lvgl, 480, 222, "hello.py", timeout_seconds=10,
            ticks_ms=lambda: clock["now"],
            ticks_diff=lambda new, old: new - old,
            sleep_ms=lambda milliseconds: clock.__setitem__(
                "now", clock["now"] + milliseconds))
        route = launcher.run()

        self.assertEqual(route, "IDE")
        self.assertGreaterEqual(clock["now"], 10000)
        self.assertIs(lvgl.active, original)
        self.assertTrue(lvgl.loaded[0].deleted)

    def test_touch_unavailable_uses_the_same_nonblocking_ide_timeout(self):
        module = self.load_launcher()
        lvgl = self.LVGL()
        clock = {"now": 0}
        platform = types.SimpleNamespace(
            capabilities={"lvgl_ui": True, "touch": False},
            width=480,
            height=222,
            _lvgl=lvgl,
            enter_ui_mode=lambda: None,
        )
        original = module.ModernTouchscreenLauncher

        class FastLauncher(original):
            def __init__(self, *args, **kwargs):
                kwargs["ticks_ms"] = lambda: clock["now"]
                kwargs["ticks_diff"] = lambda new, old: new - old
                kwargs["sleep_ms"] = lambda milliseconds: clock.__setitem__(
                    "now", clock["now"] + milliseconds)
                super().__init__(*args, **kwargs)

        module.ModernTouchscreenLauncher = FastLauncher
        try:
            route = module.run_startup_launcher(platform, timeout_seconds=10)
        finally:
            module.ModernTouchscreenLauncher = original

        self.assertEqual(route, "IDE")
        self.assertGreaterEqual(clock["now"], 10000)

    def test_choose_app_cancels_timeout_until_an_explicit_route(self):
        module = self.load_launcher()
        lvgl = self.LVGL()
        clock = {"now": 0}

        def sleep_ms(milliseconds):
            clock["now"] += milliseconds
            if clock["now"] == 50:
                self.find_button(lvgl, "Choose app").click()
            if clock["now"] == 10500:
                self.find_button(lvgl, "Cancel").click()
                self.find_button(lvgl, "Run selected app").click()

        launcher = module.ModernTouchscreenLauncher(
            lvgl, 320, 480, "games/hello.py", timeout_seconds=10,
            ticks_ms=lambda: clock["now"],
            ticks_diff=lambda new, old: new - old,
            sleep_ms=sleep_ms)

        self.assertEqual(launcher.run(), "APP")
        self.assertGreater(clock["now"], 10000)

    def test_browser_is_confined_and_lists_only_launchable_candidates(self):
        module = self.load_launcher()
        listing = {
            "/files/user": [
                "games", "hello.py", "bad-name.py", "notes.txt", ".."],
            "/files/user/games": ["tetris.py"],
        }
        kinds = {
            "/files/user/games": 2,
            "/files/user/hello.py": 1,
            "/files/user/bad-name.py": 1,
            "/files/user/notes.txt": 1,
            "/files/user/games/tetris.py": 1,
        }
        folders, files = module.browser_entries(
            "", lambda path: listing[path], lambda path: kinds.get(path, 0))
        self.assertEqual(folders, (("games", "games"),))
        self.assertEqual(files, (("hello.py", "hello.py"),))
        with self.assertRaises(ValueError):
            module.browser_entries(
                "../escape", lambda path: listing[path],
                lambda path: kinds.get(path, 0))

    def test_file_confirmation_cancel_recheck_and_commit_workflow(self):
        module = self.load_launcher()
        lvgl = self.LVGL()
        listing = {
            "/files/user": ["games", "hello.py"],
            "/files/user/games": ["tetris.py"],
        }
        kinds = {
            "/files/user/games": 2,
            "/files/user/hello.py": 1,
            "/files/user/games/tetris.py": 1,
        }
        saved = []
        launcher = module.ModernTouchscreenLauncher(
            lvgl, 480, 222, "hello.py",
            list_directory=lambda path: listing[path],
            get_path_kind=lambda path: kinds.get(path, 0),
            validate_app=module.validate_selected_app,
            save_app=saved.append)
        launcher.show()

        self.find_button(lvgl, "Choose app").click()
        self.find_button(lvgl, "[Folder] games").click()
        self.find_button(lvgl, "tetris.py").click()
        self.find_button(lvgl, "Cancel").click()
        self.assertEqual(saved, [])

        self.find_button(lvgl, "tetris.py").click()
        kinds["/files/user/games/tetris.py"] = 0
        self.find_button(lvgl, "Set as app").click()
        self.assertEqual(saved, [])
        self.assertIn("no longer exists", launcher._status.text)

        kinds["/files/user/games/tetris.py"] = 1
        self.find_button(lvgl, "Set as app").click()
        self.assertEqual(saved, ["games/tetris.py"])
        self.assertEqual(launcher._selected_app, "games/tetris.py")
        self.find_button(lvgl, "Run selected app")
        launcher.close()


class HeadlessStartupTests(unittest.TestCase):
    runtime_number = 0

    @classmethod
    def next_name(cls, prefix):
        cls.runtime_number += 1
        return "%s_%s" % (prefix, cls.runtime_number)

    def load_state_runtime(self, device):
        package_name = self.next_name("headless_runtime")
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

    def load_main_definitions(self):
        services = types.ModuleType("tartlabutils")
        services.__path__ = []
        for name in (
                "default_settings", "diagnostics", "ensure_layout", "init_logs",
                "load_settings", "log", "log_exception", "mark_app_failed",
                "mark_boot_failed", "mark_boot_route_started", "save_settings"):
            setattr(services, name, lambda *args, **kwargs: None)
        platform_module = types.ModuleType("tartlabutils.platform")
        platform_module.get_platform = lambda: HeadlessPlatform()
        platform_module.set_platform = lambda platform: None

        saved_modules = {
            name: sys.modules.get(name)
            for name in ("tartlabutils", "tartlabutils.platform")
        }
        saved_path = list(sys.path)
        sys.modules["tartlabutils"] = services
        sys.modules["tartlabutils.platform"] = platform_module
        source = (ROOT / "src/main.py").read_text()
        self.assertTrue(source.rstrip().endswith("run()"))
        definitions = source.rsplit("\nrun()", 1)[0]
        module = types.ModuleType(self.next_name("headless_main"))
        try:
            exec(compile(definitions, "main.py", "exec"), module.__dict__)
        finally:
            sys.path[:] = saved_path
            for name, previous in saved_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
        return module

    def prepare(self, root):
        shutil.copytree(
            ROOT / "tests/fixtures/legacy_mp123/layout", root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        device = VirtualDeviceFS(root)
        state, bootstate = self.load_state_runtime(device)
        state.ensure_layout()
        main = self.load_main_definitions()
        logs = []
        errors = []
        main.ensure_layout = state.ensure_layout
        main.init_logs = lambda: None
        main.log = logs.append
        main.log_exception = errors.append
        main.diagnostics = lambda: {"event": "headless_startup"}
        main._ensure_repos = lambda: None
        main.load_settings = lambda: state.read_json(state.SETTINGS_FILE)
        main.default_settings = lambda: {"STARTUP_MODE": "BUTTON"}
        main.save_settings = lambda value: state.write_json(
            state.SETTINGS_FILE, value)
        main.mark_boot_failed = bootstate.mark_boot_failed
        main.mark_app_failed = bootstate.mark_app_failed
        main.mark_boot_route_started = bootstate.mark_boot_route_started
        main._restore_modern_brightness = lambda platform, settings: (
            platform.set_brightness(1.0)
            if platform.capabilities.get("lvgl_ui", False) else None)
        main.get_platform = lambda: self.fail(
            "An injected headless platform should be used")
        return device, state, bootstate, main, logs, errors

    def tartlab_repo(self, state):
        repos = state.read_json(state.REPOS_FILE)
        return next(item for item in repos["list"] if item["name"] == "TartLab")

    def test_headless_ide_startup_commits_pending_version_after_health(self):
        with tempfile.TemporaryDirectory() as temp:
            device, state, bootstate, main, logs, errors = self.prepare(
                Path(temp) / "device")
            state.begin_update("TartLab", "v0.13", "headless-candidate")
            state.set_update_pending_health()
            platform = HeadlessPlatform(ide_button_value=1)
            routes = []

            main.run(
                platform=platform,
                start_ide=lambda: (
                    routes.append("IDE"), bootstate.mark_boot_healthy("IDE")),
                start_app=lambda: routes.append("APP"),
                start_recovery=lambda reason: routes.append("RECOVERY:" + reason),
            )

            self.assertEqual(routes, ["IDE"])
            self.assertEqual(platform.display.fills, [0])
            self.assertEqual(errors, [])
            self.assertIn("Starting IDE", logs)
            self.assertEqual(
                self.tartlab_repo(state)["installed_version"],
                "headless-candidate")
            self.assertIsNone(state.get_update_state())
            self.assertEqual(
                state.read_json(state.BOOT_STATE_FILE)["health"], "healthy")

    def test_headless_button_can_select_and_health_check_app_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, bootstate, main, logs, errors = self.prepare(
                Path(temp) / "device")
            platform = HeadlessPlatform(ide_button_value=0)
            routes = []

            main.run(
                platform=platform,
                start_ide=lambda: routes.append("IDE"),
                start_app=lambda: (
                    routes.append("APP"), bootstate.mark_boot_healthy("APP")),
                start_recovery=lambda reason: routes.append("RECOVERY:" + reason),
            )

            self.assertEqual(routes, ["APP"])
            self.assertEqual(errors, [])
            self.assertIn("Starting APP", logs)
            boot = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual((boot["health"], boot["mode"]), ("healthy", "APP"))

    def test_modern_profile_always_uses_touch_launcher_for_ide_or_app(self):
        for configured_mode, launcher_route in (("BUTTON", "IDE"),
                                                 ("IDE", "APP"),
                                                 ("APP", "IDE")):
            with self.subTest(configured_mode=configured_mode):
                with tempfile.TemporaryDirectory() as temp:
                    unused_device, state, unused_bootstate, main, logs, errors = \
                        self.prepare(Path(temp) / "device")
                    settings = state.read_json(state.SETTINGS_FILE)
                    settings["STARTUP_MODE"] = configured_mode
                    state.write_json(state.SETTINGS_FILE, settings)
                    platform = HeadlessPlatform(ide_button_value=0)
                    platform.capabilities["lvgl_ui"] = True
                    platform.ide_button_value = lambda: self.fail(
                        "modern startup must not read the IDE button")
                    routes = []

                    main.run(
                        platform=platform,
                        start_launcher=lambda selected_platform: (
                            routes.append("LAUNCHER"), launcher_route)[1],
                        start_ide=lambda: routes.append("IDE"),
                        start_app=lambda: routes.append("APP"),
                        start_recovery=lambda reason: routes.append(reason),
                    )

                    self.assertEqual(routes, ["LAUNCHER", launcher_route])
                    self.assertEqual(errors, [])
                    self.assertEqual(
                        state.read_json(state.SETTINGS_FILE)["STARTUP_MODE"],
                        "BUTTON")

    def test_modern_recovery_precedes_and_bypasses_touch_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, unused_bootstate, main, unused_logs, errors = \
                self.prepare(Path(temp) / "device")
            settings = state.read_json(state.SETTINGS_FILE)
            settings["STARTUP_MODE"] = "RECOVERY"
            state.write_json(state.SETTINGS_FILE, settings)
            platform = HeadlessPlatform()
            platform.capabilities["lvgl_ui"] = True
            routes = []

            main.run(
                platform=platform,
                start_launcher=lambda unused: self.fail(
                    "recovery must bypass the launcher"),
                start_ide=lambda: routes.append("IDE"),
                start_app=lambda: routes.append("APP"),
                start_recovery=lambda reason: routes.append(reason),
            )

            self.assertEqual(routes, ["startup_mode"])
            self.assertEqual(errors, [])

    def test_modern_app_failure_restores_brightness_and_falls_back_to_ide(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, unused_bootstate, main, logs, \
                errors = self.prepare(Path(temp) / "device")
            platform = HeadlessPlatform()
            platform.capabilities["lvgl_ui"] = True
            platform.display.brightness = 0.2
            routes = []

            def fail_app():
                self.assertEqual(platform.display.brightness, 1.0)
                raise RuntimeError("synthetic modern APP failure")

            main.run(
                platform=platform,
                start_launcher=lambda unused: "APP",
                start_ide=lambda: routes.append("IDE"),
                start_app=fail_app,
                start_recovery=lambda reason: routes.append(reason),
            )

            self.assertEqual(routes, ["IDE"])
            self.assertEqual(platform.display.brightness, 1.0)
            self.assertEqual(platform.display.fills, [0])
            self.assertEqual(len(errors), 1)
            self.assertIn("Selected APP failed; falling back to IDE", logs)
            boot = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(boot["mode"], "IDE")
            self.assertEqual(boot["consecutive_failures"], 0)
            self.assertIn("synthetic modern APP failure", boot["app_error"])

    def test_app_and_fallback_ide_failure_routes_to_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, unused_bootstate, main, unused_logs, errors = \
                self.prepare(Path(temp) / "device")
            platform = HeadlessPlatform()
            platform.capabilities["lvgl_ui"] = True
            routes = []

            def fail_app():
                raise RuntimeError("synthetic APP failure")

            def fail_ide():
                raise RuntimeError("synthetic fallback IDE failure")

            main.run(
                platform=platform,
                start_launcher=lambda unused: "APP",
                start_ide=fail_ide,
                start_app=fail_app,
                start_recovery=lambda reason: routes.append(reason),
            )

            self.assertEqual(routes, ["startup_error"])
            self.assertEqual(len(errors), 2)
            boot = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(boot["health"], "failed")
            self.assertEqual(boot["mode"], "IDE")
            self.assertIn("fallback IDE failure", boot["error"])

    def test_explicit_recovery_mode_is_one_shot_without_hardware(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, unused_bootstate, main, unused_logs, errors = \
                self.prepare(Path(temp) / "device")
            settings = state.read_json(state.SETTINGS_FILE)
            settings["STARTUP_MODE"] = "RECOVERY"
            state.write_json(state.SETTINGS_FILE, settings)
            routes = []

            main.run(
                platform=HeadlessPlatform(),
                start_ide=lambda: routes.append("IDE"),
                start_app=lambda: routes.append("APP"),
                start_recovery=lambda reason: routes.append(reason),
            )

            self.assertEqual(routes, ["startup_mode"])
            self.assertEqual(errors, [])
            self.assertEqual(
                state.read_json(state.SETTINGS_FILE)["STARTUP_MODE"], "BUTTON")

    def test_startup_failure_marks_boot_and_routes_to_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, unused_bootstate, main, unused_logs, errors = \
                self.prepare(Path(temp) / "device")
            platform = HeadlessPlatform(ide_button_value=1)
            routes = []

            def fail_ide():
                raise RuntimeError("synthetic headless IDE failure")

            main.run(
                platform=platform,
                start_ide=fail_ide,
                start_app=lambda: routes.append("APP"),
                start_recovery=lambda reason: routes.append(reason),
            )

            self.assertEqual(routes, ["startup_error"])
            self.assertEqual(platform.display.fills, [0, 0xF800])
            self.assertEqual(len(errors), 1)
            boot = state.read_json(state.BOOT_STATE_FILE)
            self.assertEqual(boot["health"], "failed")
            self.assertIn("synthetic headless IDE failure", boot["error"])


if __name__ == "__main__":
    unittest.main()
