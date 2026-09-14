"""SD-root bench boot gate. The packaged TartLab boot gate is retained separately."""

import json
import os
import sys

with open("/device/board.json") as stream:
    identity = json.load(stream)
board_id = identity["board_id"]
if not board_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in board_id):
    raise ValueError("invalid SD board identity")
for path in reversed(("/device", "/board/" + board_id, "/lib", "/", "/files/user")):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
import hdwconfig
if hdwconfig.BOARD_CONFIG["id"] != board_id:
    raise ValueError("SD selector does not match identity")

counter_path = "/.tartlab-bench/startup.json"
try:
    with open(counter_path) as stream:
        bench_counts = json.load(stream)
except OSError:
    bench_counts = {"boot": 0, "main": 0}
bench_counts["boot"] += 1
with open(counter_path, "w") as stream:
    json.dump(bench_counts, stream)
os.sync()
print("SD_BENCH_BOOT=" + json.dumps(bench_counts))
