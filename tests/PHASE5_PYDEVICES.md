# Phase 5 PyDevices/displayif comparison

This document records the required alternative modern-stack comparison for the
same LilyGO T-Display-S3 Pro PCB v1.1 used by the Phase 5 reference lifecycle
and benchmark gates. It is research evidence only. It does not alter the
legacy release channel or select a production firmware.

## Locked candidate

- MicroPython 1.27.0 at
  `78ff170de9e32c79db6e64d3e33d2bd60002bdcd`.
- LVGL 9.5.0 at `85aa60d18b3d5e5588d7b247abf90198f07c8a63`.
- PyDevices cmods, displayif, LVGL bindings, cmod integration, and minimal
  Python runtime are pinned in `firmware/lvgl-modern/pydevices.lock.json`.
- ESP-IDF 5.5.1 runs from the same digest-pinned Linux/amd64 container used by
  the first reference.
- Target clocks and geometry match the first reference: 240 MHz CPU, 60 MHz
  display SPI, and logical 480 x 222 RGB565.
- Combined image: 3,603,344 bytes, SHA-256
  `f9d374cc1bc9ea5a4dc9726682bc74eba9bba8c53c958a21be14011da3858295`.
- Application image: 3,537,808 bytes in a 4,194,304-byte partition, leaving
  656,496 bytes (about 16 percent).

Two independent clean source graphs produced byte-identical combined images.
Both builds started by deleting the exact ESP32 board build directory and the
exact MicroPython `mpy-cross/build` directory. The wrapper temporarily applies
one hash-bound compatibility include to displayif, reverses it after the build,
and leaves every pinned source repository clean. The archived candidate and
machine-readable provenance are under
`firmware/lvgl-modern/pydevices-reference`.

## Transport assessment

The alternative uses displayif's native C `spibus` module over `machine.SPI`,
not TartLab's historical pure-Python bus. Its public pixel write is blocking,
however: this pin provides no asynchronous completion callback, independent DMA
buffer allocator, or way to overlap rendering with an in-flight display
transfer. TartLab therefore exposes an honest synchronous `RGB565_BE` direct
surface backed by reusable `bytearray` buffers. The same explicit UI/game
ownership boundary remains in place.

This capability difference is decisive for Phase 5 item 8. The candidate
cannot meet the first reference's DMA-completion and render/transfer-overlap
gate without an upstream transport change.

## Physical preflight

The board is connected as native USB Serial/JTAG on COM3. Before any firmware
write, 208 current filesystem files were copied and verified into the ignored
`hardware_test_artifacts/phase5-pydevices/preflash-filesystem` directory. The
combined image ends before the filesystem partition, and the earlier exact
modern reference plus both filesystem snapshots remain available as recovery
inputs.

## Physical session: 2026-08-26

- [x] Esptool wrote and hash-verified the exact archived candidate at offset
  `0x0`. It erased only through `0x36ffff`; the filesystem starts at
  `0x410000` and was not written.
- [x] The reversible staging helper saved both protected hardware selectors
  before installing and hash-verifying the comparison adapter and config. An
  initial one-selector preflight correctly exposed that recovery-mode import
  order can select the legacy root copy; the final helper covers both copies.
- [x] Hard reset and raw-REPL Ctrl-D soft reset returned the pinned runtime,
  480 x 222 platform, ST7796, CST226, UI ownership, and no pending transfer.
- [x] Five same-runtime initialization/deinitialization cycles passed. After
  the first warm-up, heap declined 192 bytes total and converged to a 16-byte
  fifth-cycle change.
- [x] Twenty-five UI/game/UI transitions passed with final UI ownership, no
  pending transfer, no benchmark-owned steady-state allocation, and 336 bytes
  of first-to-last heap drift in the locked benchmark run.
- [x] All five RGB565 color-band transfers completed at logical 480 x 222 and
  returned to UI mode. The operator did not repeat the visual orientation
  judgment because the candidate had already failed the selection gate.
- [x] Normal boot initialized display and touch, created the fallback AP,
  started the HTTP server on port 80, and logged
  `HEALTHY mode=IDE update_committed=False`.
- [ ] A new five-point human touch observation and physical APP/error switch
  were not run. Those gates remain required if a future displayif revision is
  reconsidered for selection.
- [x] The same Phase 5 benchmark matrix completed and validated against the
  exact `lcd_bus` reference result.
- [x] Both original selectors and the exact qualified research-reference
  firmware were restored. A final uninterrupted boot started its fallback AP,
  HTTP server, and healthy IDE.

## Same-matrix benchmark

Times are medians. A ratio above 1.0 means the PyDevices candidate was slower.

| Workload | `lcd_bus` reference | PyDevices/displayif | Ratio |
| --- | ---: | ---: | ---: |
| 10% dirty transfer | 5.176 ms | 7.489 ms | 1.447x |
| 25% dirty transfer | 12.455 ms | 14.576 ms | 1.170x |
| 50% dirty transfer | 25.110 ms | 29.616 ms | 1.179x |
| Full-frame transfer | 58.418 ms | 74.414 ms | 1.274x |
| Solid fill | 60.375 ms | 76.608 ms | 1.269x |
| Sprite | 2.355 ms | 3.489 ms | 1.482x |
| Scroll | 5.633 ms | 10.440 ms | 1.853x |
| TartLab widgets | 25.136 ms | 40.335 ms | 1.605x |
| UI/game/UI switch | 80.859 ms | 176.741 ms | 2.186x |

The reference exposed 66.243 percent of its no-transfer Python-loop baseline
while a full transfer was in flight; the blocking alternative exposed zero.
The alternative recorded zero overlap for sprite and scroll, while the
reference hid their complete measured render intervals. The alternative also
missed six of twelve LVGL-animation deadlines versus one for the reference.
Raw JSON remains outside Git under
`hardware_test_artifacts/phase5-pydevices`.

## Current outcome

The first `lvgl_micropython`/`lcd_bus` repository wins the Phase 5 stack
selection. It is faster in every measured median, exposes transfer-time CPU
headroom, supports render/transfer overlap, and already passed the complete
lifecycle gate. TartLab will maintain its pinned public direct-surface adapter.

This selects the basis for future modern-firmware work; it does not promote a
production release. Adult/admin provisioning, migration, a support window, and
release-pipeline qualification remain later gates. The legacy release channel
is unchanged. The PyDevices artifact remains archived as a reproducible,
benchmarked rejected candidate for future upstream comparison.
