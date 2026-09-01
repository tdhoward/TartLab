"""Touch-inactivity backlight policy used only by modern LVGL IDE mode."""

import time


DEFAULT_MAX_BRIGHTNESS = 1.0
DEFAULT_DIM_BRIGHTNESS = 0.2
DEFAULT_AUTO_DIM_SECONDS = 180
DEFAULT_POLL_MILLISECONDS = 100
DEFAULT_TOUCH_KEEP_AWAKE_MILLISECONDS = 10000


def _ticks_ms():
    ticks_ms = getattr(time, "ticks_ms", None)
    if ticks_ms is not None:
        return ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(new, old):
    ticks_diff = getattr(time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(new, old)
    return new - old


def _number(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value


def modern_ui_settings(settings=None):
    """Return validated modern brightness settings without mutating state."""
    source = settings.get("modern_ui", {}) if isinstance(settings, dict) else {}
    if not isinstance(source, dict):
        source = {}

    maximum = _number(
        source.get("max_brightness"), DEFAULT_MAX_BRIGHTNESS)
    dim = _number(source.get("dim_brightness"), DEFAULT_DIM_BRIGHTNESS)
    delay = _number(
        source.get("auto_dim_seconds"), DEFAULT_AUTO_DIM_SECONDS)
    maximum = min(1.0, max(0.0, float(maximum)))
    dim = min(maximum, max(0.0, float(dim)))
    if delay < 0:
        delay = DEFAULT_AUTO_DIM_SECONDS
    return {
        "max_brightness": maximum,
        "dim_brightness": dim,
        "auto_dim_seconds": float(delay),
    }


def restore_normal_brightness(platform, settings=None):
    """Restore configured normal brightness in ordinary task context."""
    value = modern_ui_settings(settings)["max_brightness"]
    platform.set_brightness(value)
    return value


def _lvgl_inputs(lvgl, platform_input=None):
    get_next = getattr(lvgl, "indev_get_next", None)
    if get_next is None:
        if platform_input is None:
            return ()
        native_input = getattr(platform_input, "_indev_drv", platform_input)
        return (native_input,)
    devices = []
    current = get_next(None)
    while current is not None:
        devices.append(current)
        current = get_next(current)
    return tuple(devices)


class ModernIDEBacklightController:
    """Dim a modern IDE after inactivity and consume its first wake touch."""

    def __init__(self, platform, settings=None, ticks_ms=None,
                 ticks_diff=None, poll_milliseconds=DEFAULT_POLL_MILLISECONDS):
        values = modern_ui_settings(settings)
        self.max_brightness = values["max_brightness"]
        self.dim_brightness = values["dim_brightness"]
        self.auto_dim_seconds = values["auto_dim_seconds"]
        self._timeout_ms = int(self.auto_dim_seconds * 1000)
        self._platform = platform
        self._lvgl = getattr(platform, "_lvgl", None)
        self._ticks_ms = ticks_ms or _ticks_ms
        self._ticks_diff = ticks_diff or _ticks_diff
        self._poll_milliseconds = poll_milliseconds
        self._active = False
        self._dimmed = False
        self._touch_pending = False
        self._last_activity = None
        self._last_touch_keep_awake = None
        self._inputs = ()
        self._touch_callback = self._touch_event

    @property
    def dimmed(self):
        return self._dimmed

    @property
    def active(self):
        return self._active

    def _consume_touch(self, input_device):
        stop = getattr(input_device, "stop_processing", None)
        if stop is not None:
            stop()
        wait_release = getattr(input_device, "wait_release", None)
        if wait_release is not None:
            wait_release()

    def _touch_event(self, unused_event):
        if not self._active:
            return
        self._touch_pending = True
        if self._dimmed:
            for input_device in self._inputs:
                self._consume_touch(input_device)

    def _keep_touch_awake(self, now):
        keep_awake = getattr(self._platform, "keep_touch_awake", None)
        if keep_awake is None:
            return
        if (self._last_touch_keep_awake is None or
                self._ticks_diff(now, self._last_touch_keep_awake) >=
                DEFAULT_TOUCH_KEEP_AWAKE_MILLISECONDS):
            keep_awake()
            self._last_touch_keep_awake = now

    def _attach_inputs(self):
        if self._lvgl is None:
            return
        pressed = getattr(getattr(self._lvgl, "EVENT", None), "PRESSED", None)
        if pressed is None:
            return
        self._inputs = _lvgl_inputs(
            self._lvgl, getattr(self._platform, "input", None))
        for input_device in self._inputs:
            input_device.add_event_cb(self._touch_callback, pressed, None)

    def _detach_inputs(self):
        for input_device in self._inputs:
            remove = getattr(
                input_device, "remove_event_cb_with_user_data", None)
            if remove is not None:
                remove(self._touch_callback, None)
        self._inputs = ()

    def start(self):
        """Begin IDE-mode timing. Repeated starts do not duplicate callbacks."""
        if self._active:
            return
        self._active = True
        self._dimmed = False
        self._touch_pending = False
        self._last_activity = self._ticks_ms()
        self._last_touch_keep_awake = None
        self._keep_touch_awake(self._last_activity)
        self._platform.set_brightness(self.max_brightness)
        self._attach_inputs()

    def check(self):
        """Apply pending activity or a due dim transition once."""
        if not self._active:
            return
        now = self._ticks_ms()
        self._keep_touch_awake(now)
        if self._touch_pending:
            self._touch_pending = False
            self._last_activity = now
            if self._dimmed:
                self._platform.set_brightness(self.max_brightness)
                self._dimmed = False
            return
        if self._timeout_ms == 0 or self._dimmed:
            return
        if self._ticks_diff(now, self._last_activity) >= self._timeout_ms:
            self._platform.set_brightness(self.dim_brightness)
            self._dimmed = True

    def wake(self):
        """Restore normal brightness and restart the IDE inactivity clock."""
        if not self._active:
            return
        now = self._ticks_ms()
        self._touch_pending = False
        self._last_activity = now
        self._keep_touch_awake(now)
        self._platform.set_brightness(self.max_brightness)
        self._dimmed = False

    async def run(self, asyncio_module):
        """Run the policy until stopped by the IDE lifecycle."""
        self.start()
        try:
            while self._active:
                self.check()
                await asyncio_module.sleep_ms(self._poll_milliseconds)
        finally:
            self.stop()

    def stop(self):
        """End IDE ownership and restore normal brightness exactly once."""
        was_active = self._active
        self._active = False
        self._touch_pending = False
        self._last_touch_keep_awake = None
        self._detach_inputs()
        if was_active or self._dimmed:
            self._platform.set_brightness(self.max_brightness)
        self._dimmed = False
