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
publishing. The physical record below is partial and does not satisfy every
required gate, so this implementation does not qualify or promote a modern
release.

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

Together, the two sessions qualify the direct modern-to-modern OTA normal path,
recovery-page rendering and redacted status, the corrective-update button,
offline staged recovery resume, pending-health commit, protected-state
preservation, browser regression, and recovery availability for this candidate.
They do not yet qualify physical corrupt or interrupted OTA/recovery
containment, the support-window floor migration case, clean provisioning, or
the exhaustive power-loss matrix, so promotion remains blocked.
