# TartLab test tiers

Use the smallest environment that can establish a claim. Host tests provide
fast feedback but do not replace physical hardware qualification.

Tiers describe test environments, not a mandatory ladder to repeat in full for
every release. TartLab keeps one public version and reuses applicable qualified
platform evidence under [`RELEASE_POLICY.md`](../RELEASE_POLICY.md). The current
promotion workflow still requires a complete candidate-bound record; automated
change classification and qualification reuse are not implemented yet.

## Selecting release tests

Every release runs the automated build, integrity, profile compatibility, and
update/recovery checks, plus tests of changed behavior. The table determines
additional testing from the complete candidate's impact, not its version bump.

| Change | Additional validation and physical scope |
| --- | --- |
| Browser wording, colors, or layout | Browser checks and production build; ordinarily no physical board testing. |
| Browser file saving, device commands, or update controls | Client/server integration checks; focused device checks for affected filesystem, networking, or update behavior. |
| App rules or assets | Relevant app tests and a focused play/exit smoke on a representative qualified board. |
| App rendering, input, timing, or memory use | Focused checks across affected board capabilities and display geometries, including resource margins and return to the IDE. |
| Shared platform, startup, or device-side IDE services | Fresh physical regression checks on affected boards; expand to Tier 4 claims as behavior requires. |
| Firmware, updater, recovery, provisioning, or installation contract | Full relevant physical qualification on affected boards, including interruption/resume, protected state, and supported update paths. |
| New board | Full board qualification, plus regressions on existing boards when shared behavior changes. |

Changes to a shared renderer or helper are platform changes even when motivated
by an example app. Dependency, toolchain, configuration, package-size, ownership,
and selection changes also contribute to the assessment. Test the candidate
against the supported installed update baselines, not only the previous version.

A routine app/browser release may carry forward the platform's power-loss and
recovery evidence when the implementation, installation contract, and relevant
limits remain qualified. It must still validate the complete new payload's
compatibility, sizes, staging/install space, and update behavior. Record which
claims are inherited and which have fresh results for each included board.

## Tier 0: build and static checks

CI verifies deterministic builds, Python compilation, archive ownership,
hashes, provenance, size budgets, firmware locks, and profile/feed policy.
Important checks include:

- `tools/check_board_catalog.py`: validates discovered modern board identities,
  lifecycle states, selectors, firmware hashes, and qualification evidence.
- `tools/pydevices_inventory.py`: partitions the locked legacy vendor payload
  by conservative static reachability.
- `tools/pydevices_upstream.py`: validates the reviewed mapping to exact
  upstream commits without changing the payload.
- `tools/vendor_pydevices.py`: generates the pinned, licensed, 71-file
  compatibility payload used by the promoted legacy builder.
- `tools/modern_firmware.py check`: validates the selected modern firmware
  lock, archived artifact, provenance, and evidence bindings.
- `tools/modern_board_firmware.py`: validates each board-specific frozen-driver
  recipe, local input hashes, reproducibility record, and candidate artifact.
- `tools/check_modern_profile.py`: validates the modern filesystem profile and
  isolated release machinery.
- `tools/check_release_feed_isolation.py`: compares checked-in profile policy
  with both live public release feeds without mutation.

These are source and policy claims, not hardware claims.

## Tier 1: CPython virtual device

Run the complete hardware-free suite:

```text
python -m unittest tests.test_phase1 tests.test_phase2 tests.test_phase4 tests.test_phase5 tests.test_modern_board_firmware tests.test_elecrow_dle06235b tests.test_board_catalog tests.test_modern_profile tests.test_phase6 tests.test_phase6_provisioning tests.test_virtual_device tests.test_platform tests.test_power tests.test_headless_ide tests.test_racer_entities -v
```

The suite exercises real TartLab update, migration, recovery, startup, and IDE
logic against isolated host filesystems and injected platform/network objects.
It covers protected-state preservation, interrupted installs, staged resume,
health-gated version commits, clean modern provisioning, v0.13 migration,
support-window rejection, profile/feed isolation, startup routing, and
headless IDE route registration. The modern startup coverage includes the
touchscreen timeout and chooser, confined app navigation, wake-touch
consumption, settings validation, brightness lifecycle, and preservation of
legacy button behavior.

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

Select qualified boards that cover the behavior and capabilities affected by
the change. Test that physical behavior plus boot and IDE access; app changes
also need successful exit or reset back to the IDE. Record why any
representative board selection covers the claim. A shared hardware-facing
change may require every supported board; the default board does not stand in
for all board-specific qualification.

Relevant records and helpers:

- `PHASE3_HARDWARE.md`: legacy platform-abstraction smoke.
- `PHASE4_HARDWARE.md`: generated legacy PyDevices comparison.
- `PHASE5_HARDWARE.md`: modern lifecycle and renderer ownership.
- `PHASE5_BENCHMARKS.md`: locked legacy/modern graphics matrix.
- `MODERN_TOUCHSCREEN_QUALIFICATION.md`: current launcher, local chooser, and
  IDE backlight smoke and evidence checklist.
- `tools/phase1_device.py`, `tools/phase5_device.py`, and
  `tools/phase5_benchmark.py`: repeatable probes.

Successful driver calls or idle touch polls do not replace human color,
orientation, touch-region, and browser observations.

## Tier 4: physical release qualification

Before promotion, provide applicable qualification for the exact tag/candidate,
each included board, and its firmware. The gate owns claims about flash and
reset behavior, PSRAM, GPIO, display/touch, Wi-Fi/AP, browser behavior, direct
OTA, recovery, interruption, protected state, feed isolation, and future update
access.

Establish these claims in full for new boards and repeat the relevant physical
gates for platform changes that invalidate them. For unchanged claims, a modern
candidate record may reference prior board-bound evidence with an explicit
baseline comparison and justification. This retains complete evidence coverage
without requiring a new power-loss campaign for an app or cosmetic browser
change. The current workflow requires reviewed evidence; the planned automated
reuse checks are described in [`RELEASE_POLICY.md`](../RELEASE_POLICY.md).

- Legacy qualification follows `PHASE2_HARDWARE.md` and publishes only through
  the protected legacy workflow to `tdhoward/TartLab`.
- Modern qualification follows `PHASE6_PROVISIONING.md` and
  `PHASE6_MODERN_QUALIFICATION.md` and publishes only through the protected
  modern workflow to `tdhoward/TartLab-modern-releases`.

Passing Tiers 0–2 satisfies automated checks only. Complete any required fresh
physical checks and justified evidence reuse, then use the protected promotion
workflow. Automated checks alone do not authorize a release.
