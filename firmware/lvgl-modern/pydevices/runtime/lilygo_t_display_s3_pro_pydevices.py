"""PyDevices comparison platform for the LilyGO T-Display-S3 Pro.

This module keeps the rejected comparison stack's board wiring separate from
its reusable rendering and ownership adapter.
"""

from pydevices_modern import (
    PyDevicesDisplayController,
    PyDevicesModernPlatform,
)


def _lvgl_input_devices(lvgl):
    """Enumerate inputs through LVGL's public linked-list API when available."""
    get_next = getattr(lvgl, "indev_get_next", None)
    if get_next is None:
        return ()
    devices = []
    device = get_next(None)
    while device is not None:
        devices.append(device)
        device = get_next(device)
    return devices


def create_t_display_s3_pro_platform():
    """Construct the pinned PyDevices/displayif T-Display-S3 Pro profile."""
    import appdev
    from cst226 import CST226
    import lvgl as lv
    from machine import I2C, Pin
    from spibus import SPIBus
    from st7796 import ST7796
    import sys

    bus = SPIBus(
        id=1,
        baudrate=60_000_000,
        sck=18,
        mosi=17,
        miso=8,
        command=9,
        chip_select=39,
    )
    display = ST7796(
        bus,
        width=222,
        height=480,
        colstart=49,
        rowstart=0,
        rotation=270,
        mirrored=False,
        color_depth=16,
        bgr=True,
        reverse_bytes_in_word=True,
        invert=True,
        brightness=1.0,
        backlight_pin=48,
        backlight_on_high=True,
        reset_pin=47,
        reset_high=False,
    )
    i2c = I2C(0, sda=Pin(5), scl=Pin(6), freq=100_000)
    touch = CST226(i2c, irq_pin=21, rst_pin=13)
    app = appdev.App(
        displays=[display],
        touch_read=touch.get_point,
        touch_rotation_table=(0, 5, 6, 3),
    )

    # Import after constructing App: this is display_driver's documented path
    # for binding a public displaydev driver without a flat board_config module.
    # Re-execute it after a same-runtime teardown so its documented import-time
    # binding observes the new current App instead of a prior deinitialized one.
    sys.modules.pop("display_driver", None)
    import display_driver
    event_loop = display_driver.event_loop.current_instance()
    if event_loop is None:
        raise RuntimeError("PyDevices LVGL event loop was not created")
    lv_display = lv.display_get_default()
    controller = PyDevicesDisplayController(
        app, display, lv_display, lv, event_loop, _lvgl_input_devices(lv)
    )
    return PyDevicesModernPlatform(
        controller, display, touch, app, ide_button_pin=12, lvgl=lv
    )
