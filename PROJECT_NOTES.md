# TartLab project context

This file is the short architectural brief for contributors and AI agents. Use
[`README.md`](README.md) for product usage, [`DEVELOPMENT.md`](DEVELOPMENT.md)
for commands, and the documents under [`tests`](tests) for qualification
evidence.

## Product and current status

TartLab is a browser-based MicroPython IDE hosted by a Wi-Fi microcontroller.
It is designed for classrooms: students use a browser to edit, save, and run
programs without installing drivers, desktop IDEs, or firmware tools. The
qualified board is currently the LilyGO T-Display-S3 Pro PCB v1.1. The Elecrow
DLE06235B has a healthy experimental IDE-mode bench boot with owner-confirmed
setup-AP, LAN, and browser editing workflows, but remains recorded separately
in `bringup` state; this is not a supported-board claim.

Two runtime profiles are maintained:

| Profile | Runtime and release feed | Status |
| --- | --- | --- |
| `legacy-mp123` | Exact MicroPython 1.23.0 octal-SPIRAM image; `tdhoward/TartLab`; legacy `manifest.json` | `v0.15` is published and physically qualified on the exact MicroPython 1.23.0 image. |
| `lvgl-modern` | Pinned MicroPython 1.27.0/LVGL image; `tdhoward/TartLab-modern-releases`; `modern-manifest.json` | `modern-v0.14.8` is published and physically qualified for the T-Display-S3 Pro. Installation or migration is an adult-admin operation. |

The authoritative runtime-profile identities and status live in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json) and
[`profiles/lvgl-modern.json`](profiles/lvgl-modern.json). Modern per-board
identity, capabilities, firmware binding, and lifecycle state live under
[`boards`](boards); see [`BOARD_SUPPORT.md`](BOARD_SUPPORT.md).

## Non-negotiable constraints

- Preserve boot, IDE, recovery, and future OTA access for deployed devices.
- A normal update is one user action directly to the latest compatible stable
  release. Internal migrations may restart and resume, but users must not hunt
  for intermediate releases.
- The browser updater changes filesystem packages only. It cannot replace
  MicroPython firmware.
- Students must not need serial drivers, firmware flashing, build tools, or a
  command line. Modern firmware provisioning is an adult-admin task.
- Keep core TartLab code behind a small hardware/platform boundary. Board and
  driver details must not leak into the IDE or launcher.
- Minimize the device payload. Vendor code must be pinned, allowlisted,
  reproducible, licensed, and tested rather than copied wholesale.
- Treat settings, device captures, backups, and raw diagnostics as sensitive;
  Wi-Fi credentials are stored in plaintext.

## Runtime and hardware architecture

`src/main.py` gets display, input, networking, status rendering, delay,
brightness, and mode behavior from `tartlabutils.platform`. The legacy adapter
owns historical PyDevices paths. A headless adapter supports host tests without
board imports.

The selected hardware module is a local device property. `src/hdwconfig.py`
provides the clean-install default, while `/device/hdwconfig.py` is
authoritative after migration. Provisioning also records the board ID in
protected `/device/board.json`. The runtime adds only `/board/<board_id>` to
the import path; OTA may replace that selected board-support subtree, but must
not overwrite the local selector, identity, or calibration.

Host-side modern tooling discovers `boards/*/board.json` rather than growing
new board constants in each script. New release candidates carry a schema-2
board-to-firmware compatibility matrix while retaining the published schema-1
firmware alias for an OTA bridge from `modern-v0.14.8`. Adult provisioning
requires an explicit qualified board ID and records it under protected
`/device`; new ports proceed independently through `bringup`, `candidate`, and
`qualified` states.

The modern profile uses one native DMA-capable panel transport with exclusive
ownership between:

- LVGL UI mode for the IDE and normal controls; and
- a direct `RGB565_BE` dirty-rectangle surface for games and animation.

Mode changes must drain pending transfers, pause the old renderer, transfer
ownership, and redraw or invalidate the destination. Never let LVGL and the
direct surface drive the panel concurrently or expose private upstream driver
fields as the app API.

## Filesystem ownership

| Paths | Ownership |
| --- | --- |
| `/boot.py`, `/main.py`, `/ide`, `/configs`, managed `/lib`, `/files/help`, `/files/assets`, `/recovery` | Release-managed; replace only through the tested update transaction. |
| `/board/<board_id>` | Release-managed board shim and defaults; only the protected device identity's subtree may be installed. |
| `/device` | Authoritative board identity and calibration; never cleared by OTA. |
| `/files/user` | Student work; never cleared or seeded over existing content. |
| `/state` | Settings, repository/profile state, selected app, migrations, boot/update health, and logs; migrate deliberately. |
| Legacy `/app.py`, `/hdwconfig.py`, `/settings.json`, `/repos.json`, `/logs` | Protected migration inputs; retain for compatibility and audit. |
| `/tmp` | Disposable update staging. |
| `/defaults/user` | Authenticated clean-provisioning seeds; copied only when creating a new user area. |

The updater must validate the complete plan and package hashes before changing
active files, keep the previous version committed during installation, retain
a display-independent recovery route, and commit the target version only after
a healthy boot. Interrupted operations must resume safely.

## Release channels and authentication

Release discovery is part of the compatibility boundary:

- `tdhoward/TartLab` is permanently reserved for `legacy-mp123`. Untouched
  v0.13 devices cannot distinguish profiles or ignore unrelated release
  assets.
- `tdhoward/TartLab-modern-releases` is exclusively for `lvgl-modern`.
- Never attach modern firmware or modern filesystem assets to a legacy release.
  The v0.13 updater counts every asset when checking free space and cannot
  flash firmware.

CI artifacts, tags, and drafts are candidates, not deployments. Protected
promotion workflows rebuild deterministic output, bind physical evidence, and
publish GitHub Artifact Attestations. Adult provisioning verifies modern
attestations before mutation. Devices enforce package hashes and profile,
channel, and firmware identities; they do not currently verify Sigstore
certificates themselves. See
[`tests/PHASE6_RELEASE_SECURITY.md`](tests/PHASE6_RELEASE_SECURITY.md).

Direct managed migration to modern supports stable TartLab v0.13 or newer on
the exact qualified legacy firmware and a recognized layout. Older or unknown
layouts require a private backup, authenticated clean provisioning, and
selective reviewed restore. See
[`profiles/lvgl-modern-migration.md`](profiles/lvgl-modern-migration.md).

On a migrated v0.13 device that loses power during the legacy download before
the durable update marker is written, use **Install latest corrective release**
from recovery. The v0.13 **Retry normal boot** action cannot remove that older
staging marker. v0.14 clears it after the corrective update reaches a healthy
boot, and clean v0.14 installations also include the corrected retry behavior.

## Build and dependency model

Host support is Python `>=3.10,<3.15` and Node.js 20 or newer. The minifier and
npm graph are locked because they affect release bytes. Builds start from clean
output directories and record source, toolchain, firmware, and vendor
identities.

The legacy release uses the generated 71-file PyDevices payload whose source
and packaged identities are pinned in `profiles/legacy-mp123.json`. The
historical checked-in tree is an audited fallback/input, not the normal release
payload. The modern firmware source graph and container toolchain are pinned in
`firmware/lvgl-modern/reference.lock.json`.

Use [`DEVELOPMENT.md`](DEVELOPMENT.md) for bootstrap, build, validation, and
physical-board commands. Generated `build/`, `dist/`, `release/`, virtual
environments, raw hardware evidence, private captures, and local
`settings.json` are not source inputs.

## Testing and evidence

Run the hardware-free suite and applicable static/build checks before hardware
work. Host and pinned-MicroPython tests do not emulate flash behavior, memory
limits, reset behavior, GPIO, display/touch, or Wi-Fi. Hardware-facing changes
need a focused physical smoke; a release needs the complete candidate-bound
physical gate. Tier definitions are in
[`tests/TEST_TIERS.md`](tests/TEST_TIERS.md).

The phase documents are audit records; the entry-point summaries above avoid
requiring them for routine work:

- Phases 1–4: legacy recovery, reproducible releases, platform abstraction,
  and the promoted minimal PyDevices identity.
- Phase 5: modern lifecycle, benchmarks, and rejection of the slower blocking
  PyDevices/displayif alternative.
- Phase 6: authenticated provisioning, update/recovery containment, release
  security, and publication of `modern-v0.14.8` and legacy `v0.15`.

The three Phase 5 evidence files are hash-bound by the firmware lock and retain
their checkpoint-era wording. Treat them as immutable historical evidence;
current release status comes from the profile JSON and this summary.

## Settled decisions

- `/device` owns local hardware configuration.
- Modern firmware is installed only through authenticated adult provisioning;
  browser OTA remains filesystem-only.
- GitHub Artifact Attestations authenticate CI-published assets; on-device
  Sigstore verification is deferred hardening.
- Legacy and modern release feeds remain isolated.
- v0.13 is the managed-modern direct-migration floor.
- The pinned `lvgl_micropython`/`lcd_bus` stack is the selected modern display
  implementation; TartLab owns its public direct-surface adapter.

## Modern touchscreen startup and IDE power behavior

This section records the approved implementation plan. The launcher, confined
local app chooser, and IDE inactivity controller are implemented, host tested,
and engineering-smoked on the T-Display-S3 Pro as of 2026-08-31, but are not
yet exact-candidate physically or release qualified.

### Profile boundary and startup policy

All boards using the `lvgl-modern` profile will use an LVGL touchscreen
launcher to select IDE or application mode. Modern startup must not require or
consult a physical IDE/app button. The launcher is a profile-wide feature, not
a board-specific opt-in, and its layout must adapt to every supported modern
display geometry.

The `legacy-mp123` profile retains its existing hold-the-button startup
behavior. Do not add LVGL, touchscreen-launcher, or modern backlight-policy
dependencies to the legacy adapter or change its `STARTUP_MODE=BUTTON`
semantics.

Modern startup follows this order:

1. Honor the early recovery gate. A required or explicitly requested recovery
   bypasses the touchscreen launcher.
2. Acquire LVGL UI ownership and show the touchscreen launcher.
3. Offer **Start IDE**, **Run selected app**, and **Choose app**.
4. Default to IDE after 10 seconds of no interaction so unattended startup and
   pending-update health checks can complete. Any launcher interaction cancels
   the countdown while the user is choosing a file.
5. Treat IDE/app selection as a per-boot choice. Persist the selected filename,
   but do not persist an automatic APP boot. A reset must always provide a
   touchscreen route back to the IDE if an application is faulty.
6. Once a route is chosen, let `src/main.py` perform the existing ownership
   transition and invoke the existing IDE or selected-app launcher.

Existing modern settings containing `STARTUP_MODE=BUTTON`, `IDE`, or `APP`
must not bypass the touchscreen launcher. `RECOVERY` remains authoritative.
The modern launcher timeout is IDE regardless of the previous runtime mode.
If touch is unavailable, the launcher must remain non-blocking and take the
same IDE timeout path. Working touch is nevertheless required to qualify a
board for the complete interactive modern product experience.

### Touchscreen launcher and local app selection

The launcher home screen shows the currently selected app and uses large touch
targets suitable for the smallest qualified display. **Choose app** opens a
scrollable, one-folder-at-a-time browser rooted at `/files/user`; it must not
start Wi-Fi or the HTTP/browser IDE. The browser:

- never navigates outside `/files/user`;
- lists folders and only launchable `.py` files;
- validates candidates with the same `validate_selected_app()` contract used
  by the browser IDE;
- checks that a candidate still exists before committing it;
- asks for confirmation before changing selected-app state; and
- writes through `save_selected_app()` so both interfaces share
  `/state/selected_app.json`.

For the first implementation, **Set as app** returns to the launcher home
screen and visibly updates the selected filename. Running the app remains a
separate deliberate touch. Cancellation or navigation must not change durable
state.

The UI workflow belongs in a modern-only module, while `ModernPlatform`
provides LVGL, pointer, geometry, and backlight operations. `src/main.py`
retains routing policy and must not import a board driver. Before APP mode, the
launcher must delete or detach its LVGL objects and allow the existing
controller transition to drain LVGL, disable pointer input, and acquire the
direct `RGB565_BE` surface. Before IDE mode, it must leave LVGL ownership clean
for the normal IDE status view.

The launcher itself never marks a boot healthy. Crossing into student code
clears the protected-startup recovery streak so repeated student-app failures
cannot force recovery, but does not commit a pending update. If student code
raises while loading, startup falls back to the IDE and a persistent red status
dot reports that the previous app run failed. The marker survives IDE health
and resets, then clears after a later APP run passes its health delay. IDE
health remains tied to the HTTP server becoming ready, and APP health remains
tied to the existing selected-app health delay. A pending update is therefore
committed only after the chosen destination proves healthy.

### Modern IDE automatic backlight dimming

Every modern IDE view will use a shared touch-inactivity backlight controller.
The initial defaults are:

- normal brightness: `1.0` (100 percent);
- dim brightness: `0.2` (20 percent); and
- idle delay: `180` seconds.

The inactivity clock starts when IDE mode becomes active. Touch activity
resets it. After the idle delay, the controller lowers the panel backlight to
the dim level; the first subsequent touch restores normal brightness and is
consumed so it cannot accidentally activate an on-screen control. Later
touches behave normally. Backlight changes must run in normal task context,
not an interrupt callback, and elapsed-time comparisons must use wrap-safe
MicroPython tick operations.

Leaving IDE mode cancels the inactivity task and restores normal brightness.
APP mode then owns its brightness behavior. Startup errors should also restore
normal brightness before displaying the error/recovery indication. The legacy
IDE keeps its existing brightness and physical-button behavior.

The controller should accept an optional modern-only settings object so a
future LVGL settings gear can edit behavior without replacing the controller:

```json
{
  "modern_ui": {
    "max_brightness": 1.0,
    "dim_brightness": 0.2,
    "auto_dim_seconds": 180
  }
}
```

These keys need not be written until a user changes a value. Missing or
invalid values use the defaults above. Brightness values are clamped to the
platform range, dim brightness cannot exceed maximum brightness, and an
`auto_dim_seconds` value of `0` disables automatic dimming. No settings gear is
part of the first implementation.

### Implementation and qualification status

The source implementation and Tier 1 host coverage are complete:

- every `lvgl_ui` platform uses the launcher while legacy startup retains its
  button path;
- the responsive home screen, IDE timeout, and touch-unavailable fallback are
  implemented;
- the confined local browser, confirmation, existence recheck, and shared
  selected-app state are implemented;
- the modern IDE inactivity controller and IDE, APP, error, and teardown hooks
  are implemented; and
- modern IDE mode no longer schedules the legacy button-polling task.

A non-qualifying physical engineering smoke on the qualified T-Display-S3 Pro
found and corrected three integration defects that the original host fakes did
not expose:

- the CST226 pointer adapter pre-rotated coordinates that LVGL rotated again,
  moving visible launcher taps outside their button hitboxes; the adapter now
  leaves raw portrait coordinates for LVGL's display rotation; and
- the pinned LVGL binding does not expose `indev_get_next()`, so the power
  controller now falls back to the platform's native input object when
  attaching its activity callback; and
- on this CST226SE fixture, the one-time disable-autosleep write stopped being
  effective after roughly one minute of inactivity. The T-Display-S3 Pro
  adapter now reasserts that setting every ten seconds while IDE mode owns the
  touch input. The policy stays outside the frozen firmware driver because the
  observed persistence behavior is not yet known to apply to every CST226
  variant or board.

The follow-up cleanup preserves the intended hardware boundary. Reusable LVGL
ownership, surface, view, and platform behavior remains in
`tartlabutils.modern`; T-Display-S3 Pro pins, buses, display/touch construction,
rotation, and the CST226SE keep-awake policy now live in
`boards/lilygo_t_display_s3_pro/runtime`. The Elecrow adapter follows the same
board-owned layout. Rejected PyDevices comparison adapters live under
`firmware/lvgl-modern/pydevices/runtime`, outside production `src`, and neither
generic modern platform class assumes the LilyGO GPIO 12 button. IDE teardown
also avoids
cancelling the task that is currently unwinding, so a serial interrupt does not
turn the diagnostic stop into `RuntimeError: can't cancel self`.

The rejected PyDevices comparison lock now canonicalizes line endings for its
reviewed text inputs while retaining raw byte hashes for firmware artifacts.
This removes checkout-dependent CRLF failures without weakening binary
identity checks.

Board support now has a dedicated package and filesystem contract. A modern
distribution explicitly names its boards and stages their payloads under
`board/<board_id>`; it no longer discovers production board modules merely
because they happen to be under `src/lib`. The release publishes one signed
`board-support.tar` containing the compatible board subtrees. Adult
provisioning, normal OTA, and recovery download and validate that complete
archive but apply only the subtree matching protected `/device/board.json`.
Repository state is cross-checked against that protected identity, `/board` is
the only writable target for this selection policy, and a missing or conflicting
subtree rejects the update before installation. This keeps one release/package
flow while avoiding persistent off-target board shims on student devices.
Authenticated per-board expanded-size values keep extraction-space checks
specific to the selected board even though download-space checks cover the
whole archive.

The first bridge from a selection-unaware modern updater must keep the board
archive limited to the already-qualified default board. Stable multi-board
archives wait until the selection-aware updater and recovery client are the
supported baseline. The detailed source, provisioning, OTA, recovery, and
new-board rules are maintained in `BOARD_SUPPORT.md`.

The refactored production modules were then staged onto the COM3 engineering
fixture without replacing its qualified firmware. The device timed out through
the launcher and reached `HEALTHY mode=IDE`. Deliberately entering the serial
diagnostic REPL while that IDE task was running left `/state/boot.json` healthy
in IDE mode with zero consecutive failures, rather than recording the previous
`can't cancel self` exception. A normal reset afterward again reached
`HEALTHY mode=IDE`. This is targeted working-tree evidence, not candidate
qualification.

The later board-package layout was also exercised directly on COM3. Protected
`/device/board.json` selected `/board/lilygo_t_display_s3_pro`; after the new
platform boundary and board payload were staged, the obsolete copies under
`/lib/tartlabutils` and `/configs` were removed. An uninterrupted reset still
reached `HEALTHY mode=IDE`, demonstrating that startup used only the dedicated
board-owned subtree. Repeated diagnostic REPL entry during staging temporarily
raised the boot-failure counter, so recovery retry cleared that engineering
artifact before the final uninterrupted observation. This remains
working-tree smoke evidence, not candidate qualification.

A subsequent packaging review closed two additional fail-closed gaps. The
selected board runtime now precedes the release root and `/files/user` on the
module search path, preventing student code from shadowing the module imported
by protected `/device/hdwconfig.py`. Normal OTA and recovery also reject a
selected board package whose authenticated per-board expanded-size entry is
missing or malformed instead of falling back to the complete archive's
compressed size.

The corrected modules were staged on COM3 as another non-qualifying
working-tree smoke. Before the fix, the selected board path was observed after
`/files/user`; afterward it was index 1 while `/files/user` was index 3, and the
loaded selector module still came only from
`/board/lilygo_t_display_s3_pro`. The native probe reported the 480 by 222
ST7796/CST226 platform in UI ownership with no pending transfer, and the
touch-controller identity probe completed. A fresh 100-cycle renderer probe
could not reopen the native USB endpoint after the preceding diagnostic, so it
did not produce a new result and the earlier working-tree 100-cycle observation
was not reused as a current pass. Repeated diagnostic interruptions again
tripped the expected recovery threshold; recovery retry cleared that artifact,
and an uninterrupted launcher timeout ended at `HEALTHY mode=IDE`. None of
these observations are exact-candidate or release qualification.

Deferred guidance for updating the existing lvgl-micropython contribution is
preserved in [CST226 upstream recommendations](CST226_UPSTREAM_RECOMMENDATIONS.md).
The upstream PR is not a dependency of the TartLab local fix or qualification
sequence.

With these corrections installed, physical taps selected APP mode, navigated a
nested chooser folder, confirmed and ran the selected app, and reached healthy
APP state. The device-side power smoke observed timeout dimming, a consumed
first wake touch, a later delivered click, repeated dim/wake behavior, and
normal-brightness teardown. An unattended reset returned through the launcher
to a healthy IDE. A later real-IDE test remained idle for more than 65 seconds
after dimming and then woke on the first touch. That final test used the
qualified `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`
firmware and an application-only working-tree candidate; the frozen driver and
firmware lock were unchanged. This was not a clean tagged candidate, attested
artifact, or release qualification record.

The feature is not complete or release-qualified. The remaining sequence is:

1. Run the clean Tier 0 build/static checks and Tier 2 pinned-MicroPython
   compatibility checks for the exact candidate, including the generated
   distribution rather than only the source tree.
2. Build an exact modern release candidate and record its tag/commit,
   `checksums.json`, filesystem inventory, firmware identity, and selected
   board set. A local distribution build is not a candidate or deployment.
3. Run the focused touchscreen/backlight smoke in
   `tests/MODERN_TOUCHSCREEN_QUALIFICATION.md` on the qualified T-Display-S3
   Pro and on every additional board deliberately included in that candidate.
   The Elecrow DLE06235B remains `bringup` and is not a supported-board claim.
4. Correct any hardware findings, rebuild, and repeat the smoke against the
   replacement candidate; evidence from an earlier build cannot qualify it.
5. Run the complete candidate-bound modern provisioning, OTA, recovery,
   interruption, protected-state, feed-isolation, and future-update gates.
6. Bind sanitized evidence to the exact candidate and promote only through the
   protected modern release workflow.

### Required verification

Automated coverage must prove modern IDE and APP selection, the IDE timeout,
touch-unavailable fallback, recovery precedence, confined file navigation,
filename validation, confirmation/cancellation behavior, selected-app state
updates, and cleanup before LVGL-to-direct ownership transfer. Backlight tests
must cover timeout, activity postponement, wake-touch consumption, long-idle
touch keep-awake, settings validation, APP handoff, error handling, and
repeated task teardown. Legacy tests must prove that held-button startup and
brightness behavior are unchanged.

The Tier 1 suite now covers those behaviors. Tier 2 and exact-candidate CI must
still pass before the physical result can be treated as release evidence.

For each supported modern board, physical evidence must include an upright and
usable launcher, file selection without a browser, a visibly distinctive app
boot, `HEALTHY mode=APP` after the existing delay, reset back to the launcher,
a subsequent `HEALTHY mode=IDE`, automatic dimming and touch wake, and repeated
IDE/direct-surface ownership cycles without corruption or a crash. Do not mark
the feature complete or publish it until those results are bound to the exact
candidate and firmware identity.

## Remaining work

The legacy `v0.15` release milestone is complete. Its runtime was qualified
from v0.14, and the exact final tagged candidate was installed and verified
after candidate-content comparison. It was promoted through the protected
`legacy-release` environment, published only to the legacy feed, and audited
after publication for signed provenance, feed isolation, recovery continuity,
and future OTA availability.

The immediate engineering milestone is the modern touchscreen/backlight
qualification sequence above. No additional first-release UI feature is
currently planned; a settings gear remains explicitly deferred. Hardware
findings may still require source changes, and the feature must not be called
complete until new evidence is bound to its exact candidate. The historical
`modern-v0.14.8` evidence predates this feature and does not qualify it.

The owner still needs to decide:

1. The minimum supported board set for each release line.
2. The support lifetime or retirement rule for the exact legacy firmware.
3. Whether board adapters remain TartLab-maintained or move upstream.
4. The explicit flash-space margin for staging, recovery, and rollback.

Non-blocking cleanup: record platform capabilities in secret-safe diagnostics,
move student examples from direct legacy driver imports to stable TartLab APIs,
and continue removing stale historical status language when behavior changes.

## Guardrails for future changes

- Do not claim legacy compatibility without physical testing on the exact
  qualified MicroPython image and confirmation of octal PSRAM.
- Do not make LVGL or modern native modules mandatory for the legacy profile.
- Do not overwrite local selectors, settings, logs, selected-app state,
  recovery state, or student files with repository defaults.
- Do not advance the installed version before healthy boot.
- Do not change package ownership, clearing, or migration behavior without
  inspecting archive paths and running interruption/recovery tests.
- Do not track upstream `main`, add unverified dependencies, or remove vendor
  licenses/provenance.
- Do not claim graphics improvement without reporting geometry, clocks,
  buffering, render/transfer/total timing, and firmware identity.
- Do not publish to either profile's release feed without its protected,
  candidate-bound physical gate.
