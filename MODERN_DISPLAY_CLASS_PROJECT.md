# Modern direct-display class improvement project

Status: Complete, including ST7796 rotation-270 panel-scroll qualification

Related evidence: [`tests/DRAWING_PERFORMANCE.md`](tests/DRAWING_PERFORMANCE.md)

## Objective

Improve the speed, consistency, and maintainability of the modern direct-display
classes while preserving a small framebuffer-style interface suitable for
students. LVGL may provide optimized internal operations, but students must not
need to import LVGL, construct draw buffers, understand the panel bus, or manage
DMA memory.

The eventual public model should be one `DirectCanvas` whose logical orientation
is selected with a rotation setting. The existing `PortraitCanvas` behavior will
then become a compatibility spelling of a rotated `DirectCanvas`, rather than a
separate implementation. That consolidation is a future phase, not a requirement
of the initial performance work.

## Product principles

- Keep the student API cohesive: construct a canvas, call familiar drawing
  methods, and call `show()` for either the full canvas or a dirty rectangle.
- Keep LVGL and native display-driver objects behind TartLab's Python classes.
- Retain exclusive direct-surface ownership for student applications. This
  project will not turn games into LVGL object trees or LVGL-managed applications.
- Depend only on the pinned MicroPython firmware, its LVGL binding, and
  TartLab-maintained Python libraries. Do not add a custom C extension.
- Preserve ordinary `framebuf` drawing semantics wherever possible, including
  colors, clipping, and the built-in text appearance.
- Optimize common operations without requiring students to select an optimized
  code path.
- Keep the implementation understandable enough that advanced students can read
  it, while isolating unavoidable low-level details in short private helpers.

## Current interface and measured problem

`DirectCanvas` owns a full RGB565 framebuffer and a small DMA-capable transfer
buffer. Its drawing methods come from `framebuf.FrameBuffer`. `show()` currently
packs each dirty rectangle one Python row at a time before submitting one or more
native surface writes.

`PortraitCanvas` wraps `DirectCanvas` and maps logical portrait coordinates into
the landscape framebuffer. Most simple primitives map efficiently, but rotated
text currently creates a monochrome glyph mask and visits every glyph pixel in
Python.

The measurements in `tests/DRAWING_PERFORMANCE.md` establish the baseline:

| Behavior | Current modern median | Relevant finding |
| --- | ---: | --- |
| DirectCanvas piece move | 37.20 ms | 27.71 ms is packing/loop work |
| DirectCanvas text redraw | 31.78 ms | 25.38 ms is packing/loop work |
| PortraitCanvas piece move | 68.01 ms | 42.10 ms is packing/loop work |
| PortraitCanvas text redraw | 159.16 ms | Both rotation and packing are expensive |
| PortraitCanvas text render only | 33.25 ms | Cached pre-rotated equivalent is 2.40 ms |

Equal-size dirty regions also took from 31.25 ms to 129.03 ms depending on
shape, while a single prepacked native write remained about 3.10 ms. The native
panel transfer is therefore not the primary slowdown. Python row packing,
excess transfer subdivision, and per-pixel portrait text rotation are the first
targets.

## Intended student-facing API

The first implementation should not require application changes. Existing code
continues to use `DirectCanvas` or `PortraitCanvas`:

```python
canvas = DirectCanvas(game_surface())
canvas.fill(background)
canvas.text("Score: 10", 8, 8, foreground)
canvas.show((0, 0, 120, 16))
```

The future consolidated interface should have the same drawing calls and expose
logical dimensions after applying a quarter-turn rotation:

```python
canvas = DirectCanvas(game_surface(), rotation=90)

print(canvas.width, canvas.height)  # Logical, not physical, dimensions
canvas.fill_rect(10, 20, 40, 30, color)
canvas.text("Hello", 10, 60, color)
canvas.show((10, 20, 100, 60))      # Logical dirty rectangle
```

The final rotation contract must define the direction of positive rotation and
cover `0`, `90`, `180`, and `270` degrees. Existing `PortraitCanvas` output and
touch coordinates are the compatibility reference for its corresponding
quarter turn. Unsupported values should fail clearly at construction time.

`DirectCanvas.scroll(dx, dy)` retains ordinary deferred framebuffer semantics:
it moves pixels in the owned RAM buffer in logical canvas coordinates, leaves
the newly exposed pixels unspecified as `framebuf` does, and becomes visible
through a later `show()`. Panel scanout scrolling is a different operation and
must not silently change those semantics.

A later portable canvas operation may combine a region scroll, deterministic
filling of its exposed band, and presentation in one call:

```python
canvas.scroll_region(
    (0, 24, canvas.width, canvas.height - 24),
    dx=0,
    dy=-8,
    fill=background,
)
```

The exact name and signature should be finalized with its tests, but its
contract must be identical on every board. A capable surface may accelerate
the operation; every other surface must provide a pixel-equivalent software
copy and flush. Students must not call controller registers or choose a
board-specific path.

Applications should never call `lv.draw_buf_t.copy()`, `lv.draw_label()`,
`lv.draw_sw_rotate()`, or the underlying surface transport directly for routine
drawing. Those are private implementation options of `DirectCanvas`.

## Implementation plan

### Phase 1: compiled dirty-region packing

Replace the Python row-copy loop inside `DirectCanvas.show()` with the pinned
LVGL binding's compiled draw-buffer copy operation:

- Describe the full canvas buffer as an LVGL RGB565 draw buffer with the full
  framebuffer stride.
- Describe the existing DMA-capable bounce buffer as a tightly packed LVGL draw
  buffer.
- Copy each dirty source area into the bounce buffer with
  `lv.draw_buf_t.copy()` and then submit it through the existing public direct
  surface.
- Keep all LVGL imports, color-format selection, buffer lifetime rules, and area
  conversion private to the canvas implementation.
- Verify the pinned firmware's `RGB565_SWAPPED` interpretation against known
  non-symmetric colors; black-and-white tests cannot detect byte-order errors.

The number of rows per transfer should use the bounce buffer's byte capacity,
not a fixed row count. A narrow dirty rectangle can therefore use more rows per
write and, when it fits, be sent in one transfer. This should remove most of the
observed shape sensitivity without increasing DMA memory.

If wrapping one of the buffers as an LVGL draw buffer is unsafe on the pinned
binding, retain the current Python implementation as a correct fallback and
evaluate the Viper fallback described below. Do not expose this selection in
the student API.

### Phase 2: compiled rotated text and sprite operations

Remove the per-pixel Python loop from rotated text. Prototype the following
internal approaches in order, accepting the first one that preserves the public
rendering contract and meets the performance target:

1. Render the existing 8-pixel `framebuf` text into a small reusable mask and
   rotate or expand that buffer with an LVGL compiled draw operation.
2. Use an LVGL canvas layer and `lv.draw_label()` if its font metrics and pixels
   can match the documented student-visible text behavior.
3. Cache prepared rotated glyph or string sprites when repeated text makes that
   useful without unbounded memory growth.

Use `lv.canvas.copy_buf()` or draw-buffer copying for prepared opaque sprites
where it improves upon `framebuf.blit()`. Sprite preparation may do more work
once so that repeated `draw_sprite()` calls stay inexpensive. Cache ownership,
limits, and invalidation must remain deterministic and internal.

LVGL's `draw_sw_rotate()` is an available low-level option for small temporary
buffers. It should not be used to rotate the full display during every refresh.

### Phase 3: one rotation-aware DirectCanvas

After the performance paths are stable, move coordinate mapping into
`DirectCanvas`:

- Add a rotation setting expressed in quarter turns or degrees.
- Make `width` and `height` report logical dimensions.
- Apply the same logical coordinate system to pixels, lines, rectangles, text,
  sprites, framebuffer scrolling, dirty rectangles, and pixel reads.
- Ensure clipping and partially off-screen drawing behave consistently at every
  rotation.
- Align touch-coordinate helpers with the same rotation definition so drawing
  and input cannot drift apart.
- Avoid rotating the full framebuffer merely to implement logical orientation.

Initially, `PortraitCanvas` should remain as a thin compatibility wrapper or
alias that constructs `DirectCanvas` with the corresponding rotation. Existing
help applications should continue to work unchanged during that period. A later
cleanup may migrate examples to `DirectCanvas(rotation=...)` and deprecate the
old class deliberately; removal is not part of this project unless separately
approved.

#### Implementation result

Phase 3 was completed on 2026-09-03:

- `DirectCanvas` accepts `0`, `90`, `180`, and `270` degrees or zero through
  three quarter turns, and exposes logical `width`, `height`, and normalized
  degree-valued `rotation` attributes.
- Pixel reads and writes, lines, rectangles, ellipses, polygon outlines, text,
  prepared sprites, framebuffer scrolling, and dirty rectangles share one
  logical-to-physical mapper without rotating the full framebuffer.
- Filled polygons use logical scanlines so the pinned `framebuf` edge-rounding
  behavior remains pixel-exact after rotation. Native-orientation canvases and
  rotated polygon outlines continue to use compiled `framebuf` operations.
- `TouchGrid(rotation=...)` applies the inverse mapper to physical touch input.
- `PortraitCanvas` and `PortraitTouchGrid` are now compatibility subclasses
  that select the historical portrait rotation.
- Host reference tests cover primitives, clipping, text, sprites, dirty areas,
  scrolling, and touch mapping at every rotation. Temporary raw-REPL probes on
  the COM3 modern fixture passed these checks against the pinned MicroPython
  `framebuf` implementation without device writes.

`DirectCanvas.scroll(dx, dy)` now maps the logical vector to the underlying RAM
framebuffer and remains deferred until `show()`. It does not issue panel scroll
commands. The optional presentation accelerator below remains independent of
the completed rotation-consolidation gate.

### Independent track: capability-driven scroll presentation

Some panel controllers can change the scanout start address without
retransmitting the retained pixels. This is a presentation accelerator, not an
alternate definition of `framebuf.scroll()`. It is optional per board and is
not a prerequisite for completing Phase 3.

The implementation should use these boundaries:

- Keep the full RAM framebuffer canonical at first. An accelerated scroll may
  still move its RAM pixels, but it should use panel scrolling to avoid sending
  the retained display region and transfer only the newly exposed band.
- Put the capability below `DirectCanvas`, on the direct surface or a helper it
  owns. The surface must advertise supported logical axes, region constraints,
  fixed-area support, wrapping behavior, and any rotation restrictions.
- Let shared canvas code ask whether one concrete region, vector, and composite
  rotation can be accelerated. Unsupported axes, regions, rotations, and
  distances must take the normal software path without an application change.
- Keep controller command bytes and scanout behavior in a reusable controller-
  family adapter. A board's declarative `BOARD_CONFIG` may reference that
  adapter and contain unavoidable geometry or wiring constraints, but must not
  implement scrolling or duplicate driver behavior.
- Express advertised directions in final logical canvas coordinates. The
  implementation must compose the panel's native memory axis, the configured
  panel rotation, and the additional `DirectCanvas` rotation instead of
  assuming that controller-vertical means application-vertical.
- Serialize scroll-register commands with DMA transfers and require direct-game
  ownership. Never send them while LVGL owns the display or a transfer is in
  flight.
- Once panel scanout has moved, retain the scanout origin and translate every
  later dirty write. Writes that cross the wrap seam must be split correctly so
  the RAM framebuffer, pixel reads, and visible panel remain coherent.
- Restore the neutral scanout origin before LVGL ownership resumes, then force
  the normal LVGL invalidation/redraw. Also restore or invalidate the state on
  rotation changes, canvas closure, reset, and exceptional cleanup.

The first accelerated version deliberately optimizes transfer volume rather
than eliminating the RAM move. A ring-backed framebuffer would require
wrap-aware implementations of drawing, reads, clipping, and dirty-region
packing; it should be considered only if a focused benchmark demonstrates that
the remaining RAM copy is important.

The LilyGO T-Display-S3 Pro is the first candidate, not a special case in shared
canvas code. Its ST7796 panel is native `222 x 480`, while its current TartLab
surface is `480 x 222` at panel rotation `270`. The native vertical-scroll axis
may therefore become a logical horizontal axis, and another `DirectCanvas`
rotation may transform it again. In addition, the ST7796S documentation says
vertical scrolling mode should use `MADCTL.MV = 0`; the current landscape
configuration must be physically tested before the adapter advertises support
for it. If that configuration is unsupported or unreliable, it must fall back
to software rather than changing the established display orientation solely to
claim acceleration.

### Phase 4: MicroPython code emitters only where needed

Use LVGL's compiled operations before applying decorators to broad sections of
Python code.

`@micropython.native` is appropriate for a short, computation-heavy Python
helper when measurement shows a worthwhile improvement. It is unlikely to fix
the current bottleneck by itself because the costly operation is repeated
Python buffer slicing and loop dispatch. Do not decorate orchestration methods
that primarily call `framebuf`, LVGL, or the surface transport.

`@micropython.viper` is the fallback for a small buffer transformation that
LVGL cannot express efficiently, such as a strided RGB565 copy, rotation, or
format expansion. A Viper helper must:

- be private and narrowly scoped;
- validate buffer sizes, dimensions, and coordinates in ordinary Python before
  entering unchecked pointer code;
- cast buffer pointers once outside its inner loop;
- document integer width, alignment, byte order, and clipping assumptions;
- avoid allocation, callbacks, and long-running scheduler starvation; and
- have a normal-Python reference implementation used by host tests.

No optimization is accepted merely because it uses `native` or `viper`; it must
win the focused device benchmark and remain correct at all supported rotations.

#### Implementation result

Phase 4 was completed on 2026-09-03 with two narrowly scoped changes:

- `swap565_buffer()` validates the buffer in ordinary Python and then uses a
  private Viper byte-pair kernel. The existing Python implementation remains
  the host and unavailable-emitter fallback.
- `fill_surface()` now prepares its reusable transfer tile with compiled
  `framebuf.fill()` instead of visiting every RGB565 pixel in Python.

No drawing orchestration method was decorated. The existing LVGL draw-buffer
copy and software rotation remain the preferred compiled operations for dirty
regions, text, and prepared sprites. Python and `native` byte-swap candidates
were retained only in the repeatable diagnostic comparison; `native` did not
provide enough improvement to ship.

On the COM3 modern fixture, Viper reduced median byte-swap time from 694.44 ms
to 26.18 ms for a 213,120-byte full-display buffer (26.5x faster). It ranged
from 9.2x to 26.9x faster over the tested 128-byte through 213,120-byte sizes.
Compiled filling reduced a 15,360-byte transfer tile from 34.73 ms to 0.52 ms
(66.4x faster). All variants produced matching bytes, the public wrapper
rejected odd-length and read-only buffers before entering Viper, and the
DMA-capable surface buffer was accepted by `framebuf` on-device.

## Testing strategy

### Host tests

Extend `tests/test_modern_app.py` with fake LVGL draw buffers and surfaces to
cover:

- full-screen and dirty-region copies;
- narrow, wide, one-row, one-column, clipped, and empty areas;
- adaptive transfer sizing and exact surface-write coordinates;
- cleanup after normal use and exceptions;
- non-symmetric RGB565 colors that expose byte swapping;
- text and sprite output against a pixel-exact reference; and
- eventually, every primitive, framebuffer-scroll vector, and dirty-area
  transform at all four rotations.

For the optional presentation-scrolling path, use a fake capability adapter and
compare every result with the software reference. Cover positive and negative
movement, distances at and beyond the region extent, every composite rotation,
unsupported-axis fallback, fixed regions, exposed-band filling, dirty writes on
both sides of the wrap seam, and cleanup during ownership changes and errors.

Keep a simple Python reference mapper for rotation tests. Compare optimized
output to that reference rather than duplicating optimized implementation logic
in the tests.

### Device experiments

Use `tools/drawing_diagnostics.py` and `tools/drawing_performance.py` as the
repeatable benchmark entry points. Add focused cases when necessary to compare:

- current Python packing versus LVGL draw-buffer copying;
- fixed-row versus byte-capacity-based transfer tiling;
- candidate rotated-text implementations;
- software region scrolling versus any capability-selected panel accelerator;
- Python, `native`, and Viper implementations of any remaining hot helper; and
- output checksums or sampled pixels as well as timing.

Report render, pack/copy, submit, wait, transfer count, and total time separately.
Record dimensions, dirty-region shape, firmware identity, and the implementation
variant with every result. Use medians over enough iterations to suppress one-off
startup and allocation costs.

Device benchmarking must run temporary code through raw REPL and must not flash
firmware. If a comparison requires different firmware, stop and ask the owner to
swap devices. Do not change firmware on the test fixture as part of this project.

A panel-scroll experiment must additionally record the controller orientation,
effective logical axis, fixed and scrolling areas, start-address sequence,
bytes avoided, exposed-band transfers, and behavior after a dirty write crosses
the wrap seam. Verify ownership handoff back to LVGL and repeat the test after
reset. Datasheet restrictions are hypotheses until the exact board and pinned
driver configuration pass this focused physical check.

### Regression coverage

Run the normal host suite, static checks, and pinned-MicroPython compatibility
checks applicable to `tartlabutils.modern_app`. Hardware results from temporary
working-tree code are engineering evidence only; they do not qualify a release.

## Acceptance criteria

The first two phases are complete when all of the following are true:

- Student applications require no LVGL knowledge and existing canvas calls keep
  their behavior.
- `DirectCanvas.show()` no longer performs a Python operation for every copied
  framebuffer row in its preferred modern path.
- Every dirty region uses the fewest surface writes allowed by the existing
  bounce-buffer capacity.
- The equal-byte shape diagnostic is no longer dominated by Python packing, and
  copy time scales primarily with byte count rather than row count.
- Modern landscape piece and text redraw medians are no slower than the recorded
  legacy medians of 14.67 ms and 5.37 ms, or any miss is documented with stage
  timings identifying the remaining constraint.
- Rotated text rendering is at least five times faster than the current 33.25 ms
  render-only median, with pixel-correct output and bounded temporary memory.
- Full-screen redraw performance does not regress by more than 10% from the
  recorded 191.36 ms modern median.
- Repeated construction, drawing, showing, and closing do not leak DMA buffers
  or leave the display in the wrong ownership mode.
- No new C code, firmware change, or student-facing LVGL dependency is introduced.

The rotation-consolidation phase is complete when `DirectCanvas` passes the same
primitive, text, sprite, framebuffer-scroll, dirty-region, and touch-alignment
tests at all four rotations, and `PortraitCanvas` has become only a
compatibility layer. Hardware scrolling is not part of this gate.

A hardware scrolling path is accepted for an individual board and orientation
only when its declarative payload selects a reusable adapter, accelerated and
software results are pixel-equivalent, unsupported cases fall back correctly,
post-scroll dirty writes and ownership restoration remain coherent, a focused
device benchmark shows a material transfer or latency improvement, and the
exact panel configuration satisfies its documented constraints. Boards without
this capability continue to meet the common canvas contract through software.

## Explicit non-goals

- Converting Testris, other games, or student applications into LVGL-managed
  object trees.
- Exposing LVGL draw buffers, layers, labels, or display-driver calls as the
  normal student API.
- Adding or modifying firmware solely for these optimizations.
- Writing a custom C module or maintaining a TartLab-specific firmware fork for
  canvas performance.
- Removing `PortraitCanvas` before a compatible rotation-aware replacement and
  migration period exist.
- Changing the legacy `display_drv` implementation.

## Documentation references

- [LVGL 9.4 draw-buffer API](https://docs.lvgl.io/9.4/API/draw/lv_draw_buf_h.html)
- [LVGL 9.4 canvas documentation](https://docs.lvgl.io/9.4/details/widgets/canvas.html)
- [LVGL 9.4 label drawing API](https://docs.lvgl.io/9.4/API/draw/lv_draw_label_h.html)
- [MicroPython performance guide](https://docs.micropython.org/en/latest/reference/speed_python.html)
- [ST7796S controller datasheet](https://files.waveshare.com/wiki/common/ST7796S_Datasheet.pdf)
- [LilyGO T-Display-S3 Pro hardware repository](https://github.com/Xinyuan-LilyGO/T-Display-S3-Pro)
