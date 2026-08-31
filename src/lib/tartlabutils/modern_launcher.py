"""Touch-first per-boot launcher for the modern LVGL runtime profile."""

import os
import time

from .state import get_selected_app, path_kind, save_selected_app, \
    validate_selected_app


IDE_ROUTE = "IDE"
APP_ROUTE = "APP"
DEFAULT_TIMEOUT_SECONDS = 10
USER_ROOT = "/files/user"


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


def _folder_parts(folder):
    if not isinstance(folder, str):
        raise ValueError("launcher folder must be a string")
    folder = folder.replace("\\", "/").strip("/")
    parts = [] if not folder else folder.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("launcher folder escapes the user folder")
    return parts


def _relative_join(folder, name):
    parts = _folder_parts(folder)
    if not isinstance(name, str) or name in ("", ".", "..") or \
            "/" in name or "\\" in name:
        raise ValueError("invalid launcher entry name")
    return "/".join(parts + [name])


def _user_path(relative, user_root=USER_ROOT):
    parts = _folder_parts(relative)
    return user_root + (("/" + "/".join(parts)) if parts else "")


def browser_entries(folder, list_directory=os.listdir,
                    get_path_kind=path_kind, user_root=USER_ROOT,
                    validate_app=validate_selected_app):
    """List safe child folders and launchable Python files for one folder."""
    folder = "/".join(_folder_parts(folder))
    base = _user_path(folder, user_root)
    folders = []
    files = []
    for name in list_directory(base):
        try:
            relative = _relative_join(folder, name)
        except ValueError:
            continue
        kind = get_path_kind(_user_path(relative, user_root))
        if kind == 2:
            folders.append((name, relative))
        elif kind == 1 and name.endswith(".py"):
            try:
                validate_app(relative)
            except ValueError:
                continue
            files.append((name, relative))
    folders.sort(key=lambda item: item[0].lower())
    files.sort(key=lambda item: item[0].lower())
    return tuple(folders), tuple(files)


class ModernTouchscreenLauncher:
    """One-screen LVGL launcher whose result is consumed by ``main.py``."""

    def __init__(self, lvgl, width, height, selected_app,
                 timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                 ticks_ms=None, ticks_diff=None, sleep_ms=None,
                 list_directory=None, get_path_kind=None,
                 validate_app=None, save_app=None, user_root=USER_ROOT):
        self._lv = lvgl
        self._width = width
        self._height = height
        self._selected_app = selected_app
        self._timeout_ms = int(timeout_seconds * 1000)
        self._ticks_ms = ticks_ms or _ticks_ms
        self._ticks_diff = ticks_diff or _ticks_diff
        self._sleep_ms = sleep_ms or _sleep_ms
        self._list_directory = list_directory or os.listdir
        self._get_path_kind = get_path_kind or path_kind
        self._validate_app = validate_app or validate_selected_app
        self._save_app = save_app or save_selected_app
        self._user_root = user_root
        self._route = None
        self._countdown_cancelled = False
        self._callbacks = []
        self._screen = None
        self._previous_screen = None
        self._status = None
        self._last_countdown = None
        self._browser_folder = ""

    def _delete(self, widget, asynchronous=False):
        if widget is None:
            return
        delete = getattr(widget, "delete_async", None) \
            if asynchronous else None
        if delete is None:
            delete = getattr(widget, "delete", None)
        if delete is None:
            delete = getattr(widget, "del_", None)
        if delete is not None:
            delete()

    def _new_screen(self):
        previous = self._screen
        screen = self._lv.obj()
        screen.set_style_bg_color(self._lv.color_hex(0x101820), 0)
        self._screen = screen
        self._lv.screen_load(screen)
        if previous is not None:
            # Screen changes are initiated by child event callbacks.  LVGL's
            # asynchronous delete avoids destroying the callback's object
            # while its event is still being dispatched.
            self._delete(previous, asynchronous=True)

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
        self._countdown_cancelled = True
        self._show_browser("")

    def _show_home(self):
        self._new_screen()
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

    def _browser_button(self, parent, text, x, y, width, callback):
        button = self._lv.button(parent)
        self._set_position(button, x, y, width, 48)
        label = self._lv.label(button)
        label.set_text(text)
        label.center()
        button.add_event_cb(callback, self._lv.EVENT.CLICKED, None)
        self._callbacks.append(callback)

    def _open_folder(self, folder):
        def callback(unused_event):
            self._show_browser(folder)
        return callback

    def _choose_file(self, filename):
        def callback(unused_event):
            self._show_confirmation(filename)
        return callback

    def _cancel_browser(self, unused_event):
        self._show_home()

    def _go_up(self, unused_event):
        if not self._browser_folder:
            self._show_home()
            return
        parts = _folder_parts(self._browser_folder)
        self._show_browser("/".join(parts[:-1]))

    def _show_browser(self, folder):
        folder = "/".join(_folder_parts(folder))
        self._browser_folder = folder
        self._new_screen()
        margin = max(6, min(self._width, self._height) // 30)
        control_width = max(64, min(100, (self._width - margin * 3) // 4))
        self._browser_button(
            self._screen, "Back", margin, margin, control_width, self._go_up)
        self._browser_button(
            self._screen, "Cancel", self._width - margin - control_width,
            margin, control_width, self._cancel_browser)
        shown_folder = "/" + folder if folder else "/"
        folder_label = self._lv.label(self._screen)
        folder_label.set_text(shown_folder)
        self._set_label_width(
            folder_label, self._width - (control_width + margin) * 2)
        folder_label.align(self._lv.ALIGN.TOP_MID, 0, margin + 15)

        list_y = margin + 54
        list_height = max(48, self._height - list_y - margin)
        container = self._lv.obj(self._screen)
        self._set_position(
            container, margin, list_y, self._width - margin * 2, list_height)
        try:
            folders, files = browser_entries(
                folder, self._list_directory, self._get_path_kind,
                self._user_root, self._validate_app)
        except OSError:
            folders, files = (), ()
        row_width = self._width - margin * 2 - 12
        row_y = 0
        for name, relative in folders:
            self._browser_button(
                container, "[Folder] " + name, 0, row_y, row_width,
                self._open_folder(relative))
            row_y += 52
        for name, relative in files:
            self._browser_button(
                container, name, 0, row_y, row_width,
                self._choose_file(relative))
            row_y += 52
        if not folders and not files:
            empty = self._lv.label(container)
            empty.set_text("No folders or launchable apps")
            empty.align(self._lv.ALIGN.TOP_MID, 0, 12)

    def _confirmation_cancel(self, unused_event):
        self._show_browser(self._browser_folder)

    def _commit_app(self, filename):
        def callback(unused_event):
            try:
                validated = self._validate_app(filename)
                if self._get_path_kind(
                        _user_path(validated, self._user_root)) != 1:
                    raise ValueError("The selected app no longer exists")
                self._save_app(validated)
            except (OSError, ValueError) as error:
                self._status.set_text(str(error))
                return
            self._selected_app = validated
            self._show_home()
        return callback

    def _show_confirmation(self, filename):
        self._new_screen()
        margin = max(8, min(self._width, self._height) // 24)
        self._label("Set as selected app?", margin)
        self._label(filename, margin + 34)
        self._status = self._label("", margin + 62)
        button_width = (self._width - margin * 3) // 2
        button_y = self._height - margin - 52
        self._browser_button(
            self._screen, "Set as app", margin, button_y, button_width,
            self._commit_app(filename))
        self._browser_button(
            self._screen, "Cancel", margin * 2 + button_width, button_y,
            button_width, self._confirmation_cancel)

    def show(self):
        self._previous_screen = self._lv.screen_active()
        self._show_home()

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
        self._delete(self._screen)
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
