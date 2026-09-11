# Grid puzzle/action example: architecture and development plan

Status (2026-09-11): Phase 2 software milestone implemented. The editable
single-file example now plays First Crossing with timed movement, atomic pushing,
water filling, keys/diamonds, exit completion, scoring, pause, and restart. The
host validator replays its checked-in solution and records source/data hashes.
See [Phase 2 evidence](tests/GRID_PUZZLE_PHASE2.md) and the earlier
[Phase 1 foundation evidence](tests/GRID_PUZZLE_PHASE1.md).

Next implementation entry point: Phase 3 in
[Development phases and exit criteria](#development-phases-and-exit-criteria).
The unfinished acceptance gate is actual browser/device observation of
copy/edit/recovery, full-room readability, input comfort, and playable controls.
The current operator checklist is in the Phase 2 evidence document; no physical
pass or frame-rate qualification is inferred from host tests.
Keep this status current as phases finish; record the next unfinished gate and
link to its evidence instead of repeating completed investigations.

Working identifier: `grid_puzzle`. Choose an original display title during the
content phase. This document proposes a new modern TartLab example alongside
Racer and Testris. All art, room layouts, names, and narrative must be original.
The requested inspiration informs the style of interacting puzzle mechanics.

## Scope and first implementation

Build a real-time, top-down game with one complete 16-column by 12-row room
visible at once. Actors occupy integer cells and move only orthogonally. Each
room has exactly one player start, exactly one exit, and zero or more required
keys. Optional diamonds and a remaining-time bonus contribute to score.

The finished first version includes every requested mechanic: boulders, dirt,
water filling, false walls, teleporters, snakes, wall-following spiders and their
explosions, and extending spear traps. It also includes restart, an original
introductory room set, a student editing guide, and optional debug overlays.
The early playable milestone implements a smaller subset; it is not the full
completion target.

Target **`lvgl-modern` only**, using the existing direct canvas and touch platform
APIs. Legacy support is outside this project, including future phases. Runtime
compatibility and physical qualification target the modern platform's firmware;
compatibility with `legacy-mp123` is not an acceptance requirement. Checks involving
legacy packaging only verify that the game is excluded from those distributions.
A graphical level editor, scrolling maps, procedural room
generation, multiplayer, sound, undo, and persistent campaigns are outside this
first version. Students edit arrays of strings in a separate JSON level file and
inspect, change, and deliberately break the engine in a single Python file.
Copying and restoring that engine through the browser editor is a core teaching
requirement, alongside making rooms without changing the engine.
Physical directional input can use existing named button events when sufficient
controls exist; a two-button navigation scheme is not a prerequisite.

## Repository fit and code ownership

These existing components establish the integration points:

| Existing source | Use in this project |
| --- | --- |
| [Racer](src/files/help/racer.py) and [its architecture plan](SCROLLING_RACER_PROJECT.md) | Separate simulation, drawing, input, and presentation; reuse the testing approach rather than its pixel-based collision rules. |
| [Testris](src/files/help/testris.py) | Example-app discoverability and restart/pause interaction conventions. |
| [DirectCanvas](src/lib/tartlabutils/app.py) | Acquire `game_surface()`, choose rotation, draw to the framebuffer, and present changed rectangles. |
| [FrameClock](src/lib/tartlabutils/timing.py) | Fixed simulation increments, absolute presentation deadlines, bounded catch-up, and overrun counters. |
| [DamageTracker](src/lib/tartlabutils/damage.py) | Merge and bound display damage without growing a per-frame rectangle list. |
| [SpriteSheet](src/lib/tartlabutils/sprites.py) and [image documentation](IMAGE_ASSETS.md) | Batch preparation, clipped sprite drawing, integer nearest-neighbor scaling, and the existing TS16 format. |
| [Help manifest](src/files/help/manifest.json) and [distribution builder](makedist.py) | Register the Python example, JSON levels, and guide; ship them with assets in the modern payload. |

Keep the game engine, tile properties, rules, room geometry, input mappings,
atlas coordinates, and debug policy inside the single example Python file. Nothing here
requires a generic game framework or an entity-component system.

Do not add game-specific code to `tartlabutils`. A shared helper should be changed
only if a concrete missing reusable capability is demonstrated. All board
identities, GPIO values, electrical properties, panel configuration, and driver
quirks remain in the existing declarative `BOARD_CONFIG` payloads. The app uses
reported dimensions, rotation, input availability, and surface capabilities.

### Proposed source layout

The Python/JSON/guide, host validator, movement tests, and first solution trace exist.
Art, hazard tests, campaign traces, benchmarking, and physical qualification
deliverables below remain scheduled for their later phases.

```text
src/files/help/
    grid_puzzle.py                 # Complete editable game and engine
    grid_puzzle_levels.json        # Versioned room pack; arrays of map strings
    grid_puzzle_guide.html         # Rooms, code navigation, experiments, recovery
    manifest.json                 # Game, level-data, and guide entries
src/files/assets/
    grid_puzzle.ts16
tools/assets/grid_puzzle/
    sheet.png                     # Original canonical 16x16 tile artwork
    README.md                     # Palette, atlas map, sources, rebuild steps
tools/
    build_grid_puzzle_sprites.py   # Deterministic atlas preparation
    check_grid_puzzle_levels.py    # Validation and recorded solution replay
    grid_puzzle_benchmark.py       # Repeatable device workloads and reports
tests/
    test_grid_puzzle_levels.py
    test_grid_puzzle_engine.py
    test_grid_puzzle_hazards.py
    test_grid_puzzle_rendering.py
    test_grid_puzzle_integration.py
    fixtures/grid_puzzle/          # Focused rooms and timed solution traces
    GRID_PUZZLE_HARDWARE.md        # Operator procedures and observations
```

Maintain one hand-written `grid_puzzle.py` containing all game-specific code.
Students must be able to copy it to `/files/user/my_puzzle.py` and change the
actual movement, collision, enemy, rendering, and scoring implementations there.
Do not delegate game rules to a hidden package or generate this file by combining
separate source modules: the file students read is the source we maintain/test.
Generic platform, canvas, clock, damage, and sprite helpers remain normal imports.
The external JSON and TS16 files keep large data and binary art out of the lesson.

Organize the Python file into clearly labeled, searchable sections:

1. A short code map, paths, timing/scoring defaults, and `DEBUG`.
2. Tile symbols and interaction predicates.
3. JSON loading/validation and logical state creation.
4. Player movement, pushing, collection, and teleportation.
5. Snakes, spiders, traps, and explosions.
6. The explicit fourteen-stage simulation step.
7. Art preparation, layout, full/dirty rendering, and debug overlays.
8. Input handling, session/screens, resource cleanup, and `main()`.

Use small functions/classes with clear names, explicit data flow, and comments
that explain decisions. Keep state in a game/session object rather than many
mutable globals. Teach one action by following its call chain from input to
rule to visible result. Logical separation and independent tests still apply
within one file. Expect a substantial file; prioritize readable code over a line
count target, compressed expressions, or moving interesting rules out of reach.

The selected-app runner imports the selected module, so the file must launch
when imported as well as when executed by the IDE. A conventional
`if __name__ == "__main__"` alone would not satisfy that path. Keep a final
`if globals().get("_GRID_PUZZLE_AUTOSTART", True): main()` guard, following Racer's
pattern. Host tools load this same file with the override set to `False`.
Import device-dependent modules inside the functions that use them, and acquire
no display/input, open no files, and start no timers while loading definitions
with autostart disabled. Pure engine tests then need no platform mocks.

### Student copies, level paths, and recovery

Put these explicit settings near the top of the Python file:

```python
LEVEL_FILE = "/files/help/grid_puzzle_levels.json"
ASSET_FILE = "/files/assets/grid_puzzle.ts16"
DEBUG = False
```

A student can copy only the Python file to experiment with the engine while
using the supplied rooms and art. To customize rooms, open the level-data help
entry, save it as `/files/user/my_rooms.json`, and set `LEVEL_FILE` to that path
in their Python copy. Renaming the Python file must not change which rooms it
loads. Use explicit absolute paths, with no dependence on the current working
directory, import name, `__file__`, or automatic sibling-file discovery.
Show the selected level path in the debug inspector and load-error diagnostics.
Missing/invalid custom JSON must report the problem rather than silently loading
the supplied rooms. The loader reads JSON as data, never via `eval` or `exec`.

The guide should distinguish three recovery actions:

- **Restart Level:** rebuild in-memory state using the current engine and loaded
  room definition. It does not undo source edits or reload edited disk files.
- **Save and rerun:** load the saved Python and JSON again using the existing IDE
  run/reset workflow; verify module caching cannot retain an older engine copy.
- **Restore the example:** reopen the supplied help source or JSON and save a
  fresh user copy. Restore code and rooms independently; retain experiments
  under separate names. Do not automatically overwrite student work on launch,
  reset, or a TartLab update.

The help originals are update-managed baselines. Students should download copies
of code/rooms they want to keep at a particular version; restoring from Help
uses the version currently installed. Game saves and restart never write to the
Python or JSON source. Syntax errors, exceptions, and infinite loops are expected
learning outcomes: document the existing interrupt/reset/IDE recovery route,
which must remain usable even when the student's game no longer runs. Avoid
catch-all error handling that hides the traceback or silently restores rules.

### Browser and distribution integration

The browser [tab implementation](src/ide/www/js/tabs.js) now routes `.json` to
the existing text editor and supports normal save, while Run/Set as App remain
unavailable for JSON. JSON syntax highlighting can follow later.
The current [save flow](src/ide/www/js/main.js) and
[user-file endpoint](src/ide/ide.py) already allow non-Python filenames; verify
the complete help-open/save-user-copy/reopen path instead of adding a new upload
or project system. Register the room file in the help manifest for discoverability.

`makedist.py` already copies the chosen help tree and selects modern assets
separately. Verify IDE execution, selected-app startup, a renamed Python copy,
and loading both bundled/custom JSON in Phase 1. Update the builder only if
those checks demonstrate a gap. Keep this example in modern help/assets rather
than `src/lib`, which is also copied into legacy distributions.

`main()` owns the complete resource lifetime. Validate room data, check input and
layout capabilities, then acquire game ownership and allocate the canvas/art.
Use `try/finally` to close canvas transfer buffers and discard app-owned caches
on exit or error; restore UI ownership through the existing platform API when
returning to UI. Restart replaces level state and reuses compatible art resources
without acquiring a second surface. Reset input state at ownership changes.

## Logical state and engine contract

Use flat arrays indexed by `y * 16 + x` for the 192 cells. Coordinates are
zero-based, with `(0, 0)` at the top left; north decreases `y`. Bounds checks must
happen before indexing so negative Python indices cannot wrap around a room.

| Layer/state | Contents |
| --- | --- |
| Terrain and visual variant | Floor, wall, dirt, water, false wall, exit; retain the variant digit separately from behavior. |
| Objects | Empty, required key, diamond, boulder. |
| Actors | Player, stationary snakes, spiders, stationary spear emitters; stable IDs, integer positions, facing, and per-actor timer state. |
| Features | Teleporter twin lookup derived from map labels and location-triggered messages. |
| Effects | Growing/stopped spear occupancy, pending explosions, short visual effects. |
| Level state | Remaining keys, exit activation, status, elapsed simulation time, collected score, bonus, and once-only message flags. |
| Session state | Room index, banked score from completed rooms, pause/debug state. |

Maintain cell occupancy lookups for actor/object/effect queries. Allocate terrain
and object arrays once per level; keep actor/effect storage bounded by the room
size. Use small records and integer type constants compatible with MicroPython.
Avoid heavyweight host-only dependencies in the runtime. A source level is never
mutated: restart reconstructs all mutable state from its validated definition.

Suggested narrow interfaces, to be finalized during Phase 1:

```python
pack = load_level_pack(LEVEL_FILE)      # JSON I/O, followed by validation
definition = validate_level(pack["levels"][0], level_index=0)
state = create_state(definition)
step(state, input_state, dt_ms=10)       # No display, I/O, or wall-clock reads
renderer.present(state, changes)       # Read-only view of logical state
run(pack, start_level=0, debug=False)   # Device-facing session, called by main()
```

The engine owns reusable per-step change/event storage. Events such as
`MOVED`, `COLLECTED`, `TERRAIN_CHANGED`, `DIED`, and `COMPLETED` identify cells and
actors; they do not contain pixel rectangles. The renderer accumulates all
changes from simulation steps since its last presentation. It owns previous
visual positions, animation progress, and screen damage. Debug trails allocate
only when enabled.

### Explicit interaction predicates

Do not use a single `solid` flag for every system. Define app-local functions
such as `can_player_enter`, `can_spider_enter`, `accepts_boulder`,
`blocks_snake_ray`, `blocks_spear_ray`, and `is_explosion_destructible`. Each reads
the relevant layers. Both the runtime and debug display use these same queries.

The following are proposed version-1 defaults where the request leaves a choice.
Record them in tests and the authoring guide before introducing affected rooms.
Visual variants never change these properties.

| Cell contents | Player | Spider | Pushed boulder destination | Snake/spear ray |
| --- | --- | --- | --- | --- |
| Empty floor | Enter | Enter | Accept | Clear |
| Wall or unrevealed false wall | Wall blocks; false wall opens for player | Block | Reject | Block |
| Dirt | Remove and enter in the same attempt | Block | Reject | Block |
| Water | Block | Block | Consume boulder; turn this cell into floor | Clear |
| Key or diamond | Collect and enter | Block | Reject | Block |
| Boulder | Attempt one-cell push | Block | Reject; no chain push | Block |
| Locked exit | Block | Block | Reject | Block |
| Active exit | Enter; completion checked last | Block | Reject | Clear |
| Snake or spear emitter | Fatal snake contact; emitter blocks | Block | Reject | Block |
| Spider | Fatal contact | Other spiders block | Reject | Block |
| Growing spear | Dangerous contact | Block | Reject | Block |
| Stopped spear | Solid, harmless obstacle | Block | Reject | Block |

Rays ignore their own emitter and test the player before treating any other
occupancy as a blocker. Teleporter markers on floor and visual-only effects do
not block rays. Teleporter locations reject boulders in the first version, so pads
cannot be covered accidentally. Actor contact rules also apply on teleport
arrival. A spider may enter the player's cell to kill the player.

## Mechanics and deterministic event resolution

### Player, objects, and completion

One eligible movement attempts exactly one cardinal step. A failed attempt still
consumes that movement interval; holding a direction never repeatedly tries in
the same simulation tick. A fresh press moves at the next eligible tick; holding
repeats at the configured interval. Direction changes do not reset the cooldown.
Releasing input stops movement. Resolve competing directions to one documented
choice, such as the most recently pressed direction; never synthesize diagonals.

A push checks the destination before changing anything. On success, move the
boulder and then move the player into its old cell as one transaction. Water
consumes the boulder and becomes floor in that transaction. On failure, neither
position changes. Boulders cannot be pulled, crush actors, enter dirt, collect
items, or push another boulder in version 1.

Collect keys/diamonds on entry and remove each object exactly once. A false wall
uses its matching wall sprite until the player attempts entry, then permanently
becomes floor and admits the player. Dirt is similarly cleared and entered in
one move. A failed unrelated interaction must not reveal or clear another cell.

All `K.` objects are required keys. Derive `remainingKeys` from those objects,
update it on collection, and reconcile it at the end of a step. Keys cannot be
destroyed or created by explosions in the initial rules. The exit is active
before the first input in a zero-key room. Otherwise collecting the last key
activates it in that same simulation step. Completion requires a living player
on the active exit after all hazards and environmental changes are resolved.
Death wins over completion when both could occur in one step.

Restart must be available during play, after death, and while paused. It restores
objects, terrain, actors, traps, keys, messages, bonus, timers, and initial facing.
Keep a room-local score ledger and bank it only on completion so restarting
cannot farm diamonds. Suggested adjustable scoring: 100 per diamond and a
`bonusStart` of 500 decreasing by one per second of unpaused simulation time,
clamped at zero. The bonus is a score incentive, not a death timer. Pause, death,
and completion freeze simulation. Persistent high scores can follow later.

### Teleportation

Each used map label `T0` through `T9` identifies exactly two locations within the
same room. Both operate identically; neither has a permanent source/destination
role. The loader builds a symmetric cell-to-twin lookup from those map cells.
No teleporter coordinates, links, or overrides are supplied in metadata.

Entering either location immediately transfers a moving actor to its twin,
with no pixel travel or diagonal intermediate cells. Apply this to
the player and spiders; stationary actors and boulders do not teleport.

Use one hop per cell-entry event. Arrival does not recursively trigger another
pad, allowing bidirectional pairs without infinite bouncing. An actor must leave
and re-enter a location to trigger it again. Preserve actor direction and cooldown.
Both locations expand to object-free floor plus a teleporter feature. They cannot
contain authored keys or diamonds, accept boulders, or receive explosion drops.
If the twin becomes blocked for the arriving actor (for example by another spider
or a stopped spear), the entering actor stays on the location it just entered.
It does not retry automatically while stationary; leave and re-enter to retry.
Player/enemy contact at an otherwise legal arrival location is resolved as a lethal
collision. Spiders cannot land on another enemy. Dry-run movement queries must
use the same teleport rules as committed movement, including during trapped-spider
checks. Resolve immediate hazards at the arrival cell before any further action.

In normal play all teleporter locations look like floor; debug mode reveals the
labels and twin links. This is a display policy in the Python file, with no
per-location visibility metadata. Changing it to show pads reveals both twins
equally and does not change their operation.

### Snakes

Snakes remain stationary, but flip horizontally to point toward the player.
If the player shares a snake's row, walk cell by cell
toward the player and stop at the first configured blocker. An unobstructed ray
kills immediately; there is no projectile or reaction delay. Snakes scan both
horizontal directions and never vertically. Check contact with the snake too.

Recompute after player interactions, teleport arrival, enemy movement/removal,
and cover-changing effects. With only 192 cells, a straightforward bounded scan
is preferable to an incremental line-of-sight cache until profiling shows need.
A stationary player can die when a spider moves out of the way or an explosion
removes a protecting boulder. Keys and diamonds are cover until collected.

### Spiders

Each spider's starting cell, heading, and wall-following mode come entirely from
its map token: `Xn`, `Xe`, `Xs`, `Xw` mean `followLeft`; `XN`, `XE`, `XS`, `XW`
mean `followRight`. The second character gives the initial cardinal heading;
there is no omitted/default heading. The first character is always uppercase `X`.
Use the room's `spider_ms` interval, or the Python default when omitted, and give
each spider its own deadline. Spider metadata entries and per-spider overrides
are not part of this format. Runtime movement may change heading; restart restores
the heading and following mode from the map.

For left-following movement, try left, forward, right, then backward relative to
the current heading. Right-following reverses the side preferences. Choose the
first legal direction, move one cell, and adopt that heading. Turns do not consume
a separate interval. An open room therefore still has deterministic behavior.

Process simultaneously due spiders in stable source-map/actor-ID order, updating
occupancy after each move. Later spiders see earlier moves; they never overlap,
swap through each other, or push objects. They continue while the player is idle.

After eligible enemy moves, check every live spider for any legal direction,
even if its own timer was not due. A spider with no legal move is removed and
queues one explosion. Determine the trapped set from one occupancy snapshot, then
remove that set together, so removal order cannot free a spider inconsistently.
An initially trapped spider follows this rule on the first simulation step.

### Spear traps

Each stationary emitter gets its cardinal direction from `RN`, `RE`, `RS`, or
`RW` in the map and has states `IDLE`, `EXTENDING`,
and `STOPPED`. In `IDLE`, scan along its facing. An unobstructed player activates
it; the first extension is due one projectile interval after activation. There
is no extension during the activation scan itself.

While extending, retain the shaft and advance the tip exactly one cell per due
projectile interval. Reaching the player kills; reaching an edge or blocking
object stops before that cell. Do not damage, consume, or push the blocker.
If the newly added tip is immediately followed by a blocking cell, transition
to stopped in that same advance. Existing spear cells are dangerous while the
trap is extending, including on teleport contact.

Stopped shaft cells remain solid and harmless until level restart. The trap does
not retract or rearm in version 1, even if its original blocker later disappears.
Spear emitters and other spears block extension. A snake uses the shaft as cover.
Use stable trap IDs when more than one trap advances in a tick.

### Explosions and environment

Proposed default footprint: the destroyed spider's cell plus its four orthogonal
neighbors, clipped to the room. Default destructible types are boulders and dirt.
Provide validated rule metadata to select supported destructible types and
diamond generation, rather than arbitrary executable callbacks in level data.
Keep walls, false walls, keys, exits, teleporters, other actors, and spears
protected in version 1. Water is not filled by an explosion.

Resolve pending explosions as one deduplicated batch. Clear eligible objects or
terrain, resolve player damage within the footprint (default: lethal), then
optionally place diamonds on newly cleared empty floor and the empty blast
center. Never replace a key, exit, teleporter, occupied actor cell, or solid
effect. Use a deterministic on/off generation rule initially; seeded randomness
is unnecessary. Overlapping blasts cannot generate or score a diamond twice.
There are no secondary actor explosions in the first version.

Damage happens once on resolution; the brief explosion animation has no lasting
collision effect. Flush immediate contact and snake-ray checks after the batch,
so destroyed cover cannot grant an extra safe tick. A newly clear spear firing
path is evaluated in the next trap stage, at most one simulation quantum later.

## Timing and the required update order

Keep rendering and simulation independent. Start with a 10 ms simulation quantum,
which divides the suggested player (110 ms), spider (150 ms), and projectile
(40 ms) intervals. Each moving actor/trap owns its deadline; no timer resets when
an unrelated system acts. Accept configurable positive integer intervals; with
the initial scheduler, nonmultiples of 10 ms are serviced on the next simulation
boundary with the quantization documented. Advance deadlines from their prior
due time to avoid cumulative drift. Reject intervals shorter than 10 ms in the
initial validator, so each actor has at most one action due per quantum.

Use `FrameClock(frame_ms=50, update_ms=10, max_updates=10)` as the initial
20 fps presentation setting. A fixed 60 ms frame setting yields about 16.7 fps
when hardware measurements favor it. Select a tested setting at startup, with
an explicit app override; do not vary it opportunistically frame by frame or
branch on board identity. Sprite animation never controls collision or timers.

At each frame, collect input and execute the due simulation quanta in order, then
present their accumulated changes once. Timestamp/queue edges so a new press is
not applied retroactively to every catch-up step. Holding a direction can repeat
only at player deadlines. The real-time clock uses wrap-safe `ticks_diff` and
`ticks_add` through the existing helper; logical time is elapsed simulation time.

The existing `FrameClock` drops excess backlog after its catch-up bound. Report
`dropped_update_ms` and missed deadlines; never fast-forward positions or skip
collision steps to compensate. An isolated stall can slow simulation, but steady
overruns fail the performance gate and require optimization or the slower fixed
presentation setting. Reset/rebase the clock on restart and resume so paused
wall time is never replayed. Input polling must remain responsive when no step
is due. No filesystem access or asset decoding belongs in the running loop.

Every simulation quantum follows this order, even when the player is idle:

1. Process eligible player movement intent.
2. Resolve the movement transaction, including pushing, digging, and revealing.
3. Collect entered objects.
4. Resolve player teleportation to the paired location.
5. Resolve immediate player hazards, including contact and snake exposure.
6. Move enemies whose timers expired; resolve each enemy's teleporter entry.
7. Resolve enemy/player collisions.
8. Determine trapped spiders, remove them, and queue explosions.
9. Recalculate snake line-of-sight hazards using current occupancy.
10. Activate/advance traps and projectiles whose independent deadlines are due.
11. Resolve queued explosions/environmental changes and resulting immediate hazards.
12. Reconcile remaining-key state.
13. Activate the exit if `remainingKeys == 0`.
14. Complete the level if a living player occupies its active exit.

After death is recorded, latch that result, finish already committed environmental
transactions consistently, and suppress further player input and any completion
event. Freeze subsequent simulation quanta until restart. Emit death/completion
only once.

## Data-driven rooms and validation

Use a separate `grid_puzzle_levels.json` from the first implementation. Its root
is an object with `"version": 1` and a nonempty `"levels"` array of room objects.
Version the pack once, rather than repeating it in each room. The loader uses
`json.load()` and passes room dictionaries into the same pure validator used by
host tests. A map is exactly twelve strings, each containing sixteen two-character
tokens separated by whitespace. Additional whitespace inside row strings is
allowed; token length and spelling are strict.

Teach JSON's double-quoted strings, lowercase `true`/`false`, and absence of
comments or trailing commas. Put explanatory comments in the Python source and
authoring guide. Catch JSON/file/schema errors with the selected filename and
useful field/room coordinates; preserve the underlying error details in the
console. Do not promise parser line numbers that the device's JSON decoder may
not supply. Parse once on game startup, build mutable state only for the active
room, and reuse validated definitions for restart. Measure the decoded pack's
heap cost and set a documented file-size/room-count limit if needed, with clear
errors rather than truncated input. Keep user room data editable JSON throughout.

| Token | Meaning |
| --- | --- |
| `..`, `P.`, `E.` | Floor, player start, exit |
| `#0` through `#9` | Wall art variants |
| `K.`, `D.`, `O.` | Required key, optional diamond, boulder |
| `W0` through `W8` | Nine water edge/center variants; `W9` is invalid |
| `d0` through `d9` | Dirt art variants |
| `F0` through `F9` | False wall matching the corresponding wall variant |
| `S.` | Stationary snake; flips to point horizontally towards player |
| `RN`, `RE`, `RS`, `RW` | Spear emitter facing north, east, south, west respectively |
| `T0` through `T9` | Teleporter locations; each used label occurs exactly twice per room |
| `Xn`, `Xe`, `Xs`, `Xw` | Spider facing north, east, south, west respectively; `followLeft` |
| `XN`, `XE`, `XS`, `XW` | Spider facing north, east, south, west respectively; `followRight` |

The loader expands a token into layers: for example, `K.` means floor plus a key,
`Xn` means floor plus a north-facing, left-following spider, and `T3` means floor
plus a teleporter location paired with the room's other `T3`. Walls need not
enclose a room; out-of-bounds is always blocked. Preserve token case when parsing:
uppercasing the map would change spider behavior. The guide should show paired
examples such as `Xe`/`XE` so students can recognize the case distinction.

Spider placement, heading, and follow mode are fully specified by the map.
Teleporter placement and pairing are also fully specified by the map. Other
actors may still use supported metadata fields; the current spear emitter can
override its interval there, while its position and direction come from the map.
The following is a complete JSON file containing one small original room.
The coordinate-keyed metadata list is called `actors`; it annotates map actors
without creating duplicates.

```json
{
  "version": 1,
  "levels": [{
    "name": "First Crossing",
    "bonusStart": 500,
    "timers": {
        "player_ms": 110,
        "spider_ms": 150,
        "projectile_ms": 40
    },
    "actors": [],
    "messages": [{
        "text": "Push a boulder into water to make a crossing.",
        "loc_x": 3,
        "loc_y": 2
    }],
    "rules": {
        "explosion_destructible": ["BOULDER", "DIRT"],
        "explosion_diamonds": true,
        "explosion_hurts_player": true
    },
    "map": [
        "#0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. P. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. .. .. O. W4 .. .. .. .. K. .. E. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. d0 d1 .. #1 .. .. .. .. .. .. .. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. D. .. .. .. #0",
        "#0 .. .. .. .. .. .. #1 .. .. .. .. .. .. .. #0",
        "#0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0 #0"
    ]
  }]
}
```

The wall divides the room at column 7, leaving one water crossing. A candidate
solution from `(2, 2)` is east three times, south twice, then east nine times,
pushing the boulder into the water and collecting the key before reaching the
exit. Validate this as a timed replay once the engine exists. The final teaching
rooms also need playtesting; structural validation alone establishes neither
solvability nor teaching quality.

The following metadata example is a partial room object for a room containing
`RW` at `(12, 7)`. It overrides that spear's interval, not its map-defined heading.
It does not refer to the preceding example map. There are no spider annotations
or teleporter metadata records.

```json
{
  "actors": [
    {"x": 12, "y": 7, "step_ms": 40}
  ]
}
```

Spider and spear headings must be encoded in their valid map tokens. Effective
intervals follow Python defaults, then room timers, then a supported non-spider
actor override. In particular, all spiders use the effective room `spider_ms`;
independent deadlines do not imply per-spider metadata.
Keep presentation rate in app configuration rather than enemy metadata.
Messages trigger once on player entry at their location and use a HUD/banner.
If the player starts on a message, show it when the room opens. Messages
open an explicitly paused panel, and enemies do not continue moving.

Validate before acquiring expensive render resources where possible:

- Correct pack version, nonempty levels array, field types, and known field
  names at both pack and room scope. Reject booleans
  where integer coordinates/intervals are expected, unknown rule names, and
  unsupported property values with useful field paths.
- Exactly 12 rows, 16 tokens per row, valid two-character symbols, one player,
  and one exit. Count keys from the map instead of accepting a supplied count.
- For each label `T0` through `T9`, count its occurrences within this room. Zero
  is allowed; otherwise require exactly two distinct cells, so each location has
  one and only one twin. Reject singletons and groups of three or more, reporting
  the label, count, and coordinates. Labels may be reused independently in other
  rooms; never pair across rooms. Build both lookup directions only after validation.
- All eight spider tokens decode to the stated heading/following mode. Reject
  invalid direction letters, lowercase `x`, and obsolete `XL`/`XR` tokens instead
  of guessing a heading. Likewise reject the obsolete spear token `T.` and
  require one of `RN`, `RE`, `RS`, `RW`.
- Integer in-bounds metadata coordinates and unique actor annotations matching
  compatible map actors. Reject annotations targeting spiders, heading overrides
  for map-defined actors, and the obsolete `teleporters` metadata field. Validate
  message coordinates independently; a message may refer to a teleporter cell.
- Legal initial terrain/occupancy for every actor and feature after layer
  expansion. Teleporter locations must be object-free floor.
- Cardinal directions, sensible positive timers at least one simulation quantum,
  nonnegative score values, supported destructibles, and valid message locations.
- Resource bounds derived from the 192-cell board; no silent dropping of actors,
  projectiles, messages, or required coverage when a limit is exceeded.

Report errors as concise diagnostics such as
`room 2 "Crossing", row 4, column 7: unknown token 'W9'`, consistently indicating
zero-based map coordinates. Host validation can collect all errors; device load
should show a readable failure and provide a safe exit. Treat unreachable-key
heuristics and immediately dangerous starts as author warnings where appropriate.
Structural validation does not prove that a room can be solved. Timed solution
replays establish that supplied campaign rooms have at least one valid solution.

## Rendering, controls, and original artwork

### Complete-room layout

The native board is `16 * 16` by `12 * 16`, or 256 by 192 pixels. Use
`DirectCanvas` with an app-chosen orientation that fits this board and controls;
do not copy the portrait assumption from Racer/Testris. Try both orientations
using reported dimensions. Favor a landscape board with a control panel beside
it; on sufficiently tall displays, a board with controls below can also fit.

Reserve space for keys, score/bonus, room name/index, a four-way touch pad, and
Restart/Pause controls. Select the largest positive integer scale that fits the
board and those controls. Keep every tile the same square size and letterbox
unused space. A 2x board needs 512 by 384 pixels before UI. A layout incapable of
showing the 1x board plus usable controls is unsupported in this first version;
show a clear message and an existing platform navigation/reset route. Do not
crop rooms, scroll, or shrink their logical dimensions to fit.

Transform touch through the exact same rotation and logical viewport as drawing.
The existing `TouchGrid` is edge-triggered and cannot supply held-direction
repeat by itself. Use the platform's game-touch polling API in an app-owned
adapter to track press, held direction, and release, preserving keep-awake and
input-ownership behavior. Use existing named button events only for documented
mappings; never instantiate GPIOs in the app. Restart/Pause are edge-triggered
and must not leak a held gesture into the restarted/resumed level.

### Drawing and presentation

Draw terrain, floor features, objects, actors, effects, debug overlays, then UI.
Start with a correct full-room renderer as a reference. Add cell-based damage:
mark old/new actor cells, changed terrain/objects, spear segments, explosion
footprints, and affected UI. For interpolated actors, include the full previous
and current sprite bounds. Rebuild every contributing layer in a dirty region;
never erase a sprite by painting floor over whatever is beneath it.

Map dirty cells to rectangles, merge using `DamageTracker`, compose all changes,
then let one presentation coordinator call `show()`. Fall back to a full redraw
when damage is dense. The board does not scroll and needs no panel-scroll
acceleration. Validate dirty results against the full renderer on a fake canvas.

Begin with snapped movement. Optional short interpolation can use previous and
current cell positions, always reaching the destination before the actor's next
move. Teleports snap with a brief effect. Spear and blast effects should remain
readable at the selected frame rate. Animation never delays rule evaluation,
changes occupied cells, or supplies collision detection.

### TS16 asset pipeline

Create original 16x16 top-down pixel art with a consistent palette and strong
silhouettes. Keep source artwork and provenance with the host asset builder.
Reuse [convert_ts16.py](tools/convert_ts16.py) for format encoding rather than
introducing another runtime image format. TS16 is a file format, not the tile
size: its existing palette has fifteen opaque colors plus transparent index zero.

The initial atlas should contain floor, ten wall variants, ten dirt variants,
keys, diamonds, boulders, locked/active exits, directional player/spider art,
snake art, four emitter directions, spear tips/shafts, a short explosion sequence,
and a teleporter/debug marker. False walls reuse the corresponding wall pixels
exactly during normal play. Art variety must not imply different collision rules.

Arrange water variants in a 3x3 atlas block:

```text
W0  W1  W2    top-left corner, top edge, top-right corner
W3  W4  W5    left edge,       full water, right edge
W6  W7  W8    bottom-left,     bottom edge, bottom-right
```

`W4` contains only water pixels; outer variants depict the corresponding bank.
All nine occupy a full impassable logical cell. Honor explicit map variants;
do not silently rewrite them with an autotiler. Optional water motion can follow
after the basic atlas is complete.

The deterministic builder validates 16x16 cell alignment, palette/alpha limits,
required variants, and atlas coordinates. Store a preview and an atlas index.
Batch-extract only needed tiles/frames at level load through `SpriteSheet` and
release the decoder afterward. Account for prepared spans and Python objects,
not just the small packed atlas. A 256x256 TS16 sheet would occupy 32,808 bytes;
a separate 256x192 RGB565 board buffer would add 98,304 bytes. Avoid that second
buffer unless measurements justify it: `DirectCanvas` already owns a framebuffer.

## Editor/debug support

Expose `DEBUG = False` in the Python file and a documented debug toggle.
This is an inspection mode over the same loaded room, not a second engine.

- Show row/column labels, grid lines, and a selected-cell coordinate/type readout.
- Outline false walls with their underlying variant visible.
- Mark every teleporter location with its `T0`-`T9` label and draw one undirected
  link per twin pair, including normally invisible pads. Neither twin is singled
  out as a source or destination.
- Draw enemy heading arrows and left/right follow indicators.
- Show a bounded recent path trail per moving enemy and its next legal move.
  Compute previews without mutating state; do not promise a long-range route
  through changing obstacles.
- Draw snake rays and spear firing paths with their first blocking cell marked.
- Display remaining keys, actor deadlines, missed frame deadlines, and dropped
  simulation time in an optional inspector.
- Provide debug pause and one-simulation-step advance. Overlays never alter
  gameplay rules; explicit pause/step is the only timing change.

Allocate debug-only storage on demand; keep its drawing helpers in the same
Python file for inspection and modification. In normal play hidden pads remain
hidden and false walls must be pixel-identical to matching walls.

## Development phases and exit criteria

Phases are dependency-ordered, with reviewable deliverables and tests. Performance
and hardware observations remain unproven until measured; no dates or frame-rate
guarantees are implied by this plan.

| Phase | Deliverables | Exit criteria |
| --- | --- | --- |
| 1. Contracts and integration skeleton | Schema/symbol table, proposed-rule decisions, one-file code outline, JSON pack/loader, host fixtures, JSON text editing support, and layout/input probe. | Invalid packs/rooms fail clearly; integer layers and fresh state work; renamed Python copy uses its own functions and chosen JSON; browser opens/saves/reopens both file types; intended display/input layouts are feasible. |
| 2. First playable room | Player, floor/wall, keys, diamonds, locked/active exit, boulders, water filling, restart, room-local score, fixed-step loop, primitive full redraw. | A small original room can be completed; zero-key rooms work; no pulling/chain pushes; atomic failed pushes; 110 ms player timing independent of presentation; restart restores everything implemented. |
| 3. Terrain and teleport interactions | Dirt, false walls, map-labelled teleporter twins, arrival hazards, messages, original TS16 atlas and rebuild tool. | Exactly-two-per-label validation, travel in both directions, blocked arrivals, no bounce/retry while stationary, hidden appearance, variant validation, and 1x/integer-scaled art pass tests; gameplay uses original art. |
| 4. Complete hazard engine | Stationary snakes, all eight map-defined spider variants, trap detection, explosions/diamonds, map-directed spear traps, full fourteen-stage update order. | Heading/follow mode decode correctly without metadata; enemies act while the player is idle; simultaneous-event and cover-removal tests pass; every requested hazard interaction has a fixture; death beats completion. |
| 5. Rendering and debug inspection | Dirty renderer, optional brief animation, all requested debug overlays, shared input/drawing transforms, performance instrumentation. | Dirty/full render equivalence; overlays reflect actual queries; hidden features stay hidden normally; repeated restart releases transient resources; device workloads support a fixed 15-20 fps setting. |
| 6. Teaching rooms and authoring guide | Original room sequence, progressively combined mechanics, timed solutions, engine code map, rule-change/break/restore exercises, and manifest entries for Python, JSON, and guide. | Every campaign room validates and has a successful replay; student can edit rooms independently, change actual engine behavior in a user copy, and recover after breaking it; manual review confirms hints, fairness, and controls. |
| 7. Packaging and qualification | Modern payload checks, relevant host/MicroPython and browser build checks, physical operator checklist and observations, release-impact report. | Python/JSON/assets survive installation/update and selected-app startup; user engine/rooms stay independent of help originals; legacy payload remains isolated; actual physical results and applicable release gates pass. |

Suggested teaching sequence for Phase 6:

1. Movement, optional diamonds, keys, and the exit.
2. One irreversible push and Restart Level.
3. A boulder bridging a deliberately narrow water crossing.
4. A snake as a hazard; a boulder or collectible as protective cover.
5. A spider's predictable path; dirt and boulders redirecting it.
6. Trapping a spider to clear dirt/create a useful opening and diamonds.
7. A spear as a hazard; its stopped shaft as a solid barrier that redirects a
   spider or blocks a snake ray.
8. False walls and teleporters, followed by a combined-system final room.

Refine this into a compact campaign after playtesting; split a lesson when one
room introduces too many concepts. Timing should allow observation and planning.
Provide safe places to wait and generous controls rather than requiring narrow
reflex windows. Do not reuse the supplied inspiration's room layouts or story.

The guide also needs a progression for learning from the engine, starting with
concrete, easy-to-find functions in the student's Python copy:

1. Follow one move through input, `step`, collision, and drawing; observe it with
   debug pause/step.
2. Change diamond scoring or a default movement interval. Explain how room/actor
   timer overrides interact with the Python defaults so a change is observable.
3. Change `blocks_snake_ray` so a diamond no longer provides cover.
4. Change the spider's turn priority and compare its path overlay before/after.
5. Extend a terrain interaction or tile type, updating code and JSON validation.
6. Introduce a simple syntax/runtime error, inspect the diagnostic, recover the
   IDE if needed, and restore a working code copy while keeping custom rooms.

Tests document the shipped rules; students may intentionally change those rules
and their expected outcomes. Source hashes in diagnostics/replays identify an
experiment, not authorize which engine edits may run. Do not impose a whitelist
of editable constants, automatic rule repair, or a second hidden engine.

## Verification and efficient operator workflow

Use host tests with explicit elapsed times and scripted directions. Load the
actual single Python source with autostart disabled through one test helper;
exercise its pure engine functions under CPython without fake display/platform
modules. Inject a fake canvas only for rendering tests. Do not extract, copy, or
reimplement rules for tests. Keep tests focused on rules and outcomes, not
private implementation details.

| Area | Required evidence |
| --- | --- |
| Loader | JSON syntax, pack version/shape, missing/invalid custom path with no fallback, all token families, 16x12 shape, one start/exit, zero keys, bounds, metadata duplicates, malformed types, illegal terrain/occupancy, unknown rules/timers. |
| Player/objects | Cardinal-only movement, no edge wrap, failed-push atomicity, no pulling/chains, water consumption, dirt/false-wall entry, last-key activation, single collection, restart and score rollback. |
| Teleportation | Zero or exactly two cells per label; singleton/triple/quadruple rejection; independent labels and rooms; symmetric lookup/travel; player/spider use, blocked or lethal arrival, no arrival bounce or stationary retry, preserved direction/timer, metadata rejection. |
| Snake | Horizontal-only danger, every configured blocker, key/diamond removal, teleport arrival, enemy cover moving, explosion cover removal. |
| Spider | All eight case-sensitive map tokens, invalid/obsolete token and metadata rejection, restored initial heading on restart, room timer with independent deadlines, both priority orders, turning/dead ends, autonomous movement, actor conflicts, collisions, trapped-set snapshot, deterministic explosion footprint/drop rules. |
| Spear | Directional activation, obstructed path, exactly one cell per projectile deadline, contact death, stopping before blockers/edges, harmless solid shaft, no rearming, multiple traps. |
| Ordering/time | Simultaneous deadlines, player/enemy crossing, death versus exit, idle player, pause/resume, wrap-safe clock, bounded catch-up, identical traces at 50/60 ms rendering cadences when no time is dropped. |
| Rendering/input | Full/dirty equivalence, rotation/clipping, no stale sprites or rays, matching normal/false-wall art, integer scale, held/released directions, fresh restart gestures. |
| Integration | Help and renamed user copies, autostart-disabled load without device side effects, selected JSON path, browser JSON save/reopen without Run, packaged files/assets, modern/legacy separation, launch/error/cleanup paths, edited rule executed from user source, independent code/room restoration. |

Automate campaign validation and solution replay with one short host command:

```powershell
python tools/check_grid_puzzle_levels.py
```

This command loads the bundled JSON and single Python source by default,
validates every room, and replays `tests/fixtures/grid_puzzle/solutions.json`.
It requires a successful timed solution for each bundled room and writes detailed
results to `build/grid_puzzle/validation.json`. The Phase 2 trace completes First
Crossing in 2540 ms of simulation with 100 collected points and 498 bonus points.
These are scripted results, not a physical playtest or fairness assessment.
Accept explicit `--engine`, `--levels`, and `--solutions` paths for a trusted
local experiment; report selected paths. Custom rooms without `--solutions` get
structural checks only and explicitly report replay pending. Replay records include engine-source and room-data
hashes, schema version, timed press/release/wait events, and expected completion/
score. Hash and validate these mechanically. Running the command again must not
require an agent to reread every room or transcript.

During implementation run the relevant new `unittest` modules and existing
timing/canvas/sprite/profile checks when those integration points change. Check
the JSON browser change with relevant frontend checks and the production build.
Use the repository's normal distribution checks for packaging. Do not
start a local development server or probe localhost as a final sanity check.

The device benchmark should provide fixed representative and worst-case room
workloads, including multiple moving spiders, long spears, dense explosions,
water animation if enabled, and debug overlays. Record simulation, drawing, and
transfer time, p50/p95/max frame work, deadlines missed, dropped simulation time,
heap before/after repeated restart, and source/asset hashes. State a supported
fixed frame period only after measuring it; if normal worst-case room play cannot
sustain at least 15 fps, fix the workload/renderer before claiming completion.
Do not reduce required room coverage to obtain a passing number.
Also record startup time and free heap after compiling the full Python source,
decoding the JSON pack, and preparing art; a copyable file still has a real
MicroPython code/data memory cost.

Generate an operator form for physical observations: readable full room, all
direction controls, release behavior, restart/pause, water-edge appearance,
hidden walls/pads, visible hazards, launch from a saved copy, and repeated level
changes. Include an observed rule change in a renamed Python copy, an independent
JSON edit, recovery from a broken game, and restoration from Help. Derive device
capabilities and artifact hashes automatically; the
operator supplies actual observations and judgment. Unperformed checks stay
pending, and failing checks stay failed. Save full logs and a concise resumable
status report instead of requiring repeated manual transcription.

When preparing a modern release, start with
[RELEASE_QUALIFICATION.md](RELEASE_QUALIFICATION.md) and
[tools/qualification_session.py](tools/qualification_session.py). An app-only
change can use the existing release-impact process; any necessary shared
platform/input change expands the affected checks. The Phase 1 development build
is not a release candidate or physical qualification evidence.

## Decisions to revisit with evidence

Proceed with the documented defaults instead of blocking implementation on a
large preference questionnaire. Revisit only when a test, device measurement,
or playtest demonstrates a reason:

- The final original title and visual theme, without changing the engine schema.
- Layout/orientation and the fixed 50 or 60 ms presentation period on supported
  capabilities; narrower displays may need a separately scoped presentation mode.
- The proposed dig-and-enter, one-hop teleport, explosion footprint/damage/drop,
  and stopped-spear rules before finalizing dependent teaching rooms.
- Sprite cache representation and optional interpolation after measured memory
  and frame timing establish room for them.
- Additional controls, persistent scores, or a graphical
  editor as follow-up work once the requested first version is complete.
