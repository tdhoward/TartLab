# Firmware images

This directory archives the exact flashable firmware images used by TartLab's
runtime profiles. Firmware images are separate from TartLab filesystem release
packages: the on-device updater installs files but does not replace firmware.
Firmware installation is therefore an adult provisioning or migration task.
Legacy device releases remain in `tdhoward/TartLab`; any published modern
firmware and its compatible filesystem releases belong in the separate
`tdhoward/TartLab-modern-releases` feed. Do not attach a modern image to a legacy
GitHub Release, because deployed updaters cannot distinguish the profiles and
count every attached asset in their filesystem free-space check.

Profile artifacts have a neighboring `manifest.json` containing their byte
size, SHA-256 digest, target, runtime identity, qualification state, and known
source provenance. The reproducible Phase 5 reference uses its neighboring
`provenance.json` plus `reference.lock.json`. Verify every tracked image from
the repository root with:

```text
python tools/check_firmware_artifacts.py
```

## Profiles

- `legacy-mp123` contains the official MicroPython 1.23.0 generic ESP32-S3
  octal-SPIRAM image. Its digest matches the physically qualified TartLab
  legacy baseline in `profiles/legacy-mp123.json`.
- `lvgl-modern/1.27.0` contains a locally built MicroPython 1.27.0 image with
  LVGL built in. It is an experimental artifact and has not passed TartLab's
  modern-firmware hardware qualification gate. Its presence proves only that
  LVGL was built into that binary; the recorded provenance does not show an
  exact reproducible build or prove that TartLab used the native `lcd_bus`
  display path. It remains historical research input and is not the firmware
  identity accepted by the modern release manifest.

The selected modern profile is performance-first and dual-renderer. One
native DMA-capable display transport must serve LVGL UI mode and a mutually
exclusive direct framebuffer/dirty-rectangle game mode. The reproducible
`lvgl-micropython/lvgl_micropython` reference and the PyDevices comparison were
benchmarked on the same board before selecting the reference stack. Neither
repository's unqualified `main` build is a TartLab release artifact.

The Phase 5 reference's complete ESP32 source graph, target arguments, local
CST226 adapter, and Linux/amd64 ESP-IDF container image are pinned in
`lvgl-modern/reference.lock.json`. Validate the lock, provenance, and archived
binary with:

```text
python tools/modern_firmware.py check
```

Two independent clean checkouts produced byte-identical copies of the current
2,978,512-byte hardware checkpoint, with SHA-256
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
It freezes ST7796 and CST226 drivers, uses the native `lcd_bus` build, and
exposes the REPL through the board's native USB Serial/JTAG interface. It is a
`research-only-reproducible-hardware-qualified` reference. TartLab's checked-in
application payload supplies the Phase 5 direct RGB565 surface and exclusive
LVGL/game ownership adapter. The exact checkpoint passed the Phase 5 item 4
physical display, touch, DMA ownership, reset, network/IDE,
application-switch, and error-recovery observations in
`tests/PHASE5_HARDWARE.md`, followed by the Phase 5 legacy/modern and
alternative-stack comparisons in `tests/PHASE5_BENCHMARKS.md` and
`tests/PHASE5_PYDEVICES.md`. That evidence applies only to this board,
checkpoint, and hash-bound adapter. The comparison selected this reference as
the exact firmware compatibility identity for the promotion-gated modern
builder. Adult provisioning, migration, support-window, OTA/recovery, and final
release gates remain open. This evidence is not recovered provenance for the
archived 2025 binary.

All tracked files are combined ESP32 images intended for offset `0x0`. Erase
the device before changing between firmware layouts. Confirm the target board,
flash size, and manifest digest before flashing.

An explicit JSON `null` means that a custom-build provenance value was not
captured and could not be recovered reliably from the binary. In particular,
the modern runtime reports a dirty MicroPython source tree. Its binary digest
provides an exact artifact identity, but its recorded source commit alone is
not sufficient to reproduce the build.
