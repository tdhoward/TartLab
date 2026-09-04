# Phase 6 managed-modern provisioning qualification

`tools/provision_modern.py` is the approved repository workflow for clean
provisioning or direct adult migration to `lvgl-modern`. It is read-only by
default. Mutation requires `--execute`, `--confirm-erase`, an explicit port,
an exact signed source tag, and a durable private workspace outside the
checkout.

## Transaction contract

Before erase, the tool:

1. validates the complete release, checksums, ownership, firmware, compatibility,
   locks, provenance, support window, and migration guide;
2. verifies the qualification or release GitHub Artifact Attestation;
3. captures protected state into a private content-addressed backup;
4. validates the T-Display-S3 Pro selector and installed release/layout; and
5. verifies immutable regions of the exact qualified legacy firmware while
   excluding mutable NVS/PHY sectors.

Direct migration supports stable v0.13 or newer and a recognized legacy root or
canonical layout. Older, prerelease, wrong-board, wrong-firmware, or unknown
layouts fail before erase.

The transaction erases, writes, and verifies the combined image, reconstructs
authenticated filesystem packages, translates the active selector to
`t_display_s3_pro_modern`, restores protected state, and leaves the target
version pending until a healthy boot. Inert boot placeholders and late boot-file
activation keep incomplete filesystems from starting. A content-addressed
journal contains no captured values and supports `--resume` after power, USB,
flash, verification, or upload interruption.

## Qualified release

The final physical gate used signed `modern-v0.14.8`:

- tag commit: `49d5b82c795297fa0c6f12ed683af465502779a1`;
- candidate `checksums.json` SHA-256:
  `dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e`;
- firmware SHA-256:
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`;
- board: T-Display-S3 Pro PCB v1.1, 16 MiB flash, 8 MiB octal PSRAM.

This records a lab qualification, not a field deployment. No installed modern
population depends on this release, so future alpha qualification may proceed
directly with an explicit selection-aware multi-board candidate.

## Physical results

The combined 2026-08-27–28 sessions passed:

- direct migration from the exact v0.13 floor with a backup before erase,
  immutable legacy firmware readback, selector translation, protected-state
  preservation, browser/API checks, and exactly-once healthy commit;
- a truly clean erase/write/verify/install, including authenticated
  `/defaults/user/hello.py` seeding only into a new user area;
- tablet IDE create/edit/save/reopen/run/delete, upright colors, five-point
  touch, GPIO 12 APP boot, recovery page/AP, forced IDE return, and normal reset;
- interruption during backup and legacy readback;
- active interruption at erase, firmware write and verification, inert
  placeholders, every top-level upload, both final boot-file activations, and
  pending-health boot; and
- resume from the same private journal after every loss, with exact immutable
  prepared-file comparison at completion.

Qualification found and fixed several transaction boundaries: repeated
`mpremote` resets during capture, native-USB settle time, ROM-only chunked
legacy reads, reuse of matching firmware only during explicit resume, clean
starter-file seeding, and recovery after final boot-file activation failure.

The host failure-injection suite also proves fail-closed behavior for wrong
firmware/board, changed backup, corrupt packages, failed verification, and
incomplete upload. None advances the journal to success.

The physical provisioning gate is complete for `modern-v0.14.8`. Detailed
sanitized promotion evidence is
`tests/evidence/modern-v0.14.8-qualification.json`; private journals, backups,
credentials, and student data remain outside Git. OTA/recovery containment and
publication are summarized in `PHASE6_MODERN_QUALIFICATION.md`.
