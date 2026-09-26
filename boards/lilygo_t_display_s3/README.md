# LilyGO T-Display-S3 (non-Pro, non-touch)

Lifecycle: `qualified` for PCB revision `1.2` in the promoted
[`modern-v0.16.1`](https://github.com/tdhoward/TartLab-modern-releases/releases/tag/modern-v0.16.1)
release. The [candidate-bound qualification record](../../tests/evidence/modern-v0.16.1-qualification.json)
and [physical transcript](../../tests/evidence/modern-v0.16.1-nonpro-physical-transcript.txt)
cover the buttons-only modern target. Initial observations remain in
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md) and development history in
[DEVELOPMENT_RESULTS.md](DEVELOPMENT_RESULTS.md). The owner read PCB marking
`v1.2` on the attached unit on 2026-09-23; the descriptor accepts revision
`1.2`. This is one observed unit, not a broader revision policy.

The owner identified the non-Pro, non-touch model and authorized erasing the
bench device without a backup. Initial work started on 2026-09-09. The display
geometry in the descriptor is the tested landscape UI orientation. Subsequent
owner checks confirmed button navigation, brightness/settings and dim/wake;
the development results distinguish those observations from the remaining
physical and release gates.

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

## Development path

The declarative [runtime payload](runtime/t_display_s3_modern.py) now selects
shared I80 construction, the packaged ST7789 driver, explicit absent touch,
and named buttons. A advances focus and B activates it, both on release.
The modern help menu includes a physical-button counter example; copy it to
user files before choosing it as the startup app. Its B action restarts to
the launcher, whose timeout defaults to the IDE.

Build a board-selected development filesystem explicitly with:

```text
python makedist.py --output build/t-display-s3-dev --board lilygo_t_display_s3
```

This local build does not create an authenticated release or provision a
device. Use the signed modern-v0.16.1 release and the authenticated modern
provisioner for supported installation. Qualification covered firmware,
provisioning interruptions, OTA, recovery, power cycles, held-button/reset
behavior, display and browser use, and fresh regressions on the existing
touch boards. Battery operation remains untested.
Raw logs, temporary scripts, USB mappings, and device identifiers belong in
ignored hardware-test artifacts; checked-in results must be sanitized.
