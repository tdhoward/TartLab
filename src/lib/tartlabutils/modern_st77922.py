"""Reusable ST77922 transport and ownership adapter for modern boards."""

from tartlabutils.modern import (
    DisplayFrameSync,
    DirectRGB565Surface,
    GAME_OWNER,
    ModernDisplayController,
    ModernPlatform,
    UI_OWNER,
)
from tartlabutils.board import pin_definition

try:
    from tartlabutils._modern_emitters import (
        copy_rgb565_rows_between as _copy_rows_viper,
    )
except ImportError:
    _copy_rows_viper = None


_WRITE_COLOR = 0x32
_RAMWR = 0x2C
_TEOFF = 0x34
_TEON = 0x35
_TE_VBLANK_ONLY = b"\x00"
_COLUMN_ALIGNMENT = 4


def _qspi_color_command(command):
    return (_WRITE_COLOR << 24) | ((command & 0xFF) << 8)


def _copy_rows(source, target, source_start, target_start,
               row_bytes, row_count, source_stride, target_stride):
    if _copy_rows_viper is not None:
        _copy_rows_viper(
            source, target, source_start, target_start,
            row_bytes, row_count, source_stride, target_stride)
        return
    source = memoryview(source)
    target = memoryview(target)
    for row in range(row_count):
        source_row = source_start + row * source_stride
        target_row = target_start + row * target_stride
        target[target_row:target_row + row_bytes] = (
            source[source_row:source_row + row_bytes])


class ST77922DirectRGB565Surface(DirectRGB565Surface):
    """Direct surface that preserves ST77922-aligned neighboring pixels."""

    column_alignment = _COLUMN_ALIGNMENT
    requires_full_frame_seed = True

    def __init__(self, controller, bus, panel, width, height, transfer_rows,
                 allocation_flags, buffer_allocator, buffer_free,
                 shadow_flags, frame_sync=None):
        super().__init__(
            controller, bus, panel, width, height,
            allocation_flags=allocation_flags,
            buffer_allocator=buffer_allocator,
            buffer_free=buffer_free,
            frame_sync=frame_sync,
        )
        self._shadow = buffer_allocator(
            width * height * self.bytes_per_pixel, shadow_flags)
        self._scratch = buffer_allocator(
            width * transfer_rows * self.bytes_per_pixel, allocation_flags)
        if self._shadow is None or self._scratch is None:
            if self._shadow is not None:
                buffer_free(self._shadow)
            if self._scratch is not None:
                buffer_free(self._scratch)
            raise MemoryError("unable to allocate ST77922 direct buffers")
        self._shadow_valid = False
        self._resources_freed = False
        self._qspi_ramwr = _qspi_color_command(_RAMWR)

    @property
    def shadow_valid(self):
        return self._shadow_valid

    def invalidate_shadow(self):
        self._shadow_valid = False

    def _copy_to_shadow(self, buffer, x, y, width, height):
        row_bytes = width * self.bytes_per_pixel
        shadow_stride = self.width * self.bytes_per_pixel
        shadow_start = y * shadow_stride + x * self.bytes_per_pixel
        _copy_rows(
            buffer, self._shadow, 0, shadow_start,
            row_bytes, height, row_bytes, shadow_stride)

    def _send(self, buffer, x, y, width, height, wait):
        self._controller.begin_direct_transfer()
        try:
            panel_x, panel_y = self._set_window(x, y, width, height)
            self._bus.tx_color(
                self._qspi_ramwr,
                buffer,
                panel_x,
                panel_y,
                panel_x + width - 1,
                panel_y + height - 1,
                0,
                True,
            )
        except Exception:
            self._controller.cancel_direct_transfer()
            self._shadow_valid = False
            raise
        if wait:
            self.wait()

    def _send_shadow_region(self, x, y, width, height):
        row_bytes = width * self.bytes_per_pixel
        shadow_stride = self.width * self.bytes_per_pixel
        rows_per_transfer = len(self._scratch) // row_bytes
        if rows_per_transfer < 1:
            raise MemoryError("ST77922 direct scratch buffer is too small")
        row = 0
        while row < height:
            rows = min(rows_per_transfer, height - row)
            transfer_size = rows * row_bytes
            shadow_start = (
                (y + row) * shadow_stride + x * self.bytes_per_pixel)
            _copy_rows(
                self._shadow, self._scratch, shadow_start, 0,
                row_bytes, rows, shadow_stride, row_bytes)
            self._send(
                self._scratch[:transfer_size], x, y + row, width, rows, True)
            row += rows

    def write(self, buffer, x, y, width, height, wait=True):
        self._validate_region(buffer, x, y, width, height)
        full_frame = (
            x == 0 and y == 0 and
            width == self.width and height == self.height)
        if not self._shadow_valid and not full_frame:
            raise RuntimeError(
                "ST77922 direct mode requires a full-frame seed before "
                "partial writes")

        aligned_x = x & ~(_COLUMN_ALIGNMENT - 1)
        aligned_end = (
            (x + width + _COLUMN_ALIGNMENT - 1) &
            ~(_COLUMN_ALIGNMENT - 1))
        aligned_width = aligned_end - aligned_x
        if not wait and (aligned_x != x or aligned_width != width):
            raise ValueError(
                "unaligned ST77922 dirty rectangles require wait=True")
        if full_frame and not wait:
            raise ValueError("ST77922 full-frame seeds require wait=True")

        self._copy_to_shadow(buffer, x, y, width, height)
        if full_frame:
            self._shadow_valid = True
            self._send_shadow_region(0, 0, self.width, self.height)
            return
        if aligned_x == x and aligned_width == width:
            self._send(buffer, x, y, width, height, wait)
            return
        self._send_shadow_region(aligned_x, y, aligned_width, height)

    blit_rect = write

    def free_resources(self):
        if self._resources_freed:
            return
        self.wait()
        self._buffer_free(self._scratch)
        self._buffer_free(self._shadow)
        self._scratch = None
        self._shadow = None
        self._resources_freed = True


class ST77922DisplayController(ModernDisplayController):
    """Modern ownership controller with an ISR-safe completion boundary."""

    def __init__(self, bus, panel, lv_display, lvgl, task_handler,
                  input_device, allocation_flags, buffer_allocator,
                  buffer_free, shadow_flags, width, height, transfer_rows,
                  frame_sync=None):
        self._callback_failed = False
        super().__init__(
            bus, panel, lv_display, lvgl, task_handler, input_device,
            width=width, height=height,
            allocation_flags=allocation_flags,
            buffer_allocator=buffer_allocator,
            buffer_free=buffer_free,
        )
        self.surface = ST77922DirectRGB565Surface(
            self, bus, panel, width, height, transfer_rows,
            allocation_flags, buffer_allocator, buffer_free, shadow_flags,
            frame_sync)

    def _transfer_complete(self):
        self._transfer_pending = False
        if self._owner == UI_OWNER:
            try:
                self._lv_display.flush_ready()
            except Exception:
                self._callback_failed = True

    def wait_for_transfer(self, timeout_ms=1000):
        ModernDisplayController.wait_for_transfer(self, timeout_ms)
        if self._callback_failed:
            self._callback_failed = False
            surface = getattr(self, "surface", None)
            invalidate = getattr(surface, "invalidate_shadow", None)
            if invalidate is not None:
                invalidate()
            raise RuntimeError("display completion callback failed")

    def acquire_game(self, timeout_ms=1000):
        entering = self._owner != GAME_OWNER
        surface = ModernDisplayController.acquire_game(self, timeout_ms)
        surface.enable_frame_sync()
        if entering:
            surface.invalidate_shadow()
        return surface

    def acquire_ui(self, timeout_ms=1000):
        ModernDisplayController.acquire_ui(self, timeout_ms)
        self.surface.disable_frame_sync()


class Platform(ModernPlatform):
    def deinit(self):
        if self._deinitialized:
            return
        self.game_surface.free_resources()
        super().deinit()


def create_controller(board, bus, panel, lv_display, lvgl, handler, pointer,
                      flags, lcd_bus):
    frame_sync = _create_frame_sync(board, panel)
    width, height = board["display"]["logical_size"]
    return ST77922DisplayController(
        bus, panel, lv_display, lvgl, handler, pointer, flags,
        lcd_bus.allocate_buffer, lcd_bus.free_buffer,
        lcd_bus.MEMORY_SPIRAM, width, height,
        board["display"]["transfer_rows"], frame_sync)


def _create_frame_sync(board, panel, pin_factory=None):
    definition = pin_definition(board, "DISPLAY_SYNC")
    if definition is None:
        return None
    if pin_factory is None:
        from machine import Pin
        pin_factory = Pin

    # The vendor table leaves TE in V+H mode. Direct presentation needs one
    # safe edge per frame, so the reusable controller adapter selects V-blank.
    panel.set_params(_TEOFF, None)
    panel.set_params(_TEON, _TE_VBLANK_ONLY)
    pin = pin_factory(
        definition["number"], getattr(pin_factory, "IN", 0))
    return DisplayFrameSync(
        pin, definition.get("active_high", True), enabled=False)
