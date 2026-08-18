# Firmware images

This directory archives the exact flashable firmware images used by TartLab's
runtime profiles. Firmware images are separate from TartLab filesystem release
packages: the on-device updater installs files but does not replace firmware.
Firmware installation is therefore an adult provisioning or migration task.

Each immutable binary has a neighboring `manifest.json` containing its byte
size, SHA-256 digest, target, runtime identity, qualification state, and known
source provenance. Verify every tracked image from the repository root with:

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
  display path.

The intended future modern profile is performance-first and dual-renderer. One
native DMA-capable display transport must serve LVGL UI mode and a mutually
exclusive direct framebuffer/dirty-rectangle game mode. The first reproducible
reference will evaluate `lvgl-micropython/lvgl_micropython` and its ESP32
`lcd_bus`; a PyDevices `lvgl-micropython` + `displayif` image will be benchmarked
on the same board before a production base is selected. Neither repository's
unqualified `main` build is a TartLab release artifact.

Both tracked files are combined ESP32 images intended for offset `0x0`. Erase
the device before changing between firmware layouts. Confirm the target board,
flash size, and manifest digest before flashing.

An explicit JSON `null` means that a custom-build provenance value was not
captured and could not be recovered reliably from the binary. In particular,
the modern runtime reports a dirty MicroPython source tree. Its binary digest
provides an exact artifact identity, but its recorded source commit alone is
not sufficient to reproduce the build.
