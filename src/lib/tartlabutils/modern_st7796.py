"""Reusable ST7796 scanout-scroll adapter for modern direct surfaces."""

from tartlabutils.modern import (
    DirectRGB565Surface,
    GAME_OWNER,
    ModernDisplayController,
    ModernPlatform,
)


_VSCRDEF = 0x33
_VSCSAD = 0x37


def _quarter_turns(rotation):
    rotations = {0: 0, 1: 1, 2: 2, 3: 3,
                 90: 1, 180: 2, 270: 3}
    try:
        return rotations[rotation]
    except (KeyError, TypeError):
        raise ValueError("rotation must be a quarter turn")


def _map_area(x, y, width, height, surface_width, surface_height,
              rotation):
    turns = _quarter_turns(rotation)
    if turns == 0:
        return x, y, width, height
    if turns == 1:
        return y, surface_height - x - width, height, width
    if turns == 2:
        return (surface_width - x - width,
                surface_height - y - height, width, height)
    return surface_width - y - height, x, height, width


def _map_vector(dx, dy, rotation):
    turns = _quarter_turns(rotation)
    if turns == 0:
        return dx, dy
    if turns == 1:
        return dy, -dx
    if turns == 2:
        return -dx, -dy
    return -dy, dx


class ST7796ScrollAdapter:
    """Own ST7796 vertical-scroll registers and current scanout mapping."""

    def __init__(self, controller, panel, surface_width, surface_height,
                 panel_rotation, native_height, qualified_rotations):
        self._controller = controller
        self._panel = panel
        self.panel_rotation = panel_rotation
        self._turns = _quarter_turns(panel_rotation)
        self._axis = "x" if self._turns & 1 else "y"
        self._axis_extent = (
            surface_width if self._axis == "x" else surface_height)
        if self._axis_extent != native_height:
            raise ValueError(
                "ST7796 scroll axis must match the native panel height")
        self._native_height = native_height
        self._qualified = panel_rotation in tuple(qualified_rotations)
        # Native row addresses increase with the surface coordinate at 0/270,
        # and decrease at 90/180.
        self._native_sign = 1 if self._turns in (0, 3) else -1
        self._region_start = None
        self._region_extent = None
        self._native_top = 0
        self._origin = 0
        self._params = bytearray(6)
        self._params_view = memoryview(self._params)

    @property
    def qualified(self):
        return self._qualified

    @property
    def axis(self):
        return self._axis

    @property
    def active(self):
        return self._region_start is not None and self._origin != 0

    def _require_game(self):
        if self._controller.owner != GAME_OWNER:
            raise RuntimeError(
                "panel scrolling requires game display ownership")
        self._controller.wait_for_transfer()

    def _set_definition(self, top, extent, bottom):
        params = self._params
        params[0] = (top >> 8) & 0xFF
        params[1] = top & 0xFF
        params[2] = (extent >> 8) & 0xFF
        params[3] = extent & 0xFF
        params[4] = (bottom >> 8) & 0xFF
        params[5] = bottom & 0xFF
        self._panel.set_params(_VSCRDEF, self._params_view)

    def _set_start(self, address):
        params = self._params
        params[0] = (address >> 8) & 0xFF
        params[1] = address & 0xFF
        self._panel.set_params(_VSCSAD, self._params_view[:2])

    def _native_areas(self, start, extent):
        if self._native_sign > 0:
            top = start
        else:
            top = self._native_height - start - extent
        return top, self._native_height - top - extent

    def _restore_registers(self):
        if self._region_start is not None:
            self._set_start(self._native_top)
        self._set_definition(0, self._native_height, 0)
        self._set_start(0)

    def reset(self):
        """Restore ordinary, unscrolled scanout while game mode owns it."""
        if self._region_start is None:
            return
        self._require_game()
        try:
            self._restore_registers()
        finally:
            self._region_start = None
            self._region_extent = None
            self._native_top = 0
            self._origin = 0

    def can_scroll(self, start, extent, delta):
        return (
            self._qualified and extent > 0 and delta and
            abs(delta) < extent and start >= 0 and
            start + extent <= self._axis_extent)

    def scroll(self, start, extent, delta):
        """Move scanout by one surface-axis delta and retain its mapping."""
        if not self.can_scroll(start, extent, delta):
            return False
        self._require_game()
        if (self._region_start != start or
                self._region_extent != extent):
            self.reset()
            origin = 0
        else:
            origin = self._origin
        top, bottom = self._native_areas(start, extent)
        origin = (origin - delta) % extent
        native_offset = (self._native_sign * origin) % extent
        try:
            self._set_definition(top, extent, bottom)
            self._set_start(top + native_offset)
        except Exception:
            try:
                self._restore_registers()
            finally:
                self._region_start = None
                self._region_extent = None
                self._native_top = 0
                self._origin = 0
            raise
        self._region_start = start
        self._region_extent = extent
        self._native_top = top
        self._origin = origin
        return True

    def _map_interval(self, start, extent):
        region_start = self._region_start
        if region_start is None or self._origin == 0:
            return ((0, extent, start),)
        region_end = region_start + self._region_extent
        end = start + extent
        position = start
        result = []
        while position < end:
            if position < region_start:
                length = min(end, region_start) - position
                target = position
            elif position >= region_end:
                length = end - position
                target = position
            else:
                target = region_start + (
                    position - region_start + self._origin
                ) % self._region_extent
                length = min(end - position, region_end - position,
                             region_end - target)
            result.append((position - start, length, target))
            position += length
        return tuple(result)

    def map_regions(self, x, y, width, height):
        """Map one visible rectangle into current GRAM coordinates."""
        if self._axis == "x":
            return tuple(
                (source, 0, extent, height, target, y)
                for source, extent, target in self._map_interval(x, width))
        return tuple(
            (0, source, width, extent, x, target)
            for source, extent, target in self._map_interval(y, height))


class ST7796DirectRGB565Surface(DirectRGB565Surface):
    """Direct surface with optional ST7796 scanout address translation."""

    def __init__(self, controller, bus, panel, width, height, offset_x,
                 offset_y, transfer_rows, allocation_flags,
                 buffer_allocator, buffer_free, scroll_config,
                 native_height, panel_rotation):
        super().__init__(
            controller, bus, panel, width, height, offset_x, offset_y,
            allocation_flags, buffer_allocator, buffer_free)
        qualified = scroll_config.get("qualified_rotations", ())
        self._scroll = ST7796ScrollAdapter(
            controller, panel, width, height, panel_rotation,
            native_height, qualified)
        self._scroll_transfer_rows = transfer_rows
        self._scroll_scratch = None
        self._resources_freed = False

    def scroll_capabilities(self, rotation=0):
        """Describe supported axes in final logical canvas coordinates."""
        if not self._scroll.qualified:
            axes = ()
        else:
            turns = _quarter_turns(rotation)
            axis = self._scroll.axis
            if turns & 1:
                axis = "y" if axis == "x" else "x"
            axes = (axis,)
        return {
            "axes": axes,
            "fixed_areas": bool(axes),
            "wraps": bool(axes),
            "full_orthogonal_axis": bool(axes),
        }

    def present_scroll(self, area, dx, dy, rotation=0):
        """Try to present a completed RAM scroll through panel scanout."""
        if not self._scroll.qualified:
            return False
        x, y, width, height = area
        x, y, width, height = _map_area(
            x, y, width, height, self.width, self.height, rotation)
        dx, dy = _map_vector(dx, dy, rotation)
        if self._scroll.axis == "x":
            if dy or not dx or y != 0 or height != self.height:
                return False
            start, extent, delta = x, width, dx
        else:
            if dx or not dy or x != 0 or width != self.width:
                return False
            start, extent, delta = y, height, dy
        return self._scroll.scroll(start, extent, delta)

    def reset_scroll(self):
        self._scroll.reset()

    def _ensure_scroll_scratch(self):
        if self._scroll_scratch is None:
            self._scroll_scratch = self.allocate_buffer(
                self.width, self._scroll_transfer_rows)
        return self._scroll_scratch

    def _send(self, buffer, x, y, width, height, wait):
        self._controller.begin_direct_transfer()
        try:
            panel_x, panel_y = self._set_window(x, y, width, height)
            self._bus.tx_color(
                0x2C, buffer, panel_x, panel_y,
                panel_x + width - 1, panel_y + height - 1,
                self._controller.rotation, True)
        except Exception:
            self._controller.cancel_direct_transfer()
            raise
        if wait:
            self.wait()

    def _send_piece(self, source, source_width, source_x, source_y,
                    width, height, target_x, target_y):
        row_bytes = source_width * self.bytes_per_pixel
        if source_x == 0 and width == source_width:
            start = source_y * row_bytes
            size = height * row_bytes
            self._send(source[start:start + size], target_x, target_y,
                       width, height, True)
            return

        scratch = memoryview(self._ensure_scroll_scratch())
        piece_row_bytes = width * self.bytes_per_pixel
        rows_per_transfer = len(scratch) // piece_row_bytes
        if rows_per_transfer < 1:
            raise MemoryError("scroll seam scratch buffer is too small")
        sent = 0
        while sent < height:
            rows = min(rows_per_transfer, height - sent)
            for row in range(rows):
                source_start = (
                    (source_y + sent + row) * row_bytes +
                    source_x * self.bytes_per_pixel)
                target_start = row * piece_row_bytes
                scratch[target_start:target_start + piece_row_bytes] = \
                    source[source_start:source_start + piece_row_bytes]
            size = rows * piece_row_bytes
            self._send(scratch[:size], target_x, target_y + sent,
                       width, rows, True)
            sent += rows

    def write(self, buffer, x, y, width, height, wait=True):
        self._validate_region(buffer, x, y, width, height)
        source = memoryview(buffer)
        pieces = self._scroll.map_regions(x, y, width, height)
        if len(pieces) == 1 and pieces[0] == (0, 0, width, height, x, y):
            return self._send(buffer, x, y, width, height, wait)
        if not wait:
            raise ValueError("mapped scroll writes require wait=True")
        for source_x, source_y, piece_width, piece_height, target_x, target_y \
                in pieces:
            self._send_piece(
                source, width, source_x, source_y,
                piece_width, piece_height, target_x, target_y)

    blit_rect = write

    def free_resources(self):
        if self._resources_freed:
            return
        self.reset_scroll()
        if self._scroll_scratch is not None:
            self.free_buffer(self._scroll_scratch)
            self._scroll_scratch = None
        self._resources_freed = True


class ST7796DisplayController(ModernDisplayController):
    """Modern controller that restores neutral scanout before LVGL resumes."""

    def __init__(self, bus, panel, lv_display, lvgl, task_handler,
                 input_device, width, height, offset_x, offset_y,
                 transfer_rows, allocation_flags, buffer_allocator,
                 buffer_free, scroll_config, native_height, panel_rotation):
        super().__init__(
            bus, panel, lv_display, lvgl, task_handler, input_device,
            width=width, height=height, offset_x=offset_x, offset_y=offset_y,
            allocation_flags=allocation_flags,
            buffer_allocator=buffer_allocator, buffer_free=buffer_free)
        self.surface = ST7796DirectRGB565Surface(
            self, bus, panel, width, height, offset_x, offset_y,
            transfer_rows, allocation_flags, buffer_allocator, buffer_free,
            scroll_config, native_height, panel_rotation)

    def acquire_ui(self, timeout_ms=1000):
        if self._owner == GAME_OWNER:
            self.wait_for_transfer(timeout_ms)
            self.surface.reset_scroll()
        return ModernDisplayController.acquire_ui(self, timeout_ms)


class Platform(ModernPlatform):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capabilities["panel_scroll"] = bool(
            self.game_surface.scroll_capabilities()["axes"])

    def deinit(self):
        if self._deinitialized:
            return
        self.game_surface.free_resources()
        super().deinit()


def create_controller(board, bus, panel, lv_display, lvgl, handler, pointer,
                      flags, lcd_bus):
    display = board["display"]
    width, height = display["logical_size"]
    offset_x, offset_y = display.get("offset", (0, 0))
    return ST7796DisplayController(
        bus, panel, lv_display, lvgl, handler, pointer,
        width, height, offset_x, offset_y, display["transfer_rows"], flags,
        lcd_bus.allocate_buffer, lcd_bus.free_buffer,
        display.get("scroll", {}), display["native_size"][1],
        display["rotation"])
