# PyDevices candidate patches

This directory contains strict JSON patch manifests for the generated legacy
payload. Every operation names an allowlisted destination, pins the complete
preimage and result SHA-256, and requires exact replacement counts. The vendor
tool rejects fuzzy matches, stale hashes, unselected paths, and unexpected
dependencies.

The approved patches cover MicroPython 1.23 parser compatibility, the selected
board/display constructor, native framebuffer selection, ST7796 fill
compatibility and bounded-buffer performance, and ESP32 SPI configuration.
TartLab-owned compatibility adapters are separate hash-pinned sources under
`vendor/compatibility/pydevices-candidate`; they are not disguised upstream
patches.
