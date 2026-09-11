# Grid puzzle Phase 2 implementation evidence

Recorded 2026-09-11. The **first playable room software milestone is implemented**.
Actual browser/device acceptance remains pending. Next implementation: **Phase 3,
terrain, teleportation, messages, and original TS16 artwork**, in
[the project plan](../GRID_PUZZLE_PROJECT.md).

## Implemented behavior

- The maintained, copyable [Python source](../src/files/help/grid_puzzle.py) now
  implements cardinal movement, wall/exit collision, keys and diamonds, atomic
  boulder pushes, water filling, room-local score, bonus, pause, restart, and
  completion. No pulling or chain pushes. All nine water variants consume the
  boulder and become floor; failed pushes change neither position nor occupancy.
- Simulation advances in 10 ms quanta. The first eligible movement is at 10 ms;
  continuously held movement attempts occur at 120, 230, 340 ms, etc. Failed
  attempts consume the same interval, direction changes preserve cooldown, and
  nonmultiple intervals retain their deadlines without cumulative rounding drift.
- The app uses the existing wrap-safe `FrameClock`, with a proposed 50 ms frame
  period and at most ten catch-up updates. Newly observed input applies after the
  elapsed batch. No positions are fast-forwarded after a stall. Restart/resume
  create a fresh clock; timing diagnostics retain missed deadlines and dropped
  simulation time across those rebases.
- Touch holds/slides and named button press/release events choose one direction.
  Most recent press wins; ordered button events follow touch within each poll.
  Restart, pause, next room, and Back require fresh action edges. Ownership and
  session transitions require physical release before accepting new input.
- A full renderer rebuilds live terrain, objects, and actors, then HUD/controls,
  with one `show()` per presentation. Symbols are temporary primitive artwork:
  player P, key K, diamond *, boulder O, exit E. The active exit turns green.
- A room award banks once on completion. Restart discards unbanked points and
  reverses an already banked award for the current room. Previous rooms remain
  banked. Next loads a new state while reusing the same canvas. Pause, death,
  and completion freeze subsequent simulation. Hazard-caused death is Phase 4.
- The bundled **First Crossing** room uses only implemented mechanics. Future
  tokens remain structurally valid for authoring, but starting a room with dirt,
  false walls, pads, messages, or enemies reports that Phases 3/4 are pending.
  The old probe's dirt and hint-message placeholders were removed from this room;
  the crossing hint is now in the editing guide.
- Help lists **Grid puzzle: First Crossing**. The guide traces the actual input,
  simulation, collision, collection, and drawing functions and gives observable
  scoring/timing experiments in a renamed student copy.

## Automated evidence

| Check | Result and boundary |
| --- | --- |
| Targeted CPython suite | **141 tests passed**, including 56 grid-puzzle tests plus headless IDE, canvas, timing, sprites, and modern profile. |
| Timed bundled solution | **Passed**: First Crossing completes at 2540 ms of simulation, with 100 diamond points and 498 remaining bonus points. |
| Input and timing | Held/released inputs, fresh action edges, pause/resume/restart, bounded catch-up, and nonretroactive presses tested. The same observed input schedule yields identical per-quantum traces at 50/60 ms frame periods across tick wrap. |
| Editable engine integration | Actual IDE save/pseudo-REPL reruns changed collection rules in existing globals (37 then 73 points). A renamed source executes its own rules and chosen JSON. Selected-app import startup and cleanup paths pass with device adapters. |
| Browser integration | **3 tests passed**, using the real Help/tab/save modules with adapters, including independent Python/JSON user copies. Real browser observation remains pending. |
| Supplemental MicroPython Unix | Existing local **v1.23.0** interpreter passes source loading, all-symbol schema/state checks, the timed solution, score rollback, and held controls. This is supplemental language evidence, not legacy runtime support or modern device qualification. |
| Supplemental mpy-cross | Existing v1.23.0 compiler passes `-march=xtensawin`; artifact: `build/grid_puzzle/phase2-grid_puzzle.mpy`. Help continues to ship editable Python. |
| Modern distribution and frontend build | **Passed** normal minifying builder, 78 files / 596884 expanded bytes, in `build/grid_puzzle/phase2-modern`. Production frontend bundle is 513 KiB with the existing webpack size/performance warnings. This development build has no board payload and is not a release candidate. |
| Modern/legacy isolation | Production-builder fixtures verify editable Python/JSON/HTML appear only in modern Help and never in shared `lib` or legacy Help. |
| Hardware, memory, frame rate, visual comfort | **Pending**. Host tests, scripted solutions, and Unix MicroPython do not establish these outcomes. |

Host logs: `build/grid_puzzle/phase2-host-tests.log`. The existing IDE-style
`exec(open(...).read())` fixture emits a CPython unclosed-file ResourceWarning;
the suite passes. Build log: `build/grid_puzzle/phase2-modern-build.log`.

## Reproduce and resume

```powershell
python tools/check_grid_puzzle_levels.py
python -m unittest tests.test_grid_puzzle_levels tests.test_grid_puzzle_engine tests.test_grid_puzzle_rendering tests.test_grid_puzzle_integration tests.test_grid_puzzle_input tests.test_grid_puzzle_replay tests.test_headless_ide tests.test_app tests.test_timing tests.test_sprites tests.test_modern_profile -q
npm test --prefix src/ide/www
```

The validator writes `build/grid_puzzle/validation.json` with selected engine,
level-data, and solution paths and SHA-256 hashes; schema version; timed events;
and expected-outcome checks. It requires a successful trace for every bundled
room. Missing coverage, duplicate records, malformed events, or wrong outcomes
fail rather than silently skipping a room. The checked-in input recording is
[solutions.json](fixtures/grid_puzzle/solutions.json).

For trusted local experiments, use `--engine`, `--levels`, and `--solutions`.
Custom JSON without solutions gets structural validation and explicitly reports
replay pending. Hashes identify the selected experiment; they do not restrict
which edited engine may execute. A scripted fast solution establishes solvability,
not comfortable pacing or a recommended human completion time.

Run the supplemental interpreter/compiler through WSL on Windows:

```text
build/micropython-v1.23.0/ports/unix/build-standard/micropython tests/grid_puzzle_compat.py .
build/micropython-v1.23.0/mpy-cross/build/mpy-cross -march=xtensawin -o build/grid_puzzle/phase2-grid_puzzle.mpy src/files/help/grid_puzzle.py
```

## Pending operator observations

Use the hashes from the validator report and retain startup output containing the
selected level path, dimensions, rotation, and integer scale. Record the actual
device/firmware, observer, date, result, and notes with each observation. The
modern target uses its modern firmware; the supplemental 1.23 host check is not
the acceptance target. No device was flashed and no local server was started.

| Observation | Result | Operator notes |
| --- | --- | --- |
| Full room, HUD, symbols, square tiles, letterboxing, and controls are readable. | Pending | |
| All four directions, held repeat, release, and direction changes feel usable. | Pending | |
| Push into water, collect the optional diamond and key, and complete First Crossing. | Pending | |
| Pause freezes movement and bonus; release/resume does not leak an old gesture. | Pending | |
| Reset during play, pause, and completion restores terrain, objects, score, timers, and start; repeats remain stable. | Pending | |
| Open Help Python/JSON, save independent renamed copies, close/reopen, and run the Python copy in the actual browser. | Pending | |
| Change collection scoring in the saved Python and observe the changed rule after save/rerun. | Pending | |
| Edit JSON independently; observe the selected room and a useful error for invalid JSON/path. | Pending | |
| Recover from a syntax error or blocked loop through the console/IDE/reset route. | Pending | |
| Restore Help code and rooms independently while retaining experimental copies. | Pending | |
| Reset into the saved selected app, then Back returns usable UI ownership without stale touch. | Pending | |

These carry forward the unperformed Phase 1 browser/device gates and add playable
controls. No physical pass, heap stability, 15–20 fps support, release approval,
or completed campaign is claimed. Later hazard/art/debug/performance phases and
the normal release qualification process remain required.
