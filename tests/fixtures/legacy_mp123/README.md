# Sanitized legacy baseline

This fixture is derived from the ignored `baseline_v013` raw-REPL capture taken
from the Phase 1 test device before OTA migration. Device settings, student
programs, generated access-point identity, and logs are replaced with
deterministic synthetic content. `inventory.json` retains hashes only for
update-managed files; it deliberately does not fingerprint protected device
state. Host-side `snapshot_manifest.json` capture metadata is also excluded.

The fixture records the LilyGO T-Display-S3 Pro v1.1 board revision, the SHA-256
of the official MicroPython 1.23.0 Octal-SPIRAM image, the USB raw-REPL capture
method, and the device's measured `statvfs` capacity/free values. Its
`release_gate_ready: true` value corresponds to the completed physical test
record in `tests/PHASE1_HARDWARE.md`.
