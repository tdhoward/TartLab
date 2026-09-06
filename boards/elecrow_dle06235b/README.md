# Elecrow DLE06235B

Lifecycle: `qualified` — promoted in `modern-v0.15.4`.

The board passed the bench bring-up gates and the Elecrow-specific physical
qualification of signed `modern-v0.15.2`, followed by an authenticated clean
provision, inventory comparison, and owner-confirmed physical smoke of signed
`modern-v0.15.3`. Signed `modern-v0.15.4` retained the same byte-reproducible,
checksummed LVGL/ST77922 firmware and equivalent executable device content,
bound both release boards to validated aggregate evidence, and passed protected
promotion. The current technical results and completed qualification record are
in [`BRINGUP_RESULTS.md`](BRINGUP_RESULTS.md). Shared research and sequencing
for the Elecrow 3.5-inch and 7-inch ESP32-S3 products are in the
[`Elecrow ESP32-S3 bring-up plan`](../elecrow/ESP32_S3_BRINGUP_PLAN.md).

Machine-readable hardware identity and lifecycle state are in
[`board.json`](board.json). Raw logs, downloaded vendor archives, firmware
captures, USB mappings, and device-specific data remain ignored artifacts.
