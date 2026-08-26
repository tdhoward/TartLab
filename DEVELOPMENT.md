# TartLab development setup

This guide describes how to prepare a computer for TartLab source development,
host testing, release-candidate builds, and optional work with a physical
LilyGO T-Display-S3 Pro. The Git repository and GitHub Actions are the source
of truth; generated output and device-local data are not development inputs.

## Supported host environment

The primary hardware-development environment is Windows with PowerShell. Source
work and host tests can also run on Linux or macOS. Use:

- Git;
- Python 3.10 through 3.14 (`>=3.10,<3.15`);
- Node.js 20 or newer;
- npm, supplied with Node.js.

The compatibility ranges are recorded in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json), and the Node.js
minimum is also declared in [`src/ide/www/package.json`](src/ide/www/package.json).
Exact Python and Node.js patch versions are not required. The
payload-transforming `python-minifier==3.2.0` dependency and the npm dependency
graph remain locked because they directly affect build output. Release metadata
records the actual host-tool versions used.

Windows is recommended when controlling a board over USB serial. WSL or another
Linux environment is optional for running the Tier 2 MicroPython Unix
compatibility test locally; CI already runs that tier on Ubuntu.

## Firmware artifact integrity

Flashable images live under [`firmware`](firmware/README.md), outside the
filesystem release pipeline. Verify their exact byte sizes and SHA-256 digests
before hardware work or a commit that touches them:

```powershell
.\.venv\Scripts\python.exe tools/check_firmware_artifacts.py
```

The `legacy-mp123` artifact is the physically qualified baseline. The
`lvgl-modern` profile remains experimental and must not be presented as a
stable migration target. Its exact Phase 5 reference now has reproducible-build
and hardware evidence, and the completed alternative-stack comparison selected
it as the basis for future modern-firmware work. Production promotion still
requires an adult-admin migration path and the Phase 6 release gates.

## Modern graphics development direction

The modern target is not an LVGL-only replacement for the legacy framebuffer
path. It must contain one DMA-capable native panel transport with two mutually
exclusive TartLab rendering modes:

- LVGL UI mode for the IDE, menus, controls, text, and UI-oriented apps.
- A direct framebuffer/dirty-rectangle surface for games and frame-paced
  animation.

TartLab owns transitions between the modes. A transition must stop or pause the
current renderer, wait for outstanding display transfers, transfer ownership,
and redraw/invalidate the destination renderer. Do not let an LVGL flush race a
direct game transfer, and do not use private upstream driver fields as the game
API.

Use `lvgl-micropython/lvgl_micropython` and its ESP32 `lcd_bus` as the first
reproducible performance reference. Compare it on identical hardware with a
PyDevices `lvgl-micropython` + `displayif` build before selecting the production
firmware. The comparison must report full-frame and partial-region throughput,
sprite/scroll and LVGL animation frame times, render/transfer overlap, missed
deadlines, heap stability, soft-reset behavior, and CPU availability while the
IDE/network services remain active.

For the 480 x 222 RGB565 panel, one frame is 213,120 bytes. A 60 MHz SPI link
needs approximately 28.4 ms merely to put those bytes on the wire, so the
theoretical full-screen ceiling is about 35 FPS before any other overhead.
Prioritize dirty rectangles, DMA/double buffering, native draw operations,
preconverted RGB565 assets, and allocation-free steady-state loops. LVGL being
present in firmware is not evidence that TartLab is using an accelerated path.

The complete rationale and Phase 5 gate are recorded in
[`PROJECT_NOTES.md`](PROJECT_NOTES.md#phase-5-prototype-modern-lvgl-firmware-separately).

### Pinned Phase 5 reference

The first reference recipe is machine-checked separately from the archived,
unqualified 2025 binary. It pins the complete direct gitlink set at the selected
`lvgl_micropython` commit, the T-Display-S3 Pro build arguments, and the
Linux/amd64 manifest digest of Espressif's ESP-IDF 5.5.1 container. Docker is
required only to execute the firmware build, not for normal TartLab development.

From the repository root, validate the lock, create a detached clean checkout,
and inspect or run the exact container command with:

```powershell
.\.venv\Scripts\python.exe tools/modern_firmware.py check
.\.venv\Scripts\python.exe tools/modern_firmware.py checkout --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py check --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py command --source build/phase5/lvgl-micropython
.\.venv\Scripts\python.exe tools/modern_firmware.py build --source build/phase5/lvgl-micropython
```

`checkout` refuses to reuse a destination, and `build` refuses a wrong commit or
dirty source tree. The build command does not contain `deploy` or a serial port,
so it cannot flash a connected board. Its output remains an unqualified research
artifact. The pinned upstream tree contains the ST7796 display driver but no
CST226 input driver, so TartLab supplies the separately reviewed, hash-bound
`firmware/lvgl-modern/drivers/cst226.py` adapter through the public upstream
pointer and native I2C APIs. The build wrapper also fixes the application
partition at 4 MiB and bridges the official ESP-IDF container's Python
environment to the path expected by the pinned upstream merger.

The Phase 5 application adapter is selected explicitly; it does not alter the
qualified legacy board configuration. On an experimental modern device,
`/hdwconfig.py` selects it with:

```python
from t_display_s3_pro_modern import *
```

IDE mode then uses the LVGL status view. App startup calls the platform's game
mode transition; app code obtains the 480 x 222 direct surface from
`get_platform().game_surface` (or from the idempotent `enter_game_mode()` call).
Its `write(buffer, x, y, width, height)` API accepts big-endian,
panel-wire-order RGB565 data. Reusable native DMA memory comes from
`allocate_buffer(width, height)`. A write waits for completion by default;
callers opting into `wait=False` must not touch or release the buffer until
`surface.wait()` returns. `get_platform().enter_ui_mode()` performs the inverse
drain-and-redraw transition. These adapters are host-tested but remain
separate from the legacy path. The exact hash-bound version has passed the
Phase 5 item 4 lifecycle and item 5 benchmark gates.

The archived Phase 5 output was reproduced byte-for-byte from two independent
clean checkouts. The exact checkpoint and hash-bound application adapter have
passed the lifecycle and comparative hardware gates in
`tests/PHASE5_HARDWARE.md` and `tests/PHASE5_BENCHMARKS.md`. This makes it a
hardware-qualified research reference, not a production selection or release
input. Run `build` only on a fresh checkout; the upstream build initializes
submodules and modifies generated source state as part of compilation.

### Phase 5 comparative benchmark

Provision each exact firmware family on the same T-Display-S3 Pro, then collect
and compare the locked 480 x 222, 240 MHz CPU, 60 MHz SPI matrix with:

```powershell
.\.venv\Scripts\python.exe tools/phase5_benchmark.py collect --port COM6 --profile legacy --samples 12 --switches 25 --output hardware_test_artifacts/phase5-item5/legacy.json
.\.venv\Scripts\python.exe tools/phase5_benchmark.py collect --port COM3 --profile modern --samples 12 --switches 25 --output hardware_test_artifacts/phase5-item5/modern.json
.\.venv\Scripts\python.exe tools/phase5_benchmark.py compare --legacy hardware_test_artifacts/phase5-item5/legacy.json --modern hardware_test_artifacts/phase5-item5/modern.json --output hardware_test_artifacts/phase5-item5/comparison.json
```

Collection interrupts the foreground application through the raw REPL, changes
the displayed pixels, and restores UI ownership. It does not install files or
flash firmware. The result includes full-frame and 10/25/50% dirty transfers,
solid fill, sprite, scroll, TartLab widgets, LVGL animation, render/transfer
overlap, deadline misses, a CPU-headroom proxy, GC bytes, and repeated mode
switches. See `tests/PHASE5_BENCHMARKS.md` for the exact results and the limits
on interpreting live network availability and allocation counts.

### Phase 5 PyDevices/displayif comparison

The separately pinned alternative is a reproducible, physically benchmarked,
research-only rejected candidate. Validate its source graph, archived result,
and hash-bound evidence with:

```powershell
.\.venv\Scripts\python.exe tools/pydevices_modern_firmware.py check --source-root build/phase5-second
.\.venv\Scripts\python.exe -m unittest tests.test_phase5_pydevices -v
```

Its explicit application profile is selected with
`from t_display_s3_pro_pydevices_modern import *`. The adapter exposes the same
logical 480 x 222 `RGB565_BE` dirty-rectangle surface and ownership transitions,
but displayif's current SPI write is blocking. Its capability map therefore
reports no asynchronous direct transfer or render/transfer overlap. See
`tests/PHASE5_PYDEVICES.md` for reproducibility, hardware-gate, and selection
evidence. The first `lvgl_micropython`/`lcd_bus` repository wins the Phase 5
stack selection; this does not promote it or change the legacy release channel.

## Clean checkout and bootstrap

The commands below use the current `ArchitectureOverhaul` development branch.
For work based on another branch, substitute that branch explicitly.

```powershell
git clone https://github.com/tdhoward/TartLab.git
Set-Location TartLab
git switch ArchitectureOverhaul
git pull --ff-only
git status --short --branch

python --version
node --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-build.txt
npm ci --prefix src/ide/www
npm run build --prefix src/ide/www
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
```

On Linux or macOS, use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe`.

Before pushing, configure the intended Git author name and email and
authenticate the `origin` remote through Git Credential Manager, SSH, or
another normal GitHub credential flow. Never store an access token in a
tracked file or command transcript.

## Normal development checks

Reinstall JavaScript dependencies with `npm ci`, not `npm install`, whenever
the lockfile changes or the local dependency tree may be stale. Build the web
application with:

```powershell
npm run build --prefix src/ide/www
```

Run the hardware-free test suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
```

The exact tier boundaries and the optional local Tier 2 command are documented
in [`tests/TEST_TIERS.md`](tests/TEST_TIERS.md). Host tests do not replace a
physical smoke test or release-qualification gate when a change affects
hardware-facing behavior.

## Build a local release candidate

Build outputs are ignored and must be recreated from source. After the web
build, run:

```powershell
.\.venv\Scripts\python.exe makedist.py --output build/legacy/dist --clean --skip-web-build
.\.venv\Scripts\python.exe tools/pydevices_inventory.py --dist build/legacy/dist
.\.venv\Scripts\python.exe tools/pydevices_upstream.py
.\.venv\Scripts\python.exe tools/vendor_pydevices.py --fetch --output build/vendor/pydevices-candidate --clean
.\.venv\Scripts\python.exe -B tests/pydevices_candidate_compat.py build/vendor/pydevices-candidate/runtime src/files/assets/test.qoi
.\.venv\Scripts\python.exe tools/build_promoted_release.py --base-dist build/legacy/dist --candidate build/vendor/pydevices-candidate --output build/promoted --version descriptive-version --mpy-cross path\to\v1.23.0\mpy-cross --clean
.\.venv\Scripts\python.exe tools/check_legacy_release.py --dist build/promoted/dist --release build/promoted/release
.\.venv\Scripts\python.exe tools/build_phase4_test_release.py --base-dist build/legacy/dist --candidate build/vendor/pydevices-candidate --output build/phase4/candidate --version descriptive-research-version --mpy-cross path\to\v1.23.0\mpy-cross --clean
```

The promoted builder requires a clean Git worktree for a normal candidate and
rejects source or bytecode that differs from the physically qualified Phase 4
identities. Direct `release.py` builds from the checked-in historical vendor
tree are diagnostic-only and are rejected by its normal CLI path. The
`--allow-dirty` option remains available to lower-level diagnostic builds, but
artifacts built that way are not promotion eligible. The PyDevices inventory check compares the
generated vendor payload with the reviewed Phase 4 reachability partition; it
does not rely on an old root `dist` directory. The upstream check validates
that every reachable file has a reviewed classification against full upstream
commit pins; it neither fetches sources nor changes the runtime payload. The
candidate vendor command fetches only those pins, selects the explicit
upstream allowlist, adds the separately hash-pinned TartLab compatibility
surface, and emits provenance and size reports under ignored `build/vendor`.
The compatibility probe checks the protected board path, legacy graphics,
keys, keypad, BMP, QOI, and scalar broker behavior without loading hardware.
The inventory, upstream, vendor, and probe commands do not modify
`src/lib/pydevices`, `dist`, or a release archive. The Phase 4 builder creates a
separate, guarded comparison release under its requested output. It minifies
the exact source runtime and uses the supplied pinned MicroPython 1.23
`mpy-cross` to package all 71 modules for `xtensawin`; its metadata records the
compiler hash and both source and packaged runtime identities. The artifact is
always research-only. The promoted builder applies the same transformation but
binds it to the source and packaged identities in the legacy release profile.

CI builds the pinned MicroPython v1.23.0 Unix interpreter and `mpy-cross`, runs
the host and compatibility suites, builds the promoted-vendor release twice,
and requires the two outputs to be byte-identical. For a CI-produced candidate, use the
`legacy-mp123-<full-commit-sha>` artifact from a successful `Legacy release CI`
run whose head SHA matches the intended commit.

## Local Wi-Fi credentials

The root `settings.json` file is ignored by Git and may be used as the local
credential input for the serial helper:

```json
{
  "ssid": "YOUR_2_4_GHZ_NETWORK",
  "password": "YOUR_PASSWORD"
}
```

Confirm that the file is ignored before adding real values:

```powershell
git check-ignore -v settings.json
```

Do not paste real credentials into documentation, issues, test fixtures,
terminal transcripts, or hardware evidence. TartLab boards require a visible
2.4 GHz network; a hidden or 5 GHz-only SSID will not appear in the startup
scan.

## Optional physical-board setup

Connect the board directly and close Thonny or any other program that may hold
the serial port. Discover available ports rather than assuming a saved COM
name:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
Get-CimInstance Win32_SerialPort |
    Select-Object DeviceID, Name, PNPDeviceID
```

Install the serial dependency in the project virtual environment and probe the
selected port:

```powershell
.\.venv\Scripts\python.exe -m pip install pyserial==3.5
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx probe
```

Replace `COMx` explicitly. The qualified legacy hardware profile is a LilyGO
T-Display-S3 Pro running the exact MicroPython v1.23.0 generic ESP32-S3
octal-SPIRAM firmware recorded in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json). The installed
TartLab version depends on the candidate being tested.

Apply the ignored local Wi-Fi credential file with:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 30 wifi-update --credentials-file settings.json
```

The board display reports its current network and address. If it cannot join a
configured network, the tested fallback is an open TartLab access point with
the IDE at `192.168.4.1`. COM names and station IP addresses are local and may
change between computers, USB ports, and networks.

Before and after any candidate installation, record the protected-state digest
without printing settings or student-file contents:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx protected-digest
```

To stage an extracted CI candidate over serial:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 30 serial-install `
    --release-dir C:\path\to\extracted-artifact `
    --version descriptive-smoke-version
```

The acknowledged serial transfer can take several minutes. Keep the board
powered and do not open the port from another program.

For repeatable Phase 4 timing samples after a healthy boot, use:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 75 boot-timing
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 75 pydevices-benchmark
```

The benchmark changes the display while it measures fills and frame writes.
It records idle touch polls but cannot replace a person checking displayed
colors and touching known screen locations.

## Generated, private, and device-local data

The following ignored paths are not portable source inputs:

- `build/`, root `dist/`, root `release/`, and web `dist/`;
- all `node_modules/` directories;
- `.venv/`, `venv/`, and Python caches;
- `_example_installation/`, which may contain a private device capture;
- `hardware_test_artifacts/`, including raw serial logs and evidence;
- root `settings.json`, which may contain plaintext Wi-Fi credentials.

Recreate generated dependencies and output from the tracked lockfiles and
scripts. Keep private device captures and raw evidence outside Git; if they
must be retained for audit purposes, use encrypted storage. The sanitized
legacy fixture is tracked under `tests/fixtures/legacy_mp123`, and durable
hardware outcomes are recorded in the `tests/PHASE*_HARDWARE.md` documents.

## Release safety and current work

CI artifacts are candidates, not stable releases. Stable promotion remains a
separate reviewed workflow gated by the physical qualification record in
[`tests/PHASE2_HARDWARE.md`](tests/PHASE2_HARDWARE.md) and the protected
`legacy-release` GitHub environment.

See [`PROJECT_NOTES.md`](PROJECT_NOTES.md) for the current architecture roadmap
and next implementation task. Do not infer release status or a development
starting point from an old local build directory or device installation.
