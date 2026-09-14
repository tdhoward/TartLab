"""Experimental removable root filesystem activation; independent of apps."""

import os
import vfs

_sd_buses = {}


def activate(block_device, required=(), staging="/sd", internal="/flash"):
    """Validate a volume, move the existing root aside, then mount it at /.

    Never formats media. Validation failures leave the existing root mounted.
    The caller owns block-device cleanup if activation raises an exception.
    """
    mounts = vfs.mount()
    roots = [fs for fs, path in mounts if path == "/"]
    if len(roots) != 1 or any(path in (staging, internal) for _, path in mounts):
        raise ValueError("expected one root and unused staging/internal mounts")
    if staging == internal or staging == "/" or internal == "/":
        raise ValueError("mount paths must be distinct")
    original = roots[0]
    volume = vfs.VfsFat(block_device)
    vfs.mount(volume, staging)
    try:
        for path in required:
            mode = os.stat(staging + "/" + path.lstrip("/"))[0]
            if not mode & 0x8000:
                raise ValueError("required file is not regular: " + path)
    finally:
        vfs.umount(staging)
    os.chdir("/")
    vfs.umount("/")
    moved = False
    active = False
    try:
        vfs.mount(original, internal)
        moved = True
        vfs.mount(volume, "/")
        active = True
        os.chdir("/")
    except Exception:
        if active:
            vfs.umount("/")
        if moved:
            vfs.umount(internal)
        vfs.mount(original, "/")
        os.chdir("/")
        raise
    return volume


class _OwnedCard:
    """One active lease on a boot-lifetime native card and SPI bus."""

    def __init__(self, entry):
        self.entry = entry
        self.bus = entry["bus"]
        self.card = entry["card"]

    def _check_open(self):
        if self.card is None:
            raise OSError("SD card is closed")

    def readblocks(self, block, buffer):
        self._check_open()
        return self.card.readblocks(block, buffer)

    def writeblocks(self, block, buffer):
        self._check_open()
        return self.card.writeblocks(block, buffer)

    def ioctl(self, operation, argument):
        self._check_open()
        return self.card.ioctl(operation, argument)

    def deinit(self):
        if self.card is not None:
            # Release card initialization, but retain the native SPI device.
            # The pinned fork's deinit/finalizer can remove a reused slot twice.
            # Its native card and bus therefore stay cached until hard reset.
            if self.card.ioctl(2, 0) != 0:
                raise OSError("SD card deinitialization failed")
            self.card = None
            self.entry["active"] = False


def open_sd(board):
    """Open an initialized card using the pinned LVGL fork's SPI bus API."""
    from machine import SPI, SDCard
    pins = {pin["type"]: pin["number"] for pin in board["pins"]}
    config = board["storage"]
    host = config["host"]
    wiring = (pins["SD_SCK"], pins["SD_MOSI"], pins["SD_MISO"],
              pins["SD_CS"], config["frequency"])
    cached = _sd_buses.get(host)
    if cached is None:
        bus = SPI.Bus(host=host, sck=wiring[0], mosi=wiring[1], miso=wiring[2])
        cached = {"wiring": wiring, "bus": bus, "card": None, "active": False}
        _sd_buses[host] = cached
    else:
        if cached["wiring"] != wiring:
            raise ValueError("SD SPI configuration changed; hard reset required")
    if cached["active"]:
        raise ValueError("SD card already open")
    if cached["card"] is None:
        cached["card"] = SDCard(spi_bus=cached["bus"], cs=wiring[3], freq=wiring[4])
    card = _OwnedCard(cached)
    cached["active"] = True
    try:
        if card.ioctl(1, 0) != 0:
            raise OSError("SD card initialization failed (absent or unreadable)")
    except Exception:
        card.deinit()
        raise
    return card
