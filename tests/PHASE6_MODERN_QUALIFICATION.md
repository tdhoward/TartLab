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

`tools/check_modern_qualification.py` validates sanitized, candidate-bound
schema-3 results for new candidates and retains schema-1/schema-2 validation
for historical records. It binds the modern tag,
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

New candidates carry a signed snapshot, qualification request, and computed
report. Schema-3 evidence records each gate as fresh or inherited, plus current
automated, resource, browser, and update-path results as required. Validate it
with `tools/check_modern_qualification.py --release ...`; promotion performs
the same recomputation and verifies the baseline's protected release signatures.
Historical schemas cannot bypass those checks on new candidates. Follow
[`RELEASE_TOOLING.md`](../RELEASE_TOOLING.md) to establish the first signed
baseline, generate the evidence form, and complete the required results.

## Modern v0.16.0 promotion

`modern-v0.16.0` at source commit
`5c5b722c266700bd3fb849cdd6728c350e9c92b3` was published on 2026-09-10 by
[protected promotion run 34543990735](https://github.com/tdhoward/TartLab/actions/runs/34543990735).
The workflow rebuilt the candidate twice, validated schema-3 evidence, and
published 30 assets to the isolated modern release repository.

- Candidate checksums SHA-256:
  `2d308e32537e263a0812567243d69aee5d0b19a6f4ee89e898e4a69a8c3eebba`.
- Qualification evidence SHA-256:
  `abdf977cbe59a1fc349ec7d983db2eb5f6d5ca1c87ab583cfbf7f3dea3f19547`.
- Evidence: [`modern-v0.16.0-qualification.json`](evidence/modern-v0.16.0-qualification.json),
  with immutable references and hashes for both physical transcripts.

Fresh physical results cover the Elecrow DLE06235B and LilyGO T-Display-S3 Pro
PCB 1.1. Tim corrected the Pro's original PCB 1.2 entry: that revision belongs
to his separate non-Pro pushbutton board. The corrected transcript preserves
the explanation. The tested candidate and firmware did not change.

The tests include clean provisioning, browser editing and commands, resource
checks, same-version update application, corrupted-package rejection, real
power loss during download and recovery installation, offline recovery, and
healthy-boot commit behavior. The release declares no older installed update
sources; these results do not claim an older-version upgrade or internet OTA
delivery. See the transcripts for exact scope and operator observations.

The downloaded release matched the tested candidate checksum and both firmware
identities. The live feed audit selected `modern-v0.16.0` for modern and `v0.15`
for legacy, with no cross-profile assets.

Independent verification passed for all 29 signed release subjects against
the protected promotion workflow and `refs/tags/modern-v0.16.0`. The captured
baseline is `profiles/baselines/modern-v0.16.0.json`, pinned in the release plan
with SHA-256
`d9bc1f53e83ab555646a84a81a20ca325838acf7296bba0f0f4589450aa7291e`.
The plan remains in platform mode; future candidates compute which claims can
be inherited and which require fresh evidence.

## Historical modern v0.15.4 candidate and physical results

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
