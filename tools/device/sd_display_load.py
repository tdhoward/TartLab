"""Run after sd_root_smoke.py, with SD_LOAD_SOURCE supplied by the host.

Exercises simultaneous RGB refresh, SD copy/readback and garbage collection.
The operator must assess alignment/flicker; serial success proves file hashes.
"""

import binascii
import gc
import hashlib
import json
import os
import time


def sd_display_load(source, expected_sha256):
    destination = "/.tartlab-bench/display-load.bin"
    result_path = "/.tartlab-bench/display-load.json"
    copied = 0
    digest = hashlib.sha256()
    started = time.ticks_ms()
    previous = started

    def refresh(message):
        nonlocal previous
        now = time.ticks_ms()
        lv.tick_inc(time.ticks_diff(now, previous))
        previous = now
        status.set_text(message)
        lv.timer_handler()

    with open(source, "rb") as reader, open(destination, "wb") as writer:
        while True:
            chunk = reader.read(4096)
            if not chunk:
                break
            if writer.write(chunk) != len(chunk):
                raise OSError("short SD write")
            copied += len(chunk)
            digest.update(chunk)
            refresh("SD read/write load | %d KiB" % (copied // 1024))
            if copied % (128 * 1024) == 0:
                gc.collect()
    os.sync()
    write_ms = time.ticks_diff(time.ticks_ms(), started)
    source_hash = binascii.hexlify(digest.digest()).decode()
    digest = hashlib.sha256()
    checked = 0
    with open(destination, "rb") as reader:
        while True:
            chunk = reader.read(4096)
            if not chunk:
                break
            digest.update(chunk)
            checked += len(chunk)
            refresh("SD verify | %d KiB" % (checked // 1024))
    actual_hash = binascii.hexlify(digest.digest()).decode()
    if source_hash != expected_sha256 or actual_hash != expected_sha256 or checked != copied:
        refresh("SD load FAILED")
        raise ValueError("SD load content mismatch")
    gc.collect()
    result = {"bytes": copied, "sha256": actual_hash, "copy_sync_ms": write_ms,
              "total_ms": time.ticks_diff(time.ticks_ms(), started),
              "heap_free": gc.mem_free(), "pixel_clock_requested_hz": config["rgb"]["freq"],
              "visual_alignment": None, "visual_flicker": None}
    with open(result_path, "w") as stream:
        json.dump(result, stream)
    os.sync()
    refresh("SD load PASS | safe to power cycle")
    print("SD_DISPLAY_LOAD=" + json.dumps(result))


sd_display_load(SD_LOAD_SOURCE, SD_LOAD_SHA256)
