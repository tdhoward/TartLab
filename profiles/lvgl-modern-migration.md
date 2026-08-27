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

1. For a promoted release, download every asset from the same `@VERSION@`
   release in `tdhoward/TartLab-modern-releases`. For pre-promotion physical
   qualification, use only the artifact created for the exact source tag by
   the protected `attest-modern-candidate.yml` workflow; it is not a release.
2. Verify every asset and its single signed qualification or release bundle
   with the purpose-specific command documented in
   `tests/PHASE6_RELEASE_SECURITY.md` before connecting a device.
3. Confirm the target is the qualified LilyGO T-Display-S3 Pro checkpoint with
   16 MiB flash. Install `esptool` 5.x and `mpremote`, and identify its explicit
   serial port.
4. Choose a durable private workspace outside the TartLab checkout and any
   synchronized folder. Migration copies `/device`, `/state`, legacy settings,
   repositories, logs, `/files/user`, the generated application selection, and
   hardware configuration there. The workspace can contain plaintext Wi-Fi
   credentials and student work.

First perform the read-only release inspection:

```text
python tools/provision_modern.py --release path/to/release --mode migrate
```

Direct migration is supported from stable TartLab `v0.13` or newer, using
either the captured legacy root layout or the canonical `/state` and `/device`
layout, on the exact supported `legacy-mp123` firmware. The tool reads the
installed version and layout from the captured backup and rejects an
out-of-window source before erase. Start the authenticated migration with:

```text
python tools/provision_modern.py --release path/to/release --mode migrate --workspace path/to/private-workspace --port SERIAL_PORT --source-ref refs/tags/@VERSION@ --execute --confirm-erase
```

Use `--mode clean` instead only for clean provisioning. Before erasure, the
tool verifies every signed release asset, captures the protected backup, and
requires the immutable bootloader, partition-table, and factory-application
readback regions to match the exact legacy profile. Mutable NVS/PHY sectors are
excluded. It then erases the chip, writes and verifies `@FIRMWARE_ASSET@` at
`@FLASH_OFFSET@`, constructs the filesystem from authenticated packages,
translates the hardware selector to
`t_display_s3_pro_modern` under `/device`, preserves the legacy root
`/app.py` and `/hdwconfig.py` verbatim for rollback and audit, restores the
remaining protected state, and leaves the target version pending until TartLab
completes a healthy boot.

### Devices older than v0.13

Automatic migration is not approved for a device older than v0.13 or with an
unrecognized layout. Do not install intermediate GitHub releases and do not
override the migration check. An adult administrator must first capture a
private backup with tooling appropriate to that historical version, review and
inventory the settings and user files, then use authenticated `--mode clean`
provisioning. After a healthy modern boot, manually restore only reviewed
settings and user files through the supported IDE or administrator workflow.
Retain the original private backup until the restored device has passed its
health checks. This path deliberately does not copy an unknown historical
filesystem wholesale into the modern runtime.

If USB, power, flashing, or file upload is interrupted, do not discard or edit
the workspace. Reconnect the same board and rerun the same command with
`--resume`. The journal verifies the immutable backup and repeats the erase,
flash, and complete filesystem upload when necessary. After the IDE has booted
healthily and committed the pending version, rerun with `--resume` once more to
record completion. Retain the private workspace until that check succeeds.

## Promotion-gate warning

The checked-in profile is still `promotion-gated-unreleased`. Clean
provisioning, direct legacy migration, interruption, and resume are covered by
the CPython virtual-device gate, but have not yet passed the profile-specific
physical provisioning matrix. Profile-bound modern OTA/recovery, promotion
evidence enforcement, and the v0.13 support-window floor are implemented on the
host matrix, while their required physical observations and final hardware
release tests remain open. Until those gates are
completed and the protected modern-release environment authorizes the release,
this document is an
authenticated candidate instruction and artifact inventory—not authorization
to migrate classroom devices.

The firmware is a combined ESP32 image for offset `@FLASH_OFFSET@`. Firmware
installation remains an adult provisioning operation and is never delegated to
the filesystem-only browser updater.
