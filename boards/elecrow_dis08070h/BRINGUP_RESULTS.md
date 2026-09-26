# CrowPanel 7-inch bench results — 2026-09-12–20

**Feasible flash budget; early runtime proof complete.** The board remains
`bringup`. Physical SD storage and root switching now pass baseline checks.
The revised native firmware also passes repeated diagnostic soft reset and
the bounded SD/RGB/radio load. September 14 startup and integrity checks also pass.
Normal TartLab startup still awaits RGB platform integration and working touch.
Follow [BRINGUP_PLAN.md](BRINGUP_PLAN.md) for the remaining gates.

## Hardware and firmware

The owner confirmed PCB **V3.0**. ROM probing reports ESP32-S3 revision 0.2,
4 MiB quad flash, and 8 MiB PSRAM. Secure boot and flash encryption are off.
A full original-flash backup and hash are retained in the ignored session
directory; no unit identifiers or original flash bytes are checked in.

The initial experimental build of the existing pinned MicroPython 1.27.0 /
LVGL 9.4.0 / ESP-IDF 5.5.1 graph completed and was flashed successfully.
The combined image's bootloader/app digests, partition-table checksum,
physical bounds, and written-flash hash passed verification.

| Measurement | Result |
| --- | --- |
| Combined image | 2,981,472 bytes |
| SHA-256 | `df6e2da916d7900914c311f0a6e752ee2c2801d2fa823044b37f7259713ba15c` |
| Application image | 2,915,936 bytes |
| Application partition | 3,145,728 bytes |
| Application headroom | 229,792 bytes |
| Internal filesystem | 983,040 bytes / 240 blocks of 4,096 bytes |
| Free Python heap after baseline GC | 8,308,416 bytes |
| CPU | 240 MHz |
| LVGL runtime | 9.4.0 |
| Console | UART0, 115200 baud through USB bridge |

The image is local at `build/crowpanel7/firmware.bin`; its exact original
recipe snapshot is `build/crowpanel7/built-lock.json`. The current lock selects
the later native reset repair and corrected frozen storage helper, described
below; it does not describe this initial binary. Native source patches
performed by the existing build wrapper produce the expected `-dirty`
MicroPython version string; reproducibility still requires independent builds.

## Storage and baseline checks

- Imports of `lvgl`, `lcd_bus`, `rgb_display`, `gt911`, and `external_root` work.
- An internal test file survived hard reset and remained readable.
- Wi-Fi scan found 14 networks; no SSIDs or credentials were retained.
- A 256 KiB RAM FAT volume became `/`, internal storage remained readable at
  `/flash`, and the original root was restored. This is a VFS proof, not an
  SD-card performance or persistence result.
- The native SD interface reached card initialization and reported the absent
  card. Three retries with garbage collection returned the expected error.
- The installed internal `/main.py` reported unavailable SD startup and
  retained the serial REPL. REPL and the persistence file remained accessible
  after hard reset. No card was formatted.

The pinned LVGL fork replaces stock `machine.SDCard`: it requires `spi_bus`
and an integer `cs`. Its native SPI bus must remain strongly referenced across
failed attempts; creating a bus again after collection produced a TypeError
in the initial experiment. The corrected helper caches the bus for the boot
lifetime and retains the card's bus while mounted.

## Display and touch

The standalone RGB fixture completed a 45-second timer loop with two 38,400-byte
internal DMA draw buffers and the native driver's PSRAM scanout buffers.
The first run reported 697 timer iterations and 6,711,792 bytes of free Python
heap. Timer iterations are **not a measured frame rate**. The owner confirmed
correct colors but reported horizontal wrapping: the red tile starts inset
from the left, and `IGHT` from both right-corner labels wraps onto the left.
Alignment therefore fails at the initial 15 MHz setting. Flicker, tearing,
and physical brightness remain unconfirmed by an operator.
The final run using the conservative software I2C setting completed 696
iterations, retained 6,439,664 free heap bytes, and saw the PCA9557 at `0x18`.

On-device LVGL inspection showed screen width 800, zero left padding and
horizontal scroll, red tile x=0, and the top-right label at x=722 with width 78.
The logical geometry is correct. Scanout starvation/drift is the leading
hypothesis, not yet a confirmed root cause; Espressif documents permanent
shifts when PSRAM DMA cannot keep up. The first firmware has no RGB bounce
buffer and `CONFIG_LCD_RGB_RESTART_IN_VSYNC` is off.

The working bring-up setting requests a **10 MHz pixel clock**, preserving
the vendor porches and clock polarity. Yellow and cyan vertical edge markers
were added to the fixture. This reduces requested scanout bandwidth by one
third. The owner confirmed **edges and labels are correct** at this setting:
the initial horizontal wrapping is resolved in the visual test. Keep 10 MHz
as the bring-up default. This is not yet a sustained display/network/storage
stress qualification, and the precise starvation mechanism is still unproven.
If drift returns under load, investigate native scanout buffering/restart and
cache behavior before compensating with an arbitrary widget or porch offset. See
[Espressif's RGB driver guidance](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html).

The 10 MHz run completed 633 timer iterations with 6,709,824 free heap bytes.
Its input scan incorrectly acknowledged every address and the attempted GT911
read returned an all-zero ID and geometry. That is invalid touch evidence,
not a newly discovered controller. The fixture now rejects an all-address ACK
scan. This input issue does not change the owner's visual alignment result.

Touch is unresolved. Hardware I2C at 100 kHz found no devices. Software I2C
found the PCA9557 at `0x18` at 10, 25, and 50 kHz, but not 100 kHz. Individual
output/configuration/polarity register writes read back correctly at 10 kHz.
The V3 touch reset sequence completed, but neither GT911 address (`0x5d`,
`0x14`) responded. The bench payload now selects a conservative 10 kHz software
bus; this is diagnostic evidence, not a qualified touch configuration.

Next touch checks: physical display/touch observation and a full power cycle,
then bus waveforms/pull-ups, reset/interrupt lines, and panel connection against
the V3 schematic. Retain the working UART console throughout.

## Physical SD card — September 13

The owner inserted a nominal 32 GB card. Read-only inspection found one FAT32
LBA partition (type `0x0c`) starting at sector 8,192. Its only pre-existing root
entry was `System Volume Information`, which was preserved. No formatting or
raw-sector writes were performed.

| Measurement | Result |
| --- | --- |
| Raw card capacity | 61,132,800 × 512 = 31,299,993,600 bytes |
| FAT filesystem capacity | 31,287,410,688 bytes (about 29.1 GiB) |
| FAT allocation unit | 32,768 bytes |
| SPI clock requested | 1 MHz |
| Verified file sizes | 0, 511, 513, 8,193, and 1,048,576 bytes |
| 1 MiB write plus sync | 11,549 ms (about 88.7 KiB/s) |
| 1 MiB read plus SHA-256 after hard reset | 10,003 ms (about 102.4 KiB/s) |
| SD mounted as `/`; internal storage at `/flash` | Passed; original mounts also restored |

All five hashes matched independently generated host expectations, both
immediately and after `machine.reset()`. The 1 MiB pattern varies between
4 KiB chunks and crosses FAT cluster boundaries. These are bounded storage
checks, not a full-capacity test of the card or a power-loss qualification.

The first write attempt failed with `EIO` while opening its first test file.
Investigation reproduced a **native object lifetime bug**: close card A, open
card B, read successfully, call `gc.collect()`, then B's reads return `False`.
The pinned fork's SD deinitialization removes its native slot before checking
the SPI device's active state; its early return can leave the host-init flag
set for a later finalizer. The SPI SD constructor also does not set the active
field like the ordinary SPI-device constructor. The current helper avoids that
unsafe lifecycle: cache one native SD card and bus per host for the boot
lifetime, release only card initialization with `ioctl(2, 0)`, and return a
separate guarded lease for each open. Concurrent opens and configuration
changes are rejected. A closed lease cannot access a subsequently reopened card.

This intentionally reserves the native SD SPI device for the boot lifetime; it does
not promise to release the SPI host for another use. The old failed test
directory remains on the card as evidence. The successful test uses a separate
directory. The corrected helper was uploaded to internal flash and loaded after
hard reset; the native firmware image was unchanged during these baseline
tests. The next-build lock was updated to the corrected helper's source hash.

Ten explicit close/reopen/GC cycles passed after the correction. Read-only
fault injection with zero-filled and failing block devices produced `ENODEV`
and `EIO` respectively while preserving the internal root. These simulated
media errors do not substitute for physical removal or corruption testing.

A board-selected `makedist.py` build produced 80 files / 652,787 bytes, reusing
the existing built web assets. The bench installation verified 85 files /
660,683 bytes, including diagnostic entry points and board identity/selector.
The normal packaged `/boot.py` and `/main.py` are preserved under
`/.tartlab-bench/packaged-boot.py` and `packaged-main.py`. The diagnostic is
intentionally distinct from normal TartLab startup; the unintegrated RGB
factory was not silently bypassed and presented as a working application.

After hard reset, the installed internal launcher mounted SD at `/` and flash
at `/flash`. Bench startup counters were exactly `boot=1, main=1`. The protected
selector loaded from `/device/hdwconfig.py`, its runtime from the selected
`/board` directory, and TartLab from `/lib/tartlabutils/__init__.py`. Asset/help
directories were accessible and `/state/sd-bench.json` and
`/files/user/sd-bench.txt` were written on SD. The internal launcher remained
readable at `/flash/main.py` (1,046 bytes). Free Python heap before display
initialization was 8,201,296 bytes.

With the standalone 10 MHz RGB fixture refreshing, a further 1 MiB SD copy,
sync, and readback matched the host's expected hash. Copy plus sync took
25,358 ms; the complete run including readback took 42,003 ms. Repeated GC
during the copy caused no I/O errors. Free Python heap afterward was
6,736,672 bytes. No simultaneous network load was included.

The owner then confirmed the requested power removal/reconnection and return
of the correctly aligned diagnostic: “Yes, that worked.” Post-cycle inspection
reported power-on reset cause `1`, exactly `boot=2, main=2`, the final `SD root
OK` status, and matching state/user-file counters. All 85 installed file hashes,
all five original test files, and the additional 1 MiB display-load output
matched host expectations after cold boot. Free Python heap was 6,714,144 bytes.
Flicker and alignment specifically during the copy were not separately
described, so those detailed observation fields remain unset.

The bench tools retain host-derived hashes, serial output, and a resumable
staging journal in `hardware_test_artifacts/crowpanel7-20260913/`. Unit tests for
the lease behavior, staging collision protection, board catalog, and firmware
tooling passed (30 tests). New staging sessions bind partial-write resumption
to a marker on the card and preserve files modified after successful transfer.

## SD continuation: soft reset and bounded radio load

The continuation first rechecked the running diagnostic and then sent Ctrl-D
from the friendly REPL. **Soft-reset SD startup failed.** The launcher reported
unavailable SD and retained the internal filesystem and usable serial REPL.
An explicit retry failed while constructing `SPI.Bus`, before card mounting.
A hard reset recovered the diagnostic with exactly `boot=3, main=3`; all 85
installed files and five baseline files still matched their host expectations.

Local inspection of the exact pinned source found that
`micropy_updates/esp32/machine_hw_spi.c` retains heap-allocated bus pointers in
the static `machine_hw_spi_bus_objs` array. The built ESP32 `main.c` does not
call `mp_machine_hw_spi_bus_deinit_all`, and the corresponding builder insertion
is commented out. After soft reset, the constructor converts fields through
the retained pointer. The observed `TypeError` is consistent with stale native
state. The previously corrected Python cache cannot survive an interpreter
reset. Do not simply enable the cleanup call: the same source's device-list
registration and SD active/deinitialization handling also need repair and
native lifecycle tests. This remains a firmware gate, not a Python fix proved
by the storage lease tests.

With the recovered diagnostic, eight consecutive cycles each copied, synced,
and reread a separate 1 MiB file while the 10 MHz RGB fixture refreshed. Each
cycle also started a password-protected access point, scanned in station mode,
kept the AP active throughout SD I/O, and stopped both interfaces afterward.
The generated network configuration stayed in RAM; no credentials or scanned
network identities were retained. All eight source and destination hashes
matched the host-generated pattern.

| Measurement | Result |
| --- | --- |
| Verified new outputs | 8 files / 8,388,608 bytes |
| Sum of measured cycle durations | 375,377 ms (about 6 minutes 15 seconds) |
| Individual cycle duration | 46,415–47,177 ms |
| Free Python heap at cycle end | 6,732,096–6,732,144 bytes |
| Minimum sampled free heap after GC | 6,728,256 bytes |
| Explicit garbage collections | 144 |
| LVGL timer calls during the measured work | 4,104; not a frame-rate measurement |
| Startup counters before and after load | `boot=3, main=3` |
| AP active through I/O; both interfaces stopped afterward | Passed in all eight cycles |

This is a bounded storage/display/radio exercise, not a sustained network
throughput, full-card, or power-loss qualification. Python heap readings do not
establish internal DMA-memory headroom. The owner said they could not observe
the display during this run; alignment, flicker, and tearing remain unobserved.

After the load, the new `soft-reset` runner reproduced the failure on its first
requested cycle and stopped; it did not claim the remaining requested cycles
passed. The complete traceback reports `TypeError: can't convert str to int`
at the helper's `SPI.Bus` construction. The device remained at internal rescue.
A subsequent hard reset restored `SD root OK`, with exactly `boot=4, main=4`
and matching state/user-file counters. All **98 files** (85 installed, five
baseline, and eight load outputs) matched host expectations after that reset.
The board was left running the diagnostic with its UART REPL available and
both Wi-Fi interfaces inactive. No firmware or installed entry point changed.

The host runner now provides `status`, `soft-reset`, and resumable `soak`
actions, complete reset capture, exact file-coverage checks, unique retained
outputs, and a journal after each completed cycle. Host tests cover partial
evidence, counter/selector mismatches, reset failure capture, collision
preservation, interrupted-load Wi-Fi cleanup, and resume validation.
All 36 focused tests passed, as did Python compilation, catalog/firmware-lock
validation, and whitespace checks. Detailed continuation evidence is indexed by
`hardware_test_artifacts/crowpanel7-20260913/continuation-summary.json`.

## Native reset repair and final regression — September 13 evening

Docker became available later in the session. The experimental lock now selects
the separate hash-bound [native repair wrapper](NATIVE_RESET.md), retaining the
same pinned source graph and qualified wrapper. A fresh checkout and seven nested
repository commits were verified before building with the pinned IDF container.
The final source transformations matched the recipe. This is one successful
clean build of the final revision, not independent reproducibility evidence.

| Measurement | Final revised image |
| --- | --- |
| Combined image | 2,983,056 bytes |
| SHA-256 | `af09dbba1b3beb58fd97b00f8e2716f492028f4cb8d14ac53996fc1036f00be7` |
| Application image | 2,917,520 bytes |
| Application headroom | 228,208 bytes |
| Internal filesystem | Unchanged: 983,040 bytes at `0x310000` |
| Flash write | 115200 baud; written-data hash verified |

A current 4 MiB flash backup was retained before replacement. Firmware writes
preserved the internal filesystem. The corrected helper is now frozen; the
former internal override was renamed to `/flash/external_root.previous.py`.
The active override's absence was checked before testing the frozen helper.

Two earlier repair images exposed retained LVGL state after native SD reopening
was fixed. One failed display allocation; the next crashed in the display linked
list and recovered through a hard reboot. The final correction explicitly clears
both custom VM roots and the exported LVGL pointer: `mp_init()` does not clear
custom roots. These failed images/logs remain archived. The host capture now
rejects panic output and unexpected ROM startup even if the diagnostic returns.
An interrupted build also exposed duplicate patch application; the hook rejects
that condition, and the final image was built from a fresh checkout.

All final machine checks passed:

- Ten native SD close/reopen/GC cycles bypassed the Python cache: 20 matching
  sector-zero reads and ten closed-object guard checks. Repeated deinit and old
  finalizers did not disrupt the newly opened card. No raw-sector writes occurred.
- The diagnostic returned after the raw native test, followed by three full
  friendly-REPL soft resets. Boot/main each advanced exactly once, 19 -> 20 ->
  21 -> 22; reset cause stayed `machine.SOFT_RESET` (`5`). SD root, selector,
  library/runtime paths, and persisted state/user counters remained consistent.
- After each soft reset, free Python heap was 6,739,168 bytes, sampled internal
  DMA free space was 166,211 bytes, and the largest DMA block was 98,304 bytes.
  These samples were stable across the three cycles.
- Eight 1 MiB SD copy/sync/readback cycles passed with RGB refresh, AP activity,
  and station scans. Total measured cycle time was 364,965 ms; individual cycles
  took 45,331–45,810 ms. There were 144 explicit collections and 4,104 LVGL timer
  calls, which are not a frame-rate measurement.
- Cycle-end Python heap was 6,733,216–6,733,376 bytes; minimum sampled heap after
  GC was 6,729,360 bytes. With the AP still active, sampled internal DMA free
  space was 115,199–115,219 bytes, with a largest block of 49,152 bytes.
  These are samples, not a continuous worst-case memory measurement.
- Both Wi-Fi interfaces stopped after each cycle. Network transfer was zero;
  this exercise does not establish network throughput.
- After the final hard reset, all 98 hashes matched: 85 installed files, five
  baseline files, and eight new load outputs. Boot/main and state/user counters
  were all `23`. Earlier outputs and failed-attempt evidence were preserved.

The focused host suite passed 39 tests with one explicit native-compiler skip;
all three native tests passed separately in the pinned container with address
and undefined-behavior sanitizers. Catalog, firmware lock, Python compilation,
and whitespace checks also passed. Visual load observations remain null because
the owner could not observe the display. Touch still reports the invalid
all-address ACK condition and is unresolved.

Final machine evidence and derived measurements are indexed at
`hardware_test_artifacts/crowpanel7-20260913/native-reset/revision3/final-checks.json`
and `measurements.json` beside it. The exact firmware, recipe, source hashes,
build/flash logs, and current backup are under `build/crowpanel7-soft-reset/`.
The initial image and earlier bench evidence remain in their original locations.

## September 13 handoff

The final revised image is installed. SD is `/`, internal flash is `/flash`,
and the board is at `SD root OK | TartLab runtime integration pending` with UART
REPL available. Files were closed and synced, both Wi-Fi interfaces are inactive,
and all build/test processes have finished. This is the stopping point for
shutdown; no additional test or physical observation is needed tonight.

On the next session, capture startup and run `status` against the staging
inventory and the final soak evidence before further experiments. Keep the
baseline session name `baseline`; its remote test directory depends on that name.
The final soak journal is
`hardware_test_artifacts/crowpanel7-20260913/baseline/20260913-201250-2be2fef7-soak.json`.
Retain the ignored build and evidence directories locally.

Next gates are an observed cold boot and visual load check on this revised image,
touch recovery, normal TartLab RGB ownership integration, network throughput,
absent/full/removed/corrupt-media recovery, and independent clean firmware
reproduction. The earlier observed cold boot applied to the initial image.
The successful bounded tests do not promote the board beyond `bringup`.

## September 14 continuation

The revised firmware completed a captured hard-reset diagnostic startup with
boot/main and state/user counters all at `25`. All 98 installed, baseline, and
previous soak-output hashes matched. This confirms persistence across the
session boundary; a physical cold boot is not inferred from a software reset.

Touch inspection reproduced the invalid all-address ACK condition. Explicit
open-drain pin initialization with pull-ups left SDA reading `0` and SCL `1`.
A hardware-I2C comparison reached its scan but then raised `AttributeError`
because this pinned implementation has no `deinit()` method; it is not a
completed hardware-I2C test. Reinitializing software I2C afterward still gave
the same line levels and false scan.

After that comparison, the USB Serial/JTAG CONF0 register was `0x200`, with
USB_PAD_ENABLE already clear. Clearing that bit preserved the value and did
not change the line levels or scan; the original register value was restored.
The register address and bit were checked against ESP-IDF 5.5.1's
[register base definitions](https://github.com/espressif/esp-idf/blob/v5.5.1/components/soc/esp32s3/register/soc/reg_base.h)
and [USB register definitions](https://github.com/espressif/esp-idf/blob/v5.5.1/components/soc/esp32s3/register/soc/usb_serial_jtag_reg.h).
The generated sdkconfig still enables the secondary USB console. This test
does not establish its behavior before pin initialization or on cold boot.

Nine open-drain recovery clocks and a STOP did not release SDA. Every sampled
high clock read SDA `0`, SCL `1`. These are GPIO samples, not oscilloscope
measurements or proof of a wiring fault. No controller reset writes were
attempted on this invalid bus.

The new `sd_bringup.py touch` action records released line levels, uses a
software-I2C diagnostic scan only on an idle bus, and requires a GT911 product
ID plus nonzero geometry. It fails on a low line, all-address ACK, missing
controller, zero identity/geometry, or read error. It does not reset the
controller, reopen the active SD mount, or qualify touch coordinates. The
older `board_probe.py` now stops before expander/controller transactions on
an invalid bus, including a fault appearing after reset. Six focused touch
tests and all ten SD bringup tests passed.

Evidence is in `hardware_test_artifacts/crowpanel7-20260914/`, with the full
integrity result at
`hardware_test_artifacts/crowpanel7-20260913/baseline/20260914-123929-95b6da54-status.json`.
No firmware or installed payload was replaced. In response to the requested
full power cycle, the owner reported: "Yes, it's still aligned and stable."
The subsequent state capture reports power-on reset (`1`), with boot/main and
state/user counters all advancing once to `26`. The new `touch` check still
records SDA `0`, SCL `1` and correctly fails before controller transactions.
This confirms the fault persists after that restart. Visual behavior during
combined SD/display/network load remains unobserved.
All 98 hashes passed again after that power cycle; the result is
`hardware_test_artifacts/crowpanel7-20260913/baseline/20260914-124656-2b922787-status.json`.
The board remains at `SD root OK`, with UART REPL available. The continuation
summary and exact operator response are retained in the September 14 session.

Next isolate the bus with physical line/pull-up/panel-connection checks and
the outstanding console configuration audit. No electrical fault or controller
failure has yet been established. Keep invalid-bus guards in place before
further expander writes. Normal TartLab RGB ownership integration and the
remaining recovery/qualification gates are unchanged.

## UART-only console comparison — September 14

The previous firmware's generated sdkconfig selected a secondary USB
Serial/JTAG console despite disabling that MicroPython REPL. A raw soft reset
that skipped `main.py` reproduced SDA `0`, SCL `1` with only the internal
filesystem mounted and no RGB display running. USB CONF0 before pin
initialization was `0x4200`. A subsequent comparison actually cleared
USB_PAD_ENABLE (`0x4200` to `0x200`), but SDA remained low; the register was
restored afterward. The earlier bit-clear comparison had started at `0x200`.

The recipe now explicitly disables the secondary USB console. A fresh build
from the same pinned sources passed image and final sdkconfig inspection.
The seven patched native/binding source files match the previous build's
files byte for byte. `modern_board_firmware.py inspect-console` rejects the
previous configuration and accepts the new one; it distinguishes an omitted,
disabled derived Kconfig symbol from missing primary/secondary choices.
All 13 firmware-tool tests passed.

| UART-only image measurement | Result |
| --- | --- |
| Combined image | 2,981,216 bytes |
| SHA-256 | `1201fbc10c7347cc2cb9fbc28639c7aebfe0060e00654caca0064d2cafca49f9` |
| Application | 2,915,680 bytes |
| Application headroom | 230,048 bytes |
| Partitions | Unchanged from the previous image |

A current 4 MiB backup was retained before flashing. Its bootloader, table,
and application match the previous image; runtime NVS contents differ from
the combined image's blank padding. Separate writes of the bootloader/table
and application preserved NVS, PHY data, and the internal filesystem. Both
writes completed with hash verification. The new image completed captured
diagnostic startup, but its initial touch check still reports SDA `0`, SCL `1`.

The image, exact recipe, backup, generated sdkconfig, build/flash logs, and
inspection results are under `build/crowpanel7-uart-only/`. Hardware comparison
evidence is under `hardware_test_artifacts/crowpanel7-20260914/console-audit/`.
All three full diagnostic soft resets passed, with boot/main counters advancing
`31 -> 32 -> 33 -> 34` and 6,739,168 free Python heap bytes after each cycle.
The owner reported: "There were no display problems, but touch was unresponsive."
This applies to the observed diagnostic restarts, not combined SD/radio load.
All 98 installed/baseline/previous-load hashes passed afterward, at counters
`34`. The results are indexed in `console-audit/summary.json`; the full integrity
evidence is
`hardware_test_artifacts/crowpanel7-20260913/baseline/20260914-174546-d3e9e32a-status.json`.
The owner then confirmed a full power cycle and reported that touch still
did not respond. The device recorded power-on reset (`1`), with boot/main and
state/user counters all `35`. All 98 hashes passed again in
`hardware_test_artifacts/crowpanel7-20260913/baseline/20260914-174915-8db7dac9-status.json`.
The touch probe still reports SDA `0`, SCL `1`. Removing the secondary console
therefore did not repair touch, including after a physical cold boot.

With the board at `SD root OK`, the owner measured **SCL 3.2 V** and
**SDA 0.6 V** to board ground at the I2C connector. The meter confirms an
electrically low SDA line; this is not just a false GPIO reading. It does not
identify which component or connection is responsible.

For the next comparison, both MCU touch pins were set to input-only with
pull-ups and USB pad ownership was cleared (`0x4200` to `0x200`). GPIO samples
remain SDA `0`, SCL `1`; no I2C transactions or controller writes were issued.
The owner confirmed unchanged meter readings (SCL 3.2 V, SDA 0.6 V) and no
external device connected to the I2C port.

### P4 touch-ribbon isolation

After disconnecting P4 with power removed and powering the board again, the
owner noted that its ZIF latch appeared previously not to have been fully
closed. The touch probe now reads SDA `1`, SCL `1`, both before and after its
10 kHz scan. It finds no addresses, so neither a GT911 nor the onboard expander
has been verified in this state. The probe's overall touch result remains
false because no valid controller identity or geometry is available with the
touch ribbon disconnected.

This result was repeated after the owner's September 15 confirmation that P4
was disconnected and power was on. Evidence files in `console-audit/` are
`20260914-180527-da3b5401-touch.json` and
`20260915-074631-f22c817f-touch.json`. Releasing SDA by disconnecting P4 points
to the ribbon connection or panel side of that connection, but does not yet
identify a failed component.

### P4 reseated and USB pad ownership — September 15

The owner confirmed P4 was properly inserted but saw no touch feedback.
The initial probe still found no addresses, with SDA/SCL both high. Clearing
USB pad ownership (`0x4200` to `0x200`) then produced addresses `0x14` and
`0x18`, valid GT911 product bytes `911\0`, and geometry 800 x 480. Evidence:
`console-audit/20260915-074850-778d0ada-touch.json`. The loose connection and
pad ownership observations are distinct; neither alone proves a failed part.

The owner performed the requested taps/drag during a 60-second raw capture.
That capture recorded zero single-touch coordinates and three release samples;
finger response therefore did not pass that check. Evidence:
`console-audit/20260915-075055-reseated-touch-samples.json`.

An explicit hardware-I2C comparison changed USB CONF0 from `0x4200` to `0x200`
without a direct bit-clear command during initialization. Its scan found both
addresses; a subsequent read returned valid GT911 identity and geometry.
Evidence: `20260915-075232-hardware-touch-compare.json` and
`20260915-075300-hardware-touch-compare.json` under `console-audit/`.
The standalone GPIO sample after hardware I2C initialization read SDA `0`
even while controller reads succeeded; it is not used to claim an electrical
fault in that peripheral-owned state.

The declarative board payload now selects hardware I2C host 0 at the same
10 kHz frequency. Only that host field was changed in the installed SD payload;
the previous bytes were backed up, the replacement hash was verified, and its
configuration was checked against the repository payload. The original staging
inventory remains intact. Subsequent integrity checks must use
`console-audit/sd-stage-hardware-i2c.json`, which records the changed expected
hash. The firmware and internal rescue files were unchanged.

The hardware-I2C diagnostic restart initialized the GT911 and reached
`SD_BENCH_READY`, with boot/main counters both 41. Its 45-second fixture logged
no press events, but the owner reported possibly starting too late, so this
does not establish a failed physical touch test. All 98 file hashes passed
using the derived inventory in
`baseline/20260915-075546-76292a93-status.json`.

The two-minute replay displayed a countdown and press count. The owner
confirmed: "Yes, it works!" Serial evidence recorded 19 press events, all
within the 800 x 480 geometry, including points near each corner and the center.
Evidence: `console-audit/20260915-075947-touch-visual-replay.json`. This verifies
finger response through the initialized GT911/LVGL fixture. Exact coordinate
calibration and a renewed explicit display-alignment observation were not
established by that response.

The owner then confirmed the requested full power cycle was complete. The
device reported power-on reset (`1`), hardware I2C host 0, USB CONF0 `0x200`,
valid GT911 identity and geometry, and **seven additional press events**, all
within the panel bounds. Boot/main and persisted state/user counters all read
42. SD remained the FAT root, the internal rescue filesystem remained at
`/flash`, and the installed board payload hash matched the derived inventory.
Evidence: `console-audit/20260915-080109-hardware-i2c-cold-boot.json`.
This cold-boot check verifies runtime state, touch response, and the changed
payload; the full 98-file integrity pass was immediately before this power
cycle. Touch communication and finger response now pass warm and cold startup.
Shared TartLab RGB ownership integration and remaining qualification gates
are still open; the board remains in bringup status.

## Shared RGB runtime integration — September 15–19

The board now selects `tartlabdrivers.display.rgb` and hardware touch I2C through
its declarative payload. The shared factory accepts RGB wiring and optional
display reset, selects the responding touch address from the configured list,
and accepts the existing external-storage declaration. The RGB adapter handles
direct rectangles without panel command writes and retains TartLab's RGB565_BE
buffer contract. With the native 16-bit RGB bus, byte swapping is implemented
by swapping data lanes; caller buffers remain unchanged.

The pinned native rotation-0 copy path uses inclusive row ends for full-width
transfers but exclusive row ends for partial-width transfers. The board's
`partial_y_end_exclusive` setting enables compensation in both direct and LVGL
flushes. The adapter currently accepts native orientation and zero offsets.
Its completion signal means the source buffer has been copied; presentation
and VSYNC follow asynchronously. It does not advertise a frame-sync capability.

The built runtime payload passed 94 host tests covering existing platforms,
RGB rectangle edges, source preservation, touch address selection, and
ownership handover. The board catalog remains bringup/qualification unchanged.
The firmware binary was not changed for this integration.

Hardware evidence under `hardware_test_artifacts/crowpanel7-20260915/runtime/`
records successful shared-platform creation at 800 x 480 with touch, a
bottom-right direct pixel write with source preservation, and a return to UI
ownership. `20260915-081617-visual.json` records 144 direct writes and six
ownership cycles, no pending transfer, and 5,930,576 free Python heap bytes.
That run has no touch points or physical visual confirmation; its name does
not imply a visual pass.

Three same-interpreter teardown/recreation cycles subsequently passed,
including idempotent teardown, new GT911 initialization, a direct pixel write,
and UI restoration. Free heap was 5,934,448, 5,934,400, and 5,931,968 bytes.
Evidence: `20260919-100133-recreate.log`.

Normal built `/boot.py` and `/main.py` then replaced the diagnostic entry points.
The original diagnostic bytes and each replaced runtime file are backed up in
the artifact directory; writes were hash verified. The new inventory is
`sd-stage-normal-startup.json`. Internal rescue files were preserved.
`20260919-100256-hard-startup.log` records normal boot sequence 1, GT911 identity,
and `Starting IDE`, with no captured exception/recovery marker. The owner
reported: "Everything look normal." in response to observing the launcher,
its countdown, the IDE/status screen, colors, edges, and flicker/tearing.

The owner then reported: "Oops, now the horizontal offset has changed a couple
times, shifting and wrapping around to the right." This supersedes any implied
stability pass from the initially normal screen. The normal SD hash check had
verified eight files before a batch containing several 1 MiB files exceeded
its 90-second host timeout. It is incomplete, not a content-mismatch result.
Reads were subsequently interrupted and files synced; the board remained
responsive. Normal boot state had recorded sequence 1, healthy, IDE, and zero
consecutive failures.

The installed native RGB path uses two PSRAM frame buffers without bounce
buffers; `CONFIG_LCD_RGB_RESTART_IN_VSYNC` is disabled. The
[ESP-IDF 5.5.1 RGB guide](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html)
documents persistent displacement after scanout bandwidth starvation. This is a working
hypothesis, not a confirmed cause. Compare idle/load behavior and lower pixel
clock before choosing a native-buffering change. Normal-startup soft-reset
checks are paused while investigating display stability. The diagnostic
`sd_bringup.py status` action assumes diagnostic globals/counters and is not
the normal-startup health check. Recovery, sustained combined load, and release
qualification remain separate gates.

The next comparison changes only the installed board payload pixel clock from
10 MHz to 8 MHz; its prior bytes are retained as `pre-8mhz-board.py`. Normal
startup again reached a healthy IDE route, sequence 2. The comparison inventory
is `runtime/sd-stage-8mhz.json`. Hash verification now journals each file
individually with a separate timeout. All **99 file hashes passed** in
`runtime/20260919-100909-8mhz-integrity.json`; normal boot state remained healthy,
IDE, with zero consecutive failures. The owner reported: "It seems to be
working fine now." after watching the restart and ensuing read load.
This is a bounded observation, not sustained qualification. The repository
payload now keeps 8 MHz, and its rebuilt minified bytes match the installed
comparison payload exactly. Normal-runtime soft-reset checks have resumed.

`runtime/20260919-101257-soft-startup.log` records `MPY: soft reboot`, exactly
one normal boot-diagnostics record (sequence 3, reset cause 5), valid GT911
initialization, and `Starting IDE`, without a captured exception/recovery marker.
The owner then completed a physical power cycle at 8 MHz, tapped IDE in the
launcher, and watched alignment for approximately one minute, reporting:
"Yes, that works." `runtime/20260919-101621-normal-cold-boot.json` records
power-on reset (`1`), normal sequence 4, healthy IDE route, zero consecutive
failures, 8 MHz pixel clock, and touch I2C host 0. All six changed startup/runtime
files matched their expected hashes. SD remained the FAT root and internal
rescue storage remained at `/flash`.

The board was restarted into normal TartLab after the serial checks. Shared
RGB integration and bounded startup/read-load checks now pass at 8 MHz.
This does not qualify sustained simultaneous rendering/network/storage,
representative games, exact touch calibration, recovery, or promotion.

### Combined runtime load continuation

The combined test uses the shared RGB platform at 8 MHz and the existing SD
copy/readback helper. The helper now accepts a progress callback so the platform
can retain ownership of LVGL ticks. Each cycle copies and verifies a distinct
1 MiB output, scans Wi-Fi, and keeps a temporary protected AP active during I/O;
it measures radio coexistence, not network throughput. Existing active network
interfaces are rejected before file creation, then explicitly stopped for this
isolated test. Normal IDE startup restores its networking afterward.

The first run completed two cycles, but the owner reported no visible screen.
It was interrupted; its visual result is a failure, regardless of the verified
file cycles. Inspection found backlight on, active screen matching, UI ownership,
and no pending transfer. Explicit white text on a blue background plus a forced
redraw became visible, confirmed by the owner. Styling versus refresh was not
isolated. The replay uses explicit white text and a completed redraw for each
progress update. Evidence and preserved partial outputs are indexed under
`hardware_test_artifacts/crowpanel7-20260919/combined/`; the new eight-cycle run
is in `visible-retry/`.

The replay completed two file/radio cycles. The owner reported progress working
but no touch coordinates. The test was stopped to investigate input polling;
neither interrupted run counts as the requested eight-cycle combined pass.
The periodic task was active and LVGL ticks advanced by 198 ms during a 200 ms
sample, but the LVGL binding's nesting counter read 1. The pinned task handler
skips its LVGL processing when that counter is nonzero. This identifies a
possible polling obstruction, not its cause; do not force-clear the counter.
The user then needed to step away, so interactive checks paused and the board
was returned to normal 8 MHz startup. Next: instrument a fresh-reset fixture
through creation and ownership handover, then repeat combined load only after
visible touch feedback works. Retain all interrupted outputs and journals.

On resuming, `combined/20260919-103808-probe.log` reproduced nesting 1
immediately after platform creation and throughout ownership handover following
a raw soft reset. A normal hard restart then reached the IDE without captured
errors (`runtime/20260919-103900-hard-startup.log`). The next probe,
`combined/20260919-104007-probe.log`, measured nesting 0 before soft reset,
before platform creation, and throughout creation and ownership handover.
This establishes hard restart as a successful recovery in this comparison;
it does not yet establish what originally left the counter nonzero. The pinned
binding generator increments the native static counter around Python callbacks
without exception-unwind cleanup, so interruption during a callback remains a
candidate cause. Do not manually clear this counter. The fresh load fixture
requires nesting 0 and a two-minute touch preflight before creating load outputs.

The fresh-restart fixture captured **43 presses** during that preflight. The
owner initially reported a blank screen, then its appearance, and confirmed:
"Okay, that seems to work perfectly." All **eight 1 MiB copy/readback cycles**
then passed with AP activity, station scans, periodic GC, and normal scheduled
LVGL refresh/input processing. Total measured cycle time was **454.806 s**;
minimum sampled free Python heap after GC was **5,841,776 bytes**. Input captured
**72 presses during load**, and nesting remained 0 at every cycle boundary.
The owner reported: "That also seems to work very well." Evidence is in
`combined/fresh-restart/load.json` and its operator observations. This passes
the bounded shared-runtime coexistence check; network throughput, longer
endurance, interruption recovery, and the original nesting failure remain
separate investigations.

After a normal hard restart, all **107 installed, baseline, and load-output
file hashes matched** (`combined/fresh-restart/persistence.json`). The final
restart reached `Starting IDE` without captured error markers; the board was
left at normal 8 MHz TartLab startup. `combined/fresh-restart/finalize.json`
indexes both restart captures and the persistence result.

### Unattended endurance continuation

The reusable `tools/sd_runtime_bench.py` runner replaces the one-off normal-runtime
scripts. It binds resumption to the installation inventory and load contract,
rehashes completed outputs, retains partial attempts, and restores normal IDE
startup. A separate operator form cannot pass while observations are unanswered.
The fixture counts actual LVGL timer callbacks, drains display transfers before
sampling state, and exercises direct/UI ownership every cycle. Board parameters
continue to come from `BOARD_CONFIG`.

`hardware_test_artifacts/crowpanel7-20260919/endurance/runtime-bench.json` records
**16 accepted 1 MiB SD copy/readback/radio cycles**, totaling **829.848 s**.
Minimum sampled free Python heap after GC was **5,918,592 bytes**; settled heap
was 5,924,144 bytes after the first cycle and 5,924,064 after the last. All accepted
cycle boundaries had progressing LVGL callbacks and nesting zero. No physical
presses were recorded; this unattended result does not certify touch or visuals.

This was **12 uninterrupted accepted cycles plus four after resumption**, not
a continuous 16-cycle pass. The next attempt after cycle 12 passed its file and
radio checks but was rejected by an instantaneous pending-transfer check. That
check had not waited for a normal asynchronous UI flush and did not preserve
the rejected state, so it cannot establish a stalled transfer. The corrected
fixture pauses new submissions, applies the controller's bounded completion
wait, samples state, and resumes scheduling. It now preserves individual
handover/scheduler snapshots before validation. All 99 installed/source/earlier
output hashes passed before resumption. The rejected output remains preserved.

Earlier setup attempts exposed three runner issues: checking health before IDE
network initialization finished, unsupported MicroPython dictionary unpacking,
and an IDE AP retained across raw soft reset. The runner now waits for the
explicit healthy message, uses compatible device syntax, and explicitly stops
native networking for its isolated load fixture. Those failed attempts remain
in the journal and are not counted as load passes.

Normal post-load hard startup and the first two soft-reset checks passed. The
third soft reset reached healthy IDE state (sequence 24, reset cause 5), but
subsequent REPL inspection measured **LVGL nesting 1**. The overall runner
therefore remains **failed**, with only two accepted soft resets; the successful
load cycles do not qualify reset recovery. The inspection includes Ctrl-C, so
this observation alone does not determine whether the counter became stuck
during startup or serial interruption.

The isolated `tools/lvgl_callback_probe.py` then reproduced a specific native
defect without SD or display activity: a deliberately raised and caught timer
callback `ValueError` changed nesting **0 -> 1**, and raw soft reset retained
**1**. Evidence: `endurance/callback/ee54376f-callback-probe.json` and adjacent
logs. No counter was manually cleared. This demonstrates callback exception
leakage and reset retention; it does not prove the trigger of every earlier stall.

That probe's recovery hard boot captured a real **GT911 I2C ETIMEDOUT (116)**
inside `pointer_framework._read` / `gt911._get_coords`, caught by the upstream
task handler. IDE subsequently reported healthy, but the error correctly failed
the startup check. This is a concrete application callback error path into the
native defect. A clean hard restart and separate SD persistence verification
follow; the failed recovery log remains retained. Next firmware work must
address callback exception cleanup and native state on soft reset, then repeat
fault recovery and normal-runtime checks. Merely resetting the counter in Python
would not establish that LVGL's interrupted native operation is safe to resume.
The upstream task handler also stops itself after a callback exception; its
restart policy and touch transport error handling need qualification alongside
the native repair.

The separate `endurance/recovery-integrity.json` reverified **all 103 installed,
source-pattern and accepted load-output hashes**. At entry, normal IDE state
was healthy and nesting zero. Its final restart captured GT911 **ENODEV (19)**
inside the input callback before IDE reported healthy; therefore that script's
overall recovery result also remains failed despite every hash matching.

#### Stopping point and prepared repair

The owner requested a stopping point before firmware build/flash. The experimental
`container_prepare_storage.py` now prepares balanced native callback scopes using
MicroPython's NLR unwind callbacks, preserving exception propagation and return
values. Its interpreter teardown hook clears callback state only after native
resource shutdown. Both pinned generator transformations compile as Python, and
the experimental lock's wrapper hash was updated and validated. The native
regression covers normal/returning callbacks, nested exceptions, an inner caught
exception, and teardown reset. Host tests passed with **two native C tests
skipped** because no host C compiler was available. **No new firmware was built
or flashed, and the repair has not passed native or device validation.**

Next: run the native tests in the pinned container, build/inspect the experimental
image, retain a current flash backup, then test it on the fixture. Run
`lvgl_callback_probe.py --expect-clean` to require balanced nesting and a working
timer after soft reset. Investigate the GT911 transport errors separately; do
not suppress them or convert the existing failed reset/recovery gates to passes.
`endurance/night-stop.json` records the final bounded startup-restoration attempt.
Physical observations remain unanswered and can wait until the next session.
The first night-stop restart failed the clean-startup check; the second reached
`HEALTHY mode=IDE` without captured error markers. The board was left running
that normal startup, with the serial connection closed. This bounded recovery
does not clear the earlier reset/transport failures.

### September 20: native callback repair on hardware

All five native patch tests passed in the pinned ESP-IDF container, including
ASan/UBSan callback-unwind and storage-lifecycle tests. A fresh pinned source
checkout built the candidate in `build/crowpanel7-callback-20260920/`. Image and
UART-only console inspections passed: combined image 2,981,968 bytes, application
2,916,432 bytes, 229,296 bytes application headroom, unchanged partition layout.
Firmware SHA-256:
`3fa4f55f2efc4bdaaf99868b2767531e22d8308a6bd3abe0a286469e5482a0ae`.
The write verified at 115200 baud, preserving NVS/PHY and internal filesystem.
The owner requested no unnecessary backups: the attempted new dump was cancelled,
no new dump retained, and the existing UART-only firmware remains the rollback image.

`hardware_test_artifacts/crowpanel7-20260920/callback/47eafffe-callback-probe.json`
records the corrected native behavior: intentional callback exception was caught,
nesting stayed **0 -> 0**, soft reset retained **0**, and a fresh timer callback
executed with nesting still zero. The isolated cleanup check passed. The initial
normal boot captured another GT911 ETIMEDOUT during Wi-Fi startup, so the overall
probe correctly failed its initial-startup gate; its final restart was clean.
This repairs native counter leakage/reset retention, not touch transport errors
or safe continuation of every interrupted LVGL operation in the same interpreter.

Ten direct native SD lifecycle cycles passed, with 20 sector reads and ten
closed-object guard checks. An earlier invocation failed its internal-root
precondition after mpremote could not enter raw REPL; no SD regression was
established by that setup failure. `sd_bringup.py native-lifecycle --raw-reset`
now performs and captures its own explicit pre-test raw soft reset.

The subsequent normal-runtime bench **passed all eight uninterrupted 1 MiB
copy/readback/radio cycles, five soft resets, and 95 persistence hashes**.
Measured load time was **423.528 s**, minimum sampled free Python heap after GC
**5,918,720 bytes**. LVGL callbacks progressed and nesting stayed zero at accepted
cycle boundaries; direct/UI handover passed each cycle. Normal boot sequences
40 through 44 were healthy soft resets, each advancing once. The final normal
startup was clean. Evidence: `runtime/runtime-bench.json` under the September 20
artifact directory. No physical touch presses were recorded; this unattended run
does not certify touch response or visual stability. The intermittent GT911
transport fault remains open despite this successful bounded regression.

`final-state.json` and `final-startup.log` in that directory record the final
live timer/scheduler check and restoration. Physical cold-boot, alignment and
touch observations are the remaining operator checks for this candidate; the
board remains experimental and is not promoted to a supported target.
The live check passed with **454 timer callbacks**, nesting zero before/after,
an active task handler, and healthy IDE state at sequence 45. The final restart
was clean; the serial port was closed with normal IDE startup running.

### Brightness follow-up

The owner confirmed tapping IDE, stable screen alignment, responsive touch and
navigation into Settings. Physical power removal/reconnection was not explicitly
confirmed. The owner also reported brightness adjustment had no visible effect,
even after saving. Inspection found the board payload omitted `backlight_state`,
so the shared factory selected digital `STATE_HIGH`: every nonzero brightness
became fully on. The payload now selects the existing driver's `STATE_PWM` path;
no shared runtime or firmware change was needed. The updated minified payload was
hash-verified on SD; current inventory is
`hardware_test_artifacts/crowpanel7-20260920/sd-stage-pwm.json`.

The initial hardware duty check incorrectly required one-count precision on the
16-bit API; LEDC quantizes duty at the driver's PWM frequency. Its following
restart also captured the known GT911 ENODEV error. Both failures are retained
in `brightness.json`; the subsequent measured verification is recorded separately
in `brightness-verified.json`. Visual brightness change still needs the owner's
confirmation. Six RGB tests and board-catalog validation pass with PWM selected.
Measured duties for 10%, 50% and 100% were **6528, 32736 and 65535** respectively,
within one percentage point of each request; measured PWM frequency was 38,023 Hz.
The saved setting was **30%**, restored to duty 19648. This confirms the setting
had persisted and PWM duty changes now reach the hardware; perceived brightness
remains an operator observation.

### Session concluded — handoff

The owner confirmed the PWM brightness fix: "Yes, that worked great." Stable
display, responsive touch, Settings navigation and brightness adjustment now
have operator confirmation. A physical power cycle was not explicitly confirmed.
The final PWM verification and normal IDE restart passed; no further device
changes were made after the owner's confirmation.

Next session: investigate intermittent **GT911 ETIMEDOUT (116) / ENODEV (19)**
inside the LVGL input callback. The native nesting leak is repaired and tested,
but an input exception can still stop the upstream task handler. Compare the
standalone probe's declarative expander reset sequence with normal factory
startup, which currently does not perform that sequence. This is an investigation
lead, not an established cause; do not suppress transport errors or assume that
healthy IDE boot state proves input polling works.

Current firmware and build evidence: `build/crowpanel7-callback-20260920/`.
Current SD inventory: `hardware_test_artifacts/crowpanel7-20260920/sd-stage-pwm.json`.
Latest device result: `brightness-verified.json` in that same artifact directory.
Use the existing rollback firmware; the owner explicitly requests no unnecessary
backups. Keep physical observations until the end where practical. The board
remains experimental, with qualification/recovery gates still open.

### September 20: GT911 controlled comparison and startup investigation

COM20 retained the callback-repaired firmware and the installed 10 kHz/PWM
payload. No firmware or installed runtime changes were needed for these checks.
Artifacts are under `hardware_test_artifacts/crowpanel7-20260920/gt911/`.

`active-config/comparison.json` compares hardware I2C host 0 at 10 and 100 kHz,
each with and without the declared PCA9557 reset sequence. Each case completed
two 1 MiB SD copy/readback cycles with RGB refresh and Wi-Fi AP/scan activity.
The active platform's frequency was checked, and GT911 polling was counted with
exceptions recorded and re-raised. All eight cycles returned the expected
1 MiB SHA-256; polling counts were **2,697 / 2,626 / 2,281 / 2,297** respectively,
with **zero transport exceptions** and progressing LVGL callbacks. These bounded
results do not demonstrate that reset or frequency changes fix the intermittent
fault. Touch events are machine observations, not confirmed finger response.

Earlier comparison setup attempts are retained but excluded: the first changed
the internal rescue configuration rather than the active SD configuration; the
second lacked the isolated board import path. The accepted runner configures
the normal platform paths before importing and modifying the active payload.

`baseline-startups/results.json` records 12 alternating hard/soft normal starts.
All startup logs reached healthy IDE without captured transport errors, but the
post-Ctrl-C timer check failed after **two of six soft resets** (sequences 65
and 75): zero callbacks, nesting zero. The other ten checks passed. Because REPL
entry interrupts execution and discards some serial bytes, these stalls cannot
be attributed to GT911 or established as pre-interruption startup failures.

The reusable `tools/touch_startup_probe.py` preserves those discarded bytes in
`serial.log`, captures startup separately from post-interrupt scheduler state,
and records active/running/scheduled handler fields. It journals every cycle,
refuses to overwrite a session, and restores normal startup in `finally`.
Six focused host tests passed, covering evidence retention and rejection of a
dead scheduler despite healthy boot. Use a new session directory per run:

```powershell
python tools/touch_startup_probe.py --port COM20 --session hardware_test_artifacts/crowpanel7-touch-next --cycles 8
```

`captured-startups/touch-startup.json` passed all **eight** subsequent alternating
hard/soft starts, including progressing callbacks, active handler, zero nesting,
and healthy IDE state. The final normal restart also passed and COM20 was closed.
The two earlier post-interrupt stalls did not recur under enhanced capture;
their cause remains unclassified. No new operator observations were requested.
The preserved transcript does capture one `KeyboardInterrupt` inside
`task_handler._task_handler` during REPL entry (sequence 81); that particular
check still passed. This confirms that interruption can reach the scheduler,
but does not prove the trigger of the two earlier stalls. The enhanced transcript
contains no `OSError` or uncaught-exception marker.

The timeout remains unresolved; neither transport errors nor the earlier failed
recovery gates are waived. Physical cold-power-on and touch/display confirmation
remain separate from the unattended results.

### September 20: research and next-test strategy

Added [GT911_INVESTIGATION.md](GT911_INVESTIGATION.md) with primary sources,
the command-mode discrepancy found in the pinned GT911 driver, same-board
upstream timeout reports, and ordered experiments. The next step is passive
transaction/heartbeat capture during real startup; command mode and complete
reset timing then get separate A/B comparisons. Existing post-Ctrl-C checks do
not provide that passive evidence. No hardware tests or device changes were
performed for this research update; all new tests are explicitly planned.
