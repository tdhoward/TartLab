"""Read-only native SD lifecycle regression; run at internal root after raw reset.

Bypasses the Python card cache deliberately to exercise native deinit/finalizers.
All wiring comes from the selected declarative board payload.
"""

import binascii
import gc
import hashlib
import json
import vfs
from machine import SPI, SDCard
from hdwconfig import BOARD_CONFIG


def sd_native_lifecycle(cycles):
    if [path for _, path in vfs.mount()] != ["/"]:
        raise ValueError("native lifecycle probe requires the internal root only")
    pins = {entry["type"]: entry["number"] for entry in BOARD_CONFIG["pins"]}
    config = BOARD_CONFIG["storage"]
    options = {"host": config["host"], "sck": pins["SD_SCK"],
               "mosi": pins["SD_MOSI"], "miso": pins["SD_MISO"]}
    bus = SPI.Bus(**options)
    expected = None
    checks = 0
    closed_checks = 0
    sector = bytearray(512)
    card = old = None
    try:
        for index in range(cycles):
            old = SDCard(spi_bus=bus, cs=pins["SD_CS"], freq=config["frequency"])
            if old.ioctl(1, 0) != 0 or not old.readblocks(0, sector):
                raise OSError("initial native card read failed")
            digest = binascii.hexlify(hashlib.sha256(sector).digest()).decode()
            if expected is None:
                expected = digest
            if digest != expected:
                raise ValueError("sector changed across native opens")
            checks += 1
            old.deinit()
            if old.ioctl(1, 0) != -1 or old.readblocks(0, sector) is not False:
                raise ValueError("closed native card remained usable")
            closed_checks += 1
            card = SDCard(spi_bus=bus, cs=pins["SD_CS"], freq=config["frequency"])
            if card.ioctl(1, 0) != 0:
                raise OSError("reopened native card init failed")
            # Reproduce the old finalizer removing a newly reused native slot.
            old.deinit()
            old = None
            gc.collect()
            if not card.readblocks(0, sector):
                raise OSError("reopened card failed after old finalizer/GC")
            if binascii.hexlify(hashlib.sha256(sector).digest()).decode() != expected:
                raise ValueError("reopened sector hash mismatch")
            checks += 1
            card.deinit()
            card.deinit()
            card = None
            bus = None
            gc.collect()
            bus = SPI.Bus(**options)
        gc.collect()
        return {"board_id": BOARD_CONFIG["id"], "cycles": cycles,
                "read_checks": checks, "closed_guard_checks": closed_checks,
                "sector_sha256": expected, "heap_free": gc.mem_free(),
                "native_cache_bypassed": True}
    finally:
        if old is not None:
            old.deinit()
        if card is not None:
            card.deinit()
