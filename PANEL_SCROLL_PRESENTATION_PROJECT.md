# Capability-driven panel-scroll presentation

Status: complete; ST7796 rotation 270 hardware-qualified

Related plan: [`MODERN_DISPLAY_CLASS_PROJECT.md`](MODERN_DISPLAY_CLASS_PROJECT.md)

## Objective

Add an optional presentation accelerator for `DirectCanvas.scroll_region()`.
The RAM framebuffer remains canonical. A capable direct surface may move the
panel scanout origin and upload only the newly exposed band; every unsupported
case uses a pixel-equivalent software move and ordinary dirty-region flush.

`DirectCanvas.scroll()` is unchanged: it only moves RAM pixels and remains
deferred until `show()`.

## Public contract

```python
canvas.scroll_region(
    (0, 24, canvas.width, canvas.height - 24),
    dx=0,
    dy=-8,
    fill=background,
)
```

The operation clips the region to the logical canvas, moves retained pixels by
`dx` and `dy`, fills every newly exposed pixel, and presents the result before
returning. Distances at least as large as either region dimension fill and
flush the whole clipped region.

Acceleration is internal. Applications do not select a controller path and
cannot observe whether the surface accepted it except through timing.

## Architecture

- `DirectCanvas` owns portable RAM movement, deterministic exposed-band fill,
  logical rotation, and software fallback.
- A direct surface may implement `present_scroll(area, dx, dy, rotation)` and
  `scroll_capabilities(rotation)`. The area and vector are in final canvas
  coordinates; the surface composes the additional canvas rotation with its
  configured panel rotation.
- The reusable ST7796 adapter owns `VSCRDEF`/`VSCSAD`, scanout-origin state,
  wrap-seam address translation, DMA serialization, and neutral restoration.
- `BOARD_CONFIG` selects the adapter and records the board's qualification
  decision. Controller commands and behavior do not live in the board payload.
- A configured but unqualified rotation reports no accelerated axes and always
  takes the software path.

## Host acceptance

- Software output is identical with and without a capability.
- Positive and negative movement, overlong distances, diagonal fallback,
  clipping, and all four `DirectCanvas` rotations are covered.
- Supported regions upload only exposed bands.
- Unsupported axes and regions flush the whole changed region.
- Dirty writes are translated after scrolling and split correctly at the wrap
  seam.
- Scroll commands cannot race DMA or UI ownership.
- UI handoff, canvas close, command failure, and platform teardown restore a
  neutral scanout origin.

## ST7796 hardware gate

The LilyGO T-Display-S3 Pro uses an ST7796 surface of `480 x 222` at panel
rotation 270. Its native vertical-scroll axis therefore appears as the logical
horizontal axis. The ST7796S documentation warns that vertical scrolling
requires `MADCTL.MV = 0`, while this orientation uses `MV = 1`.

The board kept rotation 270 out of `qualified_rotations` until a temporary
raw-REPL experiment verified all of the following on the physical fixture:

1. Positive and negative start-address changes move the expected axis and
   direction without corrupting the fixed/visible area.
2. Newly exposed bands and later dirty writes remain coherent on both sides of
   the wrap seam.
3. Returning the start address to neutral and handing ownership to LVGL restores
   an ordinary full redraw.
4. The accelerated case materially reduces transferred bytes or latency.
5. Reset and a repeated run produce the same result.

If a future board or orientation fails any check, the adapter remains present
but that configuration must advertise no hardware-scroll capability. Changing
the established display orientation solely to enable scrolling is out of scope.

## Implementation result

Implemented on 2026-09-03/04:

- `DirectCanvas.scroll_region()` provides the portable move/fill/present API,
  uses compiled `framebuf.scroll()` for a full-canvas move, and falls back to a
  bounded scanline copy for partial regions.
- `tartlabutils.modern_st7796` provides the reusable controller-family adapter,
  final-coordinate capability reporting, fixed-area commands, retained origin,
  seam-aware writes, DMA serialization, and cleanup before LVGL ownership.
- The LilyGO board selects the adapter declaratively and advertises rotation
  270 after its automated and visual qualification passed.
- Host tests cover portable output at every rotation, supported and unsupported
  cases, both panel directions, fixed areas, seam repacking, command failure,
  closure, and source-lock integration.
- The COM3 raw-REPL diagnostic passed its automated checks. Full-width scrolling
  reduced transfers from 213,120 to 14,208 bytes and latency from about 102 ms
  to 32 ms. See [`tests/PANEL_SCROLL_HARDWARE.md`](tests/PANEL_SCROLL_HARDWARE.md).

The final held comparison used explicit yellow and blue section markers. The
owner confirmed that the hardware-scrolled and software-reference striped
frames were stable and visually identical despite the datasheet's `MADCTL.MV`
restriction. The rotation-270 gate is therefore complete.
