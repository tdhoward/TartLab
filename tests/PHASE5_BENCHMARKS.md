# Phase 5 comparative graphics benchmarks

This document records the Phase 5 item 5 comparison on the same LilyGO
T-Display-S3 Pro PCB v1.1 used for the lifecycle gate. It qualifies the exact
modern reference for continued research; it does not select a production
firmware or alter the legacy release channel.

## Compared identities

- Legacy firmware: MicroPython 1.23.0 image SHA-256
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`
  with the qualified Candidate 9 payload
  `phase4-candidate9-6d930fd` restored from the 139-file pre-Phase-5 snapshot.
- Modern firmware: MicroPython 1.27.0/LVGL 9.4.0 reference image SHA-256
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`
  with modern adapter SHA-256
  `bca6731673279a8a1914886fd9fe6f99b40705b233497659154fc03617c372cc`.
  This adapter differs from the item 4 file only by treating LVGL 9.4's public
  boolean animation argument as `False` when the binding has no `ANIM` enum.
  The benchmark physically exercised that corrected progress-widget path and
  repeated UI/game/UI ownership transitions.
- Board CPU frequency: 240 MHz for both profiles.
- Display SPI configuration: 60 MHz for both profiles.
- Logical panel geometry and orientation: 480 x 222 RGB565 for both profiles.

## Locked matrix and instrumentation

`tools/phase5_benchmark.py` runs one MicroPython-compatible device program on
both profiles, validates the matrix before comparing results, and preserves the
raw JSON outside Git under `hardware_test_artifacts/phase5-item5`. Each final
row below contains 12 samples; the mode-switch row contains 25 iterations.

The raw transfer asset is deterministic, byte-swap-invariant RGB565 with
SHA-256
`989f95d2463c92a242c5db41a2d454e6cdf1c36c33a99a59aa05536aaec57e86`.
Geometry, byte count, buffer count, and submission count are identical between
profiles. Storage necessarily follows the public capability of each family:
native internal-DMA buffers on modern and MicroPython bytearrays on legacy.
This difference is part of the comparison, not an uncontrolled variable.

- 10% is one 48 x 222 transfer (21,312 bytes).
- 25% is one 120 x 222 transfer (53,280 bytes).
- 50% is two 240 x 111 transfers (106,560 bytes total). A single 106,560-byte
  modern allocation fails after LVGL owns its two transport buffers, so the
  same two-tile layout is used on legacy.
- Full-frame is 213,120 bytes in ten 480-wide transfers: nine 24-row buffers
  and one final 6-row buffer. This matches the modern LVGL transport-buffer
  height and avoids claiming a contiguous DMA frame that the target cannot
  allocate.
- Sprite movement uses two 48 x 32 buffers and redraws the union of the old and
  new 32 x 32 sprite over a static background.
- Scrolling uses two 480 x 24 buffers, shifts the viewport by four rows, and
  renders the incoming rows before the next transfer.
- The full-frame and solid-fill deadline is 33.333 ms (30 FPS). Partial,
  sprite, scroll, widget, and animation deadlines are 16.667 ms (60 FPS).

Modern sprite and scroll writes are submitted asynchronously. Their overlap is
estimated from a synchronous transfer baseline minus the wait remaining after
the next buffer is rendered. Legacy transfers are synchronous and therefore
report zero overlap. Raw REPL collection pauses the foreground IDE server, so
CPU availability is a service-headroom proxy rather than a live HTTP latency
claim.

## Raw RGB565 transfers

Times and throughput are medians. Parentheses contain p95 time and missed
deadlines out of 12.

| Region | Legacy | Modern | Modern result |
| --- | ---: | ---: | ---: |
| 10% | 8.338 ms, 2.556 MB/s (8.765 ms, 0) | 5.176 ms, 4.117 MB/s (5.246 ms, 0) | 37.9% faster |
| 25% | 20.111 ms, 2.649 MB/s (20.139 ms, 12) | 12.455 ms, 4.278 MB/s (12.524 ms, 0) | 38.1% faster |
| 50% | 40.294 ms, 2.645 MB/s (40.511 ms, 12) | 25.110 ms, 4.244 MB/s (25.243 ms, 12) | 37.7% faster |
| Full | 83.369 ms, 2.556 MB/s (83.494 ms, 12) | 58.418 ms, 3.648 MB/s (58.806 ms, 12) | 29.9% faster |

The 10% and 25% modern dirty rectangles meet 60 FPS; 50% does not. Neither
profile meets 30 FPS for the complete screen. The modern full-frame result is
about 17.1 FPS. It remains a wire-and-transaction metric, not the sole graphics
score.

## Rendered workloads

| Workload | Legacy median | Modern median | Modern result | Deadline misses |
| --- | ---: | ---: | ---: | ---: |
| Solid fill, total | 85.311 ms | 60.375 ms | 29.2% faster | 12 / 12 both |
| Sprite, total | 2.750 ms | 2.355 ms | 14.3% faster | 0 / 12 both |
| Scroll, total | 10.945 ms | 5.633 ms | 48.5% faster | 0 / 12 both |
| TartLab progress widgets, total | 291.704 ms | 25.136 ms | 91.4% faster | 12 / 12 both |

Solid-fill render/transfer medians were 1.577/83.677 ms on legacy and
1.496/58.823 ms on modern. Sprite render medians were 0.256 ms on both;
modern hid approximately 0.256 ms under DMA, while legacy exposed no overlap.
Scroll render medians were 1.763 ms legacy and 1.446 ms modern; modern hid the
entire measured render interval. Its synchronous scroll-transfer baseline was
6.277 ms versus 9.089 ms on legacy.

The widget row exercises `create_ide_view()` and `show_update_progress()` on
each actual TartLab renderer. Modern separates a 1.976 ms median widget update
from a 23.104 ms median LVGL refresh. The deployed legacy abstraction renders
and transfers synchronously inside one call, so a non-invasive split is not
available. The modern p95 total was 51.386 ms because the first progress update
invalidates substantially more UI; the legacy p95 was 337.769 ms.

The modern-only 250 ms LVGL bar animation had one missed 60 FPS deadline. Its
median work excluding the intentional 17 ms cadence sleep was 14.661 ms, p95
was 20.607 ms, and maximum was 27.309 ms. LVGL reported one running animation
for the first seven samples; eight of twelve frames caused display transfers,
followed by settled frames with no dirty content. The qualified legacy
firmware contains no LVGL, so there is no legacy animation result.

## CPU availability, heap, and ownership transitions

A deterministic Python loop ran while one complete display update was in
flight. Modern completed 938 iterations versus 1,416 in an equal no-transfer
interval, exposing 66.243% of baseline CPU work for IDE/network servicing.
The synchronous legacy call exposed zero iterations. This is evidence of DMA
CPU headroom, not proof of live browser latency while the raw REPL owns the
foreground.

Both profiles reported zero benchmark-owned allocations inside the 25-cycle
steady-state UI/game/UI loop. After garbage collection, both lost 336 bytes
from the first to last sample. Modern's median transition was 80.859 ms because
it drains the direct DMA transfer, reenables LVGL/input, invalidates the UI, and
waits for the forced redraw. Legacy's no-op ownership boundary plus its 10%
write took 6.919 ms.

MicroPython exposes allocated bytes, not a general allocation-event counter.
The harness therefore instruments its own allocations and records
`gc.mem_alloc()`/`gc.mem_free()` after every switch. The modern run grew by
11,088 allocated bytes from initial setup through the final UI; legacy grew by
360,128 bytes, primarily the legacy IDE view's one-time full framebuffer and
text buffers. The repeated-switch samples, rather than those intentional UI
objects, are the steady-state leak check.

## Commands

After provisioning each exact profile on the same board:

```powershell
.\.venv\Scripts\python.exe tools/phase5_benchmark.py collect --port COM6 --profile legacy --samples 12 --switches 25 --output hardware_test_artifacts/phase5-item5/legacy.json
.\.venv\Scripts\python.exe tools/phase5_benchmark.py collect --port COM3 --profile modern --samples 12 --switches 25 --output hardware_test_artifacts/phase5-item5/modern.json
.\.venv\Scripts\python.exe tools/phase5_benchmark.py compare --legacy hardware_test_artifacts/phase5-item5/legacy.json --modern hardware_test_artifacts/phase5-item5/modern.json --output hardware_test_artifacts/phase5-item5/comparison.json
```

## Outcome

Phase 5 item 5 is complete for the exact reference checkpoint and corrected
application adapter. The modern profile wins every measured median and
demonstrates meaningful partial-refresh and CPU-overlap advantages. It is now
hardware-qualified as a research reference, not selected for production.

Production promotion remains closed. Full-frame and solid-fill workloads miss
30 FPS, a 50% dirty update misses 60 FPS, UI redraw outliers remain, the CPU
measurement is not live network latency. The subsequently completed PyDevices
`lvgl-micropython` plus `displayif` comparison is recorded in
`tests/PHASE5_PYDEVICES.md`; it confirmed this reference as the Phase 5 research
selection. Adult provisioning, migration, support-window, and release-pipeline
work remains in Phase 6. The legacy release channel is unchanged.
