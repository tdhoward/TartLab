# Grid puzzle Phase 5 implementation and device evidence

Recorded 2026-09-11. Rendering, debug inspection, and repeatable device tooling
are implemented and installed on COM18. **The Phase 5 performance exit gate
failed; this phase remains open.** Continue with the measured failures below
before moving to the teaching campaign or release qualification.

## Implemented and verified

- `Session.advance` captures every quantum's damage. The renderer composes
  changed cells from all layers, bounds presentation regions with `DamageTracker`,
  and uses full-board composition for dense changes and debug. Pixel tests compare
  both the framebuffer and the simulated transmitted image with `draw_full_game`.
  They cover both bundled timed solutions, all hazard fixtures, catch-up,
  50/60 ms presentation batches, 1x/2x layouts, transitions, and debug removal.
- Native prepared tile blits replace repeated Python span calls. The small shared
  `DirectCanvas.draw_sprite(..., key=-1)` extension supports RGB565 transparency;
  its default retains existing opaque behavior. Tests compare native and span
  rendering and preserve background pixels at all four rotations. Art is prepared
  at load, reused on compatible restart, and released on close. No second board
  framebuffer is allocated; the app selects 64 transfer rows.
- Engine work skips empty explosion batches and unchanged trapped-spider
  snapshots, uses actor lists by kind, and clears/counts fixed byte buffers with
  native operations. All rules remain in the editable source. `mark_changed`
  invalidates occupancy-dependent snapshots, including late spear/explosion
  changes; the hazard/order tests still pass.
- DBG toggles grid coordinates, hidden-wall outlines, labelled undirected twin
  links, enemy arrows/follow modes, bounded twelve-cell trails, actual next-move
  queries, and rays/first blockers. Pause exposes a paged cell inspector with
  level path, predicates, actor deadlines and clock counters. Choose a direction
  while paused, release it, then tap Step for one normal 10 ms quantum. Hint
  acknowledgement, death and completion retain their existing semantics.
- Initial presentation and explicit restart/hint transition drawing are excluded
  from accumulated play time. Restart and ownership changes require fresh input.
- The benchmark preserves complete case coverage, per-case logs, source/asset
  hashes, device identity/capabilities, startup and art cost, frame work breakdowns,
  missed/dropped time, actual playing/frozen sample counts and repeated-restart
  heap measurements. It generates a separate pending physical-observation form.

## Host evidence

**215 tests passed:** 129 grid-puzzle tests and 86 headless IDE, canvas, timing,
sprite and modern-profile checks. Both original timed solutions and the
59-sprite / 8,232-byte atlas check pass. Existing distribution integration tests
verify modern inclusion and legacy exclusion. The IDE fixture still emits its
pre-existing unclosed-file `ResourceWarning`.

Logs: `build/grid_puzzle/phase5-host-tests.log` and
`build/grid_puzzle/phase5-regression.log`. Replay hashes/results:
`build/grid_puzzle/validation.json`. The current source compiled and ran on the
actual modern firmware; a legacy MicroPython run is not substituted for it.

## COM18 measurements

Device-derived identity: `elecrow_dle06235b`; MicroPython 1.27.0,
`78ff170de9-dirty` dated 2026-09-05; touch and direct RGB565 capabilities.
The app chose logical 480x320, rotation 90, 1x tiles and side controls.
The installed-source smoke check also recorded a 240 MHz CPU clock.

The complete run contains **22/22 cases**, 40 measured presentations per case,
with a 50 ms target and 10 ms simulation quantum. Every bundled and focused
hazard room is included, followed by 80 moving spiders, 190 placed spiders for
dense explosions, four already-triggered long spear directions, and all nine
static water variants. Each case runs normally and with debug. Restart
transitions are reported separately, matching the app's paused transition time;
ordinary in-play hint/death transitions remain in the measured frame work.
Cases that deliberately die report their frozen sample counts explicitly.

| Normal workload | p95 frame work | Maximum | Dropped simulation |
| --- | ---: | ---: | ---: |
| First Crossing | 12.9 ms | 13.4 ms | 0 ms |
| Veiled Walk | 12.8 ms | 158.8 ms | 50 ms |
| Trapped neighbors | 27.0 ms | 30.8 ms | 0 ms |
| Dense moving spiders | 210.7 ms | 234.0 ms | 1,660 ms |
| Dense explosions | 231.1 ms | 469.2 ms | 720 ms |
| Four long spears | 26.7 ms | 37.0 ms | 0 ms |
| Static water variants | 13.2 ms | 15.0 ms | 0 ms |

Other normal hazard rooms had maxima around 61-69 ms and missed deadlines.
Continuous debug redraws also fail the target; see the complete report rather
than treating this compact table as reduced coverage. Even a 60 ms target cannot
cover the measured dense workloads. **No supported fixed frame period is claimed.**

Loading/compiling the full Python source took about 844 ms; loading/validating
the two-room bundled JSON took about 508 ms. Collected free heap was 7,771,568
bytes after source compilation and 7,750,768 after the bundled pack. First-room
art preparation took about 1.16 seconds. Across the measured cases, thirty
compatible restarts changed collected free heap by -192 to +4,912 bytes. These
short measurements do not establish long-running physical stability.

Full local evidence: `build/grid_puzzle/com18-phase5/report.json`, per-case logs,
`setup.log`, `installed-smoke.log`, and `install.json`. The exact measured engine
hash is `b15953e4fd4ff22e8e8ad0525987eed2d3cb78e43b81f499882e263be419e62c`.
`benchmark-tool.py` in that artifact folder retains the hash-verified invoked
tool source; subsequent host-only form-validation refactoring does not alter the
measured device program. A sanitized report is checked in under
`tests/evidence/grid-puzzle-phase5-com18.json`.

## Next gate and scope

1. Profile dense movement/trapped-set work, burst composition, display transfer,
   and overlay/transition costs. Preserve the matrix and failed logs. Recheck
   frame deadlines and dropped time after remediation; low median cost alone
   does not qualify a fixed cadence.
2. Complete the actual operator observations in the
   [hardware workflow](GRID_PUZZLE_HARDWARE.md). No browser backend was available
   in this session. Browser copy/edit/recovery and physical comfort/readability
   therefore remain pending.
3. Continue to Phase 6 only after resolving the unfinished gates. The two-room
   pack is not the complete teaching campaign.

No firmware was flashed, no student file or selected-app setting was changed,
and no release candidate was promoted. Development installation updated only
the game Python/JSON/guide/art, its merged Help entries, and the shared canvas
module. Prior existing file bytes are backed up locally. Because the canvas API
changed, eventual release work must assess the shared-platform impact through
`RELEASE_QUALIFICATION.md` and the existing qualification tools; this development
run supplies no release qualification pass.

## Operator follow-up: JSON editor dependency

The user reported successfully copying the Python game from Examples to the
user folder and running it, with no performance issue noticed in that play.
Debugging toggled on/off and looked correct. These observations establish that
reported path; they do not replace the dense workload measurements or unreported
pause/step, hazard, recovery and selected-app checks.

Opening `grid_puzzle_levels.json` produced "Unable to display this file type."
Serial inspection confirmed that the installed `bundle.js.gz` routed only
Python, HTML, TXT and LOG files. Repository `tabs.js` already included JSON, but
the initial development install had omitted the IDE assets. The installer now
always builds and includes the production browser dependency using normal
distribution compression. A regression test verifies that a fresh build replaces
a stale editor payload. The three existing JSON/Python editor integration tests
and production build pass (existing webpack size warnings remain).

The rebuilt IDE is installed on COM18. Its read-back SHA-256 matches the
production artifact, and decompressed installed code includes JSON text-tab
routing (`verification.json`). Hard-refresh the browser before reopening JSON.
Follow-up artifacts are in `build/grid_puzzle/com18-json-editor-fix`; the original
installed bundle is retained in `build/grid_puzzle/com18-phase5/ide-bundle-before.js.gz`.
The physical form records Python copy/run and debug observations, retains the
observed JSON failure, and leaves post-update JSON copy/save/reopen pending.

## Operator follow-up: spider rules

After editing the room JSON to add a spider, the user reported that a spider
passing beside the player was harmless and that spiders in open areas circled.
The requested rules replace the previous movement/contact contract:

- Both modes try forward first. When blocked, left-preferring spiders try left,
  right, reverse; right-preferring spiders try right, left, reverse. Heading
  tokens, turn-and-move timing, independent deadlines and blocked destinations
  retain their existing meanings. Debug move previews use the same query.
- Each successful move checks the spider's departure, entered cell and teleport
  arrival. Same-cell or orthogonally adjacent player occupancy kills immediately.
  Diagonals and wrapped row edges are excluded. Adjacency does not attack between
  moves; a spider unable to move follows the explosion rules. Death still wins
  over completion and latches once while committed movement finishes.
- The moving-cover fixture now starts its spider northward so it still moves
  out of the snake ray on its first deadline. Other hazard fixtures and the two
  bundled rooms are retained. Snake and spear rules are unchanged.

All **136 grid-puzzle tests pass**, including all-eight-token straight paths,
both turn orders through reverse, four-sided adjacency, diagonal/edge exclusions,
waiting/departure, source-pad/arrival proximity, death versus exit, and existing
dirty/reference and native/span pixel equivalence. Both bundled timed solutions
still pass. Art and shared platform code did not change for this rule revision.

Artifacts: `build/grid_puzzle/com18-spider-rules/host-tests.log`,
`validation.json`, and `user-engine.patch`. The user's `/files/user/grid_puzzle.py`
was identified as the existing example with its `LEVEL_FILE` changed to
`/files/user/grid_puzzle_levels.json`; the prepared patch changes only the two
spider functions and adds their contact helper. Prior source bytes are retained
locally and the custom JSON path is preserved. The updated example and patched
user copy are installed on COM18. Each passed **23 targeted checks on the actual
modern device**, including straight motion, left/right turns, orthogonal and
teleport contact, diagonal/row-edge safety, waiting/departure, exit ordering,
and snake/spear smoke cases. `device-verification.json` records both source paths,
loaded JSON paths, case results and the patched user-source hash. Read-back
verified the patched source and byte-for-byte preservation of the custom JSON.
The old benchmark matrix remains evidence for its original recorded engine and
hazard-fixture hashes, not a timing qualification of these revised rules.

## Operator follow-up: continuous wall following (2026-09-12)

The forward-first rule is superseded by a local corner check in
`next_spider_heading`. A left-following spider turns left when left is enterable
and behind-left is blocked; otherwise it tries forward, right, backward, left.
Right-following spiders mirror those directions. All existing entry blockers
support corners, including room boundaries. The diagonal query examines the
local cell, not a remote teleporter destination. Each move checks current
occupancy, so disappearing obstacles and teleportation need no remembered mode.
Movement, debug previews and trapped-set detection still share this pure query.

All **137 grid-puzzle host tests pass**, including dirty/reference rendering and
the eight portable scenarios in `tests/grid_puzzle_spider_checks.py`. Both bundled
timed solutions still pass. The portable checks cover both following sides,
every initial heading, bounded and unbounded room perimeters, rectangular and
concave obstacle circuits, removal at every position around an obstacle,
teleport reacquisition, all blocker types, diagonal pad semantics and room edges.
Route checks also verify preview purity, committed destinations and deadlines.

The Help engine, Help guide and existing `/files/user/grid_puzzle.py` were
updated on COM18. Only `next_spider_heading` was replaced in the user engine;
all remaining user-source bytes and its configured JSON path were preserved.
Both installed engines passed **all eight portable scenarios on the actual
device** and loaded their configured level packs. Installed files were read
back byte-for-byte, both JSON files retained their hashes, and normal startup
was requested before releasing the serial port.

Backups, the exact user patch, host logs, solution validation, installation
hashes and device results are in `build/grid_puzzle/com18-wall-following/`:
`user-engine.patch`, `host-tests.log`, `validation.json`, `install.json`, and
`device-verification.json`. `update_device.py` records the repeatable preparation
and installation steps. Physical play feedback is pending; the existing failed
performance gate remains unchanged and no new frame-rate claim is made.
