# Elecrow DLE06235B

Lifecycle: `candidate` — exact-board physical gates passed; protected
multi-board promotion remains pending.

The board has passed the bench bring-up gates and the Elecrow-specific physical
qualification of signed `modern-v0.15.2`, followed by an authenticated clean
provision, inventory comparison, and owner-confirmed physical smoke of signed
`modern-v0.15.3`. The two candidates use the same byte-reproducible,
checksummed LVGL/ST77922 firmware and equivalent executable device content.
It remains a candidate until the same multi-board release has complete
aggregate evidence and is promoted through the protected workflow. The
current technical results and ordered work are in
[`BRINGUP_RESULTS.md`](BRINGUP_RESULTS.md). Shared research and sequencing for
the Elecrow 3.5-inch and 7-inch ESP32-S3 products are in the
[`Elecrow ESP32-S3 bring-up plan`](../elecrow/ESP32_S3_BRINGUP_PLAN.md).

Machine-readable hardware identity and lifecycle state are in
[`board.json`](board.json). Raw logs, downloaded vendor archives, firmware
captures, USB mappings, and device-specific data remain ignored artifacts.
