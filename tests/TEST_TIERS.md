# TartLab test tiers

Use the smallest environment that can establish a claim. Host tests provide
fast feedback but do not replace physical hardware qualification.

## Tier 0: build and static checks

CI verifies deterministic builds, Python compilation, archive ownership,
hashes, provenance, size budgets, firmware locks, and profile/feed policy.
Important checks include:

- `tools/pydevices_inventory.py`: partitions the locked legacy vendor payload
  by conservative static reachability.
- `tools/pydevices_upstream.py`: validates the reviewed mapping to exact
  upstream commits without changing the payload.
- `tools/vendor_pydevices.py`: generates the pinned, licensed, 71-file
  compatibility payload used by the promoted legacy builder.
- `tools/modern_firmware.py check`: validates the selected modern firmware
  lock, archived artifact, provenance, and evidence bindings.
- `tools/check_modern_profile.py`: validates the modern filesystem profile and
  isolated release machinery.
- `tools/check_release_feed_isolation.py`: compares checked-in profile policy
  with both live public release feeds without mutation.

These are source and policy claims, not hardware claims.

## Tier 1: CPython virtual device

Run the complete hardware-free suite:

```text
python -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_phase5 tests.test_modern_profile tests.test_phase6 tests.test_phase6_provisioning tests.test_virtual_device tests.test_platform tests.test_headless_ide -v
```

The suite exercises real TartLab update, migration, recovery, startup, and IDE
logic against isolated host filesystems and injected platform/network objects.
It covers protected-state preservation, interrupted installs, staged resume,
health-gated version commits, clean modern provisioning, v0.13 migration,
support-window rejection, profile/feed isolation, startup routing, and
headless IDE route registration.

It does not emulate ESP32 flash physics, MicroPython heap constraints, reset
behavior, GPIO, display/touch, or radio behavior.

## Tier 2: pinned MicroPython compatibility

CI builds MicroPython v1.23.0 at commit
`a61c446c0b34e82aeb54b9770250d267656f2b7f` and its `mpy-cross`. It compiles
the generated legacy distribution and candidate vendor modules for the ESP32
`xtensawin` emitter, then runs the compatibility probes with the pinned Unix
interpreter.

After building those tools and a distribution, run locally with:

```text
python tools/run_micropython_compat.py --micropython PATH/TO/micropython --mpy-cross PATH/TO/mpy-cross --dist build/one/dist --candidate-runtime build/vendor/pydevices-candidate/runtime
```

This catches parser, language, import, JSON, hashing, and core filesystem API
differences. The Unix port still uses host storage and stubs; it makes no ESP32
hardware claim. CI runs this tier on Ubuntu, so local WSL use is optional.

## Tier 3: focused physical smoke

Use the qualified T-Display-S3 Pro after changes to startup, board selection,
display/touch, networking, memory-sensitive code, firmware-facing APIs, or
recovery. Test the affected physical behavior plus a boot/IDE sanity check.

Relevant records and helpers:

- `PHASE3_HARDWARE.md`: legacy platform-abstraction smoke.
- `PHASE4_HARDWARE.md`: generated legacy PyDevices comparison.
- `PHASE5_HARDWARE.md`: modern lifecycle and renderer ownership.
- `PHASE5_BENCHMARKS.md`: locked legacy/modern graphics matrix.
- `tools/phase1_device.py`, `tools/phase5_device.py`, and
  `tools/phase5_benchmark.py`: repeatable probes.

Successful driver calls or idle touch polls do not replace human color,
orientation, touch-region, and browser observations.

## Tier 4: physical release qualification

Before promotion, qualify the exact tag/candidate, board, and firmware for its
profile. The gate owns claims about flash and reset behavior, PSRAM, GPIO,
display/touch, Wi-Fi/AP, browser behavior, direct OTA, recovery, interruption,
protected state, feed isolation, and future update access.

- Legacy qualification follows `PHASE2_HARDWARE.md` and publishes only through
  the protected legacy workflow to `tdhoward/TartLab`.
- Modern qualification follows `PHASE6_PROVISIONING.md` and
  `PHASE6_MODERN_QUALIFICATION.md` and publishes only through the protected
  modern workflow to `tdhoward/TartLab-modern-releases`.

Passing Tiers 0–2 means a candidate is ready for hardware testing. It is not a
release authorization.
