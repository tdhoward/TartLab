# Phase 2 reproducible legacy release gate

Phase 2 candidate artifacts may be produced by `legacy-ci.yml`, but they must
not be promoted to a stable GitHub release until this gate passes on a LilyGO
T-Display-S3 Pro running exactly
`ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin` (SHA-256
`41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`).

Use a candidate from the `legacy-mp123-<commit>` CI artifact. Record the
candidate's `checksums.json` SHA-256, `build_metadata.json`, board revision,
firmware hash, serial output, all rolling logs, pre/post protected-state
inventories, `statvfs`, heap/PSRAM diagnostics, and the operator/date for every
run. The evidence bundle must contain no real Wi-Fi credentials or student
work; hash the final sanitized bundle.

The candidate passes when all of the following are demonstrated:

1. Two clean CI builds are byte-identical and the host legacy gate passes.
2. Clean provisioning boots into the IDE and supports display, touch, AP mode,
   editing, saving, running, application selection, and five-log rotation.
3. One update action from the sanitized v0.13 layout reaches the candidate and
   preserves `/device`, `/state`, `/files/user`, settings, selected app,
   repositories, and logs.
4. File inventory, archive inventory, expanded bytes, startup heap/PSRAM,
   display initialization, touch coordinates, and OTA outcome are compared
   with the Phase 1 record. Explain every inventory change and any regression.
5. Power loss during a download leaves active files unchanged. Power loss
   during each clear/extract boundary enters recovery, retains the old committed
   version, and can resume or reinstall the same candidate.
6. A corrupt package, truncated archive, injected write failure, and both
   pre-download and post-staging low-space cases fail before version commit and
   preserve recovery access.
7. Three failed health checks retain the old committed version and enter the
   display-independent recovery route. A later healthy corrective boot commits
   exactly once and retains future OTA capability.

After review, invoke `promote-legacy-release.yml` with the stable tag, the
candidate `checksums.json` SHA-256, the sanitized evidence-bundle SHA-256, and a
durable evidence reference. The repository's `legacy-release` GitHub
environment must require an approving reviewer. The promotion workflow rebuilds
the tag, rejects a candidate hash mismatch, records `promotion_attestation.json`,
and only then creates the stable GitHub release.

## Completed hardware session: 2026-08-10

Status: **the technical Phase 2 matrix passed for candidate `a42bedc`, with an
environmental power/network qualification; stable promotion remains closed
pending review**.

The qualification is material: the laptop's 2.4 GHz hotspot and the board's USB
power path were intermittently unstable, and several cold-update attempts saw
real power-on/brownout resets. The updater behaved safely through those resets,
and an uninterrupted retry from the unchanged sanitized v0.13 layout completed.
An earlier candidate in the same session also completed the single user action
without interruption. A reviewer may require one repetition on controlled
power/network hardware before authorizing a stable release.

### Tested identity and evidence

- Operator: Tim.
- Board: LilyGO T-Display-S3 Pro, PCB v1.1; ESP32-S3 revision 0.2, 16 MiB
  flash, and 8 MiB octal PSRAM.
- Firmware: `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`, SHA-256
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
- Candidate commit: `a42bedc1367d0b1e6b694dd059889db15f1008d2` (clean tree).
- Successful CI run: <https://github.com/tdhoward/TartLab/actions/runs/31412535152>.
- CI artifact: `legacy-mp123-a42bedc1367d0b1e6b694dd059889db15f1008d2`,
  artifact ID `9072145988`, 1,444,337-byte downloaded ZIP, SHA-256
  `ab0d9df9d42ad9f158efa9db54b380e62ca2b8559467c5be25aaa1cb9fdb40ab`.
- Candidate `checksums.json` SHA-256:
  `15cc9cec697a3cd553c6ed8c3daff6c105eb1eef6564039dfcc59a7bbb337a15`.
- Candidate `manifest.json` SHA-256:
  `47b9b0926dc46b11c19cdc400e3369585fe76df7e1670b1301fd9712ef1ed822`.
- Sanitized local evidence: `hardware_test_artifacts/phase2/evidence/run13-sanitized`.
  Its deterministic 44,079-byte archive is
  `hardware_test_artifacts/phase2/evidence/phase2-run13-sanitized.zip`, SHA-256
  `dc574e4c206b656f0d71b40091fa1aea8d253f806fff44dea28b5ccb09da8477`.
  The archive was produced twice with the same hash and passed ZIP integrity
  validation. Its inventory SHA-256 is
  `641b2fecbfee137fb318129e81e60c3b2a21e61ca1a7adf6e591b9d60fb6052c`.
- The bundle has 33 files: the exact CI build metadata, checksums, manifest,
  distribution/archive/payload inventories, summarized physical results, and
  19 sanitized rolling/serial/recovery logs. A credential scan covered all 33
  text inputs and confirmed that no discovered Wi-Fi value remained. Settings,
  repository state, and student files are not included.

### 1. Reproducible host and CI gate: passed

Two clean local builds produced byte-identical 18-file release outputs. The
independent legacy gate compiled 164 Python files and passed clean-install and
captured-layout OTA simulations. All 37 combined Phase 1 and Phase 2 tests
passed. GitHub Actions produced the clean candidate above with Python 3.11.9,
Node 20.19.4, and Python Minifier 3.2.0.

The candidate contains 11 packages, 1,351,680 archive bytes, 1,140,023 expanded
bytes, and a 194-file/1,140,585-byte distribution. Every outer and inner hash
passed, archive paths were safe and unique, and the reconstructed distribution
matched the candidate inventories.

### 2. Clean provisioning and hardware behavior: passed

The exact firmware was erased/flashed and the clean distribution uploaded. It
booted into IDE mode without a traceback. Red, green, blue, white, and black
display tests passed. In the driver's rotated 222-by-480 coordinate system,
touch points were top-left `[208, 39]`, top-right `[212, 456]`, bottom-right
`[5, 469]`, bottom-left `[8, 31]`, and center `[111, 240]`. GPIO 12 and GPIO 0
press/release tests passed.

The access-point page loaded at `192.168.4.1`. The browser IDE returned HTTP
200 and passed edit/save/run/set-app; the run marker was
`PHASE2_BROWSER_RUN_OK`. APP mode ran the selected program and intentionally did
not expose the IDE. Returning to IDE mode and five-file rolling-log retention
also passed.

The initial clean-provisioning pass used the run-11 lineage. The final
`a42bedc` payload was then installed and audited byte-for-byte on the same board;
the intervening candidate changes added the protected tarfile package and
corrected updater progress accounting, which were exercised by the run-13 OTA,
recovery, and future-OTA cases below.

### 3. Direct v0.13 update and protected state: passed

The exact sanitized pre-update snapshot contained 192 files, 1,099,071 content
bytes, 965 free filesystem blocks, two synthetic Wi-Fi records, and five logs.
The final candidate snapshot contained 213 files, 1,145,597 content bytes, 927
free blocks, the same two records, and five logs.

All 191 applicable candidate-managed files matched the reconstructed CI
distribution. The only differences from the full distribution were the three
expected protected paths: `/app.py`, `/files/user/hello.py`, and
`/hdwconfig.py`. The hardware selector, selected app, user files, canonical
settings, repository identity, and rolling logs were preserved. The migration
ran, staging and update markers were removed after health, and the target
`phase2-candidate-a42bedc1367d` committed only after a healthy IDE boot.

The already-installed v0.13 updater displayed a stale `15/11` denominator on
the first transition because it executed that operation. The installed
candidate then completed a future OTA and correctly reported `1/15` through
`15/15`, proving that the protected recovery runtime and future update path
remained usable.

### 4. Phase 1 comparison: passed, no hardware regression

Phase 1 had 10 packages, 1,351,680 archive bytes, and 1,146,337 expanded bytes.
Phase 2 has one additional `/lib/tarfile` package, the same archive total, and
6,314 fewer expanded bytes because of the reproducible/minified payload. Its
baseline inventory comparison is 14 added, 156 changed, zero removed, and 24
unchanged files. The managed additions are the protected tarfile runtime and
previously omitted source assets/helpers; there were no unexplained removals.

The Phase 1 final snapshot had 211 files/1,178,471 content bytes and Phase 2 had
213 files/1,145,597 content bytes. The remaining path/content delta is explained
by the added managed runtime/assets, minification, different rolling-log
sequence numbers, and temporary Phase 1 user-test programs intentionally absent
from the sanitized Phase 2 source state. Display, touch, IDE, APP, PSRAM, AP,
recovery, and later OTA behavior showed no regression. The final candidate had
7,791,696 bytes of free normal heap, all 8 MiB of PSRAM available to the runtime,
no boot failures, no update marker, no staged files, and a healthy HTTP 200 IDE.

### 5–7. Fault, recovery, and health matrix: passed

- A real reset during download left all 187 active non-log/non-temporary files
  byte-identical. Nine partially staged files (including one zero-byte file)
  were isolated from the active installation; no target version or install
  marker was committed.
- Corrupt-package and checksum-valid truncated-archive cases failed with the
  expected hash mismatch and truncated-tar-header errors. Neither advanced the
  version or left an install marker.
- Pre-download low space made zero download calls. Post-staging low space failed
  after staging/validation. Both retained the committed version.
- An injected write error after validation marked the update failed, kept the
  old version, and booted the display-independent `update_failed` recovery AP
  without a traceback.
- Physical power loss after the durable `installing` marker retained the old
  version and booted the `update_installing` recovery route. Further real resets
  during clear/extract retained deterministic progress; offline resume skipped
  completed packages, installed the remainder, cleared staging, and reached
  pending health.
- Four observed failed-health boots (meeting the required three) retained the
  old committed version and entered `repeated_boot_failure` recovery. A forced
  IDE corrective action cleared failures while retaining the pending marker;
  the following HTTP-healthy boot committed exactly once and removed the marker.
- Reinstalling the same candidate after recovery passed and retained future OTA
  capability.

### Promotion status

`promote-legacy-release.yml` was **not invoked**. The candidate remains a CI
artifact, not a stable release. Before promotion, review this evidence and the
power/network qualification, choose the stable tag and durable evidence
reference, and confirm that the repository's `legacy-release` environment has
an approving reviewer configured.
