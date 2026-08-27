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
    "serial_log_sha256": "<64 lowercase hex>"
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

This policy is fail closed: a missing, pending, malformed, mismatched, or
unreachable qualification record blocks the promotion job before signing or
publishing. The checked-in repository still has no passing physical evidence,
so this implementation does not qualify or promote a modern release.
