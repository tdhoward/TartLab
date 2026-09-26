"""Read-only SD-root state and integrity checks for the host bench runner."""

import binascii
import gc
import hashlib
import json
import os
import sys
import vfs


def sd_runtime_status():
    import machine
    import external_root
    from hdwconfig import BOARD_CONFIG

    result = {"board_id": BOARD_CONFIG["id"],
              "mounts": [(repr(fs), path) for fs, path in vfs.mount()],
              "reset_cause": machine.reset_cause(),
              "soft_reset_cause": machine.SOFT_RESET,
              "selector": sys.modules["hdwconfig"].__file__,
              "helper": getattr(external_root, "__file__", "<frozen>")}
    if any(path == "/flash" for _, path in vfs.mount()):
        import tartlabutils
        from tartlabutils.platform import board_runtime_path
        result["library"] = tartlabutils.__file__
        result["board_runtime"] = board_runtime_path()
        for name, path in (("counts", "/.tartlab-bench/startup.json"),
                           ("state", "/state/sd-bench.json"),
                           ("user_file", "/files/user/sd-bench.txt")):
            with open(path) as stream:
                result[name] = json.load(stream)
        result["internal_main_bytes"] = os.stat("/flash/main.py")[6]
        result["sd_frequency_hz"] = BOARD_CONFIG["storage"]["frequency"]
        result["pixel_clock_requested_hz"] = BOARD_CONFIG["display"]["rgb"]["freq"]
        result["status"] = status.get_text()
    gc.collect()
    result["heap_free"] = gc.mem_free()
    import esp32
    import lcd_bus
    # Preserve each region's total/free/largest/minimum values, rather than
    # confusing the Python PSRAM heap with internal DMA headroom.
    result["internal_dma_heap"] = esp32.idf_heap_info(lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
    return result


def sd_runtime_hashes(paths):
    results = {}
    for path in paths:
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as stream:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
        results[path] = {"bytes": size, "sha256": binascii.hexlify(digest.digest()).decode()}
    return results
