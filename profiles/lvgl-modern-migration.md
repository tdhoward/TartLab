# TartLab managed-modern provisioning and migration

Release: `@VERSION@`

Runtime profile: `lvgl-modern`

Firmware asset: `@FIRMWARE_ASSET@`

Firmware SHA-256: `@FIRMWARE_SHA256@`

Flash offset: `@FLASH_OFFSET@`

This release is for adult administrators. The normal TartLab browser updater
cannot replace firmware and must not be used to convert a `legacy-mp123`
device. Do not attach these assets to, or discover them through, the legacy
`tdhoward/TartLab` release feed.

## Required safety checks

1. Download every asset from the same `@VERSION@` release in
   `tdhoward/TartLab-modern-releases`.
2. Verify every asset and the signed bundle with the command documented in
   `tests/PHASE6_RELEASE_SECURITY.md` before connecting a device.
3. Confirm the target is the qualified LilyGO T-Display-S3 Pro checkpoint with
   16 MiB flash, then preserve its `/device`, `/state`, `/settings.json`,
   `/repos.json`, `/logs`, `/files/user`, generated application selection, and
   hardware configuration.
4. Validate the downloaded release locally with
   `tools/check_modern_release.py`, the intended `lvgl-modern` profile, and the
   authenticated release firmware digest. The future migration tool must also
   observe the pre-mutation device identity and reject any unsupported source.
   Any mismatch is a hard stop before erase, flash, extraction, or file
   mutation.

## Promotion-gate warning

The checked-in profile is still `promotion-gated-unreleased`. Clean
provisioning, direct migration from the supported legacy window, interruption,
rollback/recovery, modern OTA, and final hardware release tests belong to the
remaining Phase 6 gates. Until those gates are completed and the protected
modern-release environment authorizes the release, this document is an
authenticated candidate instruction and artifact inventory—not authorization
to migrate classroom devices.

The firmware is a combined ESP32 image for offset `@FLASH_OFFSET@`. Firmware
installation remains an adult provisioning operation. The exact flashing,
filesystem restoration, health-check, and rollback procedure will be exercised
and finalized by Phase 6 item 6; do not infer one from the filesystem-only OTA
flow.
