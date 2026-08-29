# Phase 6 modern OTA, recovery, and promotion qualification

The `lvgl-modern` profile has a separate on-device release contract. Both the
normal updater and the display-independent recovery updater require all three
of these values in the TartLab repository record:

- `runtime_profile`: `lvgl-modern`;
- `repo`: `tdhoward/TartLab-modern-releases`;
- `manifest`: `modern-manifest.json`;
- `firmware_sha256`: the exact qualified modern firmware identity.

They reject the legacy feed, an unknown profile, or the legacy manifest name
before installing files. The downloaded object manifest must also bind its
version to the selected GitHub release, its channel to the modern repository
and manifest name, and its compatibility to both `lvgl-modern` and the stored
firmware identity. Only the manifest's `packages` array is staged. The combined
firmware image and release provenance assets are never treated as filesystem
OTA payloads.

The legacy path remains unchanged: legacy TartLab state defaults to
`legacy-mp123`, consumes only `tdhoward/TartLab`, and requires the historical
`manifest.json` list. Non-TartLab package repositories retain that historical
format.

## Promotion evidence contract

`tools/check_modern_qualification.py` validates the sanitized JSON summary
that the protected modern promotion workflow downloads from the supplied
durable HTTPS reference. The workflow verifies the file's exact SHA-256 and
requires it to match the rebuilt candidate, selected firmware, modern tag,
target repository, and qualified board.

The reference must be a public HTTPS URL without embedded credentials, a query
string, or a fragment because it is copied into the published promotion
attestation. Redirects are restricted to HTTPS.

The JSON has schema 1 and exactly these top-level fields:

```json
{
  "schema": 1,
  "profile": "lvgl-modern",
  "version": "modern-v1.2.3",
  "target_repository": "tdhoward/TartLab-modern-releases",
  "candidate_checksums_sha256": "<64 lowercase hex>",
  "firmware_sha256": "187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab",
  "board": {
    "model": "LilyGO T-Display-S3 Pro",
    "pcb_revision": "1.1",
    "chip_revision": "<observed revision>",
    "flash_size_bytes": 16777216,
    "psram_size_bytes": 8388608
  },
  "operator": "<sanitized operator identifier>",
  "tested_at_utc": "2026-08-26T20:00:00Z",
  "artifacts": {
    "clean_provisioning_journal_sha256": "<64 lowercase hex>",
    "migration_provisioning_journal_sha256": "<64 lowercase hex>",
    "serial_log_sha256": "<64 lowercase hex>",
    "support_window_policy_sha256": "<SHA-256 of authenticated support-window.json>"
  },
  "gates": {
    "adult_provisioning": {"status": "passed", "evidence": ["<reference>"]},
    "hardware": {"status": "passed", "evidence": ["<reference>"]},
    "ota": {"status": "passed", "evidence": ["<reference>"]},
    "recovery": {"status": "passed", "evidence": ["<reference>"]},
    "release_feed_isolation": {"status": "passed", "evidence": ["<reference>"]},
    "support_window": {"status": "passed", "evidence": ["<reference>"]}
  }
}
```

Each gate needs at least one durable evidence reference. References point to
the detailed sanitized record; do not embed serial logs, Wi-Fi values,
credentials, student files, or captured protected-state values in this JSON.
The detailed physical record must cover the provisioning matrix in
`tests/PHASE6_PROVISIONING.md`, profile-specific display/touch/AP/IDE/APP
behavior, a direct modern-to-modern OTA with pending-health commit, offline
recovery resume, corrupt/interrupted update containment, and queries proving
that modern and legacy devices see only their own release feeds.

The support-window gate uses the approved policy in
`profiles/modern-support-window.json`: stable v0.13 is the direct-migration
floor, and recognized later stable versions remain in the window when they use
one of the declared legacy layouts. The evidence hash must match the
authenticated `support-window.json` shipped with the exact candidate. The
detailed record must exercise the floor itself, not only a newer or clean
device. Sources older than v0.13 or with an unknown layout must be shown to
stop before erase and use the documented adult clean-provision/manual-restore
path.

This policy is fail closed: a missing, pending, malformed, mismatched, or
unreachable qualification record blocks the promotion job before signing or
publishing. The physical record below now satisfies the required gates for the
exact `modern-v0.14.8` candidate. That result does not publish a release:
promotion still requires a commit-bound sanitized JSON summary, protected
environment approval, a reproducible tag rebuild, and signed publication to
the isolated modern repository.

## Physical modern-to-modern OTA session: 2026-08-27

Candidate `modern-v0.14.7` at source commit
`4cf565713537fd7fa109e628941807b1c8e18ee4` was downloaded from successful
qualification workflow run `33125667951`. The candidate `checksums.json`
SHA-256 was
`b66d3de474b05a6cf5ba04cd94bb0979a7cfb9bd672da4f0e3bbaea768027537`,
the authenticated support-window SHA-256 was
`702710eb438d67fdc4ebcb1ab6f697375b531051421ec2a63eb81334f3139a95`,
and the firmware identity remained
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
The modern release preflight passed for all 11 packages. All 23 release
subjects verified against the bundled GitHub Artifact Attestation, exact
`refs/tags/modern-v0.14.7` source ref, protected qualification workflow, SLSA
provenance predicate, and non-self-hosted-runner policy.

The qualification LilyGO T-Display-S3 Pro began in healthy IDE mode at
`modern-v0.14.6`, runtime profile `lvgl-modern`, modern repository and manifest,
and no pending version. A temporary LAN feed exposed only the authenticated
modern manifest and its 11 hash-verified package archives. The server used an
exact-interface binding, a random 256-bit path capability, no directory listing,
and a strict manifest-derived allowlist. The board fetched the manifest with
HTTP 200 while an invalid capability returned HTTP 404. The server and its
ephemeral capability were removed after the transaction.

`tools/phase1_device.py ota-install` now accepts the explicit
`--manifest modern-manifest.json` option while retaining `manifest.json` as its
legacy default. The local-release adapter supplied the authenticated candidate
assets to the normal profile-aware updater; it did not bypass the modern
repository, manifest-name, runtime-profile, firmware-identity, object-manifest,
archive-hash, TAR-structure, target, space, or pending-health checks. The device
downloaded and verified all 11 packages, preserved the installed recovery
runtime and protected boot gate, replaced all managed targets, and returned
`OTA_OK=True`. The old version remained committed until the next healthy IDE
boot consumed the `pending_health` marker. The on-disk repository state then
reported `modern-v0.14.7`; one subsequent normal reset refreshed the IDE's
startup cache, after which `/api/versions` also reported `modern-v0.14.7` with
no pending version.

All protected digests matched before and after OTA and the final recovery boot:

| Path | SHA-256 |
| --- | --- |
| `/app.py` | `e37866f2ca02e0aaaa66358e037101b54c8057cd747af57fd567c7df932af1f9` |
| `/hdwconfig.py` | `49d36afa0627c30c930bc9db642d20dedb3252340f9079ce27fc62eefccdab06` |
| `/device` | `a1f4f961652900fb7a4e2de517095c1a083e1bea5cc594d5d7f6f405817ab42e` |
| `/files/user` | `bd441be8219289c23d4b02ec5f3f008d46ca518d390c50ac6abc03541fb1007e` |
| `/state/selected_app.json` | `1e720e1ecff3dc514c6ebcf1d95508001c601062d3911fa34fb77ef223d398ab` |

Chrome then rendered the updated TartLab page with no file-panel error and
working editor controls. A browser-origin synthetic save/read/run/delete cycle
returned HTTP 200 throughout, read back exact content, observed
`PHASE6_POST_OTA_BROWSER_OK`, and removed its temporary user file. The sanitized
browser screenshot SHA-256 was
`dbd78a5e8fa1b68647e47be19b0da5db05550006fa7a93416a9c990fbf3556c7`.
The OTA transcript SHA-256 was
`67d54f6ee800c6d2b86b5e846f6d5a404ac6303f72266de51326a1e646ed4e5b`;
it contains no Wi-Fi credentials or protected-file contents.

A final one-shot recovery boot took the station IDE offline and advertised the
open `TartLab-Recovery` SSID, which was physically observed. An ordinary reset
returned the board to `modern-v0.14.7`, healthy IDE mode, zero consecutive
failures, and no update marker.

## Physical recovery-browser corrective session: 2026-08-27

The same authenticated `modern-v0.14.7` candidate was then exercised through
the display-independent recovery browser. The physical helper joined the
configured station network before enabling the recovery AP, downloaded the
modern object manifest and all 11 package archives from the temporary candidate
feed, and used the installed recovery implementation to validate the profile,
channel, firmware identity, package hashes, TAR structure, protected targets,
and required extraction space. It recorded a recovery-source `installing`
marker with no completed packages, then exposed the real recovery console for
an offline staged resume. The local release adapter affected only this physical
qualification session; production profile and manifest validation remained in
force.

Windows temporarily joined the open `TartLab-Recovery` AP and Chrome loaded
`http://192.168.4.1/`. Chrome observed the `TartLab Recovery` heading, all three
`/retry`, `/ide`, and `/update` forms, and the `/status` link. The redacted
status endpoint returned HTTP 200 with recovery mode, zero boot failures,
`installing` update status, and pending `modern-v0.14.7`. Clicking the actual
`Install latest corrective release` button returned `Installing update; watch
the serial log`. The recovery updater then revalidated the staged files,
installed all 10 non-recovery packages, retained its running recovery package,
and reported `Recovery installed modern-v0.14.7; boot health is pending`.
The recovery-page screenshot SHA-256 was
`d89425e9d41bec6d84b011ea5cc98d2b348d9e479e60f7923974a7d6f1805b08`.

Boot sequence 76 reached `HEALTHY mode=IDE` and committed the pending version
exactly once. Later diagnostic boots retained no update marker. An independent
browser physically loaded the IDE after reset; headless Chrome then confirmed
the loading overlay was hidden, `/api/versions` returned HTTP 200 with
`modern-v0.14.7` and `lvgl-modern`, and final boot sequence 82 was healthy IDE
mode with zero consecutive failures. All five protected digests in the table
above still matched exactly. The final sanitized IDE screenshot SHA-256 was
`dbd78a5e8fa1b68647e47be19b0da5db05550006fa7a93416a9c990fbf3556c7`.
The temporary server was stopped and the temporary host recovery Wi-Fi profile
was removed after the original saved Wi-Fi profile had been restored.

## Live public release-feed isolation: 2026-08-27

`tools/check_release_feed_isolation.py` bound the sanitized deployed v0.13
repository record and the checked-in modern profile to their respective public
GitHub Release API responses. The read-only live check observed 14 releases in
`tdhoward/TartLab`; the legacy updater's first stable selection was `v0.13`,
all 14 releases contained `manifest.json`, and none contained
`modern-manifest.json`, a modern-only metadata asset, or a firmware BIN. The
separate `tdhoward/TartLab-modern-releases` feed contained zero releases, which
matches the checked-in `promotion-gated-unreleased` status. The physically
qualified modern device's `/api/versions` response independently recorded that
same modern repository and `modern-manifest.json`, so it cannot discover the 14
legacy releases.

The checker performs no mutation and fails closed on an empty legacy feed,
cross-profile manifest or firmware assets, an unexpected pre-promotion modern
release, invalid tags, duplicate assets, or a checked-in profile/fixture that
points at the other feed. This passes the public pre-promotion release-feed
isolation observation. The promotion workflow's existing static policy still
owns the future publication target; the live check must be repeated if public
feed state changes before promotion.

## Stable promotion and post-promotion feed isolation: 2026-08-29

Protected workflow run `33223821198` rebuilt tag `modern-v0.14.8` twice,
matched the hardware-tested candidate checksum
`dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e`,
validated the commit-bound qualification evidence, produced signed GitHub
provenance, and published only to
`tdhoward/TartLab-modern-releases`. The stable release contains 25 assets: all
22 entries in `checksums.json` match GitHub's published SHA-256 digests, and
`checksums.json`, `promotion_attestation.json`, and
`release-attestation.sigstore.json` form the three required promotion extras.
The promotion record binds evidence SHA-256
`1d889e55d969a906c888af9a0ac6c3af355e5b9e6770175b2c5b0e02b7d4d8c8`
to tag commit `49d5b82c795297fa0c6f12ed683af465502779a1` and firmware SHA-256
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.

The repeated read-only feed check observed the original 14 legacy releases
still selecting `v0.13` and exactly one modern release selecting
`modern-v0.14.8`. The legacy feed contains no modern manifest or firmware, the
modern feed contains no legacy manifest, and the checker reported
`cross_profile_assets: false` and `mutation_performed: false`.

## Physical support-window floor migration: 2026-08-27--28

The same authenticated `modern-v0.14.7` candidate was provisioned from the
oldest approved direct-migration source. The qualification board ran the exact
1,631,424-byte MicroPython 1.23.0 legacy image with SHA-256
`41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
Its runtime enumerated on COM6 and the ESP32-S3 ROM/modern endpoint on COM3.
The sanitized `legacy-root-v1` fixture reported installed version `v0.13`; the
ignored local credential file was applied only to the physical device and no
credential value was retained as evidence.

The authenticated provisioning transaction reverified all 23 candidate
subjects and captured 11 protected source files before any erase. The journal
recorded source profile `legacy-mp123`, layout `legacy-root-v1`, minimum and
installed version `v0.13`, and backup identifier
`sha256:761202b737d5ee4a62915d3db63cf5cf483fef0a285bb3eacf877dcd614b4cff`.
The ESP32-S3 native-USB flasher stub disconnected reproducibly while reading
absolute flash address `0x83000`. Source validation was therefore hardened to
SHA-256 the same locked identity regions through bounded 256 KiB ROM-only
reads with no intervening reset. The targeted 18-test provisioning suite
covers the bound, ROM-only behavior and cleanup of every temporary readback.
The physical retry passed both pinned region hashes before the journal advanced
to `backed_up` or permitted erase.

The candidate firmware then flashed and verified. Windows exposed the reset
native-USB name before it was writable during the first filesystem upload, so
the installer now uses the same qualified three-second settle interval as the
health check. Resume verified and reused the already matching firmware,
installed all 210 prepared files, reached `awaiting_health`, and committed
`modern-v0.14.7` exactly once after the health check. The completed private
journal SHA-256 is
`c85ef50ff93adfe0704ce21ece7bf175ab933d58276c84c454376329a5078d62`.

Secret-safe comparison against a fresh 211-file post-migration snapshot found
byte-identical legacy `/app.py`, `/hdwconfig.py`, canonical settings, and both
user files. The active modern selector exactly matched the prepared image, the
selected application retained its legacy semantic value, the repository moved
to `tdhoward/TartLab-modern-releases` with profile `lvgl-modern`, and no pending
update remained. The five source logs remain in the private backup and the
device retained a healthy five-file rolling window. The post-snapshot manifest
SHA-256 is
`d718f99e57d049b442e738da4b0fc7e0df92d6b89e59920778a07683ac6561d0`.

After a normal reset, isolated headless Chrome rendered the physical IDE with
title `TartLab`, hid the loading overlay, and showed no file-panel connection
error. Read-only `/api/versions`, `/api/space`, and `/api/files/user` requests
all succeeded; they reported `modern-v0.14.7`, `lvgl-modern`, valid filesystem
space, both migrated user files, and a valid selected-app index. This passes
the candidate-bound physical support-window floor observation without
qualifying any source older than v0.13.

## Physical clean-filesystem transaction: 2026-08-28

The same authenticated `modern-v0.14.7` candidate was exercised through a new
clean provisioning journal on COM3. All 23 candidate subjects reverified
against the tag-bound qualification signer before mutation. The transaction
used an empty source inventory, performed an actual erase even though the
qualification board initially contained matching modern firmware, wrote and
verified the exact candidate, uploaded 200 prepared files, retained the old
version state until a healthy normal IDE boot, and then reached journal stage
`complete` with `healthy: true`. The completed private journal SHA-256 is
`686482b6a79cec4e6b4e63113155b9a006b8b500c07b3af11f78c18e8069b379`.

The matching-firmware boundary exposed a host-tool defect before erase: a new
clean transaction could previously treat an already matching image like a
resume and overlay stale filesystem content. New transactions now always
erase/write/verify, while only an explicit resume may reuse verified firmware.
The targeted provisioning suite and all 164 host tests passed with that guard.

USB-only post-provision inspection reported MicroPython 1.27.0, exact modern
firmware identity, the isolated modern profile/feed/manifest, committed
`modern-v0.14.7`, no pending update, zero configured Wi-Fi networks, and the
fallback AP active at `192.168.4.1`. A fresh 207-file snapshot matched every
immutable prepared file; its only differences were the consumed update marker,
committed repository state, and expected generated boot/log/migration/settings
state. The private snapshot-manifest SHA-256 is
`f2b419086d5dae9b4aa971bf3aa17c35ea5b1df3ba222faaebd795d039558c8d`.

That snapshot also proved that `modern-v0.14.7` selected `hello.py` without
shipping `/files/user/hello.py` or an authenticated clean-default copy. The
candidate therefore cannot pass APP mode on a truly empty device. The build
now includes the source starter application under update-managed
`/defaults/user`, clean provisioning requires and copies that authenticated
seed, and modern release preflight fails closed when it is absent. A local
dirty `modern-v0.14.8` diagnostic build passed that preflight and all 165 host
tests, but it is not signed qualification input. Clean qualification must be
repeated with a new commit- and tag-bound candidate.

This is partial clean-case evidence. Human display/touch, tablet IDE
edit/save/run, selected APP, and recovery observations remain required before
the clean-provisioning gate can pass.

The correction was then committed as
`49d5b82c795297fa0c6f12ed683af465502779a1`, tagged
`modern-v0.14.8`, and rebuilt by protected qualification workflow run
`33188118448`. All 23 subjects in that candidate reverified against the bundled
attestation, exact tag ref, protected signer, SLSA predicate, and hosted-runner
policy. Its `checksums.json` SHA-256 is
`dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e`.
Read-only clean preflight and all 165 host tests passed.

A new COM3 clean transaction used an empty source inventory, erased flash,
wrote and verified the exact candidate firmware, and uploaded 202 prepared
files including authenticated `/defaults/user/hello.py` and its clean-seeded
`/files/user/hello.py` copy. The journal remained at `awaiting_health` until a
normal boot consumed `/state/update.json`, then committed
`modern-v0.14.8` at stage `complete`. Its SHA-256 is
`98f712cfff5252be368d767cda45688d4097adb7881000361fbd382a71131a53`.

USB-only inspection reported MicroPython 1.27.0, exact firmware identity,
profile `lvgl-modern`, the isolated modern feed/manifest, zero configured Wi-Fi
networks, and the expected root layout. In the 208-file snapshot, every
immutable prepared file matched; only the consumed update marker, committed
repository state, and seven generated boot/log/migration/settings paths
differed. Both starter copies matched the authenticated prepared bytes. The
private snapshot-manifest SHA-256 is
`054fbdcd82990efdd47e6195f2d56bc7b5cfb87f1b34cf6c9ada2871d4e50f1c`.
The board was reset after capture without joining this PC to its temporary AP.

This supersedes the unsigned diagnostic result and passes the corrected
candidate's automated clean-filesystem checks. The operator then used only a
tablet on the temporary fallback AP to load the IDE, verify seeded `hello.py`,
and complete create/edit/save/reopen/run/delete with expected console output.
This PC did not join the device AP.

Human observation confirmed upright, correctly ordered red/green/blue/white/
black display bands and correctly oriented touches at all four corners and the
center. A hash-bound, collision-safe temporary visual app preserved the
original `hello.py` selection; the GPIO 12 APP boot showed the expected five
vertical color bands, after which cleanup restored `hello.py` and removed only
the temporary qualification files.

A durable early-boot request then advertised `TartLab-Recovery`; the tablet
loaded its page and observed the status and controls. `Force IDE on next boot`
returned the normal fallback AP and IDE, and a further unpressed physical reset
again returned to the IDE. Final USB state was healthy IDE mode with zero boot
failures, selected `hello.py`, `STARTUP_MODE=BUTTON`, and no recovery flag. The
corrected signed candidate therefore passes the complete clean-provisioning
case.

Together, the candidate-bound sessions qualify the support-window floor
migration, direct modern-to-modern OTA normal path,
recovery-page rendering and redacted status, the corrective-update button,
offline staged recovery resume, pending-health commit, protected-state
preservation, browser regression, and recovery availability for this candidate.
The exhaustive provisioning power-loss matrix subsequently passed with the
same signed candidate, as recorded in `PHASE6_PROVISIONING.md`.

## Physical corrupt/interrupted OTA containment: 2026-08-28 (item 7 passed)

The signed `modern-v0.14.8` candidate was staged over USB through
`tools/qualify_modern_update_containment.py`. The qualification-only helper is
separate from both installed updaters, requires `--execute` and
`--confirm-fault`, verifies the complete release and its 23-subject GitHub
Artifact Attestation, and binds its reusable receipt to the exact source ref,
candidate checksums, Sigstore bundle, and all twelve staged asset hashes. This
PC never joined a device Wi-Fi network and no local HTTP server was started.

For the corrupt-download case, the adapter changed one bit only in the
normal updater's temporary copy of authenticated `pydevices.tar`. The installed
updater rejected its hash, returned `UPDATE_FAILED`, retained committed version
`modern-v0.14.8`, and created no update marker. The private receipt SHA-256 is
`07b4ebc42d7fd77a9b47c281e742b2d5e8154e87bea8626ac0e00f743e827de1`.

For the first real power loss, the normal updater began copying
`pydevices.tar` into its isolated `/tmp` stage. The qualified modern renderer
filled the display white, the operator immediately removed USB power for five
seconds, and the host independently observed COM3 disappear and re-enumerate.
The next boot retained `modern-v0.14.8`, no update marker, healthy IDE mode,
and zero failures. Evidence capture found eight complete authenticated staged
assets and a zero-byte `/tmp/pydevices.tar`, with no active-target overlap. The
private receipt SHA-256 is
`55c3311b7cc58fede1026ddf1ad01ef915764454cb449c8d4179e2bfec0feed7`.

For the recovery case, all twelve authenticated assets were copied into the
installed recovery updater's `/tmp/recovery` stage and revalidated there. The
updater wrote a durable recovery-source `installing` marker, recorded
`assetfiles.tar` and `libahttpserver.tar` complete, and began
`pydevices.tar`. At the white display cue, the operator again removed USB power
for five seconds and the host observed the disconnect/reconnect. Durable state
still committed `modern-v0.14.8`, retained all twelve staged assets, and booted
through the `update_installing` recovery gate. Offline
`resume_staged_update()` skipped the two completed packages, installed the
remaining eight non-recovery packages, removed recovery staging, and reached
pending health. A stable IDE boot then committed health exactly once and
cleared the marker. The private receipt SHA-256 is
`fc6e0204c6f58b1537e217c7deba015154251b73430c3146f43fff96606778f5`.

The 218-file evidence snapshot preserved the nine isolated normal-download
files. Excluding those temporary files, its 209 active files had the same
expected relationship to the authenticated 202-file prepared image as the
clean case: all 200 immutable prepared files matched byte-for-byte,
`/state/update.json` was consumed, only `/state/repos.json` changed, and the
eight extras were boot state, five logs, migration state, and settings. The
private snapshot-manifest SHA-256 is
`04bb068a60eebe9d45432efcbac3d35c16aa112d0655d7a06011a6b9210be4d6`.
Normal temporary cleanup then restored exactly 209 files. Final USB inspection
reported MicroPython 1.27.0, the expected ten root entries, zero configured
Wi-Fi networks, no update or staging state, exact `modern-v0.14.8`, and the
isolated modern feed and manifest. The sanitized transcript is
`tests/evidence/modern-v0.14.8-physical-transcript.txt`; its SHA-256 is
`d7e0caeaa8c64b08c55b40f251a921153fdfddbcab6b8f1e24f9cf5ad228862a`.

Together with the previously recorded direct OTA, recovery browser, offline
recovery, release-feed isolation, support-window floor, clean provisioning,
hardware, browser, APP, and exhaustive provisioning-interruption sessions,
this completes every physical gate required by the modern qualification
contract. The strict sanitized summary is
`tests/evidence/modern-v0.14.8-qualification.json`; it passes all six gates in
`tools/check_modern_qualification.py` and has SHA-256
`1d889e55d969a906c888af9a0ac6c3af355e5b9e6770175b2c5b0e02b7d4d8c8`.
Release publication has not been invoked.
