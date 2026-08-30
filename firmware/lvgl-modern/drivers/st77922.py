"""Experimental ST77922 QSPI display driver for the Elecrow DLE06235B.

The command framing follows Espressif's ST77922 QSPI protocol: register
commands use opcode 0x02 and pixel writes use opcode 0x32, each packed into a
32-bit command/address phase.  The class is intentionally separate from the
qualified TartLab display driver while the new board is being evaluated.
"""

import gc

import display_driver_framework
import lcd_bus
import lvgl as lv
from micropython import const


STATE_HIGH = display_driver_framework.STATE_HIGH
STATE_LOW = display_driver_framework.STATE_LOW
STATE_PWM = display_driver_framework.STATE_PWM

BYTE_ORDER_RGB = display_driver_framework.BYTE_ORDER_RGB
BYTE_ORDER_BGR = display_driver_framework.BYTE_ORDER_BGR

_WRITE_CMD = const(0x02)
_WRITE_COLOR = const(0x32)

_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_MADCTL = const(0x36)


class ST77922(display_driver_framework.DisplayDriver):
    """ST77922 display using single-line commands and four-line pixel data."""

    # Unlike the more common ST77xx controllers, ST77922 MADCTL bit 5 is
    # reserved rather than MV (row/column exchange).  Keep the panel in its
    # native portrait scan order and rotate partial buffers in software.
    _ORIENTATION_TABLE = (0x00, 0x00, 0x00, 0x00)

    @staticmethod
    def _qspi_command(command):
        return (_WRITE_CMD << 24) | ((command & 0xFF) << 8)

    @staticmethod
    def _qspi_color_command(command):
        return (_WRITE_COLOR << 24) | ((command & 0xFF) << 8)

    def __init__(
        self,
        data_bus,
        display_width,
        display_height,
        frame_buffer1=None,
        frame_buffer2=None,
        reset_pin=None,
        reset_state=STATE_HIGH,
        power_pin=None,
        power_on_state=STATE_HIGH,
        backlight_pin=None,
        backlight_on_state=STATE_HIGH,
        offset_x=0,
        offset_y=0,
        color_byte_order=BYTE_ORDER_RGB,
        color_space=lv.COLOR_FORMAT.RGB565_SWAPPED,
        rgb565_byte_swap=False,
    ):
        if not isinstance(data_bus, lcd_bus.SPIBus):
            raise TypeError("ST77922 requires lcd_bus.SPIBus")
        if data_bus.get_lane_count() != 4:
            raise ValueError("ST77922 QSPI requires four data lanes")

        bytes_per_pixel = lv.color_format_get_size(color_space)
        if bytes_per_pixel not in (2, 3):
            raise ValueError("ST77922 supports RGB565 or RGB888")

        row_size = display_width * bytes_per_pixel
        buffer_size = row_size * 24
        if frame_buffer1 is None:
            gc.collect()
            flags = lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
            frame_buffer1 = data_bus.allocate_framebuffer(buffer_size, flags)
            frame_buffer2 = data_bus.allocate_framebuffer(buffer_size, flags)

        if frame_buffer1 is None or len(frame_buffer1) < row_size:
            raise MemoryError("unable to allocate an ST77922 render buffer")
        if len(frame_buffer1) % row_size:
            raise ValueError("ST77922 render buffer must contain whole rows")
        if frame_buffer2 is not None and len(frame_buffer2) != len(frame_buffer1):
            raise ValueError("ST77922 render buffers must be the same size")

        gc.collect()
        flags = lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
        rotation_buffer = lcd_bus.allocate_buffer(len(frame_buffer1), flags)
        if rotation_buffer is None:
            raise MemoryError("unable to allocate an ST77922 rotation buffer")

        self._qspi_ramwr = self._qspi_color_command(_RAMWR)
        self._qspi_caset = self._qspi_command(_CASET)
        self._qspi_raset = self._qspi_command(_RASET)
        self._native_width = display_width
        self._native_height = display_height
        self._rotation_buffer = rotation_buffer
        # lv_draw_sw_rotate does not recognize the byte-swapped RGB565 alias,
        # but rotation is byte-order agnostic and ordinary RGB565 has the same
        # two-byte pixel size.
        self._rotation_color_space = (
            lv.COLOR_FORMAT.RGB565 if bytes_per_pixel == 2 else color_space
        )

        super().__init__(
            data_bus,
            display_width,
            display_height,
            frame_buffer1,
            frame_buffer2,
            reset_pin,
            reset_state,
            power_pin,
            power_on_state,
            backlight_pin,
            backlight_on_state,
            offset_x,
            offset_y,
            color_byte_order,
            color_space,
            rgb565_byte_swap=rgb565_byte_swap,
            _cmd_bits=32,
            _param_bits=8,
            _init_bus=True,
        )

        # The pinned ESP32 QSPI completion callback path crashes before the
        # Python flush-ready callback runs.  Keep this experimental driver
        # blocking until that native path is fixed and independently tested.
        self._data_bus.register_callback(None)

        # ST77922 CASET requires both the physical start column and physical
        # window width to be multiples of four.  Round LVGL invalidations before
        # rendering so each flush buffer includes the extra edge pixels.
        self._disp_drv.add_event_cb(
            self._on_invalidate_area,
            lv.EVENT.INVALIDATE_AREA,
            None,
        )

    def set_params(self, command, params=None):
        self._data_bus.tx_param(self._qspi_command(command), params)

    def _on_invalidate_area(self, event):
        area = lv.area_t.__cast__(event.get_param())
        rotation = self._disp_drv.get_rotation()
        if rotation in (1, 3):
            # After transposition, logical Y is the physical column axis.
            area.y1 &= ~0x03
            area.y2 |= 0x03
            maximum = self._disp_drv.get_vertical_resolution() - 1
            if area.y2 > maximum:
                area.y2 = maximum
        else:
            area.x1 &= ~0x03
            area.x2 |= 0x03
            maximum = self._disp_drv.get_horizontal_resolution() - 1
            if area.x2 > maximum:
                area.x2 = maximum

    def _on_size_change(self, _):
        rotation = self._disp_drv.get_rotation()
        self._width = self._disp_drv.get_horizontal_resolution()
        self._height = self._disp_drv.get_vertical_resolution()
        if rotation == self._rotation:
            return
        self._rotation = rotation
        if self._initilized:
            self._param_buf[0] = self._madctl(
                self._color_byte_order, self._ORIENTATION_TABLE, ~rotation
            )
            self.set_params(_MADCTL, self._param_mv[:1])

    def _set_memory_location(self, x1, y1, x2, y2):
        params = self._param_buf
        params[0] = (x1 >> 8) & 0xFF
        params[1] = x1 & 0xFF
        params[2] = (x2 >> 8) & 0xFF
        params[3] = x2 & 0xFF
        self._data_bus.tx_param(self._qspi_caset, self._param_mv)

        params[0] = (y1 >> 8) & 0xFF
        params[1] = y1 & 0xFF
        params[2] = (y2 >> 8) & 0xFF
        params[3] = y2 & 0xFF
        self._data_bus.tx_param(self._qspi_raset, self._param_mv)
        return self._qspi_ramwr

    def _flush_cb(self, _, area, color_pointer):
        x1 = area.x1
        x2 = area.x2
        y1 = area.y1
        y2 = area.y2
        width = x2 - x1 + 1
        height = y2 - y1 + 1
        pixel_size = lv.color_format_get_size(self._color_space)
        # LVGL may align each row of a partial draw buffer beyond its visible
        # pixel width.  This matters for odd-width widget invalidations: using
        # width * pixel_size as the source stride makes every rotated row drift
        # into the preceding row's padding.
        source_stride = lv.draw_buf_width_to_stride(width, self._color_space)
        source_size = source_stride * height
        transfer_size = width * height * pixel_size
        data = color_pointer.__dereference__(source_size)

        rotation = self._rotation
        if rotation:
            rotated_data = self._rotation_buffer[:transfer_size]
            destination_width = height if rotation in (1, 3) else width
            lv.draw_sw_rotate(
                data,
                rotated_data,
                width,
                height,
                source_stride,
                destination_width * pixel_size,
                rotation,
                self._rotation_color_space,
            )
            data = rotated_data

            if rotation == 1:
                x1, x2, y1, y2 = (
                    y1,
                    y2,
                    self._native_height - x2 - 1,
                    self._native_height - x1 - 1,
                )
            elif rotation == 2:
                x1, x2, y1, y2 = (
                    self._native_width - x2 - 1,
                    self._native_width - x1 - 1,
                    self._native_height - y2 - 1,
                    self._native_height - y1 - 1,
                )
            else:
                x1, x2, y1, y2 = (
                    self._native_width - y2 - 1,
                    self._native_width - y1 - 1,
                    x1,
                    x2,
                )
        elif source_stride != width * pixel_size:
            # A portrait partial area can also have aligned source rows.  Pack
            # them before QSPI transfer so row padding is never interpreted as
            # panel pixels.
            packed_data = self._rotation_buffer[:transfer_size]
            lv.draw_sw_rotate(
                data,
                packed_data,
                width,
                height,
                source_stride,
                width * pixel_size,
                0,
                self._rotation_color_space,
            )
            data = packed_data

        x1 += self._offset_x
        x2 += self._offset_x
        y1 += self._offset_y
        y2 += self._offset_y
        command = self._set_memory_location(x1, y1, x2, y2)
        self._data_bus.tx_color(
            command,
            data,
            x1,
            y1,
            x2,
            y2,
            0,
            self._disp_drv.flush_is_last(),
        )
        self._disp_drv.flush_ready()
