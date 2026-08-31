# Modern touchscreen startup and IDE power qualification

This is the live focused-smoke checklist for the modern touchscreen launcher,
local app chooser, and IDE inactivity backlight policy. The implementation is
host-tested, but no physical or release qualification has been recorded for
it. The published `modern-v0.14.8` evidence predates the feature and must not be
reused.

## Claim boundary

Passing this checklist on an arbitrary source checkout is useful engineering
feedback, not release evidence. Qualification must name and hash the exact:

- source tag and commit;
- candidate `checksums.json` and filesystem inventory;
- runtime profile and release repository;
- board ID and lifecycle state; and
- firmware image, lock, and SHA-256.

The qualified T-Display-S3 Pro is the minimum current target. Test every other
board deliberately included in the candidate. The Elecrow DLE06235B remains a
`bringup` board unless its separate lifecycle gates are completed; a successful
smoke does not advance or imply its support status.

Keep raw serial output, Wi-Fi credentials, student files, backups, device IDs,
and protected-state values in the private hardware workspace. Commit only a
sanitized result tied to public candidate identities.

## Before hardware

- [ ] The worktree and candidate inputs are clean and reviewed.
- [ ] The normal Tier 0 and Tier 1 checks pass, including
  `tests.test_modern_power`.
- [ ] Tier 2 pinned-MicroPython compatibility passes on the generated
  distribution.
- [ ] The modern profile, board catalog, firmware artifact, release package,
  archive ownership, and feed-isolation validators pass.
- [ ] The candidate board set is explicit; no `bringup` board is presented as
  qualified.
- [ ] Candidate and firmware hashes are recorded before installation.
- [ ] Protected-state digests are captured privately before installation.

## Focused physical smoke per included board

Use reliable power. Start from a known healthy candidate installation and
record observations without exposing protected data.

- [ ] Reset shows an upright launcher with readable text and usable touch
  targets; no physical IDE/app button is required or read.
- [ ] No interaction starts IDE after 10 seconds, the HTTP server becomes
  ready, and the device records `HEALTHY mode=IDE`.
- [ ] **Start IDE** takes the same healthy route without waiting for timeout.
- [ ] **Choose app** opens without starting Wi-Fi or the browser IDE, lists
  folders and valid `.py` files only, stays under `/files/user`, and scrolls on
  the board's native geometry.
- [ ] Folder navigation and cancellation leave `/state/selected_app.json`
  unchanged.
- [ ] Selecting a file requires confirmation; cancelling confirmation leaves
  state unchanged.
- [ ] **Set as app** updates the visible filename and durable selected-app
  state but does not run the app automatically.
- [ ] **Run selected app** cleanly transfers LVGL ownership to the direct
  surface, shows a visually distinctive app, and records `HEALTHY mode=APP`
  after the existing health delay.
- [ ] Reset from that app returns to the launcher rather than automatically
  repeating APP mode; a subsequent IDE selection becomes healthy.
- [ ] In IDE mode the display remains at configured maximum brightness until
  the inactivity delay, then visibly dims to the configured dim level.
- [ ] Touch activity before the deadline postpones dimming.
- [ ] The first touch after dimming restores normal brightness and is consumed;
  a later touch is delivered normally.
- [ ] `auto_dim_seconds=0`, brightness clamping, and dim-not-above-maximum
  behavior match the host-tested contract; restore default/local settings
  after the observation.
- [ ] APP handoff, an injected startup error, and repeated IDE teardown restore
  normal brightness without leaving duplicate inactivity tasks.
- [ ] At least 100 LVGL/direct-surface ownership cycles complete without panel
  corruption, a stuck DMA transfer, heap exhaustion, or a crash.
- [ ] Display orientation, touch regions, free heap, reset behavior, Wi-Fi/AP,
  browser editing, recovery access, and future OTA access remain healthy.

If a file is removed between display and confirmation, **Set as app** must fail
without changing selected-app state. This race is covered on the host and
should be included in the physical smoke when practical without risking real
student work.

## Candidate and release completion

- [ ] Rebuild after every source or packaging correction and repeat the smoke
  against the replacement candidate.
- [ ] Run the complete modern provisioning, migration, OTA, recovery,
  interruption/resume, protected-state, feed-isolation, support-window, and
  future-update gates from `PHASE6_PROVISIONING.md` and
  `PHASE6_MODERN_QUALIFICATION.md`.
- [ ] Compare final installed inventory and protected-state digests with the
  expected candidate and pre-install values.
- [ ] Add sanitized board-bound evidence and validate it with
  `tools/check_modern_qualification.py`.
- [ ] Promote only the exact qualified tag through the protected modern
  workflow, then perform the post-publication feed and provenance audit.

Until every applicable item passes for one unchanged candidate, describe the
feature as implemented and host-tested, not physically qualified, complete, or
released.
