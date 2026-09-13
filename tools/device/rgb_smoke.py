"""Standalone RGB/LVGL visual fixture; requires /hdwconfig.py and a hard reset.

Run board_probe.py first to sequence any touch reset expander. This fixture
does not qualify TartLab's shared display ownership or direct rendering.
"""

import gc
import json
import time
import lvgl as lv
import lcd_bus
import rgb_display
import i2c
import gt911
from hdwconfig import BOARD_CONFIG

pins = {p["type"]: p["number"] for p in BOARD_CONFIG["pins"]}
backlight = next(p for p in BOARD_CONFIG["pins"] if p["type"] == "BACKLIGHT")
config = BOARD_CONFIG["display"]
width, height = config["native_size"]
kwargs = dict(config["rgb"])
for index in range(16):
    kwargs["data" + str(index)] = pins["DISPLAY_DATA_" + str(index)]
for signal in ("hsync", "vsync", "de", "pclk"):
    kwargs[signal] = pins["DISPLAY_" + signal.upper()]
bus = lcd_bus.RGBBus(**kwargs)
buffer_bytes = width * config["transfer_rows"] * 2
buffer1 = bus.allocate_framebuffer(buffer_bytes, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
buffer2 = bus.allocate_framebuffer(buffer_bytes, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
display = rgb_display.RGBDisplay(data_bus=bus, display_width=width,
                                display_height=height, color_space=lv.COLOR_FORMAT.RGB565,
                                frame_buffer1=buffer1, frame_buffer2=buffer2,
                                backlight_pin=pins["BACKLIGHT"],
                                backlight_on_state=(rgb_display.STATE_HIGH if backlight["active_high"]
                                                    else rgb_display.STATE_LOW))
display.init()
display.set_backlight(100)
screen = lv.screen_active()
screen.set_style_bg_color(lv.color_hex(0), 0)
children = []
for index, color in enumerate((0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF, 0x808080, 0)):
    tile = lv.obj(screen)
    children.append(tile)
    tile.set_pos(index * width // 6, height // 3)
    tile.set_size(width // 6 + 1, height // 3)
    tile.set_style_bg_color(lv.color_hex(color), 0)
    tile.set_style_bg_opa(255, 0)
    tile.set_style_border_width(0, 0)
    tile.set_style_radius(0, 0)
for name, align in (("TOP LEFT", lv.ALIGN.TOP_LEFT), ("TOP RIGHT", lv.ALIGN.TOP_RIGHT),
                    ("BOTTOM LEFT", lv.ALIGN.BOTTOM_LEFT), ("BOTTOM RIGHT", lv.ALIGN.BOTTOM_RIGHT)):
    label = lv.label(screen)
    children.append(label)
    label.set_text(name)
    label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    label.align(align, 0, 0)
status = lv.label(screen)
children.append(status)
status.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
status.align(lv.ALIGN.TOP_MID, 0, 45)
# Straight edge markers make scanout wrap distinguishable from label layout.
for x, color in ((0, 0xFFFF00), (width - 2, 0x00FFFF)):
    edge = lv.obj(screen)
    children.append(edge)
    edge.set_pos(x, 0)
    edge.set_size(2, height)
    edge.set_style_bg_color(lv.color_hex(color), 0)
    edge.set_style_bg_opa(255, 0)
    edge.set_style_border_width(0, 0)
    edge.set_style_radius(0, 0)
touch_config = BOARD_CONFIG["touch"]
touch_bus = i2c.I2C.Bus(host=touch_config["i2c"]["host"], scl=pins["TOUCH_SCL"],
                       sda=pins["TOUCH_SDA"], freq=touch_config["i2c"]["frequency"])
addresses = touch_bus.scan()
touch_error = None
if addresses == list(range(0x08, 0x78)):
    # MicroPython scans this non-reserved address range. Every address ACKing
    # is a bus fault, not evidence that the selected input controller exists.
    touch_error = "All scanned I2C addresses acknowledge; touch probe invalid"
touch_address = None if touch_error else next(
    (address for address in touch_config["addresses"] if address in addresses), None)
touch = None
if touch_address is not None:
    touch = gt911.GT911(i2c.I2C.Device(touch_bus, dev_id=touch_address, reg_bits=gt911.BITS))
events = []


def touched(event):
    point = lv.point_t()
    lv.indev_active().get_point(point)
    events.append((point.x, point.y))
    status.set_text("TOUCH %d, %d" % (point.x, point.y))


screen.add_event_cb(touched, lv.EVENT.PRESSED, None)
for child in children:
    child.remove_flag(lv.obj.FLAG.CLICKABLE)
start = time.ticks_ms()
previous = start
frames = 0
while time.ticks_diff(time.ticks_ms(), start) < 45_000:
    now = time.ticks_ms()
    lv.tick_inc(time.ticks_diff(now, previous))
    previous = now
    if not events:
        message = "touch the panel" if touch is not None else "touch unavailable"
        status.set_text("RGB %d MHz | %s | %ds" % (kwargs["freq"] // 1_000_000, message,
                                                 time.ticks_diff(now, start) // 1000))
    lv.timer_handler()
    frames += 1
    time.sleep_ms(5)
gc.collect()
print("RGB_SMOKE=" + json.dumps({"timer_iterations": frames, "touch_points": events,
      "heap_free": gc.mem_free(), "draw_buffer_bytes_each": buffer_bytes,
      "touch_address": touch_address, "i2c_addresses": addresses,
      "touch_error": touch_error, "pixel_clock_requested_hz": kwargs["freq"], "visual_pass": None}))
