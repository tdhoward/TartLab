# Elecrow DLE06235B bring-up results

Status: experimental bench result, not a TartLab board qualification

Test date: 2026-08-29

## Outcome

The Elecrow 3.5-inch DLE06235B passed the standard MicroPython gate and booted
TartLab's pinned LVGL 9.4 / MicroPython 1.27 reference runtime. An experimental
ST77922 QSPI driver initializes and completes blocking pixel transfers at
40 MHz. Native 320 x 480 portrait LVGL, fast partial redraws, and single-pointer
touch are owner-confirmed correct. A 480 x 320 software-rotated landscape proof
also works, but portrait is the selected board mode; landscape remains
experimental and is not part of this bench acceptance.

No factory backup was retained because the board was new and the owner
explicitly authorized erasing its contents.

## Hardware observed

- ESP32-S3 revision 0.2 at 240 MHz;
- 16 MiB flash and 8 MiB octal PSRAM;
- Secure Boot and flash encryption disabled;
- native ESP32-S3 USB Serial/JTAG connection;
- QSPI ST77922 display on GPIO CS 10, clock 12, and data 11/13/14/9;
- backlight GPIO41, active high;
- shared I2C on GPIO38/39 with responders at `0x18`, `0x28`, and `0x55`.

The `0x55` device identifies as the ST77922 integrated touch interface:

| Field | Value |
| --- | --- |
| Firmware version | 3 |
| Firmware revision | 1.6.1.17 |
| Reported geometry | 320 x 480 |
| Maximum touches | 5 |

This live result and Elecrow's active example contradict the FT6336G/`0x38`
description found elsewhere in the vendor materials. Address `0x18` is
consistent with the documented ES8311 audio codec. Address `0x28` remains
unidentified and must not be assigned a function without evidence.

## Standard MicroPython result

Official image:

- board variant: `ESP32_GENERIC_S3-SPIRAM_OCT`;
- MicroPython: 1.29.0, dated 2026-08-24;
- image size: 1,786,704 bytes;
- SHA-256: `ab24eadfe3ef0e6ee38834d730e648def7cd82f3fa51ee0bbc59c29a6e1bd176`.

Observed checks:

| Check | Result |
| --- | --- |
| Native USB REPL | Pass |
| CPU frequency | 240,000,000 Hz |
| Free heap after collection | 8,318,224 bytes |
| 6 MiB allocation | Pass; 1,809,328 bytes remained during allocation |
| Heap after deleting allocation | 1,809,344 bytes in the same raw-exec cycle; a reset restored the full heap, so allocator behavior needs a focused follow-up |
| Filesystem | 3,584 blocks of 4,096 bytes; write/reset/read persistence passed |
| Wi-Fi station scan | Pass; four networks observed without recording identities |
| Wi-Fi AP start/stop | Pass |
| Backlight GPIO41 off/on writes | Pass; left on |
| `machine.reset()` and reconnect | Pass |

Windows assigned COM18 to the ROM bootloader and COM19 to the official
MicroPython application interface. The port-number change initially resembled
a silent REPL failure; using a watchdog reset and enumerating USB devices
revealed the application port.

## Pinned LVGL runtime result

The existing reproducible TartLab reference image was flashed unchanged:

- MicroPython 1.27.0;
- LVGL 9.4.0 source lock;
- 16 MiB partition layout;
- image size: 2,978,512 bytes;
- SHA-256: `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.

The runtime imported `lvgl` and `lcd_bus`, exposed `lcd_bus.SPIBus`, and had
8,319,728 bytes free before display allocation. Its native Serial/JTAG REPL
enumerated as COM18 on this workstation.

Prototype files:

- `firmware/lvgl-modern/drivers/st77922.py` implements the 32-bit QSPI command,
  address, window, and pixel-write framing;
- `firmware/lvgl-modern/drivers/_st77922_init.py` reproduces all 63 entries in
  Elecrow's active DLE06235B init table exactly;
- `firmware/lvgl-modern/drivers/elecrow_dle06235b_smoke.py` configures the
  published pins, uses dual 24-row internal DMA render buffers plus a DMA
  rotation buffer, and runs QSPI at 40 MHz;
- `firmware/lvgl-modern/drivers/elecrow_dle06235b_direct_fill.py` bypasses LVGL
  and writes blocking red/green/blue bands as a transport diagnostic;
- `firmware/lvgl-modern/drivers/elecrow_dle06235b_partial_fill.py` exercises
  variable CASET widths without LVGL and exposed the four-column constraint;
- `firmware/lvgl-modern/drivers/elecrow_dle06235b_touch_probe.py` captures raw
  press, release, corner, and drag reports;
- `firmware/lvgl-modern/drivers/elecrow_dle06235b_touch_smoke.py` provides the
  owner-confirmed five-target LVGL pointer test;
- `firmware/lvgl-modern/drivers/st77922_touch.py` implements the reviewed first
  contact of Elecrow's integrated-touch register protocol.

The direct diagnostic completed all pixel writes. The initial asynchronous
LVGL flush crashed at a stable native address before its Python completion
callback. The same transfer succeeds in blocking mode, and the blocking LVGL
smoke printed `ELECROW_LVGL_SMOKE_READY` and ran for five seconds without a
crash. The prototype therefore disables the QSPI completion callback and calls
LVGL's `flush_ready()` synchronously. This is useful for continued bring-up but
is not an acceptable final performance architecture.

The controller datasheet requires both CASET start column and programmed width
to be multiples of four. This was also reproduced directly on the board:
320- and 128-pixel windows were clean, while 130- and 131-pixel windows produced
alternating-color rows and right-edge overrun. A 129-pixel window happened to
look clean but violates the documented constraint and is not relied upon. The
driver now rounds LVGL invalidations outward on the physical column axis before
rendering. In native portrait this means rounding logical X; for transposed
landscape it means logical Y. With rounding active, all five portrait touch
targets, their green state changes, and the final status label redraw sharply
and quickly without full-frame invalidation.

The shared GPIO48 display/touch reset pulse is required after MCU reset. The
ST77922 touch report is not acknowledged by reading only the first seven-byte
contact: with five supported contacts, the host must read all 35 coordinate
bytes through register `0x0036`. The prototype now does this and retains the
current state when no new report is pending. Live testing confirmed distinct
press/release events, center and four-corner coverage, continuous drag motion,
and the raw portrait-to-landscape mapping `x = 479 - raw_y`, `y = raw_x`.
The final native portrait LVGL five-target test passed visual inspection.

The ST77922 differs from common ST77xx controllers: MADCTL bit 5 is reserved,
not the usual MV row/column-exchange control. MADCTL-only attempts therefore
produced portrait-axis output that was mirrored or rotated relative to the
requested landscape geometry. The confirmed implementation keeps the panel in
its native portrait scan order and uses LVGL's native `draw_sw_rotate` routine
to rotate each partial pixel buffer. The flush callback also maps each LVGL
area to its rotated physical write window. LVGL rotation 270 degrees produces
the owner-confirmed upright 480 x 320 orientation; rotation 90 degrees produces
the otherwise-correct landscape image upside-down. Dynamic landscape redraws
were not requalified after discovering the CASET alignment rule; the board will
remain in native portrait for the rest of bring-up.

The first landscape relaunch also exposed a native lifecycle issue: rebuilding
`machine.SPI.Bus` after a MicroPython soft reset can reuse stale pin objects and
raise `TypeError: can't convert function to int`. A full MCU reset clears the
native singleton. From clean state, LVGL reported rotation 270 degrees and
480 x 320 resolution and rendered for five seconds without a crash. Firmware
integration must make SPI teardown/recreation safe rather than relying on this
bench reset workaround.

## Remaining gates

1. Identify or explicitly quarantine the unexplained I2C `0x28` response.
2. Test repeated soft resets, hard resets, and a cold USB power cycle with the
   LVGL driver active.
3. Fix and qualify the pinned native QSPI asynchronous-completion path; do not
   promote the blocking workaround as the final display transport.
4. Fix and qualify QSPI bus teardown/recreation across MicroPython soft reset.
5. Measure transfer and render timing, Wi-Fi coexistence, heap use, and at
   least 100 LVGL/direct-surface ownership transitions.
6. Decide whether simultaneous multi-touch must be exposed; the qualified
   TartLab pointer path currently reports the first active contact only.
7. Convert the prototype into a pinned reproducible board build before adding
   a TartLab platform selector or fixture promotion record.

Raw serial logs, firmware downloads, and vendor resource archives remain under
the ignored `hardware_test_artifacts` directory. They may contain workstation
or device-specific data and are not source artifacts.
