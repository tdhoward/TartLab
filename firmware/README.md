# Firmware images

This directory archives the exact flashable images used by TartLab profiles.
Firmware is separate from TartLab filesystem packages: browser OTA never
flashes it. Firmware installation is an adult provisioning task.

Verify every tracked image, size, and SHA-256 from the repository root:

```text
python tools/check_firmware_artifacts.py
```

All tracked artifacts are combined ESP32 images for offset `0x0`. Confirm the
board and flash size, erase before changing layouts, and retain a private backup
and known-good recovery image.

## Qualified profiles

- `legacy-mp123` is the official MicroPython 1.23.0 generic ESP32-S3
  octal-SPIRAM image. Its identity is pinned in
  `profiles/legacy-mp123.json` and remains the deployed compatibility baseline.
- `lvgl-modern/reference` is the reproducible MicroPython 1.27.0/LVGL 9.4.0
  image selected for the T-Display-S3 Pro. Two clean builds produced the same
  2,978,512-byte image with SHA-256
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
  Its complete source graph, local CST226 input, target arguments, and
  digest-pinned ESP-IDF container are recorded by
  `lvgl-modern/reference.lock.json` and the neighboring provenance file.

Validate the modern lock and archived image with:

```text
python tools/modern_firmware.py check
```

The modern image uses native USB Serial/JTAG, ST7796/CST226 support, and one
DMA-capable transport shared exclusively by LVGL UI mode and TartLab's direct
RGB565 game surface. Its lifecycle, benchmark, provisioning, OTA/recovery, and
promotion evidence is summarized in the Phase 5 and Phase 6 documents under
`tests/`. It is the firmware identity published with stable
`modern-v0.14.8`.

## Historical and comparison artifacts

- `lvgl-modern/1.27.0` is an older experimental build with incomplete
  provenance. Its binary hash identifies the artifact, but it is not accepted
  by the modern release manifest.
- `lvgl-modern/pydevices-reference` is the reproducible PyDevices/displayif
  comparison. It was slower and blocking at the pinned checkpoint and is not
  the selected production stack.

Neighboring manifests are authoritative for artifact identity and provenance.
JSON `null` means a historical build value was not captured and must not be
invented.

Legacy releases belong only in `tdhoward/TartLab`; modern firmware and
filesystem releases belong only in `tdhoward/TartLab-modern-releases`. Never
attach a modern image to the legacy feed.
