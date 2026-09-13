"""Run with mpremote after copying a declarative payload to /hdwconfig.py."""

import gc
import json
import machine
import os
import sys
import time
from hdwconfig import BOARD_CONFIG

pins = {p["type"]: p["number"] for p in BOARD_CONFIG["pins"]}
gc.collect()
report = {
    "version": sys.version, "heap_free": gc.mem_free(),
    "heap_allocated": gc.mem_alloc(), "cpu_hz": machine.freq(),
    "statvfs": os.statvfs("/"),
}
for name in ("lvgl", "lcd_bus", "rgb_display", "gt911", "external_root"):
    try:
        module = __import__(name)
        report[name] = "imported"
        if name == "lvgl":
            report["lvgl_version"] = (module.version_major(), module.version_minor(), module.version_patch())
    except ImportError as error:
        report[name] = str(error)

touch = BOARD_CONFIG["touch"]
sda = machine.Pin(pins["TOUCH_SDA"], machine.Pin.OPEN_DRAIN, machine.Pin.PULL_UP, value=1)
scl = machine.Pin(pins["TOUCH_SCL"], machine.Pin.OPEN_DRAIN, machine.Pin.PULL_UP, value=1)
if touch["i2c"]["host"] < 0:
    i2c = machine.SoftI2C(sda=sda, scl=scl, freq=touch["i2c"]["frequency"])
else:
    i2c = machine.I2C(touch["i2c"]["host"], sda=sda, scl=scl, freq=touch["i2c"]["frequency"])
report["i2c_before"] = i2c.scan()
expander = touch.get("reset_expander")
if expander and expander["address"] in report["i2c_before"]:
    if expander["driver"] != "PCA9557":
        raise ValueError("unsupported touch reset expander")
    # PCA9557 output/configuration registers. Preserve unrelated outputs.
    address = expander["address"]
    reset_mask = 1 << expander["reset_bit"]
    interrupt_mask = 1 << expander["interrupt_bit"]
    mask = reset_mask | interrupt_mask
    output = i2c.readfrom_mem(address, 1, 1)[0]
    direction = i2c.readfrom_mem(address, 3, 1)[0]
    i2c.writeto_mem(address, 1, bytes([output & ~mask]))
    i2c.writeto_mem(address, 3, bytes([direction & ~mask]))
    time.sleep_ms(expander["assert_ms"])
    i2c.writeto_mem(address, 1, bytes([(output & ~mask) | reset_mask]))
    time.sleep_ms(expander["release_ms"])
    i2c.writeto_mem(address, 3, bytes([(direction & ~reset_mask) | interrupt_mask]))
    report["touch_reset"] = "PCA9557 sequence completed"
report["i2c_after"] = i2c.scan()
for address in touch["addresses"]:
    if address in report["i2c_after"]:
        report["touch_product"] = list(i2c.readfrom_mem(address, 0x8140, 4, addrsize=16))
        report["touch_geometry"] = list(i2c.readfrom_mem(address, 0x8146, 4, addrsize=16))
        report["touch_address"] = address
deinit = getattr(i2c, "deinit", None)
if deinit is not None:
    deinit()
i2c = None
gc.collect()
sd = None
try:
    from external_root import open_sd
    sd = open_sd(BOARD_CONFIG)
    report["sd"] = {"blocks": sd.ioctl(4, 0)}
except Exception as error:
    report["sd"] = {"error": repr(error), "tested_card_io": False}
finally:
    if sd is not None:
        sd.deinit()
print("BOARD_PROBE=" + json.dumps(report))
