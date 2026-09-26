"""SD-root diagnostic, not TartLab's normal main or a qualification result."""

import gc
import json
import os
import sys
import vfs

with open("/.tartlab-bench/startup.json") as stream:
    bench_counts = json.load(stream)
bench_counts["main"] += 1
with open("/.tartlab-bench/startup.json", "w") as stream:
    json.dump(bench_counts, stream)
os.sync()
assert bench_counts["boot"] == bench_counts["main"], "boot/main count mismatch"

import hdwconfig
import tartlabutils
from tartlabutils.platform import board_runtime_path

tartlabutils.ensure_layout()
for path in ("/state/sd-bench.json", "/files/user/sd-bench.txt"):
    with open(path, "w") as stream:
        stream.write(json.dumps(bench_counts))
os.sync()
report = {
    "fixture": "SD-root diagnostic; normal TartLab startup pending RGB integration",
    "counts": bench_counts,
    "mounts": [(repr(fs), path) for fs, path in vfs.mount()],
    "selector": hdwconfig.__file__,
    "library": tartlabutils.__file__,
    "board_runtime": board_runtime_path(),
    "assets": len(os.listdir("/files/assets")),
    "help": len(os.listdir("/files/help")),
    "internal_main_bytes": os.stat("/flash/main.py")[6],
    "statvfs": os.statvfs("/"),
}
gc.collect()
report["heap_free_before_display"] = gc.mem_free()
with open("/.tartlab-bench/startup-result.json", "w") as stream:
    json.dump(report, stream)
os.sync()
print("SD_BENCH_MAIN=" + json.dumps(report))
# Use the same measured RGB fixture and board configuration as the internal
# experiment. Its visual result stays pending until observed by the operator.
with open("/.tartlab-bench/rgb_smoke.py") as stream:
    exec(stream.read(), globals())
status.set_text("SD root OK | TartLab runtime integration pending")
lv.timer_handler()
print("SD_BENCH_READY")
