import gc
import os
import sys

try:
    import machine
except ImportError:
    machine = None

from .state import BOOT_STATE_FILE, commit_pending_update, get_update_state, read_json, write_json


def _safe_call(obj, name):
    try:
        return getattr(obj, name)()
    except Exception:
        return None


def ensure_boot_started():
    state = read_json(BOOT_STATE_FILE, {})
    if state.get("health") != "starting":
        state["sequence"] = state.get("sequence", 0) + 1
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["health"] = "starting"
        write_json(BOOT_STATE_FILE, state)
    return state


def diagnostics():
    state = ensure_boot_started()
    update = get_update_state()
    data = {
        "event": "boot_diagnostics",
        "sequence": state.get("sequence", 0),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "implementation": getattr(sys, "implementation", ("unknown",))[0],
        "runtime": sys.version,
        "heap_free": _safe_call(gc, "mem_free"),
        "heap_alloc": _safe_call(gc, "mem_alloc"),
        "update_status": update.get("status") if isinstance(update, dict) else "none",
    }
    try:
        uname = os.uname()
        data["firmware_release"] = uname.release
        data["machine"] = uname.machine
    except Exception:
        pass
    if machine is not None:
        data["reset_cause"] = _safe_call(machine, "reset_cause")
        data["wake_reason"] = _safe_call(machine, "wake_reason")
    try:
        stats = os.statvfs("/")
        data["filesystem_total"] = stats[0] * stats[2]
        data["filesystem_free"] = stats[0] * stats[3]
    except Exception:
        pass
    try:
        import esp32
        data["esp32_data_heaps"] = esp32.idf_heap_info(esp32.HEAP_DATA)
    except Exception:
        pass
    return data


def mark_boot_healthy(mode):
    state = ensure_boot_started()
    state["health"] = "healthy"
    state["mode"] = mode
    state["consecutive_failures"] = 0
    state.pop("error", None)
    write_json(BOOT_STATE_FILE, state)
    return commit_pending_update()


def mark_boot_failed(message):
    state = ensure_boot_started()
    state["health"] = "failed"
    state["error"] = str(message)[:160]
    write_json(BOOT_STATE_FILE, state)
