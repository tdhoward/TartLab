# Phase 2 reproducible legacy release gate

Phase 2 candidate artifacts may be produced by `legacy-ci.yml`, but they must
not be promoted to a stable GitHub release until this gate passes on a LilyGO
T-Display-S3 Pro running exactly
`ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` (SHA-256
`41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`).

Use a candidate from the `legacy-mp123-<commit>` CI artifact. Record the
candidate's `checksums.json` SHA-256, `build_metadata.json`, board revision,
firmware hash, serial output, all rolling logs, pre/post protected-state
inventories, `statvfs`, heap/PSRAM diagnostics, and the operator/date for every
run. The evidence bundle must contain no real Wi-Fi credentials or student
work; hash the final sanitized bundle.

The candidate passes when all of the following are demonstrated:

1. Two clean CI builds are byte-identical and the host legacy gate passes.
2. Clean provisioning boots into the IDE and supports display, touch, AP mode,
   editing, saving, running, application selection, and five-log rotation.
3. One update action from the sanitized v0.13 layout reaches the candidate and
   preserves `/device`, `/state`, `/files/user`, settings, selected app,
   repositories, and logs.
4. File inventory, archive inventory, expanded bytes, startup heap/PSRAM,
   display initialization, touch coordinates, and OTA outcome are compared
   with the Phase 1 record. Explain every inventory change and any regression.
5. Power loss during a download leaves active files unchanged. Power loss
   during each clear/extract boundary enters recovery, retains the old committed
   version, and can resume or reinstall the same candidate.
6. A corrupt package, truncated archive, injected write failure, and both
   pre-download and post-staging low-space cases fail before version commit and
   preserve recovery access.
7. Three failed health checks retain the old committed version and enter the
   display-independent recovery route. A later healthy corrective boot commits
   exactly once and retains future OTA capability.

After review, invoke `promote-legacy-release.yml` with the stable tag, the
candidate `checksums.json` SHA-256, the sanitized evidence-bundle SHA-256, and a
durable evidence reference. The repository's `legacy-release` GitHub
environment must require an approving reviewer. The promotion workflow rebuilds
the tag, rejects a candidate hash mismatch, records `promotion_attestation.json`,
and only then creates the stable GitHub release.
