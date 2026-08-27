# Phase 6 managed-modern provisioning gate

## Host transaction gate

`tools/provision_modern.py` is the only approved path in this repository for
clean provisioning or direct adult-admin migration to the promotion-gated
`lvgl-modern` profile. Its default action is read-only. Physical mutation
requires all of `--execute`, `--confirm-erase`, an explicit serial port, a
signed source-tag reference, and a private durable workspace outside the Git
checkout.

Before erasure, migration performs these fail-closed checks:

1. Validate the complete modern release, compatibility declaration, checksums,
   firmware, provenance, package ownership, and rendered instructions.
2. Verify every release asset against its GitHub Artifact Attestation bundle.
3. Capture protected canonical and legacy state into a sensitive host backup.
4. Validate the legacy T-Display-S3 Pro selector and release state.
5. Read back the flash span occupied by the pinned 1.23.0 image and verify the
   hash-locked immutable bootloader/partition-table and factory-application
   regions. The mutable NVS/PHY range at `0x9000` through `0xFFFF` is excluded;
   the checked-in source artifact itself retains whole-image SHA-256
   `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
6. Enforce the authenticated support window against the captured backup:
   stable v0.13 or newer and a declared legacy root or canonical layout.
   Older, prerelease, or unknown layouts stop before erase.

The host then erases and writes the combined modern image at offset `0x0`, uses
`esptool verify-flash`, reconstructs all authenticated filesystem packages,
translates the legacy board selector to `t_display_s3_pro_modern`, restores
settings, repositories, logs, selected application, hardware state, and user
files, and records both the modern feed and exact firmware identity with the
target version pending health. The existing TartLab health gate commits the
version exactly once. A content-addressed host journal
contains no captured values and makes backup, flash, or upload interruption
resumable with `--resume`.

`tests.test_phase6_provisioning` currently proves on the CPython directory
transport:

- clean provisioning creates a modern selector, isolated release state,
  recovery payload, and pending-health transaction;
- direct migration from the sanitized v0.13 layout preserves settings, logs,
  user programs, selected application, and installed-version history;
- the legacy selector is translated instead of being copied into incompatible
  firmware;
- the journal does not contain the fixture Wi-Fi password;
- an active legacy update and a changed backup both fail before erase/resume;
- USB loss after erase and during upload retains the immutable backup, and one
  resume re-erases and installs a complete recoverable image;
- inert boot/main placeholders prevent incomplete filesystems from starting,
  and the real boot files are activated only after recovery and state exist;
- unsupported hardware stops before erase;
- v0.12, prerelease, and unrecognized source layouts stop before erase while
  v0.13 root-v1 and newer canonical layouts pass the host policy; and
- the physical transport accepts an exact legacy firmware readback and rejects
  a different image.

This host gate does not qualify a physical migration or authorize classroom
deployment.

The approved path below the v0.13 floor is not automatic migration. An adult
captures a private version-appropriate backup, performs authenticated clean
provisioning, and selectively restores reviewed settings and user files after
a healthy boot. Intermediate releases and wholesale historical filesystem
copies are not part of the supported process.

## Remaining physical gate

On a sanitized LilyGO T-Display-S3 Pro PCB v1.1 running the exact legacy image,
record the port, chip revision, flash/PSRAM size, pre/post protected-state
inventories, release and firmware hashes, journal hash, serial output, and
operator/date. Do not archive credentials or student work.

The physical item 6 gate passes only after all of the following are observed:

1. Clean provisioning reaches the IDE and APP paths with display, touch, AP,
   browser edit/save/run, selected application, and recovery available.
2. Direct migration preserves every protected category and translates the
   hardware selector; the old version remains committed until a healthy IDE
   boot commits the modern version exactly once.
3. Power or USB loss during backup, legacy flash readback, erase/write,
   verification, each top-level filesystem upload, and the pending-health boot
   can be resumed from the same private workspace.
4. A wrong legacy firmware, wrong board selector, changed backup, bad modern
   firmware, corrupt package, failed verification, and incomplete upload all
   fail closed without claiming success.
5. After every post-erase failure, USB reflash/resume remains available; after
   the filesystem is complete, the on-device recovery route also boots.

The profile-aware modern OTA/recovery client and promotion evidence validator
are implemented as Phase 6 item 7 host gates. Their physical OTA, recovery,
release-feed, and support-window observations remain required even after this
physical provisioning matrix passes; see `tests/PHASE6_MODERN_QUALIFICATION.md`.
