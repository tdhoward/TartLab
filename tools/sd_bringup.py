"""Non-formatting SD checks with host-derived hashes and persistent evidence.

Start with inspect, then write, reset, verify, and root. After installing and
booting the SD diagnostic, status checks startup and file hashes; soft-reset
checks exact boot/main counts; soak runs bounded RGB/storage cycles, optionally
with AP lifecycle and Wi-Fi scans. Keep --session pointing to the original
successful write session. Soak retains each output and saves progress per cycle.
The older load action replaces only its designated diagnostic output.
COM ports and wiring are not built in.
The touch action inspects bus health and controller identity without SD or
controller register writes; physical input remains an operator check.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import time
import uuid

from phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
SIZES = (0, 511, 513, 8193, 1048576)


def expected_file(size):
    digest = hashlib.sha256()
    block = bytearray(bytes(range(256)) * 16)
    for offset in range(0, size, len(block)):
        struct.pack_into("<I", block, 0, offset // len(block))
        digest.update(block[:min(len(block), size - offset)])
    return {"bytes": size, "sha256": digest.hexdigest()}


def validate_files(actual, expected):
    if set(actual) != set(expected):
        raise ValueError("device file coverage differs from host expectations")
    for path, wanted in expected.items():
        if any(actual[path].get(key) != wanted[key] for key in ("bytes", "sha256")):
            raise ValueError("device/host content mismatch for " + path)


def validate_runtime(state, previous=None):
    mounts = {path: kind for kind, path in state["mounts"]}
    if set(mounts) != {"/", "/flash"} or mounts["/"] != "<VfsFat>":
        raise ValueError("SD root is not active")
    counts = state.get("counts", {})
    if (set(counts) != {"boot", "main"} or
            any(type(value) is not int or value < 1 for value in counts.values()) or
            counts["boot"] != counts["main"] or
            counts != state.get("state") or counts != state.get("user_file")):
        raise ValueError("boot/main or persisted counters differ")
    if (state.get("selector") != "/device/hdwconfig.py" or
            state.get("library") != "/lib/tartlabutils/__init__.py" or
            state.get("board_runtime") != "/board/" + state["board_id"] or
            state.get("internal_main_bytes", 0) <= 0):
        raise ValueError("selector, library, board or rescue path is incorrect")
    if previous is not None:
        if state["board_id"] != previous["board_id"]:
            raise ValueError("board changed across reset")
        if counts != {key: value + 1 for key, value in previous["counts"].items()}:
            raise ValueError("boot/main did not run exactly once after reset")
        if state["reset_cause"] != state["soft_reset_cause"]:
            raise ValueError("soft reset unexpectedly became a hard reset")


def validate_soak_resume(prior, session, state):
    remote = prior.get("output_directory", "")
    if (prior.get("action") != "soak" or prior.get("session") != session or
            prior.get("before", {}).get("board_id") != state["board_id"] or
            not re.fullmatch(r"/\.tartlab-bench/soak-[0-9a-f]{32}", remote)):
        raise ValueError("resume journal does not match this SD bench")
    cycles = prior.get("cycles", [])
    requested = prior.get("requested_cycles")
    if type(requested) is not int or not 1 <= requested <= 100 or len(cycles) > requested:
        raise ValueError("invalid resume cycle coverage")
    paths = [entry["path"] for entry in cycles]
    if len(set(paths)) != len(paths) or any(
            not re.fullmatch(re.escape(remote) + r"/[0-9a-f-]+\.bin", path) for path in paths):
        raise ValueError("invalid resume output paths")
    validate_files({entry["path"]: entry for entry in cycles},
                   {path: expected_file(1048576) for path in paths})


def capture_reset(repl, soft, log, timeout=75):
    """Capture complete startup or the returned rescue prompt, even on failure."""
    repl.exec("import os; os.sync()")
    if soft:
        repl.serial.write(b"\x02")
        repl._read_until(b">>> ")
        repl.serial.write(b"\x04")
    else:
        repl.serial.write(b"import machine; machine.reset()\x04")
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            output.extend(repl.serial.read(repl.serial.in_waiting or 1))
            if b">>> " in output:
                break
    finally:
        log.write_bytes(output)
    failures = (b"Traceback", b"Guru Meditation", b"panic'ed", b"A fatal error",
                b"abort() was called", b"Brownout", b"Task watchdog")
    # A panic can reboot into a healthy diagnostic within the capture window.
    # Preserve that log, but never count the recovery as the requested startup.
    return (output.count(b"SD_BENCH_READY") == 1 and b">>> " in output and
            not any(marker in output for marker in failures) and
            (not soft or (b"MPY: soft reboot" in output and b"ESP-ROM:" not in output)))


def runtime_checks(repl, args, destination, result):
    probe = (ROOT / "tools/device/sd_runtime_probe.py").read_text(encoding="utf-8")

    def status(label):
        output = repl.exec(probe + "\nprint(json.dumps(sd_runtime_status()))")
        destination.with_name(destination.stem + "-" + label + ".log").write_bytes(output)
        return json.loads(output.decode())

    result["before"] = status("before")
    validate_runtime(result["before"])
    if args.action == "soft-reset":
        result["cycles"] = []
        previous = result["before"]
        for index in range(args.cycles):
            ready = capture_reset(repl, True, destination.with_name(
                destination.stem + "-%02d-startup.log" % (index + 1)))
            repl.enter()
            current = status("%02d-after" % (index + 1))
            result["cycles"].append({"startup_ready": ready, "state": current})
            validate_runtime(current, previous)
            if not ready:
                raise ValueError("SD diagnostic did not complete after soft reset")
            previous = current
        return

    if args.action == "soak":
        invocation_state = result["before"]
        if args.resume:
            prior = json.loads(args.resume.read_text(encoding="utf-8"))
            validate_soak_resume(prior, args.session.name, invocation_state)
            # Recheck retained outputs to bind resumption to the actual media.
            paths = [entry["path"] for entry in prior["cycles"]]
            output = repl.exec("print(json.dumps(sd_runtime_hashes(%r)))" % paths, timeout=240)
            validate_files(json.loads(output.decode()), {path: expected_file(1048576) for path in paths})
            result.update(prior)
            result["port"] = args.port
            result["resumed_from"] = str(args.resume)
            result["pass"] = False
            result.setdefault("resumptions", []).append({"state": invocation_state,
                                                         "previous_error": result.pop("error", None)})
            args.cycles = result["requested_cycles"]
            args.wifi = result.get("wifi_radio", bool(result["cycles"] and result["cycles"][0]["wifi_radio"]))
            remote = result["output_directory"]
            repl.exec("os.stat(%r)" % remote)
        else:
            remote = "/.tartlab-bench/soak-" + uuid.uuid4().hex
            result.update({"output_directory": remote, "cycles": [],
                           "requested_cycles": args.cycles, "wifi_radio": args.wifi})
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            repl.exec("os.mkdir(%r)\nos.sync()" % remote)
        # Persist before touching the card so interrupted attempts remain locatable.
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        repl.exec((ROOT / "tools/device/sd_runtime_load.py").read_text(encoding="utf-8"))
        wifi = {"ssid": "TartLab-SD-" + uuid.uuid4().hex[:8],
                "password": uuid.uuid4().hex} if args.wifi else None
        expected = expected_file(1048576)
        for index in range(len(result["cycles"]), args.cycles):
            path = remote + "/%02d-%s.bin" % (index + 1, uuid.uuid4().hex[:8])
            result.setdefault("attempted_outputs", []).append(path)
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            output = repl.exec("print(json.dumps(sd_runtime_load(%r, %r, %r, %r)))" % (
                "/.tartlab-bench-" + args.session.name + "/1048576.bin", path, expected, wifi),
                timeout=120)
            destination.with_name(destination.stem + "-%02d.log" % (index + 1)).write_bytes(output)
            current = json.loads(output.decode())
            validate_files({path: current}, {path: expected})
            if args.wifi and not all(current.get(key) is True for key in (
                    "ap_active", "ap_active_after_io", "wifi_stopped")):
                raise ValueError("AP lifecycle check failed")
            result["cycles"].append({"path": path, **current})
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("SD_SOAK %d/%d verified" % (index + 1, args.cycles), flush=True)
        # Drop the host reference to this run's ephemeral credentials.
        wifi = None
        result["after"] = status("after")
        validate_runtime(result["after"])
        if invocation_state["counts"] != result["after"]["counts"]:
            raise ValueError("unexpected restart during SD load")
        repl.exec("status.set_text('SD soak verified | visual check pending'); lv.timer_handler()")
        return

    expected = {"/.tartlab-bench-" + args.session.name + "/%d.bin" % size: expected_file(size)
                for size in SIZES}
    if args.inventory:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        if inventory["board"] != result["before"]["board_id"] or not inventory["complete"]:
            raise ValueError("staging inventory is incomplete or belongs to another board")
        expected.update({"/" + path: entry for path, entry in inventory["inventory"].items()})
    if args.load_evidence:
        evidence = json.loads(args.load_evidence.read_text(encoding="utf-8"))
        if (evidence.get("action") != "soak" or evidence.get("pass") is not True or
                evidence["before"]["board_id"] != result["before"]["board_id"] or
                len(evidence["cycles"]) != evidence["requested_cycles"]):
            raise ValueError("load evidence is incomplete or belongs to another board")
        expected.update({entry["path"]: expected_file(1048576) for entry in evidence["cycles"]})
    output = repl.exec("print(json.dumps(sd_runtime_hashes(%r)))" % list(expected), timeout=240)
    destination.with_suffix(".log").write_bytes(output)
    result["files"] = json.loads(output.decode())
    validate_files(result["files"], expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "write", "verify", "root", "reset", "load",
                                         "status", "soft-reset", "soak", "native-lifecycle", "touch"))
    parser.add_argument("--port", required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=8, help="soft-reset/soak cycles (default: 8)")
    parser.add_argument("--wifi", action="store_true", help="soak: AP lifecycle and station scans")
    parser.add_argument("--inventory", type=Path, help="status: verify an sd-stage.json inventory")
    parser.add_argument("--load-evidence", type=Path, help="status: also verify a completed soak's files")
    parser.add_argument("--resume", type=Path, help="soak: continue an existing journal, preserving partial files")
    args = parser.parse_args()
    if not 1 <= args.cycles <= 100:
        parser.error("cycles must be between 1 and 100")
    if args.resume and args.action != "soak":
        parser.error("--resume is only available for soak")
    name = args.session.name
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
        parser.error("session name must be 1-64 letters, digits, underscores or hyphens")
    args.session.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    destination = args.session / (stamp + "-" + args.action + ".json")
    if args.resume:
        # Validate the journal before opening the device or overwriting evidence.
        prior = json.loads(args.resume.read_text(encoding="utf-8"))
        validate_soak_resume(prior, name, prior.get("before", {}))
    observations = args.session / "operator-observations.json"
    if not observations.exists():
        observations.write_text(json.dumps({
            "cold_boot_persistence": None,
            "display_alignment_during_sd_io": None,
            "display_flicker_during_sd_io": None,
            "notes": "Record physical observations only; serial checks do not imply a visual pass."
        }, indent=2) + "\n", encoding="utf-8")
    result = dict(prior) if args.resume else {}
    result.update({"action": args.action, "session": name, "port": args.port, "pass": False})
    if args.resume:
        result["resumed_from"] = str(args.resume)
    repl = None
    try:
        repl = RawRepl(args.port, timeout=20)
        repl.enter()
        if args.action in ("status", "soft-reset", "soak"):
            runtime_checks(repl, args, destination, result)
            result["pass"] = True
        elif args.action == "reset":
            result["pass"] = None  # Request/capture only; verify persistence separately.
            result["startup_ready"] = capture_reset(repl, False, destination.with_suffix(".log"))
            result["reset_requested"] = True
        else:
            prefix = "SD_RESULT="
            if args.action == "touch":
                prefix = "TOUCH_BUS_PROBE="
                command = (ROOT / "tools/device/touch_bus_probe.py").read_text(encoding="utf-8")
                command += ("\nimport json\nfrom hdwconfig import BOARD_CONFIG\n"
                            "print(%r + json.dumps(touch_bus_probe(BOARD_CONFIG)))" % prefix)
            elif args.action == "native-lifecycle":
                prefix = "SD_NATIVE_LIFECYCLE="
                command = (ROOT / "tools/device/sd_native_lifecycle.py").read_text(encoding="utf-8")
                command += "\nprint(%r + json.dumps(sd_native_lifecycle(%d)))" % (prefix, args.cycles)
            elif args.action == "load":
                prefix = "SD_DISPLAY_LOAD="
                command = "SD_LOAD_SOURCE=%r\nSD_LOAD_SHA256=%r\n" % (
                    "/.tartlab-bench-" + name + "/1048576.bin", expected_file(1048576)["sha256"])
                command += (ROOT / "tools/device/sd_display_load.py").read_text(encoding="utf-8")
            else:
                source = (ROOT / "tools/device/sd_storage_probe.py").read_text(encoding="utf-8")
                command = source + ("\ntry:\n print('SD_RESULT=' + json.dumps(run(%r, %r, %r)))\n"
                                    "except Exception as error:\n import sys\n sys.print_exception(error)\n"
                                    " print('SD_RESULT=' + json.dumps({'error':repr(error)}))\n") % (
                                        args.action, name, SIZES)
            output = repl.exec(command, timeout=90)
            destination.with_suffix(".log").write_bytes(output)
            line = next(line for line in output.decode().splitlines() if line.startswith(prefix))
            result["device"] = json.loads(line.split("=", 1)[1])
            if "error" in result["device"]:
                raise RuntimeError(result["device"]["error"])
            if args.action == "native-lifecycle":
                for key, expected in (("cycles", args.cycles), ("read_checks", 2 * args.cycles),
                                      ("closed_guard_checks", args.cycles)):
                    if result["device"].get(key) != expected:
                        raise ValueError("incomplete native lifecycle coverage: " + key)
            if args.action == "load":
                expected = expected_file(1048576)
                if any(result["device"][key] != value for key, value in expected.items()):
                    raise ValueError("SD display load content mismatch")
            if args.action in ("write", "verify", "root"):
                validate_files(result["device"].get("files", {}),
                               {str(size): expected_file(size) for size in SIZES})
            result["pass"] = True
    except Exception as error:
        result["error"] = str(error)
        print("SD_ERROR " + str(error))
    finally:
        if repl is not None:
            repl.close()
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"action": args.action, "pass": result["pass"], "evidence": str(destination)}))
    return 1 if result["pass"] is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
