# Phase 2 reproducible legacy release gate

This record qualifies the first reproducible legacy candidate and defines the
minimum physical gate for future legacy promotion. It does not authorize a
different current candidate.

## Qualified checkpoint

- Session: 2026-08-10; operator Tim.
- Board: LilyGO T-Display-S3 Pro PCB v1.1, 16 MiB flash, 8 MiB octal PSRAM.
- Firmware SHA-256:
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
- Clean candidate commit:
  `a42bedc1367d0b1e6b694dd059889db15f1008d2`.
- CI run: <https://github.com/tdhoward/TartLab/actions/runs/31412535152>.
- Candidate `checksums.json` SHA-256:
  `15cc9cec697a3cd553c6ed8c3daff6c105eb1eef6564039dfcc59a7bbb337a15`.
- Sanitized evidence ZIP SHA-256:
  `dc574e4c206b656f0d71b40091fa1aea8d253f806fff44dea28b5ccb09da8477`.
- Result: the technical matrix passed with an environmental qualification;
  the candidate was not promoted.

The laptop hotspot and USB power path caused intermittent real resets. Recovery
containment held and an uninterrupted retry from unchanged v0.13 completed,
but a reviewer was permitted to require repetition on controlled power/network
hardware.

## Established behavior

The exact candidate demonstrated:

- byte-identical clean builds, validated inventories, hashes, ownership, and
  size budgets;
- clean provisioning with display, touch, GPIO, AP/browser IDE,
  edit/save/run/select-app, APP mode, and five-log rotation;
- one user action from the sanitized v0.13 layout to the candidate with all
  protected state preserved;
- no material regression from Phase 1 and continued octal-PSRAM availability;
- safe handling of real download resets, corrupt packages, truncated TARs,
  pre/post-staging low space, injected writes, and power loss after the install
  marker;
- deterministic offline recovery resume;
- retention of the old version through repeated failed-health boots followed by
  exactly-once commit after a healthy corrective boot; and
- a subsequent OTA, proving future update access.

The first transition displayed a stale progress denominator because the v0.13
updater itself rendered it; the installed candidate reported later progress
correctly.

## Promotion rule

`promote-legacy-release.yml` was not invoked. Every future stable legacy
release must bind a clean tag, the exact CI candidate checksum, and a sanitized
durable physical record to the protected `legacy-release` environment. The
current open milestone is to repeat this matrix on the candidate selected for
publication, then audit the legacy-only feed after promotion.
