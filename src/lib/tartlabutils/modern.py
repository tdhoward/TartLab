"""LVGL and direct-game rendering boundary for the modern firmware profile.

The upstream display driver owns panel initialization and LVGL flushing.  This
module owns the public TartLab rendering contract: callers never receive the
driver's private bus or LVGL fields, and only one renderer can submit transfers
at a time.
"""

import time


UI_OWNER = "ui"
GAME_OWNER = "game"
_RAMWR = 0x2C
_CASET = 0x2A
_RASET = 0x2B


class DisplayOwnershipError(RuntimeError):
    """Raised when a renderer uses the display without owning it."""


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


class DirectRGB565Surface:
    """Public dirty-rectangle RGB565 surface backed by the native LCD bus.

    Buffers passed to :meth:`write` must remain unchanged until the method
    returns, or until :meth:`wait` returns when ``wait=False`` is used.
    Each pixel is big-endian (panel wire order), matching LVGL's
    ``RGB565_SWAPPED`` output and avoiding a CPU byte-swap in ``lcd_bus``.
    Coordinates and rectangle ends are expressed in the current logical
    display orientation.
    """

    bytes_per_pixel = 2
    color_format = "RGB565_BE"

    def __init__(self, controller, bus, panel, width, height,
                 offset_x=0, offset_y=0, allocation_flags=None,
                 buffer_allocator=None, buffer_free=None):
        self._controller = controller
        self._bus = bus
        self._panel = panel
        self.width = width
        self.height = height
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._allocation_flags = allocation_flags
        self._buffer_allocator = buffer_allocator
        self._buffer_free = buffer_free
        self._params = bytearray(4)
        self._params_view = memoryview(self._params)

    def _validate_region(self, buffer, x, y, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("rectangle is outside the direct surface")
        expected = width * height * self.bytes_per_pixel
        if len(buffer) != expected:
            raise ValueError(
                "RGB565 buffer has %s bytes; expected %s" %
                (len(buffer), expected))

    def _set_window_axis(self, command, start, end):
        params = self._params
        params[0] = (start >> 8) & 0xFF
        params[1] = start & 0xFF
        params[2] = (end >> 8) & 0xFF
        params[3] = end & 0xFF
        self._panel.set_params(command, self._params_view)

    def _set_window(self, x, y, width, height):
        x += self._offset_x
        y += self._offset_y
        self._set_window_axis(_CASET, x, x + width - 1)
        self._set_window_axis(_RASET, y, y + height - 1)
        return x, y

    def write(self, buffer, x, y, width, height, wait=True):
        """Transfer one packed RGB565 rectangle through the native LCD bus."""
        self._validate_region(buffer, x, y, width, height)
        self._controller.begin_direct_transfer()
        try:
            panel_x, panel_y = self._set_window(x, y, width, height)
            self._bus.tx_color(
                _RAMWR, buffer, panel_x, panel_y,
                panel_x + width - 1, panel_y + height - 1,
                self._controller.rotation, True)
        except Exception:
            self._controller.cancel_direct_transfer()
            raise
        if wait:
            self.wait()

    blit_rect = write

    def wait(self, timeout_ms=1000):
        """Wait until the current direct DMA transfer has completed."""
        self._controller.wait_for_transfer(timeout_ms)

    @property
    def busy(self):
        return self._controller.transfer_pending

    def allocate_buffer(self, width, height):
        """Allocate a reusable RGB565 buffer, preferring native DMA memory."""
        size = width * height * self.bytes_per_pixel
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if self._allocation_flags is None:
            return bytearray(size)
        if self._buffer_allocator is None:
            raise RuntimeError("native direct-buffer allocator is unavailable")
        buffer = self._buffer_allocator(size, self._allocation_flags)
        if buffer is None:
            raise MemoryError("unable to allocate direct RGB565 buffer")
        return buffer

    def free_buffer(self, buffer):
        """Release a buffer returned by :meth:`allocate_buffer`."""
        if self._allocation_flags is not None:
            self.wait()
            self._buffer_free(buffer)


class ModernDisplayController:
    """Serialize LVGL and direct rendering over one completion-signaled bus."""

    def __init__(self, bus, panel, lv_display, lvgl, task_handler,
                 input_device=None, width=None, height=None,
                 offset_x=0, offset_y=0, allocation_flags=None,
                 buffer_allocator=None, buffer_free=None):
        self._bus = bus
        self._panel = panel
        self._lv_display = lv_display
        self._lvgl = lvgl
        self._task_handler = task_handler
        self._input = input_device
        self._owner = UI_OWNER
        self._transfer_pending = False
        self._task_paused = False

        if width is None:
            width = lv_display.get_horizontal_resolution()
        if height is None:
            height = lv_display.get_vertical_resolution()
        self.surface = DirectRGB565Surface(
            self, bus, panel, width, height, offset_x, offset_y,
            allocation_flags, buffer_allocator, buffer_free)

        # lcd_bus has one completion callback.  TartLab multiplexes that public
        # callback so an LVGL flush and a direct transfer cannot race.
        bus.register_callback(self._transfer_complete)
        flush_start = getattr(getattr(lvgl, "EVENT", None), "FLUSH_START", None)
        if flush_start is None:
            raise RuntimeError("pinned LVGL FLUSH_START event is unavailable")
        lv_display.add_event_cb(self._lvgl_flush_started, flush_start, None)

    @property
    def owner(self):
        return self._owner

    @property
    def transfer_pending(self):
        return self._transfer_pending

    @property
    def rotation(self):
        return self._lv_display.get_rotation()

    def _lvgl_flush_started(self, unused_event):
        if self._owner != UI_OWNER:
            raise DisplayOwnershipError(
                "LVGL attempted to flush while game mode owned the display")
        self._transfer_pending = True

    def _transfer_complete(self, *unused):
        # Clear first: flush_ready can immediately begin another queued LVGL
        # flush, whose FLUSH_START event must leave this flag set again.
        self._transfer_pending = False
        if self._owner == UI_OWNER:
            self._lv_display.flush_ready()

    def wait_for_transfer(self, timeout_ms=1000):
        started = _ticks_ms()
        while self._transfer_pending:
            if _ticks_diff(_ticks_ms(), started) >= timeout_ms:
                raise RuntimeError("display transfer did not complete")
            _sleep_ms(1)

    def begin_direct_transfer(self):
        if self._owner != GAME_OWNER:
            raise DisplayOwnershipError(
                "direct surface requires game display ownership")
        if self._transfer_pending:
            raise DisplayOwnershipError(
                "a direct display transfer is already in progress")
        self._transfer_pending = True

    def cancel_direct_transfer(self):
        self._transfer_pending = False

    def acquire_game(self, timeout_ms=1000):
        """Pause LVGL, drain its final flush, and return the direct surface."""
        if self._owner == GAME_OWNER:
            return self.surface
        self._task_handler.disable()
        self._task_paused = True
        if self._input is not None:
            self._input.enable(False)
        try:
            self._lvgl.refr_now(self._lv_display)
            self.wait_for_transfer(timeout_ms)
        except Exception:
            if self._input is not None:
                self._input.enable(True)
            self._task_handler.enable()
            self._task_paused = False
            raise
        self._owner = GAME_OWNER
        return self.surface

    def acquire_ui(self, timeout_ms=1000):
        """Drain direct DMA, restore LVGL input/ticks, and force a redraw."""
        if self._owner == UI_OWNER:
            return
        self.wait_for_transfer(timeout_ms)
        self._owner = UI_OWNER
        if self._input is not None:
            self._input.enable(True)
        screen = self._lvgl.screen_active()
        screen.invalidate()
        if self._task_paused:
            self._task_handler.enable()
            self._task_paused = False
        self._lvgl.refr_now(self._lv_display)
        self.wait_for_transfer(timeout_ms)


class ModernIDEView:
    """Small TartLab status view rendered entirely with LVGL widgets."""

    def __init__(self, controller, lvgl):
        controller.acquire_ui()
        self._controller = controller
        self._lv = lvgl
        self._screen = lvgl.obj()
        self._screen.set_style_bg_color(lvgl.color_hex(0x000000), 0)
        self._screen.set_style_border_width(3, 0)
        self._screen.set_style_border_color(lvgl.color_hex(0x0000FF), 0)

        self._title = lvgl.label(self._screen)
        self._network = lvgl.label(self._screen)
        self._address = lvgl.label(self._screen)
        self._hostname = lvgl.label(self._screen)
        self._status = lvgl.label(self._screen)
        for label in (
                self._title, self._network, self._address,
                self._hostname, self._status):
            label.set_text("")
        self._app_error_indicator = None
        self._progress = lvgl.bar(self._screen)
        animation = getattr(lvgl, "ANIM", None)
        self._animation_off = getattr(animation, "OFF", False)
        self._progress.set_range(0, 1)
        progress_width = max(1, (controller.surface.width * 7) // 8)
        self._progress.set_size(progress_width, 20)
        self._progress.align(lvgl.ALIGN.BOTTOM_MID, 0, -8)
        lvgl.screen_load(self._screen)

    def _set_label(self, label, text, align, y):
        label.set_text(text)
        label.align(align, 0, y)

    def show_startup(self, version):
        self._set_label(
            self._title, "TARTLAB " + version, self._lv.ALIGN.TOP_MID, 18)

    def show_network(self, wifi_name, address, hostname=None):
        self._set_label(
            self._network, "WiFi: " + wifi_name, self._lv.ALIGN.CENTER, -28)
        self._set_label(
            self._address, address, self._lv.ALIGN.CENTER, 0)
        self._set_label(
            self._hostname, (hostname + ".local") if hostname else "",
            self._lv.ALIGN.CENTER, 28)

    def show_update_progress(self, status, step, steps):
        if step > steps:
            steps = step
        self._set_label(
            self._status, "%s  Step %s of %s" % (status, step, steps),
            self._lv.ALIGN.BOTTOM_MID, -36)
        self._progress.set_range(0, steps + 1)
        self._progress.set_value(step, self._animation_off)

    def show_app_error(self):
        if self._app_error_indicator is not None:
            return
        indicator = self._lv.obj(self._screen)
        indicator.set_size(14, 14)
        indicator.align(self._lv.ALIGN.TOP_RIGHT, -12, 12)
        indicator.set_style_bg_color(self._lv.color_hex(0xFF0000), 0)
        indicator.set_style_border_width(0, 0)
        indicator.set_style_radius(7, 0)
        self._app_error_indicator = indicator


class ModernPlatform:
    """TartLab platform implementation for the pinned modern LVGL firmware."""

    def __init__(self, controller, panel, input_device, ide_button_pin=None,
                 pin_factory=None, network_module=None, lvgl=None,
                 touch_keep_awake=None):
        self.controller = controller
        self.display = panel
        self.input = input_device
        self.game_surface = controller.surface
        self.ide_button_pin = ide_button_pin
        self.width = controller.surface.width
        self.height = controller.surface.height
        self._pin_factory = pin_factory
        self._button = None
        self._network_module = network_module
        self._lvgl = lvgl or controller._lvgl
        self._touch_keep_awake = touch_keep_awake
        self._deinitialized = False
        self.capabilities = {
            "display": True,
            "touch": input_device is not None,
            "ide_button": ide_button_pin is not None,
            "backlight": True,
            "network": True,
            "lvgl_ui": True,
            "direct_rgb565": True,
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
                self.ide_button_pin, getattr(pin_factory, "IN", 0))
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

    @property
    def lvgl(self):
        """Return the supported LVGL module for modern user interfaces."""
        return self._lvgl

    def read_game_touch(self):
        """Return the current logical game-mode touch point, or ``None``.

        Native pointer drivers report panel coordinates.  Keep that private
        protocol inside the platform boundary and expose coordinates in the
        same logical orientation used by :attr:`game_surface`.
        """
        if self.controller.owner != GAME_OWNER:
            raise DisplayOwnershipError(
                "game touch input requires game display ownership")
        if self.input is None:
            return None
        get_coords = getattr(self.input, "_get_coords", None)
        if get_coords is None:
            raise RuntimeError("modern pointer does not support game polling")
        try:
            point = get_coords()
        except OSError:
            return None
        pressed = getattr(self.input, "PRESSED", 1)
        if point is None or point[0] != pressed:
            return None
        x, y = point[1], point[2]
        rotations = getattr(self._lvgl, "DISPLAY_ROTATION", None)
        rotation = self.controller.rotation
        if rotations is None or rotation == getattr(rotations, "_0", 0):
            return x, y
        if rotation == getattr(rotations, "_90", 1):
            return self.width - 1 - y, x
        if rotation == getattr(rotations, "_180", 2):
            return self.width - 1 - x, self.height - 1 - y
        if rotation == getattr(rotations, "_270", 3):
            return y, self.height - 1 - x
        raise RuntimeError("unsupported display rotation")

    def create_ide_view(self):
        return ModernIDEView(self.controller, self._lvgl)

    def keep_touch_awake(self):
        if self._touch_keep_awake is not None:
            self._touch_keep_awake()

    def clear_display(self):
        self.enter_ui_mode()
        screen = self._lvgl.screen_active()
        screen.set_style_bg_color(self._lvgl.color_hex(0x000000), 0)
        screen.invalidate()
        self._lvgl.refr_now(self.controller._lv_display)
        self.controller.wait_for_transfer()

    def show_error(self):
        self.enter_ui_mode()
        screen = self._lvgl.screen_active()
        screen.set_style_bg_color(self._lvgl.color_hex(0xFF0000), 0)
        screen.invalidate()
        self._lvgl.refr_now(self.controller._lv_display)

    def set_brightness(self, value):
        self.display.set_backlight(value * 100)

    def sleep(self, seconds):
        time.sleep(seconds)

    def deinit(self):
        if self._deinitialized:
            return
        self.controller.wait_for_transfer()
        self._task_handler_deinit()

        # The upstream Python wrappers retain displays and input devices in
        # class-level registries.  Bus teardown alone therefore leaves LVGL
        # objects alive across same-runtime reinitialization.  Delete the
        # native input first, then invoke the display wrapper's own finalizer,
        # which removes it from the registry and releases the LVGL display.
        if self.input is not None:
            self.input.enable(False)
            indev = getattr(self.input, "_indev_drv", None)
            delete = getattr(indev, "delete", None)
            if delete is not None:
                delete()
            registry = getattr(self.input.__class__, "_indevs", None)
            if registry is not None and self.input in registry:
                registry.remove(self.input)

        finalize_display = getattr(self.display, "__del__", None)
        if finalize_display is not None:
            finalize_display()

        deinit = getattr(self._bus(), "deinit", None)
        if deinit is not None:
            deinit()
        self._deinitialized = True

    def _task_handler_deinit(self):
        deinit = getattr(self.controller._task_handler, "deinit", None)
        if deinit is not None:
            deinit()

    def _bus(self):
        return self.controller._bus
