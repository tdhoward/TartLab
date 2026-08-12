# Development computer transfer handoff

This is the restart point for moving TartLab development to another computer.
The Git repository and GitHub Actions are the portable source of truth. Do not
copy ignored build directories or private device captures as a substitute for a
clean checkout.

## Repository checkpoint

- Remote: `https://github.com/tdhoward/TartLab.git`
- Working branch: `ArchitectureOverhaul`
- Last implementation and hardware-smoke commit before this handoff:
  `9bee3f12786a7220fafbf492f655f4b4e0aca384`
- CI for that checkpoint:
  <https://github.com/tdhoward/TartLab/actions/runs/31630391840> (passed)
- Phase 3 platform-abstraction smoke record:
  [`tests/PHASE3_HARDWARE.md`](tests/PHASE3_HARDWARE.md)
- Release qualification record and remaining gate:
  [`tests/PHASE2_HARDWARE.md`](tests/PHASE2_HARDWARE.md)

The handoff documentation commit is expected to be newer than `9bee3f1`. After
cloning, the tip of `origin/ArchitectureOverhaul` is authoritative. Confirm the
exact tip and its CI result rather than resetting back to the checkpoint above.

The Phase 3 candidate was deliberately **not promoted**. Do not invoke the
promotion workflow or describe this branch as a stable release.

## Clean setup on the new Windows computer

Install Git, Python, and Node.js, then use PowerShell:

```powershell
git clone https://github.com/tdhoward/TartLab.git
Set-Location TartLab
git switch ArchitectureOverhaul
git pull --ff-only
git status --short --branch
git log -1 --oneline --decorate

py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-build.txt
npm ci --prefix src/ide/www
npm run build --prefix src/ide/www
.\.venv\Scripts\python.exe -m unittest tests.test_phase1 tests.test_phase2 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
```

Before the first push from the new computer, configure the intended Git author
name/email and authenticate `origin` using Git Credential Manager, an SSH
remote, or another normal GitHub credential flow. Do not put a token in a
tracked file or command transcript.

The reproducible legacy profile pins Python 3.11.9 and Node 20.19.4 in
[`profiles/legacy-mp123.json`](profiles/legacy-mp123.json). Use those exact versions for byte-reproducible
candidate builds. Ordinary source inspection and host tests may work on newer
versions, but that is not evidence that a release matches CI.

CI builds the pinned MicroPython v1.23.0 Unix interpreter and `mpy-cross` on
Ubuntu. A local Windows build of full MicroPython is not required. See
[`tests/TEST_TIERS.md`](tests/TEST_TIERS.md) if a local Tier 2 run is needed; use WSL/Linux for that
runner while keeping physical serial access on Windows unless the USB device is
deliberately attached to WSL.

### Recreate a local candidate

Build outputs are deliberately ignored. Recreate them after the web build:

```powershell
.\.venv\Scripts\python.exe makedist.py --output build/legacy/dist --clean --skip-web-build
.\.venv\Scripts\python.exe release.py --dist build/legacy/dist --output build/legacy/release --clean --version local-transfer-check
.\.venv\Scripts\python.exe tools/check_legacy_release.py --dist build/legacy/dist --release build/legacy/release
```

For an exact CI candidate, open the successful `Legacy release CI` run whose
head SHA matches `git rev-parse HEAD`, then download
`legacy-mp123-<full-commit-sha>`. Artifacts are retained for 30 days. If one has
expired, rerun the workflow or push the next validated commit; do not rely on an
old local ZIP. The serial installer validates `checksums.json`, the manifest,
every package hash, and every tar before modifying managed files.

## Physical board continuation

The Phase 3 board was left in this state:

- Firmware: exact MicroPython v1.23.0 generic ESP32-S3 octal-SPIRAM image.
- Installed TartLab version: `phase3-smoke-ae9c861`.
- Final recorded boot state: healthy IDE mode, zero consecutive failures, and
  empty update state.
- Protected `/app.py`, `/hdwconfig.py`, `/device`, `/files/user`, and selected
  application hashes matched their pre-install values.
- The last check on the old computer returned HTTP 200 from the IDE.

The old `COM6` name and `192.168.137.192` station address are machine/network
specific. Do not assume either after the move. Connect the board directly,
close Thonny or any other program holding the serial port, and discover it:

```powershell
Get-CimInstance Win32_SerialPort |
    Select-Object DeviceID, Name, PNPDeviceID
```

Install the hardware helper's only additional Python dependency and probe the
discovered port:

```powershell
.\.venv\Scripts\python.exe -m pip install pyserial==3.5
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx probe
```

Replace `COMx` explicitly. A successful probe must still report MicroPython
1.23.0, octal-SPIRAM hardware, installed version `phase3-smoke-ae9c861`, and a
normal file/heap inventory. If the board cannot join a configured 2.4 GHz
network, its tested fallback is an open TartLab access point with the IDE at
`192.168.4.1`; read the board display for its current network and address. The
old station IP is not portable.

The device retains its own settings. Do not export Wi-Fi credentials into the
repository, terminal logs, or this document. Avoid using **Check for updates**
while resuming development: the smoke candidate is not a stable release and the
update button follows stable-release selection rules.

If another candidate must be staged directly from an extracted CI artifact:

```powershell
.\.venv\Scripts\python.exe tools/phase1_device.py --port COMx --timeout 30 serial-install `
    --release-dir C:\path\to\extracted-artifact `
    --version descriptive-smoke-version
```

The acknowledged serial transfer is intentionally slow (about eight minutes
for the current artifact). Keep the board powered and do not open the port from
another program. Run `protected-digest` before and after any installation and
record the result without printing settings or student-file contents.

## Data that intentionally does not transfer through Git

The following paths are ignored and may contain generated, bulky, private, or
secret material:

- `build/`, `dist/`, `release/`, web `dist/`, and all `node_modules/` folders;
- `.venv/` and Python caches;
- `_example_installation/`, the original private deployed-device capture;
- `hardware_test_artifacts/`, including local raw serial logs and evidence;
- root `settings.json`, which may contain plaintext Wi-Fi credentials.

Nothing in those paths is required to resume Phase 4. The sanitized legacy
fixture is tracked under
[`tests/fixtures/legacy_mp123`](tests/fixtures/legacy_mp123), and the durable
hardware outcomes are recorded in
[`tests/PHASE1_HARDWARE.md`](tests/PHASE1_HARDWARE.md),
[`tests/PHASE2_HARDWARE.md`](tests/PHASE2_HARDWARE.md), and
[`tests/PHASE3_HARDWARE.md`](tests/PHASE3_HARDWARE.md).

If private raw evidence must be retained for audit purposes, move it separately
using encrypted storage and keep it outside the repository. It is not needed on
the new development computer for normal continuation.

## Exact next development step

Resume at **Phase 4, item 1** in
[`PROJECT_NOTES.md`](PROJECT_NOTES.md): inventory which modules in the embedded
`src/lib/pydevices` tree TartLab actually imports at runtime.

The first Phase 4 change should be evidence and tests, not a vendor replacement:

1. Produce a tracked static import/reachability inventory beginning at
   `src/hdwconfig.py`, `src/configs/t_display_s3_pro.py`, the legacy platform
   adapter, and shipped examples.
2. Separate core startup/IDE dependencies from optional student-example and
   board-adapter dependencies.
3. Compare the reachable set with `vendor/legacy-pydevices.lock.json` and the
   generated distribution inventory.
4. Add a regression check or machine-readable allowlist so unused modules
   cannot silently re-enter the release payload.
5. Only after the current dependency set is established should upstream
   `pydisplay`, `micropython-hardware`, and `pygraphics` equivalents be mapped.

Do not change firmware, replace the vendored runtime, prune files, or promote a
release merely to begin this inventory. Preserve the legacy platform contract
and the exact MicroPython 1.23.0 compatibility profile while collecting the
evidence.

## Before retiring the old computer

Run this final checklist:

```powershell
git status --short --branch
git log -1 --oneline --decorate
git rev-parse HEAD
git rev-parse origin/ArchitectureOverhaul
```

The worktree should be clean and the two revisions should match. Confirm that
the matching GitHub Actions run passed. Then separately decide whether private
ignored evidence should be encrypted and archived or securely discarded; do
not force-add it to Git.
