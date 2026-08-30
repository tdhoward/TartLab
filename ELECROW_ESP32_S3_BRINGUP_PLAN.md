# Elecrow ESP32-S3 MicroPython, LVGL, and TartLab bring-up plan

Status: research and execution plan. The DLE06235B stock-MicroPython gate was
completed on 2026-08-29; LVGL/ST77922 work remains experimental and is not a
qualification claim.

Research date: 2026-08-29

Targets:

- Elecrow 3.5-inch ESP32-S3 display, SKU `DLE06235B`;
- Elecrow CrowPanel 7-inch ESP32 HMI, order SKU `DIS08070H001`, documented by
  Elecrow as module `DIS08070H` / store SKU `DIS08070H-1`.

## Recommendation

Start with the **3.5-inch DLE06235B**.

It is the better first TartLab target because its ESP32-S3 N16R8 configuration
has 16 MiB flash and 8 MiB octal PSRAM, matching the important memory topology
of TartLab's qualified modern target. Its Type-C connection uses the ESP32-S3's
native USB, and its display resolution is close to the existing 480 x 222
target. The difficult part is well bounded: the ST77922 QSPI display controller
is not in the display list of TartLab's pinned `lvgl_micropython` stack, so it
needs a reviewed driver or native component integration. Bench probing and
Elecrow's active LVGL example show that touch is provided through the ST77922's
integrated TDDI interface at I2C address `0x55`. The FT6336G description and
datasheet in other vendor materials do not match the tested board.

The **7-inch DIS08070H** is attractive for an early LVGL display demonstration:
its parallel RGB panel and GT911 touch controller already have corresponding
generic drivers in `lvgl_micropython`, and Elecrow publishes a MicroPython/LVGL
tutorial. It is not the best first TartLab target, however, because its N4R8
module has only 4 MiB flash. The current TartLab modern image and installed
payload do not fit safely, even before normal filesystem and update overhead.

Recommended order:

1. Preserve both factory images and identify the exact PCB revisions.
2. Bring up stock, generic MicroPython on the 3.5-inch board.
3. Build and qualify an LVGL 9.4 / MicroPython 1.27 image for the 3.5-inch board.
4. Add the 3.5-inch TartLab board adapter and take it through modern-release
   qualification.
5. Bring up stock MicroPython and then a display-only LVGL image on the 7-inch
   board.
6. Make a separate, evidence-based decision about a reduced or SD-assisted
   TartLab architecture for the 7-inch board.

## Hardware comparison

| Property | 3.5-inch `DLE06235B` | 7-inch `DIS08070H` |
| --- | --- | --- |
| MCU/module | ESP32-S3 N16R8, dual-core LX7 up to 240 MHz | ESP32-S3-WROOM-1-N4R8, dual-core LX7 up to 240 MHz |
| Flash | 16 MiB, quad SPI | 4 MiB |
| PSRAM | 8 MiB, octal | 8 MiB, octal |
| Display | 3.5-inch IPS, 320 x 480, 300 cd/m2 typical | 7-inch TN TFT, 800 x 480 |
| Display transport | QSPI: clock plus four data lanes | 16-bit parallel RGB/DPI with PCLK, DE, HSYNC, and VSYNC |
| Display controller | ST77922 | Panel source/gate driver pair EK9716BD3 + EK73002ACGB; software uses a generic RGB panel driver |
| Pixel format | RGB565 is the normal target | RGB565 over the 16-bit RGB bus |
| Touch | Capacitive, ST77922 integrated TDDI over I2C at `0x55` on the tested board; some vendor documents incorrectly identify FT6336G at `0x38` | Capacitive GT911 over I2C; recent V3 boards add PCA9557-controlled touch reset timing |
| USB/programming | Type-C connected to native ESP32-S3 USB | Type-C USB-to-UART0 path; UART0 is GPIO43/44 |
| Storage slot | MicroSD using 4-bit SDIO | MicroSD using SPI |
| Audio | ES8311 codec, onboard MEMS mic, amplified speaker output | I2S amplified speaker output |
| Power | 5 V; LiPo connector and charger | 5 V / 2 A specified; LiPo connector and charger |
| First-order TartLab fit | Good memory fit; new display driver work | Display stack is more familiar, but current TartLab modern flash layout does not fit |

### DLE06235B pin summary

| Function | Pins / notes |
| --- | --- |
| LCD QSPI | CS 10, clock 12, D0 11, D1 13, D2 14, D3 9 |
| LCD reset | Shared with ESP32-S3 `EN`; there is no independent reset pin in the published mapping |
| Backlight | GPIO41, active high/PWM |
| Touch I2C | ST77922 TDDI at `0x55`: SDA 38, SCL 39, reset 48, interrupt 47 |
| Touch/audio/expansion I2C | GPIO38/39 is a shared bus |
| SDIO | clock 5, command 4, data 0-3 on GPIO6/7/2/3 |
| Audio | amp enable 1; I2S MCLK 17, BCLK 18, data out 15, LRCLK 21, data in 16 |
| RGB status LED | GPIO40 |
| Battery sense | GPIO8 ADC |
| UART0 header | RX 43, TX 44 |
| Free expansion | GPIO45 and GPIO46 |
| Buttons | BOOT on GPIO0 and reset on `EN` |

The Elecrow wiki has multiple apparent editorial mistakes: it labels the
microphone description as the I2C interface, one manual paragraph calls the
integrated touch panel 2.8 inches, and some materials identify an FT6336G touch
controller. The tested board reports the ST77922 TDDI firmware and 320 x 480
geometry at I2C `0x55`, matching Elecrow's active example source. The SKU,
product page, mechanical specification, and display measurements consistently
identify the product as 3.5 inches. The bench inventory should record such
discrepancies rather than silently choosing one document.

### DIS08070H pin summary

The published RGB mapping is:

- blue B0-B4: GPIO15, 7, 6, 5, 4;
- green G0-G5: GPIO9, 46, 3, 8, 16, 1;
- red R0-R4: GPIO14, 21, 47, 48, 45;
- DE 41, VSYNC 40, HSYNC 39, PCLK 0;
- backlight GPIO2;
- GT911 I2C SDA 19 and SCL 20;
- MicroSD SPI MOSI 11, MISO 13, clock 12, CS 10;
- general-purpose connector GPIO38;
- I2S LRCLK 18, BCLK 42, data 17, plus the documented I2S control signal;
- UART0 RX 44 and TX 43.

Elecrow's reference timing uses a 15-16 MHz pixel clock, negative/active-low
clock behavior, horizontal porches 40/48/40, and vertical porches 1/31/13.
These are starting values to reproduce exactly before any tuning.

The order SKU does not identify the PCB revision. Recent units are likely V3,
but that must be read from the PCB. V3 adds a PCA9557-mediated reset sequence
for reliable GT911 startup; a V2-only touch configuration is not sufficient
evidence for a V3 unit.

## Why the 7-inch board is not yet a TartLab modern target

The checked-in, qualified modern firmware is 2,978,512 bytes. The exact files
in the current `modern-v0.14.8` installed payload total 1,169,016 bytes. Their
sum is 4,147,528 bytes. A 4 MiB flash is 4,194,304 bytes, leaving only 46,776
bytes before accounting for the bootloader, partition table, NVS, PHY data,
filesystem metadata, free-space reserve, settings, student files, downloaded
update staging, or rollback data.

In addition, the present modern firmware recipe requests a 4 MiB application
partition on a 16 MiB target. That partition alone cannot be reproduced on a
4 MiB device. Therefore:

- the existing TartLab modern image must never be flashed to the 7-inch board;
- a successful Elecrow or custom LVGL demo is not evidence that TartLab fits;
- the 7-inch board may initially be an LVGL/driver fixture without being a
  supported TartLab release target;
- any later TartLab work needs a new flash budget with meaningful headroom and
  a tested OTA/recovery design, not merely a build that barely flashes.

Possible later investigations are a board-specific reduced firmware and
payload, moving selected `/files` content to the MicroSD card, or treating the
board as non-OTA development hardware. The first two change TartLab's storage
and recovery architecture; the third does not meet the stated modern-release
goal. None should be selected before measuring the achievable firmware and
filesystem reductions.

## Phase 0: preserve and inventory the boards

Do this before erasing either factory image.

1. Photograph the front and back of each PCB, including the PCB version,
   module marking, display FPC marking, USB bridge, and touch/expander chips.
2. Record the order SKU and the PCB/module identifiers separately. In
   particular, confirm whether the 7-inch unit is V2.x or V3.0.
3. Download and checksum Elecrow's resource packages, factory firmware, current
   schematics, and examples. Treat vendor binaries as recovery/reference
   artifacts, not as the source for a TartLab production image.
4. Use `esptool` read-only commands to record chip, flash manufacturer/capacity,
   security state, and MAC without publishing unique identifiers.
5. Read the complete factory flash to a private, ignored directory: 16 MiB for
   the DLE06235B and 4 MiB for the DIS08070H after `flash-id` confirms those
   sizes. Compute SHA-256 hashes and perform a second read/compare when
   practical.
6. Verify that the matching factory image can be restored in principle before
   relying on a destructive experiment. Keep the original dumps private; they
   may contain unique calibration or network data.
7. Establish a local fixture inventory with a human board label, SKU, PCB
   revision, flash size, PSRAM size, USB topology, and expected driver set.
   Keep COM ports and unique device identities in ignored local configuration.

Exit criteria:

- both boards are unambiguously identified;
- each board has a hash-verified private factory backup;
- the 7-inch touch-reset revision is known;
- the expected flash and PSRAM sizes agree with physical probes.

## Phase 1: stock MicroPython on the DLE06235B

Use the official `ESP32_GENERIC_S3` **Support for Octal-SPIRAM** combined `.bin`.
As of the research date, the latest stable release is MicroPython 1.29.0. This
phase deliberately uses ordinary MicroPython without LVGL or display drivers.
It proves the base MCU, flash, PSRAM, USB, filesystem, reset, and network path;
the LCD remaining blank is expected.

Suggested workflow, with explicit paths and port substituted:

```text
python -m esptool --chip esp32s3 --port COMx flash-id
python -m esptool --chip esp32s3 --port COMx erase-flash
python -m esptool --chip esp32s3 --port COMx write-flash 0x0 path/to/downloaded-SPIRAM_OCT-v1.29.0.bin
mpremote connect COMx repl
```

Checks:

1. Capture `sys.implementation`, `os.uname()`, `machine.freq()`, `gc.mem_free()`,
   and `os.statvfs('/')` after boot. Confirm that the large PSRAM-backed heap is
   present; do not accept an 8 MiB data-sheet claim without runtime evidence.
2. Write a small file, hard reset, and confirm it persists.
3. Scan for 2.4 GHz Wi-Fi networks and start/stop an access point without using
   or recording real credentials.
4. Toggle GPIO41 to prove backlight control. A lit blank panel is success for
   this phase, not a display-driver test.
5. Scan I2C on GPIO38/39. Record all observed addresses; expect ST77922 touch at
   `0x55` and the ES8311 audio codec at `0x18` on the tested revision. Do not
   make a fixed list a pass condition until the schematic and physical board
   agree. The first bench scan also observed an unidentified responder at
   `0x28`.
6. Exercise the BOOT button as a normal GPIO0 input after boot, then reconfirm
   that the documented bootloader-entry sequence still works.
7. Reset and reconnect repeatedly, including one cold power cycle.

Exit criteria:

- stable native-USB REPL across soft reset, hard reset, and power cycle;
- a persistent baseline filesystem and correct octal PSRAM behavior (record the
  stock image's exposed filesystem capacity without assuming it uses all 16 MiB);
- Wi-Fi and persistent storage work;
- LCD backlight and shared I2C bus are observable;
- factory recovery remains available.

If this fails, stop before LVGL. Diagnose USB enumeration, wrong firmware
variant, flash mode, power, or PSRAM configuration independently.

## Phase 2: pinned LVGL firmware for the DLE06235B

Do not combine a board port with a runtime upgrade. Start from TartLab's pinned
MicroPython 1.27.0 / LVGL 9.4.0 / ESP-IDF 5.5.1 source graph and build a new,
explicitly unqualified DLE06235B artifact. Retain the existing T-Display-S3 Pro
image and lock unchanged.

### Driver work

1. Reproduce Elecrow's QSPI pins and the vendor ST77922 initialization sequence
   at a conservative clock, initially 40 MHz.
2. Determine whether the pinned `lcd_bus.SPIBus` quad mode can express the
   ST77922 command/address format and pixel transfer protocol. The controller
   uses one command byte followed by a 24-bit address phase, so ordinary
   single-lane SPI display assumptions are not enough.
3. If the Python display framework cannot express that protocol cleanly,
   integrate a pinned, licensed native driver. Espressif publishes an
   `esp_lcd_st77922` component supporting SPI/QSPI; evaluate and pin its exact
   version and transitive source rather than importing a moving dependency.
4. Handle the shared `EN` reset safely. The display cannot be independently
   toggled through a normal reset GPIO according to Elecrow's mapping; prefer
   the controller's software-reset/init sequence after MCU boot.
5. Add the smallest reviewed ST77922 TDDI input driver using the vendor register
   protocol at `0x55`. Validate firmware/geometry reads, coordinates,
   press/release behavior, multi-touch reporting, edge coverage, and rotation.
6. Use RGB565 and first prove portrait 320 x 480. Then qualify landscape
   480 x 320, because that is the likely TartLab orientation.
7. Use two small DMA-capable partial buffers rather than allocating full
   internal-memory frames. Record geometry, QSPI clock, buffer sizes and
   capabilities, color order, byte swapping, render time, transfer time, and
   total frame time.

### Standalone acceptance program

The first LVGL image should run a board-only smoke program, not TartLab. It must
show:

- red, green, blue, white, black, and a gradient to detect channel order and
  byte swapping;
- labeled corner and center targets to prove orientation and offsets;
- live touch points and press/release state over the full panel;
- adjustable backlight including off, low, medium, and full;
- a moving region to reveal tearing, blocking transfers, or corruption;
- heap and framebuffer allocation data over serial;
- at least 100 UI/direct-render ownership transitions without a crash;
- cold boots and repeated hard resets.

Exit criteria:

- a reproducible, source-locked combined firmware image;
- stable LVGL 9 display and touch behavior in landscape;
- native USB REPL remains recoverable;
- measured performance is adequate for TartLab's IDE and direct game surface;
- no unreviewed private driver fields are required by the application layer.

## Phase 3: TartLab port for the DLE06235B

1. Add a board-specific platform constructor and a small config selector, for
   example `elecrow_dle06235b_modern`, behind the existing
   `tartlabutils.platform` boundary. Do not place board pins in IDE, launcher,
   recovery, or student application code.
2. Expose the same public TartLab capabilities as the qualified board:
   display, touch/pointer input, Wi-Fi, status rendering, brightness, delay,
   IDE-button behavior, LVGL UI mode, and direct RGB565 dirty rectangles.
3. Map GPIO0 as the IDE button only if the bench tests show reliable normal
   input behavior after boot. Preserve its bootloader role and document the
   interaction. If that is confusing in classroom use, define a supported
   external button on GPIO45/46 instead.
4. Preserve exclusive display ownership. Pending QSPI transfers must be
   drained before switching between LVGL and the direct game surface.
5. Add clean provisioning first. Do not claim migration support from an
   unknown Elecrow factory filesystem.
6. Generalize the modern firmware/release metadata from a single firmware hash
   to an explicit board-to-firmware compatibility matrix. Provisioning must
   identify the board, verify 16 MiB flash, and reject a T-Display or 7-inch
   image before erase.
7. Keep board identity and touch calibration under `/device`; OTA packages may
   update the board adapter but must not overwrite the local selector or
   calibration.
8. Verify the existing browser UI at 480 x 320. Check layout, touch target
   sizes, status overlays, IDE/recovery pages, examples, and every game or
   animation that uses the direct surface.
9. Measure free flash and heap after clean provisioning, first healthy boot,
   IDE startup, a representative program run, OTA staging, and rollback.
   Establish an explicit release margin rather than inheriting the 16 MiB
   assumption implicitly.

Qualification must include the repository's Tier 0-2 checks, a focused physical
smoke, clean adult provisioning, interrupted provisioning/resume, normal OTA,
interrupted OTA, display-independent recovery, protected-state preservation,
feed isolation, and future-update availability. Evidence and promotion status
must be per board and bound to the exact firmware and release candidate.

Exit criteria:

- TartLab boots directly into a usable 480 x 320 LVGL UI;
- IDE, Wi-Fi, examples, touch, brightness, and direct rendering behave smoothly;
- provisioning, OTA, interruption recovery, and rollback pass on the exact
  DLE06235B hardware and firmware;
- the board has a separately promoted qualification record and cannot receive
  an incompatible board image.

## Phase 4: stock MicroPython and LVGL on the DIS08070H

After the DLE06235B path is understood, repeat the factory backup and generic
MicroPython smoke on the 7-inch unit with two differences:

1. Use the verified 4 MiB flash length and the octal-SPIRAM generic image.
2. Treat the Type-C connection as the USB-to-UART0 console. GPIO19/20 are the
   GT911 I2C pins and also the ESP32-S3 native USB pins, so a final LVGL build
   should use UART0 REPL and disable native USB initialization if it interferes
   with touch. A generic-firmware I2C scan failure on these pins is a reason to
   test a UART-only build, not proof of failed touch hardware.

For LVGL, reproduce the Elecrow RGB timing and pin mapping with
`lcd_bus.RGBBus`, the generic `rgb_display` driver, and GT911. Allocate the RGB
framebuffer in PSRAM and keep only suitable bounce/partial buffers in internal
DMA memory. On a V3 board, reproduce the required PCA9557 touch-reset sequence
before constructing the GT911 device.

Elecrow's downloadable `firmware-7.0.bin` and tutorial can be used as a
temporary hardware cross-check: if it works, it helps separate hardware faults
from the new build. It is not the TartLab firmware baseline because its exact
source graph, current runtime identity, reproducibility, update model, and
security provenance are not established here.

The standalone display/touch acceptance program should use the same color,
orientation, touch-edge, motion, reset, and performance checks as the
DLE06235B, adjusted to 800 x 480. Also record RGB scanout pressure on PSRAM and
Wi-Fi behavior while the display is active.

Exit criteria for this phase are deliberately limited to a reproducible
MicroPython/LVGL board image and reliable display/touch operation. They do not
grant TartLab release support.

## Phase 5: 7-inch TartLab feasibility gate

Before writing a TartLab board adapter, produce a proposed 4 MiB partition and
storage budget containing all of the following:

- bootloader, partition table, NVS, PHY and any crash/recovery state;
- the actual board-specific LVGL/MicroPython application image;
- active TartLab core files and required assets;
- settings, `/device`, `/state`, and a useful minimum student-work allowance;
- one complete update's worst-case staging requirement;
- rollback/recovery requirement;
- filesystem metadata and an explicit free-space reserve.

Proceed only if that budget passes worst-case physical update and interruption
tests with an agreed margin. If it does not, keep the board as an LVGL fixture
or explicitly authorize a larger storage architecture project. Do not weaken
TartLab's recovery and OTA guarantees merely to list the board as supported.

## Test-fixture integration

Once either board passes its board-only LVGL smoke:

1. Assign a stable fixture label and capabilities: board/SKU/revision, flash,
   PSRAM, resolution, transport, touch, console type, and power requirement.
2. Parameterize hardware helpers by a local board descriptor instead of adding
   more hard-coded COM ports or T-Display assumptions.
3. Split reusable probes from board assertions. Common probes should cover
   runtime identity, heap, filesystem, Wi-Fi, display ownership, reset, OTA,
   and recovery; board descriptors supply expected geometry, pins, firmware,
   and selectors.
4. Store sanitized result summaries and hashes in source. Keep raw serial logs,
   factory dumps, photos with identifiers, Wi-Fi data, COM mappings, and
   private workspaces ignored.
5. Add power-cycle capability through a controllable powered USB fixture only
   after manual workflows are stable. The 7-inch board must have a supply that
   meets Elecrow's 5 V / 2 A specification.
6. Keep visual color/orientation and physical touch-region checks as explicit
   human gates until a camera/touch actuator can establish them reliably.
7. Bind every promoted hardware result to board revision, firmware SHA-256,
   source candidate checksum, TartLab version, operator/date, and sanitized
   evidence hashes.

Adding a board to the fixture inventory means it can detect regressions; it
does not by itself make that board a supported release target.

## Stop conditions

Stop and diagnose before advancing when any of these occurs:

- the physical flash/PSRAM topology differs from the documented module;
- the factory image was not captured or cannot be associated with one board;
- USB/REPL is unreliable across resets;
- PSRAM is absent or unstable under display load;
- display or touch depends on an unpinned binary-only driver;
- the display stack requires concurrent LVGL and direct-surface ownership;
- the release partition lacks measured OTA, rollback, and student-file margin;
- provisioning cannot reject an image intended for another board;
- recovery depends on the display working.

## Sources

Primary vendor and upstream references used for this plan:

- [DLE06235B product page](https://www.elecrow.com/3-5-esp32-s3-display-320x480-capacitive-ips-touchscreen-with-speaker-mic-bat-interface-supports-ai-voice-chat.html)
- [DLE06235B Elecrow wiki and pin assignment](https://media-cdn.elecrow.com/wiki/3.5_ESP32-S3_Display_with_320x480_Capacitive_IPS_Touch_Panel.html)
- [DLE06235B mechanical/electrical specification](https://www.elecrow.com/download/product/DLE06235B/3.5inch_IPS_ESP32-S3_Specification.pdf)
- [DLE06235B quick-start manual](https://www.elecrow.com/download/product/DLE06235B/3.5inch_ESP32-S3_Quick_Start_Manual.pdf)
- [DIS08070H product page and memory specification](https://www.elecrow.com/esp32-display-7-inch-hmi-display-rgb-tft-lcd-touch-screen-support-lvgl.html)
- [DIS08070H Elecrow wiki, pins, timing, and V3 touch note](https://media-cdn.elecrow.com/wiki/esp32-display-702727-intelligent-touch-screen-wi-fi26ble-800480-hmi-display.html)
- [Elecrow DIS08070H hardware/example repository](https://github.com/Elecrow-RD/CrowPanel-7.0-HMI-ESP32-Display-800x480)
- [Elecrow 7-inch MicroPython/LVGL tutorial](https://media-cdn.elecrow.com/wiki/7.0-inch_ESP32_Display_MicroPython_Tutorial.html)
- [Official MicroPython ESP32-S3 downloads and octal-SPIRAM guidance](https://micropython.org/download/ESP32_GENERIC_S3/)
- [MicroPython ESP32 port build guidance](https://github.com/micropython/micropython/blob/master/ports/esp32/README.md)
- [`lvgl_micropython` supported drivers and build options](https://github.com/lvgl-micropython/lvgl_micropython)
- [Espressif `esp_lcd_st77922` component](https://components.espressif.com/components/espressif/esp_lcd_st77922)

TartLab-local facts and constraints are taken from `PROJECT_NOTES.md`,
`profiles/lvgl-modern.json`, `firmware/lvgl-modern/reference.lock.json`,
`src/lib/tartlabutils/modern.py`, `tests/TEST_TIERS.md`, and the built
`modern-v0.14.8` payload inventory in the local workspace.
