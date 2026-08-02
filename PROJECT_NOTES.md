# TartLab Project Notes

> Repository review date: 2026-08-02  
> Primary repository: <https://github.com/tdhoward/TartLab>

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

### 2. Continue supporting deployed MicroPython 1.24 devices

Existing TartLab deployments use a generic MicroPython 1.24 firmware. New TartLab releases must continue to run on that baseline until an explicit migration policy says otherwise.

Consequences:

- Do not require LVGL, frozen modules, native display buses, or newly added MicroPython APIs in the legacy runtime path.
- New dependencies must be tested on actual MicroPython 1.24 hardware, not only CPython or a recent MicroPython build.
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

`src/main.py` adds TartLab, user-file, board-config, and embedded PyDevices directories to `sys.path`. It imports `IDE_BUTTON_PIN` and `display_drv` from `hdwconfig.py`, then selects IDE or APP mode from settings and button state. The user's application is launched through `app.py`.

This is a sensible basic separation, but core startup currently knows the historical embedded PyDevices directory layout (`bus_drv`, `display_drv`, `touch_drv`, and `add_ons`). Those paths should not remain a permanent public contract because upstream PyDisplay has changed its repository and package structure.

### Hardware selection

`src/hdwconfig.py` is intended to be set once for a device and imports a board-specific module from `/configs`. It currently selects `t_display_s3_pro`.

The intended distinction is useful:

- A local selector identifies the physical board.
- Update-managed board support modules provide the implementation.

However, the update boundaries need to be made explicit and enforced by tooling. `hdwconfig.py` is included among top-level distribution files, while `/configs` is an update package configured with `clear_first: true`. The root package is not cleared, but files present in its archive are still overwritten during extraction. Therefore the current comments alone do not guarantee that local hardware configuration is preserved.

Treat this as a critical migration item: define one clearly named local configuration location that is never included in release archives and is never deleted or overwritten by the updater.

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

Important weaknesses:

- Build and release scripts are interactive, which makes reproducible CI releases difficult.
- `makedist.py` directly invokes `npm.cmd`, making the build Windows-specific.
- The default installed version is hard-coded in `main.py` as `v0.13` when `repos.json` is first created.
- The manifest has no schema version, runtime compatibility declaration, package dependency information, preservation rules, or rollback metadata.
- Installation is in-place and sequential. For `clear_first` packages, the old directory is deleted before the replacement is extracted.
- A reset, power loss, write failure, or extraction error can leave a partially replaced installation with no automatic rollback.
- Free-space checking is based mainly on release asset sizes and a small fixed buffer; it does not model all staging, extraction, backup, and filesystem-overhead requirements.

### Embedded PyDevices snapshot

TartLab currently contains a partial, modified copy under `src/lib/pydevices`. The script `distill_pydevices.py` was created to generate this payload from a neighboring repository named `mpdisplay`.

The script is now tied to an older upstream layout. It expects paths such as:

- `board_configs/busdisplay/...`
- `drivers/bus`
- `drivers/display`
- `drivers/touch`
- `src/add_ons`

It also flattens or renames parts of that structure into TartLab-specific import directories. This explains why a current PyDisplay checkout cannot simply replace the embedded copy.

## Current PyDevices/PyDisplay direction

The upstream project has been reorganized into multiple repositories:

- `PyDevices/pydisplay`: portable display, event, and timer core.
- `PyDevices/micropython-hardware`: MicroPython/CircuitPython board configurations and hardware drivers that previously lived inside PyDisplay.
- `PyDevices/pygraphics`: graphics functionality now maintained as a sister package.
- `PyDevices/lv_micropython_cmod` and `PyDevices/lv_bindings`: LVGL integration for custom MicroPython builds.
- `PyDevices/cmods`: optional workspace and scripts for building MicroPython with multiple native user C modules.

Relevant upstream repositories:

- <https://github.com/PyDevices/pydisplay>
- <https://github.com/PyDevices/micropython-hardware>
- <https://github.com/PyDevices/pygraphics>
- <https://github.com/PyDevices/lv_micropython_cmod>
- <https://github.com/PyDevices/lv_bindings>
- <https://github.com/PyDevices/cmods>

PyDisplay explicitly describes itself as alpha quality with rapidly evolving APIs and documentation. Therefore TartLab should not automatically follow upstream `main` on deployed devices. Upgrades should be deliberate, pinned, tested changes.

PyDisplay's architecture is compatible with TartLab's broad goal: application code can use a stable display/input abstraction while board configuration selects a backend. It can support ordinary Python display drivers and can also participate in LVGL-enabled firmware. That does not mean the same collection of files can be dropped onto every firmware version without testing.

## Required compatibility model

TartLab should explicitly maintain two runtime profiles during migration.

### Profile A: Legacy generic firmware

Target:

- Existing generic MicroPython 1.24 installations.
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
- LVGL and selected native user C modules compiled or frozen into firmware.
- Faster native display/bus paths where supported.

Rules:

- Firmware builds must be reproducible and versioned.
- TartLab must detect capabilities rather than assume them from a board name alone.
- The filesystem application package should still be independently OTA-updatable.
- A firmware-specific TartLab package may be produced when unavoidable, but common application logic should remain shared.

### Critical migration limitation

The current TartLab updater changes filesystem files only. It cannot convert an existing generic MicroPython 1.24 device into an LVGL-enabled custom firmware device.

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
platform.input
platform.ide_button_pin
platform.capabilities
platform.deinit()
```

Keep the contract deliberately small. Board-specific code may import PyDisplay internals, but the IDE, updater UI, and student app launcher should not.

This isolates TartLab from future PyDisplay path and API changes and makes legacy and LVGL backends selectable behind the same interface.

### 2. Replace the hand-maintained PyDevices snapshot with a reproducible vendor pipeline

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

### 3. Make local files structurally impossible to overwrite

Define update ownership by top-level directory. For example:

- `/system` or `/lib/tartlab`: TartLab-managed and replaceable.
- `/lib/vendor`: generated third-party runtime and replaceable.
- `/device`: hardware identity and local calibration; never replaced.
- `/files/user`: student projects; never replaced.
- `/state`: settings, installed versions, logs, and update health state; migrated carefully, never blindly cleared.
- `/recovery`: minimal recovery/updater code; changed only through a protected process.

The exact names may differ, but ownership must be represented in code and tests, not comments.

For already deployed layouts, add a one-time migration that copies the existing hardware selection into the new local area only when the new file is absent. Never overwrite a detected local selection with a repository default.

### 4. Harden OTA updates

Evolve the release manifest to include at least:

- Manifest schema version.
- TartLab version.
- Supported MicroPython version range or runtime profile.
- Required and optional capabilities.
- Package hashes and sizes.
- Expanded-size estimate.
- Target paths and ownership class.
- Install order.
- Preserve/migration instructions.
- Whether restart is required.

Use a staged update flow:

1. Download manifest.
2. Validate schema and compatibility before modifying installed files.
3. Download every required package.
4. Verify all hashes.
5. Extract into staging directories when space permits.
6. Save an update-in-progress marker and previous-version metadata.
7. Swap or copy staged packages into place in a controlled order.
8. Update the minimal updater/recovery component last.
9. Boot into a health-check state.
10. Commit the installed version only after startup succeeds.
11. Roll back or enter recovery if startup fails repeatedly.

True atomic directory replacement may not be available on every MicroPython filesystem, so design the algorithm around the guarantees actually provided by the target filesystems. At minimum, preserve a bootable recovery path that does not depend on the package currently being replaced.

### 5. Generate version information during the build

Remove the manually maintained `v0.13` default from `main.py`. Generate a small build metadata module or JSON file containing:

- TartLab version.
- Git commit.
- Build timestamp.
- Runtime profile.
- Vendor lock identifier.

Initialize or repair `repos.json` from that metadata. Update installed-version state only after a successful update health check.

### 6. Make build and release tooling CI-friendly

Refactor scripts into callable functions plus a command-line interface with explicit flags such as:

- `--clean`
- `--profile legacy-mp124`
- `--profile lvgl-modern`
- `--vendor-lock vendor-lock.json`
- `--non-interactive`
- `--include-package NAME`
- `--output PATH`

Use platform-aware npm invocation rather than hard-coding `npm.cmd`. A GitHub Actions build should be able to generate exactly the same artifacts as a developer machine.

## Recommended next steps

### Phase 1: Protect existing deployments

1. Create physical-device backups of at least one deployed-style MicroPython 1.24 T-Display-S3 Pro filesystem.
2. Document the current boot, IDE, application, and update sequence.
3. Add an automated release-archive inspection test that lists every path each package can overwrite.
4. Correct the local configuration boundary so hardware selection, user files, and state cannot be cleared or overwritten.
5. Add a minimal recovery boot path and an update-in-progress marker before changing PyDisplay.
6. Create an OTA regression fixture that starts from the last public TartLab layout and updates to a test release.

### Phase 2: Establish reproducible dependency management

1. Inventory which modules from the current embedded `pydevices` tree TartLab actually imports at runtime.
2. Identify the current upstream equivalents across `pydisplay`, `micropython-hardware`, and `pygraphics`.
3. Confirm whether a maintained T-Display-S3 Pro board configuration exists upstream; otherwise port TartLab's working board configuration to the current contract.
4. Create the vendor lock/allowlist pipeline.
5. Build a minimal legacy-compatible payload.
6. Compare flash usage, RAM at startup, display initialization time, frame/update performance, and touch behavior against the current deployed code.

### Phase 3: Add the TartLab hardware abstraction

1. Define the smallest useful TartLab platform contract.
2. Wrap the current legacy backend first without changing visible behavior.
3. Remove direct historical PyDevices path assumptions from core startup code.
4. Add capability detection and diagnostic reporting.
5. Add a headless or desktop test backend for non-hardware logic where practical.

### Phase 4: Prototype modern LVGL firmware separately

1. Pin a MicroPython version and the required PyDevices LVGL repositories.
2. Produce a reproducible firmware build for one reference device.
3. Verify hard reset, soft reset, repeated import/deinit, Wi-Fi AP mode, IDE server operation, touch input, and application switching.
4. Measure whether native buses/LVGL materially improve the workloads TartLab needs.
5. Keep the existing legacy release channel unchanged during this experiment.
6. Only after successful hardware testing, define how new devices are provisioned and how adults migrate old ones.

### Phase 5: Harden and automate releases

1. Add a test matrix for legacy and modern profiles.
2. Build signed or otherwise authenticated release metadata if feasible; SHA-256 verifies integrity but, by itself, does not establish publisher authenticity.
3. Add interrupted-download, corrupted-package, low-space, power-loss, and failed-boot tests.
4. Publish release artifacts and provenance from CI.
5. Require successful OTA upgrade tests before a release is promoted to deployed devices.

## Minimum test matrix

Every significant platform or dependency change should cover:

| Scenario | Required checks |
|---|---|
| Generic MicroPython 1.24, T-Display-S3 Pro | Boot, display, touch, AP mode, IDE, edit/save/run app, switch modes, OTA update |
| Modern generic MicroPython without LVGL | Same behavior, confirms pure-Python path is not accidentally tied to 1.24 |
| Pinned LVGL-enabled firmware | Boot and soft reset, display/touch, AP/IDE, app mode, update, native-driver behavior |
| Update from existing deployed layout | Preserve hardware selection, settings, and user applications |
| Interrupted update | Recovery path remains bootable; update can be retried |
| Low filesystem space | Update refuses safely before deleting active packages |
| Bad package/hash | No installed files are modified |
| Missing/failed display backend | Device exposes recovery/update diagnostics where possible |

Record exact firmware hashes and board revisions for hardware test results.

## Agent guardrails

An AI agent working on TartLab must follow these rules:

- Do not remove or weaken OTA capability without an explicit replacement and migration test.
- Do not assume that firmware can be changed through the existing file updater.
- Do not make LVGL mandatory for the legacy profile.
- Do not replace a local hardware selector, calibration file, student project, settings file, or recovery state with a repository default.
- Do not copy an entire PyDevices repository into the device image.
- Do not track upstream `main` without a pinned commit and test results.
- Do not silently add a dependency because it imports successfully on CPython.
- Do not change update package ownership or clearing behavior without inspecting the resulting archive paths.
- Do not update the recorded installed version until the new system has booted successfully.
- Prefer small compatibility adapters over widespread imports of unstable upstream internals.
- Preserve upstream licenses and record the exact source of vendored code.
- Test on physical legacy hardware before declaring a release compatible.

## Decisions still requiring explicit confirmation

Before the migration is considered complete, the project owner should make explicit decisions about:

1. The exact directory reserved for immutable/local device configuration.
2. The minimum set of boards supported by each release.
3. How long the MicroPython 1.24 compatibility profile will be maintained.
4. Whether TartLab will maintain its own T-Display-S3 Pro board adapter or contribute/consume an upstream one.
5. The approved firmware provisioning method for LVGL-capable devices.
6. The amount of flash space reserved for staging, recovery, and rollback.
7. Whether release authenticity will use signatures, a pinned public key, or another mechanism beyond hashes delivered in the same GitHub release.

## Near-term definition of success

The next architectural milestone should not be “TartLab runs on the newest PyDisplay.” It should be:

> A reproducible, minimal, pinned PyDisplay-derived payload can be built for TartLab; an existing MicroPython 1.24 device can update to it without losing hardware configuration, user programs, recovery capability, or future OTA access; and the same TartLab hardware API can later select an LVGL-enabled backend on separately provisioned firmware.
