# Phase 5 modern-firmware lifecycle qualification

This document records physical evidence for Phase 5 item 4. It qualifies the
reproducible reference only for continued research and benchmarking; it does
not promote the modern profile or alter the legacy release channel.

## Candidate identity

- Board: LilyGO T-Display-S3 Pro PCB v1.1, the same physical target used for
  the Phase 2 through Phase 4 sessions.
- Firmware: `firmware/lvgl-modern/reference/lvgl_micropy_ESP32_GENERIC_S3-
  SPIRAM_OCT-16-phase5-reference.bin` at offset `0x0`.
- Firmware SHA-256:
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
- Firmware source: pinned `lvgl_micropython` commit
  `d2d26467fa4cb9e99e569d899709043d086f7a6f`, MicroPython 1.27.0, LVGL
  9.4.0, and ESP-IDF 5.5.1 as recorded by `reference.lock.json`.
- Application adapter inputs are the exact files and hashes recorded by
  `profiles/lvgl-modern.json`.

## Recovery guardrail

Before changing the firmware partition layout, capture the device filesystem
with `tools/phase1_device.py snapshot`. Keep the official qualified legacy
firmware and the snapshot available until the modern session is complete.
Changing between the legacy and modern layouts requires an erase followed by
flashing the complete image at offset `0x0`; a filesystem snapshot alone is
not a flashable image.

The 2026-08-24 pre-session snapshot contains 139 files and is retained only in
the ignored `hardware_test_artifacts/phase5-item4` workspace. It includes local
settings and is intentionally not committed. Its protected-path digests match
the completed Phase 4 record.

## Repeatable probes

After provisioning the modern image and selecting
`from t_display_s3_pro_modern import *` in `/hdwconfig.py`, run:

```powershell
.\.venv\Scripts\python.exe tools/modern_firmware.py check
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 probe
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 renderer-cycle --iterations 25
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 color
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 touch --seconds 20
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 init-cycle --iterations 5
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 monitor-reset --seconds 300
.\.venv\Scripts\python.exe tools/phase5_device.py --port COM3 device-status
```

The renderer probe uses a reusable native DMA buffer, measures every
UI-to-game and game-to-UI transition, waits for each dirty transfer, returns
to UI ownership, and records heap after garbage collection. The color probe
draws red, green, blue, white, and black horizontal bands in logical portrait
order and then restores the LVGL UI. Its successful return proves transfer
completion, not correct human-perceived color or orientation. The touch probe
records raw and rotation-adjusted coordinates; an operator must touch all four
corners and the center during its sampling window.

## Required item 4 observations

- [x] Pinned runtime identity after a hard reset.
- [x] Soft reset returns to a working UI with the same runtime identity.
- [x] Five same-runtime initialization/deinitialization cycles complete
  without a resource error or material heap decline.
- [x] Twenty-five UI-to-game-to-UI cycles complete with no stuck transfer,
  renderer overlap, or visible stale UI.
- [x] Red, green, blue, white, and black are visually correct and the logical
  480 x 222 orientation is correct.
- [x] Touch reaches all four logical corners and the center with the expected
  rotation.
- [x] Fallback open-AP mode starts and the IDE is usable from a browser.
- [x] IDE server remains responsive while display/touch services are active.
- [x] IDE-to-application and application-to-IDE switching works.
- [x] A deliberately failing application displays the error state and enters
  recovery; the next healthy selection restores normal operation.
- [x] Final state is healthy UI mode with no pending display transfer.

## Session: 2026-08-24

Status: **in progress.** The Phase 4 filesystem was captured and its five
protected digests matched the prior qualification record. A raw full-flash
read was attempted before any erase, but the ESP32-S3 native USB loader
dropped consistently during the read. The filesystem snapshot plus the repo's
exact qualified legacy image provide the recovery path.

The original reproducible reference (SHA-256
`172fb43b08c046e8a90b03caa9ecb1c15af6360f5f589d9b9ef86f31972be6f6`) was
flashed and verified, exposing an
item 4 provisioning failure: its UART-only REPL recipe disabled the board's
native USB console. It was therefore rejected before application provisioning
or runtime qualification. The corrected recipe disables UART and CDC REPL and
enables USB Serial/JTAG. Two fresh clean checkouts produced byte-identical
2,963,840-byte candidates, but physical provisioning then found two defects:
the 8-bit I2C helper dropped the second byte of the CST226's `D2 04` identity
command, and LVGL consumed both bus-owned framebuffer slots before the direct
renderer could allocate one.

The touch driver now uses the legacy driver's raw write-then-read transaction.
The pinned build wrapper adds a module-level `heap_caps_calloc` buffer API so
application DMA buffers are independent of LVGL's two framebuffers. The first
clean build produced the 2,978,512-byte checkpoint recorded above in 1,204.4
seconds.

On this board, software entry through `machine.bootloader()` can leave the
Windows USB endpoint unavailable. Manual ROM-loader entry (hold BOOT while
pressing RESET) is the reliable recovery method; use an ordinary RESET after
flashing to start the application image.

The one-build checkpoint was flashed and its write hash verified. With the
exact frozen touch driver and exact application adapter, the runtime probe
constructed ST7796 and CST226 successfully at logical 480 x 222, reported UI
ownership, and had no transfer pending. A 25-cycle renderer probe then found
that return-to-UI requested a forced LVGL redraw but did not wait for its DMA
completion. The adapter now waits for that completion and passes host tests.

Nightly stopping point (2026-08-25): no further flashing is needed to resume.
The board contains the one-build checkpoint and the updated exact adapter. It
is currently in the display-independent repeated-failure recovery path and may
be safely unplugged. On resumption, press ordinary RESET once, immediately
interrupt COM3, capture `/state/boot.json` and the newest log, then rerun
`probe` and `renderer-cycle`. Do not hold BOOT unless flashing becomes
necessary. No final Phase 5 item 4 runtime or physical claim has been made.

## Session resumed: 2026-08-25

The recovery evidence preserved the original CST226 failure and a stale
failure count of 12. Direct probing with the corrected frozen driver
constructed the full platform successfully. Twenty-five UI/game/UI cycles
then completed with final UI ownership and no pending transfer. Direct 96 x 48
transfers took approximately 3.1 to 3.3 ms; heap declined 464 bytes across the
sample. Return-to-UI, including its forced LVGL redraw, took approximately
55 ms.

The first repeated initialization probe exposed an approximately 4.1 KiB loss
per cycle because upstream display and input wrappers remained in class-level
registries. Modern-platform teardown now deletes the native input and invokes
the upstream display finalizer before releasing the bus. Five repetitions then
completed successfully; after the first warm-up cycle, the remaining four
declined only 400 bytes total and converged to no change on the fifth cycle.

After clearing only the stale recovery counter, normal startup reached
`HEALTHY mode=IDE` with zero consecutive failures. A subsequent software reset
reported the identical MicroPython runtime and again reached healthy IDE mode
with zero failures. The automated color transfer completed for all five bands
at logical 480 x 222. Human observation confirmed correct colors but found both
the direct bands and normal TartLab UI rotated 180 degrees from the physical
board orientation; the panel and touch startup rotation are being corrected
from 90 to 270 degrees before repeating the observation.

The corrected 270-degree panel and touch rotation passed the repeated visual
check: the five color bands and the normal TartLab UI were upright with the
expected colors. Touch samples reached approximately `(13, 19)`, `(471, 3)`,
`(467, 212)`, and `(15, 218)` at the four corners and `(244, 111)` at center.
A second 25-cycle renderer run completed with final UI ownership, no pending
transfer, and no visible stale rectangle; the UI returned cleanly after every
direct-render interval. The fallback open AP and browser IDE then worked while
display and touch services remained active.

Extended observation exposed a new qualification blocker: the board restarted
without operator input. A passive five-minute COM3 capture recorded
`Brownout detector was triggered` at 10:41:10 local time, followed by an
ESP-ROM reset and a healthy sequence 78 IDE boot. There was no Python panic or
watchdog report, and no second brownout in the remaining capture window. The
same session found the screen less bright than the qualified legacy firmware.
Readback showed the modern driver already commanding 100 percent backlight at
PWM duty 65535/65535 (approximately 38 kHz), so software brightness limiting
is ruled out. After changing to a known-good USB power path, a second passive
five-minute capture passed without a reset, including the interval at which the
first connection had failed. A controlled grayscale comparison temporarily
applied the legacy negative-gamma table and restored the modern table; the
operator did not obtain a reliable A/B judgment, but the normal TartLab screen
subsequently returned to its expected brightness without retaining a gamma
change. No panel-gamma change is justified by this session.

The first physical APP selection correctly entered the APP route and displayed
the red error state, then recorded `ImportError: no module named 'testris'` and
entered `startup_error` recovery. The preserved selection still named
`testris.py`, but modern provisioning had installed only `hello.py`; no user
file was overwritten or silently substituted. The following unpressed reset
reached a healthy IDE and cleared the failure counter, qualifying the error and
recovery path while leaving the original selection intact.

For a valid modern APP switch, the host staged a uniquely named, hash-verified
temporary app using only TartLab's public direct RGB565 surface. It saved the
original `testris.py` selection in a cleanup marker and refused path
collisions. Holding the physical upper-right GPIO 12 button during reset
displayed the expected magenta, cyan, yellow, green, and blue vertical bands;
an unpressed reset returned the normal TartLab IDE.

That run exposed a launcher health defect: ESP32 rejects virtual
`machine.Timer(-1)`, and an indefinitely running module never returns to the
existing synchronous fallback. The launcher now tries the virtual timer first,
then hardware timer 3 while avoiding LVGL's timer 0, and deinitializes it as
soon as the three-second APP health window completes. Host coverage verifies
fallback selection, health marking, and timer release. The exact updated
launcher was device-hash-verified as
`265cdae5ed3eae1884c4fdbd27afdd772b99eab46532c72d72d4e0a74daf2d19`.
A repeated physical APP boot logged `Starting APP` at sequence 103 and
`HEALTHY mode=APP update_committed=False` four seconds later while the color
bands remained displayed. The next unpressed reset returned to healthy IDE.
Cleanup restored `testris.py` as the preserved selection and removed only the
temporary app and marker; a final reset again logged healthy IDE startup.

After physical qualification, a second detached clean checkout of the exact
pinned source graph completed the non-flashing container build in 906.7
seconds. Its combined image is byte-for-byte identical to the archived
checkpoint: 2,978,512 bytes with SHA-256
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
This closes the independent-reproduction gate. The subsequent item 5 session
completed the comparative benchmark gate in `tests/PHASE5_BENCHMARKS.md` with a
single LVGL boolean-enum compatibility correction to the hash-bound
application adapter. That later evidence hardware-qualifies the exact research
reference; it does not promote it.
