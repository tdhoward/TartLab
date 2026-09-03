"""TartLab-owned boundary around board-specific startup hardware."""

import sys


LEGACY_SEARCH_PATHS = (
    "/configs",
    "/lib/pydevices",
    "/lib/pydevices/bus_drv",
    "/lib/pydevices/display_drv",
    "/lib/pydevices/touch_drv",
    "/lib/pydevices/add_ons",
)
BOARD_IDENTITY_FILE = "/device/board.json"
BOARD_RUNTIME_ROOT = "/board"


def board_runtime_path(identity_file=BOARD_IDENTITY_FILE):
    """Return the provisioned board's isolated runtime path, if present."""
    try:
        with open(identity_file, "r") as stream:
            try:
                import ujson as json
            except ImportError:
                import json
            identity = json.load(stream)
    except OSError:
        return None
    board_id = identity.get("board_id") if isinstance(identity, dict) else None
    if not isinstance(board_id, str) or not board_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in board_id):
        raise ValueError("protected board identity is invalid")
    return BOARD_RUNTIME_ROOT + "/" + board_id


class NullIDEView:
    """No-op view used by supported devices without a display."""

    def show_startup(self, version):
        pass

    def show_network(self, wifi_name, address, hostname=None):
        pass

    def show_update_progress(self, status, step, steps):
        pass

    def show_app_error(self):
        pass


class LegacyIDEView:
    """Render the IDE status UI with the deployed PyDevices display API."""

    FONT_WIDTH = 8

    def __init__(self, display):
        from graphics import FrameBuffer, RGB565
        import graphics

        self.display = display
        self.display.rotation = 90
        self.width = display.width
        self.height = display.height
        self.base_unit = min([self.width, self.height]) // 2
        bytes_per_pixel = display.color_depth // 8
        self.buffer = bytearray(self.width * self.height * bytes_per_pixel)
        self.framebuffer = FrameBuffer(
            self.buffer, self.width, self.height, RGB565)
        self.text_width = self.width - 2
        self.text_buffer = bytearray(
            self.text_width * self.FONT_WIDTH * 2 * bytes_per_pixel)
        self.text_framebuffer = FrameBuffer(
            self.text_buffer, self.text_width, self.FONT_WIDTH * 2, RGB565)
        self.graphics = graphics
        if display.requires_byteswap:
            needs_swap = display.disable_auto_byteswap(True)
        else:
            needs_swap = False
        self.black = 0x0000
        self.white = 0xFFFF
        self.green = 0x07E0 if not needs_swap else 0xE007
        self.red = 0xF800 if not needs_swap else 0x00F8
        self.blue = 0x001F if not needs_swap else 0xF800
        self.cyan = 0x07FF if not needs_swap else 0xFF07
        self.grey = 0x8410 if not needs_swap else 0x1084
        self._border(self.blue)

    def _border(self, color):
        self.framebuffer.fill(self.black)
        self.framebuffer.rect(0, 0, self.width, self.height, color)
        self.display.blit_rect(
            self.buffer, 0, 0, self.width, self.height)

    def _text(self, text, row, color=None, size=2):
        if color is None:
            color = self.white
        font_width = self.FONT_WIDTH * size
        self.text_framebuffer.fill(0)
        self.text_framebuffer.text(
            text, (self.text_width - font_width * len(text)) // 2,
            0, color, size)
        self.display.blit_rect(
            self.text_buffer, (self.width - self.text_width) // 2,
            self.height // 2 + (font_width * row), self.text_width,
            self.FONT_WIDTH * 2)

    def show_startup(self, version):
        self._text("TARTLAB " + version, -4)

    def show_network(self, wifi_name, address, hostname=None):
        self._text("WiFi: " + wifi_name, -1)
        self._text(address, 1)
        if hostname:
            self._text(hostname + ".local", 3)

    def show_update_progress(self, status, step, steps):
        small_unit = self.base_unit // 5
        if step == 1:
            self._border(self.green)
            self._text("UPDATE IN PROGRESS", -4)
        self._text(status, 0)
        if step > steps:
            steps = step
        self._text("Step %s of %s" % (step, steps), 2, self.grey, 2)
        bar_height = small_unit
        bar_width = self.width - 10
        start_x = 5
        start_y = self.height - (5 + bar_height)
        progress_width = int(bar_width * step / (steps + 1))
        self.graphics.gradient_rect(
            self.display, start_x, start_y, start_x + progress_width,
            bar_height, self.cyan, self.blue)

    def show_app_error(self):
        marker_size = 14
        marker_buffer = bytearray(marker_size * marker_size * 2)
        marker = self.graphics.FrameBuffer(
            marker_buffer, marker_size, marker_size, self.graphics.RGB565)
        marker.fill(self.black)
        marker.ellipse(7, 7, 6, 6, self.red, True)
        self.display.blit_rect(
            marker_buffer, self.width - marker_size - 6, 6,
            marker_size, marker_size)


def configure_legacy_paths(paths=None):
    """Add the selected board runtime, then historical PyDevices paths."""
    if paths is None:
        paths = sys.path
    runtime_path = board_runtime_path()
    if runtime_path is not None and runtime_path not in paths:
        # Protected board support must precede release root and student code.
        # /device stays first because it owns the generated selector and local
        # calibration, but /files/user must never be able to shadow its import.
        insert_at = paths.index("/device") + 1 if "/device" in paths else 0
        paths.insert(insert_at, runtime_path)

    insert_at = 0
    for core_path in ("/device", "/lib", "/", "/files/user"):
        if core_path in paths:
            position = paths.index(core_path) + 1
            if position > insert_at:
                insert_at = position
    for path in LEGACY_SEARCH_PATHS:
        if path not in paths:
            paths.insert(insert_at, path)
            insert_at += 1
    return paths


class LegacyPlatform:
    """Adapter for the deployed ``hdwconfig`` and PyDevices layout."""

    def __init__(self, hardware=None, pin_factory=None, network_module=None):
        configure_legacy_paths()
        if hardware is None:
            import hdwconfig as hardware
        self.display = getattr(hardware, "display_drv", None)
        self.input = getattr(hardware, "touch_drv", None)
        self.ide_button_pin = getattr(hardware, "IDE_BUTTON_PIN", None)
        self.width = getattr(self.display, "width", 0)
        self.height = getattr(self.display, "height", 0)
        self.capabilities = {
            "display": self.display is not None,
            "touch": self.input is not None,
            "ide_button": self.ide_button_pin is not None,
            "backlight": hasattr(self.display, "brightness"),
            "network": True,
        }
        self._pin_factory = pin_factory
        self._button = None
        self._network_module = network_module

    def _network(self):
        if self._network_module is None:
            import network
            self._network_module = network
        return self._network_module

    def ide_button_value(self):
        if self.ide_button_pin is None:
            return 1
        pin_factory = self._pin_factory
        if pin_factory is None:
            from machine import Pin
            pin_factory = Pin
        if self._button is None:
            mode = getattr(pin_factory, "IN", 0)
            self._button = pin_factory(self.ide_button_pin, mode)
        return self._button.value()

    def set_hostname(self, hostname):
        self._network().hostname(hostname)

    def station_interface(self):
        network = self._network()
        return network.WLAN(network.STA_IF)

    def access_point_interface(self):
        network = self._network()
        return network.WLAN(network.AP_IF)

    def configure_open_access_point(self, interface, name):
        network = self._network()
        interface.active(True)
        interface.config(essid=name)
        interface.config(authmode=network.AUTH_OPEN)

    def create_ide_view(self):
        if self.display is None:
            return NullIDEView()
        return LegacyIDEView(self.display)

    def enter_ui_mode(self):
        """Legacy firmware has one renderer, so ownership is already implicit."""

    def enter_game_mode(self):
        """Return the deployed direct display through the common boundary."""
        return self.display

    def clear_display(self):
        if self.display is not None:
            self.display.fill(0)

    def show_error(self):
        if self.display is not None:
            self.display.fill(0xF800)

    def set_brightness(self, value):
        if self.display is not None and hasattr(self.display, "brightness"):
            self.display.brightness = value

    def sleep(self, seconds):
        import utime
        utime.sleep(seconds)

    def deinit(self):
        """Release optional platform resources when a caller explicitly asks."""
        for device in (self.input, self.display):
            deinit = getattr(device, "deinit", None)
            if deinit is not None:
                try:
                    deinit()
                except Exception:
                    pass


_current_platform = None


def set_platform(platform):
    global _current_platform
    _current_platform = platform


def get_platform():
    global _current_platform
    if _current_platform is None:
        # Adult provisioning identifies the selected board in protected state.
        # Its isolated runtime is searched before historical /configs modules.
        configure_legacy_paths()
        import hdwconfig as hardware
        board = getattr(hardware, "BOARD_CONFIG", None)
        if board is not None:
            from tartlabutils.modern_factory import create_platform
            _current_platform = create_platform(board)
        else:
            factory = getattr(hardware, "create_platform", None)
            if factory is not None:
                _current_platform = factory()
            else:
                _current_platform = LegacyPlatform(hardware=hardware)
    return _current_platform
