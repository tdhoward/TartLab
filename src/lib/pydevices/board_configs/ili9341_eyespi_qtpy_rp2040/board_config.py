""" QT Py RP2040 with EyeSPI and ILI9341 2.8" display """

from spibus import SPIBus
from ili9341 import ILI9341
from machine import Pin, I2C
from ft6x36 import FT6x36
from eventsys.devices import Devices, Broker
import gc


gc.collect()

display_bus = SPIBus(
    id=0,
    baudrate=60_000_000,
    sck=6,
    mosi=3,
    miso=4, 
    dc=5,
    cs=20,
)

gc.collect()

display_drv = ILI9341(
    display_bus,
    width=240,
    height=320,
    colstart=0,
    rowstart=0,
    rotation=0,
    mirrored=False,
    color_depth=16,
    bgr=True,
    reverse_bytes_in_word=True,
    invert=False,
    brightness=1.0,
    backlight_pin=None,
    backlight_on_high=True,
    reset_pin=None,
    reset_high=True,
    power_pin=None,
    power_on_high=True,
)

gc.collect()

i2c = I2C(0, sda=Pin(24), scl=Pin(25), freq=100000)
touch_drv = FT6x36(i2c)
touch_read_func=touch_drv.get_positions
touch_rotation_table=(6, 3, 0, 5)

gc.collect()

broker = Broker()

touch_dev = broker.create_device(
    type=Devices.TOUCH,
    read=touch_read_func,
    data=display_drv,
    data2=touch_rotation_table,
)

gc.collect()
