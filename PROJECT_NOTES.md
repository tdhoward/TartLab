# TartLab Project Notes

> Repository review date: 2026-08-03
> Primary repository: <https://github.com/tdhoward/TartLab>
> Development environment and hardware-tooling setup: `DEVELOPMENT.md`

## Purpose of this document

This file gives an AI coding agent the project context needed to make safe architectural and implementation decisions. It describes the intended product, the installed-device constraints, the present update and hardware-integration design, the risks found during repository review, and a recommended sequence of work.

The most important rule is that a change is not successful merely because it works on a newly flashed development board. TartLab already has deployed devices, and preserving their ability to boot, enter the IDE, and receive later OTA updates is a primary requirement.

## Product vision

TartLab is a kid-friendly, web-based MicroPython IDE hosted directly by a microcontroller device. The target device:

- Has a screen, preferably with touch input.
- Can run MicroPython.
- Can create a temporary Wi-Fi access point.
- Serves the TartLab IDE to a browser without requiring a cloud service.
- Lets a student create, save, and run a MicroPython application on the device itself.
- Can switch between IDE mode and running the student's application.

The LilyGO T-Display-S3 Pro is the primary development and test device so far, but TartLab must not become inseparably tied to it.

## Non-negotiable product constraints

### 1. Preserve OTA recovery and update capability

TartLab updates application files in the MicroPython filesystem from GitHub release assets. The updater does not replace the MicroPython firmware.

Every release must preserve a reliable path to:

1. Boot the device.
2. Enter TartLab IDE or recovery mode.
3. Connect to a network when required.
4. Check GitHub releases.
5. Download, verify, and install a later corrective release.

Do not make an OTA change that can permanently strand a deployed device merely because a local USB reflash would repair it.

#### Single-action direct-to-latest update policy

Normal TartLab updates must remain a single user-initiated operation. The updater
selects the latest stable (non-alpha/non-prerelease) GitHub release; users must
not be required to install or select intermediate TartLab releases before they
can reach it.

This is a user-experience rule, not a prohibition on ordered migrations inside
the update. A single update may run multiple internal schema or filesystem
migration steps and may resume those steps across automatic restarts. Those
steps must remain part of the same update operation and must not require the
user to repeat “Check for updates.”

Consequences:

- Every stable release must provide a tested direct path from every deployed
  version/layout inside the supported compatibility window.
- The latest release must retain an entry path that the oldest supported
  deployed updater can understand. If a richer updater or manifest is needed,
  install a small compatible bootstrap/recovery stage first and let it finish
  the same update automatically.
- Ship required migrations with the target release as an ordered, idempotent,
  resumable plan. Record migration progress separately from the user-visible
  installed version.
- Download and validate the complete migration plan before modifying active
  files. Commit the target version only after every internal stage has finished
  and the final target release passes boot health.
- If a starting version is outside the supported compatibility window, reject
  it before modification and provide a recovery or administrator path. Never
  partially update it or instruct a classroom user to hunt down intermediate
  GitHub releases.

### 2. Continue supporting deployed MicroPython 1.23.0 devices

Existing TartLab deployments use the generic ESP32-S3 MicroPython 1.23.0 image `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`. This is the octal-SPIRAM build required to use the T-Display-S3/T-Display-S3 Pro's octal PSRAM. New TartLab releases must continue to run on that exact legacy baseline until an explicit migration policy says otherwise; compatibility with another 1.23.0 build or a newer generic build is not a substitute.

Consequences:

- Do not require LVGL, frozen modules, native display buses, or newly added MicroPython APIs in the legacy runtime path.
- New dependencies must be tested on actual hardware running `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`, not only CPython or a recent MicroPython build.
- Syntax compatibility is insufficient; imports, memory use, filesystem use, networking, soft resets, and display/touch behavior must also be tested.
- The legacy-compatible path should remain a first-class build profile rather than an accidental fallback.

### 3. No kid-facing firmware or driver workflow

Students should not need to:

- Install serial drivers.
- Compile MicroPython.
- Build LVGL bindings.
- Flash firmware.
- Use command-line deployment tools.

A teacher, developer, manufacturer, or administrator may perform one-time device provisioning, but normal classroom operation and TartLab updates must remain browser/device based.

### 4. Support multiple hardware targets

Hardware-specific details must remain outside the core IDE and student application model. TartLab should consume a small, stable hardware contract that provides at least:

- Display object and dimensions.
- Touch or pointer input when available.
- The button or other mechanism used to select IDE mode.
- Optional capabilities such as backlight, battery status, audio, storage, and extra controls.

A board may implement this contract through pure-Python PyDisplay drivers on generic firmware, through native/frozen modules on custom firmware, or through another compatible backend.

### 5. Minimize device filesystem usage

Microcontroller filesystems are small. Do not copy an entire upstream development repository to a device. Exclude tests, demos, documentation, development tooling, unused board definitions, unused drivers, optional fonts, screenshots, and other non-runtime content.

The exact runtime payload must be generated reproducibly rather than maintained as an unexplained hand-edited snapshot.

## Current TartLab architecture observed in the repository

### Startup and mode selection

`src/main.py` adds only TartLab's core `/device`, `/lib`, root, and user-file
directories to `sys.path`. It obtains display and IDE-button behavior through
`tartlabutils.platform`, selects IDE or APP mode from settings and platform
input, and launches the selected user module through
`tartlabutils.launcher`. Its injectable mode runners support headless startup
tests without changing normal device startup.

The legacy platform adapter, rather than core startup, owns the historical
embedded PyDevices paths (`bus_drv`, `display_drv`, `touch_drv`, and `add_ons`).
The IDE also consumes the platform boundary for status rendering, WLAN/AP
configuration, hostname, delay, button input, and brightness. Some bundled
student examples still import `hdwconfig` and PyDevices display APIs directly;
the stable TartLab boundary is currently a core startup/IDE contract, not yet a
replacement student graphics API.

### Hardware selection

`src/hdwconfig.py` is the clean-provisioning default and imports a
board-specific module from `/configs`. It currently selects
`t_display_s3_pro`. After migration, `/device/hdwconfig.py` is the authoritative
device-local selector.

The intended distinction is useful:

- A local selector identifies the physical board.
- Update-managed board support modules provide the implementation.

The ownership boundary is now enforced. Clean provisioning supplies a default
`hdwconfig.py`, while OTA archives exclude `/hdwconfig.py`. Layout migration
copies the detected local selector to `/device/hdwconfig.py` only when the
destination is absent, and `/device` is searched first and remains protected.
Board support modules under `/configs` remain update-managed and may be replaced
with `clear_first: true`; local identity and calibration under `/device` may
not be cleared or overwritten.

### Deployed filesystem evidence and persistent state

`_example_installation` was the original private deployed-style filesystem
capture used to establish the migration requirements. The authoritative tracked
baseline is now `tests/fixtures/legacy_mp123`: a sanitized v0.13 layout with
synthetic credentials, board revision, exact firmware hash, capture method,
filesystem capacity/free values, deterministic inventory, and
`release_gate_ready: true`. The ignored private capture and hardware evidence
may contain protected state and must not be treated as a distributable fixture
or as a claim that it still matches the evolving source tree.

The captured `settings.json` confirms that it is device-local persistent state, not a release default. In addition to startup behavior, hostname, and access-point identity, it stores Wi-Fi SSIDs and passwords in plaintext parallel arrays. Device captures, backups, and diagnostic bundles must therefore be treated as sensitive: exclude or sanitize real settings before committing a fixture, redact credentials before sharing, and use synthetic credentials in tests. Do not quote real SSIDs, passwords, or generated access-point names in documentation or test output.

The capture, current source, and package manifest establish these ownership
classes and compatibility boundaries:

- `/boot.py` is an update-managed early recovery gate. It evaluates durable
  update and boot-health state before normal startup and can enter the
  display-independent recovery path. Migration/install logic preserves the
  working gate at the compatibility boundary where required.
- `/main.py` is TartLab's update-managed entry point and is included in the `rootfiles` package.
- `/app.py` is protected legacy state. Current startup uses a fixed launcher and
  the validated `/state/selected_app.json` value; migration preserves the
  historical selection and OTA archives do not overwrite `/app.py`.
- `/hdwconfig.py` is protected legacy hardware selection. The authoritative
  migrated selector is `/device/hdwconfig.py`, which is also protected; clean
  distributions retain a default only for first provisioning.
- `/ide`, `/configs`, `/lib/ahttpserver`, `/lib/pydevices`, and `/lib/tartlabutils` are update-managed directories that are deleted before their replacement packages are extracted.
- `/files/help` and `/files/assets` are update-managed. `/files/user` contains student work and must be preserved; the capture contains both the seeded `hello.py` and the student's selected `testris.py`.
- `/state` is authoritative persistent state for settings, repositories,
  selected application, update/boot health, migrations, and rolling logs.
  Legacy `/settings.json`, `/repos.json`, and `/logs` remain protected migration
  inputs. Settings contain secrets.
- `/device` is authoritative local hardware identity/configuration and is never
  update-cleared.
- `/tmp` is disposable update staging space and may be recursively cleared by the updater.

### Observed boot logs

The capture contains the full five-file retention window, `000000.log` through `000004.log`. In order, the logs show:

1. Initial startup without `settings.json`, followed by IDE selection. The IDE subsequently creates default settings.
2. Two more IDE selections.
3. One APP selection. The captured generated `/app.py` currently imports the student's `testris.py`, although the log itself does not record which app was selected at that boot.
4. A final IDE selection.

No captured log contains a traceback or explicit error. This is encouraging but is not a boot-health result: `Starting IDE` is written before `import ide` and before the network/server is ready, while `Starting APP` is written before `import app`. There is no later success marker. The files also lack timestamps, reset/wake causes, firmware identity, PSRAM or heap information, filesystem free space, update-in-progress state, and a boot identifier that survives log rotation.

In the captured v0.13 runtime, `main.py` wrote `System startup` before importing
hardware configuration, so those historical logs identify only the last
explicit checkpoint reached. Current startup records structured diagnostics,
catches and logs startup exceptions where possible, marks boot failures, and
routes failures through the early recovery gate. Preserve both rolling logs and
serial output when diagnosing boot loops: logging can still fail before normal
libraries are usable, while `/boot.py` and `/recovery` deliberately avoid that
dependency.

### Distribution and release tooling

`makedist.py`:

- Copies selected source trees into `dist`.
- Optionally minifies Python files.
- Builds the web UI with npm.
- Gzips larger static web assets.

`release.py`:

- Uses `tartlab_packages.json` to create tar archives.
- Computes SHA-256 hashes.
- Creates a release manifest consumed by the device updater.

Useful properties already exist: the device downloads all listed packages, verifies package hashes, installs the updater package last, and records the new version only after package installation completes.

The current update selector goes directly to the latest non-alpha GitHub
release; it has no user-visible version-by-version progression. This matches the
intended product experience, but it also means every newly published stable
release inherits the compatibility obligation described above. In particular,
an untouched v0.13 device begins with the v0.13 updater, so the latest stable
release must preserve a bootstrap path that updater can consume.

Historical v0.13 weaknesses:

The following findings describe the deployed v0.13 updater and original build
path that motivated Phases 1 and 2. They are retained as migration context, not
as claims about the current implementation; the phase-status sections below
record the implemented protections and remaining release decisions.

- Build and release scripts are interactive, which makes reproducible CI releases difficult.
- `makedist.py` directly invokes `npm.cmd`, making the build Windows-specific.
- The default installed version is hard-coded in `main.py` as `v0.13` when `repos.json` is first created.
- The manifest has no schema version, runtime compatibility declaration, package dependency information, preservation rules, or rollback metadata.
- Installation is in-place and sequential. For `clear_first` packages, the old directory is deleted before the replacement is extracted.
- `untar()` catches extraction exceptions without returning failure or re-raising them. `update_folder()` can consequently log `Success`, and the updater can advance `repos.json`, after an incomplete extraction.
- The `rootfiles` package includes the device-generated `/app.py` selection and device-specific `/hdwconfig.py`, so an otherwise successful OTA can silently reset local behavior.
- A reset, power loss, write failure, or extraction error can leave a partially replaced installation with no automatic rollback.
- Free-space checking is based mainly on release asset sizes and a small fixed buffer; it does not model all staging, extraction, backup, and filesystem-overhead requirements.
- The captured installation matches the local `dist`, but both omit `test.qoi`, `display_qoi.py`, and `qoi_reader.py` that are present in `src`. Without generated build metadata, it is not possible to distinguish a deliberately older payload from a stale build directory.

### Embedded PyDevices snapshot

TartLab currently contains a partial, modified copy under `src/lib/pydevices`. The script `distill_pydevices.py` was created to generate this payload from a neighboring repository named `mpdisplay`.

The script is now tied to an older upstream layout. It expects paths such as:

- `board_configs/busdisplay/...`
- `drivers/bus`
- `drivers/display`
- `drivers/touch`
- `src/add_ons`

It also flattens or renames parts of that structure into TartLab-specific import directories. This explains why a current PyDisplay checkout cannot simply replace the embedded copy.

The deployed capture quantifies the pruning opportunity: `/lib/pydevices` contains 145 files and 729,986 bytes, about 65% of all captured file content. Its `add_ons` subtree alone is 427,540 bytes. It includes 20 board configurations, 14 display drivers, 6 touch drivers, many large font modules, and desktop-only display backends. A target-specific allowlist should remove unused boards, buses, displays, touch controllers, fonts, add-ons, and desktop backends, with hardware tests proving that every removed module is unnecessary.

## Current PyDevices/PyDisplay direction

The upstream project has been reorganized into multiple repositories:

- `PyDevices/pydisplay`: top-level integration, examples, documentation, and display utility modules.
- `PyDevices/pydevices`: canonical display, event, timer, hardware-driver, and board-configuration packages. The former `PyDevices/micropython-hardware` URL redirects here.
- `PyDevices/pygraphics`: graphics functionality now maintained as a sister package.
- `PyDevices/palettes`: color palettes now maintained as a separate package.
- `PyDevices/lv_micropython_cmod` and `PyDevices/lv_bindings`: LVGL integration for custom MicroPython builds.
- `PyDevices/cmods`: optional workspace and scripts for building MicroPython with multiple native user C modules.

Relevant upstream repositories:

- <https://github.com/PyDevices/pydisplay>
- <https://github.com/PyDevices/pydevices>
- <https://github.com/PyDevices/pygraphics>
- <https://github.com/PyDevices/palettes>
- <https://github.com/PyDevices/lv_micropython_cmod>
- <https://github.com/PyDevices/lv_bindings>
- <https://github.com/PyDevices/cmods>

PyDisplay explicitly describes itself as alpha quality with rapidly evolving APIs and documentation. Therefore TartLab should not automatically follow upstream `main` on deployed devices. Upgrades should be deliberate, pinned, tested changes.

PyDisplay's architecture is compatible with TartLab's broad goal: application code can use a stable display/input abstraction while board configuration selects a backend. It can support ordinary Python display drivers and can also participate in LVGL-enabled firmware. That does not mean the same collection of files can be dropped onto every firmware version without testing.

## Required compatibility model

TartLab should explicitly maintain two runtime profiles during migration.

### Profile A: Legacy generic firmware

Target:

- Existing installations running `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` (MicroPython 1.23.0 with octal PSRAM).
- Pure-Python display/touch/bus support.
- OTA-updatable filesystem payload only.

Rules:

- Must not import LVGL or native modules unconditionally.
- Must include every required pure-Python dependency in the TartLab release.
- Must stay within the storage and RAM budget of deployed boards.
- Must remain capable of running the updater and recovery path even when the normal display/application layer fails.

### Profile B: Managed modern firmware

Target:

- A recent, explicitly pinned MicroPython version.
- LVGL plus a DMA-capable native display bus compiled into firmware.
- One native panel transport shared by an LVGL UI renderer and a direct
  framebuffer/dirty-rectangle renderer for games.
- Native framebuffer operations, reusable transfer buffers, and asynchronous
  completion where the target port supports them.

Rules:

- Firmware builds must be reproducible and versioned.
- TartLab must detect capabilities rather than assume them from a board name alone.
- The filesystem application package should still be independently OTA-updatable.
- A firmware-specific TartLab package may be produced when unavoidable, but common application logic should remain shared.
- LVGL must not be the only way to draw. Games must have a supported direct
  surface API that does not require Python per-pixel loops or a full-screen
  refresh after every small change.
- LVGL and the direct renderer must not drive the panel concurrently. TartLab
  owns mode transitions, waits for pending DMA, and restores or invalidates the UI
  when returning from a game.
- No application may depend directly on private binding or display-driver
  attributes. Firmware-specific details belong behind the TartLab platform
  boundary.

### Critical migration limitation

The current TartLab updater changes filesystem files only. It cannot convert an existing generic MicroPython 1.23.0 octal-SPIRAM device into an LVGL-enabled custom firmware device.

Migrating deployed devices to Profile B therefore requires a separate adult/admin provisioning mechanism, for example:

- A one-time USB/web-flasher procedure.
- A manufacturer-provisioned firmware image for new units.
- A future bootloader/partition-level firmware OTA design, if the hardware and risk model justify it.

Do not represent a PyDisplay package update as a firmware migration.

## Recommended target architecture

### 1. Introduce a TartLab-owned hardware API boundary

Create a small stable module, for example `tartlab_hal` or `tartlab_platform`, that is the only hardware-facing API imported by core TartLab code.

A possible contract could expose:

```python
platform.display
platform.ui
platform.surface
platform.input
platform.ide_button_pin
platform.capabilities
platform.enter_ui()
platform.enter_game()
platform.deinit()
```

Keep the contract deliberately small. Board-specific code may import PyDisplay internals, but the IDE, updater UI, and student app launcher should not.

This isolates TartLab from future PyDisplay path and API changes and makes legacy and LVGL backends selectable behind the same interface.

### 2. Separate rendering policy from the native panel transport

The managed modern profile is deliberately dual-mode rather than LVGL-only:

- **UI mode:** LVGL owns its partial draw buffers, task handler, input devices,
  invalidation, and display flush callbacks. Use this mode for the TartLab IDE,
  settings, menus, text, controls, and UI-oriented student applications.
- **Game mode:** a TartLab direct surface owns the panel and exposes a small,
  stable `blit_rect`, `fill_rect`, `wait`, width, and height contract. Use this
  mode for sprite, scrolling, framebuffer, and other frame-paced workloads.

Both modes must use the same native display transport. A mode switch must stop
or pause the current renderer, finish outstanding transfers, transfer bus
ownership, and perform the redraw needed by the destination renderer. Do not
initialize two independent panel drivers or allow an LVGL refresh callback to
race a game transfer.

On the T-Display-S3 Pro, a 480 x 222 RGB565 frame is 213,120 bytes. At the
configured 60 MHz SPI clock, the wire alone needs approximately 28.4 ms for a
full frame, for an absolute ceiling of about 35 full-screen frames per second
before command, scheduling, rendering, or memory overhead. Consequently the
modern graphics design must prioritize:

1. Dirty rectangles and partial refresh.
2. DMA and overlap between transfer and rendering.
3. Reusable buffers and allocation-free steady-state frame loops.
4. Native framebuffer/LVGL drawing and preconverted RGB565 assets.
5. Avoiding runtime byte swaps, scaling, and color conversion where possible.

The initial Phase 5 reference should use
`lvgl-micropython/lvgl_micropython`, whose `lcd_bus` path exposes DMA-capable
buffer allocation and transfer-completion callbacks. This is a performance
baseline, not a production selection. Compare it with the modular PyDevices
`lvgl-micropython` plus `displayif` build on the same board and workloads.
PyDevices remains attractive for API portability, but its current native SPI
interface ultimately performs synchronous `machine.SPI.write()` calls and must
demonstrate equivalent throughput and render/transfer overlap before it is
chosen for the performance-first profile.

The first reference firmware's native panel driver is LVGL-oriented and does
not expose TartLab's direct-surface contract. Add a small supported TartLab
adapter or an upstream public API for direct transfers; do not build the game
backend around private `_data_bus`, `_set_memory_location`, or LVGL driver
fields.

### 3. Replace the hand-maintained PyDevices snapshot with a reproducible vendor pipeline

Do not use a git submodule alone. A submodule pins a repository but does not solve pruning, multi-repository dependencies, path adaptation, or payload reporting.

Create a noninteractive vendor tool driven by a checked-in lock/manifest file. It should:

1. Pin exact commit hashes or release tags for every upstream repository.
2. Fetch into a temporary build workspace.
3. Copy only an explicit allowlist of runtime modules and supported board files.
4. Apply small, reviewed TartLab compatibility patches from separate patch files.
5. Preserve upstream license and attribution files.
6. Generate a provenance file containing repository URLs, commits, selected files, and patch hashes.
7. Produce a per-package size report.
8. Fail if an expected upstream path disappears or an unexpected dependency is introduced.
9. Run import and compile checks for the legacy target.
10. Produce the update payload without modifying the source checkout interactively.

Prefer an allowlist over a growing exclusion list. New upstream demos or fonts should not silently enter device releases.

### 4. Make local files structurally impossible to overwrite

Define update ownership by top-level directory. For example:

- `/system` or `/lib/tartlab`: TartLab-managed and replaceable.
- `/lib/vendor`: generated third-party runtime and replaceable.
- `/device`: hardware identity and local calibration; never replaced.
- `/files/user`: student projects; never replaced.
- `/state`: settings, selected application, installed versions, logs, and update health state; migrated carefully, never blindly cleared.
- `/recovery`: minimal recovery/updater code; changed only through a protected process.

The exact names may differ, but ownership must be represented in code and tests, not comments.

For already deployed layouts, add a one-time migration that copies the existing hardware selection into the new local area only when the new file is absent. Never overwrite a detected local selection with a repository default.

Before any layout migration, back up and explicitly migrate the current `/settings.json`, `/repos.json`, `/logs`, `/files/user`, generated `/app.py` selection, and hardware selection. Prefer replacing mutable `/app.py` with a fixed system launcher that reads a validated selected-app value from preserved state. Do not copy captured Wi-Fi credentials into repository fixtures while developing or testing the migration.

### 5. Harden OTA updates

Evolve the release manifest to include at least:

- Manifest schema version.
- TartLab version.
- Release channel/stability and the rule for selecting the latest stable release.
- Supported source versions, layout/schema versions, and compatibility floor.
- Ordered internal migration identifiers and target schema version.
- Supported MicroPython version range or runtime profile.
- Required and optional capabilities.
- Package hashes and sizes.
- Expanded-size estimate.
- Target paths and ownership class.
- Install order.
- Preserve/migration instructions.
- Whether restart is required.

Use a staged update flow:

1. Select the latest stable release; do not ask the user to choose or install
   intermediate releases.
2. Download its manifest and direct-upgrade plan.
3. Validate the manifest, runtime, source layout/version, compatibility floor,
   and complete ordered migration path before modifying installed files.
4. Download every required bootstrap, migration, and target package.
5. Verify all hashes.
6. Extract into staging directories when space permits.
7. Save an update-in-progress marker, previous-version metadata, and the next
   internal migration step.
8. Apply idempotent migration steps and swap/copy staged packages into place in
   a controlled order, resuming automatically after a restart when necessary.
9. Update the minimal updater/recovery component through its protected process.
10. Boot the final target release into a health-check state.
11. Commit the target installed version only after startup succeeds.
12. Roll back or enter recovery if any stage fails repeatedly.

True atomic directory replacement may not be available on every MicroPython filesystem, so design the algorithm around the guarantees actually provided by the target filesystems. At minimum, preserve a bootable recovery path that does not depend on the package currently being replaced.

### 6. Generate version information during the build

Remove the manually maintained `v0.13` default from `main.py`. Generate a small build metadata module or JSON file containing:

- TartLab version.
- Git commit.
- Build timestamp.
- Runtime profile.
- Vendor lock identifier.

Initialize or repair `repos.json` from that metadata. Update installed-version state only after a successful update health check.

### 7. Make build and release tooling CI-friendly

Refactor scripts into callable functions plus a command-line interface with explicit flags such as:

- `--clean`
- `--profile legacy-mp123`
- `--profile lvgl-modern`
- `--vendor-lock vendor-lock.json`
- `--non-interactive`
- `--include-package NAME`
- `--output PATH`

Use platform-aware npm invocation rather than hard-coding `npm.cmd`. A GitHub Actions build should be able to generate exactly the same artifacts as a developer machine.

## Recommended next steps

### Phase 1: Protect existing deployments

1. Turn `_example_installation` into a reproducible, sanitized baseline fixture: record the board revision, exact firmware hash, capture method, filesystem capacity/free space, and expected file inventory; exclude or replace real credentials.
2. Create an automated OTA regression harness that starts from that fixture, plus release-archive inspection that lists every path each package can overwrite. Establish the tests before changing updater or filesystem ownership behavior.
3. Correct the local ownership boundary so hardware selection, selected-app state, user files, settings, release state, and logs cannot be cleared or overwritten. Replace mutable `/app.py` with a fixed launcher plus preserved selected-app state, or explicitly preserve it until that migration is complete.
4. Add structured boot diagnostics: firmware/runtime identity, reset cause, boot sequence number, free heap/PSRAM and filesystem space, update state, and explicit health markers after the IDE server or selected app is actually ready. Capture serial output alongside the rolling files during failure tests.
5. Add a minimal recovery boot path and an update-in-progress marker that remain usable when the normal IDE, display stack, or vendor libraries cannot import.
6. Fix updater failure semantics before another architectural migration: propagate download/extraction/write failures, never log package success after a failed extraction, and never advance `repos.json` until the new installation passes its boot health check.
7. Run first-boot, IDE/app-mode, preserved-state, interrupted-update, extraction-failure, and recovery tests on the exact MicroPython 1.23.0 octal-SPIRAM baseline before deploying these protections.

Do not ship an intermediate Phase 1 state that changes package ownership or updater behavior without the recovery path and OTA regression results required to repair it.

Phase 1 implementation and its physical legacy-hardware release gate are complete for the
tested working tree. The sanitized `tests/fixtures/legacy_mp123` baseline is marked
release-ready with physical board, firmware-hash, capture, and filesystem metadata. See
`tests/PHASE1_HARDWARE.md` for the complete 2026-08-03 through 2026-08-05 evidence record.
Before publishing a deployment artifact, commit the reviewed changes and repeat the final
legacy build/tests from that clean commit; the hardware-test artifact itself records a dirty
working tree and is not a release tag.

### Phase 2: Make the legacy build and release path reproducible

Implementation and test status (2026-08-10): the host-side Phase 2 build,
provenance, CI, failure-injection, and promotion gates are implemented. The
historical vendored source and deployed payload have separate content locks because the
tracked source contains one file that the stale v0.13 distribution omitted.
`makedist.py` and `release.py` now use clean noninteractive outputs,
platform-aware commands, normalized gzip/USTAR metadata, the pinned
`legacy-mp123` profile, deterministic inventories and checksums, explicit size
budgets, and legacy-compatible manifests. `legacy-ci.yml` builds twice and
publishes candidates; `promote-legacy-release.yml` requires a matching tested
candidate hash plus reviewed physical evidence through the protected
`legacy-release` environment.

Candidate `a42bedc1367d0b1e6b694dd059889db15f1008d2` passed the reproducible
host/CI gates and the physical legacy-hardware provisioning, browser, OTA,
protected-state, failure, recovery, failed-health, and future-OTA matrix on
2026-08-10. The complete record and sanitized evidence hash are in
`tests/PHASE2_HARDWARE.md`. Testing has an explicit environmental qualification:
the laptop hotspot and USB power path produced intermittent real resets, all of
which preserved recovery guarantees; a retry from unchanged v0.13 completed.
The implementation is therefore technically validated but is not yet approved
for stable deployment. Keep promotion closed until a reviewer accepts the
qualification (or requests a controlled-power repetition), selects a stable tag
and durable evidence reference, and confirms that the `legacy-release`
environment requires an approving reviewer.

1. Record content hashes and provenance for the currently deployed vendored payload before attempting to replace it.
2. Make `makedist.py` and `release.py` noninteractive and platform-aware, and require builds to start from a clean output directory so stale `dist` files cannot survive.
3. Generate build metadata containing TartLab version, Git commit, build timestamp, `legacy-mp123` profile, firmware compatibility, and a vendor-payload identifier.
4. Rebuild the known-working legacy payload without changing its runtime behavior; compare its file inventory, archive contents, expanded size, startup RAM, display/touch behavior, and OTA result with `_example_installation`.
5. Add legacy CI for clean builds, import/compile checks, archive ownership, size budgets, first installation, and OTA from the captured layout.
6. Add interrupted-download, corrupted-package, extraction/write failure, low-space, power-loss, and failed-health-check tests to the legacy release gate.
7. Publish reproducible legacy artifacts and provenance from CI, and require successful physical-device OTA tests before promoting a legacy release.

### Phase 3: Add the TartLab hardware abstraction

Implementation status (2026-08-12): three headless testing slices and a pinned
MicroPython compatibility tier are in place. The CPython hardware-free suite
contained 52 tests at this checkpoint; CI also builds the MicroPython v1.23.0
Unix interpreter and cross-compiler from pinned commit
`a61c446c0b34e82aeb54b9770250d267656f2b7f`.
`tests/virtual_device.py` provides an isolated device-root filesystem,
deterministic capacity reporting, a mutation journal, and abrupt power-loss
injection. `tests/test_virtual_device.py` applies the real candidate archives
through the recovery updater, interrupts every managed target during clearing
and every installable package at its first extraction write, reloads the
recovery runtime, and verifies protected content, old-version retention, staged
resume, and exactly-once health commit.

`tartlabutils.platform` is now the production startup boundary. Its legacy
adapter owns the historical PyDevices search paths and exposes display, pointer,
IDE-button, dimensions, capabilities, and deinitialization without changing the
deployed backend. `main.run()` accepts that contract plus injectable mode
runners. The test-only headless backend exercises real IDE/APP/recovery mode
selection, health commit, and startup-failure routing without board imports.
The platform boundary also owns IDE status rendering, WLAN interface creation,
hostname/open-AP configuration, delay, button reads, and brightness changes.
The complete IDE module now initializes headlessly in station and fallback-AP
modes, registers its real HTTP routes, and records startup, network, update, and
brightness UI behavior against the virtual filesystem. The test tiers and claim
boundaries are documented in `tests/TEST_TIERS.md`. Actual socket acceptance,
browser behavior, touch input, and student display programs remain outside the
headless claim and in the applicable physical tiers.

The pinned compatibility tier compiles every Python file in the generated
legacy distribution with the v1.23.0 `mpy-cross` using the ESP32 port's
`xtensawin` native emitter, then executes the real state migration, boot
recovery decisions, recovery validation/hash helpers, and legacy platform
adapter with the v1.23.0 Unix interpreter. It catches parser and core runtime
differences without claiming to emulate ESP32 flash, memory, reset, peripheral,
or radio behavior.

1. **Implemented:** define the small TartLab platform contract used by startup
   and the IDE.
2. **Implemented; focused physical smoke completed 2026-08-12:** wrap the
   current legacy backend without intentionally changing visible behavior.
   `tests/PHASE3_HARDWARE.md` records healthy update commit, IDE/APP routing,
   fallback-AP and station HTTP behavior, display-driver calls, and unchanged
   protected-state hashes. The candidate will not be promoted; pressed-button
   and human visual checks remain explicitly unclaimed.
3. **Implemented for core startup:** move direct historical PyDevices path
   assumptions into the legacy adapter.
4. **Partial:** capability detection is exposed by the platform; include it in
   structured device diagnostics after the physical behavior is confirmed.
5. **Implemented:** provide virtual-filesystem and headless backends for OTA,
   recovery, startup, and IDE initialization logic.

### Phase 4: Migrate and prune PyDevices behind the abstraction

Implementation status (2026-08-17): Phase 4 is implemented. The import/payload inventory,
current-upstream equivalence audit, pinned candidate vendor pipeline, minimal
legacy compatibility surface, guarded research release builder, and Phase 4
item 6 physical qualification are complete. Item 7 promotes the exact
qualified source and packaged-runtime identities into the normal legacy CI and
stable-tag rebuild paths. The checked-in historical tree remains an audited
base/fallback input, but a direct normal `release.py` invocation rejects it.
The promoted builder overlays the generated allowlisted runtime, compiles it to
MicroPython 1.23 `xtensawin` bytecode, and fails on source or packaged identity
drift. A conservative static analysis
starts separately from the TartLab platform/IDE boundary, the default
T-Display-S3 Pro adapter, and all shipped Python examples. It classifies 39 of
the locked payload's 146 files as reachable (317,934 normalized source bytes)
and explicitly records the remaining 107 files (731,358 bytes) as retained but
not statically reachable. Conditional and function-local imports are included;
runtime-string imports remain an explicit limitation. CI checks both the source
analysis and the exact generated `dist/lib/pydevices` path set against
`vendor/legacy-pydevices.imports.json`. No file has been pruned by this step.

The reviewed `vendor/legacy-pydevices.upstream.json` pins four official
upstream trees at full commits and maps all 39 reachable files. Thirty-eight
have maintained equivalents; the TartLab-added QOI reader has none. The current
split includes the separate `palettes` repository, and the former
`micropython-hardware` URL now resolves to the canonical `pydevices` repository.
No mapped file is a drop-in replacement for the legacy payload. A maintained
T-Display-S3 Pro board configuration does exist at the audited `pydevices` pin,
but it uses current `displaydev` and `eventsys` contracts rather than TartLab's
legacy `displaysys`/`Broker` exports. These audit pins do not approve a source
replacement or establish MicroPython 1.23 compatibility.

The candidate lock selects all 47 unique upstream sources referenced by that
mapping plus 18 explicit dependencies. The noninteractive vendor tool reads
content from exact git objects, preserves all four upstream licenses, applies
only hash-pinned strict patch manifests, host-compiles selected Python sources,
enforces the reviewed external/dynamic-import sets, and emits deterministic
provenance and size reports.

Item 5 adds five hash-pinned TartLab adapters and the retained local QOI reader
as separate sources rather than upstream modifications. They preserve
`graphics`, `bmp565`, `touch_keypad`, `eventsys.keys.Keys`, the protected
T-Display-S3 Pro board path, and scalar legacy broker polling. Core TartLab
continues to use only its existing platform boundary and legacy-compatible
names. The generated runtime is now 71 files and 522,319 normalized source
bytes, 49.7% of the historical snapshot's 1,049,292 bytes, with identifier
`sha256:277bc307b4e20dc07afd61580e737800f639a161ac2a9a341c4febef981fe23c`.
Six strict patches cover the MicroPython 1.23 parser, display constructor,
native framebuffer selection, two stages of ST7796 fill compatibility and
performance work, and ESP32 SPI transfer configuration. The board adapter
keeps touch application-polled instead of
using the unsupported upstream timer keyword. The host probe covers the
compatibility surface, and CI compiles all candidate sources and runs the probe
with pinned MicroPython 1.23 host tools.

`tools/build_phase4_test_release.py` overlays that exact runtime on a normal
legacy distribution, applies the locked minifier, compiles all 71 modules with
pinned MicroPython 1.23 `mpy-cross` for `xtensawin`, verifies source and
packaged identities, and marks both evidence and release metadata
research-only. `tools/build_promoted_release.py` uses the same transformation
but additionally requires a clean worktree, the pinned release toolchain, and
the exact item 6 identities recorded in the legacy profile. Normal CI builds
that promoted path twice, and the stable-tag workflow rebuilds the same path
before binding physical evidence. The completed comparison in
`tests/PHASE4_HARDWARE.md` records a
75.9% smaller PyDevices archive, 1,196,032 more free filesystem bytes, 0.9%
less startup heap, solid fills about 20% faster than legacy, and full-frame
blits about 9.8% slower. Steady healthy startup remains 13.7% slower and the
startup-to-IDE proxy 22.9% slower; that bounded residual is explicitly accepted
for the research migration gate. Human color and five-point touch checks,
direct network OTA, corrupt/truncated/low-space/write containment, physical
install interruption, offline recovery resume, repeated-health recovery, and
protected-state preservation all passed.

1. **Implemented:** inventory which modules from the current embedded
   `pydevices` tree TartLab imports through the reviewed static roots.
2. **Implemented:** identify and pin the current upstream equivalents across
   `pydisplay`, canonical `pydevices`, `pygraphics`, and `palettes`.
3. **Confirmed:** a maintained T-Display-S3 Pro board configuration exists
   upstream; the compatibility adapter is implemented by item 5.
4. **Implemented:** create the pinned, explicit vendor lock/allowlist pipeline
   with license retention, strict patch support, dependency gates, deterministic
   provenance, and size reporting. The generated tree remains research-only.
5. **Implemented for the generated candidate:** build a minimal
   legacy-compatible payload without exposing upstream paths or APIs to core
   TartLab code.
6. **Completed 2026-08-17:** the final Candidate 9 passed storage, heap,
   steady-startup, display transfer, real touch/color, direct OTA, recovery
   fault/resume, health commit, and protected-state checks on the qualified
   board and firmware. The remaining bounded startup and blit regressions are
   recorded and accepted for this research gate; they are not a promotion.
7. **Implemented:** promote only the qualified source and packaged identities
   through the normal reproducible CI and stable-tag release paths. The
   candidate lock remains research-only input provenance; promotion authority
   lives in the hardware-gated legacy release profile.

### Phase 5: Prototype modern LVGL firmware separately

A locally built MicroPython 1.27.0/LVGL combined image is archived under
`firmware/lvgl-modern/1.27.0` with an exact artifact hash and measured runtime
identity. It remains experimental: the build reported a dirty MicroPython tree,
and the LVGL repository commit, source diff, exact build command, LVGL version,
and toolchain were not captured. Archiving the artifact therefore does not yet
satisfy the reproducible-build or hardware-qualification items below. It also
does not prove that TartLab used that image's native `lcd_bus`; an LVGL module
present in firmware provides no acceleration while TartLab continues to flush
through the pure-Python PyDisplay bus.

The Phase 5 objective is a performance-first dual-renderer firmware, not merely
a firmware on which `import lvgl` succeeds. The first reproducible reference
should be based on `lvgl-micropython/lvgl_micropython`, because TartLab has
already built it successfully and its ESP32 `lcd_bus` path provides the most
promising current DMA/double-buffer baseline. A PyDevices `lvgl-micropython` +
`displayif` build remains a required comparison rather than the default winner.

Phase 5 item 1 implementation status (2026-08-24):
`firmware/lvgl-modern/reference.lock.json` now pins the outer binding commit,
all five of its direct gitlinks, MicroPython 1.27.0, LVGL 9.4.0, ESP-IDF 5.5.1,
the exact T-Display-S3 Pro target arguments, and a Linux/amd64 ESP-IDF container
manifest digest. `tools/modern_firmware.py` validates the lock, verifies an
exact clean detached checkout and its gitlinks, and generates or executes a
non-flashing digest-pinned Docker build. This completes the source/toolchain
lock and clean-input recipe without retrofitting provenance onto the archived
dirty-tree binary.

Phase 5 item 2 implementation status (2026-08-24): TartLab now supplies a
hash-bound CST226 driver through the pinned upstream public `PointerDriver` and
native I2C device APIs. The fixed recipe freezes that driver and ST7796 support,
builds the native `lcd_bus`/LVGL firmware with a 4 MiB application partition,
and bridges the official container's Python environment to the path expected by
the upstream merger. The first reproducible recipe used UART-only REPL and was
rejected during item 4 provisioning because the target is connected through
native USB. A USB Serial/JTAG revision was reproduced from two clean checkouts,
then physical testing found a mixed-width CST226 identity bug and the upstream
bus's two-framebuffer allocation limit. The current recipe fixes the touch
transaction and adds an explicit capability-bound application buffer API. Two
independent clean checkouts produce the same 2,978,512-byte checkpoint with
SHA-256
`187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`;
the second image is byte-identical to the archived reference.
The binary and provenance are archived under `firmware/lvgl-modern/reference`.
This completes the reproducible host-build portion of item 2.

Phase 5 item 3 implementation status (2026-08-24): the explicit modern
T-Display-S3 Pro configuration now constructs the pinned native `lcd_bus`,
ST7796, CST226, dual DMA buffers, LVGL task handler, and TartLab platform
adapter. IDE status rendering uses LVGL widgets. Game mode exposes a public
logical 480 x 222 `RGB565_BE` dirty-rectangle surface with native DMA buffer
allocation, synchronous or explicitly awaited asynchronous writes, bounds and
buffer-size checks, and no upstream private fields in its public API. A single
completion-callback multiplexer pauses LVGL and input, drains the final UI
flush, transfers exclusive ownership to the game surface, then drains game DMA,
reenables LVGL/input, invalidates the UI, and forces its redraw on return. The
legacy platform implements the same mode-entry boundary as no-ops and retains
its existing renderer. Host tests cover ownership, completion, unsafe buffer
reuse, transfer parameters, and redraw behavior. Item 4 physically verified
the adapter on the exact reference checkpoint.

Phase 5 item 4 implementation status (2026-08-25): the exact reference
checkpoint passed the recorded physical lifecycle gate on the T-Display-S3 Pro
PCB v1.1. Hard and soft reset, five same-runtime init/deinit cycles, two
25-cycle UI/game/UI runs, color and orientation, five-point touch, fallback AP
and browser IDE, physical APP selection, APP-to-IDE return, error recovery, and
final healthy UI all passed. Testing corrected panel/touch rotation, upstream
display/input registry teardown, return-to-UI DMA draining, and the APP health
timer fallback required on ESP32 when virtual `machine.Timer(-1)` is
unsupported. A captured spontaneous reset was an explicit brownout; changing
to a known-good USB path then passed a five-minute passive reset capture. The
backlight read 100 percent duty, a gamma A/B was inconclusive, and normal
brightness returned without retaining a gamma change. Exact commands,
observations, and limitations are recorded in `tests/PHASE5_HARDWARE.md`.
This completes item 4 for the checkpoint but does not qualify or promote it.
The reproducibility gate is also complete; item 5 comparative benchmarks are
the remaining gate.

1. **Implemented for the first reference:** pin MicroPython, LVGL, ESP-IDF, the
   binding repository, every direct submodule, and the host toolchain; require a
   clean source state and record the exact non-flashing build command.
2. **Implemented and reproducible:**
   produce reference firmware for the T-Display-S3 Pro with LVGL, its ST7796
   panel driver, CST226 support, native SPI transport, DMA-capable buffers, and
   transfer-completion signaling.
3. **Implemented and physically verified:** implement TartLab
   UI and game rendering adapters behind the platform boundary. UI mode uses
   LVGL; game mode exposes a public direct surface and explicit
   display-ownership transitions.
4. **Completed for the exact reference checkpoint:** verify hard reset, soft
   reset, repeated initialization/deinitialization,
   UI-to-game-to-UI transitions, Wi-Fi AP mode, IDE server operation, touch
   input, application switching, and recovery after an application exception.
5. Benchmark both firmware families on identical clocks, buffers, panel
   orientation, assets, and instrumentation. At minimum record:

   - raw RGB565 full-frame transfer and achieved throughput;
   - 10%, 25%, and 50% dirty-region transfers;
   - solid fills, sprite movement over a static background, and scrolling;
   - LVGL widget and animation workloads;
   - render time, transfer time, overlap, total frame time, missed frame
      deadlines, CPU availability for the IDE/network stack, and heap stability;
   - steady-state allocation count and behavior across repeated mode switches.

6. Test partial refresh first. Treat full-screen FPS as a wire-limited metric,
   not as the only graphics score, and do not claim a speedup from LVGL merely
   being compiled into the firmware.
7. Keep the existing legacy release channel unchanged during the experiment.
   Sunset it only after a qualified modern image, an adult/admin provisioning
   path, and a documented support window exist.
8. Select the production firmware only after the benchmark and lifecycle gates
   pass. If the first repository wins, maintain a pinned public direct-surface
   adapter; if PyDevices wins, require its native bus to meet the same DMA,
   overlap, and soft-reset requirements.

### Phase 6: Mature release security and promotion

1. Extend the established legacy test matrix and CI pipeline to the modern firmware profile rather than creating a separate release process.
2. Build signed or otherwise authenticated release metadata; SHA-256 verifies integrity but, by itself, does not establish publisher authenticity.
3. Publish versioned firmware, filesystem packages, source/vendor provenance, compatibility declarations, and migration instructions from CI.
4. Test both clean provisioning and adult-admin migration from the legacy firmware, including failure and recovery paths.
5. Require successful profile-specific hardware, OTA, and recovery tests before any artifact is promoted to its deployment channel.

## Minimum test matrix

Every significant platform or dependency change should cover:

| Scenario | Required checks |
|---|---|
| MicroPython 1.23.0 octal-SPIRAM (`ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`), T-Display-S3 Pro | Boot, display, touch, PSRAM availability, AP mode, IDE, edit/save/run app, switch modes, OTA update, five-log rotation |
| Modern generic MicroPython without LVGL | Same behavior, confirms the pure-Python path remains portable without replacing the 1.23.0 legacy baseline |
| Pinned LVGL-enabled firmware | Boot and soft reset, display/touch, AP/IDE, LVGL UI, direct game rendering, UI/game ownership transitions, native DMA behavior, update and recovery |
| First boot without settings | Create defaults safely, reach the IDE, and preserve a recovery route |
| Update from existing deployed layout | Preserve hardware selection, selected app, settings, logs, release state, and user applications |
| Direct update from every supported historical layout | One user action reaches the current stable release; all ordered internal migrations resume safely without requiring intermediate releases |
| Interrupted update | Recovery path remains bootable; update can be retried |
| Extraction failure | Installer reports failure, does not log package success, and does not advance the installed version |
| Low filesystem space | Update refuses safely before deleting active packages |
| Bad package/hash | No installed files are modified |
| Missing/failed display backend | Device exposes recovery/update diagnostics where possible |

Record exact firmware hashes and board revisions for hardware test results.

## Agent guardrails

An AI agent working on TartLab must follow these rules:

- Do not remove or weaken OTA capability without an explicit replacement and migration test.
- Do not assume that firmware can be changed through the existing file updater.
- Do not claim legacy compatibility without testing the exact `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` image on physical hardware and confirming PSRAM availability.
- Do not make LVGL mandatory for the legacy profile.
- Do not equate `import lvgl` with accelerated TartLab graphics; verify that the
  selected native bus and renderer are actually active.
- Do not allow LVGL and a direct game renderer to own the panel concurrently.
- Do not build the direct game surface on private upstream driver attributes;
  add and pin a supported adapter/API.
- Do not claim a graphics speedup without reporting region size, render time,
  transfer time, total frame time, display clock, buffering mode, and firmware
  identity.
- Do not replace a local hardware selector, calibration file, selected-app value or generated launcher, student project, settings file, or recovery state with a repository default.
- Do not copy an entire PyDevices repository into the device image.
- Do not track upstream `main` without a pinned commit and test results.
- Do not silently add a dependency because it imports successfully on CPython.
- Do not change update package ownership or clearing behavior without inspecting the resulting archive paths.
- Do not update the recorded installed version until the new system has booted successfully.
- Do not require users to install intermediate TartLab releases. Preserve and
  test a direct path from every supported deployed layout to the latest stable
  release, using automatic internal migration stages when needed.
- Do not publish a latest stable release that the oldest supported deployed
  updater cannot enter. Retain a compatible bootstrap/recovery path or reject
  the source version safely before changing active files.
- Prefer small compatibility adapters over widespread imports of unstable upstream internals.
- Preserve upstream licenses and record the exact source of vendored code.
- Treat filesystem captures, `/settings.json`, and diagnostic bundles as sensitive because settings contain plaintext Wi-Fi credentials.
- Test on physical legacy hardware before declaring a release compatible.

## Decisions still requiring explicit confirmation

Before the migration is considered complete, the project owner should make
explicit decisions about the following items. The local configuration directory
is no longer undecided: `/device` is the authoritative protected location.

1. The minimum set of boards supported by each release.
2. How long the exact MicroPython 1.23.0 octal-SPIRAM compatibility profile will be maintained.
3. Whether TartLab will maintain its own T-Display-S3 Pro board adapter or contribute/consume an upstream one.
4. The approved firmware provisioning method for LVGL-capable devices.
5. The amount of flash space reserved for staging, recovery, and rollback.
6. Whether release authenticity will use signatures, a pinned public key, or another mechanism beyond hashes delivered in the same GitHub release.
7. The oldest deployed TartLab version/layout included in the direct-to-latest
   compatibility window and the administrator process for devices older than
   that floor.
8. The measured winner of the first-repository `lcd_bus` and PyDevices
   `displayif` modern-firmware comparison, including who maintains TartLab's
   public direct-surface adapter.

## Near-term definition of success

The next architectural milestone should not be “TartLab runs on the newest PyDisplay.” It should be:

> A reproducible, minimal, pinned PyDisplay-derived payload can be built for
> TartLab; with one user-initiated update, any supported existing device running
> `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` can move directly to the
> latest stable release without installing intermediate releases or losing
> hardware configuration, selected application, user programs, settings, logs,
> recovery capability, or future OTA access; and the same TartLab hardware API
> can later select an LVGL-enabled backend on separately provisioned firmware.

The corresponding modern milestone is:

> A reproducible, pinned firmware gives TartLab exclusive, lifecycle-safe
> ownership of one native display transport; LVGL drives the IDE and normal UI,
> a supported direct surface drives frame-paced games, both paths pass measured
> partial-refresh, DMA, mode-transition, soft-reset, network, and heap gates,
> and adults can provision or migrate devices without weakening recovery.
