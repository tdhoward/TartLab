"""Experimental TartLab board payload for the Elecrow DLE06235B.

Board pins and ST77922 transport constraints live here so applications keep
using the board-neutral :mod:`tartlabutils.platform` contract.
"""

from tartlabutils.modern import (
    DirectRGB565Surface,
    GAME_OWNER,
    ModernDisplayController,
    ModernIDEView,
    ModernPlatform,
    UI_OWNER,
)


IDE_BUTTON_PIN = None


_WRITE_COLOR = 0x32
_RAMWR = 0x2C
_COLUMN_ALIGNMENT = 4
_DIRECT_ROWS = 24


def _qspi_color_command(command):
    return (_WRITE_COLOR << 24) | ((command & 0xFF) << 8)


class ST77922DirectRGB565Surface(DirectRGB565Surface):
    """Direct surface that preserves ST77922-aligned neighboring pixels.

    The controller requires the physical CASET start and width to be multiples
    of four.  A game must seed the shadow with one full-frame write after each
    UI-to-game ownership transition.  Subsequent arbitrary dirty rectangles
    are copied into that shadow; unaligned edges are transferred from the
    shadow rather than read outside the caller's buffer or filled with guessed
    pixels.
    """

    column_alignment = _COLUMN_ALIGNMENT
    requires_full_frame_seed = True

    def __init__(self, controller, bus, panel, width, height,
                 allocation_flags, buffer_allocator, buffer_free,
                 shadow_flags):
        super().__init__(
            controller, bus, panel, width, height,
            allocation_flags=allocation_flags,
            buffer_allocator=buffer_allocator,
            buffer_free=buffer_free,
        )
        self._shadow = buffer_allocator(
            width * height * self.bytes_per_pixel, shadow_flags)
        self._scratch = buffer_allocator(
            width * _DIRECT_ROWS * self.bytes_per_pixel, allocation_flags)
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
        source = memoryview(buffer)
        row_bytes = width * self.bytes_per_pixel
        shadow_stride = self.width * self.bytes_per_pixel
        for row in range(height):
            source_start = row * row_bytes
            shadow_start = (y + row) * shadow_stride + (
                x * self.bytes_per_pixel)
            self._shadow[shadow_start:shadow_start + row_bytes] = (
                source[source_start:source_start + row_bytes])

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
            for chunk_row in range(rows):
                shadow_start = (y + row + chunk_row) * shadow_stride + (
                    x * self.bytes_per_pixel)
                scratch_start = chunk_row * row_bytes
                self._scratch[scratch_start:scratch_start + row_bytes] = (
                    self._shadow[shadow_start:shadow_start + row_bytes])
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
            raise ValueError(
                "ST77922 full-frame seeds require wait=True")

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


class ElecrowDisplayController(ModernDisplayController):
    """Modern ownership controller with an ISR-safe completion boundary."""

    def __init__(self, bus, panel, lv_display, lvgl, task_handler,
                 input_device, allocation_flags, buffer_allocator,
                 buffer_free, shadow_flags):
        self._callback_failed = False
        super().__init__(
            bus, panel, lv_display, lvgl, task_handler, input_device,
            width=320,
            height=480,
            allocation_flags=allocation_flags,
            buffer_allocator=buffer_allocator,
            buffer_free=buffer_free,
        )
        self.surface = ST77922DirectRGB565Surface(
            self, bus, panel, 320, 480,
            allocation_flags, buffer_allocator, buffer_free, shadow_flags)

    def _transfer_complete(self):
        # lcd_bus invokes this from an ESP-IDF ISR.  Do not print, allocate an
        # exception, or let an LVGL error escape into lcd_bus's fatal ISR
        # exception printer.  The main thread observes the sticky flag at the
        # next ownership/drain boundary.
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
        if entering:
            surface.invalidate_shadow()
        return surface


class ElecrowIDEView(ModernIDEView):
    """Portrait status view using the shared geometry-aware layout."""


class ElecrowPlatform(ModernPlatform):
    def create_ide_view(self):
        return ElecrowIDEView(self.controller, self._lvgl)

    def deinit(self):
        if self._deinitialized:
            return
        self.game_surface.free_resources()
        super().deinit()


def create_elecrow_dle06235b_platform():
    """Construct the experimental native-portrait DLE06235B platform."""
    import i2c
    import lcd_bus
    import lvgl as lv
    import machine
    import st77922
    import st77922_touch
    import task_handler

    spi = machine.SPI.Bus(
        host=2,
        sck=12,
        quad_pins=(11, 13, 14, 9),
    )
    bus = lcd_bus.SPIBus(
        spi_bus=spi,
        dc=-1,
        freq=40_000_000,
        cs=10,
        quad=True,
    )
    dma_flags = lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
    frame_buffer_size = 320 * _DIRECT_ROWS * 2
    frame_buffer1 = bus.allocate_framebuffer(frame_buffer_size, dma_flags)
    frame_buffer2 = bus.allocate_framebuffer(frame_buffer_size, dma_flags)
    if frame_buffer1 is None or frame_buffer2 is None:
        raise MemoryError("unable to allocate dual ST77922 render buffers")

    panel = st77922.ST77922(
        data_bus=bus,
        display_width=320,
        display_height=480,
        frame_buffer1=frame_buffer1,
        frame_buffer2=frame_buffer2,
        reset_pin=48,
        reset_state=st77922.STATE_LOW,
        backlight_pin=41,
        color_space=lv.COLOR_FORMAT.RGB565_SWAPPED,
        rgb565_byte_swap=False,
    )
    panel.reset()
    panel.init()
    panel.set_rotation(lv.DISPLAY_ROTATION._0)
    panel.set_backlight(100)

    i2c_bus = i2c.I2C.Bus(
        host=0, scl=39, sda=38, freq=100_000, use_locks=False)
    touch_device = i2c.I2C.Device(
        bus=i2c_bus,
        dev_id=st77922_touch.I2C_ADDR,
        reg_bits=st77922_touch.BITS,
    )
    pointer = st77922_touch.ST77922Touch(
        touch_device,
        startup_rotation=lv.DISPLAY_ROTATION._0,
    )

    handler = task_handler.TaskHandler()
    controller = ElecrowDisplayController(
        bus,
        panel,
        lv.display_get_default(),
        lv,
        handler,
        pointer,
        dma_flags,
        lcd_bus.allocate_buffer,
        lcd_bus.free_buffer,
        lcd_bus.MEMORY_SPIRAM,
    )
    platform = ElecrowPlatform(
        controller, panel, pointer, ide_button_pin=None, lvgl=lv)
    # Keep native bus wrappers alive for the lifetime of the platform.
    platform._spi_bus = spi
    platform._i2c_bus = i2c_bus
    platform._touch_device = touch_device
    return platform


def create_platform():
    return create_elecrow_dle06235b_platform()
