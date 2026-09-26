# TartLab project context

This file is the short architectural brief for contributors and AI agents. Use
[`README.md`](README.md) for product usage, [`DEVELOPMENT.md`](DEVELOPMENT.md)
for commands, [`RELEASE_POLICY.md`](RELEASE_POLICY.md) for release scope and
versioning, and the documents under [`tests`](tests) for qualification evidence.
The [documentation index](docs/README.md) maps the repository's guides;
[project status and history](docs/projects/README.md) live under `docs/projects`.

## Product and current status

TartLab is a browser-based MicroPython IDE hosted by a Wi-Fi microcontroller.
It is designed for classrooms: students use a browser to edit, save, and run
programs without installing drivers, desktop IDEs, or firmware tools. The
current qualified modern board set is recorded in the [`boards`](boards)
catalog and the candidate-bound records in
[`tests/PHASE6_MODERN_QUALIFICATION.md`](tests/PHASE6_MODERN_QUALIFICATION.md).

The modern platform is still in early alpha and has no field-deployed devices.
Its published multi-board releases bind the explicitly selected, qualified board
set. The release plan declares the supported installed update sources; lab
fixtures alone do not create a rollout compatibility obligation.

Two runtime profiles are maintained:

| Profile | Runtime and release feed | Status |
| --- | --- | --- |
| `legacy-mp123` | Exact MicroPython 1.23.0 octal-SPIRAM image; `tdhoward/TartLab`; legacy `manifest.json` | `v0.15` is published and physically qualified on the exact MicroPython 1.23.0 image. |
| `lvgl-modern` | Pinned MicroPython 1.27.0/LVGL image; `tdhoward/TartLab-modern-releases`; `modern-manifest.json` | The two-board-qualified `modern-v0.16.0` alpha is published and its signed qualification baseline is pinned; modern has no field deployments. Firmware provisioning is an adult-admin operation. |

The authoritative runtime-profile identities and status live in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json) and
[`profiles/lvgl-modern.json`](profiles/lvgl-modern.json). Modern per-board
identity, capabilities, firmware binding, and lifecycle state live under
[`boards`](boards); see [`BOARD_SUPPORT.md`](BOARD_SUPPORT.md).

Experimental non-touch device support is scoped in
[Button navigation](docs/projects/active/button-navigation.md). Prioritize
two-button launcher, app chooser, settings, and browser IDE workflows, using the
non-Pro LilyGO T-Display-S3 as the initial bring-up target. Example-app ports,
including Racer, are optional. The non-Pro port now has declarative I80/pin
configuration, optional touch, named button events, and LVGL focus navigation;
its validation and outstanding qualification are recorded in
[`DEVELOPMENT_RESULTS.md`](boards/lilygo_t_display_s3/DEVELOPMENT_RESULTS.md).
This work does not add a qualified board.

## Non-negotiable constraints

- Preserve boot, IDE, recovery, and future OTA access for deployed devices.
- A normal update is one user action directly to the latest compatible stable
  release. Internal migrations may restart and resume, but users must not hunt
  for intermediate releases.
- Keep one public TartLab version for platform, browser IDE, and apps. Testing
  follows changed behavior, independently of major/minor/patch numbering.
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
firmware alias for manifest-format compatibility. It is not a required rollout
bridge because no field device depends on the schema-1 modern release. Adult
provisioning requires an explicit qualified board ID and records it under
protected `/device`; new ports proceed independently through `bringup`,
`candidate`, and `qualified` states.

The modern profile uses one native DMA-capable panel transport with exclusive
ownership between:

- LVGL UI mode for the IDE and normal controls; and
- a direct `RGB565_BE` dirty-rectangle surface for games and animation.

Mode changes must drain pending transfers, pause the old renderer, transfer
ownership, and redraw or invalidate the destination. Never let LVGL and the
direct surface drive the panel concurrently or expose private upstream driver
fields as the app API.

Optional panel acceleration remains behind this same surface boundary. Common
canvas operations must retain software-correct behavior on every board; a
declarative board payload may select a reusable accelerator adapter where the
hardware supports one. Shared code must compose native panel, configured
surface, and canvas rotations before advertising logical axes, preserve
framebuffer/display coherence across wrapped addressing, serialize commands
with DMA ownership, and restore neutral panel state before returning to LVGL.

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

Routine app/browser releases retain a qualified platform baseline and reuse
its applicable board-bound evidence. Platform changes require fresh tests for
affected claims; new boards and changes to firmware or installation/update
behavior require full relevant physical qualification. The baseline includes
shared runtime, startup, device-side IDE services, updater, recovery, board
configuration, and installation contracts as well as firmware.

[`RELEASE_POLICY.md`](RELEASE_POLICY.md) defines these boundaries and the
single-version convention. [`RELEASE_TOOLING.md`](RELEASE_TOOLING.md) documents
signed baseline capture, distribution assembly, computed change reports, and
schema-3 evidence validation during protected promotion. The release plan pins
the authenticated `modern-v0.16.0` baseline and remains in platform mode.
Earlier releases lack the signed metadata needed for automatic reuse.

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
need fresh physical checks for affected claims and boards. Modern releases
need complete candidate-bound evidence coverage, combining fresh results with
justified baseline reuse where applicable; an app/browser release need not
repeat an unchanged platform's entire physical campaign. Test selection is in
[`tests/TEST_TIERS.md`](tests/TEST_TIERS.md).

The phase documents are audit records; the entry-point summaries above avoid
requiring them for routine work:

- Phases 1–4: legacy recovery, reproducible releases, platform abstraction,
  and the promoted minimal PyDevices identity.
- Phase 5: modern lifecycle, benchmarks, and rejection of the slower blocking
  PyDevices/displayif alternative.
- Phase 6: authenticated provisioning, update/recovery containment, release
  security, legacy `v0.15`, and modern publications through the signed
  `modern-v0.16.0` qualification baseline.

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

## Modern startup and IDE power behavior

The touchscreen launcher, local app chooser, settings, and IDE dim/wake
behavior shipped in the qualified two-board modern release. The original
[project record](docs/projects/completed/touchscreen-startup.md) retains the
design and engineering history;
[current qualification](tests/PHASE6_MODERN_QUALIFICATION.md) records release
coverage. Use the [focused checklist](tests/MODERN_TOUCHSCREEN_QUALIFICATION.md)
when changing these behaviors. Experimental
[button navigation](docs/projects/active/button-navigation.md) extends the
same UI to non-touch boards and has its own unfinished qualification.

## Release milestones and open decisions

The legacy `v0.15` release milestone is complete. Its runtime was qualified
from v0.14, and the exact final tagged candidate was installed and verified
after candidate-content comparison. It was promoted through the protected
`legacy-release` environment, published only to the legacy feed, and audited
after publication for signed provenance, feed isolation, recovery continuity,
and future OTA availability.

Modern `modern-v0.16.0` qualification and promotion are recorded in
[`tests/PHASE6_MODERN_QUALIFICATION.md`](tests/PHASE6_MODERN_QUALIFICATION.md).
The original touchscreen project is complete; use its focused checklist for
affected future changes. The historical `modern-v0.14.8` evidence cannot
establish claims for features introduced after it.

Automated qualification reuse is implemented and the first signed baseline was
established by `modern-v0.16.0`. Routine app/browser releases can reuse applicable
platform evidence while retaining one public TartLab version. Each new candidate
still computes its own changed claims and required checks; the release plan is
currently in platform mode. The classifier remains conservative for shared
platform changes and representative-board coverage. See
[`RELEASE_TOOLING.md`](RELEASE_TOOLING.md).

Current unfinished projects and their next gates are maintained in the
[project index](docs/projects/README.md#active-work), including Racer, button
navigation, Grid Puzzle, and CrowPanel 7-inch bring-up.

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
  candidate-bound qualification evidence. Modern evidence reuse must satisfy
  the release policy; a version bump or app/browser label is not justification.
