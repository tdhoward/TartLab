# Phase 6 managed-modern provisioning gate

## Host transaction gate

`tools/provision_modern.py` is the only approved path in this repository for
clean provisioning or direct adult-admin migration to the promotion-gated
`lvgl-modern` profile. Its default action is read-only. Physical mutation
requires all of `--execute`, `--confirm-erase`, an explicit serial port, a
signed source-tag reference, and a private durable workspace outside the Git
checkout.

Physical qualification uses the unpublished, tag-bound artifact produced when
an exact `modern-v*` source tag runs
`.github/workflows/attest-modern-candidate.yml`. That protected workflow
rebuilds the candidate twice, attests its TAR/JSON/BIN/MD subjects, and uploads
`qualification-attestation.sigstore.json` with the candidate without creating
a GitHub Release. `tools/provision_modern.py` accepts that qualification
workflow as the signer for pre-promotion device testing, or the separate
promotion signer for an eventual published release; it rejects a missing or
ambiguous bundle. Final promotion remains blocked on the completed physical
gates.

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
the legacy root `/app.py` and `/hdwconfig.py` verbatim, restores settings,
repositories, logs, selected application, hardware state, and user files, and
records both the modern feed and exact firmware identity with the target
version pending health. The existing TartLab health gate commits the version
exactly once. A content-addressed host journal
contains no captured values and makes backup, flash, or upload interruption
resumable with `--resume`.

`tests.test_phase6_provisioning` currently proves on the CPython directory
transport:

- clean provisioning creates a modern selector, isolated release state,
  recovery payload, and pending-health transaction;
- direct migration from the sanitized v0.13 layout preserves settings, logs,
  user programs, selected application, legacy root files, and
  installed-version history;
- the legacy selector is translated instead of being copied into incompatible
  firmware;
- the journal does not contain the fixture Wi-Fi password;
- an active legacy update and a changed backup both fail before erase/resume;
- USB loss after erase and during upload retains the immutable backup; resume
  reuses an already verified firmware image instead of erasing it again, then
  installs a complete recoverable filesystem;
- inert boot/main placeholders prevent incomplete filesystems from starting,
  and the real boot files are activated only after recovery and state exist;
- unsupported hardware stops before erase;
- v0.12, prerelease, and unrecognized source layouts stop before erase while
  v0.13 root-v1 and newer canonical layouts pass the host policy; and
- the physical transport accepts an exact legacy firmware readback and rejects
  a different image.

This host gate does not qualify a physical migration or authorize classroom
deployment.

## Physical direct-migration session: 2026-08-27

Candidate `modern-v0.14.6` was migrated on the qualification LilyGO
T-Display-S3 Pro from the exact MicroPython 1.23.0 legacy image. The legacy
application enumerated on COM6 and the ROM/modern runtime on COM3; the ESP32-S3
reported chip revision 0.2, 16 MiB flash, and 8 MiB octal PSRAM. The signed
candidate's `checksums.json` SHA-256 was
`f0388af976033818665352f91c5af932c9c27d2e84cf043bd3518bc4f1f25878`.

The protected capture completed in one raw-REPL session without a soft reset.
The private journal recorded 22 inventoried files, approved source profile
`legacy-mp123`, canonical-v1 layout, installed v0.13, and backup identifier
`sha256:e30827b98825bcb5413e36b920848ae2e79af32dfe3ca453d4c950294f0971ee`
before ROM entry. Resume on COM3 verified the pinned immutable legacy regions,
flashed and verified the modern firmware, restored the filesystem, committed
the version after health, and reached journal stage `complete`.

Physical interruption exposed three host-transport gaps which are now covered
by regression tests: capture must not perform repeated mpremote soft resets;
resume must reuse an already matching firmware and explicitly exit the ROM
loader with a watchdog reset; and the health check must allow the native USB
endpoint to become writable before reading exact repository state. The final
device reported MicroPython 1.27.0, runtime profile `lvgl-modern`, repository
`tdhoward/TartLab-modern-releases`, installed version `modern-v0.14.6`, no
pending update, the modern hardware selector, selected application
`selected_app.py`, and 213 filesystem files. A passive final boot reached
`HEALTHY mode=IDE` after the expected synthetic-network fallback.

The post-migration protected digests for `/app.py`, `/hdwconfig.py`, and
`/files/user` exactly matched their pre-migration values. `/device` changed as
required for the modern selector. The selected-application JSON retained the
same semantic value but was canonically reformatted. Legacy logs were present
immediately after restoration; repeated diagnostic boots subsequently advanced
the active five-entry rolling log window, while the original logs remain in
the retained private backup.

The session resumed after migration with the ignored root `settings.json` as
the serial helper's credential source. The credential values were not retained
as evidence. The modern device joined the local network and Chrome loaded the
TartLab IDE from the device with the loading overlay dismissed and no file-panel
error. An automated browser interaction created `phase6_browser_test.py` in a
CodeMirror tab, entered a synthetic print statement, clicked Save, read back the
exact saved content, clicked Run, and observed `PHASE6_BROWSER_RUN_OK` in the
expanded IDE console. `/api/space`, `/api/versions`, and `/api/files/user` all
returned HTTP 200; the repository state reported `modern-v0.14.6` and
`lvgl-modern`. The temporary device file was deleted and subsequently returned
HTTP 404. The sanitized browser screenshot SHA-256 is
`188a19caf5e696763f6f9036fbee329786258226f65509dde4ce7931d6f81f1c`.

The collision-safe Phase 5 switch helper then staged its hash-verified direct
RGB565 test app while retaining `selected_app.py` in the cleanup marker.
Holding the physical upper-right GPIO 12 button during reset displayed the
expected magenta, cyan, yellow, green, and blue vertical bands. Cleanup restored
`selected_app.py` and removed only the temporary app and marker. An ordinary
unpressed reset returned the IDE page and version API with HTTP 200 responses.

Finally, the live IDE pseudo-REPL set the next startup mode to `RECOVERY` and
reset the device without using serial. The station IDE went offline and the
open `TartLab-Recovery` SSID was physically observed from a separate Wi-Fi
client. Because recovery mode is one-shot, an ordinary unpressed reset returned
the station IDE page and version API with HTTP 200 responses. This confirms the
display-independent recovery boot, AP advertisement, and safe normal-boot
return path; the recovery page's browser controls and corrective-update path
were not exercised in this migration session. The subsequent candidate-bound
modern OTA session recorded in `PHASE6_MODERN_QUALIFICATION.md` physically
exercised the recovery page, redacted status endpoint, corrective-update
button, offline staged resume, healthy IDE return, and protected-state
preservation.

This session qualifies the direct migration, normal health-commit path, and
post-migration browser edit/save/run, APP-selection, and recovery boot/AP paths
on the device. Together with the subsequent modern qualification session, the
normal physical OTA and recovery-browser corrective paths are also observed.
The live release-feed isolation and candidate-bound v0.13 support-floor
observations recorded in `PHASE6_MODERN_QUALIFICATION.md` now also pass. The
still-open clean-provisioning, destructive interruption/containment, and
exhaustive power-loss matrix observations are not claimed.

## Candidate-bound v0.13 floor migration: 2026-08-27--28

The exact sanitized `legacy-root-v1` v0.13 fixture was staged on the pinned
MicroPython 1.23.0 image and migrated to the authenticated
`modern-v0.14.7` candidate. The transaction captured an 11-file private backup
with identifier
`sha256:761202b737d5ee4a62915d3db63cf5cf483fef0a285bb3eacf877dcd614b4cff`
before erase, verified the locked legacy runtime regions through bounded
ROM-only reads, installed 210 prepared files, and reached journal stage
`complete` only after an exact version health check.

The physical session exposed and fixed two native-USB transport boundaries:
the flasher stub dropped reproducibly at absolute address `0x83000`, so legacy
identity reads now remain in the ROM loader and are SHA-256 hashed in 256 KiB
chunks; and Windows published COM3 before the modern endpoint was writable, so
filesystem upload waits the same qualified three seconds as the health check.
Both behaviors have targeted regression coverage, and resume reused the
already verified firmware rather than erasing it again.

Post-migration comparison found exact legacy app, root hardware selector,
settings, and user-file bytes; the active selector and selected-app translation
were correct; the repository reported `modern-v0.14.7` and `lvgl-modern`; and
the pending update marker was absent. Headless Chrome hid the loading overlay
without a file-panel error, and the versions, space, and user-files APIs all
returned valid state. Full candidate hashes, journal/snapshot identifiers, and
the secret-handling boundary are recorded in
`PHASE6_MODERN_QUALIFICATION.md`. This closes the candidate-bound physical
support-window floor observation, not the remaining clean or interruption
matrix.

The approved path below the v0.13 floor is not automatic migration. An adult
captures a private version-appropriate backup, performs authenticated clean
provisioning, and selectively restores reviewed settings and user files after
a healthy boot. Intermediate releases and wholesale historical filesystem
copies are not part of the supported process.

## Remaining physical gate

The candidate-bound direct-migration floor case now has the required device,
runtime, port, protected-state, release/firmware, journal, and operator/date
record without credentials or student work. The rest of the item 6 physical
matrix remains open.

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
are implemented as Phase 6 item 7 host gates. Their normal physical OTA,
recovery-browser, release-feed, and support-window observations now pass for
this candidate; destructive containment and the complete provisioning matrix
remain required. See `tests/PHASE6_MODERN_QUALIFICATION.md`.
