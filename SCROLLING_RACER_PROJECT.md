# Scrolling racer architecture and performance project

Status: Phase 4 implemented; Phase 5 not started

Related implementation:

- [`src/files/help/racer.py`](src/files/help/racer.py)
- [`src/lib/tartlabutils/modern_app.py`](src/lib/tartlabutils/modern_app.py)
- [`PANEL_SCROLL_PRESENTATION_PROJECT.md`](PANEL_SCROLL_PRESENTATION_PROJECT.md)
- [`tests/PANEL_SCROLL_HARDWARE.md`](tests/PANEL_SCROLL_HARDWARE.md)

## Objective

Refactor the scrolling Racer help example so its drawing cost and gameplay
timing remain predictable as interactive road objects are added. The design
must support collectibles, hazards, collision responses, road-relative
objects, objects with steady horizontal motion, and staged increases in road
speed without tying simulation speed to the time required to draw a frame.

The result should remain approachable as a student-facing example. It should
use a few small, explicit classes and functions rather than introduce a generic
entity-component system or a reusable game engine prematurely.

## Product principles

- Simulation state is authoritative. Framebuffer pixels are never used to
  determine collisions, collection, object identity, or movement.
- Input, simulation, interaction, rendering, and frame pacing are separate
  steps even if they remain in one example file.
- Road speed is expressed as distance over time, not pixels per rendered
  frame.
- Spawning and difficulty progression are based on accumulated road distance
  or another explicit game-state metric, not loop counts.
- One rendering coordinator owns dirty regions and display presentation.
  Individual entities never call `canvas.show()`.
- Per-board identities, dimensions, controller names, and accelerator details
  do not appear in the game. Optional acceleration is selected only through
  reported final-coordinate capabilities.
- The steady-state frame loop avoids racer-owned heap allocation wherever
  practical so garbage collection does not introduce avoidable frame jitter.
- Optimizations must preserve a correct portable rendering path.

## Current implementation and measured problem

The current example already avoids rebuilding the entire scene in Python on
every frame. It keeps a canonical RGB565 framebuffer, prepares the repeating
road bands ahead of time, and calls `DirectCanvas.scroll_region()` so a capable
surface can move panel scanout and upload only the newly exposed band.

That is an effective transfer optimization when panel scrolling is available,
but the current loop has several limitations:

- `FRAME_DELAY` is slept after all update, drawing, and transfer work. The
  actual frame interval is therefore work time plus 32 ms rather than a
  controlled 32 ms target.
- `SCROLL_STEP` simultaneously represents road speed, per-frame movement,
  centerline phase granularity, and prepared-band height. These concerns must
  vary independently when road speed changes.
- Every scroll moves the retained track inside the RAM framebuffer. On an
  unsupported surface, the canvas then flushes the complete track region.
- The fixed player is moved by the framebuffer scroll and must be repaired
  every frame even when the player did not steer.
- `draw_centerline()` is vertically clipped but not horizontally clipped to
  the car's dirty rectangle. `redraw_car()` consequently restores every
  obstacle intersecting the same rows, including horizontally distant ones.
- Obstacles are positional lists with drawing-specific fields. There is no
  place for object type, velocity, collision shape, interaction behavior, or
  lifecycle state.
- The obstacle-list comprehension allocates a replacement list every frame,
  and filled-circle rendering performs repeated Python exponentiation and
  square-root work.
- A spawn frame performs an immediate object update and another player update
  instead of letting one rendering coordinator collect and flush damage.
- The prepared-band table contains only four-row bands at phases divisible by
  four. A variable scroll delta cannot reuse that table safely.

The hardware evidence in
[`tests/PANEL_SCROLL_HARDWARE.md`](tests/PANEL_SCROLL_HARDWARE.md) measured the
portrait racer's four-pixel fixed-header scroll at 38.39 ms with accelerated
presentation and 110.10 ms with software presentation. The accelerated case
transferred 1,776 bytes rather than 202,464 bytes, but both cases still moved
the canonical retained region in RAM. A 32 ms sleep after that operation
necessarily produces a substantially slower and workload-dependent frame
rate.

## Intended architecture

### Game state

`GameState` owns only gameplay state:

- player position and collision bounds;
- active entities;
- accumulated road distance;
- current road speed and speed stage;
- score, lives, or crash state when those concepts are introduced;
- spawn scheduling; and
- deterministic randomization inputs when tests need them.

The state update must not draw or present pixels. It returns or records state
changes that the renderer can turn into damage.

### Road state and speed progression

`RoadState` owns the visual centerline phase and a fixed-point distance
accumulator. A `SpeedSchedule` maps explicit distance thresholds to speed
levels. Changing a speed level changes distance advanced per unit of time; it
does not change the target render cadence.

Fixed-point integer arithmetic is preferred over floating point in the hot
loop. Fractional distance carries between updates and is converted to an
integer screen delta only when rendering requires pixels. Spawning consumes
the same authoritative distance so object spacing remains stable across frame
rates and speed changes.

If prepared scroll bands remain in use, screen deltas should be quantized to a
small base unit. A `RoadBandCache` then owns sprites keyed by both integer
delta and resulting centerline phase. Every band required during a speed
transition must be prepared before the transition becomes visible; creating a
new band in the frame loop would add allocation and rotation jitter.

### Entity model

Use a lightweight `Entity` object rather than positional lists. The initial
model should contain only fields needed by the planned gameplay:

- entity kind;
- fixed-point horizontal and longitudinal position;
- previous and current visible bounds;
- horizontal velocity;
- road-relative or screen-relative movement policy;
- collision geometry;
- visual reference;
- draw layer; and
- active state.

An entity kind describes its visual, collision category, and player-contact
behavior. For example, a coin kind can increment score and deactivate itself,
while a cow kind can trigger a crash. This avoids putting a growing chain of
type checks in the main loop while keeping runtime entity instances small.

The simulation updates an entity's horizontal velocity independently of road
speed. Road-relative objects receive the camera's longitudinal movement in
addition to any object-specific movement. Horizontal boundary behavior such
as bouncing, reversing, wrapping, or leaving the road belongs to an explicit
movement policy rather than the renderer.

Interactions are resolved after simulation and before rendering. Circle
collisions should compare squared distances; rectangle or mixed shapes can use
their logical bounds. Collection or removal marks both the old and current
bounds dirty so no stale pixels remain.

### Background reconstruction

Replace the car-specific repair routine with a road background renderer that
can reconstruct any clipped rectangle. Given one dirty rectangle and the
current road phase, it:

1. draws only the intersecting grass;
2. draws only the intersecting asphalt;
3. draws only the horizontally and vertically clipped centerline fragments;
4. redraws every active entity whose bounds intersect the rectangle in layer
   order; and
5. redraws the player last when its bounds intersect the rectangle.

This makes overlapping objects, removal, collection, crashes, and horizontal
movement use one correctness path. It also removes the current need to redraw
every obstacle that merely shares rows with the player.

### Damage coordinator

One `DamageTracker` collects old and new bounds from every visible change.
Before rendering, it clips damage to the track, merges rectangles that overlap
or are close enough for one transfer to be cheaper, and limits pathological
rectangle growth. It should not blindly union distant regions because the
additional pixel transfer can cost more than another small transaction.

The coordinator rebuilds all pixels in every final dirty rectangle before it
presents any of them. Entities may expose a draw operation or visual
descriptor, but they do not flush the canvas themselves.

The tracker should reuse its internal rectangle storage. Spawns and occasional
content creation may allocate outside the hot path, while steady movement and
rendering should avoid racer-owned allocations after warm-up.

### Rendering strategies

Two strategies should be evaluated behind the same game-state and damage
interfaces.

#### Dirty-region animation

The grass, road surface, and road edges are visually static in the current
example. The impression of movement can be produced by updating only:

- a narrow vertical centerline strip;
- the old and new bounds of each moving entity; and
- the player when it steers or intersects other damage.

This removes the retained full-track RAM move and prevents a full-track panel
flush on surfaces without scanout acceleration. It is the first alternative
that should be implemented and benchmarked. The shared background
reconstruction path ensures that center markers and overlapping entities are
restored correctly.

#### Scanout scrolling

The existing `canvas.scroll_region()` path remains a useful candidate when a
surface can accelerate the exact track region and the scene contains enough
road-relative objects to make individual damage expensive. Road-relative
pixels ride the scroll without being redrawn. Fixed objects, horizontally
moving objects, removed objects, and the player contribute damage after the
scroll.

If both strategies remain, selection must use reported logical scroll
capabilities and measured workload behavior. The racer must never branch on a
board identity, display resolution, transport, or controller. Controller
commands, scanout mapping, wrap seams, and ownership remain below
`DirectCanvas` in reusable shared adapters.

The first implementation may choose dirty-region animation universally if it
meets the performance gates on all supported modern targets. Maintaining two
paths is justified only when device measurements show a material benefit.

### Frame clock and simulation loop

Replace the unconditional sleep with an absolute-deadline `FrameClock`. The
clock uses wrap-safe tick operations and separately tracks elapsed real time,
fixed simulation steps, and the next render deadline.

A representative loop is:

```text
read input
measure elapsed time
run zero or more bounded fixed simulation updates
resolve collisions and interaction events
render accumulated damage once
sleep only until the absolute render deadline
record an overrun when the deadline has passed
```

Fixed updates prevent movement and collision results from changing with draw
cost. Catch-up work must be capped so a slow frame cannot cause an unbounded
update spiral. When the cap is reached, the clock records the dropped time or
updates according to an explicit recovery policy rather than silently adding a
full delay.

An initial 20 FPS target is realistic for the existing measured accelerated
scroll path. The final target should be selected from p95 measurements of the
new dirty renderer under the representative entity workloads below; 30 FPS is
preferred if it leaves useful headroom.

## Drawing optimizations

The architecture changes remove the largest sources of unnecessary work.
These smaller optimizations should then be measured:

- Prefer the compiled `canvas.ellipse(..., True)` primitive for circles if its
  raster shape is suitable. Otherwise cache horizontal circle spans once for
  each supported radius instead of taking a square root on every redraw.
- Pre-render repeated visuals and rotate them before gameplay. If transparent
  prepared sprites are needed, add that as a tested, reusable `DirectCanvas`
  feature rather than introducing a portrait-specific sprite path in Racer.
- Cache center-marker geometry or a narrow repeating road texture.
- Compact inactive entities in place instead of replacing the entity list on
  every frame.
- Cull entities and dirty rectangles before drawing. A simple longitudinally
  ordered list is sufficient until measurements justify spatial indexing.
- Keep display calls centralized so spawn, movement, removal, and player
  damage can be coalesced deliberately.
- Measure the remaining canonical RAM copy before considering a ring-backed
  framebuffer. Ring-aware drawing, clipping, reads, and dirty packing are too
  complex to add without evidence that they are still the limiting cost.

## Implementation plan

### Phase 1: baseline and deterministic timing

- Add a bounded device benchmark for the current Racer frame.
- Record update, RAM drawing, presentation, total frame interval, transferred
  bytes, transaction count, and missed deadlines.
- Replace `FRAME_DELAY` with the absolute-deadline frame clock.
- Introduce fixed-point road distance, time-based road speed, and a speed
  schedule with at least two configured stages.
- Preserve the current visuals and four-pixel average starting motion while
  timing changes are isolated.

Exit gate: equal simulated elapsed time produces equal road distance and spawn
spacing despite different synthetic render delays.

#### Implementation result

Implemented in the working tree:

- The reusable `tartlabutils.timing.FrameClock` provides wrap-safe absolute deadlines,
  remaining-budget sleep, bounded fixed-step catch-up, missed-deadline counts,
  and explicit dropped-update accounting.
- The reusable `tartlabutils.motion.StagedMotion` owns unit-agnostic fixed-point
  distance, quantized movement, and distance-selected speed stages. Road and
  centerline state remain in the Racer app rather than the shared library.
- Racer now targets 20 FPS with a 50 ms fixed simulation step. Its initial
  80-pixel-per-second speed retains four pixels of normal-frame movement. A
  second stage begins at 1,200 pixels and raises speed to 120 pixels per
  second without changing the render deadline.
- Prepared road bands are warmed for every four-pixel delta reachable through
  the two-update catch-up cap and for every compatible centerline phase.
- Spawning uses authoritative road distance rather than a per-frame counter.
- `tools/racer_benchmark.py` runs a bounded working-tree workload through raw
  REPL and reports update, render, CPU-render, surface-write, scroll-command,
  total-work, and frame-interval timing alongside bytes, transactions,
  deadlines, update counts, scroll pixels, and heap observations.
- Deterministic host tests cover remaining-budget sleep, fixed cadence,
  overruns, catch-up limits, dropped time, tick wraparound, starting speed,
  speed changes, quantization, and independence from synthetic render cost.

The benchmark does not flash firmware or write the device filesystem.

#### Device baseline

On September 4, 2026, a 20-frame working-tree probe was collected from the
modern 222 by 480 fixture on COM3. Median frame work was 49.032 ms and p95 was
52.150 ms against the 50 ms target. Two measured frames exceeded the work
budget. Median rendering was 48.604 ms, median surface-write time was 4.911 ms,
and median CPU rendering time was 42.549 ms. The normal frame transferred
3,226 bytes in two transactions. The clock recorded 21 missed deadline periods
during the capture, while no fixed simulation time was dropped. The complete
machine-readable result is in
`hardware_test_artifacts/scrolling-racer/phase1-modern.json`.

### Phase 2: entities and interactions

- Replace obstacle lists with lightweight entity objects and entity-kind
  descriptors.
- Add old/current bounds, road-relative movement, horizontal velocity, active
  state, and collision geometry.
- Implement a generic player-contact event path with placeholder collectible
  and hazard outcomes.
- Move spawning, culling, collision, and lifecycle changes into simulation
  code with no canvas calls.

Exit gate: host tests can simulate collection, hazard contact, horizontal
motion, boundary behavior, and off-screen removal without constructing a
display.

#### Implementation result

Implemented in the working tree:

- Racer's display-independent `RoadState`, `GameState`, `Entity`,
  `EntityKind`, circle collision descriptor, and interaction-event record can
  be imported on a host without constructing a canvas or surface.
- Entity positions use fixed-point coordinates. Each entity retains previous
  and current visible bounds and independently describes road-relative
  movement, horizontal velocity, boundary policy, visual, collision radius,
  draw layer, lifecycle state, and exactly-once contact state.
- Bounce, wrap, and deactivate boundary policies are explicit and testable.
- Generic player-contact dispatch invokes kind-provided collectible and hazard
  behaviors. The placeholder outcomes update score or crash state and emit
  one interaction event without reading framebuffer pixels.
- Fixed updates own entity motion, contact resolution, off-screen culling,
  in-place compaction, and distance-based spawning. Injected random functions
  make spawn tests deterministic, and newly spawned entities do not receive an
  immediate extra update.
- The Phase 2 simulation records spawned and removed entities so a renderer
  can repair lifecycle changes even when inactive entities are compacted.

The complete host suite passes 347 tests. An in-memory raw-REPL smoke on the
COM3 MicroPython fixture also parsed the working-tree Racer source and verified
that one collectible contact emitted one event, incremented score once, and
removed the inactive entity. The smoke did not write the device filesystem.

### Phase 3: clipped damage compositor

- Generalize road background reconstruction to an arbitrary clipped
  rectangle.
- Add the reusable damage tracker and layer-ordered redraw.
- Remove the car-specific same-row obstacle repair.
- Eliminate immediate entity-owned or spawn-specific display updates.
- Use compiled circles or cached circle spans.
- Add the dirty-region animation strategy and measure it with several entity
  counts.

Exit gate: pixel-reference tests cover overlapping entities, movement,
collection, removal, centerline intersections, player steering, and every
track edge.

#### Implementation result

Implemented in the working tree:

- The reusable `tartlabutils.damage.DamageTracker` clips to caller-defined
  bounds, cost-merges nearby regions, caps pathological region growth, and
  reuses storage allocated during construction.
- Racer's app-owned `RoadRenderer` reconstructs an arbitrary clipped track
  rectangle from simulation state. It horizontally and vertically clips the
  background and center markers, redraws active entities in layer order, and
  draws the player last.
- `DirtyRegionAnimator` collects center-strip, old/new entity, removal,
  spawn, and steering damage. The renderer reconstructs every final region
  before it issues any `canvas.show()` call.
- The car-specific same-row repair, scanout scroll, prepared-band table, and
  per-spawn presentation path have been removed from Racer. The first Phase 3
  strategy is universally selected without any board or controller test.
- Circle spans are cached during renderer setup for the marker, player, and
  configured entity radii. Clipped redraws no longer perform square roots.
- Pixel-reference host tests compare dirty reconstruction with a complete
  redraw after overlap, movement, collection/removal, marker phase changes,
  and steering. Separate checks cover horizontal marker clipping and all four
  track edges.
- `tools/racer_benchmark.py` now injects the working-tree compositor in memory
  and records dirty pixels and regions alongside timing, bytes, transactions,
  deadlines, update counts, and heap observations for configurable entity
  loads.

The complete host suite passes 358 tests.

#### Device measurement

On September 4, 2026, a 20-frame measurement per workload was collected from
the modern 222 by 480 fixture on COM3. With no entities, median frame work was
11.521 ms and p95 was 22.040 ms. With the representative three-entity scene,
median work was 29.909 ms, median transfer was 9,208 bytes across four
transactions, and p95 work was 93.266 ms; 8 of 20 frames exceeded the 50 ms
work budget. Eight and sixteen moving entities produced median work of
68.889 ms and 154.117 ms respectively and missed the work budget on every
sample.

The three-entity median improves on the Phase 1 scanout baseline, but its tail
and the heavier workloads do not yet meet the performance objective. Phase 4
must compare dirty reconstruction with scanout scrolling by workload rather
than removing the scanout candidate. The complete machine-readable result is
in `hardware_test_artifacts/scrolling-racer/phase3-modern.json`.

### Phase 4: variable speed and scroll comparison

- Exercise at least two road speeds without changing the target frame period.
- If scanout scrolling remains beneficial, introduce the prepared band cache
  keyed by delta and phase and warm it before use.
- Make fixed, road-relative, and horizontally moving entities share the same
  damage reconstruction rules after a scroll.
- Compare dirty-region animation and scanout scrolling through reported
  capabilities and representative object loads.
- Retain only strategies whose measured benefit justifies their complexity.

Exit gate: a speed transition changes road distance per second, centerline
motion, entity motion, and spawn rate coherently without a frame-cadence
change, incorrect band, or visible stale pixel.

#### Implementation result

Implemented in the working tree:

- `DirectCanvas.scroll_capabilities()` now reports surface capabilities in
  final logical canvas coordinates. Racer requires logical vertical scroll,
  fixed areas, wrapping, and a full orthogonal axis; its selection has no
  board, controller, transport, or geometry inference.
- `RoadBandCache` prepares every four-pixel-aligned delta and center phase
  reachable through the bounded two-update catch-up. The current schedule
  warms 4-, 8-, and 12-pixel bands before gameplay.
- `ScanoutAnimator` uses beginning-of-frame entity bounds and the same clipped
  `RoadRenderer` reconstruction as dirty animation. Stationary road-relative
  entities ride the scroll, while fixed entities, horizontal movement,
  steering, spawning, collection, hazards, and removal repair their carried
  and authoritative bounds after the scroll.
- The interactive example applies a measured workload policy after checking
  capabilities. It uses scanout for at least three stationary road-relative
  entities and retains dirty animation for empty, fixed, or horizontally
  moving workloads.
- Pixel-reference tests cover every warmed delta/phase pair and compare the
  scanout result with a full redraw for mixed movement, spawn, collection,
  removal, centerline overlap, and the player. A deterministic transition
  test verifies that 80- and 120-pixel-per-second stages advance distance,
  center phase, entities, and distance-based spawning together.
- `tools/racer_benchmark.py` compares both strategies at both configured
  speeds with empty, 3-, 8-, and 16-entity stationary and mixed-motion loads.
  It records logical scroll capabilities, command time, dirty regions and
  pixels, setup heap cost, transfer data, deadlines, and the earlier timing
  and heap metrics.

#### Device comparison

On September 4, 2026, the 20-sample matrix ran on the modern 222 by 480 COM3
fixture at the unchanged 50 ms target. The device reported logical vertical
scroll with fixed areas, wrapping, and full orthogonal-axis coverage.

For an empty road, dirty animation met the work deadline on all samples at
both speeds: median work was 16.38 ms at 80 pixels per second and 16.05 ms at
120, with p95 below 28 ms. Scanout took about 53 ms median and missed 19 of 20
deadlines because its retained framebuffer copy alone remained about 46 to
48 ms of median CPU render time.

Scanout became materially beneficial as stationary road-relative population
grew. At eight entities, its p95 work was 63.79 ms at 80 pixels per second and
63.76 ms at 120, versus 270.38 ms and 237.34 ms for dirty animation. At 16
entities, scanout p95 was 69.50 ms and 71.43 ms, versus 423.12 ms and 428.02
ms. Stationary scanout transfer stayed at two transactions and a median 3,018
bytes at the starting speed or 4,978 bytes at the higher stage, independent
of entity count.

Mixed fixed and horizontal workloads require reconstruction after either
strategy and did not justify scanout selection. Neither strategy qualifies
the representative three-entity workload at the current 20 FPS target:
dirty animation had the lower median but substantial tails, while scanout was
more consistent but slightly over budget. Phase 5 must select the final
cadence and address the remaining frame outliers. The machine-readable result
is in `hardware_test_artifacts/scrolling-racer/phase4-modern.json`.

### Phase 5: performance qualification and cleanup

- Remove remaining racer-owned steady-state allocations where practical.
- Record median, p95, and maximum frame work and frame interval.
- Record missed deadlines, dirty pixel counts, bytes transferred, display
  transactions, entity count, and garbage-collection observations.
- Run a held visual comparison for tearing, wrap seams, centerline corruption,
  stale objects, and collision removal.
- Update this document with the selected renderer, target cadence, measured
  headroom, and final implementation result.

Exit gate: the accepted workload meets the performance and functional criteria
below on every supported modern display profile under test.

## Testing strategy

### Host tests

- Wrap-safe deadline calculations and overrun recovery.
- Fixed simulation results under varying render durations.
- Fixed-point road accumulation and integer screen-delta carry.
- Distance-based spawning and speed-stage transitions.
- Horizontal entity movement and each boundary policy.
- Collision checks and exactly-once interaction outcomes.
- Entity removal and in-place list compaction.
- Dirty rectangle clipping, merging, and transfer-cost decisions.
- Background reconstruction at road edges and centerline phases.
- Layer ordering for overlapping road objects and the player.
- Prepared-band dimensions and pixels for every supported delta/phase pair if
  scanout scrolling remains.
- Pixel equivalence between accepted rendering strategies for deterministic
  scenes.

The game logic should accept injected clock and random sources so these tests
do not depend on real time or nondeterministic spawns.

### Device workloads

At minimum, benchmark:

1. an empty road with center markers;
2. the current normal road-object population;
3. a dense collectible population;
4. several horizontally moving objects;
5. overlapping objects near the player;
6. a burst of collection or removal events; and
7. each road-speed transition.

Measure update time, render time, synchronous wait time, full frame interval,
transferred bytes, transaction count, dirty rectangles, missed deadlines, and
racer-owned allocation behavior. Report p95 as well as medians because a
stable game is constrained by frame outliers rather than its best frames.

## Acceptance criteria

- Road and entity speed are functions of elapsed simulation time, not render
  count or drawing duration.
- At least two road-speed stages work at one unchanged target frame cadence.
- Spawn spacing remains distance-based through speed changes and delayed
  frames.
- Road-relative, fixed, and steady-horizontal entities can coexist.
- A collectible can deactivate and produce one interaction event without
  leaving stale pixels.
- A hazard can produce one crash event through the same interaction boundary.
- Collision logic does not inspect framebuffer pixels.
- Background reconstruction and layer redraw remain correct when entities
  overlap the centerline, player, track edge, or one another.
- No entity calls `canvas.show()` or surface methods directly.
- The accepted steady-state workload meets its selected frame deadline on at
  least 95% of post-warm-up frames, with missed frames reported rather than
  hidden by an unconditional sleep.
- The non-scroll rendering path does not flush the complete track merely to
  move a solid road background.
- Racer-owned steady-state allocations are eliminated or shown by measurement
  not to cause collection-related frame outliers.
- Rendering decisions contain no board identity, controller identity,
  electrical detail, or inferred capability based on display geometry.
- Host tests and device measurements document the selected renderer and its
  performance margin.

## Explicit non-goals

- Completing the final game content, art, scoring model, sound, menus, or
  difficulty curve in this project.
- Building a general-purpose game engine or entity-component framework.
- Moving display-controller behavior or board policy into the Racer example.
- Adding a ring-backed framebuffer before focused measurements show the
  canonical RAM move remains a relevant bottleneck.
- Guaranteeing one universal FPS number before the representative workloads
  are measured on supported hardware.
