"""Validate the actual editable engine/JSON pair; keep detailed results on disk.

Bundled rooms also replay checked-in timed solutions. Custom room packs without
--solutions receive structural checks only; their solvability remains pending.
An --engine path executes trusted local Python with game autostart disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import types
import traceback


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / "src/files/help/grid_puzzle.py"
DEFAULT_LEVELS = ROOT / "src/files/help/grid_puzzle_levels.json"
DEFAULT_SOLUTIONS = ROOT / "tests/fixtures/grid_puzzle/solutions.json"


def load_engine(path=DEFAULT_ENGINE):
    """Load the maintained source without device mocks or import/bytecode caches."""
    path = Path(path).resolve()
    module = types.ModuleType("grid_puzzle_experiment")
    module._GRID_PUZZLE_AUTOSTART = False
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def replay(engine, definition, recording):
    """Replay timed press/release/wait edges through the actual pure step().

    at_ms is elapsed time before the next quantum. A press replaces the held
    direction. No wall-clock reads or rendering cadence affect this trace.
    """
    engine._fields(recording, ("room", "end_ms", "events", "expected"),
                   ("room", "end_ms", "events", "expected"), "solution")
    end_ms = engine._integer(recording["end_ms"], 10, "solution.end_ms")
    if end_ms % engine.UPDATE_MS:
        raise ValueError("solution.end_ms must align with the simulation quantum")
    events = recording["events"]
    if not isinstance(events, list):
        raise ValueError("solution.events must be an array")
    previous = -1
    for event in events:
        engine._fields(event, ("at_ms", "action", "direction"), ("at_ms", "action"), "event")
        at = engine._integer(event["at_ms"], 0, "event.at_ms", end_ms)
        if at < previous or at % engine.UPDATE_MS:
            raise ValueError("event times must be ordered simulation boundaries")
        previous = at
        if event["action"] == "press":
            if event.get("direction") not in engine.ACTION_DIRECTIONS:
                raise ValueError("press requires a cardinal direction name")
        elif event["action"] not in ("release", "wait") or "direction" in event:
            raise ValueError("expected press/direction, release, or wait event")
    expected = recording["expected"]
    fields = ("status", "score", "bonus", "elapsed_ms")
    engine._fields(expected, fields, fields, "solution.expected")
    if expected["status"] != "completed":
        raise ValueError("a solution must expect completed status")
    for field in fields[1:]:
        engine._integer(expected[field], 0, "solution.expected." + field)
    engine.validate_playable_pack({"levels": (definition,)})
    state, direction, index = engine.create_state(definition), None, 0
    for elapsed in range(0, end_ms, engine.UPDATE_MS):
        while index < len(events) and events[index]["at_ms"] <= elapsed:
            event = events[index]
            if event["action"] == "press":
                direction = engine.ACTION_DIRECTIONS[event["direction"]]
            elif event["action"] == "release":
                direction = None
            index += 1
        engine.step(state, direction)
    actual = {"status": ("playing", "dead", "completed")[state.status],
              "score": state.score, "bonus": state.bonus, "elapsed_ms": state.elapsed_ms}
    if actual != expected:
        raise ValueError("room %s replay mismatch: expected %s; got %s" %
                         (recording["room"], expected, actual))
    return {"room": recording["room"], "status": "passed", "actual": actual,
            "end_ms": end_ms, "events": events}


def check(engine_path=DEFAULT_ENGINE, levels_path=DEFAULT_LEVELS, solutions_path=None):
    engine_path, levels_path = Path(engine_path).resolve(), Path(levels_path).resolve()
    report = {"engine": str(engine_path), "levels": str(levels_path),
              "status": "failed", "scope": "structure",
              "solution_replay": "pending: no solutions supplied for custom rooms",
              "rooms": [], "replays": [], "errors": []}
    try:
        report["engine_sha256"] = hashlib.sha256(engine_path.read_bytes()).hexdigest()
        report["levels_sha256"] = hashlib.sha256(levels_path.read_bytes()).hexdigest()
        engine = load_engine(engine_path)
        pack = engine.load_level_pack(str(levels_path))
        report["schema_version"] = pack["version"]
        for index, definition in enumerate(pack["levels"]):
            state = engine.create_state(definition)
            report["rooms"].append({"index": index, "name": definition["name"],
                                    "keys": state.remaining_keys, "actors": len(state.actors),
                                    "teleporter_pairs": sum(c >= 0 for c in definition["twins"]) // 2})
        if solutions_path is None and levels_path == DEFAULT_LEVELS.resolve():
            solutions_path = DEFAULT_SOLUTIONS
        if solutions_path is not None:
            solutions_path = Path(solutions_path).resolve()
            report["scope"] = "structure-and-solutions"
            report["solution_replay"] = "failed"
            report["solutions"] = str(solutions_path)
            raw = solutions_path.read_bytes()
            report["solutions_sha256"] = hashlib.sha256(raw).hexdigest()
            solutions = json.loads(raw)
            engine._fields(solutions, ("version", "schema_version", "solutions"),
                           ("version", "schema_version", "solutions"), "solutions")
            engine._integer(solutions["version"], 1, "solutions.version", 1)
            engine._integer(solutions["schema_version"], 1, "solutions.schema_version", 1)
            if not isinstance(solutions["solutions"], list):
                raise ValueError("solutions.solutions must be an array")
            seen = set()
            for recording in solutions["solutions"]:
                if not isinstance(recording, dict) or "room" not in recording:
                    raise ValueError("solution requires a room index")
                index = engine._integer(recording["room"], 0, "solution.room", len(pack["levels"]) - 1)
                if index in seen:
                    raise ValueError("duplicate solution for room %s" % index)
                seen.add(index)
                result = replay(engine, pack["levels"][index], recording)
                result.update(engine_sha256=report["engine_sha256"],
                              levels_sha256=report["levels_sha256"], schema_version=pack["version"])
                report["replays"].append(result)
            if len(seen) != len(pack["levels"]):
                raise ValueError("solutions must cover every room")
            report["solution_replay"] = "passed"
        report["status"] = "passed"
    except Exception as error:
        report["errors"].append("%s: %s" % (type(error).__name__, error))
        report["traceback"] = traceback.format_exc()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE,
                        help="trusted local Python source; executes with autostart disabled")
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--solutions", type=Path, help="timed solution JSON; defaults to bundled traces for bundled rooms")
    parser.add_argument("--report", type=Path, default=ROOT / "build/grid_puzzle/validation.json")
    args = parser.parse_args()
    report = check(args.engine, args.levels, args.solutions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Engine: %s\nLevels: %s" % (report["engine"], report["levels"]))
    print("%s: %s rooms structurally validated; solution replay %s" %
          (report["status"].upper(), len(report["rooms"]), report["solution_replay"]))
    for error in report["errors"]:
        print(error)
    print("Report: %s" % args.report.resolve())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
