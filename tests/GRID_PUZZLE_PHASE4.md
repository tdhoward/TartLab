# Grid puzzle Phase 4 implementation evidence

Recorded 2026-09-11. The **complete hazard engine software milestone is
implemented**. Next implementation: **Phase 5, dirty rendering, debug inspection,
and performance instrumentation**, in [the project plan](../GRID_PUZZLE_PROJECT.md).
Actual browser/device acceptance remains pending.

## Implemented behavior

- All version-1 validated rooms can launch, including stationary snakes, all
  eight case-sensitive spider tokens, and all four map-directed spear emitters.
  Rules remain in the single editable Python file. Shared runtime, board
  configuration, browser code, and the two bundled teaching rooms are unchanged.
- Snakes resolve horizontal exposure after player interactions, enemy movement
  and removal, and explosion batches. Collectibles and actors provide cover;
  removing that cover can kill a stationary player in the same quantum.
- Each spider advances its own deadline from the previous due time, tries its
  map-defined follow order, and resolves one-hop teleportation. Pure destination
  previews use the same entry/arrival predicates as committed movement. Stable
  map order settles competing destinations; spiders cannot overlap or swap.
- Every live spider is checked for trapping after due movement, including when
  its own timer is not due. The entire trapped set is found before removal.
  Cross-shaped explosions resolve as one deduplicated batch: clear selected
  boulders/dirt, apply player damage, then place permitted diamonds. Protected
  layers and actors remain intact. Diamonds score only on collection.
- Spears activate only along their facing and first extend one interval later.
  Tips advance one cell per deadline, retain shafts, and stop before blockers
  without consuming them. Tip/player contact resolves before immediate stopping.
  Stopped shafts stay solid and harmless, never retract or rearm, and provide
  snake cover. Multiple traps resolve in stable actor order.
- `step` now executes all fourteen required stages. Death latches while the
  committed environment batch finishes; it suppresses completion and freezes
  later quanta. A blast-cleared spear path activates at the next trap stage.
  Pause freezes every hazard timer; restart rebuilds all mutable hazard state.
- The full reference renderer draws directional tips/shafts and three blast
  frames over 180 ms of simulation. Blast art has no collision effect and
  freezes with simulation on pause/death/completion. Startup prepares generated
  diamond/blast sprites as well as authored sprites. No decoding occurs in the
  running loop, and restart reuses compatible art.
- The guide documents implemented hazards, ordering, and entry points for
  editing snake cover, spider priority, projectiles, and explosion rules.

## Automated evidence

| Check | Result and boundary |
| --- | --- |
| Targeted host regression | **204 tests passed**, including **119 grid-puzzle tests**, plus headless IDE, canvas, timing, sprites, and modern profile checks. |
| Hazard rules | **34 focused hazard tests** cover blocker families, all spider tokens and turn priorities, independent/quantized deadlines, conflicts, teleport arrival, trapped snapshots, overlapping/clipped blasts, protected layers, drops, spear states, death versus exit, pause and restart. |
| Presentation scheduling | The actual app loop and `FrameClock`, with fake time and platform adapters, produce identical hazard/input traces at **50 ms and 60 ms** frame periods across tick wrap, without dropped updates. This verifies scheduling, not device speed. |
| Hazard rendering | Generated drops and all blast frames render; dead spiders disappear. Spear tips/shafts render at 1x/2x; full redraw removes expired blast pixels. Existing atlas pixel, clipping, hidden-feature and lifecycle tests pass. Dirty rendering remains Phase 5. |
| Bundled solutions | **Both passed unchanged**: First Crossing, 2540 ms / 100 points / 498 bonus; Veiled Walk, 560 ms / 100 points / 500 bonus, with three explicit hint acknowledgements. |
| Hazard room data | **Five focused JSON rooms validate**. Tests exercise their intended outcomes, including deliberate deaths. These fixtures are not a campaign with successful solution coverage. |
| Atlas rebuild | **Passed**: 59 sprites, 8,232 bytes; canonical atlas/index/preview verified. No new raster generation or binary changes. |
| Supplemental MicroPython | Existing pinned v1.23.0 Unix interpreter passes definitions, both solutions, all five hazard scenarios, restart, controls, and 1x/2x art preparation. Existing `mpy-cross -march=xtensawin` compiles the updated source. Neither substitutes for testing modern firmware. |
| Distribution integration | Existing production-builder fixture checks retain editable Python/JSON/assets in modern payloads and exclude them from legacy payloads. A new install/update or release qualification was not performed. |

The existing IDE pseudo-REPL fixture still emits an unclosed-file
`ResourceWarning`; the suite passes. Full host log:
`build/grid_puzzle/phase4-host-tests.log`. Engine/data hashes and bundled replays:
`build/grid_puzzle/validation.json`. Hazard fixture hashes and structural status:
`build/grid_puzzle/phase4-hazards.json`. Supplemental compiled artifact:
`build/grid_puzzle/phase4-grid_puzzle.mpy`.

## Reproduce and resume

```powershell
python tools/check_grid_puzzle_levels.py
python tools/check_grid_puzzle_levels.py --levels tests/fixtures/grid_puzzle/hazards.json --report build/grid_puzzle/phase4-hazards.json
python tools/build_grid_puzzle_sprites.py --check
python -m unittest discover -s tests -p 'test_grid_puzzle_*.py'
```

The full regression command adds `tests.test_headless_ide`, `tests.test_app`,
`tests.test_timing`, `tests.test_sprites`, and `tests.test_modern_profile` to the
nine grid-puzzle test modules. Custom data without solutions explicitly reports
solvability pending; hazard fixtures intentionally include death scenarios.

Run the supplemental interpreter/compiler through WSL on Windows:

```text
build/micropython-v1.23.0/ports/unix/build-standard/micropython tests/grid_puzzle_compat.py .
build/micropython-v1.23.0/mpy-cross/build/mpy-cross -march=xtensawin -o build/grid_puzzle/phase4-grid_puzzle.mpy src/files/help/grid_puzzle.py
```

## Pending operator observations

Retain the [Phase 3 operator checklist](GRID_PUZZLE_PHASE3.md#pending-operator-observations)
for full-room readability, input comfort/release, hints, hidden art, browser
copies/edits, broken-game recovery, selected-app startup, and UI restoration.
Every unperformed item remains pending. Record observer/date, actual firmware,
and notes; attach validator hashes and capability/layout console output rather
than transcribing machine-known values.

| Additional observation | Result | Observer/date and notes |
| --- | --- | --- |
| Snake/spider direction is readable at the selected integer scale; moving cover exposes the player visibly. | Pending | |
| Left/right spiders and teleport arrivals are understandable with actual controls; waiting does not stop hazards. | Pending | |
| Extending spear tips and retained shafts are readable; stopped shafts block harmlessly. | Pending | |
| Trapped-spider blasts, cleared terrain, and generated diamonds are visible and understandable. | Pending | |
| Pause/hints freeze hazards; restart after death restores actors, traps, drops and controls. | Pending | |
| Repeated hazard-room restarts and transitions retain usable input/rendering; capture heap/timing with the forthcoming benchmark. | Pending | |

Phase 5 must provide dirty/full equivalence, full inspection overlays, and
repeatable performance workloads. Device frame rate, heap/startup cost, teaching
fairness, the full campaign, and release gates remain unproven. Start modern
release preparation with `RELEASE_QUALIFICATION.md` and
`tools/qualification_session.py`.
