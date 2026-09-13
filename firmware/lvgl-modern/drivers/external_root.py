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
    """Keep the custom SPI bus alive for as long as its native SD device."""

    def __init__(self, bus, card):
        self.bus = bus
        self.card = card

    def readblocks(self, block, buffer):
        return self.card.readblocks(block, buffer)

    def writeblocks(self, block, buffer):
        return self.card.writeblocks(block, buffer)

    def ioctl(self, operation, argument):
        return self.card.ioctl(operation, argument)

    def deinit(self):
        if self.card is not None:
            self.card.deinit()
            self.card = None


def open_sd(board):
    """Open an initialized card using the pinned LVGL fork's SPI bus API."""
    from machine import SPI, SDCard
    pins = {pin["type"]: pin["number"] for pin in board["pins"]}
    config = board["storage"]
    host = config["host"]
    wiring = (pins["SD_SCK"], pins["SD_MOSI"], pins["SD_MISO"])
    cached = _sd_buses.get(host)
    if cached is None:
        bus = SPI.Bus(host=host, sck=wiring[0], mosi=wiring[1], miso=wiring[2])
        # The fork keeps a native bus registry. Retain the Python object even
        # after missing-card cleanup so retries cannot reuse a collected bus.
        _sd_buses[host] = (wiring, bus)
    else:
        if cached[0] != wiring:
            raise ValueError("SD SPI bus wiring changed; hard reset required")
        bus = cached[1]
    card = _OwnedCard(bus, SDCard(spi_bus=bus, cs=pins["SD_CS"], freq=config["frequency"]))
    try:
        if card.ioctl(1, 0) != 0:
            raise OSError("SD card initialization failed (absent or unreadable)")
    except Exception:
        card.deinit()
        raise
    return card
