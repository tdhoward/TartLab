# Phase 1 legacy recovery qualification

This record establishes the original physical recovery and ownership baseline
for the LilyGO T-Display-S3 Pro. It is historical evidence, not authorization
for a current release candidate.

## Qualified checkpoint

- Session: 2026-08-03 through 2026-08-05.
- Board: T-Display-S3 Pro PCB v1.1.
- Firmware: MicroPython 1.23.0 octal-SPIRAM,
  `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`, SHA-256
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
- Source: commit `22d9315dfb93531580cecdac028fea452ed37be9` plus
  uncommitted Phase 1 changes. Because the tested tree was dirty, this session
  cannot identify a publishable artifact.
- Result: physical Phase 1 gate passed for the tested working tree.

## Established behavior

The session physically confirmed:

- first boot creates complete defaults and reaches a healthy IDE;
- button-selected IDE and APP modes record health only after readiness;
- one OTA from the sanitized v0.13 layout preserves hardware selection,
  settings, repositories, logs, selected app, and student files;
- power loss during download or after the durable install marker retains the
  old committed version and a usable recovery route;
- corrupt/truncated archives and injected writes fail without false success;
- offline staged recovery resumes and commits only after a healthy IDE boot;
- display colors, five-point touch, octal PSRAM, AP/browser IDE,
  edit/save/run/select-app, log rotation, and subsequent OTA work.

Issues found during qualification led to complete default settings, explicit
ASCII validation compatible with MicroPython 1.23, strict TAR validation,
propagated write/extraction failures, atomic staged downloads, resumable
recovery, and health-gated version commits.

## Durable outputs and limits

The sanitized, release-ready v0.13 fixture is
`tests/fixtures/legacy_mp123`; it contains synthetic credentials and no real
student work. Repeatable tooling is in `tools/phase1_device.py`,
`tools/build_phase1_test_release.py`, and
`tools/capture_legacy_fixture.py`.

Raw serial logs, snapshots, settings, and protected-state captures remain
private because they can contain credentials or student data. A current legacy
release must repeat the applicable Tier 4 matrix on its exact clean candidate;
this historical pass is only the baseline.
