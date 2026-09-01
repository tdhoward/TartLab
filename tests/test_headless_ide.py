import asyncio
from contextlib import redirect_stdout
import gc
import importlib.util
import io
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("ujson", json)

from tests.headless_platform import HeadlessPlatform
from tests.virtual_device import VirtualDeviceFS


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeHTTPServer:
    def __init__(self, host="0.0.0.0", port=80, *args, **kwargs):
        self.host = host
        self.port = port
        self.routes = {}
        self.started = False

    def route(self, method="GET", path="/"):
        def register(function):
            self.routes[(method, path)] = function
            return function
        return register

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False


class FakeHTTPResponse:
    def __init__(self, *args, **kwargs):
        pass


class HeadlessIDEInitializationTests(unittest.TestCase):
    runtime_number = 0

    @classmethod
    def next_name(cls, prefix):
        cls.runtime_number += 1
        return "%s_%s" % (prefix, cls.runtime_number)

    def load_state_runtime(self, device):
        package_name = self.next_name("headless_ide_runtime")
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

    def fake_http_modules(self):
        package = types.ModuleType("ahttpserver")
        package.__path__ = []
        package.HTTPResponse = FakeHTTPResponse
        package.HTTPServer = FakeHTTPServer

        sse = types.ModuleType("ahttpserver.sse")
        sse.EventSource = type("EventSource", (), {})
        servefile = types.ModuleType("ahttpserver.servefile")
        async def serve_file_response(*args, **kwargs):
            return None
        servefile.serve_file = serve_file_response
        response = types.ModuleType("ahttpserver.response")
        async def send_http_response(writer, status, message, msgkey=''):
            writer.responses.append((status, message, msgkey))
        response.sendHTTPResponse = send_http_response
        multipart = types.ModuleType("ahttpserver.multipart")
        async def handle_multipart(
                reader, writer, request, folder, timeout=30,
                validate_filename=None):
            if validate_filename is not None:
                validate_filename(request.upload_filename)
        multipart.handleMultipartUpload = handle_multipart
        server = types.ModuleType("ahttpserver.server")
        server.HTTPServerError = type("HTTPServerError", (Exception,), {})
        return {
            "ahttpserver": package,
            "ahttpserver.sse": sse,
            "ahttpserver.servefile": servefile,
            "ahttpserver.response": response,
            "ahttpserver.multipart": multipart,
            "ahttpserver.server": server,
        }

    def load_ide(self, device, state, bootstate, platform):
        logs = []
        errors = []
        services = types.ModuleType("tartlabutils")
        services.__path__ = []
        services.file_exists = state.path_kind
        services.unquote = lambda value: value
        services.rmvdir = lambda path: None

        async def no_update(*args, **kwargs):
            return None

        services.check_for_update = no_update
        services.main_update_routine = no_update
        services.log = logs.append
        services.repl_exception = lambda *args, **kwargs: None
        services.log_exception = errors.append
        services.get_logs = lambda: []
        services.load_settings = lambda: state.read_json(state.SETTINGS_FILE)
        services.save_settings = lambda value: state.write_json(
            state.SETTINGS_FILE, value)
        services.default_settings = lambda: {"STARTUP_MODE": "BUTTON"}
        services.get_app_failure = bootstate.get_app_failure
        services.get_selected_app = state.get_selected_app
        services.save_selected_app = state.save_selected_app
        services.validate_selected_app = state.validate_selected_app
        services.mark_boot_healthy = bootstate.mark_boot_healthy

        state_alias = types.ModuleType("tartlabutils.state")
        state_alias.REPOS_FILE = state.REPOS_FILE
        platform_alias = types.ModuleType("tartlabutils.platform")
        platform_alias.get_platform = lambda: platform

        replacements = {
            "os": device.os,
            "uasyncio": asyncio,
            "tartlabutils": services,
            "tartlabutils.state": state_alias,
            "tartlabutils.platform": platform_alias,
            **self.fake_http_modules(),
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        source = (ROOT / "src/ide/ide.py").read_text()
        module = types.ModuleType(self.next_name("headless_ide"))
        module.open = device.open
        # Ensure these standard modules are already loaded before ``os`` is
        # temporarily replaced for the IDE module under test.
        unused = (gc, io, random)
        try:
            sys.modules.update(replacements)
            with redirect_stdout(io.StringIO()):
                exec(compile(source, "ide.py", "exec"), module.__dict__)
        finally:
            for name, old_module in previous.items():
                if old_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old_module
        return module, logs, errors

    def prepare(self, root, *, wifi=True, app_error=None):
        shutil.copytree(
            ROOT / "tests/fixtures/legacy_mp123/layout", root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        device = VirtualDeviceFS(root)
        state, bootstate = self.load_state_runtime(device)
        state.ensure_layout()
        if app_error is not None:
            bootstate.mark_app_failed(app_error)
        if not wifi:
            settings = state.read_json(state.SETTINGS_FILE)
            settings["wifi_ssids"] = []
            settings["wifi_passwords"] = []
            state.write_json(state.SETTINGS_FILE, settings)
        networks = [
            (b"SYNTHETIC_CLASSROOM", b"\0" * 6, 1, -30, 0, False),
        ] if wifi else []
        platform = HeadlessPlatform(
            networks=networks, station_address="10.0.0.42")
        module, logs, errors = self.load_ide(
            device, state, bootstate, platform)
        return device, state, platform, module, logs, errors

    def test_previous_app_failure_adds_ide_status_indicator(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, platform, unused_ide, unused_logs, \
                errors = self.prepare(
                    Path(temp) / "device", app_error="student app failed")

            self.assertEqual(errors, [])
            self.assertEqual(platform.ide_view.events[:3], [
                ("startup", "v0.13"),
                ("app_error",),
                ("network", "SYNTHETIC_CLASSROOM", "10.0.0.42",
                 "tartlab-fixture"),
            ])

    def test_real_ide_initializes_routes_station_and_view_headlessly(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, platform, ide, unused_logs, errors = self.prepare(
                Path(temp) / "device")

            self.assertEqual(errors, [])
            self.assertFalse(ide.softAP)
            self.assertEqual(ide.ip_address, "10.0.0.42")
            self.assertEqual(platform.hostname, "tartlab-fixture")
            self.assertEqual(platform.station.connection_attempts, [
                ("SYNTHETIC_CLASSROOM", "not-a-real-password"),
            ])
            self.assertEqual(platform.sleeps, [1])
            self.assertEqual(platform.ide_view.events[:2], [
                ("startup", "v0.13"),
                ("network", "SYNTHETIC_CLASSROOM", "10.0.0.42",
                 "tartlab-fixture"),
            ])
            self.assertEqual((ide.app.host, ide.app.port), ("10.0.0.42", 80))
            self.assertGreaterEqual(len(ide.app.routes), 20)
            self.assertIn(("GET", "/api/space"), ide.app.routes)
            self.assertIn(("POST", "/api/doupdates"), ide.app.routes)
            self.assertEqual(
                state.read_json(state.SETTINGS_FILE)["hostname"],
                "tartlab-fixture")

            ide.show_update_progress("Installing", 4, 3)
            self.assertEqual(
                platform.ide_view.events[-1],
                ("update", "Installing", 4, 4))

    def test_real_ide_falls_back_to_open_access_point_headlessly(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, platform, ide, unused_logs, errors = \
                self.prepare(Path(temp) / "device", wifi=False)

            self.assertEqual(errors, [])
            self.assertTrue(ide.softAP)
            self.assertEqual(ide.wifi_ssid, "PySyntheticDevice42")
            self.assertEqual(platform.access_point.configuration, {
                "essid": "PySyntheticDevice42",
                "authmode": "open",
            })
            self.assertTrue(platform.access_point.enabled)
            self.assertEqual(platform.ide_view.events[:2], [
                ("startup", "v0.13"),
                ("network", "PySyntheticDevice42", "192.168.4.1", None),
            ])

    def test_healthy_update_refreshes_display_and_in_memory_version(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, state, platform, ide, logs, errors = self.prepare(
                Path(temp) / "device")
            state.begin_update("TartLab", "v0.13", "v0.14")
            state.set_update_pending_health()

            asyncio.run(ide.start_ide_server())

            self.assertTrue(ide.app.started)
            self.assertEqual(platform.ide_view.events[-1], ("startup", "v0.14"))
            self.assertEqual(ide.version, "v0.14")
            self.assertEqual(ide.repos["list"][0]["installed_version"], "v0.14")
            self.assertIn("HEALTHY mode=IDE update_committed=True", logs)
            self.assertEqual(errors, [])

    def test_python_file_paths_follow_selected_app_naming_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, unused_platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")

            self.assertEqual(
                ide.validate_user_python_path(
                    "/files/user/games/testris_original.py"),
                "games/testris_original.py")
            self.assertEqual(
                ide.validate_user_python_path(
                    "/files/user/assets/title.screen.png"),
                "/files/user/assets/title.screen.png")
            with self.assertRaisesRegex(ValueError, "App names"):
                ide.validate_user_python_path(
                    "/files/user/games/testris.original.py")
            with self.assertRaisesRegex(ValueError, "App names"):
                ide.validate_user_python_path(
                    "/files/user/my-games/testris.py")

    def test_file_endpoints_explain_and_reject_unsafe_python_names(self):
        with tempfile.TemporaryDirectory() as temp:
            device, unused_state, unused_platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")

            writer = types.SimpleNamespace(responses=[])
            request = types.SimpleNamespace(
                path="/files/user/testris.original.py",
                body=json.dumps({"content": "print('unsafe')"}).encode())
            asyncio.run(ide.store_user_file(None, writer, request))
            self.assertEqual(writer.responses[0][0], 400)
            self.assertEqual(
                writer.responses[0][1],
                "App names: letters, digits, _ only.")
            self.assertFalse(
                device.host_path("/files/user/testris.original.py").exists())

            source = device.host_path("/files/user/rename_source.py")
            source.write_text("print('safe')")
            writer.responses = []
            request = types.SimpleNamespace(
                path="/api/files/move",
                body=json.dumps({
                    "src": "rename_source.py",
                    "dest": "renamed.app.py",
                }).encode())
            asyncio.run(ide.api_move_file(None, writer, request))
            self.assertEqual(writer.responses[0][0], 400)
            self.assertEqual(
                writer.responses[0][1],
                "App names: letters, digits, _ only.")
            self.assertTrue(source.exists())

            legacy_name = device.host_path(
                "/files/user/testris.original.py")
            legacy_name.write_text("print('preserved legacy file')")
            writer.responses = []
            request = types.SimpleNamespace(
                path="/api/setasapp",
                body=json.dumps({"filename": "testris.original.py"}).encode())
            asyncio.run(ide.api_setasapp(None, writer, request))
            self.assertEqual(writer.responses[0][0], 400)
            self.assertEqual(
                writer.responses[0][1],
                "App names: letters, digits, _ only.")

            writer.responses = []
            request = types.SimpleNamespace(
                path="/api/files/upload/",
                upload_filename="uploaded.app.py")
            asyncio.run(ide.api_upload_file(None, writer, request))
            self.assertEqual(writer.responses[0][0], 400)
            self.assertEqual(
                writer.responses[0][1],
                "App names: letters, digits, _ only.")

    def test_runtime_brightness_button_uses_platform_input_and_view(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, platform, ide, unused_logs, unused_errors = \
                self.prepare(Path(temp) / "device")
            platform.queue_ide_button_values(0, 1)

            class StopButtonTask(Exception):
                pass

            async def stop_after_iteration(delay):
                raise StopButtonTask()

            ide.asyncio = types.SimpleNamespace(sleep=stop_after_iteration)
            with self.assertRaises(StopButtonTask):
                asyncio.run(ide.check_buttons())

            self.assertEqual(platform.display.brightness, 0.75)
            self.assertEqual(
                platform.ide_view.events[-1], ("brightness", 0.75))

    def test_file_execution_wakes_the_modern_backlight_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")
            platform.capabilities["lvgl_ui"] = True

            class FakePowerController:
                def __init__(self):
                    self.wake_calls = 0

                def wake(self):
                    self.wake_calls += 1

            controller = FakePowerController()
            ide.power_controller = controller
            ide.os = types.SimpleNamespace(dupterm=lambda unused_stream: None)

            ide.pseudoREPL("pass", "student_app.py")
            ide.pseudoREPL("pass", "console")

            self.assertEqual(controller.wake_calls, 1)

    def test_modern_ide_schedules_power_policy_not_button_polling(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")
            platform.capabilities["lvgl_ui"] = True

            class FakeTask:
                def __init__(self, coroutine):
                    self.coroutine = coroutine
                    self.cancelled = False

                def cancel(self):
                    self.cancelled = True
                    self.coroutine.close()

            class FakeLoop:
                def __init__(self):
                    self.tasks = []

                def set_exception_handler(self, handler):
                    self.handler = handler

                def create_task(self, coroutine):
                    task = FakeTask(coroutine)
                    self.tasks.append(task)
                    return task

                def run_forever(self):
                    raise KeyboardInterrupt()

            class FakePowerController:
                instances = []

                def __init__(self, selected_platform, settings):
                    self.platform = selected_platform
                    self.settings = settings
                    self.stop_calls = 0
                    self.instances.append(self)

                async def run(self, asyncio_module):
                    return asyncio_module

                def stop(self):
                    self.stop_calls += 1

            loop = FakeLoop()
            ide.asyncio = types.SimpleNamespace(
                get_event_loop=lambda: loop,
                run=asyncio.run,
                new_event_loop=lambda: None,
            )
            package = types.ModuleType("tartlabutils")
            package.__path__ = []
            power = types.ModuleType("tartlabutils.modern_power")
            power.ModernIDEBacklightController = FakePowerController
            previous = {
                name: sys.modules.get(name)
                for name in ("tartlabutils", "tartlabutils.modern_power")
            }
            try:
                sys.modules["tartlabutils"] = package
                sys.modules["tartlabutils.modern_power"] = power
                ide.main()
            finally:
                for task in loop.tasks:
                    if not task.cancelled:
                        task.coroutine.close()
                for name, old_module in previous.items():
                    if old_module is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = old_module

            task_names = [
                task.coroutine.cr_code.co_name for task in loop.tasks]
            self.assertNotIn("check_buttons", task_names)
            self.assertIn("free_memory_task", task_names)
            self.assertIn("start_ide_server", task_names)
            self.assertEqual(len(FakePowerController.instances), 1)
            self.assertEqual(FakePowerController.instances[0].stop_calls, 1)
            self.assertTrue(loop.tasks[0].cancelled)

    def test_cleanup_does_not_cancel_the_current_power_task(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, unused_platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")

            class FakeTask:
                def __init__(self):
                    self.cancel_calls = 0

                def cancel(self):
                    self.cancel_calls += 1

            current = FakeTask()
            background = FakeTask()
            ide.asyncio = types.SimpleNamespace(current_task=lambda: current)

            ide._cancel_background_task(current)
            ide._cancel_background_task(background)

            self.assertEqual(current.cancel_calls, 0)
            self.assertEqual(background.cancel_calls, 1)

    def test_cleanup_tolerates_pinned_runtime_self_cancel_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            unused_device, unused_state, unused_platform, ide, unused_logs, \
                unused_errors = self.prepare(Path(temp) / "device")

            class SelfTask:
                def cancel(self):
                    raise RuntimeError("can't cancel self")

            ide.asyncio = types.SimpleNamespace()
            ide._cancel_background_task(SelfTask())

            class BrokenTask:
                def cancel(self):
                    raise RuntimeError("unexpected cancellation failure")

            with self.assertRaisesRegex(
                    RuntimeError, "unexpected cancellation failure"):
                ide._cancel_background_task(BrokenTask())


if __name__ == "__main__":
    unittest.main()
