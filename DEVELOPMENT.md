# TartLab development

This guide covers source setup, host validation, release-candidate builds, and
optional physical-board work. The tracked repository and lockfiles are source
inputs; generated output and device-local data are not.

## Host requirements

- Git
- Python `>=3.10,<3.15`
- Node.js 20 or newer, including npm
- Windows/PowerShell for the established USB-serial workflow; Linux and macOS
  are supported for hardware-free work

The pinned `python-minifier==3.2.0` and npm dependency graph affect release
bytes and must remain locked. Docker is needed only to reproduce modern
firmware, not for ordinary TartLab development.

## Bootstrap a clean checkout

```powershell
git clone https://github.com/tdhoward/TartLab.git
Set-Location TartLab
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-build.txt
npm ci --prefix src/ide/www
npm run build --prefix src/ide/www
```

On Linux or macOS use `.venv/bin/python`. Use `npm ci`, not `npm install`, when
the lockfile changes or the dependency tree may be stale.

## Normal validation

Run the web build and complete hardware-free suite:

```powershell
npm run build --prefix src/ide/www
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_phase5 tests.test_board_catalog tests.test_modern_profile tests.test_phase6 tests.test_phase6_provisioning tests.test_virtual_device tests.test_platform tests.test_modern_power tests.test_headless_ide -v
```

Verify tracked firmware identities when firmware or profile metadata changes:

```powershell
.\.venv\Scripts\python.exe tools/check_board_catalog.py
.\.venv\Scripts\python.exe tools/check_firmware_artifacts.py
.\.venv\Scripts\python.exe tools/modern_firmware.py check
```

Modern board descriptors and the port lifecycle are documented in
[`BOARD_SUPPORT.md`](BOARD_SUPPORT.md). New ports start in `bringup`; changing a
descriptor to `candidate` or `qualified` adds enforced artifact and evidence
requirements.

CI additionally builds pinned MicroPython 1.23 host tools and runs the Tier 2
compatibility probe. The optional local command and exact claim boundaries are
in [`tests/TEST_TIERS.md`](tests/TEST_TIERS.md). Host tests do not replace an
applicable physical smoke or release gate.

## Build a legacy candidate

Builds must start from clean output. After the web build:

```powershell
.\.venv\Scripts\python.exe makedist.py --output build/legacy/dist --clean --skip-web-build
.\.venv\Scripts\python.exe tools/pydevices_inventory.py --dist build/legacy/dist
.\.venv\Scripts\python.exe tools/pydevices_upstream.py
.\.venv\Scripts\python.exe tools/vendor_pydevices.py --fetch --output build/vendor/pydevices-candidate --clean
.\.venv\Scripts\python.exe -B tests/pydevices_candidate_compat.py build/vendor/pydevices-candidate/runtime src/files/assets/test.qoi
.\.venv\Scripts\python.exe tools/build_promoted_release.py --base-dist build/legacy/dist --candidate build/vendor/pydevices-candidate --output build/promoted --version vX.Y.Z --mpy-cross path\to\v1.23.0\mpy-cross --clean
.\.venv\Scripts\python.exe tools/check_legacy_release.py --dist build/promoted/dist --release build/promoted/release
```

The promoted builder requires a clean worktree, the pinned toolchain, and exact
source and packaged PyDevices identities from
`profiles/legacy-mp123.json`. Direct normal releases from the historical
checked-in PyDevices tree are rejected. For an explicitly research-only
comparison, use `tools/build_phase4_test_release.py`; it cannot authorize a
release.

CI builds the candidate twice and requires byte-identical output. Use only the
`legacy-mp123-<full-commit-sha>` artifact from a successful **Legacy release
CI** run whose head SHA matches the intended commit.

## Modern firmware and releases

The published modern profile is bound to the exact image and adapter hashes in
[`profiles/lvgl-modern.json`](profiles/lvgl-modern.json). Validate the pinned
source graph and create a fresh detached checkout with:

```powershell
.\.venv\Scripts\python.exe tools/modern_firmware.py check
.\.venv\Scripts\python.exe tools/modern_firmware.py checkout --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py check --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py command --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py build --source build/phase5/lvgl-micropython
```

The build is non-flashing and refuses the wrong commit or dirty upstream tree.
The upstream build mutates generated source state, so do not reuse its checkout
for reproducibility claims.

Modern releases contain a combined firmware image, filesystem packages,
compatibility data, locks, provenance, and migration instructions. The
protected qualification and promotion workflows target only
`tdhoward/TartLab-modern-releases`. Detailed authentication commands are in
[`tests/PHASE6_RELEASE_SECURITY.md`](tests/PHASE6_RELEASE_SECURITY.md).

Candidate builds include the qualified default board unless `--board` is
provided. Repeat `--board BOARD_ID` to build a deliberate multi-board candidate;
the default board must always be included. Shared filesystem packages are built
once, while firmware, locks, provenance, and compatibility entries remain
board-specific.

## Adult modern provisioning

Start with a read-only inspection of a complete downloaded release:

```powershell
.\.venv\Scripts\python.exe tools/provision_modern.py --release path\to\release --mode migrate --board lilygo_t_display_s3_pro
```

Mutation additionally requires the exact signed source ref, `--execute`,
`--confirm-erase`, an explicit serial port, `esptool` 5.x, `mpremote`, and a
durable private workspace outside the checkout. Follow the authenticated
`MIGRATION.md` shipped in the release. The workflow is resumable; retain the
workspace until a final `--resume` confirms healthy completion.

Direct migration supports stable v0.13 or newer on the exact legacy firmware
and a recognized layout. Validate a captured backup without mutation with
`tools/check_modern_support_window.py --backup PATH`. Older or unknown layouts
require clean provisioning and selective reviewed restore, not intermediate
releases. See [`profiles/lvgl-modern-migration.md`](profiles/lvgl-modern-migration.md).

## Optional physical modern-board work

The touchscreen launcher and IDE backlight behavior require a focused physical
smoke before they can enter a release candidate's qualification record. Follow
[`tests/MODERN_TOUCHSCREEN_QUALIFICATION.md`](tests/MODERN_TOUCHSCREEN_QUALIFICATION.md)
and bind results to the exact candidate and firmware identity. The historical
`modern-v0.14.8` evidence predates this feature and cannot be reused.

The existing modern helpers can recheck the underlying display, touch, and
ownership boundary without installing or flashing anything:

```powershell
.\.venv\Scripts\python.exe tools/phase5_device.py --port COMx probe
.\.venv\Scripts\python.exe tools/phase5_device.py --port COMx touch --seconds 20
.\.venv\Scripts\python.exe tools/phase5_device.py --port COMx renderer-cycle --iterations 100
```

These probes supplement the interactive launcher/backlight checklist; they do
not qualify a filesystem candidate by themselves.

## Optional physical legacy-board work

Close programs holding the serial port and discover the current port:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Name, PNPDeviceID
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx probe
```

The qualified legacy target is the T-Display-S3 Pro running the exact firmware
hash in `profiles/legacy-mp123.json`. Record protected-state digests before and
after installation without printing file contents:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx protected-digest
```

Stage an extracted candidate over serial with:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 30 serial-install `
    --release-dir C:\path\to\extracted-artifact `
    --version descriptive-smoke-version
```

Keep the board on reliable power and do not open the port from another program.
Use the appropriate phase document for any required visual, touch, network,
fault, recovery, or benchmark observations.

## Credentials and private data

An ignored root `settings.json` may supply local 2.4 GHz Wi-Fi credentials to
serial helpers:

```json
{"ssid": "YOUR_2_4_GHZ_NETWORK", "password": "YOUR_PASSWORD"}
```

Confirm it is ignored with `git check-ignore -v settings.json`. Never put real
credentials, student files, access-point identities, private backups, or raw
device captures in documentation, fixtures, issues, or command transcripts.

Ignored/non-source data includes `build/`, root `dist/` and `release/`, web
`dist/`, `node_modules/`, virtual environments, Python caches,
`_example_installation/`, `hardware_test_artifacts/`, and root `settings.json`.
The sanitized legacy fixture is `tests/fixtures/legacy_mp123`.

## Release safety

- A CI artifact, tag, or draft is not a stable release.
- Legacy releases require the protected `legacy-release` workflow and an exact
  candidate-bound physical gate.
- Modern releases require the protected qualification and `modern-release`
  workflows and all six physical gates.
- Never mix legacy and modern release assets or feeds.
- Installed versions commit only after a healthy boot; recovery and future OTA
  must remain available after every promoted release.

Current architecture, decisions, and open work are summarized in
[`PROJECT_NOTES.md`](PROJECT_NOTES.md).
