# CrowPanel 7-inch bench results — 2026-09-12

**Feasible flash budget; early runtime proof complete.** The board remains
`bringup`. TartLab itself has not been installed or launched, and no SD card
was present. Follow [BRINGUP_PLAN.md](BRINGUP_PLAN.md) for the remaining gates.

## Hardware and firmware

The owner confirmed PCB **V3.0**. ROM probing reports ESP32-S3 revision 0.2,
4 MiB quad flash, and 8 MiB PSRAM. Secure boot and flash encryption are off.
A full original-flash backup and hash are retained in the ignored session
directory; no unit identifiers or original flash bytes are checked in.

A single experimental build of the existing pinned MicroPython 1.27.0 /
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
recipe snapshot is `build/crowpanel7/built-lock.json`. **The current checked-in
lock is the next-build recipe**, with the corrected storage helper. Do not
claim its helper hash describes the earlier binary. Native source patches
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

## Device left for continuation

**Physical SD-card testing is explicitly deferred at the owner's request**
until a card is available. This does not block RGB/touch investigation.

Internal flash holds the experimental firmware, declarative `/hdwconfig.py`,
`/main.py` SD launcher, a persistence marker, and corrected `/external_root.py`.
The filesystem helper intentionally overrides the older frozen module; its
`__file__` was checked on-device. On reset without a card, startup prints a
missing/unreadable-card error and leaves the REPL. The RGB fixture is a manual
bench test and is not installed as the boot application.

The corrected helper still needs to be rebuilt into firmware. Automatic
approval review rejected a read-only Docker check because the account's tool
usage limit was reached; further build-environment work was deferred. The
existing flash experiment and local/serial work were completed independently.

Local detailed evidence is under `hardware_test_artifacts/crowpanel7-20260912/`.
`observations.json` contains operator fields with unobserved values left null.
`build/crowpanel7/` retains the build log, image, original recipe, and vendor
reference downloads. Those directories are ignored and should be retained
locally until the next session.
