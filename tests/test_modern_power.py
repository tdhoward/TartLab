import importlib.util
from pathlib import Path
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_power_module():
    spec = importlib.util.spec_from_file_location(
        "modern_power_under_test",
        ROOT / "src/lib/tartlabutils/modern_power.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInput:
    def __init__(self):
        self.callbacks = []
        self.stop_calls = 0
        self.wait_release_calls = 0
        self.remove_calls = 0

    def add_event_cb(self, callback, event, user_data):
        self.callbacks.append((callback, event, user_data))

    def remove_event_cb_with_user_data(self, callback, user_data):
        self.remove_calls += 1
        self.callbacks = [
            item for item in self.callbacks
            if item[0] != callback or item[2] != user_data]

    def stop_processing(self):
        self.stop_calls += 1

    def wait_release(self):
        self.wait_release_calls += 1

    def press(self):
        for callback, unused_event, unused_data in tuple(self.callbacks):
            callback(None)


class FakeLVGL:
    EVENT = types.SimpleNamespace(PRESSED=7)

    def __init__(self, inputs):
        self.inputs = list(inputs)

    def indev_get_next(self, previous):
        if previous is None:
            return self.inputs[0] if self.inputs else None
        index = self.inputs.index(previous) + 1
        return self.inputs[index] if index < len(self.inputs) else None


class FakePlatform:
    def __init__(self, inputs=()):
        self._lvgl = FakeLVGL(inputs)
        self.brightness = []

    def set_brightness(self, value):
        self.brightness.append(value)


class ModernPowerSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.power = load_power_module()

    def test_defaults_invalid_values_clamping_and_disable(self):
        self.assertEqual(self.power.modern_ui_settings(), {
            "max_brightness": 1.0,
            "dim_brightness": 0.2,
            "auto_dim_seconds": 180.0,
        })
        self.assertEqual(self.power.modern_ui_settings({"modern_ui": {
            "max_brightness": 1.5,
            "dim_brightness": 9,
            "auto_dim_seconds": 0,
        }}), {
            "max_brightness": 1.0,
            "dim_brightness": 1.0,
            "auto_dim_seconds": 0.0,
        })
        self.assertEqual(self.power.modern_ui_settings({"modern_ui": {
            "max_brightness": "bright",
            "dim_brightness": None,
            "auto_dim_seconds": -1,
        }}), {
            "max_brightness": 1.0,
            "dim_brightness": 0.2,
            "auto_dim_seconds": 180.0,
        })

    def test_restore_uses_configured_normal_brightness(self):
        platform = FakePlatform()
        value = self.power.restore_normal_brightness(
            platform, {"modern_ui": {"max_brightness": 0.65}})
        self.assertEqual(value, 0.65)
        self.assertEqual(platform.brightness, [0.65])


class ModernBacklightControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.power = load_power_module()

    def controller(self, settings=None):
        clock = {"now": 0}
        input_device = FakeInput()
        platform = FakePlatform([input_device])
        controller = self.power.ModernIDEBacklightController(
            platform,
            settings or {"modern_ui": {"auto_dim_seconds": 1}},
            ticks_ms=lambda: clock["now"],
            ticks_diff=lambda new, old: new - old)
        return clock, input_device, platform, controller

    def test_timeout_dims_and_wake_touch_is_consumed_before_restore(self):
        clock, input_device, platform, controller = self.controller()
        controller.start()
        clock["now"] = 999
        controller.check()
        self.assertEqual(platform.brightness, [1.0])
        clock["now"] = 1000
        controller.check()
        self.assertEqual(platform.brightness, [1.0, 0.2])
        self.assertTrue(controller.dimmed)

        input_device.press()
        self.assertEqual(platform.brightness, [1.0, 0.2])
        self.assertEqual(input_device.stop_calls, 1)
        self.assertEqual(input_device.wait_release_calls, 1)
        controller.check()
        self.assertEqual(platform.brightness, [1.0, 0.2, 1.0])
        self.assertFalse(controller.dimmed)

    def test_activity_postpones_timeout_without_consuming_normal_touch(self):
        clock, input_device, platform, controller = self.controller()
        controller.start()
        clock["now"] = 900
        input_device.press()
        controller.check()
        self.assertEqual(input_device.stop_calls, 0)
        clock["now"] = 1800
        controller.check()
        self.assertEqual(platform.brightness, [1.0])
        clock["now"] = 1900
        controller.check()
        self.assertEqual(platform.brightness, [1.0, 0.2])

    def test_zero_delay_disables_dimming_and_stop_is_repeatable(self):
        settings = {"modern_ui": {
            "max_brightness": 0.8,
            "dim_brightness": 0.1,
            "auto_dim_seconds": 0,
        }}
        clock, input_device, platform, controller = self.controller(settings)
        controller.start()
        clock["now"] = 999999
        controller.check()
        controller.stop()
        controller.stop()
        self.assertEqual(platform.brightness, [0.8, 0.8])
        self.assertEqual(input_device.remove_calls, 1)
        self.assertFalse(controller.active)

    def test_app_or_error_handoff_restores_after_a_dimmed_ide(self):
        clock, input_device, platform, controller = self.controller()
        controller.start()
        clock["now"] = 1000
        controller.check()
        controller.stop()
        self.assertEqual(platform.brightness, [1.0, 0.2, 1.0])
        input_device.press()
        self.assertEqual(input_device.stop_calls, 0)


if __name__ == "__main__":
    unittest.main()
