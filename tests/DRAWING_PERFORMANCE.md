# Drawing performance

The implementation plan is documented in
[`MODERN_DISPLAY_CLASS_PROJECT.md`](../MODERN_DISPLAY_CLASS_PROJECT.md).

Median end-to-end time per frame on the connected modern and legacy test
devices; lower is faster.
The benchmark uses a 200-block grid, a moving 2 x 2 piece, and a three-line
text region. Black/white RGB565 assets keep byte order from affecting the
comparison.

| API | Orientation | Full grid (ms) | Piece move (ms) | Text redraw (ms) |
| --- | --- | ---: | ---: | ---: |
| display_drv | Landscape | 331.84 | 14.67 | 5.37 |
| DirectCanvas | Landscape | 79.62 | 6.40 | 4.51 |
| display_drv | Portrait | 343.89 | 14.41 | 5.61 |
| PortraitCanvas | Portrait | 208.64 | 8.27 | 38.27 |

- Modern collected: `2026-09-02T23:49:20.419602+00:00`
- Legacy collected: `2026-09-02T22:40:46.466509+00:00`
- Modern app source: `working_tree_in_memory`

Collection runs temporary code through raw REPL. Modern collection injects
the working-tree module in memory; it does not flash firmware or write to
the device filesystem. Raw result JSON stays in the ignored
`hardware_test_artifacts/drawing-performance` directory.

```powershell
.\.venv\Scripts\python.exe tools/drawing_performance.py collect --port COM3 --profile modern
# Physically swap in a legacy-firmware device; do not flash the fixture.
.\.venv\Scripts\python.exe tools/drawing_performance.py collect --port COM6 --profile legacy
.\.venv\Scripts\python.exe tools/drawing_diagnostics.py --port COM3
.\.venv\Scripts\python.exe tools/drawing_performance.py report
```

## Modern slowdown experiments

All values are medians in milliseconds. The stage experiment separates
framebuffer rendering from `DirectCanvas.show()` row packing, transfer
submission, and synchronous waiting.

| Case | Render | Pack/loop | Submit | Wait | Transfers | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DirectCanvas piece | 1.28 | 0.76 | 1.03 | 1.15 | 1 | 4.22 |
| DirectCanvas text | 0.97 | 1.03 | 1.07 | 2.20 | 1 | 5.26 |
| PortraitCanvas piece | 2.98 | 1.20 | 1.08 | 1.15 | 1 | 6.40 |
| PortraitCanvas text | 31.20 | 1.81 | 1.00 | 2.21 | 1 | 36.16 |

The shape experiment transfers 10,368 bytes in every row. Tiled uses the
canvas's 15,360-byte bounce buffer with adaptive row counts; raw uses one
prepacked `surface.write()`.

| Physical shape | Tiled transfers | Tiled total | One raw write | Ratio |
| --- | ---: | ---: | ---: | ---: |
| 144 x 36 | 1 | 3.89 | 3.12 | 1.2x |
| 72 x 72 | 1 | 3.89 | 3.07 | 1.3x |
| 36 x 144 | 1 | 3.99 | 3.11 | 1.3x |

The text experiment measures rendering only, with no display transfer.
The reusable-mask case removes per-line mask allocation while retaining
Python pixel rotation. The cached-sprite case rotates once before timing.

| Text renderer | Render time |
| --- | ---: |
| DirectCanvas native text | 0.90 |
| PortraitCanvas current text | 31.15 |
| PortraitCanvas reusable mask | 33.33 |
| PortraitCanvas cached sprite | 2.36 |

### Findings

- Row packing and loop overhead accounts for 24% to 36% of the
  measured `show()` time in all four slow cases.
- With byte count held constant, the 36 x 144 tiled region took 1.0x
  as long as the 144 x 36 region. The single-write medians stayed between
  3.07 and 3.12 ms, showing that pixel count and the native transfer are
  not the source of that shape-dependent slowdown.
- Current portrait text rendering took 34.7x the native landscape text
  path. Reusing the glyph mask changed the median by only +7.0%, while a
  pre-rotated sprite was 13.2x faster. The Python per-pixel rotation loop,
  rather than mask allocation, is the portrait rendering bottleneck.
- Ten construct/show/close cycles ended with allocation balance 0,
  owner `ui`, no pending transfer, and heap change -480 bytes.

Diagnostics collected: `2026-09-02T23:52:04.566736+00:00`
