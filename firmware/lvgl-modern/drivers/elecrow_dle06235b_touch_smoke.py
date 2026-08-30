"""Five-target LVGL touch smoke for the Elecrow DLE06235B."""

import i2c
import lvgl as lv

import elecrow_dle06235b_smoke as smoke
from st77922_touch import ST77922Touch


i2c_bus = i2c.I2C.Bus(
    host=0,
    scl=39,
    sda=38,
    freq=100_000,
    use_locks=False,
)
touch_device = i2c.I2C.Device(
    bus=i2c_bus,
    dev_id=0x55,
    reg_bits=16,
)
pointer = ST77922Touch(
    touch_device,
    startup_rotation=lv.DISPLAY_ROTATION._0,
    debug=True,
)

screen = lv.screen_active()
screen.clean()
screen.set_style_bg_color(lv.color_hex(0x102040), lv.PART.MAIN)

status = lv.label(screen)
status.set_text("Tap all five targets: 0 / 5")
status.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
status.set_pos(58, 135)

hits = set()
targets = []
callbacks = []


def _add_target(name, x, y):
    button = lv.button(screen)
    button.set_pos(x, y)
    button.set_size(130, 70)
    button.set_style_bg_color(lv.color_hex(0x205080), lv.PART.MAIN)

    label = lv.label(button)
    label.set_text(name)
    label.center()

    def clicked(_event):
        if name in hits:
            return
        hits.add(name)
        button.set_style_bg_color(lv.color_hex(0x208040), lv.PART.MAIN)
        status.set_text("Tap all five targets: {} / 5".format(len(hits)))
        print("LVGL_TOUCH_HIT {} {}_of_5".format(name, len(hits)))
        if len(hits) == 5:
            status.set_text("LVGL TOUCH PASS - 5 / 5")
            print("LVGL_TOUCH_SMOKE_PASS")

    button.add_event_cb(clicked, lv.EVENT.CLICKED, None)
    targets.append(button)
    callbacks.append(clicked)


_add_target("TOP LEFT", 5, 5)
_add_target("TOP RIGHT", 185, 5)
_add_target("CENTER", 95, 205)
_add_target("BOTTOM LEFT", 5, 405)
_add_target("BOTTOM RIGHT", 185, 405)

print("ELECROW_LVGL_TOUCH_SMOKE_READY")
