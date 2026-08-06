"""Early recovery gate. Keep this independent of TartLab's normal libraries."""

import os
import sys

try:
    import ujson as json
except ImportError:
    import json


STATE_DIR = "/state"
BOOT_STATE = STATE_DIR + "/boot.json"
UPDATE_STATE = STATE_DIR + "/update.json"
RECOVERY_FLAG = STATE_DIR + "/recovery.flag"
FAILURE_LIMIT = 3


def _kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0


def _read(path, default):
    try:
        with open(path, "r") as stream:
            return json.load(stream)
    except Exception:
        return default


def _write(path, value):
    if _kind(STATE_DIR) == 0:
        os.mkdir(STATE_DIR)
    temporary = path + ".tmp"
    if _kind(temporary) == 1:
        os.remove(temporary)
    with open(temporary, "w") as stream:
        json.dump(value, stream)
    if _kind(path) == 1:
        os.remove(path)
    os.rename(temporary, path)


def _start_boot():
    state = _read(BOOT_STATE, {})
    state["sequence"] = state.get("sequence", 0) + 1
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    state["health"] = "starting"
    _write(BOOT_STATE, state)
    return state


def _recovery_reason(boot_state):
    update = _read(UPDATE_STATE, {})
    if update.get("status") in ("installing", "failed"):
        return "update_" + update.get("status")
    if _kind("/tmp/manifest.json") == 1 and not update:
        return "legacy_update_interrupted"
    if _kind(RECOVERY_FLAG) == 1:
        return "recovery_requested"
    if boot_state.get("consecutive_failures", 0) >= FAILURE_LIMIT:
        return "repeated_boot_failure"
    return None


def _run_recovery(reason):
    if "/recovery" not in sys.path:
        sys.path.insert(0, "/recovery")
    try:
        import recovery
        recovery.run(reason)
    except Exception as error:
        print("TartLab recovery failed:", error)


_reason = _recovery_reason(_start_boot())
if _reason:
    _run_recovery(_reason)
