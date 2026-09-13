"""Exercise root switching with a RAM FAT volume, never format an SD card."""

import os
import json
import vfs
from external_root import activate


class RamDisk:
    def __init__(self):
        self.data = bytearray(256 * 1024)

    def readblocks(self, block, buffer):
        buffer[:] = self.data[block * 512:block * 512 + len(buffer)]

    def writeblocks(self, block, buffer):
        self.data[block * 512:block * 512 + len(buffer)] = buffer

    def ioctl(self, operation, argument):
        if operation == 4:
            return len(self.data) // 512
        if operation == 5:
            return 512
        return 0


original = next(fs for fs, path in vfs.mount() if path == "/")
ram = RamDisk()
vfs.VfsFat.mkfs(ram)
volume = vfs.VfsFat(ram)
vfs.mount(volume, "/ram")
with open("/ram/main.py", "w") as stream:
    stream.write("# RAM-only fixture\n")
vfs.umount("/ram")
try:
    activate(ram, required=("main.py",))
    with open("/main.py") as stream:
        assert stream.read() == "# RAM-only fixture\n"
    assert os.stat("/flash/hdwconfig.py")[6] > 0
    print("VFS_ROOT_PROBE=" + json.dumps({"ram_root_read": True, "internal_visible": True, "sd_tested": False}))
finally:
    for fs, path in vfs.mount():
        if path == "/" and fs is not original:
            vfs.umount("/")
    if any(path == "/flash" for _, path in vfs.mount()):
        vfs.umount("/flash")
    if not any(path == "/" for _, path in vfs.mount()):
        vfs.mount(original, "/")
    os.chdir("/")
assert next(fs for fs, path in vfs.mount() if path == "/") is original
print("INTERNAL_ROOT_RESTORED=True")
