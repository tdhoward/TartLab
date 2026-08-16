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
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
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
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
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
.\.venv\Scripts\python.exe release.py --dist build/legacy/dist --output build/legacy/release --clean --version local-development-check
.\.venv\Scripts\python.exe tools/check_legacy_release.py --dist build/legacy/dist --release build/legacy/release
```

`release.py` requires a clean Git worktree for a normal candidate. The
`--allow-dirty` option is available for local diagnostics, but artifacts built
that way are not promotion eligible.

CI builds the pinned MicroPython v1.23.0 Unix interpreter and `mpy-cross`, runs
the host and compatibility suites, builds the release twice, and requires the
two outputs to be byte-identical. For a CI-produced candidate, use the
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
