# Phase 6 modern OTA and promotion qualification

The modern updater and display-independent recovery updater require this
profile-bound repository record:

- `runtime_profile: lvgl-modern`;
- `repo: tdhoward/TartLab-modern-releases`;
- `manifest: modern-manifest.json`; and
- the exact qualified `firmware_sha256`.

They reject cross-profile feeds, mismatched release versions, and mismatched
firmware before installation. Only manifest filesystem packages
are staged; firmware and provenance assets are never installed by device OTA.

## Promotion evidence contract

`tools/check_modern_qualification.py` validates a sanitized, candidate-bound
schema-1 single-board summary or schema-2 aggregate. It binds the modern tag,
target repository, candidate checksums, each firmware and board, operator/date,
artifact hashes, and these five passed gates:

1. adult clean provisioning;
2. profile-specific hardware;
3. OTA;
4. recovery;
5. release-feed isolation.

Each gate must reference durable sanitized evidence. Credentials, serial logs,
student files, private backups, and protected-state values do not belong in the
summary. Missing, pending, unreachable, or mismatched evidence fails before
signing or publication.

Qualification artifacts include the clean-provisioning journal and sanitized
physical transcript hashes. Legacy-to-modern migration is not a supported
deployment path and is deliberately outside the modern qualification contract.

## Baseline evidence and fresh qualification

[`RELEASE_POLICY.md`](../RELEASE_POLICY.md) defines one public product version
and different testing scopes for routine app/browser releases and platform
changes. All five gates still need applicable evidence for every board in the
candidate. Satisfying that evidence contract does not require rerunning every
physical test when the implementation and assumptions behind a claim remain
unchanged.

For reused claims, add a new candidate record referencing the prior board-bound
artifacts and a reviewed comparison of built content, installation semantics,
dependencies, and relevant resource limits. Record fresh focused or full test
results for changed claims, including affected supported update paths. Keep
historical records unchanged. An unchanged firmware hash alone is insufficient,
and one board's qualification cannot be inherited by another board.

The v0.15.4 records below demonstrate reviewed reuse with candidate equivalence.
They do not qualify arbitrary later app or platform changes. Select additional
checks using [`TEST_TIERS.md`](TEST_TIERS.md#selecting-release-tests).

The current schema requires `passed` plus evidence references for each gate;
it has no machine-readable inherited-claim or platform-baseline fields. Explain
the distinction in the referenced sanitized artifacts using the existing
schema. Automatic impact analysis, baseline assembly, and validation of reuse
are pending implementation. Continue through the existing protected promotion
workflow with its exact candidate, board-set, and firmware bindings.

## Qualified candidate and physical results

The qualified multi-board candidate is `modern-v0.15.4` at commit
`f86c6b02b66ed62399b73ad4f9270774e0f366e9`:

- candidate `checksums.json` SHA-256:
  `2c3688ec80a279dccb6e6265c2b72a0e7b2b510f95047670a45b5c1ddda53da8`;
- LilyGO firmware SHA-256:
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`;
- Elecrow firmware SHA-256:
  `50d98625a1ef58eee6c5fbe55b5107968301ea4dc6b8954167cad9f0d65ee5a3`;
- qualification summary SHA-256:
  `7785f0ba835a44ff7408346598348a52c44b0ebaed174564882d4fb24d2b4406`.

The aggregate binds prior full physical records and exact-candidate bridges for
both boards. Together they establish:

- authenticated clean provisioning and health;
- display, touch, brightness, launcher, app, and browser IDE behavior;
- normal modern-to-modern OTA with the old version retained until a healthy
  boot, protected-state preservation, and browser regression checks;
- the recovery page, redacted status, corrective-update control, staged offline
  resume, and exactly-once commit;
- rejection of a physically corrupted temporary package before mutation;
- real power loss during normal download with staging isolated from active
  files;
- real power loss during recovery installation, durable completed-package
  markers, offline resume, and exact final inventory; and
- public feed checks showing no legacy/modern cross-profile assets.

The sanitized physical transcript is
`tests/evidence/modern-v0.15.4-elecrow-physical-transcript.txt` for Elecrow and
`tests/evidence/modern-v0.15.4-lilygo-physical-transcript.txt` for LilyGO.
The machine-readable qualification summary is
`tests/evidence/modern-v0.15.4-qualification.json`.

## Promotion result

Protected workflow run `34009221873` rebuilt the tag twice, matched the
qualified candidate, validated the evidence, generated signed provenance, and
published 29 assets only to
`tdhoward/TartLab-modern-releases`. Independent post-publication verification
matched the two-board matrix and candidate checksum and verified all 28 signed
release subjects against the protected promotion workflow and source tag.

The post-promotion audit confirmed that `modern-v0.15.4` exists as a release
only in the isolated modern repository and not in the source repository. It is
the published, lab-qualified modern alpha for the LilyGO T-Display-S3 Pro and
Elecrow DLE06235B, not evidence of a field rollout.
