"""Non-formatting SD bench checks; called by tools/sd_bringup.py over raw REPL."""

import binascii
import hashlib
import json
import os
import struct
import time
import vfs

from external_root import activate, open_sd
from hdwconfig import BOARD_CONFIG


def digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": binascii.hexlify(digest.digest()).decode()}


def inventory(card):
    sector = bytearray(512)
    card.readblocks(0, sector)
    partitions = []
    if sector[510:] == b"\x55\xaa":
        for offset in range(446, 510, 16):
            kind = sector[offset + 4]
            start, count = struct.unpack_from("<II", sector, offset + 8)
            if kind and count:
                partitions.append({"type": kind, "start_sector": start, "sectors": count})
    return {"sectors": card.ioctl(4, 0), "sector_bytes": card.ioctl(5, 0),
            "partitions": partitions, "frequency_hz": BOARD_CONFIG["storage"]["frequency"],
            "board_id": BOARD_CONFIG["id"]}


def write_files(directory, sizes):
    # Refuse collisions. A partially written session must be inspected, not erased.
    os.mkdir(directory)
    results = {}
    for size in sizes:
        path = directory + "/%d.bin" % size
        block = bytearray(bytes(range(256)) * 16)
        started = time.ticks_ms()
        with open(path, "wb") as stream:
            for offset in range(0, size, len(block)):
                struct.pack_into("<I", block, 0, offset // len(block))
                chunk = memoryview(block)[:min(len(block), size - offset)]
                if stream.write(chunk) != len(chunk):
                    raise OSError("short write")
        os.sync()
        elapsed = time.ticks_diff(time.ticks_ms(), started)
        result = digest_file(path)
        result["write_sync_ms"] = elapsed
        results[str(size)] = result
    return results


def verify_files(directory, sizes):
    results = {}
    for size in sizes:
        started = time.ticks_ms()
        result = digest_file(directory + "/%d.bin" % size)
        result["read_hash_ms"] = time.ticks_diff(time.ticks_ms(), started)
        results[str(size)] = result
    return results


def run(action, name, sizes):
    if any(path != "/" for _, path in vfs.mount()):
        raise ValueError("run from internal root with no other mounts")
    card = open_sd(BOARD_CONFIG)
    mounted = False
    switched = False
    original = next(fs for fs, path in vfs.mount() if path == "/")
    relative = "/.tartlab-bench-" + name
    try:
        result = inventory(card)
        if action == "root":
            activate(card, required=(relative + "/1048576.bin",))
            switched = True
            result["files"] = verify_files(relative, sizes)
            result["internal_main"] = digest_file("/flash/main.py")
            result["mounts"] = [(repr(fs), path) for fs, path in vfs.mount()]
        else:
            vfs.mount(vfs.VfsFat(card), "/sd", readonly=action != "write")
            mounted = True
            result["statvfs"] = os.statvfs("/sd")
            if action == "inspect":
                result["entries"] = list(os.ilistdir("/sd"))
            elif action == "write":
                result["files"] = write_files("/sd" + relative, sizes)
            elif action == "verify":
                result["files"] = verify_files("/sd" + relative, sizes)
            else:
                raise ValueError("unknown action")
        return result
    finally:
        if switched:
            os.sync()
            os.chdir("/")
            vfs.umount("/")
            vfs.umount("/flash")
            vfs.mount(original, "/")
            os.chdir("/")
        if mounted:
            vfs.umount("/sd")
        card.deinit()
