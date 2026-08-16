# Phase 1 legacy-hardware release gate

Phase 1 is not approved for deployment until this checklist passes on a LilyGO
T-Display-S3 Pro running exactly
`ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`.

The release policy is one user-initiated update directly to the latest stable
(non-alpha/non-prerelease) GitHub release. Ordered schema/layout migrations may
run and resume internally, including across automatic restarts, but the user
must not need to install intermediate releases or invoke the updater again.

Before testing, regenerate `fixtures/legacy_mp123` with the capture tool and
`--release-gate-ready`, supplying the board revision, SHA-256 of the flashed
firmware binary, capture method, and device `statvfs` capacity/free values. Keep
real Wi-Fi credentials and student programs out of the fixture.

For each case, retain serial output, all five rolling logs, the pre/post protected
path inventory, reset cause, heap/PSRAM diagnostics, and filesystem statistics:

1. First boot without settings reaches IDE and writes an IDE health marker.
2. Button-selected IDE and APP modes work; an app that keeps running for at least
   three seconds writes an APP health marker.
3. A single OTA from the v0.13 captured layout directly to the candidate latest
   stable release preserves `/device`, `/state`, `/files/user`, the legacy
   hardware selector, selected app, settings, repositories, and logs without a
   user-visible intermediate release.
4. Power loss during download makes no installed changes; power loss after the
   install marker enters the display-independent recovery AP.
5. A truncated archive and a forced write error report failure, never report
   package success, retain the prior committed version, and enter recovery.
6. Recovery can join a configured network, install a corrective release, boot the
   IDE, and commit the pending version only after the IDE server is listening.
7. Five-log rotation, display, touch, PSRAM, AP mode, edit/save/run, application
   selection, and a subsequent OTA all still work.

Record the artifact tag/commit and mark the fixture `release_gate_ready: true` only
after every check passes on physical hardware.

## Completed hardware session: 2026-08-03 through 2026-08-05

Status: **physical Phase 1 release gate passed for the tested working tree**.

The test device was a LilyGO T-Display-S3 Pro PCB revision v1.1 on COM6. It
reported MicroPython `v1.23.0 on 2024-06-02` on a generic ESP32-S3 module with
Octal-SPIRAM. The corresponding official firmware artifact is
`ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` (1,631,424 bytes), SHA-256:

`41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`

The tested source was commit `22d9315dfb93531580cecdac028fea452ed37be9`
plus the uncommitted Phase 1 working-tree changes. The final reproducibility
build recorded profile `legacy-mp123`, 10 packages, 1,351,680 archive bytes,
1,146,337 expanded bytes, and `git_dirty: true`. The hardware gate is complete,
but a deployable published artifact must still be rebuilt from the committed
clean tree.

### Release-gate results

1. **First boot without settings: passed.** Reversible removal of both settings
   files initially exposed a missing-defaults bug: `main.py` selected IDE mode
   but the IDE later raised `KeyError: hostname`. `default_settings()` now
   returns the complete schema and both startup callers use it. The repeated
   physical test created defaults, started AP/IDE mode, returned HTTP 200, and
   wrote `HEALTHY mode=IDE`. The original protected settings were restored
   byte-for-byte afterward.
2. **Button-selected modes and health: passed.** IDE and APP selection worked.
   A long-running temporary app remained active past the three-second gate and
   produced `HEALTHY mode=APP`; IDE health was recorded only after its server
   listened. The final GPIO12 trace was released `1`, pressed `0`, released
   `1`. The temporary health app was removed and `phase1_hw_test.py` restored as
   the selected application.
3. **OTA migration and preservation: passed.** OTA from the 192-file v0.13
   physical capture preserved `/device`, `/state`, `/files/user`, both hardware
   selectors, selected-app state, settings, repository identity, and logs. The
   first physical OTA exposed MicroPython 1.23.0's missing `str.isalnum()`;
   replacing it with explicit ASCII validation allowed migration to complete.
   Subsequent OTAs left the prior version committed during installation and
   committed the pending version only after an IDE HTTP 200 health result.
4. **Both physical power-loss boundaries: passed.** Power removal during the
   package download left no update marker, installed target, or version change.
   The staged legacy manifest caused recovery reason
   `legacy_update_interrupted`. Power removal after the durable `installing`
   marker preserved the complete staging files and marker but created no target
   files; the next boot entered the `TartLab-Recovery` AP with recovery reason
   `update_installing`. In both cases the committed version remained
   `phase1-recovery-corrective`, essential boot/recovery files were intact, and
   exact test-only cleanup returned the IDE to HTTP 200.
5. **Archive/write failures: passed.** A truncated archive returned
   `UPDATE_FAILED`, logged `Truncated tar header`, emitted no package-success
   result, wrote no marker, retained the committed version, and created no
   target. A forced write error after validation also returned failure, emitted
   no success result, retained the committed version, wrote a `failed` marker,
   and entered recovery without creating the target. The legacy tar reader now
   validates USTAR header size/checksum, member size, padding, termination, and
   non-empty inventory before clearing a target.
6. **Recovery corrective install: passed without Internet.** The device joined
   an isolated Windows 2.4 GHz Mobile Hotspot and downloaded the unpublished
   corrective release from a local HTTP server. Recovery downloads now support
   verified reuse, atomic `.part` promotion, package completion markers, and
   offline staged resume. Several power-on/brownout-class resets occurred during
   Wi-Fi plus flash activity; recovery containment held each time. The staged
   resume installed all nine non-recovery packages, booted the IDE, returned
   HTTP 200, and only then committed `phase1-recovery-corrective`.
7. **Post-update hardware/application matrix: passed.** Browser IDE load,
   edit/save/run/set-app, IDE/AP mode, APP mode, five-log rotation, structured
   diagnostics, and subsequent OTA all worked. The final display sequence was
   red, green, blue, white, black with RGB565 byte swapping enabled. All final
   touch prompts registered: top-left `[214, 41]`, top-right `[210, 469]`,
   bottom-right `[1, 468]`, bottom-left `[7, 13]`, and center `[110, 246]` in
   the driver's rotated coordinate system. The 8 MiB SPIRAM heap remained
   available.

### Final evidence and state

- The tracked sanitized fixture `tests/fixtures/legacy_mp123` is regenerated
  from the physical `baseline_v013` capture with synthetic credentials,
  recorded capture method, board revision, firmware hash, and measured
  filesystem capacity/free values. `release_gate_ready` is `true`.
- All 21 host regressions pass, including ownership, migration, health commit,
  first-boot defaults, strict archive handling, recovery download/resume, and
  early recovery-gate cases. `git diff --check` reports no whitespace errors.
- Ignored evidence includes `baseline_v013`, `pre_ota_browser_state`,
  `post_ota_r2`, `pre_powerloss_final`, `pre_powerloss_marker`, `phase1_final`,
  and the local release artifacts. These captures contain protected state and
  must not be committed or printed.
- The final pre/post power-loss hash comparison reported every non-transient
  file unchanged. Exclusions were limited to rolling `/state/logs`, boot state,
  the restored selected-app record, the removed temporary health app, and the
  host-side snapshot manifest.
- Final recorded device state: IDE HTTP 200; boot sequence 31 healthy with
  zero failures; five state logs; no update marker; empty `/tmp`; committed
  version `phase1-recovery-corrective`; selected app `phase1_hw_test.py`; and no
  temporary health-test file.
- The temporary Python HTTP server was stopped and TCP port 8765 had no
  listener. At the project owner's request, the Private-profile Windows
  firewall rule `TartLab Phase1 HTTP 8765` and the 2.4 GHz Mobile Hotspot were
  retained for future device development.

The repeatable serial/raw-REPL harness is `tools/phase1_device.py`; the
noninteractive builder is `tools/build_phase1_test_release.py`; and fixture
sanitization is performed by `tools/capture_legacy_fixture.py`.
