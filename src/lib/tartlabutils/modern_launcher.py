"""Touch-first per-boot launcher for the modern LVGL runtime profile."""

import time

from .state import get_selected_app


IDE_ROUTE = "IDE"
APP_ROUTE = "APP"
DEFAULT_TIMEOUT_SECONDS = 10


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


def _sleep_ms(milliseconds):
    sleep_ms = getattr(time, "sleep_ms", None)
    if sleep_ms is not None:
        sleep_ms(milliseconds)
    else:
        time.sleep(milliseconds / 1000)


def launcher_layout(width, height):
    """Return geometry-derived launcher positions for landscape or portrait."""
    if width <= 0 or height <= 0:
        raise ValueError("launcher geometry must be positive")
    short_side = min(width, height)
    margin = max(8, short_side // 24)
    title_y = margin
    selected_y = title_y + max(28, short_side // 8)
    if width >= height:
        gap = margin
        button_height = max(48, min(70, height // 3))
        button_y = height - margin - button_height
        button_width = max(1, (width - (margin * 2) - (gap * 2)) // 3)
        buttons = []
        for index in range(3):
            buttons.append((
                margin + index * (button_width + gap),
                button_y,
                button_width,
                button_height,
            ))
    else:
        gap = max(10, margin)
        button_width = width - margin * 2
        button_height = max(48, min(72, (height - selected_y - 4 * gap) // 3))
        button_y = max(selected_y + 34, height // 4)
        buttons = []
        for index in range(3):
            buttons.append((
                margin,
                button_y + index * (button_height + gap),
                button_width,
                button_height,
            ))
    return {
        "margin": margin,
        "title_y": title_y,
        "selected_y": selected_y,
        "buttons": tuple(buttons),
    }


class ModernTouchscreenLauncher:
    """One-screen LVGL launcher whose result is consumed by ``main.py``."""

    def __init__(self, lvgl, width, height, selected_app,
                 timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                 ticks_ms=None, ticks_diff=None, sleep_ms=None):
        self._lv = lvgl
        self._width = width
        self._height = height
        self._selected_app = selected_app
        self._timeout_ms = int(timeout_seconds * 1000)
        self._ticks_ms = ticks_ms or _ticks_ms
        self._ticks_diff = ticks_diff or _ticks_diff
        self._sleep_ms = sleep_ms or _sleep_ms
        self._route = None
        self._countdown_cancelled = False
        self._callbacks = []
        self._screen = None
        self._previous_screen = None
        self._status = None
        self._last_countdown = None

    def _set_position(self, widget, x, y, width, height):
        widget.set_size(width, height)
        widget.set_pos(x, y)

    def _set_label_width(self, label, width):
        set_width = getattr(label, "set_width", None)
        if set_width is not None:
            set_width(width)
        set_align = getattr(label, "set_style_text_align", None)
        text_align = getattr(self._lv, "TEXT_ALIGN", None)
        if set_align is not None and text_align is not None:
            set_align(getattr(text_align, "CENTER", 0), 0)

    def _label(self, text, y):
        label = self._lv.label(self._screen)
        label.set_text(text)
        self._set_label_width(label, self._width - 16)
        label.align(self._lv.ALIGN.TOP_MID, 0, y)
        return label

    def _button(self, text, bounds, callback):
        button = self._lv.button(self._screen)
        self._set_position(button, *bounds)
        label = self._lv.label(button)
        label.set_text(text)
        label.center()
        button.add_event_cb(callback, self._lv.EVENT.CLICKED, None)
        self._callbacks.append(callback)
        return button

    def _choose_route(self, route):
        def callback(unused_event):
            self._countdown_cancelled = True
            self._route = route
        return callback

    def _choose_app(self, unused_event):
        # File navigation is the next planned implementation stage.  Cancelling
        # here is important now: no future chooser may race the IDE timeout.
        self._countdown_cancelled = True
        self._status.set_text("Select IDE or the current app")

    def show(self):
        self._previous_screen = self._lv.screen_active()
        self._screen = self._lv.obj()
        self._screen.set_style_bg_color(self._lv.color_hex(0x101820), 0)
        layout = launcher_layout(self._width, self._height)
        self._label("TartLab", layout["title_y"])
        self._label(
            "Selected app: " + self._selected_app, layout["selected_y"])
        self._status = self._label("", layout["selected_y"] + 24)
        labels = ("Start IDE", "Run selected app", "Choose app")
        callbacks = (
            self._choose_route(IDE_ROUTE),
            self._choose_route(APP_ROUTE),
            self._choose_app,
        )
        for text, bounds, callback in zip(
                labels, layout["buttons"], callbacks):
            self._button(text, bounds, callback)
        self._lv.screen_load(self._screen)

    def _update_countdown(self, elapsed_ms):
        if self._countdown_cancelled:
            return
        remaining = max(0, self._timeout_ms - elapsed_ms)
        seconds = (remaining + 999) // 1000
        if seconds != self._last_countdown:
            self._status.set_text("Starting IDE in %s seconds" % seconds)
            self._last_countdown = seconds

    def wait_for_route(self):
        started = self._ticks_ms()
        while self._route is None:
            elapsed = self._ticks_diff(self._ticks_ms(), started)
            if not self._countdown_cancelled and elapsed >= self._timeout_ms:
                self._route = IDE_ROUTE
                break
            self._update_countdown(elapsed)
            self._sleep_ms(50)
        return self._route

    def close(self):
        if self._screen is None:
            return
        if self._previous_screen is not None:
            self._lv.screen_load(self._previous_screen)
        delete = getattr(self._screen, "delete", None)
        if delete is None:
            delete = getattr(self._screen, "del_", None)
        if delete is not None:
            delete()
        self._screen = None
        self._callbacks = []

    def run(self):
        self.show()
        try:
            return self.wait_for_route()
        finally:
            self.close()


def run_startup_launcher(platform, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    """Acquire modern UI ownership and return a per-boot IDE or APP route."""
    platform.enter_ui_mode()
    lvgl = getattr(platform, "_lvgl", None)
    if lvgl is None:
        raise RuntimeError("modern platform does not provide LVGL")
    launcher = ModernTouchscreenLauncher(
        lvgl, platform.width, platform.height, get_selected_app(),
        timeout_seconds=timeout_seconds)
    return launcher.run()
