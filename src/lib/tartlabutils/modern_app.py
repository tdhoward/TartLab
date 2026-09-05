"""Direct-drawing helpers for TartLab's modern student applications.

Use :class:`DirectCanvas` for framebuffer primitives and explicit refreshes,
or :func:`game_surface` when an image is already packed as RGB565_BE.  Both
target the public exclusive surface without exposing the native display bus.
"""

import time
from array import array

from .platform import get_platform

from framebuf import FrameBuffer, MONO_HLSB, RGB565

try:
    import lvgl as _lv
except ImportError:
    _lv = None

try:
    from ._modern_emitters import swap565 as _swap565_viper
except ImportError:
    _swap565_viper = None

try:
    from ._modern_emitters import copy_rgb565_rows as _copy_rows_viper
except ImportError:
    _copy_rows_viper = None


TRANSFER_ROWS = 16
_TEXT_CHUNK_CHARS = 24


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


def _trunc_division(numerator, denominator):
    """Return integer division truncated toward zero, as C does."""
    quotient = abs(numerator) // abs(denominator)
    if (numerator < 0) != (denominator < 0):
        return -quotient
    return quotient


def framebuffer_color(color):
    """Convert native RGB565 to the direct framebuffer's stored byte order."""
    return ((color & 0xFF) << 8) | ((color >> 8) & 0xFF)


def rgb565(red, green, blue):
    """Create a direct-framebuffer color from 8-bit RGB components."""
    native = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return framebuffer_color(native)


def _swap565_python(view):
    """Reference byte-swap implementation for hosts without Viper."""
    for offset in range(0, len(view), 2):
        view[offset], view[offset + 1] = view[offset + 1], view[offset]


def swap565_buffer(buffer):
    """Swap every RGB565 byte pair in a writable buffer, in place."""
    view = memoryview(buffer)
    size = len(view)
    if size & 1:
        raise ValueError("an RGB565 buffer must contain an even byte count")
    if size:
        # Viper pointer writes are unchecked. Validate writability in ordinary
        # Python before entering the optimized helper.
        view[0] = view[0]
    if _swap565_viper is None:
        _swap565_python(view)
    else:
        _swap565_viper(view, size)
    return buffer


def game_surface():
    """Acquire exclusive modern display ownership and return its surface."""
    platform = get_platform()
    surface = platform.enter_game_mode()
    if getattr(surface, "color_format", None) != "RGB565_BE":
        raise RuntimeError("modern examples require an RGB565_BE game surface")
    return surface


def fill_surface(surface, color):
    """Fill a direct surface with a standard 16-bit RGB565 color."""
    rows = min(TRANSFER_ROWS, surface.height)
    buffer = surface.allocate_buffer(surface.width, rows)
    try:
        view = memoryview(buffer)
        tile = FrameBuffer(buffer, surface.width, rows, RGB565)
        tile.fill(framebuffer_color(color))
        y = 0
        while y < surface.height:
            height = min(rows, surface.height - y)
            size = surface.width * height * 2
            surface.write(view[:size], 0, y, surface.width, height)
            y += height
    finally:
        surface.free_buffer(buffer)


class _PreparedSprite:
    """An RGB565 framebuffer prepared for a canvas's native orientation."""

    def __init__(self, framebuffer, width, height):
        self.framebuffer = framebuffer
        self.width = width
        self.height = height


def _buffer_view(value):
    """Return a byte view for a buffer or a FrameBuffer wrapping one."""
    try:
        return memoryview(value)
    except TypeError:
        return memoryview(value.buffer)


def _rotate_rgb565(source, target, width, height, rotation,
                   source_stride=None, target_stride=None):
    """Rotate an RGB565 buffer counter-clockwise by quarter turns."""
    if _lv is None:
        return False
    is_initialized = getattr(_lv, "is_initialized", None)
    if is_initialized is not None and not is_initialized():
        return False
    try:
        # Rotation does not inspect the two bytes within a pixel.  The pinned
        # binding's software rotator accepts RGB565, but not its byte-swapped
        # alias, so the stored framebuffer byte order remains unchanged.
        target_width = height if rotation & 1 else width
        _lv.draw_sw_rotate(
            source, target, width, height,
            width * 2 if source_stride is None else source_stride,
            target_width * 2 if target_stride is None else target_stride,
            rotation,
            _lv.COLOR_FORMAT.RGB565)
        return True
    except Exception:
        return False


class _RotatedTextWorkspace:
    """Bounded scratch buffers for compiled rotation of framebuf text."""

    def __init__(self):
        self.width = _TEXT_CHUNK_CHARS * 8
        size = self.width * 8 * 2
        self.source_data = bytearray(size)
        self.rotated_data = bytearray(size)
        self.source = FrameBuffer(self.source_data, self.width, 8, RGB565)

    def render(self, value, color, rotation):
        width = len(value) * 8
        transparent = 0 if (color & 0xFFFF) != 0 else 0xFFFF
        self.source.fill(transparent)
        self.source.text(value, 0, 0, color)
        if not _rotate_rgb565(
                self.source_data, self.rotated_data, width, 8,
                rotation, self.width * 2):
            return None, None
        target_width = 8 if rotation & 1 else width
        target_height = width if rotation & 1 else 8
        return FrameBuffer(
            self.rotated_data, target_width, target_height, RGB565), \
            transparent


class DirectCanvas(FrameBuffer):
    """A rotation-aware framebuffer flushed through a display surface.

    ``rotation`` accepts degrees (0, 90, 180, or 270) or the equivalent
    number of quarter turns (0 through 3). Positive rotation describes the
    clockwise rotation of the physical display from its native position. For
    example, at 90 degrees logical ``(x, y)`` maps to surface
    ``(y, surface.height - 1 - x)``. This is the orientation historically
    exposed by :class:`PortraitCanvas` on a landscape surface.
    """

    _ROTATIONS = {0: 0, 1: 1, 2: 2, 3: 3,
                  90: 1, 180: 2, 270: 3}

    def __init__(self, surface=None, transfer_rows=TRANSFER_ROWS, rotation=0):
        try:
            self._quarter_turns = self._ROTATIONS[rotation]
        except (KeyError, TypeError):
            raise ValueError(
                "rotation must be 0, 90, 180, or 270 degrees "
                "(or 0 through 3 quarter turns)")
        self.rotation = self._quarter_turns * 90
        self.surface = surface or game_surface()
        width = self.surface.width
        height = self.surface.height
        self._width = width
        self._height = height
        self.buffer = bytearray(width * height * 2)
        self._buffer_view = memoryview(self.buffer)
        self._transfer_rows = min(max(1, transfer_rows), height)
        self._transfer = self.surface.allocate_buffer(
            width, self._transfer_rows)
        self._transfer_view = memoryview(self._transfer)
        self._closed = False
        self._source_draw_buffer = None
        self._transfer_draw_buffer = None
        self._source_area = None
        self._transfer_area = None
        self._draw_buffer_format = None
        self._init_draw_buffer_copy()
        super().__init__(self.buffer, width, height, RGB565)
        if self._quarter_turns & 1:
            self.width = height
            self.height = width
        else:
            self.width = width
            self.height = height
        self._text_workspace = None
        self._compiled_text = self._quarter_turns != 0
        # Retain this private spelling during the PortraitCanvas transition.
        self._canvas = self
        if self._quarter_turns == 0:
            # Avoid adding Python dispatch to the native-orientation hot path.
            self.fill = super().fill
            self.pixel = super().pixel
            self.fill_rect = super().fill_rect
            self.rect = super().rect
            self.hline = super().hline
            self.vline = super().vline
            self.line = super().line
            self.ellipse = super().ellipse
            self.poly = super().poly
            self.scroll = super().scroll
            self.text = super().text

    def _init_draw_buffer_copy(self):
        """Wrap the owned buffers for compiled, strided LVGL copies."""
        if _lv is None:
            return
        is_initialized = getattr(_lv, "is_initialized", None)
        if is_initialized is not None and not is_initialized():
            return
        try:
            color_format = _lv.COLOR_FORMAT.RGB565_SWAPPED
            source = _lv.draw_buf_t()
            target = _lv.draw_buf_t()
            if not source.init(
                    self._width, self._height, color_format,
                    self._width * 2, self.buffer, len(self.buffer)):
                return
            if not target.init(
                    self._width, self._transfer_rows, color_format,
                    self._width * 2, self._transfer,
                    len(self._transfer_view)):
                return
            self._source_draw_buffer = source
            self._transfer_draw_buffer = target
            self._source_area = _lv.area_t()
            self._transfer_area = _lv.area_t()
            self._draw_buffer_format = color_format
        except Exception:
            self._disable_draw_buffer_copy()

    def _disable_draw_buffer_copy(self):
        self._source_draw_buffer = None
        self._transfer_draw_buffer = None
        self._source_area = None
        self._transfer_area = None
        self._draw_buffer_format = None

    def prepare_sprite(self, framebuffer, width, height):
        """Prepare an RGB565 framebuffer for repeated logical drawing."""
        if width <= 0 or height <= 0:
            raise ValueError("sprite width and height must be positive")
        rotation = self._quarter_turns
        if rotation == 0:
            return _PreparedSprite(framebuffer, width, height)

        target_width = height if rotation & 1 else width
        target_height = width if rotation & 1 else height
        buffer = bytearray(width * height * 2)
        rotated = FrameBuffer(buffer, target_width, target_height, RGB565)
        try:
            source = _buffer_view(framebuffer)
        except (AttributeError, TypeError):
            source = None
        if (source is not None and len(source) == len(buffer) and
                _rotate_rgb565(source, buffer, width, height, rotation)):
            return _PreparedSprite(rotated, width, height)

        for source_y in range(height):
            for source_x in range(width):
                target_x, target_y = self._sprite_point(
                    source_x, source_y, width, height)
                rotated.pixel(
                    target_x, target_y,
                    framebuffer.pixel(source_x, source_y))
        return _PreparedSprite(rotated, width, height)

    def draw_sprite(self, sprite, x, y):
        """Copy a prepared opaque sprite using logical coordinates."""
        if self._quarter_turns == 0:
            return super().blit(sprite.framebuffer, x, y)
        target_x, target_y, unused_width, unused_height = self._area(
            x, y, sprite.width, sprite.height)
        return super().blit(sprite.framebuffer, target_x, target_y)

    def _point(self, x, y):
        rotation = self._quarter_turns
        if rotation == 0:
            return x, y
        if rotation == 1:
            return y, self._height - 1 - x
        if rotation == 2:
            return self._width - 1 - x, self._height - 1 - y
        return self._width - 1 - y, x

    def _sprite_point(self, x, y, width, height):
        rotation = self._quarter_turns
        if rotation == 1:
            return y, width - 1 - x
        if rotation == 2:
            return width - 1 - x, height - 1 - y
        return height - 1 - y, x

    def _area(self, x, y, width, height):
        rotation = self._quarter_turns
        if rotation == 0:
            return x, y, width, height
        if rotation == 1:
            return y, self._height - x - width, height, width
        if rotation == 2:
            return (self._width - x - width,
                    self._height - y - height, width, height)
        return self._width - y - height, x, height, width

    def fill(self, color):
        return super().fill(color)

    def pixel(self, x, y, color=None):
        target_x, target_y = self._point(x, y)
        if color is None:
            return super().pixel(target_x, target_y)
        return super().pixel(target_x, target_y, color)

    def fill_rect(self, x, y, width, height, color):
        x, y, width, height = self._area(x, y, width, height)
        return super().fill_rect(x, y, width, height, color)

    def rect(self, x, y, width, height, color, fill=False):
        x, y, width, height = self._area(x, y, width, height)
        return super().rect(x, y, width, height, color, fill)

    def hline(self, x, y, width, color):
        rotation = self._quarter_turns
        if rotation == 0:
            return super().hline(x, y, width, color)
        if rotation == 1:
            return super().vline(
                y, self._height - x - width, width, color)
        if rotation == 2:
            return super().hline(
                self._width - x - width,
                self._height - 1 - y, width, color)
        return super().vline(
            self._width - 1 - y, x, width, color)

    def vline(self, x, y, height, color):
        rotation = self._quarter_turns
        if rotation == 0:
            return super().vline(x, y, height, color)
        if rotation == 1:
            return super().hline(
                y, self._height - 1 - x, height, color)
        if rotation == 2:
            return super().vline(
                self._width - 1 - x,
                self._height - y - height, height, color)
        return super().hline(
            self._width - y - height, x, height, color)

    def line(self, x1, y1, x2, y2, color):
        x1, y1 = self._point(x1, y1)
        x2, y2 = self._point(x2, y2)
        return super().line(x1, y1, x2, y2, color)

    def ellipse(self, x, y, x_radius, y_radius, color,
                fill=False, mask=0xF):
        """Draw an ellipse in logical coordinates."""
        x, y = self._point(x, y)
        rotation = self._quarter_turns
        if rotation & 1:
            x_radius, y_radius = y_radius, x_radius
        mask &= 0xF
        mask = ((mask << rotation) |
                (mask >> (4 - rotation))) & 0xF
        return super().ellipse(
            x, y, x_radius, y_radius, color, fill, mask)

    def poly(self, x, y, coordinates, color, fill=False):
        """Draw a polygon whose origin and vertices are logical."""
        # framebuf ignores a trailing unmatched coordinate and treats fewer
        # than one complete point as a no-op.
        length = len(coordinates) & ~1
        if not length:
            return
        if fill:
            return self._fill_poly(x, y, coordinates, length, color)
        rotation = self._quarter_turns
        transformed = []
        for index in range(0, length, 2):
            point_x = coordinates[index]
            point_y = coordinates[index + 1]
            if rotation == 1:
                point_x, point_y = point_y, -point_x
            elif rotation == 2:
                point_x, point_y = -point_x, -point_y
            else:
                point_x, point_y = -point_y, point_x
            transformed.append(point_x)
            transformed.append(point_y)
        x, y = self._point(x, y)
        return super().poly(
            x, y, array("i", transformed), color, False)

    def _fill_poly(self, x, y, coordinates, length, color):
        """Match framebuf's scanline fill while drawing logical spans."""
        y_min = coordinates[1]
        y_max = y_min
        for index in range(3, length, 2):
            point_y = coordinates[index]
            y_min = min(y_min, point_y)
            y_max = max(y_max, point_y)

        for row in range(y_min, y_max + 1):
            nodes = []
            point_x_1 = coordinates[0]
            point_y_1 = coordinates[1]
            index = length - 1
            while index >= 0:
                point_y_2 = coordinates[index]
                point_x_2 = coordinates[index - 1]
                index -= 2
                if (point_y_1 != point_y_2 and
                        ((point_y_1 > row and point_y_2 <= row) or
                         (point_y_1 <= row and point_y_2 > row))):
                    crossing = _trunc_division(
                        32 * (point_x_2 - point_x_1) *
                        (row - point_y_1),
                        point_y_2 - point_y_1)
                    nodes.append(_trunc_division(
                        32 * point_x_1 + crossing + 16, 32))
                elif row == max(point_y_1, point_y_2):
                    if point_y_1 < point_y_2:
                        self.pixel(
                            x + point_x_2, y + point_y_2, color)
                    elif point_y_2 < point_y_1:
                        self.pixel(
                            x + point_x_1, y + point_y_1, color)
                    else:
                        self.line(
                            x + point_x_1, y + point_y_1,
                            x + point_x_2, y + point_y_2, color)
                point_x_1 = point_x_2
                point_y_1 = point_y_2

            nodes.sort()
            for index in range(0, len(nodes), 2):
                self.hline(
                    x + nodes[index], y + row,
                    nodes[index + 1] - nodes[index] + 1, color)

    def scroll(self, x_step, y_step):
        """Move pixels in RAM by a logical vector; presentation is deferred."""
        rotation = self._quarter_turns
        if rotation == 1:
            x_step, y_step = y_step, -x_step
        elif rotation == 2:
            x_step, y_step = -x_step, -y_step
        else:
            x_step, y_step = -y_step, x_step
        return super().scroll(x_step, y_step)

    def _scroll_physical_region(self, x, y, width, height, dx, dy):
        """Move one clipped physical rectangle in overlap-safe row order."""
        if (x == 0 and y == 0 and
                width == self._width and height == self._height):
            return super().scroll(dx, dy)
        retained_width = width - abs(dx)
        retained_height = height - abs(dy)
        if retained_width <= 0 or retained_height <= 0:
            return
        source_x = x + max(-dx, 0)
        source_y = y + max(-dy, 0)
        target_x = x + max(dx, 0)
        target_y = y + max(dy, 0)
        row_bytes = retained_width * 2
        stride = self._width * 2
        source_start = source_y * stride + source_x * 2
        target_start = target_y * stride + target_x * 2

        # The region above was clipped to the owned framebuffer, but keep the
        # pointer kernel's safety contract explicit in ordinary Python. Viper
        # pointer reads and writes do not perform their own bounds checks.
        final_source = source_start + (retained_height - 1) * stride
        final_target = target_start + (retained_height - 1) * stride
        buffer_size = len(self._buffer_view)
        if (source_start < 0 or target_start < 0 or
                final_source + row_bytes > buffer_size or
                final_target + row_bytes > buffer_size):
            raise ValueError("scroll region exceeds the framebuffer")

        if _copy_rows_viper is not None:
            _copy_rows_viper(
                self._buffer_view, source_start, target_start,
                row_bytes, retained_height, stride, int(dy > 0))
            return

        scratch = bytearray(row_bytes)
        scratch_view = memoryview(scratch)
        rows = range(retained_height - 1, -1, -1) if dy > 0 else \
            range(retained_height)
        for row in rows:
            source_row = source_start + row * stride
            target_row = target_start + row * stride
            scratch_view[:] = self._buffer_view[
                source_row:source_row + row_bytes]
            self._buffer_view[target_row:target_row + row_bytes] = \
                scratch_view

    @staticmethod
    def _exposed_regions(x, y, width, height, dx, dy):
        regions = []
        vertical = min(abs(dy), height)
        horizontal = min(abs(dx), width)
        if dy > 0:
            regions.append((x, y, width, vertical))
            middle_y = y + vertical
        else:
            middle_y = y
            if dy < 0:
                regions.append(
                    (x, y + height - vertical, width, vertical))
        middle_height = height - vertical
        if middle_height > 0 and dx > 0:
            regions.append((x, middle_y, horizontal, middle_height))
        elif middle_height > 0 and dx < 0:
            regions.append((
                x + width - horizontal, middle_y,
                horizontal, middle_height))
        return regions

    def scroll_capabilities(self):
        """Describe panel scrolling in final logical canvas coordinates."""
        capabilities = getattr(self.surface, "scroll_capabilities", None)
        if capabilities is None:
            return {
                "axes": (),
                "fixed_areas": False,
                "wraps": False,
                "full_orthogonal_axis": False,
            }
        return capabilities(self.rotation)

    def scroll_region(self, area, dx=0, dy=0, fill=0, exposed=None):
        """Move, fill, and present a logical region.

        ``exposed`` may be an opaque sprite returned by ``prepare_sprite()``
        whose logical dimensions exactly match the single newly exposed band.
        It replaces the solid ``fill`` and is composed before presentation.
        A capable surface may change its scanout origin and upload only the
        newly exposed bands. Unsupported cases perform the same RAM operation
        and flush the complete changed region.
        """
        if self._closed:
            raise RuntimeError("canvas is closed")
        dx = int(dx)
        dy = int(dy)
        if not dx and not dy:
            return
        x, y, width, height = self._clip_area(
            area, self.width, self.height)
        if width <= 0 or height <= 0:
            return

        exposed_regions = self._exposed_regions(
            x, y, width, height, dx, dy)
        if abs(dx) >= width or abs(dy) >= height:
            exposed_regions = [(x, y, width, height)]
        if exposed is not None:
            if not isinstance(exposed, _PreparedSprite):
                raise TypeError(
                    "exposed must be returned by prepare_sprite()")
            if len(exposed_regions) != 1:
                raise ValueError(
                    "an exposed sprite requires one exposed region")
            replacement_area = exposed_regions[0]
            if (exposed.width != replacement_area[2] or
                    exposed.height != replacement_area[3]):
                raise ValueError(
                    "exposed sprite dimensions must match the exposed region")

        physical_x, physical_y, physical_width, physical_height = self._area(
            x, y, width, height)
        physical_dx, physical_dy = dx, dy
        rotation = self._quarter_turns
        if rotation == 1:
            physical_dx, physical_dy = dy, -dx
        elif rotation == 2:
            physical_dx, physical_dy = -dx, -dy
        elif rotation == 3:
            physical_dx, physical_dy = -dy, dx
        self._scroll_physical_region(
            physical_x, physical_y, physical_width, physical_height,
            physical_dx, physical_dy)

        if exposed is not None:
            self.draw_sprite(
                exposed, replacement_area[0], replacement_area[1])
        else:
            for exposed_area in exposed_regions:
                self.fill_rect(
                    exposed_area[0], exposed_area[1],
                    exposed_area[2], exposed_area[3], fill)

        presenter = getattr(self.surface, "present_scroll", None)
        accelerated = False
        if presenter is not None and len(exposed_regions) == 1 and \
                abs(dx) < width and abs(dy) < height:
            try:
                accelerated = presenter(
                    (x, y, width, height), dx, dy, self.rotation)
            except Exception:
                self.show((x, y, width, height))
                raise
        if accelerated:
            self.show(exposed_regions[0])
        else:
            self.show((x, y, width, height))

    def text(self, value, x, y, color):
        """Draw the built-in 8-pixel font in logical orientation."""
        if not value:
            return
        if self._quarter_turns == 0:
            return super().text(value, x, y, color)
        if self._compiled_text and self._text_with_compiled_rotation(
                value, x, y, color):
            return
        self._text_with_python_rotation(value, x, y, color)

    def _text_with_compiled_rotation(self, value, x, y, color):
        """Render and rotate visible text chunks using compiled operations."""
        if y <= -8 or y >= self.height:
            return True
        first = max(0, (-x) // 8)
        stop = min(len(value), (self.width - x + 7) // 8)
        if stop <= first:
            return True
        if self._text_workspace is None:
            try:
                self._text_workspace = _RotatedTextWorkspace()
            except Exception:
                self._compiled_text = False
                return False

        index = first
        while index < stop:
            end = min(index + _TEXT_CHUNK_CHARS, stop)
            chunk = value[index:end]
            sprite, transparent = self._text_workspace.render(
                chunk, color, self._quarter_turns)
            if sprite is None:
                self._compiled_text = False
                self._text_workspace = None
                return False
            chunk_x = x + index * 8
            target_x, target_y, unused_width, unused_height = self._area(
                chunk_x, y, len(chunk) * 8, 8)
            super().blit(sprite, target_x, target_y, transparent)
            index = end
        return True

    def _text_with_python_rotation(self, value, x, y, color):
        """Reference fallback for bindings without software rotation."""
        width = len(value) * 8
        mask = bytearray(((width + 7) // 8) * 8)
        glyphs = FrameBuffer(mask, width, 8, MONO_HLSB)
        glyphs.text(value, 0, 0, 1)
        for glyph_y in range(8):
            for glyph_x in range(width):
                if glyphs.pixel(glyph_x, glyph_y):
                    self.pixel(x + glyph_x, y + glyph_y, color)

    @staticmethod
    def _area_values(area, width, height):
        if area is None:
            return 0, 0, width, height
        if hasattr(area, "x"):
            return area.x, area.y, area.w, area.h
        return area

    @staticmethod
    def _clip_area(area, canvas_width, canvas_height):
        x, y, width, height = DirectCanvas._area_values(
            area, canvas_width, canvas_height)
        x = int(x)
        y = int(y)
        width = int(width)
        height = int(height)
        right = min(canvas_width, x + width)
        bottom = min(canvas_height, y + height)
        x = max(0, x)
        y = max(0, y)
        return x, y, right - x, bottom - y

    def _copy_with_lvgl(self, x, y, width, rows):
        target = self._transfer_draw_buffer
        if target is None:
            return False
        try:
            if target.reshape(
                    self._draw_buffer_format, width, rows, width * 2) is None:
                raise RuntimeError("LVGL could not reshape the transfer buffer")
            source_area = self._source_area
            source_area.x1 = x
            source_area.y1 = y
            source_area.x2 = x + width - 1
            source_area.y2 = y + rows - 1
            transfer_area = self._transfer_area
            transfer_area.x1 = 0
            transfer_area.y1 = 0
            transfer_area.x2 = width - 1
            transfer_area.y2 = rows - 1
            target.copy(
                transfer_area, self._source_draw_buffer, source_area)
            return True
        except Exception:
            self._disable_draw_buffer_copy()
            return False

    def _copy_with_python(self, x, y, width, rows):
        row_bytes = width * 2
        for row in range(rows):
            source_start = ((y + row) * self._width + x) * 2
            target_start = row * row_bytes
            self._transfer_view[target_start:target_start + row_bytes] = \
                self._buffer_view[source_start:source_start + row_bytes]

    def show(self, area=None):
        """Flush all or part of the logical framebuffer to the surface."""
        if self._closed:
            raise RuntimeError("canvas is closed")
        x, y, width, height = self._clip_area(
            area, self.width, self.height)
        if width <= 0 or height <= 0:
            return
        x, y, width, height = self._area(x, y, width, height)

        # Some surfaces preserve partial writes in a shadow framebuffer and
        # therefore need one complete image before accepting dirty regions.
        # Seed that shadow from the canvas's physical backing buffer. The
        # surface remains responsible for any controller-specific DMA tiling.
        if (getattr(self.surface, "requires_full_frame_seed", False) and
                not getattr(self.surface, "shadow_valid", False)):
            self.surface.write(
                self._buffer_view, 0, 0, self._width, self._height)
            return

        target = self._transfer_view
        row_bytes = width * 2
        rows_per_transfer = len(target) // row_bytes
        sent_rows = 0
        while sent_rows < height:
            rows = min(rows_per_transfer, height - sent_rows)
            source_y = y + sent_rows
            if not self._copy_with_lvgl(x, source_y, width, rows):
                self._copy_with_python(x, source_y, width, rows)
            size = row_bytes * rows
            self.surface.write(
                target[:size], x, source_y, width, rows)
            sent_rows += rows

    def close(self):
        if not self._closed:
            self._text_workspace = None
            self._disable_draw_buffer_copy()
            try:
                reset_scroll = getattr(self.surface, "reset_scroll", None)
                if reset_scroll is not None:
                    reset_scroll()
            finally:
                try:
                    self.surface.free_buffer(self._transfer)
                finally:
                    self._closed = True


class PortraitCanvas(DirectCanvas):
    """Compatibility spelling for a portrait-oriented DirectCanvas."""

    def __init__(self, surface=None, transfer_rows=TRANSFER_ROWS):
        surface = surface or game_surface()
        rotation = 90 if surface.width > surface.height else 0
        super().__init__(surface, transfer_rows, rotation=rotation)
        self._rotated = rotation != 0


class TouchGrid:
    """Edge-triggered grid input for an exclusive direct-rendering app."""

    def __init__(self, keys, cols, rows, x=0, y=0,
                 width=None, height=None, rotation=0):
        self._platform = get_platform()
        if self._platform.input is None:
            raise RuntimeError("the modern platform has no touch input")
        try:
            self._quarter_turns = DirectCanvas._ROTATIONS[rotation]
        except (KeyError, TypeError):
            raise ValueError(
                "rotation must be 0, 90, 180, or 270 degrees "
                "(or 0 through 3 quarter turns)")
        self.rotation = self._quarter_turns * 90
        self._keys = keys
        self.cols = cols
        self.rows = rows
        self.x = x
        self.y = y
        if self._quarter_turns & 1:
            logical_width = self._platform.height
            logical_height = self._platform.width
        else:
            logical_width = self._platform.width
            logical_height = self._platform.height
        self.width = width if width is not None else logical_width
        self.height = height if height is not None else logical_height
        self._down = False
        self._last_keep_awake = None
        self._keep_awake()

    def _keep_awake(self):
        keep_awake = getattr(self._platform, "keep_touch_awake", None)
        if keep_awake is not None:
            keep_awake()
        self._last_keep_awake = _ticks_ms()

    def _logical_point(self, point):
        x, y = point
        rotation = self._quarter_turns
        if rotation == 0:
            return x, y
        if rotation == 1:
            return self._platform.height - 1 - y, x
        if rotation == 2:
            return (self._platform.width - 1 - x,
                    self._platform.height - 1 - y)
        return y, self._platform.width - 1 - x

    def read(self):
        now = _ticks_ms()
        if _ticks_diff(now, self._last_keep_awake) >= 5000:
            self._keep_awake()
        point = self._platform.read_game_touch()
        if point is None:
            self._down = False
            return None
        if self._down:
            return None
        self._down = True
        x, y = self._logical_point(point)
        if not (self.x <= x < self.x + self.width and
                self.y <= y < self.y + self.height):
            return None
        col = int((x - self.x) * self.cols / self.width)
        row = int((y - self.y) * self.rows / self.height)
        index = row * self.cols + col
        return self._keys[index] if index < len(self._keys) else None


class PortraitTouchGrid(TouchGrid):
    """Touch grid using the same portrait coordinates as PortraitCanvas."""

    def __init__(self, keys, cols, rows, x=0, y=0,
                 width=None, height=None):
        platform = get_platform()
        self._portrait_rotated = platform.width > platform.height
        rotation = 90 if self._portrait_rotated else 0
        super().__init__(
            keys, cols, rows, x, y,
            width, height, rotation=rotation)
