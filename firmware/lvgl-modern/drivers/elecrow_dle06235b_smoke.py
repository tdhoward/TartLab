"""Interactive LVGL smoke for the Elecrow DLE06235B prototype driver."""

import machine
import lcd_bus
import lvgl as lv
import task_handler

from st77922 import STATE_LOW, ST77922


spi = machine.SPI.Bus(
    host=2,
    sck=12,
    quad_pins=(11, 13, 14, 9),
)
bus = lcd_bus.SPIBus(
    spi_bus=spi,
    dc=-1,
    freq=40_000_000,
    cs=10,
    quad=True,
)
display = ST77922(
    bus,
    display_width=320,
    display_height=480,
    reset_pin=48,
    reset_state=STATE_LOW,
    backlight_pin=41,
    color_space=lv.COLOR_FORMAT.RGB565_SWAPPED,
    rgb565_byte_swap=False,
)
display.reset()
display.init()
display.set_rotation(lv.DISPLAY_ROTATION._0)
display.set_backlight(100)

screen = lv.screen_active()
screen.set_style_bg_color(lv.color_hex(0x102040), lv.PART.MAIN)

title = lv.label(screen)
title.set_text("TartLab | Elecrow DLE06235B\nLVGL 9 / ST77922 | 320 x 480")
title.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
title.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
title.center()

handler = task_handler.TaskHandler()
print("ELECROW_LVGL_SMOKE_READY")
