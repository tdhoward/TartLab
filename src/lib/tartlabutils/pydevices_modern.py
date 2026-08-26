"""TartLab boundary for the pinned PyDevices LVGL/displayif comparison."""

import time

from tartlabutils.modern import DisplayOwnershipError, ModernIDEView


UI_OWNER = "ui"
GAME_OWNER = "game"


class PyDevicesDirectRGB565Surface:
    """Public synchronous dirty-rectangle surface using displaydev."""

    bytes_per_pixel = 2
    color_format = "RGB565_BE"

    def __init__(self, controller, display):
        self._controller = controller
        self._display = display
        self.width = display.width
        self.height = display.height

    def _validate_region(self, buffer, x, y, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("rectangle is outside the direct surface")
        expected = width * height * self.bytes_per_pixel
        if len(buffer) != expected:
            raise ValueError(
                "RGB565 buffer has %s bytes; expected %s" %
                (len(buffer), expected)
            )

    def write(self, buffer, x, y, width, height, wait=True):
        """Write one rectangle; displayif's current SPI call is blocking."""
        self._validate_region(buffer, x, y, width, height)
        self._controller.begin_direct_transfer()
        try:
            self._display.blit_rect(buffer, x, y, width, height)
        except Exception:
            self._controller.finish_direct_transfer()
            raise
        self._controller.finish_direct_transfer()

    blit_rect = write

    def wait(self, timeout_ms=1000):
        """Return immediately because a successful write is already complete."""
        self._controller.wait_for_transfer(timeout_ms)

    @property
    def busy(self):
        return self._controller.transfer_pending

    def allocate_buffer(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        return bytearray(width * height * self.bytes_per_pixel)

    def free_buffer(self, buffer):
        self.wait()


class PyDevicesDisplayController:
    """Serialize the public LVGL bridge and synchronous direct surface."""

    def __init__(self, app, display, lv_display, lvgl, event_loop,
                 input_devices=None):
        self._app = app
        self._display = display
        self._lv_display = lv_display
        self._lvgl = lvgl
        self._event_loop = event_loop
        self._input_devices = tuple(input_devices or ())
        self._owner = UI_OWNER
        self._transfer_pending = False
        self._loop_paused = False
        self._refresh_claim = None
        self.surface = PyDevicesDirectRGB565Surface(self, display)

    @property
    def owner(self):
        return self._owner

    @property
    def transfer_pending(self):
        return self._transfer_pending

    def _enable_input(self, enabled):
        for device in self._input_devices:
            enable = getattr(device, "enable", None)
            if enable is not None:
                enable(enabled)

    def begin_direct_transfer(self):
        if self._owner != GAME_OWNER:
            raise DisplayOwnershipError(
                "direct surface requires game display ownership"
            )
        if self._transfer_pending:
            raise DisplayOwnershipError(
                "a direct display transfer is already in progress"
            )
        self._transfer_pending = True

    def finish_direct_transfer(self):
        self._transfer_pending = False

    def wait_for_transfer(self, timeout_ms=1000):
        if self._transfer_pending:
            raise RuntimeError("blocking display transfer did not complete")

    def acquire_game(self, timeout_ms=1000):
        if self._owner == GAME_OWNER:
            return self.surface
        self._event_loop.disable()
        self._loop_paused = True
        self._enable_input(False)
        try:
            self._lvgl.refr_now(self._lv_display)
            self.wait_for_transfer(timeout_ms)
            self._refresh_claim = self._app.pause_refresh()
        except Exception:
            self._enable_input(True)
            self._event_loop.enable()
            self._loop_paused = False
            raise
        self._owner = GAME_OWNER
        return self.surface

    def acquire_ui(self, timeout_ms=1000):
        if self._owner == UI_OWNER:
            return
        self.wait_for_transfer(timeout_ms)
        self._owner = UI_OWNER
        claim = self._refresh_claim
        self._refresh_claim = None
        if claim is not None:
            claim.release()
        self._enable_input(True)
        screen = self._lvgl.screen_active()
        screen.invalidate()
        if self._loop_paused:
            self._event_loop.enable()
            self._loop_paused = False
        self._lvgl.refr_now(self._lv_display)
        self.wait_for_transfer(timeout_ms)


class PyDevicesModernPlatform:
    """TartLab platform backed by PyDevices LVGL and native displayif SPI."""

    def __init__(self, controller, display, touch, app,
                 ide_button_pin=12, pin_factory=None, network_module=None,
                 lvgl=None):
        self.controller = controller
        self.display = display
        self.input = touch
        self.app = app
        self.game_surface = controller.surface
        self.ide_button_pin = ide_button_pin
        self.width = controller.surface.width
        self.height = controller.surface.height
        self._pin_factory = pin_factory
        self._button = None
        self._network_module = network_module
        self._lvgl = lvgl or controller._lvgl
        self._deinitialized = False
        self.capabilities = {
            "display": True,
            "touch": touch is not None,
            "ide_button": ide_button_pin is not None,
            "backlight": True,
            "network": True,
            "lvgl_ui": True,
            "direct_rgb565": True,
            "async_direct_rgb565": False,
            "direct_buffer_storage": "micropython-bytearray",
            "phase5_benchmark_profile": "pydevices",
            "exclusive_display_ownership": True,
        }

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
            self._button = pin_factory(
                self.ide_button_pin, getattr(pin_factory, "IN", 0)
            )
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

    def enter_ui_mode(self):
        self.controller.acquire_ui()

    def enter_game_mode(self):
        return self.controller.acquire_game()

    def create_ide_view(self):
        return ModernIDEView(self.controller, self._lvgl)

    def pause_ui_for_benchmark(self):
        """Pause automatic LVGL servicing while the harness drives it."""
        self.controller._event_loop.disable()

    def resume_ui_after_benchmark(self):
        self.controller._event_loop.enable()

    def clear_display(self):
        self.enter_ui_mode()
        screen = self._lvgl.screen_active()
        screen.set_style_bg_color(self._lvgl.color_hex(0x000000), 0)
        screen.invalidate()

    def show_error(self):
        self.enter_ui_mode()
        screen = self._lvgl.screen_active()
        screen.set_style_bg_color(self._lvgl.color_hex(0xFF0000), 0)
        screen.invalidate()
        self._lvgl.refr_now(self.controller._lv_display)

    def set_brightness(self, value):
        self.display.brightness = value

    def sleep(self, seconds):
        time.sleep(seconds)

    def deinit(self):
        if self._deinitialized:
            return
        self.enter_ui_mode()
        self.app.request_quit()
        self._deinitialized = True


def _lvgl_input_devices(lvgl):
    """Enumerate inputs through LVGL's public linked-list API when available."""
    get_next = getattr(lvgl, "indev_get_next", None)
    if get_next is None:
        return ()
    devices = []
    device = get_next(None)
    while device is not None:
        devices.append(device)
        device = get_next(device)
    return devices


def create_t_display_s3_pro_platform():
    """Construct the pinned PyDevices/displayif T-Display-S3 Pro profile."""
    import appdev
    from cst226 import CST226
    import lvgl as lv
    from machine import I2C, Pin
    from spibus import SPIBus
    from st7796 import ST7796
    import sys

    bus = SPIBus(
        id=1,
        baudrate=60_000_000,
        sck=18,
        mosi=17,
        miso=8,
        command=9,
        chip_select=39,
    )
    display = ST7796(
        bus,
        width=222,
        height=480,
        colstart=49,
        rowstart=0,
        rotation=270,
        mirrored=False,
        color_depth=16,
        bgr=True,
        reverse_bytes_in_word=True,
        invert=True,
        brightness=1.0,
        backlight_pin=48,
        backlight_on_high=True,
        reset_pin=47,
        reset_high=False,
    )
    i2c = I2C(0, sda=Pin(5), scl=Pin(6), freq=100_000)
    touch = CST226(i2c, irq_pin=21, rst_pin=13)
    app = appdev.App(
        displays=[display],
        touch_read=touch.get_point,
        touch_rotation_table=(0, 5, 6, 3),
    )

    # Import after constructing App: this is display_driver's documented path
    # for binding a public displaydev driver without a flat board_config module.
    # Re-execute it after a same-runtime teardown so its documented import-time
    # binding observes the new current App instead of a prior deinitialized one.
    sys.modules.pop("display_driver", None)
    import display_driver
    event_loop = display_driver.event_loop.current_instance()
    if event_loop is None:
        raise RuntimeError("PyDevices LVGL event loop was not created")
    lv_display = lv.display_get_default()
    controller = PyDevicesDisplayController(
        app, display, lv_display, lv, event_loop, _lvgl_input_devices(lv)
    )
    return PyDevicesModernPlatform(
        controller, display, touch, app, ide_button_pin=12, lvgl=lv
    )
