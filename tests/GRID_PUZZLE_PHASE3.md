# Grid puzzle Phase 3 implementation evidence

Recorded 2026-09-11. The **terrain, teleportation, messages, and original art
software milestone is implemented**. Actual browser/device acceptance remains
pending. Next implementation: **Phase 4, the complete hazard engine**, in
[the project plan](../GRID_PUZZLE_PROJECT.md).

## Implemented behavior

- All ten dirt and false-wall variants become floor on player entry in the
  same movement transaction. Failed pushes neither dig nor reveal. Restart
  restores authored terrain and variants.
- Paired map labels operate in both directions, once per successful entry.
  A blocked arrival leaves the actor on the entered pad; standing still never
  bounces or retries. Teleports preserve heading and movement deadlines.
  Player and spider queries share the committed arrival rules. Dry-run queries
  do not mutate state; future spider movement can use them for trap detection.
- Immediate contact and horizontal snake-ray checks cover arrival safety.
  Growing spear contact is fatal; stopped spears block harmlessly. Players can
  collide fatally with enemies on either pad; spiders cannot land on another
  enemy. These are tested with constructed occupancy. Autonomous spider moves,
  emitter activation/extension, trapped sets, and explosions remain Phase 4;
  launching a room containing those actors still reports that gate explicitly.
- Messages trigger once per attempt, including at the start. Entry messages
  open after the committed step's hazards/completion. A teleport's source and
  arrival hints are queued in travel order. Hints pause all simulation and bonus
  decay; More/OK uses the existing Pause control and requires fresh input.
  Long text wraps and paginates without dropping later words. Restart restores
  message flags and clears queued hints.
- The full renderer now uses original 16x16 TS16 sprites. All false-wall variants
  use their exact matching wall pixels; normal teleporter cells use ordinary
  floor. `DEBUG = True` reveals tokens; the complete overlays remain Phase 5.
- The **59-sprite, 8,232-byte** atlas includes future hazard artwork, all nine
  water tiles in the specified 3x3 block, and all wall/dirt variants. The
  [art README](../tools/assets/grid_puzzle/README.md) retains provenance, the
  original raster, canonical sheet, preview, palette and coordinate/hash index.
  The builder uses the repository TS16 encoder and rejects malformed artwork.
- `PuzzleArt` batch-prepares only tiles needed by the active room, releases the
  decoder, reuses compatible sprites on restart, and replaces the cache on
  room changes. Exit/errors clear sprites and close the canvas, then restore UI
  ownership. Startup art loading is excluded from simulation/dropped-time counts.
  No shared runtime modules or board configuration were changed.
- **Veiled Walk** adds a compact original terrain/teleporter lesson after
  **First Crossing**. It includes a start hint and hints at both pad locations.
  The guide documents implemented rules, source navigation, and editable
  false-wall/pad/message experiments. The full teaching campaign remains Phase 6.

## Automated evidence

| Check | Result and boundary |
| --- | --- |
| Targeted CPython suite | **167 tests passed**, including **82 grid-puzzle tests**, plus headless IDE, canvas, timing, sprites, and modern profile. |
| Bundled timed solutions | **Both passed**. First Crossing: 2540 ms simulation, 100 points, 498 bonus. Veiled Walk: 560 ms simulation, 100 points, 500 bonus; three explicit hint acknowledgements. |
| Original atlas rebuild | **Passed** deterministic source import, canonical PNG encoding, hash/index/preview verification, palette/alpha/alignment/required-cell checks. |
| Pixel rendering | All 59 tiles match decoded palette pixels at **1x, 2x, 3x**; transparent edges and clipping pass. Hidden pads and all false-wall variants are pixel-identical to normal floor/walls at 1x/2x. Cleared dirt/walls/water and previous actor cells match a fresh reference room. |
| Teleportation/messages | Symmetric travel, adjacent twins, blocked/stationary arrival, direction/deadline preservation, pure spider previews, lethal contacts/rays, hint ordering, no repeated hint, long-text pagination, freeze/restart, and fresh input pass. Existing label-count/metadata validation remains covered. |
| Resource lifecycle | Compatible sprites survive 25 repeated preparations; room changes remove unused sprites. Missing art closes the acquired canvas and restores UI. Asset load time does not count as play time. These tests do not measure device heap stability. |
| Editable source integration | Renamed source, selected-app startup, changed user rules/JSON, actual IDE rerun, independent restoration, and cleanup paths pass. Python remains a single maintained source file. |
| Browser module integration | **3 tests passed** with the actual Help/tab/save modules and adapters. Actual browser observation remains pending. |
| Supplemental Unix MicroPython | Local **v1.23.0** passes source loading, schema/state, both solutions, score rollback, controls, and actual 1x/2x sprite preparation/cache reuse. The art check uses an empty package shell to bypass unrelated device network startup, then imports the unchanged shared image/sprite modules. |
| Supplemental mpy-cross | Local v1.23.0 compiler passes `-march=xtensawin`. Artifact: `build/grid_puzzle/phase3-grid_puzzle.mpy`; Help still ships editable Python. |
| Modern distribution | Normal minifying builder includes editable Python/JSON/guide and byte-identical TS16. Production-builder fixtures verify all four files are excluded from legacy payloads and shared `lib`. Development output is under `build/grid_puzzle/phase3-modern-final`; no board payload or release candidate is claimed. |
| Frontend production build | **Passed**, with the existing 513 KiB bundle and webpack size/performance warnings. |
| Hardware, heap, frame rate, controls and visual comfort | **Pending**. Host rendering and scripted solutions do not establish these outcomes. |

The existing IDE pseudo-REPL fixture emits an unclosed-file ResourceWarning;
the suite passes. Full host log: `build/grid_puzzle/phase3-host-tests.log`.
Frontend/distribution log: `build/grid_puzzle/phase3-modern-build.log`;
final payload log: `build/grid_puzzle/phase3-modern-final-build.log`.
Validation hashes/results: `build/grid_puzzle/validation.json` and the checked-in
`tools/assets/grid_puzzle/index.json`.

## Reproduce and resume

```powershell
python tools/build_grid_puzzle_sprites.py --check
python tools/check_grid_puzzle_levels.py
python -m unittest tests.test_grid_puzzle_levels tests.test_grid_puzzle_engine tests.test_grid_puzzle_terrain tests.test_grid_puzzle_sprites tests.test_grid_puzzle_rendering tests.test_grid_puzzle_integration tests.test_grid_puzzle_input tests.test_grid_puzzle_replay tests.test_headless_ide tests.test_app tests.test_timing tests.test_sprites tests.test_modern_profile -q
npm test --prefix src/ide/www
```

The validator requires a successful trace for every bundled room. `dismiss`
acknowledges one whole message and clears held input; UI pagination has separate
tests. Event times include pauses in the script, while result `elapsed_ms`
counts only simulation. Dismiss without an active message is an error. Custom
rooms without supplied traces explicitly retain pending solvability.

Run the supplemental interpreter/compiler through WSL on Windows:

```text
build/micropython-v1.23.0/ports/unix/build-standard/micropython tests/grid_puzzle_compat.py .
build/micropython-v1.23.0/mpy-cross/build/mpy-cross -march=xtensawin -o build/grid_puzzle/phase3-grid_puzzle.mpy src/files/help/grid_puzzle.py
```

These supplemental host tools are not the modern firmware acceptance target
and do not imply support for the legacy runtime profile.

## Pending operator observations

Record observer/date, actual device/firmware, result, and notes. Attach the
validator report and atlas index for machine-derived hashes and retain startup
output for the selected level path, dimensions, rotation, and integer scale.
All unperformed observations below remain **Pending**; do not infer a pass.
No local server was started and no device was flashed.

| Observation | Result | Operator notes |
| --- | --- | --- |
| Full room, original art, HUD, letterboxing, and all controls are readable at the selected integer scale. | Pending | |
| Direction hold/release/change, water pushing, collection and First Crossing completion feel comfortable. | Pending | |
| All nine water variants read as one pool; banks do not suggest walkable portions of a water cell. | Pending | |
| Dirt clears and false walls reveal in the same movement; false walls and pads stay visually hidden before entry. | Pending | |
| Veiled Walk teleports correctly; leaving/reentering returns; standing still does not bounce. | Pending | |
| Start/source/arrival hints appear in order; More/OK works, text fits, bonus freezes, held directions do not leak through. | Pending | |
| Pause/resume and restart during play, hints, or completion restore correct state without stale input. | Pending | |
| Repeated restarts and room transitions retain usable rendering and input. Record heap/timing in the later benchmark. | Pending | |
| Actual browser opens Help Python/JSON, saves independent renamed copies, closes/reopens, and runs the Python copy. | Pending | |
| A saved Python rule change and independent JSON change execute after rerun; invalid data/path gives a useful diagnostic. | Pending | |
| Console/IDE/reset recovery works after a syntax error or blocked loop; Help code and rooms restore independently. | Pending | |
| Selected-app reset launches the saved copy and art; Back restores usable UI ownership. | Pending | |

These carry forward the unfinished Phase 1/2 observations. Hazard interactions,
complete debug overlays, performance workloads, full campaign/manual fairness,
and normal release qualification remain required in their later phases. Begin
a release with `RELEASE_QUALIFICATION.md` and `tools/qualification_session.py`.
