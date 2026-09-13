"""Measure the editable game on modern firmware and retain resumable evidence.

run stages only probe-owned files under /_grid_puzzle_benchmark. It never
flashes firmware or edits student files. status validates the operator form;
unperformed physical checks remain pending. A soft reset restores normal startup
after serial work. This development measurement is not release qualification.
"""

from __future__ import annotations

import argparse
import base64
import configparser
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

try:
    from phase1_device import RawRepl
except ImportError:
    from tools.phase1_device import RawRepl

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/_grid_puzzle_benchmark"
ENGINE = ROOT / "src/files/help/grid_puzzle.py"
ASSET = ROOT / "src/files/assets/grid_puzzle.ts16"
CHECKS = {
    "room_art": "Whole room readable; water edges, snake/spider headings, growing/stopped spears and blasts understandable.",
    "controls": "All four directions, held repeat and release work; Pause, hints, Reset and Back require fresh gestures.",
    "debug": "DBG shows grid, hidden wall outlines, labelled twin pairs, headings/follow, trails, next moves and ray blockers; paused cell pages and Step work.",
    "hidden": "Normal false walls match walls and pads are hidden; debug off removes every overlay.",
    "copies": "Open Help Python/JSON, save renamed user copies, reopen both; JSON has Save but no Run/Set as App.",
    "edits": "Run a changed rule from a renamed Python copy and independently edited JSON; save/rerun executes each saved change.",
    "recovery": "Recover syntax/runtime error and blocked loop using documented IDE/interrupt/reset route; restore code and rooms independently from Help.",
    "startup": "IDE Run and selected-app startup launch the renamed copy with its explicit JSON path.",
    "restarts": "Repeated room changes, death/restart and pause retain usable controls and art; Back restores UI.",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def workloads():
    """Fixed complete matrix, including room-size adversarial occupancy.

    The spear case seeds already-triggered traps so long simultaneous shafts
    remain measurable without an intentional player death ending the workload.
    Water is static in the app; no water animation is claimed.
    """
    levels = []
    for path in ("src/files/help/grid_puzzle_levels.json", "tests/fixtures/grid_puzzle/hazards.json"):
        levels.extend(json.loads((ROOT / path).read_bytes())["levels"])

    def add(name, rows, **extra):
        levels.append({"name": name, "map": [" ".join(row) for row in rows], **extra})

    rows = [["Xe" if (x + y) % 2 else ".." for x in range(16)] for y in range(12)]
    rows[0] = ["P."] + ["#0"] * 15
    rows[1] = ["#0"] * 16
    rows[11][15] = "E."
    add("Stress moving spiders", rows)
    rows = [["Xe"] * 16 for unused in range(12)]
    rows[0][0], rows[11][15] = "P.", "E."
    add("Stress dense explosions", rows, rules={"explosion_hurts_player": False})
    rows = [[".."] * 16 for unused in range(12)]
    rows[0][0], rows[11][15] = "P.", "E."
    rows[3][0], rows[5][15], rows[0][5], rows[11][10] = "RE", "RW", "RS", "RN"
    add("Stress long spears (triggered)", rows)
    rows = [["W%s" % ((y % 3) * 3 + x % 3) for x in range(16)] for y in range(12)]
    rows[0] = ["P."] + [".."] * 15
    rows[11][15] = "E."
    add("Water variants (static)", rows)
    return {"version": 1, "levels": levels}


SETUP = r'''
import gc, sys, time, json, os, hashlib, binascii
from tartlabutils.platform import get_platform
import tartlabutils.app as app
with open(REMOTE + '/app.py') as f:
    exec(f.read(), app.__dict__)
from tartlabutils.app import DirectCanvas
from tartlabutils.timing import FrameClock
def elapsed(start):
    return time.ticks_diff(time.ticks_us(), start)
def checkpoint(start):
    duration = elapsed(start)
    gc.collect()
    return {'us': duration, 'heap_free': gc.mem_free()}
def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            h.update(chunk)
    return binascii.hexlify(h.digest()).decode()
platform = get_platform()
if not platform.capabilities.get('direct_rgb565'):
    raise ValueError('modern direct canvas required')
gc.collect()
startup = {'before_compile_heap': gc.mem_free()}
started = time.ticks_us()
scope = {'__name__': 'grid_puzzle_probe', '_GRID_PUZZLE_AUTOSTART': False}
with open(REMOTE + '/engine.py') as f:
    source = f.read()
exec(source, scope)
del source
startup['compile'] = checkpoint(started)
scope['ASSET_FILE'] = REMOTE + '/art.ts16'
started = time.ticks_us()
bundled_pack = scope['load_level_pack'](REMOTE + '/bundled.json')
startup['pack'] = checkpoint(started)
pack = scope['load_level_pack'](REMOTE + '/levels.json')
buttons = getattr(platform, 'buttons', None)
layout = scope['choose_layout'](platform.width, platform.height,
    platform.capabilities.get('touch', False), buttons.names if buttons else ())
with open('/device/board.json') as f:
    identity = json.load(f)
runtime_hashes = {}
for name in ('app', 'damage', 'sprites', 'timing', 'platform'):
    runtime_hashes[name] = file_hash('/lib/tartlabutils/' + name + '.py')
print('GRID_SETUP=' + json.dumps({'firmware': sys.version,
    'implementation': repr(sys.implementation), 'board': identity,
    'capabilities': platform.capabilities,
    'layout': {'width': layout.width, 'height': layout.height,
               'rotation': layout.rotation, 'scale': layout.scale,
               'placement': layout.placement},
    'startup': startup, 'runtime_sha256': runtime_hashes,
    'app_override_sha256': file_hash(REMOTE + '/app.py')}))
def summary(values):
    values = sorted(values)
    return {'p50': values[len(values) // 2],
            'p95': values[(len(values) * 95 + 99) // 100 - 1],
            'max': values[-1]}
def seed(session):
    state = session.state
    if state.active_message != -1:
        scope['dismiss_message'](state)
    if state.definition['name'] == 'Stress long spears (triggered)':
        for actor in state.actors:
            if actor.kind == scope['EMITTER']:
                actor.trap_state = scope['EXTENDING']
                actor.next_due_ms = actor.interval_ms
def measure(index, debug, samples, frame_ms):
    canvas = session = renderer = None
    try:
        started = time.ticks_us()
        canvas = DirectCanvas(platform.enter_game_mode(), rotation=layout.rotation,
                             transfer_rows=scope['CANVAS_TRANSFER_ROWS'])
        canvas_start = checkpoint(started)
        session = scope['Session'](pack, index)
        session.art = scope['PuzzleArt'](scope['ASSET_FILE'], layout.scale)
        started = time.ticks_us()
        session.art.prepare(session.state.definition, canvas)
        art_start = checkpoint(started)
        renderer = scope['Renderer'](canvas, layout, debug)
        session.renderer = renderer
        seed(session)
        started = time.ticks_us()
        renderer.present(session)
        first_frame = elapsed(started)
        simulation, drawing, transfer, total, dirty = [], [], [], [], []
        clock = FrameClock(frame_ms, scope['UPDATE_MS'], max_updates=10)
        missed, dropped, transitions = 0, 0, []
        playing_frames, frozen_frames = 0, 0
        for frame in range(samples):
            started = time.ticks_us()
            due = clock.updates_due()
            # Repeat transient scenarios; retain restart cost separately, just
            # as the app excludes transition drawing from elapsed play time.
            if frame and frame % 20 == 0:
                transition_start = time.ticks_us()
                session.restart()
                seed(session)
                renderer.present(session)
                transitions.append(elapsed(transition_start))
                missed += clock.missed_deadlines
                dropped += clock.dropped_update_ms
                clock = FrameClock(frame_ms, scope['UPDATE_MS'], max_updates=10)
                due = 0
                started = time.ticks_us()
            session.direction = scope['EAST'] if frame % 40 < 20 else scope['WEST']
            sim_start = time.ticks_us()
            session.advance(due)
            simulation.append(elapsed(sim_start))
            if session.state.status == scope['PLAYING'] and not session.state.paused:
                playing_frames += 1
            else:
                frozen_frames += 1
            if renderer.inspector is not None:
                renderer.inspector.missed = clock.missed_deadlines
                renderer.inspector.dropped = clock.dropped_update_ms
            renderer.present(session)
            drawing.append(renderer.draw_us)
            transfer.append(renderer.transfer_us)
            dirty.append(renderer.dirty_count)
            total.append(elapsed(started))
            clock.pace()
        # Collect after both warmup and restart batches; release old state via
        # bind so the comparison doesn't retain the preceding room's trails.
        session.restart()
        renderer.bind(session.state)
        gc.collect()
        heap_before = gc.mem_free()
        for unused in range(30):
            session.restart()
            session.art.prepare(session.state.definition, canvas)
            renderer.bind(session.state)
        gc.collect()
        heap_after = gc.mem_free()
        result = {'room': session.state.definition['name'], 'debug': debug,
            'samples': samples, 'frame_ms': frame_ms,
            'playing_frames': playing_frames, 'frozen_frames': frozen_frames,
            'simulation_us': summary(simulation), 'drawing_us': summary(drawing),
            'transfer_us': summary(transfer), 'frame_work_us': summary(total),
            'dirty_cells': summary(dirty), 'first_frame_us': first_frame,
            'missed_deadlines': missed + clock.missed_deadlines,
            'dropped_update_ms': dropped + clock.dropped_update_ms,
            'restart_transition_us': summary(transitions),
            'heap_before_30_restarts': heap_before, 'heap_after_30_restarts': heap_after,
            'canvas_start': canvas_start, 'art_start': art_start}
        return result
    finally:
        try:
            if renderer is not None:
                renderer.close()
            if session is not None and session.art is not None:
                session.art.close()
            if canvas is not None:
                canvas.close()
        finally:
            platform.enter_ui_mode()
'''


def extract(output, marker):
    for line in output.decode("utf-8", "replace").splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    raise ValueError("missing " + marker)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_form(output, binding):
    path = output / "operator.ini"
    if path.exists():
        return
    form = configparser.ConfigParser(interpolation=None)
    form["session"] = {"binding": binding, "observer": "", "observed_at_utc": ""}
    for name, procedure in CHECKS.items():
        form["check:" + name] = {"procedure": procedure, "status": "pending", "notes": ""}
    with path.open("w", encoding="utf-8") as stream:
        form.write(stream)


def status(output):
    report = json.loads((output / "report.json").read_bytes())
    form = configparser.ConfigParser(interpolation=None)
    form.read(output / "operator.ini", encoding="utf-8")
    issues = []
    if form.get("session", "binding", fallback="") != report["binding"]:
        issues.append("operator form is for a different build")
    for field in ("observer", "observed_at_utc"):
        if not form.get("session", field, fallback="").strip():
            issues.append("missing " + field)
    observed = form.get("session", "observed_at_utc", fallback="").strip()
    if observed:
        try:
            parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
                raise ValueError("UTC required")
        except ValueError:
            issues.append("observed_at_utc requires an ISO timestamp with UTC offset")
    for name in CHECKS:
        section = "check:" + name
        result = form.get(section, "status", fallback="missing")
        if result != "passed":
            issues.append(name + ": " + result)
        elif not form.get(section, "notes", fallback="").strip():
            issues.append(name + ": observation notes required")
    print("Measurements: %s/%s; performance: %s" %
          (len(report["results"]), report["expected_results"], report["performance"]))
    for issue in issues:
        print(issue)
    return int(bool(issues) or report["performance"] != "passed")


def performance_status(results, expected, frame_ms):
    if len(results) != expected:
        return "pending"
    normal = [result for result in results.values() if not result["debug"]]
    if len(normal) * 2 != expected:
        return "failed"
    return "passed" if all(result["frame_work_us"]["max"] <= frame_ms * 1000
        and result["dropped_update_ms"] == 0 and result["missed_deadlines"] == 0
        for result in normal) else "failed"


def remote_bytes(repl, path):
    """Read exactly one known payload; never enumerate or display user data."""
    raw = repl.exec("import binascii\ntry:\n f=open(%r,'rb')\n data=f.read()\n f.close()\n print(binascii.b2a_base64(data).decode())\nexcept OSError as e:\n if e.args[0] != 2: raise\n print('MISSING')" % path)
    return None if raw.strip() == b"MISSING" else base64.b64decode(raw.strip(), validate=True)


def merge_manifest(installed):
    manifest = json.loads(installed)
    supplied = json.loads((ROOT / "src/files/help/manifest.json").read_bytes())
    for folder in supplied["folders"]:
        entries = [e for e in folder["entries"] if e["file"].startswith("grid_puzzle")]
        if not entries:
            continue
        target = next((f for f in manifest["folders"] if f["folder name"] == folder["folder name"]), None)
        if target is None:
            target = {"folder name": folder["folder name"], "entries": []}
            manifest["folders"].append(target)
        replacements = {e["file"] for e in entries}
        target["entries"] = entries + [e for e in target["entries"] if e["file"] not in replacements]
    return (json.dumps(manifest, indent=2) + "\n").encode()


def build_ide_payloads(output):
    """Build the JSON editor dependency using the normal distribution pipeline.

    Always build before opening serial: reusing an older bundle can install a
    working game whose companion JSON cannot be opened or saved in the IDE.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import makedist
    import subprocess
    web = ROOT / "src/ide/www"
    log = output / "ide-build.log"
    print("Building IDE assets (log: %s)" % log, flush=True)
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([makedist.npm_executable(), "run", "build"], cwd=web,
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    with tempfile.TemporaryDirectory(prefix="ide-payload-", dir=output) as folder:
        stage = Path(folder)
        makedist.copy_tree(web / "dist", stage, False)
        makedist.compress_large_files(stage, makedist.source_date_epoch())
        return {"/ide/www/" + path.relative_to(stage).as_posix(): path.read_bytes()
                for path in sorted(stage.rglob("*")) if path.is_file()}


def install(args):
    """Install the reviewed development payload, preserving previous bytes."""
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    backups = output / "device-backup"
    backups.mkdir(exist_ok=True)
    payloads = {"/files/help/" + name: (ROOT / "src/files/help" / name).read_bytes()
                for name in ("grid_puzzle.py", "grid_puzzle_levels.json", "grid_puzzle_guide.html")}
    payloads["/files/assets/grid_puzzle.ts16"] = ASSET.read_bytes()
    payloads["/lib/tartlabutils/app.py"] = (ROOT / "src/lib/tartlabutils/app.py").read_bytes()
    payloads.update(build_ide_payloads(output))
    record = {"kind": "development-install", "port": args.port, "files": {},
              "installed_at_utc": datetime.now(timezone.utc).isoformat()}
    repl = RawRepl(args.port, timeout=60)
    try:
        repl.enter()
        manifest = remote_bytes(repl, "/files/help/manifest.json")
        if manifest is None:
            raise ValueError("installed Help manifest is missing")
        payloads["/files/help/manifest.json"] = merge_manifest(manifest)
        for remote, data in payloads.items():
            old = remote_bytes(repl, remote)
            backup = backups / (remote.strip("/").replace("/", "__"))
            if old is not None and not backup.exists():
                backup.write_bytes(old)
            record["files"][remote] = {"sha256": digest(data),
                                       "previous_sha256": digest(old) if old is not None else None}
            if old != data:
                print("Updating %s (%s bytes)" % (remote, len(data)), flush=True)
                staged = remote + ".grid-puzzle-new"
                repl.stream_file(staged, data, digest(data))
                repl.exec("import os\nos.rename(%r,%r)" % (staged, remote))
            print("Installed " + remote, flush=True)
            write_json(output / "install.json", record)
    finally:
        repl.serial.write(b"\r\x02\rimport machine; machine.soft_reset()\r")
        time.sleep(0.2)
        repl.close()
    print("Development payload installed; normal device startup restored.")
    return 0


def run(args):
    try:
        from check_grid_puzzle_levels import load_engine
    except ImportError:
        from tools.check_grid_puzzle_levels import load_engine
    if args.samples < 40 or args.frame_ms not in (50, 60):
        raise ValueError("use at least 40 samples and a fixed 50 or 60 ms frame period")
    pack = workloads()
    load_engine().validate_level_pack(pack)
    payloads = {"engine.py": ENGINE.read_bytes(), "art.ts16": ASSET.read_bytes(),
                "app.py": (ROOT / "src/lib/tartlabutils/app.py").read_bytes(),
                "bundled.json": (ROOT / "src/files/help/grid_puzzle_levels.json").read_bytes(),
                "levels.json": (json.dumps(pack, sort_keys=True) + "\n").encode()}
    inputs = {name: digest(data) for name, data in payloads.items()}
    inputs.update(tool=digest(Path(__file__).read_bytes()), samples=args.samples, frame_ms=args.frame_ms)
    binding = digest(json.dumps(inputs, sort_keys=True).encode())
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "report.json"
    report = {"binding": binding, "inputs": inputs, "results": {},
              "expected_results": len(pack["levels"]) * 2, "performance": "pending"}
    if report_path.exists():
        report = json.loads(report_path.read_bytes())
        if report["binding"] != binding:
            raise ValueError("inputs changed; choose a fresh --output directory")
    make_form(output, binding)
    write_json(report_path, report)
    repl = RawRepl(args.port, timeout=60)
    try:
        repl.enter()
        repl.exec("import os\ntry:\n os.mkdir(%r)\nexcept OSError as e:\n if e.args[0] != 17: raise" % REMOTE)
        for name, data in payloads.items():
            repl.stream_file(REMOTE + "/" + name, data, inputs[name])
        setup = repl.exec("REMOTE = %r\n" % REMOTE + SETUP, 60)
        (output / "setup.log").write_bytes(setup)
        device = extract(setup, "GRID_SETUP=")
        if "device" in report:
            for field in ("firmware", "board", "layout", "runtime_sha256"):
                if report["device"][field] != device[field]:
                    raise ValueError("device changed; choose a fresh --output directory")
        report["device"] = device
        write_json(report_path, report)
        for index, level in enumerate(pack["levels"]):
            for debug in (False, True):
                key = "%02d-%s" % (index, "debug" if debug else "normal")
                if key in report["results"]:
                    continue
                if args.cases and key not in args.cases:
                    continue
                print("Measuring %s: %s" % (key, level["name"]), flush=True)
                raw = repl.exec("print('GRID_RESULT=' + json.dumps(measure(%s, %s, %s, %s)))" %
                                (index, debug, args.samples, args.frame_ms), 60)
                (output / (key + ".log")).write_bytes(raw)
                result = extract(raw, "GRID_RESULT=")
                report["results"][key] = result
                write_json(report_path, report)
                print("  p95 %.1f ms; max %.1f ms; missed %s; dropped %s ms" %
                      (result["frame_work_us"]["p95"] / 1000,
                       result["frame_work_us"]["max"] / 1000,
                       result["missed_deadlines"], result["dropped_update_ms"]), flush=True)
        report["performance"] = performance_status(report["results"], report["expected_results"], args.frame_ms)
        write_json(report_path, report)
    except Exception as error:
        (output / "error.txt").write_text(str(error) + "\n", encoding="utf-8")
        raise
    finally:
        # Send reset without waiting for the non-returning boot program.
        repl.serial.write(b"\r\x02\rimport machine; machine.soft_reset()\r")
        time.sleep(0.2)
        repl.close()
    print("Performance: %s. Physical checks: %s" % (report["performance"], output / "operator.ini"))
    return int(report["performance"] != "passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "install"))
    parser.add_argument("--port", default="COM18")
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--frame-ms", type=int, default=50)
    parser.add_argument("--cases", nargs="+", help="diagnostic subset; omitted cases stay pending")
    parser.add_argument("--output", type=Path, default=ROOT / "build/grid_puzzle/device")
    args = parser.parse_args()
    if args.command == "install":
        return install(args)
    return run(args) if args.command == "run" else status(args.output)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
