# TartLab test tiers

TartLab uses the smallest test environment that can establish each claim. Host
tests provide fast feedback, but they do not replace the physical release gate.

## Tier 0: build and static checks

Run deterministic builds, source compilation, archive ownership, provenance,
hash, size-budget, and PyDevices import/payload inventory checks on every
change. These checks require neither a virtual device nor physical hardware and
run in `legacy-ci.yml`.

`tools/pydevices_inventory.py` follows static imports from the core platform,
the default T-Display-S3 Pro adapter, and every shipped Python example. Its
reviewed allowlist partitions every locked vendor file into one reachable
category or an explicitly retained-unreachable set. CI compares the generated
`dist/lib/pydevices` tree with the same partition. This is a conservative static
claim, not proof that every runtime-dependent import path has executed.

`tools/pydevices_upstream.py` validates the separate current-upstream audit:
full repository commits and license hashes, a unique classification for every
reachable file, and the explicit finding that none is a drop-in legacy
replacement. It performs no network fetch and does not change release content.

`tools/vendor_pydevices.py` builds the separately pinned migration candidate
from exact git objects and an explicit source/destination allowlist. Tier 0
checks its pin agreement, audited-source coverage, patch and TartLab adapter
hashes, Python host compilation, dependency allowlists, licenses, provenance,
deterministic runtime identifier, and size report. The candidate contains 65
upstream files plus five compatibility adapters and the retained QOI reader.
`tests/pydevices_candidate_compat.py` exercises the legacy import/API surface
against the generated runtime. The source output remains under ignored
`build/vendor`; the promoted release builder accepts it only when both its
source identity and resulting `mpy` payload identity match the physically
qualified values in `profiles/legacy-mp123.json`.

`tools/modern_firmware.py check` validates the separate Phase 5 reference lock:
the binding commit, ESP32 submodule graph, target arguments, reviewed local
inputs, manifest digest of the Linux/amd64 ESP-IDF build container, archived
artifact hash, two-clean-build provenance, and exact reviewed lifecycle and
benchmark evidence hashes. CI does not rebuild the large firmware image or
repeat the physical work; this tier validates the recorded claim rather than
creating a new hardware claim.

`tools/check_modern_profile.py` is the corresponding filesystem-profile gate.
It verifies that the current `lvgl-modern` profile remains promotion gated,
checks the hash-bound adapter and isolated release machinery, builds the
ordinary TartLab filesystem twice, compares every output file, and compiles
each generated Python source. The separate builder, promotion workflow, and
adult provisioning transaction target only
`tdhoward/TartLab-modern-releases`; `tdhoward/TartLab` GitHub Releases remain
reserved for the `legacy-mp123` profile.

The protected `attest-modern-candidate.yml` workflow is the Tier 4 handoff. It
creates a reproducible, tag-bound, signed candidate artifact for physical
qualification without publishing a release. Adult provisioning verifies that
qualification workflow's identity; final release verification separately pins
the promotion workflow's identity.

## Tier 1: CPython virtual device

Run:

```text
python -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_phase5 tests.test_modern_profile tests.test_phase6 tests.test_phase6_provisioning tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
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

The separate Phase 6 provisioning transaction tests exercise clean modern
provisioning and direct v0.13 migration through a host directory transport.
They verify protected-state preservation, selector translation, isolated feed
state, exact legacy-firmware readback enforcement, pending-health commit, and
resumption after a simulated USB loss. The support-window policy additionally
proves that v0.13 root-v1 and newer canonical layouts are eligible while older,
prerelease, and unknown layouts fail before erase. See
`PHASE6_PROVISIONING.md`; physical
flash, display, touch, network, and recovery observations remain Tier 4.

The updater tests also exercise the `lvgl-modern` object manifest through the
normal OTA path, prove that the combined firmware asset is not downloaded to
the device, and require both normal and recovery clients to reject cross-profile
feeds. `tools/check_modern_qualification.py` rejects incomplete or
candidate-mismatched Phase 6 promotion evidence, including a different
support-window policy hash. These are policy and virtual
filesystem claims; see `PHASE6_MODERN_QUALIFICATION.md` for the remaining
physical observations.

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
ESP32 port's `xtensawin` native emitter, compiles every generated Phase 4
candidate module for the same target, and runs `tests/micropython_compat.py`
plus `tests/pydevices_candidate_compat.py` with the pinned interpreter.

The runtime probe executes the real state/layout migration, early boot recovery
decisions, recovery manifest/path/hash helpers, and legacy platform adapter. It
uses an isolated host directory for device-style paths and injected platform
objects; it performs no network access and imports no board drivers. This tier
catches MicroPython parser, core-language, import, JSON, hashing, and host
filesystem API differences that CPython may accept.

After building the pinned tools and a distribution, the direct command is:

```text
python tools/run_micropython_compat.py --micropython PATH/TO/micropython --mpy-cross PATH/TO/mpy-cross --dist build/one/dist --candidate-runtime build/vendor/pydevices-candidate/runtime
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
`PHASE4_HARDWARE.md` records the 2026-08-16 and 2026-08-17 generated-PyDevices
comparisons, including the accepted bounded regressions and completed
touch/color, OTA, recovery, and fault cases that support the promoted vendor
identity. `tools/phase1_device.py boot-timing` and `pydevices-benchmark` provide
repeatable samples, but idle touch polls and successful driver calls are not
human touch or visual assertions.

`PHASE5_HARDWARE.md` is the separate modern-firmware lifecycle gate.
`tools/phase5_device.py` records runtime/module identity, native dirty-transfer
completion, renderer ownership transitions, heap behavior, repeated
initialization, and touch samples. Its automated output does not replace the
required human color, orientation, touch-region, browser, and recovery
observations.

`PHASE5_BENCHMARKS.md` records the locked legacy/modern item 5 comparison.
`tools/phase5_benchmark.py collect` runs identical geometry, clock, asset,
buffer-count, deadline, and workload instrumentation on a provisioned physical
profile; `compare` rejects matrix drift before summarizing the samples. Raw
REPL collection pauses the foreground IDE, so its CPU-availability result is a
service-headroom proxy rather than live browser latency.

## Tier 4: physical release qualification

Before stable promotion, run the complete applicable hardware gate in
`PHASE2_HARDWARE.md` on the exact pinned firmware. This tier remains responsible
for PSRAM, GPIO, display byte order, touch calibration, Wi-Fi/AP behavior,
actual flash and reset behavior, a real direct OTA/recovery cycle, and confirming
that the candidate targets only its profile's release repository. Legacy
promotion targets `tdhoward/TartLab`; future modern promotion targets
`tdhoward/TartLab-modern-releases`.

Passing Tiers 0–2 means the candidate is ready for hardware testing. It does not
mean the legacy hardware profile is release-qualified.
