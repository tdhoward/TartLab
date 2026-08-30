"""Interactive raw-touch probe for the Elecrow DLE06235B.

Run after a clean MCU reset.  The probe keeps the working LVGL landscape smoke
active, polls the ST77922 TDDI registers, and prints only press, significant
motion, and release events so a human can exercise the center and four corners.
"""

import time

import i2c
import machine

import elecrow_dle06235b_smoke as smoke


_TOUCH_INFO = 0x0010
_FIRST_COORDINATE = 0x0014
_WITH_COORDINATES = 0x08
_VALID = 0x80
_NO_UPDATE = object()


i2c_bus = i2c.I2C.Bus(
    host=0,
    scl=39,
    sda=38,
    freq=100_000,
    use_locks=False,
)
touch_device = i2c.I2C.Device(bus=i2c_bus, dev_id=0x55, reg_bits=16)
interrupt = machine.Pin(47, machine.Pin.IN, machine.Pin.PULL_UP)

identity = touch_device.read_mem(0x0000, num_bytes=10)
firmware_version = identity[0]
status = identity[1]
max_x = (identity[5] << 8) | identity[6]
max_y = (identity[7] << 8) | identity[8]
max_touches = identity[9]

_info = bytearray(1)
_points = bytearray(max_touches * 7)


def _read_raw():
    touch_device.read_mem(_TOUCH_INFO, buf=_info)
    if not _info[0] & _WITH_COORDINATES:
        return _NO_UPDATE

    # The controller does not acknowledge the report until the host reads the
    # final record supported by Max Touches.  Read all records even though this
    # probe reports only the first active contact.
    touch_device.read_mem(_FIRST_COORDINATE, buf=_points)
    for offset in range(0, len(_points), 7):
        if not _points[offset] & _VALID:
            continue

        x = ((_points[offset] & 0x3F) << 8) | _points[offset + 1]
        y = ((_points[offset + 2] & 0x3F) << 8) | _points[offset + 3]
        return x, y
    return None


def _to_landscape(raw_x, raw_y):
    return max_y - raw_y - 1, raw_x


def run(duration_ms=60_000):
    print(
        "ST77922_TOUCH_PROBE_READY fw={} status=0x{:02X} geometry={}x{} "
        "contacts={} irq={}".format(
            firmware_version,
            status,
            max_x,
            max_y,
            max_touches,
            interrupt.value(),
        )
    )
    print("Tap center, then the four corners; drag once; finally release.")

    pressed = False
    last_x = -1000
    last_y = -1000
    deadline = time.ticks_add(time.ticks_ms(), duration_ms)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        point = _read_raw()
        if point is _NO_UPDATE:
            time.sleep_ms(15)
            continue
        if point is None:
            if pressed:
                print("RELEASE irq={}".format(interrupt.value()))
                pressed = False
            time.sleep_ms(15)
            continue

        raw_x, raw_y = point
        landscape_x, landscape_y = _to_landscape(raw_x, raw_y)
        if (
            not pressed
            or abs(raw_x - last_x) >= 12
            or abs(raw_y - last_y) >= 12
        ):
            print(
                "{} raw=({}, {}) landscape=({}, {}) irq={} info=0x{:02X}".format(
                    "PRESS" if not pressed else "MOVE ",
                    raw_x,
                    raw_y,
                    landscape_x,
                    landscape_y,
                    interrupt.value(),
                    _info[0],
                )
            )
            last_x = raw_x
            last_y = raw_y
        pressed = True
        time.sleep_ms(15)

    print("ST77922_TOUCH_PROBE_DONE")
