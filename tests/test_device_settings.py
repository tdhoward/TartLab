import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest.mock import patch

from tests import test_headless_ide as headless
from tests.test_power import load_power_module
from tests import test_platform as platform_tests
from tests import test_phase2 as update_tests


ROOT = Path(__file__).resolve().parents[1]


def load_settings_ui():
    spec = importlib.util.spec_from_file_location(
        'device_settings_under_test', ROOT / 'src/ide/device_settings.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Widget(platform_tests.ModernTouchscreenLauncherTests.Widget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = set()

    def set_style_text_color(self, *unused):
        pass

    def set_width(self, width):
        self.width = width

    def add_state(self, state):
        self.states.add(state)

    def remove_state(self, state):
        self.states.discard(state)


class LVGL(platform_tests.ModernTouchscreenLauncherTests.LVGL):
    DIR = types.SimpleNamespace(VER=4, NONE=0)
    STATE = types.SimpleNamespace(DISABLED=1)
    obj = Widget
    label = Widget

    def button(self, parent):
        button = Widget(parent)
        self.buttons.append(button)
        return button


async def immediate_sleep(unused_delay):
    pass


class DeviceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        fixture = headless.HeadlessIDEInitializationTests()
        self.device, self.state, self.platform, self.ide, unused_logs, self.errors = \
            fixture.prepare(Path(self.temp.name) / 'device')
        self.lv = LVGL()
        self.power = load_power_module()
        self.ui = load_settings_ui().DeviceSettings(
            self.lv, 320, 480,
            lambda: self.power.modern_ui_settings(self.ide.settings),
            self.ide.save_display_settings,
            lambda: list(self.ide.settings['wifi_ssids']),
            self.ide.forget_wifi_network,
            lambda: [(repo['name'], repo['installed_version'])
                     for repo in self.ide.repos['list']],
            self.ide.check_device_updates, self.ide.install_device_updates,
            self.errors.append)
        self.addCleanup(self.ui.close)

    def click(self, text):
        for button in reversed(self.ui._buttons):
            if any(child.text == text for child in button.children):
                button.click()
                self.pump()
                return
        self.fail('Button missing: ' + text)

    def pump(self):
        action, value = self.ui._pending
        self.ui._pending = None
        asyncio.run(self.ui.dispatch(action, value, types.SimpleNamespace(sleep=immediate_sleep)))

    def open_settings(self):
        self.ui._entry.click()
        self.pump()

    def test_save_persists_only_display_fields_and_applies_immediately(self):
        self.ide.settings['modern_ui'] = {'dim_brightness': 0.15, 'future': 'keep'}
        before = dict(self.ide.settings)
        self.open_settings()
        self.ui._queue('brightness', -1)
        self.pump()
        self.ui._queue('timeout', -1)
        self.pump()
        self.assertEqual(self.ide.settings, before)
        self.click('Save')
        stored = self.state.read_json(self.state.SETTINGS_FILE)
        self.assertEqual(stored['modern_ui'], {
            'max_brightness': 0.9, 'auto_dim_seconds': 60,
            'dim_brightness': 0.15, 'future': 'keep'})
        self.assertEqual(self.platform.display.brightness, 0.9)
        self.assertEqual({key: value for key, value in stored.items() if key != 'modern_ui'},
                         {key: value for key, value in before.items() if key != 'modern_ui'})
        self.click('Back')
        self.open_settings()
        self.assertEqual(self.ui._brightness, 0.9)
        self.assertEqual(self.ui._timeout, 60)

    def test_save_failure_preserves_memory_disk_and_brightness(self):
        before = json.dumps(self.ide.settings)
        disk_before = self.device.host_path(self.state.SETTINGS_FILE).read_bytes()
        self.open_settings()
        self.ui._queue('brightness', -1)
        self.pump()
        with patch.object(self.ide, 'save_settings', side_effect=OSError('disk full')):
            self.click('Save')
        self.assertEqual(json.dumps(self.ide.settings), before)
        self.assertEqual(self.device.host_path(self.state.SETTINGS_FILE).read_bytes(), disk_before)
        self.assertEqual(self.platform.display.brightness, 1)
        self.assertIn('Could not save', self.ui._status.text)

    def test_forget_selected_network_keeps_credentials_paired_and_wifi_connected(self):
        self.ide.settings['wifi_ssids'] += ['second', 'third']
        self.ide.settings['wifi_passwords'] += ['second-key', 'third-key']
        self.open_settings()
        self.click('WiFi')
        self.click('second')
        self.assertIn('second', self.ide.settings['wifi_ssids'])
        self.click('Back')
        self.click('second')
        self.click('Forget this network')
        stored = self.state.read_json(self.state.SETTINGS_FILE)
        self.assertEqual(stored['wifi_ssids'], ['SYNTHETIC_CLASSROOM', 'third'])
        self.assertEqual(stored['wifi_passwords'], ['not-a-real-password', 'third-key'])
        self.assertTrue(self.platform.station.isconnected())
        self.click('SYNTHETIC_CLASSROOM')
        self.click('Forget this network')
        self.assertTrue(self.platform.station.isconnected())

    def test_browser_forget_uses_same_transaction_and_missing_ssid_is_404(self):
        writer = types.SimpleNamespace(responses=[])
        request = types.SimpleNamespace(path='/api/remove_ssid/SYNTHETIC_CLASSROOM')
        with patch.object(self.ide, 'save_settings', side_effect=OSError('disk full')):
            asyncio.run(self.ide.api_remove_ssid(None, writer, request))
        self.assertEqual(writer.responses[-1][0], 400)
        self.assertEqual(self.ide.settings['wifi_ssids'], ['SYNTHETIC_CLASSROOM'])
        asyncio.run(self.ide.api_remove_ssid(None, writer, request))
        self.assertEqual(writer.responses[-1][0], 200)
        asyncio.run(self.ide.api_remove_ssid(None, writer, request))
        self.assertEqual(writer.responses[-1][0], 404)

    def test_update_check_confirmation_and_install_use_existing_services(self):
        calls = []
        async def check(repo, raise_errors=False):
            self.assertTrue(raise_errors)
            self.assertTrue(self.ide.updates_in_progress)
            self.ui._entry.click()
            self.assertIsNone(self.ui._pending)
            return [{'name': 'manifest.json'}], 'v99'
        async def install(callback):
            self.assertTrue(self.ide.updates_in_progress)
            calls.append('install')
            callback('Downloading', 2, 5)
            self.assertIn('Downloading', self.ui._status.text)
        self.ide.check_for_update = check
        self.ide.main_update_routine = install
        self.ide.device_settings = self.ui
        self.open_settings()
        self.click('Updates')
        self.click('Check now')
        self.assertEqual(self.ui._status.text, 'Updates available.')
        self.click('Install update')
        self.assertEqual(calls, [])
        self.click('Back')
        self.click('Install update')
        self.click('Update and restart')
        self.assertEqual(calls, ['install'])
        self.assertFalse(self.ide.updates_in_progress)
        self.assertFalse(self.ui._busy)

    def test_offline_and_failed_checks_are_retryable_not_up_to_date(self):
        self.open_settings()
        self.click('Updates')
        self.ide.softAP = True
        self.click('Check now')
        self.assertIn('Connect to WiFi', self.ui._status.text)
        self.ide.softAP = False
        async def fail(*args, **kwargs):
            raise OSError('Network unavailable')
        self.ide.check_for_update = fail
        self.click('Check now')
        self.assertIn('Network unavailable', self.ui._status.text)
        self.assertFalse(self.ide.updates_in_progress)
        self.assertFalse(self.ui._busy)
        async def no_update(*args, **kwargs):
            return None, None
        self.ide.check_for_update = no_update
        self.click('Check now')
        self.assertEqual(self.ui._status.text, 'You are up to date.')
        self.assertFalse(any(child.text == 'Install update'
                             for button in self.ui._buttons for child in button.children))

    def test_shared_update_guard_rejects_browser_and_device_duplicates(self):
        self.ide.updates_in_progress = True
        for action in (self.ide.check_device_updates, self.ide.install_device_updates):
            with self.assertRaisesRegex(ValueError, 'in progress'):
                asyncio.run(action())
        writer = types.SimpleNamespace(responses=[])
        for route in (self.ide.api_check_updates, self.ide.api_do_updates):
            asyncio.run(route(None, writer, None))
            self.assertEqual(writer.responses[-1][0], 400)
        self.assertTrue(self.ide.updates_in_progress)

    def test_browser_update_check_preserves_asset_version_response(self):
        assets = [{'name': 'manifest.json'}]
        async def check(repo, raise_errors=False):
            return assets, 'v99'
        async def drain():
            pass
        response = types.SimpleNamespace(send=lambda unused: drain())
        output = []
        writer = types.SimpleNamespace(write=output.append, drain=drain)
        self.ide.check_for_update = check
        self.ide.HTTPResponse = lambda *args, **kwargs: response
        asyncio.run(self.ide.api_check_updates(None, writer, types.SimpleNamespace(path='/api/checkupdates')))
        self.assertEqual(json.loads(output[0]), [[assets, 'v99']])

    def test_install_failure_releases_lock_and_restores_navigation(self):
        async def fail(callback):
            raise OSError('Update failed')
        self.ide.main_update_routine = fail
        self.open_settings()
        self.ui._queue('install')
        self.pump()
        self.assertEqual(self.ui._status.text, 'Update failed')
        self.assertFalse(self.ide.updates_in_progress)
        self.click('Back')
        self.assertEqual(self.ui._page, 'settings')

    def test_creation_is_gated_by_touch_and_lvgl_and_uses_live_settings(self):
        self.assertIsNone(self.ide.create_device_settings())
        package = types.ModuleType('device_settings_fixture')
        package.__path__ = []
        replacements = {
            'device_settings_fixture': package,
            'device_settings_fixture.device_settings': load_settings_ui(),
            'tartlabutils.power': self.power,
        }
        self.ide.__package__ = 'device_settings_fixture'
        self.platform.capabilities['lvgl_ui'] = True
        self.platform.lvgl = self.lv
        with patch.dict(sys.modules, replacements):
            created = self.ide.create_device_settings()
        try:
            self.ide.settings = dict(self.ide.settings, modern_ui={'max_brightness': 0.4})
            self.assertEqual(created._get_display()['max_brightness'], 0.4)
        finally:
            created.close()
        self.platform.capabilities['touch'] = False
        self.assertIsNone(self.ide.create_device_settings())

    def test_navigation_queues_callbacks_and_deletes_old_screens(self):
        home = self.lv.active
        self.ui._entry.click()
        self.assertIs(self.lv.active, home)
        self.pump()
        for unused in range(10):
            settings_screen = self.lv.active
            self.click('WiFi')
            self.assertTrue(settings_screen.deleted)
            wifi_screen = self.lv.active
            self.click('Back')
            self.assertTrue(wifi_screen.deleted)
        self.assertEqual(len(self.ui._callbacks), len(self.ui._buttons))
        self.click('Back')
        self.assertIs(self.lv.active, home)
        self.assertIsNone(self.ui._screen)

    def test_invalid_display_input_does_not_write_settings(self):
        before = dict(self.ide.settings)
        for brightness, timeout in ((0, 180), (2, 180), (True, 180),
                                    (float('nan'), 180), (0.5, -1),
                                    (0.5, float('inf')), (0.5, True)):
            with self.assertRaises(ValueError):
                self.ide.save_display_settings(brightness, timeout)
        self.assertEqual(self.ide.settings, before)

    def test_scrollable_pages_fit_landscape_and_portrait(self):
        for width, height in ((480, 222), (320, 480)):
            self.ui._width, self.ui._height = width, height
            self.open_settings()
            x, y = self.ui._body.position
            w, h = self.ui._body.size
            self.assertLessEqual(x + w, width)
            self.assertLessEqual(y + h, height)
            self.assertEqual(self.ui._body.scroll_dir, self.lv.DIR.VER)
            for button in self.ui._buttons:
                self.assertLessEqual(button.position[0] + button.size[0], width - 16)
                if button.parent is self.ui._body:
                    self.assertLessEqual(button.position[1] + button.size[1], h)
            self.click('Back')


class UpdateCheckReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        update_tests.UpdaterFailureInjectionTests.setUpClass()
        cls.updater = update_tests.UpdaterFailureInjectionTests.updater

    def test_failed_release_requests_raise_only_when_requested_and_close_response(self):
        repo = {'name': 'TartLab', 'repo': 'tdhoward/TartLab', 'installed_version': 'v0.13'}
        for status in (403, 500):
            closed = []
            response = types.SimpleNamespace(status_code=status, close=lambda: closed.append(True))
            with patch.object(self.updater, 'urequests', types.SimpleNamespace(get=lambda *args, **kwargs: response)):
                self.assertEqual(asyncio.run(self.updater.check_for_update(repo)), (None, None))
                with self.assertRaisesRegex(OSError, 'HTTP %s' % status):
                    asyncio.run(self.updater.check_for_update(repo, raise_errors=True))
            self.assertEqual(closed, [True, True])

    def test_network_failure_and_successful_no_update_are_distinct(self):
        repo = {'name': 'TartLab', 'repo': 'tdhoward/TartLab', 'installed_version': 'v0.13'}
        with patch.object(self.updater.urequests, 'get', side_effect=OSError('offline')):
            with self.assertRaisesRegex(OSError, 'offline'):
                asyncio.run(self.updater.check_for_update(repo, raise_errors=True))
        response = types.SimpleNamespace(
            status_code=200, json=lambda: [{'tag_name': 'v0.13'}], close=lambda: None)
        with patch.object(self.updater, 'urequests', types.SimpleNamespace(get=lambda *args, **kwargs: response)):
            self.assertEqual(asyncio.run(self.updater.check_for_update(repo, raise_errors=True)), (None, None))


if __name__ == '__main__':
    unittest.main()

