# LilyGO T-Display-S3 (non-Pro, non-touch)

Lifecycle: `bringup`. This is the initial buttons-only modern development
target in [BUTTON_NAVIGATION_PROJECT.md](../../BUTTON_NAVIGATION_PROJECT.md).
Initial physical observations are in [BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).
It is not a supported installation target. PCB revision is unverified; the
descriptor's revision value is a research placeholder, not an accepted
production revision policy.

The owner identified the non-Pro, non-touch model and authorized erasing the
bench device without a backup. Initial work started on 2026-09-09. The display
geometry in the descriptor is the intended landscape UI orientation; readable
launcher and settings layouts still require physical validation.

## Hardware reference

[LilyGO's hardware documentation](https://wiki.lilygo.cc/products/t-display-series/t-display-s3/)
and [factory pin configuration](https://github.com/Xinyuan-LilyGO/T-Display-S3/blob/main/examples/factory/pin_config.h)
identify the following wiring. These are vendor facts until the corresponding
physical checks have been recorded.

| Purpose | GPIO / value |
| --- | --- |
| MCU / memory | ESP32-S3R8; 16 MiB quad flash; 8 MiB octal PSRAM |
| Display | ST7789V, native 170 x 320, 8-bit I8080 |
| Display power enable | 15, high enables peripheral power |
| Backlight | 38, active high |
| Reset / chip select / data-command | 5 / 6 / 7 |
| Write / read strobe | 8 / 9; hold read high for writes |
| Data D0 through D7 | 39, 40, 41, 42, 45, 46, 47, 48 |
| Button A (BOOT) / Button B | 0 / 14; expected active low |
| Touch | Absent on this unit; touch tests are inapplicable |

The vendor factory example uses a 16 MHz display pixel clock. Final clock,
address offsets, rotation, color order, inversion, reset timing, and buffering
must be established on the pinned modern driver before a production payload
is selected. Existing legacy PyDevices configuration is reference material
only and must not be packaged into the modern port.

Button A is also the ROM boot strap. Normal navigation must use press/release
gestures after startup. To recover manually, hold BOOT, press and release RST,
then release BOOT. Press RST with BOOT released to boot the installed image.

## Integration work still required

1. Establish stock MicroPython console, memory, filesystem, radio, and reset
   evidence, distinguishing automatic checks from manual power-cycle checks.
2. Prove the pinned modern I80/ST7789 display and both buttons independently.
   Record readable geometry, colors, edges, brightness and press/release data.
3. Define compatible absent-touch and named multiple-button configuration;
   add a declarative `BOARD_CONFIG` and reusable I80/power construction.
   The current shared factory requires SPI and touch, and the current pin
   validator requires a unique purpose for every pin. Do not bypass those
   contracts with a fake pointer or a Pro selector.
4. Implement debounce, focus groups, UI/app ownership, wake-press consumption,
   and smaller-screen launcher/settings layouts under the navigation plan.
5. Demonstrate browser programming, a simple button/display app, reliable IDE
   return, and touch-only app fallback. Then complete the applicable new-board
   provisioning, update/recovery, resource and existing-board regression gates.

Firmware, selector, runtime, and qualification remain null until their actual
artifacts and contracts exist. Bench use of a reference image does not bind
this board to another board's qualification or make it eligible for releases.
Raw logs, temporary scripts, USB mappings, and device identifiers belong in
ignored hardware-test artifacts; checked-in results must be sanitized.
