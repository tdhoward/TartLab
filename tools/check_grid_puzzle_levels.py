"""Validate the actual editable engine/JSON pair; keep detailed results on disk.

Phase 1 checks structure and state construction only. Timed solution replay is
pending the simulation phase and is explicitly reported as pending, not passed.
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


def load_engine(path=DEFAULT_ENGINE):
    """Load the maintained source without device mocks or import/bytecode caches."""
    path = Path(path).resolve()
    module = types.ModuleType("grid_puzzle_experiment")
    module._GRID_PUZZLE_AUTOSTART = False
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def check(engine_path=DEFAULT_ENGINE, levels_path=DEFAULT_LEVELS):
    engine_path, levels_path = Path(engine_path).resolve(), Path(levels_path).resolve()
    report = {"engine": str(engine_path), "levels": str(levels_path),
              "status": "failed", "scope": "phase1-structure",
              "solution_replay": "pending: simulation not implemented", "rooms": [], "errors": []}
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
    parser.add_argument("--report", type=Path, default=ROOT / "build/grid_puzzle/validation.json")
    args = parser.parse_args()
    report = check(args.engine, args.levels)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Engine: %s\nLevels: %s" % (report["engine"], report["levels"]))
    print("%s: %s rooms structurally validated; solution replay pending" %
          (report["status"].upper(), len(report["rooms"])))
    for error in report["errors"]:
        print(error)
    print("Report: %s" % args.report.resolve())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
