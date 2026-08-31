# TartLab

TartLab is a lightweight, browser-based MicroPython IDE served directly by an
embedded device.

![TartLab logo](images/TartLabLogoHoriz_bluebg.png)

> TartLab is alpha software. Use a recovery-capable test device and retain a
> backup before upgrades or firmware changes.

## Why TartLab exists

TartLab is designed for classrooms where installing USB drivers and desktop
IDEs on every laptop or tablet is impractical. Once a device is provisioned,
students connect over Wi-Fi and use a modern browser to edit, save, and run
MicroPython files stored on the device.

Current features include Python syntax highlighting, a REPL-like console,
Wi-Fi configuration, application selection, and browser-driven filesystem
updates.

## Qualified hardware and profiles

The currently qualified board is the LilyGO T-Display-S3 Pro PCB v1.1. TartLab
is intended to support more Wi-Fi-capable MicroPython boards, but other ESP32,
ESP8266, RP2040, and RP2350 targets are ports requiring their own adapter and
test evidence. The machine-checked [`boards`](boards) catalog distinguishes
bring-up work from candidate and qualified support. The repeatable port layout
and onboarding process are documented in
[`BOARD_SUPPORT.md`](BOARD_SUPPORT.md).

TartLab maintains two profiles:

- `legacy-mp123` supports deployed devices running the exact MicroPython
  1.23.0 octal-SPIRAM image
  `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`.
- `lvgl-modern` uses the pinned MicroPython 1.27.0/LVGL firmware and native
  display transport. Stable `modern-v0.14.8` is published in the isolated
  [modern release repository](https://github.com/tdhoward/TartLab-modern-releases/releases/tag/modern-v0.14.8).

The normal browser updater changes TartLab filesystem packages only; it cannot
change firmware. Modern installation or migration is therefore an adult-admin
task performed with the authenticated provisioning workflow in
[`profiles/lvgl-modern-migration.md`](profiles/lvgl-modern-migration.md).

## Install the legacy profile

1. Flash the exact octal-SPIRAM MicroPython image above. The archived image and
   its checksum are documented in [`firmware/README.md`](firmware/README.md).
2. Before first provisioning, select the board module in `src/hdwconfig.py`.
   The default is the T-Display-S3 Pro. TartLab later migrates the choice to
   protected `/device/hdwconfig.py`.
3. Build a clean distribution:

   ```text
   python -m pip install --require-hashes -r requirements-build.txt
   npm ci --prefix src/ide/www
   python makedist.py --clean
   ```

4. Upload the generated `dist` files with
   [mpsync](https://github.com/tdhoward/mpsync), then restart the device.

Source-development and release-candidate commands are in
[`DEVELOPMENT.md`](DEVELOPMENT.md).

## Use TartLab

### Startup modes

- The legacy profile and published `modern-v0.14.8` normally start the TartLab
  IDE. Holding the application button during reset runs the selected student
  app; on the T-Display-S3 Pro this is GPIO 12.
- Current unreleased modern source replaces that button choice with an LVGL
  touchscreen launcher for IDE, selected-app, and local app-selection routes.
  It is implemented and host-tested but is not yet physically qualified or in
  a stable modern release. See
  [`tests/MODERN_TOUCHSCREEN_QUALIFICATION.md`](tests/MODERN_TOUCHSCREEN_QUALIFICATION.md).

### Connect to the IDE

When the device cannot join a configured Wi-Fi network, it creates an access
point named like `PyAdjectiveAnimalNumber`. Join it and open
`http://192.168.4.1`. When the device joins another network, use
`http://tartlab.local` or the IP address shown on its display. The browser must
be on the same network.

Wi-Fi-capable microcontrollers commonly support only 2.4 GHz networks. Add or
remove saved networks from **Settings → WiFi Settings**.

### Update TartLab

Use **Settings → Check for updates** while the device has Internet access. One
request moves the device directly to the latest compatible stable release;
internal migrations and restarts may occur automatically. Keep the board on
reliable power, wait for completion, and do not start a second update while one
is resuming.

Release feeds are profile-specific:

- legacy devices use `tdhoward/TartLab`; and
- modern devices use `tdhoward/TartLab-modern-releases`.

Never place modern firmware or packages in a legacy release. Deployed legacy
updaters cannot distinguish the profiles and cannot flash firmware.

## Development and testing

The complete hardware-free suite is:

```text
python -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_phase5 tests.test_board_catalog tests.test_modern_profile tests.test_phase6 tests.test_phase6_provisioning tests.test_virtual_device tests.test_platform tests.test_modern_power tests.test_headless_ide -v
```

Host tests cover deterministic builds, update/recovery behavior, virtual device
state, startup modes, headless IDE initialization, and profile policy. They do
not replace physical display, touch, Wi-Fi, reset, memory, migration, or release
qualification. See [`tests/TEST_TIERS.md`](tests/TEST_TIERS.md).

![TartLab in action](images/screenshots/TartLab_ss2.png)

Issues and contributions are welcome in the
[main repository](https://github.com/tdhoward/TartLab).
