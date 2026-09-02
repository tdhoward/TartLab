# Elecrow DLE06235B bring-up results

Status: experimental bench result, not a TartLab board qualification

Test date: 2026-08-29

Remaining-work checklist updated: 2026-08-31

## Outcome

The Elecrow 3.5-inch DLE06235B passed the standard MicroPython gate and booted
TartLab's pinned LVGL 9.4 / MicroPython 1.27 reference runtime. An experimental
ST77922 QSPI driver initializes and completes asynchronous pixel transfers at
40 MHz. Native 320 x 480 portrait LVGL, fast partial redraws, and single-pointer
touch are owner-confirmed correct. On 2026-08-31 a complete TartLab filesystem
also reached its persisted `healthy` checkpoint in IDE mode using the new
board selector and platform adapter. A 480 x 320 software-rotated landscape
proof also works, but portrait is the selected board mode; landscape remains
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
callback, so the first prototype temporarily used blocking completion. Focused
testing on 2026-08-31 showed that a no-op callback and LVGL's exact
`flush_ready()` callback both work; 100 manual refreshes and then 500 forced
LVGL redraws completed asynchronously. A Python exception escaping the native
callback is fatal, however. The TartLab controller callback therefore contains
all exceptions in ISR context, records a sticky failure, and raises it later
from the main-thread transfer wait. The driver now uses the real asynchronous
completion signal and no longer calls `flush_ready()` synchronously.

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
480 x 320 resolution and rendered for five seconds without a crash. Explicit
TartLab teardown now disables and deletes the input device, removes retained
wrapper registry entries, finalizes the display, deinitializes the bus, and
frees the ST77922 driver's independent DMA rotation buffer. Ten consecutive
portrait construct/refresh/deinitialize/reconstruct cycles passed in one
runtime; free heap stabilized at 8,298,704 bytes for cycles 4 through 10.

## TartLab integration result (2026-08-31)

The experimental board integration now consists of:

- `boards/elecrow_dle06235b/runtime/elecrow_dle06235b_modern.py`, selected
  through the board catalog's protected `/device/hdwconfig.py` boundary and
  installed only for that board; it owns the QSPI, I2C, reset, backlight,
  portrait geometry, touch, and lifecycle details;
- a packed-QSPI direct RGB565 surface using command `0x32002C00`;
- a full-frame SPIRAM shadow plus a 24-row internal-DMA scratch buffer. Games
  must seed the shadow with one full-frame synchronous write after each
  UI-to-game transition. Arbitrary dirty rectangles are merged into the
  shadow, rounded to the four-column physical constraint, and transferred from
  the scratch buffer without reading beyond the caller's buffer or inventing
  neighboring pixels;
- a 296-pixel portrait progress bar in place of the qualified board's fixed
  420-pixel width; and
- no built-in IDE button. With the default `BUTTON` policy, the platform's
  absent-button value selects IDE mode without assigning a boot-strapping GPIO
  as a classroom control.

The exact adapter completed a live platform construction, touch discovery,
LVGL UI refresh, and teardown. Its public game surface then completed a
chunked 320 x 480 seed, an unaligned 3 x 2 dirty rectangle at X=1, return to
LVGL ownership, UI refresh, and teardown.

A clean complete filesystem subsequently booted into TartLab IDE mode. A
read-only LittleFS snapshot recorded:

| Check | Result |
| --- | --- |
| Promoted entry points | `boot.py` and `main.py`; no bootstrap files remained |
| Boot health | `healthy`, mode `IDE`, zero consecutive failures |
| HTTP startup | log ended with `HEALTHY mode=IDE update_committed=False` after the server start completed |
| Heap at startup diagnostics | 8,199,504 bytes free |
| Filesystem at startup diagnostics | 12,517,376 bytes total; 9,588,736 bytes free |

Because the clean board had no station credentials, this boot followed the
setup-AP path. The owner subsequently confirmed the complete browser workflow:

- connect to the temporary TartLab hotspot;
- enter and save credentials for a local Wi-Fi network;
- reconnect to TartLab over the LAN;
- load, edit, save, and run files in the browser IDE; and
- mark a file as the selected app.

Booting the selected app remains untested. This board exposes only Reset and
Boot, and the current bench configuration intentionally assigns neither as a
TartLab IDE/app selector. The product-level startup-mode control is deferred;
it is not a blocker for the confirmed IDE workflow in this pass.

The bench staging sequence exposed an operational caveat. `mpremote` raw-mode
soft resets execute `boot.py` but intentionally skip `main.py`; repeatedly
connecting after installing TartLab's recovery-aware `boot.py` can therefore
consume the boot-failure budget before the application can mark itself
healthy. The successful clean install used stock `boot.py` plus a one-shot
temporary `main.py` to atomically promote the final entry points and execute
the real application. Production provisioning must provide an equivalent
transaction instead of copying the final entry points in an unsafe order.

## Remaining work

The selected TartLab mode for this board is native 320 x 480 portrait. The
earlier
[`ESP32-S3 bring-up plan`](../elecrow/ESP32_S3_BRINGUP_PLAN.md)'s 480 x 320
landscape requirement is superseded for the DLE06235B. Landscape remains an
optional experiment and is not on the critical path to a supported portrait
target.

There are two distinct milestones. A successful one-off TartLab bench boot is
not a supported-board claim; release support additionally requires reproducible
firmware, safe provisioning, recovery, OTA, and board-bound qualification.

### Milestone A: first complete TartLab bench boot

1. **Completed for bench use:** restore and qualify the native QSPI
   asynchronous-completion path, with callback exceptions contained until a
   main-thread wait can report them.
2. **Partially completed:** explicit construction/refresh/teardown passed ten
   same-runtime cycles with stable heap. Repeated soft resets, hard resets, and
   a cold USB power-cycle series remain to be qualified.
3. **Completed for bench use:** add the packed-QSPI direct surface and define a
   shadow-backed dirty-rectangle contract that satisfies the physical CASET
   alignment rule without caller-buffer overread.
4. **Completed for bench use:** add the platform factory and protected board
   selector while keeping hardware details behind `tartlabutils.platform`.
5. **Partially completed:** the known fixed-width progress bar is now
   geometry-aware. Visual review of every status overlay, error view, and touch
   target in portrait remains.
6. **Completed for the current bench policy:** configure no built-in IDE
   button rather than assigning GPIO0, GPIO45, or GPIO46 without qualification.
   This means the default button policy always selects IDE mode. A future
   external-button or buttonless app-mode control remains a product decision.
7. **Partially completed:** the complete filesystem reached a healthy IDE
   server; temporary-AP setup, Wi-Fi station/LAN access, and browser file
   load/edit/save/run were owner-confirmed. Selecting an app also worked, and
   the direct-surface ownership round trip passed. Still verify brightness,
   booting a selected app, representative examples/direct games, and their
   complete launcher ownership transitions.

Milestone A means TartLab runs end to end on the bench. It does not authorize
publishing or provisioning the board as a supported target.

### Milestone B: reproducible supported target

8. Complete the board hardening gates: identify or explicitly quarantine the
   unexplained I2C `0x28` responder; measure transfer and render timing, Wi-Fi
   coexistence, heap and flash margins; and complete at least 100
   LVGL/direct-surface ownership transitions without a crash or corruption.
9. Decide whether the existing first-active-contact pointer behavior is the
   supported contract or whether TartLab must expose simultaneous multitouch.
   The former is sufficient for the current single-pointer UI if it is made an
   explicit qualification decision.
10. Integrate the native QSPI fixes and reviewed Python drivers into TartLab's
    pinned MicroPython 1.27.0 / LVGL 9.4.0 source graph. Produce a reproducible,
    checksummed DLE06235B firmware artifact with its own build lock and
    provenance; do not reuse the T-Display-S3 Pro firmware identity.
11. Generalize the modern profile, release builder, validators, provisioning
    tool, and tests from one firmware hash and selector to an explicit
    board-to-firmware compatibility matrix. Clean provisioning must identify
    or require explicit confirmation of the board, verify 16 MiB flash, write
    the DLE06235B selector, and reject incompatible images before erase. Do not
    claim migration from an unknown Elecrow factory filesystem.
12. Run the repository Tier 0-2 checks and board-specific physical
    qualification: clean adult provisioning, interrupted provisioning and
    resume, normal and interrupted OTA, display-independent recovery,
    rollback, protected-state preservation, release-feed isolation, browser
    and API regression checks, and future-update availability.
13. Create and promote a separate sanitized DLE06235B qualification record
    bound to the exact firmware hash, board identity, release candidate, and
    durable evidence. Only this milestone permits listing the board as a
    supported TartLab target.

Raw serial logs, firmware downloads, and vendor resource archives remain under
the ignored `hardware_test_artifacts` directory. They may contain workstation
or device-specific data and are not source artifacts.
