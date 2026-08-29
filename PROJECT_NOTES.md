# TartLab project context

This file is the short architectural brief for contributors and AI agents. Use
[`README.md`](README.md) for product usage, [`DEVELOPMENT.md`](DEVELOPMENT.md)
for commands, and the documents under [`tests`](tests) for qualification
evidence.

## Product and current status

TartLab is a browser-based MicroPython IDE hosted by a Wi-Fi microcontroller.
It is designed for classrooms: students use a browser to edit, save, and run
programs without installing drivers, desktop IDEs, or firmware tools. The
qualified board is currently the LilyGO T-Display-S3 Pro PCB v1.1.

Two runtime profiles are maintained:

| Profile | Runtime and release feed | Status |
| --- | --- | --- |
| `legacy-mp123` | Exact MicroPython 1.23.0 octal-SPIRAM image; `tdhoward/TartLab`; legacy `manifest.json` | `v0.14` is published and physically qualified on the exact MicroPython 1.23.0 image. |
| `lvgl-modern` | Pinned MicroPython 1.27.0/LVGL image; `tdhoward/TartLab-modern-releases`; `modern-manifest.json` | `modern-v0.14.8` is published and physically qualified for the T-Display-S3 Pro. Installation or migration is an adult-admin operation. |

The authoritative identities and status live in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json) and
[`profiles/lvgl-modern.json`](profiles/lvgl-modern.json).

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
authoritative after migration. OTA packages may replace board-support modules
under `/configs`, but must not overwrite the local selector or calibration.

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
  security, and publication of `modern-v0.14.8` and legacy `v0.14`.

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

## Remaining work

The legacy `v0.14` release milestone is complete. The exact tagged candidate
was qualified from untouched v0.13, promoted through the protected
`legacy-release` environment, published only to the legacy feed, and audited
after publication for signed provenance, feed isolation, recovery continuity,
and future OTA availability.

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
