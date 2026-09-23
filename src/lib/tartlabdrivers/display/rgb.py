"""Ownership and packed rectangles for the pinned native RGB scanout bus.

The completion callback releases the caller's source buffer after copying it
into the native back buffer. Presentation and VSYNC follow asynchronously;
neither ``wait`` nor ownership handover promises a visible frame boundary.
"""

from tartlabutils.runtime import DirectRGB565Surface, DisplayController, Platform


class RGBSurface(DirectRGB565Surface):
    def write(self, buffer, x, y, width, height, wait=True):
        """Copy a big-endian RGB565 rectangle without modifying its bytes."""
        self._validate_region(buffer, x, y, width, height)
        self._controller.begin_direct_transfer()
        try:
            self._controller.submit(buffer, x, y, x + width - 1,
                                    y + height - 1, True)
        except Exception:
            self._controller.cancel_direct_transfer()
            raise
        if wait:
            self.wait()

    blit_rect = write


class RGBDisplayController(DisplayController):
    def __init__(self, bus, panel, lv_display, lvgl, handler, pointer,
                 width, height, flags, allocator, free, partial_y_end_exclusive):
        if lv_display.get_rotation() != lvgl.DISPLAY_ROTATION._0:
            raise ValueError("RGB direct rendering currently requires native orientation")
        super().__init__(bus, panel, lv_display, lvgl, handler, pointer,
                         width=width, height=height, allocation_flags=flags,
                         buffer_allocator=allocator, buffer_free=free)
        self._width = width
        self._partial_y_end_exclusive = partial_y_end_exclusive
        self.surface = RGBSurface(self, bus, panel, width, height,
                                  allocation_flags=flags,
                                  buffer_allocator=allocator, buffer_free=free)
        # Keep the native RGB bus visible to the upstream panel wrapper. Only
        # bridge its flush callback, so LVGL and direct writes share endpoints.
        lv_display.set_flush_cb(self._flush)

    def submit(self, buffer, x1, y1, x2, y2, last):
        if self.rotation != self._lvgl.DISPLAY_ROTATION._0:
            raise ValueError("RGB direct rendering currently requires native orientation")
        # The pinned rotation-0 native fast path takes inclusive full-width
        # ends, but its partial-width row loop takes an exclusive y end.
        # The board's declarative compatibility setting selects that ABI.
        if self._partial_y_end_exclusive and (x1 != 0 or x2 != self._width - 1):
            y2 += 1
        self._bus.tx_color(-1, buffer, x1, y1, x2, y2, self.rotation, last)

    def _flush(self, unused_display, area, color):
        size = (area.x2 - area.x1 + 1) * (area.y2 - area.y1 + 1) * 2
        self.submit(color.__dereference__(size), area.x1, area.y1,
                    area.x2, area.y2, self._lv_display.flush_is_last())


def create_controller(board, bus, panel, lv_display, lvgl, handler, pointer,
                      flags, lcd_bus):
    display = board["display"]
    if display.get("offset", (0, 0)) != (0, 0):
        raise ValueError("RGB direct rendering does not support panel offsets")
    width, height = display["logical_size"]
    return RGBDisplayController(
        bus, panel, lv_display, lvgl, handler, pointer, width, height,
        flags, lcd_bus.allocate_buffer, lcd_bus.free_buffer,
        display.get("partial_y_end_exclusive", False))
