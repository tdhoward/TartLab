"""Bounded SD copy/readback with RGB refresh and optional Wi-Fi radio activity.

The host supplies paths and expectations. New outputs refuse collisions.
Wi-Fi checks exercise AP start/stop and station scans, not network throughput.
"""

import binascii
import gc
import hashlib
import json
import os
import time


def sd_runtime_load(source, destination, expected, wifi, refresh_callback=None):
    # Never replace an existing file, including a partial earlier attempt.
    try:
        os.stat(destination)
    except OSError as error:
        if error.args[0] != 2:
            raise
    else:
        raise ValueError("existing load output preserved: " + destination)
    previous = time.ticks_ms()
    refreshes = 0
    collections = 0
    heap_min = gc.mem_free()
    ap = station = None
    result = {"wifi_radio": wifi is not None, "network_transfer_bytes": 0}

    def refresh(message):
        nonlocal previous, refreshes
        if refresh_callback is not None:
            # A shared platform owns its LVGL ticks and task handler. Let the
            # caller update its view without ticking LVGL a second time.
            refresh_callback(message)
            refreshes += 1
            return
        now = time.ticks_ms()
        lv.tick_inc(time.ticks_diff(now, previous))
        previous = now
        status.set_text(message)
        lv.timer_handler()
        refreshes += 1

    def collect():
        nonlocal collections, heap_min
        gc.collect()
        collections += 1
        heap_min = min(heap_min, gc.mem_free())

    started = time.ticks_ms()
    try:
        if wifi:
            import network
            candidate_ap = network.WLAN(network.AP_IF)
            candidate_station = network.WLAN(network.STA_IF)
            if candidate_ap.active() or candidate_station.active():
                raise ValueError("Wi-Fi already active; existing network state preserved")
            ap, station = candidate_ap, candidate_station
            ap.config(essid=wifi["ssid"], password=wifi["password"],
                      authmode=network.AUTH_WPA2_PSK)
            ap.active(True)
            station.active(True)
            result["ap_active"] = ap.active()
            refresh("SD + RGB + Wi-Fi scan")
            result["scan_network_count"] = len(station.scan())
            collect()

        copied = 0
        source_digest = hashlib.sha256()
        with open(source, "rb") as reader, open(destination, "wb") as writer:
            while True:
                chunk = reader.read(4096)
                if not chunk:
                    break
                if writer.write(chunk) != len(chunk):
                    raise OSError("short SD write")
                source_digest.update(chunk)
                copied += len(chunk)
                refresh("SD + RGB%s | copy %d KiB" % (" + AP" if wifi else "", copied // 1024))
                if copied % (128 * 1024) == 0:
                    collect()
        os.sync()
        result["copy_sync_ms"] = time.ticks_diff(time.ticks_ms(), started)
        checked = 0
        digest = hashlib.sha256()
        with open(destination, "rb") as reader:
            while True:
                chunk = reader.read(4096)
                if not chunk:
                    break
                digest.update(chunk)
                checked += len(chunk)
                refresh("SD + RGB%s | verify %d KiB" % (" + AP" if wifi else "", checked // 1024))
                if checked % (128 * 1024) == 0:
                    collect()
        result["bytes"] = checked
        result["sha256"] = binascii.hexlify(digest.digest()).decode()
        result["source_sha256"] = binascii.hexlify(source_digest.digest()).decode()
        if (copied != expected["bytes"] or checked != expected["bytes"] or
                result["sha256"] != expected["sha256"] or
                result["source_sha256"] != expected["sha256"]):
            raise ValueError("SD load content mismatch")
        if wifi:
            if not ap.active():
                raise ValueError("AP stopped during SD load")
            result["ap_active_after_io"] = True
        collect()
        result.update({"total_ms": time.ticks_diff(time.ticks_ms(), started),
                       "heap_free": gc.mem_free(), "heap_min_after_gc": heap_min,
                       "gc_collections": collections, "timer_iterations": refreshes})
        import esp32
        import lcd_bus
        # Sample before radio teardown, while scanout and AP are still active.
        result["internal_dma_heap"] = esp32.idf_heap_info(lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
        refresh("SD load cycle verified")
    except Exception:
        refresh("SD load FAILED | serial evidence retained")
        raise
    finally:
        # Restore only interfaces this probe activated; credentials stay off disk.
        if station is not None:
            try:
                station.active(False)
            finally:
                ap.active(False)
            result["wifi_stopped"] = not station.active() and not ap.active()
        os.sync()
    return result
