# Modern touchscreen startup and IDE power qualification

This is the live focused-smoke checklist for the modern touchscreen launcher,
local app chooser, and IDE inactivity backlight policy. The implementation is
host-tested, but no physical or release qualification has been recorded for
it. The published `modern-v0.14.8` evidence predates the feature and must not be
reused.

Modern remains early alpha and has no field-deployed devices. The exact
candidate used for this qualification may therefore introduce selection-aware
multi-board packaging directly; no single-board bridge release is required.
This changes release sequencing only, not the requirement to qualify every
included board and firmware identity.

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

## 2026-08-31 engineering smoke (not qualification)

A T-Display-S3 Pro engineering fixture was clean-flashed from the local modern
build based on commit `1a0850a88dda42ef747953908f9689701bb1edfc`, then updated
with working-tree corrections found during the smoke. Because the final source
was dirty and was not an attested exact candidate, these observations do not
check off the qualification gates below.

The smoke found that raw CST226 samples were correct but visible launcher
buttons initially received no clicks. Instrumentation recorded left, middle,
and right taps at logical `(97, 184)`, `(256, 170)`, and `(415, 173)`, all
inside their displayed hitboxes. The pointer framework had applied the 270
degree panel rotation before LVGL applied the same rotation again. Leaving the
pointer at its raw startup rotation corrected the duplicated transform; the
normal launcher then accepted **Run selected app** and reached
`HEALTHY mode=APP`.

The corrected chooser physically navigated into a temporary folder, selected
and confirmed a nested Python file, returned to the launcher with the updated
selection, ran it, and reached healthy APP state. The temporary file and
selection were removed afterward. Raw touch sampling recorded 32 contacts
across nearly the full 480 by 222 logical panel, and 100 UI/direct-surface
ownership cycles completed with UI ownership restored, no pending transfer,
and stable free heap.

The first physical power probe then found that the pinned LVGL binding lacks
`indev_get_next()`, leaving the inactivity controller with no touch callback.
After adding a fallback to the platform's native input object, the device
dimmed from approximately 75 percent to 15 percent, restored approximately 75
percent on the first touch without a button click, delivered one later click,
repeated the dim/wake cycle, and restored normal brightness during teardown.
That short probe did not expose a third defect: after roughly one minute of
continuous inactivity, this CST226SE fixture stopped reporting touch even
though initialization had written `0x01` to its disable-autosleep register
`0xFE`.

An isolated 85-second probe reproduced the failure. Reasserting `0xFE = 0x01`
every ten seconds kept touch observable, and a real-IDE test then remained idle
for more than 65 seconds after dimming and restored normal brightness on the
first touch. The keep-awake policy is implemented by the T-Display-S3 Pro
application adapter rather than changing the frozen CST226 driver: only one
board/controller fixture has demonstrated the persistence quirk. The final
test ran against the existing qualified firmware image with SHA-256
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab` and an
application-only working-tree candidate. The final unattended reset timed out
through the launcher and reached `HEALTHY mode=IDE`; temporary brightness and
selection settings were removed afterward.

Follow-up cleanup moved the T-Display-S3 Pro constructor and hardware quirks
out of the generic modern adapter and into its board-owned runtime payload,
moved the rejected PyDevices comparison outside production `src`, made IDE task
teardown safe when a serial interrupt occurs inside the task being stopped, and
made reviewed PyDevices text-input hashes independent of checkout line endings.
The later board-package cleanup made `/device/board.json` authoritative and
confined installed board support to the selected `/board/<board_id>` subtree.
After that cleanup,
the focused regression sets and full 241-test discovery suite passed. The board
catalog, firmware artifact, modern firmware lock, and modern profile validators
passed; the production web build and a validated 200-file board-targeted modern
distribution also completed. A dirty synthetic release build produced and
validated twelve packages, including one `board-support.tar` whose only current
subtree is the qualified T-Display-S3 Pro. Earlier working-tree checks passed
the pinned MicroPython Tier
2 probe and a dirty engineering-candidate preflight. The refactored production
modules were also staged onto COM3: the fixture reached `HEALTHY mode=IDE`, an
intentional serial interruption left boot state healthy with zero consecutive
failures, and the following reset again reached healthy IDE. A clean commit,
exact candidate, authenticated provisioning transaction, complete checklist
repetition, and release gates remain required.

The subsequent isolated board-payload layout was staged without reflashing:
protected `/device/board.json` selected
`/board/lilygo_t_display_s3_pro/t_display_s3_pro_modern.py`. The obsolete
T-Display adapter copies under `/lib/tartlabutils` and `/configs` were removed,
and an uninterrupted reset again reached `HEALTHY mode=IDE`. This proves the
engineering fixture used the dedicated selected-board path, but it does not
qualify the new package/update transaction.

A later review found that the selected board path was still added after
`/files/user`, permitting a student module with the selector's name to shadow
the protected choice, and that a missing selected expanded-size value fell
back to compressed archive size during the install-space check. Both cases now
fail closed or preserve protected import precedence and have host regression
coverage. On COM3 the path order changed from board index 6/user index 2 to
board index 1/user index 3 while the selector continued loading from the
dedicated LilyGO board subtree. The native platform and CST226 identity probes
passed and an uninterrupted reset reached healthy IDE. A new renderer-cycle
probe did not run because the diagnostic USB endpoint stopped accepting writes
after the preceding probe; this is not recorded as a renderer pass. The prior
100-cycle working-tree result remains non-qualifying historical smoke and is
not substituted for an exact-candidate gate.

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
