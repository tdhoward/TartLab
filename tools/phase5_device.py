"""Focused Phase 5 modern-firmware probes over the MicroPython raw REPL.

These commands exercise the physical LVGL/native-lcd-bus adapter.  They do
not flash firmware or install a filesystem, and their results are research
evidence until the operator observations in ``tests/PHASE5_HARDWARE.md`` are
complete.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import sys
import time

import serial

try:
    from phase1_device import RawRepl
except ImportError:  # Allow import as ``tools.phase5_device`` in host tests.
    from tools.phase1_device import RawRepl


PROBE_CODE = r'''
import gc, os, sys, machine, ujson

result = {
    "sys_version": sys.version,
    "implementation": repr(sys.implementation),
    "uname": repr(os.uname()),
    "reset_cause": machine.reset_cause(),
    "heap_free_before_platform": gc.mem_free(),
    "filesystem": os.statvfs("/"),
}

modules = {}
for name in (
    "lvgl", "lcd_bus", "st7796", "cst226", "i2c", "task_handler",
    "appdev", "displaydev", "spibus",
):
    try:
        module = __import__(name)
        modules[name] = True
        if name == "lvgl":
            version = getattr(module, "version_info", None)
            if version is not None:
                modules["lvgl_version"] = repr(version)
    except Exception as error:
        modules[name] = repr(error)
result["modules"] = modules

try:
    from tartlabutils.platform import get_platform
    platform = get_platform()
    result["platform"] = {
        "type": platform.__class__.__name__,
        "width": platform.width,
        "height": platform.height,
        "capabilities": platform.capabilities,
        "owner": platform.controller.owner,
        "transfer_pending": platform.controller.transfer_pending,
        "display_type": platform.display.__class__.__name__,
        "input_type": platform.input.__class__.__name__,
    }
    result["heap_free_after_platform"] = gc.mem_free()
except Exception as error:
    result["platform_error"] = repr(error)

print("PHASE5_PROBE=" + ujson.dumps(result))
'''


SOFT_RESET_PREFLIGHT = r'''
import os, ujson
from hdwconfig import BOARD_CONFIG

def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

with open("/state/boot.json", "r") as stream:
    boot = ujson.load(stream)
if boot.get("health") != "healthy" or \
        boot.get("consecutive_failures") != 0:
    raise ValueError("soft-reset cycle requires a healthy boot baseline")
if exists("/state/update.json") or exists("/state/recovery.flag") or \
        exists("/tmp/manifest.json"):
    raise ValueError("soft-reset cycle refuses active update or recovery state")
reset = BOARD_CONFIG.get("reset", {})
print("PHASE5_SOFT_RESET_PREFLIGHT=" + ujson.dumps({
    "boot": boot,
    "soft_reset_policy": reset.get("soft_reset", "native"),
}))
'''


SOFT_RESET_CYCLE_TEMPLATE = r'''
import gc, os, sys, ujson
from tartlabutils.platform import get_platform, set_platform

baseline = __BASELINE__
with open("/state/boot.json", "r") as stream:
    boot_after_reset = ujson.load(stream)

gc.collect()
result = {
    "boot_after_reset": boot_after_reset,
    "runtime": sys.version,
    "heap_before_platform": gc.mem_free(),
}
platform = None
try:
    platform = get_platform()
    platform.enter_ui_mode()
    controller = getattr(platform, "controller", None)
    wait = getattr(controller, "wait_for_transfer", None)
    if wait is not None:
        wait()
    result["platform"] = {
        "type": platform.__class__.__name__,
        "width": platform.width,
        "height": platform.height,
        "capabilities": platform.capabilities,
        "owner": getattr(controller, "owner", None),
        "transfer_pending": getattr(controller, "transfer_pending", False),
    }
    result["heap_with_platform"] = gc.mem_free()
finally:
    if platform is not None:
        platform.deinit()
    set_platform(None)
    gc.collect()
    result["heap_after_teardown"] = gc.mem_free()

temporary = "/state/boot.json.soft-reset-cycle.tmp"
try:
    os.remove(temporary)
except OSError:
    pass
with open(temporary, "w") as stream:
    ujson.dump(baseline, stream)
os.remove("/state/boot.json")
os.rename(temporary, "/state/boot.json")
print("PHASE5_SOFT_RESET_CYCLE=" + ujson.dumps(result))
'''


PROMOTED_SOFT_RESET_AUDIT = r'''
import machine, ujson
with open("/state/boot.json", "r") as stream:
    boot = ujson.load(stream)
print("PHASE5_PROMOTED_SOFT_RESET=" + ujson.dumps({
    "boot": boot,
    "reset_cause": machine.reset_cause(),
    "hard_reset": getattr(machine, "HARD_RESET", None),
}))
'''


HARDENING_TEMPLATE = r'''
import gc, os, time, ujson
from tartlabutils.platform import get_platform

scan_iterations = __SCAN_ITERATIONS__
frames_per_scan = __FRAMES_PER_SCAN__

def elapsed_us(started):
    return time.ticks_diff(time.ticks_us(), started)

def interface_state(interface):
    result = {"active": interface.active()}
    try:
        result["status"] = interface.status()
    except Exception as error:
        result["status_error"] = repr(error)
    return result

def filesystem_state():
    values = os.statvfs("/")
    block_size = values[0]
    total = block_size * values[2]
    free = block_size * values[3]
    return {
        "block_size": block_size,
        "total_bytes": total,
        "free_bytes": free,
        "used_bytes": total - free,
    }

def flash_state():
    result = {}
    try:
        import esp
        result["physical_bytes"] = esp.flash_size()
    except Exception as error:
        result["physical_error"] = repr(error)
    try:
        import esp32
        running = esp32.Partition(esp32.Partition.RUNNING)
        info = running.info()
        result["running_partition"] = {
            "type": info[0],
            "subtype": info[1],
            "address": info[2],
            "size_bytes": info[3],
            "label": info[4],
            "encrypted": info[5],
        }
        result["app_partition_sizes"] = [
            partition.info()[3]
            for partition in esp32.Partition.find(esp32.Partition.TYPE_APP)
        ]
    except Exception as error:
        result["partition_error"] = repr(error)
    return result

def sample_summary(values):
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count & 1:
        median = ordered[middle]
    else:
        median = (ordered[middle - 1] + ordered[middle]) // 2
    p95_index = ((count * 95 + 99) // 100) - 1
    return {
        "count": count,
        "minimum": ordered[0],
        "median": median,
        "p95": ordered[p95_index],
        "maximum": ordered[-1],
    }

network = {
    "scan_counts": [],
    "scan_us": [],
    "scan_errors": [],
    "concurrent_display_frames": [],
}
station = None
access_point = None
station_was_active = None
thread_module = None
try:
    import _thread as thread_module
    import network as network_module
    station = network_module.WLAN(network_module.STA_IF)
    access_point = network_module.WLAN(network_module.AP_IF)
    station_was_active = station.active()
    network["before"] = {
        "station": interface_state(station),
        "access_point": interface_state(access_point),
    }
    if not station_was_active:
        station.active(True)
        network["station_activated_for_probe"] = True
        time.sleep_ms(250)
    else:
        network["station_activated_for_probe"] = False
    network["workload_start"] = {
        "station": interface_state(station),
        "access_point": interface_state(access_point),
    }
except Exception as error:
    network["setup_error"] = repr(error)

gc.collect()
heap = {"baseline": gc.mem_free()}
filesystem = filesystem_state()
flash = flash_state()
platform = get_platform()
controller = platform.controller
surface = None
buffer = None
seed_buffer = None
write_us = []
write_summary = None
display_frames = 0
heap_minimum = None
requires_full_frame_seed = False
try:
    surface = platform.enter_game_mode()
    heap["after_enter_game"] = gc.mem_free()
    requires_full_frame_seed = bool(
        getattr(surface, "requires_full_frame_seed", False))
    if (requires_full_frame_seed and
            not getattr(surface, "shadow_valid", False)):
        seed_buffer = bytearray(
            surface.width * surface.height * surface.bytes_per_pixel)
        heap["with_seed_buffer"] = gc.mem_free()
        started = time.ticks_us()
        surface.write(
            seed_buffer, 0, 0, surface.width, surface.height)
        heap["after_seed_write"] = gc.mem_free()
        heap["seed_write_us"] = elapsed_us(started)

    width = min(96, surface.width)
    height = min(48, surface.height)
    buffer = surface.allocate_buffer(width, height)
    for offset in range(0, len(buffer), 2):
        buffer[offset] = 0x07
        buffer[offset + 1] = 0xE0
    heap["with_transfer_buffer"] = gc.mem_free()
    heap_minimum = heap["with_transfer_buffer"]

    for scan_index in range(scan_iterations):
        if station is not None and station.active():
            scan_state = {
                "active": False,
                "done": False,
                "count": None,
                "elapsed_us": None,
                "error": None,
            }

            def perform_scan():
                scan_state["active"] = True
                started = time.ticks_us()
                try:
                    networks = station.scan()
                    scan_state["count"] = len(networks)
                    networks = None
                except Exception as error:
                    scan_state["error"] = repr(error)
                scan_state["elapsed_us"] = elapsed_us(started)
                scan_state["done"] = True

            thread_module.start_new_thread(perform_scan, ())
            start_deadline = time.ticks_add(time.ticks_ms(), 1000)
            while (not scan_state["active"] and not scan_state["done"] and
                   time.ticks_diff(start_deadline, time.ticks_ms()) > 0):
                time.sleep_ms(5)
            if not scan_state["active"]:
                raise RuntimeError("Wi-Fi scan worker did not start")
        else:
            scan_state = None

        concurrent_frames = 0
        for frame_index in range(frames_per_scan):
            index = scan_index * frames_per_scan + frame_index
            x = (index * 17) % (surface.width - width + 1)
            y = (index * 11) % (surface.height - height + 1)
            scan_active = bool(
                scan_state is not None and scan_state["active"] and
                not scan_state["done"])
            started = time.ticks_us()
            surface.write(buffer, x, y, width, height)
            write_us.append(elapsed_us(started))
            display_frames += 1
            if scan_active:
                concurrent_frames += 1
            if surface.busy or controller.transfer_pending:
                raise RuntimeError("display transfer did not settle")
            current_heap = gc.mem_free()
            if current_heap < heap_minimum:
                heap_minimum = current_heap

        if scan_state is not None:
            scan_deadline = time.ticks_add(time.ticks_ms(), 15000)
            while (not scan_state["done"] and
                   time.ticks_diff(scan_deadline, time.ticks_ms()) > 0):
                time.sleep_ms(10)
            if not scan_state["done"]:
                raise RuntimeError("Wi-Fi scan worker did not finish")
            network["scan_us"].append(scan_state["elapsed_us"])
            network["concurrent_display_frames"].append(concurrent_frames)
            if scan_state["error"] is None:
                network["scan_counts"].append(scan_state["count"])
            else:
                network["scan_errors"].append(scan_state["error"])

    write_summary = sample_summary(write_us)
    write_us = None
    heap["minimum_during_workload"] = heap_minimum
finally:
    if surface is not None and controller.owner == "game":
        platform.enter_ui_mode()
    if surface is not None and buffer is not None:
        surface.free_buffer(buffer)
    buffer = None
    seed_buffer = None
    write_us = None
    if station is not None:
        try:
            network["workload_end"] = {
                "station": interface_state(station),
                "access_point": interface_state(access_point),
            }
            if station_was_active is False:
                station.active(False)
                time.sleep_ms(100)
            network["after_restore"] = {
                "station": interface_state(station),
                "access_point": interface_state(access_point),
            }
        except Exception as error:
            network["restore_error"] = repr(error)
    gc.collect()
    heap["after_cleanup"] = gc.mem_free()

result = {
    "scan_iterations": scan_iterations,
    "frames_per_scan": frames_per_scan,
    "display_frames": display_frames,
    "surface": {
        "width": surface.width,
        "height": surface.height,
        "requires_full_frame_seed": requires_full_frame_seed,
        "owner": controller.owner,
        "transfer_pending": controller.transfer_pending,
    },
    "write_us": write_summary,
    "heap": heap,
    "filesystem": filesystem,
    "flash": flash,
    "network": network,
}
print("PHASE5_HARDENING=" + ujson.dumps(result))
'''


RENDERER_CYCLE_TEMPLATE = r'''
import gc, time, ujson
from tartlabutils.platform import get_platform

iterations = %d
hold_ms = %d
platform = get_platform()
controller = platform.controller
surface = platform.enter_game_mode()
width = 96
height = 48
buffer = surface.allocate_buffer(width, height)
requires_full_frame_seed = bool(
    getattr(surface, "requires_full_frame_seed", False))
seed_buffer = None
if requires_full_frame_seed:
    seed_buffer = bytearray(
        surface.width * surface.height * surface.bytes_per_pixel)
for offset in range(0, len(buffer), 2):
    buffer[offset] = 0xF8
    buffer[offset + 1] = 0x00

transfer_us = []
seed_us = []
to_game_us = []
to_ui_us = []
heap_samples = []
try:
    platform.enter_ui_mode()
    for index in range(iterations):
        started = time.ticks_us()
        surface = platform.enter_game_mode()
        to_game_us.append(time.ticks_diff(time.ticks_us(), started))

        started = time.ticks_us()
        if (requires_full_frame_seed and
                not getattr(surface, "shadow_valid", False)):
            surface.write(
                seed_buffer, 0, 0, surface.width, surface.height)
        seed_us.append(time.ticks_diff(time.ticks_us(), started))

        started = time.ticks_us()
        surface.write(
            buffer,
            (index * 17) %% (surface.width - width + 1),
            (index * 11) %% (surface.height - height + 1),
            width,
            height,
        )
        transfer_us.append(time.ticks_diff(time.ticks_us(), started))
        if surface.busy:
            raise RuntimeError("synchronous direct transfer remained busy")
        if hold_ms:
            time.sleep_ms(hold_ms)

        started = time.ticks_us()
        platform.enter_ui_mode()
        to_ui_us.append(time.ticks_diff(time.ticks_us(), started))
        if controller.owner != "ui" or controller.transfer_pending:
            raise RuntimeError("UI ownership did not settle")
        if hold_ms:
            time.sleep_ms(hold_ms)
        gc.collect()
        heap_samples.append(gc.mem_free())
finally:
    if controller.owner == "game":
        platform.enter_ui_mode()
    surface.free_buffer(buffer)
    seed_buffer = None

result = {
    "iterations": iterations,
    "hold_ms": hold_ms,
    "owner": controller.owner,
    "transfer_pending": controller.transfer_pending,
    "requires_full_frame_seed": requires_full_frame_seed,
    "seed_us": seed_us,
    "transfer_us": transfer_us,
    "to_game_us": to_game_us,
    "to_ui_us": to_ui_us,
    "heap_free": heap_samples,
}
print("PHASE5_RENDERER_CYCLE=" + ujson.dumps(result))
'''


COLOR_CODE = r'''
import time, ujson
from tartlabutils.platform import get_platform

platform = get_platform()
surface = platform.enter_game_mode()
seeded = False
if (getattr(surface, "requires_full_frame_seed", False) and
        not getattr(surface, "shadow_valid", False)):
    seed_buffer = bytearray(
        surface.width * surface.height * surface.bytes_per_pixel)
    surface.write(seed_buffer, 0, 0, surface.width, surface.height)
    seed_buffer = None
    seeded = True
height = surface.height // 5
colors = (
    ("red", 0xF8, 0x00),
    ("green", 0x07, 0xE0),
    ("blue", 0x00, 0x1F),
    ("white", 0xFF, 0xFF),
    ("black", 0x00, 0x00),
)
drawn = []
try:
    for index, (name, high, low) in enumerate(colors):
        y = index * height
        band_height = surface.height - y if index == 4 else height
        buffer = surface.allocate_buffer(surface.width, band_height)
        for offset in range(0, len(buffer), 2):
            buffer[offset] = high
            buffer[offset + 1] = low
        started = time.ticks_us()
        surface.write(buffer, 0, y, surface.width, band_height)
        drawn.append((name, time.ticks_diff(time.ticks_us(), started)))
        surface.free_buffer(buffer)
finally:
    # Keep the color bars visible long enough for an operator observation.
    time.sleep(8)
    platform.enter_ui_mode()

print("PHASE5_COLOR=" + ujson.dumps({
    "logical_size": (surface.width, surface.height),
    "bands_top_to_bottom": drawn,
    "full_frame_seeded": seeded,
}))
'''


STATUS_VISUAL_CODE = r'''
import time, ujson
from tartlabutils.platform import get_platform

platform = get_platform()
platform.enter_ui_mode()
controller = platform.controller
lvgl = platform.lvgl

def refresh_and_hold(seconds):
    lvgl.refr_now(controller._lv_display)
    controller.wait_for_transfer()
    time.sleep(seconds)

view = platform.create_ide_view()
view.show_startup("VISUAL TEST")
view.show_network("TEST NETWORK", "192.0.2.1", "tartlab-test")
view.show_update_progress("Portrait status layout", 2, 4)
refresh_and_hold(5)

view.show_app_error()
refresh_and_hold(5)

platform.show_error()
controller.wait_for_transfer()
time.sleep(5)

view = platform.create_ide_view()
view.show_startup("VISUAL TEST COMPLETE")
view.show_update_progress("Returning to TartLab", 4, 4)
refresh_and_hold(3)

print("PHASE5_STATUS_VISUAL=" + ujson.dumps({
    "logical_size": (platform.width, platform.height),
    "stages": ("status", "app_error_indicator", "fatal_error", "complete"),
}))
'''


TOUCH_TEMPLATE = r'''
import time, ujson
from tartlabutils.platform import get_platform

duration_ms = %d
platform = get_platform()
platform.enter_ui_mode()
pointer = platform.input
samples = []
started = time.ticks_ms()
last = None
while time.ticks_diff(time.ticks_ms(), started) < duration_ms:
    if hasattr(pointer, "_get_coords"):
        value = pointer._get_coords()
        if value is not None:
            state, raw_x, raw_y = value
            logical_x, logical_y = pointer._calc_coords(raw_x, raw_y)
            sample = (raw_x, raw_y, logical_x, logical_y)
        else:
            sample = None
    else:
        touch_device = platform.app.touch_dev
        touch_device.poll()
        if touch_device.points:
            logical_x, logical_y = touch_device.points[0][:2]
            sample = (None, None, logical_x, logical_y)
        else:
            sample = None
    if sample is not None:
        if sample != last:
            samples.append(sample)
            last = sample
    time.sleep_ms(10)

print("PHASE5_TOUCH=" + ujson.dumps({
    "duration_ms": duration_ms,
    "samples": samples,
    "sample_count": len(samples),
}))
'''


INIT_CYCLE_TEMPLATE = r'''
import gc, ujson
from tartlabutils.platform import get_platform, set_platform

iterations = %d
results = []
for index in range(iterations):
    entry = {"index": index, "heap_before": gc.mem_free()}
    try:
        platform = get_platform()
        entry["owner"] = platform.controller.owner
        platform.enter_game_mode()
        platform.enter_ui_mode()
        platform.deinit()
        set_platform(None)
        del platform
        gc.collect()
        entry["heap_after"] = gc.mem_free()
        entry["ok"] = True
    except Exception as error:
        entry["ok"] = False
        entry["error"] = repr(error)
        results.append(entry)
        break
    results.append(entry)

print("PHASE5_INIT_CYCLE=" + ujson.dumps({
    "requested": iterations,
    "results": results,
}))
'''


TOUCH_ID_CODE = r'''
import i2c, machine, time, ujson

bus = i2c.I2C.Bus(host=0, scl=6, sda=5, freq=100000, use_locks=False)
reset = machine.Pin(13, machine.Pin.OUT)

def reset_touch():
    reset(0)
    time.sleep_ms(1)
    reset(1)
    time.sleep_ms(50)

def identify_raw():
    device = i2c.I2C.Device(bus=bus, dev_id=0x5A, reg_bits=8)
    result = bytearray(4)
    device.write(b"\xD2\x04")
    device.read(buf=result)
    return list(result)

def identify_register(bits):
    device = i2c.I2C.Device(bus=bus, dev_id=0x5A, reg_bits=bits)
    result = bytearray(4)
    device.write_readinto(b"\xD2\x04", result)
    return list(result)

reset_touch()
raw = identify_raw()
reset_touch()
register8 = identify_register(8)
reset_touch()
register16 = identify_register(16)
print("PHASE5_TOUCH_ID=" + ujson.dumps({
    "scan": bus.scan(),
    "raw_write_then_read": raw,
    "register_8_bit": register8,
    "register_16_bit": register16,
}))
'''


DEVICE_STATUS_CODE = r'''
import machine, ujson
from tartlabutils.platform import get_platform
from tartlabutils import get_selected_app, load_settings

platform = get_platform()
display = platform.display
backlight = getattr(display, "_backlight_pin", None)
settings = load_settings()
result = {
    "reset_cause": machine.reset_cause(),
    "backlight_percent": display.get_backlight(),
    "selected_app": get_selected_app(),
    "startup_mode": settings.get("STARTUP_MODE", "BUTTON"),
}
if backlight is not None:
    for name in ("freq", "duty_u16"):
        try:
            result["backlight_" + name] = getattr(backlight, name)()
        except Exception as error:
            result["backlight_" + name] = repr(error)
try:
    with open("/state/boot.json", "r") as stream:
        result["boot"] = ujson.load(stream)
except Exception as error:
    result["boot_error"] = repr(error)
print("PHASE5_DEVICE_STATUS=" + ujson.dumps(result))
'''


GAMMA_COMPARE_CODE = r'''
import time, ujson
from tartlabutils.platform import get_platform

modern_gamma = bytes((
    0xF0, 0x09, 0x0B, 0x06, 0x04, 0x03, 0x2D,
    0x43, 0x42, 0x3B, 0x16, 0x14, 0x17, 0x1B,
))
legacy_gamma = bytes((
    0xE0, 0x09, 0x0B, 0x06, 0x04, 0x03, 0x2B,
    0x43, 0x42, 0x3B, 0x16, 0x14, 0x17, 0x1B,
))
grays = (
    (0x00, 0x00),
    (0x42, 0x08),
    (0x84, 0x10),
    (0xC6, 0x18),
    (0xFF, 0xFF),
)

platform = get_platform()
surface = platform.enter_game_mode()
stripe_width = surface.width // len(grays)

def fill(x, y, width, height, high, low):
    buffer = surface.allocate_buffer(width, height)
    try:
        for offset in range(0, len(buffer), 2):
            buffer[offset] = high
            buffer[offset + 1] = low
        surface.write(buffer, x, y, width, height)
    finally:
        surface.free_buffer(buffer)

def marker(high, low):
    fill(0, 0, surface.width, 18, high, low)

try:
    for index, (high, low) in enumerate(grays):
        x = index * stripe_width
        width = surface.width - x if index == len(grays) - 1 else stripe_width
        fill(x, 18, width, surface.height - 18, high, low)

    # Give the operator time to turn attention to the device.
    time.sleep(5)
    marker(0xF8, 0x00)
    time.sleep(6)
    platform.display.set_params(0xE1, legacy_gamma)
    marker(0x07, 0xE0)
    time.sleep(10)
    platform.display.set_params(0xE1, modern_gamma)
    marker(0xF8, 0x00)
    time.sleep(6)
finally:
    platform.display.set_params(0xE1, modern_gamma)
    platform.enter_ui_mode()

print("PHASE5_GAMMA_COMPARE=" + ujson.dumps({
    "backlight_percent": platform.display.get_backlight(),
    "phases": (
        ("modern", "red", 6),
        ("legacy", "green", 10),
        ("modern", "red", 6),
    ),
}))
'''


FAILURE_STATUS_CODE = r'''
import os, ujson

def read_json(path, default):
    try:
        with open(path, "r") as stream:
            return ujson.load(stream)
    except Exception:
        return default

logs = sorted(
    name for name in os.listdir("/state/logs") if name.endswith(".log"))
latest = logs[-1] if logs else None
latest_text = ""
if latest is not None:
    with open("/state/logs/" + latest, "r") as stream:
        latest_text = stream.read()
recent_logs = []
for name in logs[-3:]:
    with open("/state/logs/" + name, "r") as stream:
        recent_logs.append((name, stream.read()[-6000:]))
try:
    import tartlabutils.launcher as launcher
    launcher_timer = repr(launcher._health_timer)
except Exception as error:
    launcher_timer = repr(error)

print("PHASE5_FAILURE_STATUS=" + ujson.dumps({
    "boot": read_json("/state/boot.json", {}),
    "startup_mode": read_json("/state/settings.json", {}).get(
        "STARTUP_MODE", "BUTTON"),
    "selected_app": read_json("/state/selected_app.json", {}).get(
        "filename", "hello.py"),
    "latest_log": latest,
    "latest_log_tail": latest_text[-6000:],
    "launcher_health_timer": launcher_timer,
    "recent_logs": recent_logs,
    "user_files": sorted(os.listdir("/files/user")),
}))
'''


SWITCH_TEST_APP = r'''"""Temporary Phase 5 application-switch qualification app."""

import time

from tartlabutils.platform import get_platform


platform = get_platform()
surface = platform.enter_game_mode()
colors = (
    (0xF8, 0x1F),  # magenta
    (0x07, 0xFF),  # cyan
    (0xFF, 0xE0),  # yellow
    (0x07, 0xE0),  # green
    (0x00, 0x1F),  # blue
)
stripe_width = surface.width // len(colors)

if getattr(surface, "requires_full_frame_seed", False):
    # Full-frame seeds can exceed internal DMA memory. The ST77922 surface
    # copies this ordinary heap/PSRAM buffer into its own bounded DMA scratch.
    buffer = bytearray(surface.width * surface.height * 2)
    row = bytearray(surface.width * 2)
    for x in range(surface.width):
        index = min(x // stripe_width, len(colors) - 1)
        high, low = colors[index]
        row[x * 2] = high
        row[x * 2 + 1] = low
    for y in range(surface.height):
        offset = y * len(row)
        buffer[offset:offset + len(row)] = row
    surface.write(buffer, 0, 0, surface.width, surface.height)
else:
    for index, (high, low) in enumerate(colors):
        x = index * stripe_width
        width = surface.width - x if index == len(colors) - 1 else stripe_width
        buffer = surface.allocate_buffer(width, surface.height)
        try:
            for offset in range(0, len(buffer), 2):
                buffer[offset] = high
                buffer[offset + 1] = low
            surface.write(buffer, x, 0, width, surface.height)
        finally:
            surface.free_buffer(buffer)

while True:
    time.sleep_ms(250)
'''


SWITCH_APP_PATH = "/files/user/phase5_modern_switch_test.py"
SWITCH_MARKER_PATH = "/state/phase5_modern_switch_test.json"


def _extract(output: bytes, marker: str) -> dict:
    decoded = output.decode("utf-8", "replace")
    prefix = marker + "="
    for line in decoded.splitlines():
        if line.startswith(prefix):
            value = json.loads(line[len(prefix):])
            if not isinstance(value, dict):
                raise ValueError(f"{marker} payload is not an object")
            return value
    raise ValueError(f"device output did not contain {marker}: {decoded[-500:]}")


def _run(args: argparse.Namespace, code: str, marker: str,
         timeout: int | None = None) -> None:
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(code, timeout or args.timeout)
    finally:
        repl.close()
    print(json.dumps(_extract(output, marker), indent=2, sort_keys=True))


def probe(args: argparse.Namespace) -> None:
    _run(args, PROBE_CODE, "PHASE5_PROBE", max(args.timeout, 45))


def _reconnect_after_soft_reset(
        repl: RawRepl, args: argparse.Namespace) -> RawRepl:
    repl.serial.reset_input_buffer()
    repl.serial.write(b"\x04")
    repl._read_until(b"soft reboot\r\n", max(args.timeout, 30))
    repl._read_until(
        b"raw REPL; CTRL-B to exit\r\n>", max(args.timeout, 30))
    repl.close()
    time.sleep(0.5)
    replacement = RawRepl(args.port, args.baudrate, args.timeout)
    replacement.enter()
    return replacement


def _wait_for_boot_markers(
        args: argparse.Namespace, timeout: int) -> dict[str, int]:
    markers = (b"System startup", b"HEALTHY mode=IDE")
    found = {}
    captured = bytearray()
    started = time.monotonic()
    deadline = started + timeout
    connection = None
    try:
        while len(found) < len(markers) and time.monotonic() < deadline:
            if connection is None:
                try:
                    connection = serial.Serial(
                        port=None,
                        baudrate=args.baudrate,
                        timeout=0.2,
                        write_timeout=2,
                        dsrdtr=False,
                        rtscts=False,
                    )
                    connection.dtr = False
                    connection.rts = False
                    connection.port = args.port
                    connection.open()
                except (OSError, serial.SerialException):
                    if connection is not None:
                        connection.close()
                    connection = None
                    time.sleep(0.2)
                    continue
            try:
                chunk = connection.read(connection.in_waiting or 1)
            except (OSError, serial.SerialException):
                connection.close()
                connection = None
                time.sleep(0.2)
                continue
            if not chunk:
                continue
            captured.extend(chunk)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            for marker in markers:
                if marker not in found and marker in captured:
                    found[marker] = elapsed_ms
            if len(captured) > 8192:
                del captured[:-4096]
    finally:
        if connection is not None:
            connection.close()
    if len(found) != len(markers):
        missing = [marker.decode() for marker in markers if marker not in found]
        raise TimeoutError("soft-reset boot markers not observed: %r" % missing)
    return {
        "system_startup_ms": found[markers[0]],
        "ide_healthy_ms": found[markers[1]],
    }


def soft_reset_cycle(args: argparse.Namespace) -> None:
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    baseline = None
    restore_state = None
    results = []
    try:
        repl.enter()
        preflight = _extract(
            repl.exec(SOFT_RESET_PREFLIGHT, max(args.timeout, 30)),
            "PHASE5_SOFT_RESET_PREFLIGHT",
        )
        baseline = preflight["boot"]
        restore_state = baseline
        if preflight["soft_reset_policy"] == "hard_reset":
            previous = baseline
            for unused_index in range(args.iterations):
                repl.serial.write(b"\x04")
                repl.close()
                repl = None
                timing = _wait_for_boot_markers(
                    args, max(args.timeout, 75))
                repl = RawRepl(args.port, args.baudrate, args.timeout)
                repl.enter()
                result = _extract(
                    repl.exec(
                        PROMOTED_SOFT_RESET_AUDIT, max(args.timeout, 30)),
                    "PHASE5_PROMOTED_SOFT_RESET",
                )
                boot = result["boot"]
                if (result["reset_cause"] != result["hard_reset"] or
                        boot.get("health") != "healthy" or
                        boot.get("consecutive_failures") != 0 or
                        boot.get("sequence") !=
                        previous.get("sequence", 0) + 1):
                    raise RuntimeError(
                        "promoted soft-reset state did not match expectation")
                result["timing"] = timing
                results.append(result)
                previous = boot
                restore_state = boot
        else:
            code = SOFT_RESET_CYCLE_TEMPLATE.replace(
                "__BASELINE__", repr(baseline))
            for unused_index in range(args.iterations):
                repl = _reconnect_after_soft_reset(repl, args)
                result = _extract(
                    repl.exec(code, max(args.timeout, 60)),
                    "PHASE5_SOFT_RESET_CYCLE",
                )
                boot = result["boot_after_reset"]
                if (boot.get("health") != "starting" or
                        boot.get("consecutive_failures") != 1 or
                        boot.get("sequence") !=
                        baseline.get("sequence", 0) + 1):
                    raise RuntimeError(
                        "soft-reset boot state did not match expectation")
                results.append(result)
    finally:
        if repl is None and restore_state is not None:
            try:
                repl = RawRepl(args.port, args.baudrate, args.timeout)
                repl.enter()
            except Exception:
                repl = None
        if repl is not None and restore_state is not None:
            try:
                restore = (
                    "import os,ujson\n"
                    "p='/state/boot.json.soft-reset-cycle.tmp'\n"
                    "try: os.remove(p)\n"
                    "except OSError: pass\n"
                    "f=open(p,'w');ujson.dump(%r,f);f.close()\n"
                    "try: os.remove('/state/boot.json')\n"
                    "except OSError: pass\n"
                    "os.rename(p,'/state/boot.json')\n"
                ) % restore_state
                repl.exec(restore, max(args.timeout, 30))
            except Exception:
                pass
        if repl is not None:
            try:
                repl.serial.write(b"import machine\nmachine.reset()\n\x04")
                time.sleep(0.5)
            finally:
                repl.close()
    print(json.dumps({
        "iterations": args.iterations,
        "policy": preflight["soft_reset_policy"],
        "baseline": baseline,
        "results": results,
    }, indent=2, sort_keys=True))


def hardening(args: argparse.Namespace) -> None:
    code = HARDENING_TEMPLATE.replace(
        "__SCAN_ITERATIONS__", str(args.scan_iterations)).replace(
            "__FRAMES_PER_SCAN__", str(args.frames_per_scan))
    timeout = max(
        args.timeout,
        args.scan_iterations * 15 + 60,
    )
    _run(args, code, "PHASE5_HARDENING", timeout)


def renderer_cycle(args: argparse.Namespace) -> None:
    code = RENDERER_CYCLE_TEMPLATE % (args.iterations, args.hold_ms)
    _run(args, code, "PHASE5_RENDERER_CYCLE", max(args.timeout, 120))


def color(args: argparse.Namespace) -> None:
    _run(args, COLOR_CODE, "PHASE5_COLOR", max(args.timeout, 45))


def status_visual(args: argparse.Namespace) -> None:
    _run(
        args, STATUS_VISUAL_CODE, "PHASE5_STATUS_VISUAL",
        max(args.timeout, 45))


def touch(args: argparse.Namespace) -> None:
    code = TOUCH_TEMPLATE % (args.seconds * 1000)
    _run(args, code, "PHASE5_TOUCH", max(args.timeout, args.seconds + 15))


def init_cycle(args: argparse.Namespace) -> None:
    code = INIT_CYCLE_TEMPLATE % args.iterations
    _run(args, code, "PHASE5_INIT_CYCLE", max(args.timeout, 120))


def touch_id(args: argparse.Namespace) -> None:
    _run(args, TOUCH_ID_CODE, "PHASE5_TOUCH_ID", max(args.timeout, 45))


def device_status(args: argparse.Namespace) -> None:
    _run(args, DEVICE_STATUS_CODE, "PHASE5_DEVICE_STATUS", max(args.timeout, 45))


def gamma_compare(args: argparse.Namespace) -> None:
    _run(args, GAMMA_COMPARE_CODE, "PHASE5_GAMMA_COMPARE", max(args.timeout, 60))


def failure_status(args: argparse.Namespace) -> None:
    _run(args, FAILURE_STATUS_CODE, "PHASE5_FAILURE_STATUS", max(args.timeout, 45))


def stage_switch_app(args: argparse.Namespace) -> None:
    content = SWITCH_TEST_APP.encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        preflight = r'''
import os, uhashlib, ujson
from tartlabutils import get_selected_app

def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

if exists(%r):
    raise ValueError("qualification marker already exists")
resume_existing = exists(%r)
if resume_existing:
    value = uhashlib.sha256()
    with open(%r, "rb") as stream:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break
            value.update(chunk)
    actual = "".join("%%02x" %% byte for byte in value.digest())
    if actual != %r:
        raise ValueError("qualification app path has unexpected content")
print("PHASE5_SWITCH_PREFLIGHT=" + ujson.dumps({
    "original_selection": get_selected_app(),
    "resume_existing": resume_existing,
}))
''' % (
            SWITCH_MARKER_PATH, SWITCH_APP_PATH, SWITCH_APP_PATH, digest)
        original = _extract(
            repl.exec(preflight, max(args.timeout, 45)),
            "PHASE5_SWITCH_PREFLIGHT")
        if not original["resume_existing"]:
            repl.stream_file(
                SWITCH_APP_PATH, content, digest, max(args.timeout, 90))
        finalize = r'''
import ujson
from tartlabutils import save_selected_app
marker = {
    "schema": 1,
    "original_selection": %r,
    "test_app": %r,
    "sha256": %r,
}
with open(%r, "w") as stream:
    ujson.dump(marker, stream)
save_selected_app(%r)
print("PHASE5_SWITCH_STAGED=" + ujson.dumps(marker))
''' % (
            original["original_selection"], SWITCH_APP_PATH, digest,
            SWITCH_MARKER_PATH, SWITCH_APP_PATH.rsplit("/", 1)[-1])
        staged = _extract(
            repl.exec(finalize, max(args.timeout, 45)),
            "PHASE5_SWITCH_STAGED")
    finally:
        repl.close()
    print(json.dumps(staged, indent=2, sort_keys=True))


def cleanup_switch_app(args: argparse.Namespace) -> None:
    code = r'''
import os, ujson
from tartlabutils import save_selected_app
with open(%r, "r") as stream:
    marker = ujson.load(stream)
if marker.get("test_app") != %r:
    raise ValueError("unexpected qualification cleanup marker")
save_selected_app(marker["original_selection"])
os.remove(%r)
os.remove(%r)
print("PHASE5_SWITCH_CLEANED=" + ujson.dumps({
    "restored_selection": marker["original_selection"],
}))
''' % (
        SWITCH_MARKER_PATH, SWITCH_APP_PATH,
        SWITCH_APP_PATH, SWITCH_MARKER_PATH)
    _run(args, code, "PHASE5_SWITCH_CLEANED", max(args.timeout, 45))


def monitor_reset(args: argparse.Namespace) -> None:
    """Passively capture console output, reconnecting across USB resets."""
    deadline = time.monotonic() + args.seconds
    connection = None
    pending = bytearray()

    def report(message: str) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"[{stamp}] {message}", flush=True)

    report(f"monitoring {args.port} for {args.seconds} seconds (no writes)")
    try:
        while time.monotonic() < deadline:
            if connection is None:
                try:
                    connection = serial.Serial(
                        port=None,
                        baudrate=args.baudrate,
                        timeout=0.2,
                        write_timeout=2,
                        dsrdtr=False,
                        rtscts=False,
                    )
                    # Establish inactive modem-control states before opening so
                    # merely observing native USB cannot request a board reset.
                    connection.dtr = False
                    connection.rts = False
                    connection.port = args.port
                    connection.open()
                    report("serial connected")
                except (OSError, serial.SerialException) as error:
                    if connection is not None:
                        connection.close()
                    connection = None
                    time.sleep(0.5)
                    continue
            try:
                chunk = connection.read(connection.in_waiting or 1)
                if not chunk:
                    continue
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, pending = pending.partition(b"\n")
                    report("RX " + repr(bytes(line.rstrip(b"\r"))))
            except (OSError, serial.SerialException) as error:
                report(f"serial disconnected: {error}")
                connection.close()
                connection = None
        if pending:
            report("RX " + repr(bytes(pending)))
    finally:
        if connection is not None:
            connection.close()
    report("monitor complete")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--port", default="COM6")
    result.add_argument("--baudrate", type=int, default=115200)
    result.add_argument("--timeout", type=int, default=20)
    commands = result.add_subparsers(dest="command", required=True)

    commands.add_parser("probe").set_defaults(func=probe)

    soft_reset = commands.add_parser("soft-reset-cycle")
    soft_reset.add_argument("--iterations", type=int, default=5)
    soft_reset.set_defaults(func=soft_reset_cycle)

    hardening_parser = commands.add_parser("hardening")
    hardening_parser.add_argument("--scan-iterations", type=int, default=3)
    hardening_parser.add_argument("--frames-per-scan", type=int, default=25)
    hardening_parser.set_defaults(func=hardening)

    renderer = commands.add_parser("renderer-cycle")
    renderer.add_argument("--iterations", type=int, default=25)
    renderer.add_argument(
        "--hold-ms", type=int, default=0,
        help="hold direct and UI phases for visual inspection")
    renderer.set_defaults(func=renderer_cycle)

    commands.add_parser("color").set_defaults(func=color)
    commands.add_parser("status-visual").set_defaults(func=status_visual)

    commands.add_parser("touch-id").set_defaults(func=touch_id)
    commands.add_parser("device-status").set_defaults(func=device_status)
    commands.add_parser("gamma-compare").set_defaults(func=gamma_compare)
    commands.add_parser("failure-status").set_defaults(func=failure_status)
    commands.add_parser("stage-switch-app").set_defaults(func=stage_switch_app)
    commands.add_parser("cleanup-switch-app").set_defaults(func=cleanup_switch_app)

    monitor = commands.add_parser("monitor-reset")
    monitor.add_argument("--seconds", type=int, default=300)
    monitor.set_defaults(func=monitor_reset)

    touch_parser = commands.add_parser("touch")
    touch_parser.add_argument("--seconds", type=int, default=20)
    touch_parser.set_defaults(func=touch)

    initialization = commands.add_parser("init-cycle")
    initialization.add_argument("--iterations", type=int, default=5)
    initialization.set_defaults(func=init_cycle)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "iterations", 1) <= 0:
        raise ValueError("iterations must be positive")
    if getattr(args, "scan_iterations", 1) <= 0:
        raise ValueError("scan-iterations must be positive")
    if getattr(args, "frames_per_scan", 1) <= 0:
        raise ValueError("frames-per-scan must be positive")
    if getattr(args, "hold_ms", 0) < 0:
        raise ValueError("hold-ms must be nonnegative")
    if getattr(args, "seconds", 1) <= 0:
        raise ValueError("seconds must be positive")
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TimeoutError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
