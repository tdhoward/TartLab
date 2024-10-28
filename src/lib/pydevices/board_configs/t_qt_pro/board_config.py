""" LILYGO T-QT Pro GC9107 128x128 display """

from spibus import SPIBus
from gc9a01 import GC9A01  # same as GC9107


display_bus = SPIBus(
    id=1,
    baudrate=60_000_000,
    sck=3,
    cs=5,
    mosi=2,
    dc=6,
)

display_drv = GC9A01(
    display_bus,
    width=128,
    height=128,
    colstart=0,
    rowstart=0,
    rotation=180,
    mirrored=False,
    color_depth=16,
    bgr=True,
    reverse_bytes_in_word=True,
    invert=True,
    brightness=1.0,
    backlight_pin=10,
    backlight_on_high=True,
    reset_pin=1,
    reset_high=True,
    power_pin=None,
    power_on_high=True,
)
