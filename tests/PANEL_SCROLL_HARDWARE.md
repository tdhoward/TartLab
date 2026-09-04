# ST7796 panel-scroll hardware experiment

Date: 2026-09-04 UTC

Status: passed, including visual `MADCTL.MV = 1` confirmation

## Fixture and method

- Board: LilyGO T-Display-S3 Pro on COM3
- Panel: ST7796, native `222 x 480`
- Surface: `480 x 222`, panel rotation 270
- Working tree base: `5d92385`
- Tool: `tools/panel_scroll_diagnostics.py`
- Delivery: working-tree sources injected temporarily through raw REPL
- Device filesystem writes: none
- Firmware writes: none

The diagnostic seeded a striped framebuffer, compared accelerated and software
`scroll_region()` results in RAM, recorded actual adapter transfer regions and
byte counts, exercised a dirty rectangle across the wrap seam, closed each
canvas to restore neutral scanout, and repeated the first case after reset.

## Results

| Case | Accelerated | Software | Transfer reduction | Accelerated time | Software time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full width, `dx=-32` | 14,208 bytes | 213,120 bytes | 15.0x | 31.90 ms | 101.97 ms |
| Full width, `dx=32` | 14,208 bytes | 213,120 bytes | 15.0x | 32.81 ms | 103.05 ms |
| Fixed 40-pixel sides, `dx=16` | 7,104 bytes | 177,600 bytes | 25.0x | 1466.47 ms | 1524.71 ms |
| Repeated full width, `dx=-32` | 14,208 bytes | 213,120 bytes | 15.0x | 31.88 ms | 98.16 ms |

All accelerated and software RAM-buffer SHA-256 values matched. The full-width
accelerator was 3.1x to 3.2x faster in addition to reducing transfer volume.
The fixed-area case materially reduced transfer volume, but its partial-region
RAM move remains dominated by the portable Python scanline copy.

With a 32-pixel active origin, a visible dirty rectangle at `x=440`, width 24,
was split into GRAM writes `(472, 40, 8, 24)` and `(0, 40, 16, 24)`, matching
the expected wrap seam. The repeated case produced the same exposed-band
coordinates. Every run completed its neutral-reset commands and returned to
the LVGL UI.

## Physical qualification result

The automated test proved that the pinned driver accepts `VSCRDEF` and
`VSCSAD` at panel rotation 270 and validated software state, address
calculations, transfer volume, timing, cleanup, and repeatability. The final
visual run added explicit yellow and blue section markers around ten-second
hardware and software holds. The owner observed that both striped sections
were stable and identical, followed distinctly by the completion screen.

This confirms that the glass scanned the expected GRAM rows while
`MADCTL.MV = 1`. The LilyGO board payload may therefore include rotation 270
in `qualified_rotations` and advertise logical horizontal panel scrolling.

Run the held comparison while watching the display with:

```powershell
.\.venv\Scripts\python.exe tools/panel_scroll_diagnostics.py `
    --port COM3 --visual-hold 5
```

The tool runs its automated cases first. A solid yellow cue marks the start of
the held hardware-scrolled frame. A two-second solid blue fill then separates
it from the held, fully transmitted software reference. The striped holds must
be pixel-identical. A black `VISUAL TEST COMPLETE` screen explicitly marks the
end before the ordinary LVGL UI returns.
