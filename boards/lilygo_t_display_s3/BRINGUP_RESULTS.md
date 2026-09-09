# T-Display-S3 initial bring-up results

Date: 2026-09-09. Lifecycle: `bringup`; no release qualification claimed.

The owner identified a non-Pro, non-touch T-Display-S3 and authorized erasing
it without backup. Initial hardware checks and a standalone display/button
diagnostic passed on stock MicroPython and TartLab's pinned modern reference
firmware. This establishes the first bench stage of the
[buttons-only project](../../BUTTON_NAVIGATION_PROJECT.md), not the complete
navigation milestone. No shared production runtime code was changed.

## Stock MicroPython

Used the archived official `ESP32_GENERIC_S3-SPIRAM_OCT` v1.23.0 image dated
2024-06-02, 1,631,424 bytes, SHA-256
`41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
Its archive location under `firmware/legacy-mp123` does not mean the legacy
TartLab filesystem or PyDevices was installed. This was an interpreter-only
hardware probe; the modern firmware replaced it after a second full erase.

| Check | Observed result |
| --- | --- |
| ROM identification | ESP32-S3 revision 0.2; native USB Serial/JTAG |
| Flash / embedded PSRAM | 16 MiB quad flash; 8 MiB embedded PSRAM reported by esptool |
| Erase and write | Completed; esptool verified written data hash |
| CPU | 240 MHz |
| Collected free heap | 8,311,760 bytes before test; 8,312,672 after allocation cleanup |
| PSRAM exercise | 6 MiB allocation; deterministic write/read samples every 4 KiB passed; not an exhaustive memory test |
| Filesystem | 1,536 blocks of 4,096 bytes under this stock image's smaller layout |
| Persistence | 4 KiB pattern write/read, `machine.reset()`, reconnect and readback passed; test file removed |
| Wi-Fi station | Scan returned four networks; identities not retained |
| Access point | Start, address assignment and stop passed; no client association tested |
| Buttons | Both configured as pulled-up inputs; released levels were high |

The stock USB application enumerated separately from the ROM endpoint and
required DTR asserted for raw REPL output. The existing helper with inactive
DTR initially timed out; `mpremote` and an explicit bench-only DTR setting
worked. No shared serial helper was modified.

The first RTS hard reset did not yield a REPL; esptool's watchdog reset booted
the stock application. Later, `machine.bootloader()` removed the USB endpoint
without exposing a usable serial port. The owner restored ROM mode using
BOOT/RST. Treat this software bootloader route as unsuitable for this stock
bench configuration. Manual recovery was exercised successfully; unplugged
power cycles and battery operation remain untested.

## Pinned modern firmware and display

Flashed the unmodified archived reference image at offset `0x0` after erase:

- Artifact: `firmware/lvgl-modern/reference/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16-phase5-reference.bin`.
- Size: 2,978,512 bytes; SHA-256
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
- Source lock: `firmware/lvgl-modern/reference.lock.json`;
  MicroPython 1.27.0 / LVGL 9.4.0.
- Reported interpreter banner: `MicroPython 78ff170de9-dirty on 2026-06-23`;
  this is the archived reference banner, not a new local firmware build.
- Native I80, LVGL keypad input, and focus-group creation APIs present.
- Free heap before display: 8,319,728 bytes on the first boot.
- Modern filesystem: 3,056 blocks of 4,096 bytes.

The reference image has the required native bus support. For this experiment,
the two ST7789 Python modules were uploaded unchanged from the exact locked
`lvgl_micropython` commit
`d2d26467fa4cb9e99e569d899709043d086f7a6f`:

| Upstream path under `api_drivers/common_api_drivers/display/st7789/` | Uploaded SHA-256 |
| --- | --- |
| `st7789.py` | `9e8799a9014314fd4dd30efdd99f7016add8094d02d7f5b551f67edaecaa314b` |
| `_st7789_init.py` | `c7e7dc846354626ccd17811fe0eb36a775d355c41643f8ad246ded60bc49d5e1` |

No PyDevices files or Pro board selector were installed. Reference firmware
reuse here does not confer Pro qualification on this board. A production
driver packaging/firmware recipe and its provenance are still needed.

Working bench settings:

| Setting | Value |
| --- | --- |
| Wiring | Board-local table in [README.md](README.md) |
| Display power / read strobe | Both held high; 100 ms power settle before construction |
| Transport | `lcd_bus.I80Bus`, 8 data lanes, 16 MHz |
| Panel driver | Upstream `st7789.ST7789`; active-low reset |
| Geometry | Native 170 x 320; rotation 90 degrees; logical 320 x 170 |
| Address offset after rotation | x=0, y=35 |
| LVGL format | `RGB565_SWAPPED`, `rgb565_byte_swap=False` |
| Controller color order | BGR; inversion enabled |
| Buffers | Two internal DMA buffers, 15,360 bytes each (320 x 24 x 2) |
| Backlight | Driver PWM mode; set to 70 percent after first redraw |

The first RGB setting swapped red and blue, as reported by the owner. BGR
corrected that. The owner then confirmed correct RED/GREEN/BLUE blocks,
upright readable text, and all four white border edges. This establishes the
tested landscape orientation only; other rotations and brightness levels are
not qualified.

Both buttons produced three presses and three releases in the captured test.
The diagnostic samples every 5 ms and accepts a level after 30 ms of stability.
Its on-screen counts demonstrate independent physical inputs. This is not
production navigation, a general debounce qualification, or held-button/page
ownership validation.

Modern Wi-Fi scan returned eight networks. AP start/address/stop passed with
the initialized display; both radios were disabled afterward. Free heap at
that checkpoint was 8,295,536 bytes. Browser connectivity, station association,
and continuous radio/display stress remain untested.

## Device handoff and remaining work

The device is left on the pinned modern reference firmware with a temporary
`/main.py` that runs the display/button diagnostic. It shows the color blocks,
border and press/release counters and restarts after reset. It contains no
Wi-Fi credentials and does not start the TartLab IDE. Ctrl-C over the native
serial REPL stops the diagnostic; use `machine.reset()` to restart it.

Three consecutive `machine.reset()`/reconnect cycles passed: each automatically
imported the diagnostic from `/main.py`, reconstructed the 8-lane display,
retained the installed filesystem, and reported 8,298,704 bytes free after
collection. A final reset returned it to the running diagnostic. These are
software-reset checks, not physical power-cycle or brownout evidence.

The temporary host scripts, uploaded source copies, per-file hashes and raw
logs are in the ignored local directory
`hardware_test_artifacts/t_display_s3_bringup_20260909/`. They are bench
artifacts rather than a production runtime payload. The board-local bench
configuration contains the wiring; the display script consumes it.

Next: implement the compatible optional-touch, named-button, I80 construction,
and input ownership contracts described in the project plan; then add the
declarative production `BOARD_CONFIG` and integrate launcher/settings focus.
Complete browser programming and a simple app/IDE-return demonstration before
advancing to the applicable full new-board qualification gates. Touch is
absent, so touch-only checks need explicit inapplicability and actual button
evidence in their place.
