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

For a legacy device running the exact supported `legacy-mp123` firmware, start
the authenticated migration with:

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
`t_display_s3_pro_modern`, restores protected state, and leaves the target
version pending until TartLab completes a healthy boot.

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
physical provisioning matrix. Modern OTA, on-device recovery, support-window,
and final hardware release tests also remain open. Until those gates are
completed and the protected modern-release environment authorizes the release,
this document is an
authenticated candidate instruction and artifact inventory—not authorization
to migrate classroom devices.

The firmware is a combined ESP32 image for offset `@FLASH_OFFSET@`. Firmware
installation remains an adult provisioning operation and is never delegated to
the filesystem-only browser updater.
