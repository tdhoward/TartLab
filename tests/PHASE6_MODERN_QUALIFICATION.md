# Phase 6 modern OTA and promotion qualification

The modern updater and display-independent recovery updater require this
profile-bound repository record:

- `runtime_profile: lvgl-modern`;
- `repo: tdhoward/TartLab-modern-releases`;
- `manifest: modern-manifest.json`; and
- the exact qualified `firmware_sha256`.

They reject cross-profile feeds, legacy manifests, mismatched release versions,
and mismatched firmware before installation. Only manifest filesystem packages
are staged; firmware and provenance assets are never installed by device OTA.
The legacy updater contract remains unchanged.

## Promotion evidence contract

`tools/check_modern_qualification.py` validates a sanitized, candidate-bound
schema-1 JSON summary. It binds the modern tag, target repository, candidate
checksums, firmware, board, support-window policy, operator/date, artifact
hashes, and these six passed gates:

1. adult provisioning and migration;
2. profile-specific hardware;
3. OTA;
4. recovery;
5. release-feed isolation; and
6. support window.

Each gate must reference durable sanitized evidence. Credentials, serial logs,
student files, private backups, and protected-state values do not belong in the
summary. Missing, pending, unreachable, or mismatched evidence fails before
signing or publication.

## Qualified candidate and physical results

The final candidate was `modern-v0.14.8` at commit
`49d5b82c795297fa0c6f12ed683af465502779a1`:

- candidate `checksums.json` SHA-256:
  `dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e`;
- firmware SHA-256:
  `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`;
- qualification summary SHA-256:
  `1d889e55d969a906c888af9a0ac6c3af355e5b9e6770175b2c5b0e02b7d4d8c8`.

Candidate-bound sessions established:

- migration from the exact stable v0.13 floor with protected categories
  preserved through the required selector/state translations and browser/API
  validation;
- clean provisioning with authenticated starter content, display/touch,
  tablet IDE, APP mode, and recovery;
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
`tests/evidence/modern-v0.14.8-physical-transcript.txt`, SHA-256
`d7e0caeaa8c64b08c55b40f251a921153fdfddbcab6b8f1e24f9cf5ad228862a`.
The machine-readable qualification summary is
`tests/evidence/modern-v0.14.8-qualification.json`.

## Promotion result

Protected workflow run `33223821198` rebuilt the tag twice, matched the
qualified candidate, validated the evidence, generated signed provenance, and
published 25 assets only to
`tdhoward/TartLab-modern-releases`. All 22 checksummed release subjects matched
GitHub's published digests; the remaining assets were the checksums, promotion
attestation, and release-attestation bundle.

The post-promotion read-only feed audit found the unchanged 14-release legacy
feed selecting `v0.13` and one modern release selecting
`modern-v0.14.8`, with no cross-profile assets. This is a published,
lab-qualified modern alpha reference for the T-Display-S3 Pro, not evidence of
a field rollout. No modern devices are field-deployed, so this historical
release does not require an intermediate bridge before the first supported
selection-aware multi-board alpha.
