# Grid puzzle Phase 1 implementation evidence

Recorded 2026-09-11. Software foundation implemented; physical acceptance remains
pending. The next code phase is **Phase 2: first playable room** in
[the project plan](../GRID_PUZZLE_PROJECT.md). The current app is an interactive
room/layout/input probe. It does not simulate movement, hazards, or completion.

The project targets `lvgl-modern` only. Legacy packaging checks verify exclusion
of the game, not support for running it. Future runtime and physical acceptance
checks follow the modern platform's firmware. The recorded MicroPython 1.23
host probe is supplemental evidence, not a legacy compatibility requirement.

## Implemented contracts

- [One editable Python source](../src/files/help/grid_puzzle.py), with eight
  searchable sections and the selected-app/IDE autostart guard. Loading
  definitions with autostart disabled performs no imports, I/O or device work.
- [Version-1 room data](../src/files/help/grid_puzzle_levels.json) and validation
  for every planned token family, including all eight spider variants and ten
  independent teleporter pairs. Diagnostics include the selected file and useful
  field paths or zero-based cell coordinates. Unknown fields never silently pass.
- Separate integer terrain, variant, object, actor, and spear-occupancy layers;
  stable map-order actor IDs and independent deadlines; fresh state rebuilds all
  implemented mutable state without modifying source definitions or files.
- Effective timers resolve Python defaults, room overrides, then spear-only
  actor overrides. Each room requires `name` and `map`. Messages are unique by
  cell, at most 192 per room, and reject walls/water/stationary enemies. A start
  message initializes paused state. A zero-key room initializes an active exit.
- A whole 256×192 board with HUD and 32-pixel directional touch targets.
  Capability-only layout selection tries both orientations and integer scales.
  Synthetic 480×222 and 320×480 touch surfaces fit at 1× with side controls;
  256×328 fits controls below; 800×480 fits at 2×. A 170×320 surface does not fit.
  These calculations do not establish physical usability or performance.
- Probe directions inspect cells, Reset reconstructs state, Pause reveals hidden
  token labels, and Back returns UI ownership. Initial held touch is suppressed
  until release. Resource cleanup covers normal return, rendering failure,
  allocation failure, and canvas-close failure.
- Generic JSON text-tab support, including save under a new name, focus, dirty
  close protection, and editor cleanup. Help originals can be copied without
  first editing them. A save response cannot mark another tab or a newer edit
  clean. Run/Set as App remain Python-only.
- [Help guide](../src/files/help/grid_puzzle_guide.html) documents source/JSON
  independence, schema, planned rules, code navigation, and restart/rerun/restore.

## Automated verification

| Check | Result and boundary |
| --- | --- |
| CPython targeted suite | **113 tests passed**, including all grid-puzzle modules, headless IDE, canvas, timing, sprites, and modern profile. |
| Browser module integration | **3 tests passed** using actual Help/sidebar/tab/save modules with DOM, editor, and HTTP adapters. Includes Help → saved user copy → close → file-list reopen for JSON and Python-copy execution eligibility. |
| Production browser build | **Passed**, 513 KiB bundle; webpack reports size/performance warnings. No local server was started. |
| Pinned MicroPython Unix | **Passed**, v1.23.0 (build date 2026-08-16). Actual source loads both bundled/all-symbol JSON, constructs fresh state, checks twin symmetry and layouts. This found and fixed MicroPython's bytes-only `bytearray.count` difference. |
| Pinned mpy-cross | **Passed**, v1.23.0, mpy v6.3, `-march=xtensawin`. Generated `build/grid_puzzle/grid_puzzle.mpy`; the shipped Help source remains Python. |
| Selected-app startup | Actual `app_runner.launch_selected_app()` imports a renamed source with device adapters; its normal guard runs and its canvas closes. |
| Student edit/rerun | Actual IDE save endpoint and pseudo-REPL reload updated source into existing globals. A renamed copy executes an edited `inspect_cell` function and reloads independently edited JSON. |
| Modern distribution | **Passed**, normal minifying `makedist.py` build in `build/grid_puzzle/modern`; Help Python/JSON/HTML are copied as editable source. |
| Profile isolation | Production-builder fixture verifies these files appear only in modern Help, never legacy Help or `src/lib`. |
| Room solution replay | **Pending**; structural validation is not a successful gameplay trace. |
| Physical/visual/heap/frame-rate qualification | **Pending**; host adapters and Unix MicroPython are not device observations. |

The existing modern-example source tests were updated to recognize the existing
Calculator/Nearby Chat native UI examples, the new modern-only files, and public
`enter_ui_mode()` cleanup. Driver/board import restrictions remain enforced.

## Reproduce or resume

```powershell
python tools/check_grid_puzzle_levels.py
python -m unittest tests.test_grid_puzzle_levels tests.test_grid_puzzle_engine tests.test_grid_puzzle_rendering tests.test_grid_puzzle_integration tests.test_headless_ide tests.test_app tests.test_timing tests.test_sprites tests.test_modern_profile -q
npm test --prefix src/ide/www
npm run build --prefix src/ide/www
```

The validator accepts trusted local `--engine`, `--levels`, and `--report` paths.
Its JSON report includes the exact source/data paths, SHA-256 hashes, room
summaries, and detailed failures. It explicitly marks solution replay pending.
The local host-test transcript is `build/grid_puzzle/host-tests.log`; the normal
distribution-build transcript is `build/grid_puzzle/modern-build.log`.

With the existing pinned Unix tools (use WSL on Windows):

```text
build/micropython-v1.23.0/ports/unix/build-standard/micropython tests/grid_puzzle_compat.py .
build/micropython-v1.23.0/mpy-cross/build/mpy-cross -march=xtensawin -o build/grid_puzzle/grid_puzzle.mpy src/files/help/grid_puzzle.py
```

## Unfinished Phase 1 acceptance gate

These checks require actual observation. They have not been performed here.
Record the source/data hashes from the validator report and retain the probe's
console output (selected path, display dimensions, rotation, scale, placement).
Keep results pending until observed; preserve failures rather than inferring a
pass from host tests.

| Observation | Status |
| --- | --- |
| Full room and HUD are readable; square tiles, letterboxing, controls fit the physical display. | Pending |
| All four directions, release suppression, Reset, label toggle, cell inspection, and Back are usable. | Pending |
| Open bundled Python and JSON in the real browser, save independent user copies, close/reopen, and run the Python copy. | Pending |
| Change `inspect_cell` in the renamed Python; observe changed console output after save/rerun. | Pending |
| Change custom JSON independently; observe new name/tiles after save/rerun. | Pending |
| Invalid custom path/JSON gives a useful diagnostic and leaves the IDE/recovery route usable. | Pending |
| Recover after a syntax error or blocked loop using console interrupt/reset and the board's existing IDE startup route. | Pending |
| Restore Help code and rooms independently, retaining experimental copies under other names. | Pending |
| Reset into the saved selected-app copy and return to UI without stale touch or display ownership. | Pending |

## Next implementation

Implement Phase 2 player transactions, scoring/restart/session state, and the
fixed-step loop in the reserved sections of the same file. Add timed replay to
the validator once movement exists. Then follow the remaining terrain/art,
hazard, dirty-render/debug, teaching-room, and packaging phases. Do not treat the
probe as completed gameplay or silently relax later gates.

No TS16 atlas, benchmark, playable campaign, device results, release candidate,
or release approval was created. When a real release candidate exists, generate
its operator form through [qualification_session.py](../tools/qualification_session.py)
and follow [RELEASE_QUALIFICATION.md](../RELEASE_QUALIFICATION.md).
