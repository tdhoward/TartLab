"""Page focus/cleanup and button-only IDE power policy on host widgets."""

import asyncio
from types import SimpleNamespace
import unittest

from tests import test_platform as platform_tests
from tests.test_device_settings import LVGL, load_settings_ui, immediate_sleep
from tests.test_power import load_power_module, FakePlatform


class Focus:
    def __init__(self):
        self.widgets = []
        self.selected = None
        self.closed = False

    def add(self, widget):
        self.widgets.append(widget)
        if self.selected is None:
            self.selected = widget

    def focus(self, widget):
        self.selected = widget

    def close(self):
        self.closed = True
        self.widgets = []


class Navigation:
    def __init__(self):
        self.listeners = []
        self.pages = []

    def add_activity_listener(self, callback):
        self.listeners.append(callback)

    def remove_activity_listener(self, callback):
        self.listeners.remove(callback)

    def page(self):
        page = Focus()
        self.pages.append(page)
        return page


def button_text(widget):
    return widget.children[0].text


class ButtonPageTests(unittest.TestCase):
    def test_startup_distinguishes_ui_touch_and_navigation(self):
        main = platform_tests.HeadlessStartupTests().load_main_definitions()
        platform = SimpleNamespace(capabilities={'lvgl_ui': True, 'touch': False})
        calls = []
        launcher = lambda selected: calls.append(selected) or 'APP'
        self.assertEqual(main._select_mode({'STARTUP_MODE': 'BUTTON'}, platform, launcher), 'IDE')
        self.assertFalse(calls)
        platform.capabilities['button_navigation'] = True
        self.assertEqual(main._select_mode({'STARTUP_MODE': 'BUTTON'}, platform, launcher), 'APP')
        self.assertEqual(calls, [platform])

    def test_touch_only_app_error_is_recorded_and_returns_to_ide(self):
        main = platform_tests.HeadlessStartupTests().load_main_definitions()
        main._restore_modern_brightness = lambda *args: None
        main._ensure_repos = lambda: None
        main.load_settings = lambda: {'STARTUP_MODE': 'BUTTON'}
        main.ujson = SimpleNamespace(dumps=lambda value: '{}')
        platform = SimpleNamespace(display=None, capabilities={
            'lvgl_ui': True, 'button_navigation': True, 'touch': False})
        class MissingInput(RuntimeError):
            input_unavailable = True
        def app():
            raise MissingInput('This app needs touch input.')
        routes = []
        errors = []
        main.mark_app_failed = errors.append
        main.run(platform=platform, start_launcher=lambda p: 'APP', start_app=app,
                 start_ide=lambda: routes.append('IDE'),
                 start_recovery=lambda reason: routes.append('RECOVERY'))
        self.assertEqual(routes, ['IDE'])
        self.assertEqual(str(errors[0]), 'This app needs touch input.')

    def test_launcher_cancels_countdown_confirmation_defaults_cancel_and_cleans_pages(self):
        module = platform_tests.ModernTouchscreenLauncherTests().load_launcher()
        nav = Navigation()
        lv = LVGL()
        launcher = module.TouchscreenLauncher(
            lv, 320, 170, 'buttons.py', navigation=nav,
            list_directory=lambda path: ['buttons.py', 'folder'],
            get_path_kind=lambda path: 1 if path.endswith('.py') else 2)
        launcher.show()
        self.assertEqual([button_text(w) for w in nav.pages[-1].widgets],
                         ['Start IDE', 'Run app', 'Choose app'])
        self.assertFalse(launcher._countdown_cancelled)
        nav.listeners[0]()
        self.assertTrue(launcher._countdown_cancelled)
        previous = nav.pages[-1]
        launcher._show_browser('')
        self.assertTrue(previous.closed)
        self.assertEqual([button_text(w) for w in nav.pages[-1].widgets],
                         ['Back', 'Cancel', '[Folder] folder', 'buttons.py'])
        launcher._show_confirmation('buttons.py')
        self.assertEqual(button_text(nav.pages[-1].selected), 'Cancel')
        launcher.close()
        self.assertFalse(nav.listeners)
        self.assertTrue(all(page.closed for page in nav.pages))
        self.assertFalse(launcher._callbacks)

    def test_settings_focus_all_controls_and_confirmation_defaults_back(self):
        nav = Navigation()
        lv = LVGL()
        ui = load_settings_ui().DeviceSettings(
            lv, 320, 170,
            lambda: {'max_brightness': 1, 'auto_dim_seconds': 180},
            lambda *args: None, lambda: ['network'], lambda value: None,
            lambda: [], lambda: None, lambda: None, lambda error: None,
            navigation=nav)
        self.assertEqual(nav.pages[-1].widgets, [ui._entry])
        asyncio.run(ui.dispatch('settings', None, SimpleNamespace(sleep=immediate_sleep)))
        self.assertEqual([button_text(w) for w in nav.pages[-1].widgets],
                         ['Back', '-', '+', '-', '+', 'Save', 'WiFi', 'Updates'])
        self.assertTrue(nav.pages[0].closed)
        ui._network_page('network')
        self.assertEqual(button_text(nav.pages[-1].selected), 'Back')
        ui._confirm_update_page()
        self.assertEqual(button_text(nav.pages[-1].selected), 'Back')
        ui._set_busy(True)
        ui._queue('install')
        self.assertIsNone(ui._pending)
        ui.close()
        self.assertTrue(all(page.closed for page in nav.pages))

    def test_button_only_backlight_wakes_in_task_context_and_removes_listener(self):
        now = [0]
        platform = FakePlatform()
        platform.navigation = Navigation()
        controller = load_power_module().ModernIDEBacklightController(
            platform, {'modern_ui': {'auto_dim_seconds': 1}}, ticks_ms=lambda: now[0])
        controller.start()
        now[0] = 1001
        controller.check()
        self.assertTrue(controller.dimmed)
        before = list(platform.brightness)
        self.assertTrue(platform.navigation.listeners[0]())
        self.assertEqual(platform.brightness, before)
        controller.check()
        self.assertFalse(controller.dimmed)
        self.assertFalse(platform.navigation.listeners[0]())
        controller.stop()
        self.assertFalse(platform.navigation.listeners)


if __name__ == '__main__':
    unittest.main()
