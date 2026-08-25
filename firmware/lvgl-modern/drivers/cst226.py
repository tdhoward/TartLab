"""CST226 pointer driver for TartLab's pinned LVGL MicroPython firmware."""

# SPDX-License-Identifier: GPL-3.0-or-later
#
# The CST226 protocol handling is adapted from TartLab's physically exercised
# legacy driver. The PointerDriver integration follows the public driver
# framework in the pinned lvgl_micropython reference.

from micropython import const  # NOQA
import machine  # NOQA
import pointer_framework
import time


I2C_ADDR = const(0x5A)
BITS = const(8)

_CHIP_ID = const(0x00A8)
_CHIP_ID_COMMAND = const(0xD204)
_STATUS_REGISTER = const(0x00)
_STATUS_BYTES = const(28)
_NO_TOUCH = const(0xAB)
_BUTTON_EVENT = const(0x80)
_MAX_TOUCHES = const(5)

_DISABLE_AUTOSLEEP_REGISTER = const(0xFE)
_IRQ_CONTROL_REGISTER = const(0xFA)
_MOTION_MASK_REGISTER = const(0xEC)


class CST226(pointer_framework.PointerDriver):
    """Expose the first CST226 contact as an LVGL pointer device."""

    def __init__(
        self,
        device,
        reset_pin=None,
        interrupt_pin=None,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,  # NOQA
        debug=False,
    ):
        self._device = device
        self._tx_buf = bytearray(3)
        self._tx_mv = memoryview(self._tx_buf)
        self._rx_buf = bytearray(_STATUS_BYTES)
        self._rx_mv = memoryview(self._rx_buf)

        if isinstance(reset_pin, int):
            reset_pin = machine.Pin(reset_pin, machine.Pin.OUT)
        if isinstance(interrupt_pin, int):
            interrupt_pin = machine.Pin(
                interrupt_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self._reset_pin = reset_pin
        self._interrupt_pin = interrupt_pin

        self.hw_reset()
        self._check_identity()
        self._write_reg(_DISABLE_AUTOSLEEP_REGISTER, 0x01)
        self._write_reg(_IRQ_CONTROL_REGISTER, 0x00)
        self._write_reg(_MOTION_MASK_REGISTER, 0x00)

        super().__init__(
            touch_cal=touch_cal,
            startup_rotation=startup_rotation,
            debug=debug,
        )

    def _check_identity(self):
        self._tx_buf[0] = _CHIP_ID_COMMAND >> 8
        self._tx_buf[1] = _CHIP_ID_COMMAND & 0xFF
        self._device.write_readinto(self._tx_mv[:2], self._rx_mv[:4])
        chip_id = (self._rx_buf[3] << 8) | self._rx_buf[2]
        if chip_id != _CHIP_ID:
            raise RuntimeError(
                "CST226 not detected: expected 0x{:04X}, got 0x{:04X}".format(
                    _CHIP_ID, chip_id))

    def _write_reg(self, register, value):
        self._tx_buf[0] = register
        self._tx_buf[1] = value
        self._device.write(self._tx_mv[:2])

    def hw_reset(self):
        if self._reset_pin is None:
            self._write_reg(0xD1, 0x0E)
            time.sleep_ms(20)  # NOQA
            return
        self._reset_pin(0)
        time.sleep_ms(1)  # NOQA
        self._reset_pin(1)
        time.sleep_ms(50)  # NOQA

    def _get_coords(self):
        self._tx_buf[0] = _STATUS_REGISTER
        self._device.write_readinto(
            self._tx_mv[:1], self._rx_mv[:_STATUS_BYTES])

        if self._rx_buf[0] == _NO_TOUCH or self._rx_buf[5] == _BUTTON_EVENT:
            return None

        touch_count = self._rx_buf[5] & 0x7F
        if touch_count == 0 or touch_count > _MAX_TOUCHES:
            self._write_reg(_STATUS_REGISTER, _NO_TOUCH)
            return None

        x = (self._rx_buf[1] << 4) | (self._rx_buf[3] >> 4)
        y = (self._rx_buf[2] << 4) | (self._rx_buf[3] & 0x0F)
        return self.PRESSED, x, y
