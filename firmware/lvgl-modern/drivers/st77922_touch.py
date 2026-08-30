"""LVGL pointer driver for the ST77922 integrated TDDI touch interface."""

from micropython import const
import pointer_framework


I2C_ADDR = const(0x55)
BITS = const(16)

_FIRMWARE_VERSION = const(0x0000)
_GEOMETRY = const(0x0005)
_TOUCH_INFO = const(0x0010)
_FIRST_COORDINATE = const(0x0014)
_WITH_COORDINATES = const(0x08)
_VALID = const(0x80)


class ST77922Touch(pointer_framework.PointerDriver):
    """Expose the first ST77922 contact as an LVGL pointer device."""

    def __init__(
        self,
        device,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,
        debug=False,
    ):
        self._device = device
        self._info = bytearray(1)
        self._geometry = bytearray(5)
        self.__x = 0
        self.__y = 0
        self.__touch_state = self.RELEASED

        version = self._device.read_mem(_FIRMWARE_VERSION, num_bytes=1)[0]
        self._device.read_mem(_GEOMETRY, buf=self._geometry)
        width = (self._geometry[0] << 8) | self._geometry[1]
        height = (self._geometry[2] << 8) | self._geometry[3]
        touches = self._geometry[4]
        if width <= 0 or height <= 0 or touches <= 0:
            raise RuntimeError("invalid ST77922 touch identity")
        # Reading through the final record is the controller's acknowledgement
        # handshake.  A first-contact-only seven-byte read leaves With Coord.
        # latched and prevents subsequent press/release reports.
        self._points = bytearray(touches * 7)
        print(
            "ST77922 touch: firmware={}, geometry={}x{}, contacts={}".format(
                version, width, height, touches
            )
        )

        super().__init__(
            touch_cal=touch_cal,
            startup_rotation=startup_rotation,
            debug=debug,
        )

    @property
    def hw_size(self):
        return (
            (self._geometry[0] << 8) | self._geometry[1],
            (self._geometry[2] << 8) | self._geometry[3],
        )

    def _get_coords(self):
        self._device.read_mem(_TOUCH_INFO, buf=self._info)
        if not self._info[0] & _WITH_COORDINATES:
            return self.__touch_state, self.__x, self.__y

        self._device.read_mem(_FIRST_COORDINATE, buf=self._points)
        point_offset = None
        for offset in range(0, len(self._points), 7):
            if self._points[offset] & _VALID:
                point_offset = offset
                break
        if point_offset is None:
            self.__touch_state = self.RELEASED
            return self.__touch_state, self.__x, self.__y

        self.__x = (
            ((self._points[point_offset] & 0x3F) << 8)
            | self._points[point_offset + 1]
        )
        self.__y = (
            ((self._points[point_offset + 2] & 0x3F) << 8)
            | self._points[point_offset + 3]
        )
        self.__touch_state = self.PRESSED
        return self.__touch_state, self.__x, self.__y
