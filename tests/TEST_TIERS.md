# TartLab test tiers

TartLab uses the smallest test environment that can establish each claim. Host
tests provide fast feedback, but they do not replace the physical release gate.

## Tier 0: build and static checks

Run deterministic builds, source compilation, archive ownership, provenance,
hash, and size-budget checks on every change. These checks require neither a
virtual device nor physical hardware and run in `legacy-ci.yml`.

## Tier 1: CPython virtual device

Run:

```text
python -m unittest tests.test_phase1 tests.test_phase2 tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
```

`tests/virtual_device.py` maps MicroPython-style absolute paths into an isolated
host directory. It supplies deterministic `statvfs` capacity, journals writes,
renames, removals, and directory changes, and can raise an abrupt power-loss
event after a selected mutation. `VirtualPowerLoss` inherits directly from
`BaseException`, so device code cannot accidentally handle a simulated reset as
an ordinary update failure.

The virtual recovery tests start with the sanitized v0.13 fixture and use the
real current release archives, layout migration, recovery updater, early boot
recovery decision, and health-commit code. They currently cover:

- installation of the current candidate while protected content is retained;
- old-version retention until health and exactly-once version commit;
- interruption while clearing every `clear_first` target and on the first
  extraction write of every installable package;
- `update_installing` recovery selection after the simulated reset; and
- staged resume by a newly loaded recovery runtime.

`tests/headless_platform.py` implements the startup-facing platform contract
without importing board drivers. The startup tests run the real `main.run()`
logic against the virtual filesystem and cover:

- button-selected IDE and APP routing;
- successful IDE/APP health markers and pending-version commit;
- one-shot explicit recovery mode; and
- startup failure diagnostics, red error display, and recovery routing.

`tests/test_headless_ide.py` executes the complete real IDE module with the
headless platform and virtual filesystem. It verifies station-mode and fallback
open-AP initialization, hostname and credential selection, HTTP route
registration, startup/network/update view events, and runtime brightness-button
handling. Socket acceptance and browser rendering are not claimed by this tier.

These models are TartLab-specific. They do not emulate ESP32 flash physics,
MicroPython memory constraints, peripherals, or radio behavior.

## Tier 2: pinned MicroPython compatibility

CI checks out MicroPython v1.23.0 at commit
`a61c446c0b34e82aeb54b9770250d267656f2b7f` and builds its Unix interpreter and
`mpy-cross`. `tools/run_micropython_compat.py` verifies both tool versions,
compiles every Python module in the generated legacy distribution for the
ESP32 port's `xtensawin` native emitter, and runs
`tests/micropython_compat.py` with the pinned interpreter.

The runtime probe executes the real state/layout migration, early boot recovery
decisions, recovery manifest/path/hash helpers, and legacy platform adapter. It
uses an isolated host directory for device-style paths and injected platform
objects; it performs no network access and imports no board drivers. This tier
catches MicroPython parser, core-language, import, JSON, hashing, and host
filesystem API differences that CPython may accept.

After building the pinned tools and a distribution, the direct command is:

```text
python tools/run_micropython_compat.py --micropython PATH/TO/micropython --mpy-cross PATH/TO/mpy-cross --dist build/one/dist
```

The Unix port still uses host storage and platform stubs. It does not emulate
ESP32 flash behavior, heap/PSRAM limits, peripherals, reset behavior, or radio
AP/STA behavior, so it makes no physical-hardware compatibility claim. WSL can
provide this runner locally, but is optional because CI runs it on Ubuntu.
Physical serial control should remain on Windows unless there is a specific
reason to attach the USB device exclusively to WSL.

## Tier 3: physical smoke tests

Use the LilyGO T-Display-S3 Pro for focused checks after changes to startup,
hardware configuration, display/touch, networking, memory-sensitive code,
firmware-facing APIs, or recovery behavior. A smoke run should cover only the
affected physical claims plus a boot/IDE sanity check.

`PHASE3_HARDWARE.md` records the 2026-08-12 focused smoke for the platform
abstraction. Its explicitly unobserved manual items are not release claims.

## Tier 4: physical release qualification

Before stable promotion, run the complete applicable hardware gate in
`PHASE2_HARDWARE.md` on the exact pinned firmware. This tier remains responsible
for PSRAM, GPIO, display byte order, touch calibration, Wi-Fi/AP behavior,
actual flash and reset behavior, and a real direct OTA/recovery cycle.

Passing Tiers 0–2 means the candidate is ready for hardware testing. It does not
mean the legacy hardware profile is release-qualified.
