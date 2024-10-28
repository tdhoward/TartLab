""" Waveshare RP2040-Touch-LCD-1.28 GC9A01 240x240 """

from spibus import SPIBus
from gc9a01 import GC9A01
from machine import Pin, I2C
from cst8xx import CST8XX
from eventsys.devices import Devices, Broker


display_bus = SPIBus(
    id=1,
    baudrate=60_000_000,
    sck=10,
    mosi=11,
    miso=12,
    dc=8,
    cs=9,
)

display_drv = GC9A01(
    display_bus,
    width=240,
    height=240,
    colstart=0,
    rowstart=0,
    rotation=0,
    mirrored=False,
    color_depth=16,
    bgr=True,
    reverse_bytes_in_word=True,
    invert=True,
    brightness=1.0,
    backlight_pin=25,
    backlight_on_high=True,
    reset_pin=13,
    reset_high=False,
    power_pin=None,
    power_on_high=True,
)

i2c = I2C(1, sda=Pin(6), scl=Pin(7), freq=100_000)
touch_drv = CST8XX(i2c, irq_pin=21, rst_pin=22)
touch_read_func = touch_drv.get_point
touch_rotation_table = (0, 5, 6, 3)

broker = Broker()

touch_dev = broker.create_device(
    type=Devices.TOUCH,
    read=touch_read_func,
    data=display_drv,
    data2=touch_rotation_table,
)
