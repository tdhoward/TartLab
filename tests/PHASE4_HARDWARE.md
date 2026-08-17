# Phase 4 PyDevices candidate comparison

This document records the first physical comparison of the generated current-
upstream PyDevices candidate with the qualified Phase 2 legacy payload. It is a
research result, not a stable-release qualification.

## Session: 2026-08-17

Status: **Phase 4 item 6 completed. Candidate 9 resolves the severe Candidate
7 startup and fill regressions, passes observed color and five-point touch,
direct network OTA, corrupt/truncated/low-space/write containment, physical
interruption, offline recovery resume, repeated-health recovery, and protected
state checks. The remaining bounded startup and full-frame-blit regressions are
accepted for this research gate. The subsequent item 7 implementation promotes
only Candidate 9's exact source and packaged identities into the normal release
builder; this record does not itself declare a stable TartLab release.**

### Final candidate identity and reproducibility

- Target and firmware are unchanged: LilyGO T-Display-S3 Pro PCB v1.1 on COM6,
  MicroPython 1.23.0 octal-SPIRAM image SHA-256
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
- Source commit: `6d930fd5525e65b6a3439f707cd35a116df4b803`, plus the
  uncommitted item 6 completion changes recorded in this session.
- Generated source runtime: 71 files, 522,319 normalized bytes, identifier
  `sha256:277bc307b4e20dc07afd61580e737800f639a161ac2a9a341c4febef981fe23c`.
- Packaged runtime: 71 MicroPython 1.23 `xtensawin` modules, 146,227 expanded
  bytes, identifier
  `sha256:409eda4922f6b66c7fde8cdbca75489d15813749e6ef607ed94e4f81d67dc034`.
- Pinned `mpy-cross` SHA-256:
  `923ee05d103f76b6693e1e6fc3396240c63fc89ed08bd10cd7863e9f6328da9d`;
  it reported MicroPython v1.23.0 and mpy format v6.3.
- Installed research version: `phase4-candidate9-6d930fd`.
- Release `checksums.json` SHA-256:
  `0f4a0555e84b71bea00657a018e7914ce62a331f3789210410b238549db20b57`.
- Release manifest SHA-256:
  `ab392b11e2becf2ea6ce6f23ddd09403c24bbbd16489afee1859b26645106f3c`.
- Two complete 139-file build directories were byte-identical. All 67 host
  tests and the 18-check candidate compatibility probe passed. The guarded
  metadata remains `research-only-not-for-promotion`.

The research builder now minifies the exact provenance-checked source tree and
compiles it with the pinned firmware-generation compiler. This removes most of
the current stack's on-device parse cost without changing the normal legacy
release path. A second strict ST7796 patch sends bounded 16 KiB fill chunks and
constructs the cached color buffer without a repeated-bytes allocation.

### Final comparison and accepted performance decision

Three steady samples were taken after the OTA/recovery fault state was fully
settled. Post-install and immediate post-recovery boots were slower but healthy
and are not mixed into the steady-state row.

| Measurement | Legacy payload | Candidate 9 | Result |
| --- | ---: | ---: | --- |
| Complete release archives | 1,361,920 B | 716,800 B | 645,120 B (47.4%) smaller |
| Complete release expanded | 1,143,019 B | 560,767 B | 582,252 B (50.9%) smaller |
| PyDevices archive | 849,920 B | 204,800 B | 645,120 B (75.9%) smaller |
| PyDevices expanded | 728,479 B | 146,227 B | 582,252 B (79.9%) smaller |
| Device filesystem free | 3,760,128 B | 4,956,160 B | 1,196,032 B more free |
| Heap before framebuffer, median | 7,882,368 B | 7,813,152 B | 69,216 B (0.9%) less free |
| Reset to healthy IDE | 22.234 s | 25.281 s median (24.937-26.204) | 13.7% slower |
| Startup-to-IDE marker proxy | 7.282 s | 8.953 s median (8.921-9.000) | 22.9% slower |
| Full-screen solid fill | about 74.1 ms median | 59.172 ms median (49.447-61.924) | about 20.1% faster |
| 480x222 full-frame blit | about 70.6 ms median | 77.571 ms median (76.953-77.987) | about 9.8% slower |
| Idle touch poll | about 3.6 ms | about 3.8 ms | near parity |

Candidate 7's 41.500-second healthy startup and 16.921-second startup-to-IDE
proxy fell to 25.281 and 8.953 seconds. Its approximately 87 ms fill fell to a
stable 59.172 ms without the periodic garbage-collection spikes seen during
the first chunking experiment. The residual 13.7% total-startup, 22.9% proxy,
and 9.8% full-frame-blit regressions are explicitly accepted for Phase 4's
research migration gate because health timing remains reliable, the severe
regressions are removed, and the storage/fill results materially improve. This
acceptance does not approve promotion.

### Observed display and touch

The operator observed red, green, blue, white, and black in the announced
order with no swapped or visibly incorrect colors. At display rotation 90 in
the driver's 480-by-222 coordinate report, the prompted points were:

| Prompt | Recorded point |
| --- | ---: |
| Top left | `[205, 19]` |
| Top right | `[203, 467]` |
| Bottom right | `[2, 469]` |
| Bottom left | `[10, 8]` |
| Center | `[109, 247]` |

All prompts recorded a contact in the expected rotated region. This closes the
color-byte-order, coordinate, rotation, and edge observations left open by the
2026-08-16 session.

### Direct OTA, fault containment, and recovery resume

Candidate 8 fetched Candidate 9 from a temporary LAN HTTP server through the
normal updater. All 15 progress steps completed; every archive hash and tar
validated, managed paths installed, Candidate 8 stayed committed during
`pending_health`, and the next healthy IDE boot committed Candidate 9. The
temporary server was stopped and its port verified closed after use.

The isolated fault target was `/phase1_fault_target`; it never overlapped an
active or protected TartLab path.

- A bad package hash and a checksum-valid truncated tar failed during
  validation with the expected errors. Both left no marker or target and kept
  Candidate 9 committed.
- Pre-download low space made zero download calls. Post-staging low space made
  two download calls, validated both files, then refused extraction. Both left
  no marker or target and kept Candidate 9 committed.
- An injected write failure after validation wrote a `failed` marker, created
  no target, retained Candidate 9, and booted the display-independent
  `update_failed` recovery route. A full recovery reinstall reached
  `pending_health` and committed only after a healthy IDE boot.
- Physical USB power loss after the normal updater's durable `installing`
  marker retained Candidate 9, both staged files, and recovery access. Those
  normal-updater files are intentionally not misclassified as recovery staging;
  a corrective full recovery reinstall passed.
- Physical USB power loss inside the recovery installer, immediately before
  `pydevices.tar`, retained all 12 staged files and a recovery-source
  `installing` marker. The marker recorded `assetfiles.tar` and
  `libahttpserver.tar` complete. With the HTTP server stopped, offline resume
  explicitly skipped those two packages, installed the remaining eight
  managed packages, removed recovery staging, and reached `pending_health`.
- Two deliberately interrupted pre-health boots left the same-version pending
  marker uncommitted. The third boot entered `repeated_boot_failure` recovery
  with a failure count of three. Clearing only that counter retained the
  pending marker; the next genuine healthy IDE boot committed it exactly once.

The final state was Candidate 9, healthy IDE mode, zero consecutive failures,
no update marker, empty temporary staging, no fault target, and no listening
test server.

### Protected state and outcome

The final protected digests exactly match both the pre-session values and the
Candidate 7 record:

| Protected path | SHA-256 |
| --- | --- |
| `/app.py` | `e37866f2ca02e0aaaa66358e037101b54c8057cd747af57fd567c7df932af1f9` |
| `/hdwconfig.py` | `49d36afa0627c30c930bc9db642d20dedb3252340f9079ce27fc62eefccdab06` |
| `/state/selected_app.json` | `1e720e1ecff3dc514c6ebcf1d95508001c601062d3911fa34fb77ef223d398ab` |
| `/device` | `f598649a5a97fa70a36c11e3806d9d2069ff225a0f3e3806fd1007f8cc63e948` |
| `/files/user` | `5e207def500cac176a5fd64b07b207ce3a77a2250de9efff4852a3fcba9a4b77` |

At the conclusion of the physical session, Candidate 9 remained an uncommitted,
research-only comparison artifact and no stable promotion was attempted. The
subsequent item 7 code change uses these exact identities as the promoted vendor
input for new normal release candidates. Stable publication still requires an
exact candidate to pass the established reviewed release workflow.

## Session: 2026-08-16

Status: **the automated storage, heap, boot, display-transfer, idle-touch, and
verified recovery-install comparisons completed. The candidate saves
substantial filesystem space and full-frame blits are near the legacy result,
but startup and solid fills regress. Human-observed touch coordinates and
visual color fidelity, a network OTA, and recovery fault/resume were not
completed. The candidate will not be promoted.**

### Candidate identity and guardrails

- Target: LilyGO T-Display-S3 Pro PCB v1.1 on COM6.
- Firmware: `ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin`, MicroPython
  v1.23.0, SHA-256
  `41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212`.
- Source commit: `1e17b00acb3ad7a8b958f05371684b5fe6c50457`, plus the
  uncommitted Phase 4 comparison changes described here.
- Generated source runtime: 71 files, 521,163 bytes, identifier
  `sha256:090f9bd96352cfd8730e1bf3448112129f12e9f4954efbf5feb237b639783984`.
- Minified packaged vendor identifier:
  `sha256:ba75bc604f189e92e17ae2b17e16ebfbb7f90ef0cd67d7cb4b1c769c6bda1da5`.
- Installed research version: `phase4-candidate7-1e17b00`.
- Release manifest SHA-256:
  `24675493512c2baf0b57783b3ad5be9789ecc185ee335b1878c83942740e2241`.
- The guarded builder labels both metadata layers
  `research-only-not-for-promotion`; the ordinary legacy release path still
  requires its exact historical vendor inventory.
- Two builds of the same candidate produced identical inventories and bytes
  for all 18 release files.
- The exact minified runtime passed the pinned MicroPython 1.23 gate: 71
  candidate modules compiled for `xtensawin`, with 31 runtime checks and 18
  candidate compatibility checks passing.

The comparison work exposed five concrete incompatibilities. Strict,
hash-pinned inputs now remove the unsupported CircuitPython `cp` display
argument, prefer MicroPython's native C framebuffer, retain the ST7796
RAM-continue fill path, and avoid reconfiguring ESP32 SPI pins on every
transfer. The TartLab board adapter also creates an application-polled touch
device because MicroPython 1.23 does not accept the current auto-service
timer's `hard=False` argument. No patch is applied outside the exact locked
candidate.

### Measured comparison

The legacy reference was the installed `phase3-smoke-ae9c861` payload built
from the same legacy release profile. Three graphics/heap samples were taken
for each payload. Candidate boot results below are three post-install cold
resets; the legacy boot is the valid healthy-marker baseline from the same
session.

| Measurement | Legacy payload | Candidate 7 | Result |
| --- | ---: | ---: | --- |
| Complete release archives | 1,361,920 B | 931,840 B | 430,080 B (31.6%) smaller |
| Complete release expanded | 1,143,019 B | 769,177 B | 373,842 B (32.7%) smaller |
| PyDevices archive | 849,920 B | 419,840 B | 430,080 B (50.6%) smaller |
| PyDevices expanded | 728,479 B | 354,637 B | 373,842 B (51.3%) smaller |
| Device filesystem free | 3,760,128 B | 4,743,168 B | 983,040 B more free |
| Heap before framebuffer, median | 7,882,368 B | 7,829,776 B | 52,592 B (0.7%) less free |
| Reset to healthy IDE | 22.234 s | 41.500 s median (41.203-43.578) | 86.7% slower |
| Startup-to-IDE marker proxy | 7.282 s | 16.921 s median | 132% slower |
| Full-screen solid fill | about 74.1 ms median | 87.019 ms median (85.385-98.202) | about 17% slower |
| 480x222 full-frame blit | about 70.6 ms median | 71.971 ms median (71.568-72.510) | about 2% slower |
| Idle touch poll | about 3.6 ms | 3.613 ms median | near parity |

The startup-to-IDE interval begins at `System startup` and ends at `Starting
IDE`. It includes platform/display construction, the initial clear, state
loading, and mode selection, so it is a repeatable display-initialization proxy
rather than a driver-only timer.

All samples reported the physical `st7796.ST7796` display at 480x222x16 with
byte swapping enabled and the `cst226.CST226` touch driver. The display
completed black, red, green, blue, white, black fills and full-frame writes
without an exception. No person observed the colors during this run, so byte
order and visual color fidelity are not claimed. Twenty idle touch polls per
sample completed without an exception, but none contained a touch; coordinate,
rotation, edge, and gesture behavior remain unverified.

### Installation, recovery, and protected state

The complete 11-package release was transferred through the recovery staging
area. The host and device verified every archive hash, the recovery installer
validated each tar before modifying managed paths, and the install entered
`pending_health`. The following boot reached `HEALTHY mode=IDE`, committed
`phase4-candidate7-1e17b00`, removed the update marker, and ended with boot
sequence 47, healthy IDE mode, and zero consecutive failures.

This proves the ordinary transactional recovery installer can install this
payload and commit it only after health. It does not prove a real network OTA,
power-loss rollback, failed-archive containment, or recovery resume for the
candidate; those established Phase 2 cases must be rerun for a promotable
artifact.

The pre/post candidate digests were identical:

| Protected path | SHA-256 |
| --- | --- |
| `/app.py` | `e37866f2ca02e0aaaa66358e037101b54c8057cd747af57fd567c7df932af1f9` |
| `/hdwconfig.py` | `49d36afa0627c30c930bc9db642d20dedb3252340f9079ce27fc62eefccdab06` |
| `/state/selected_app.json` | `1e720e1ecff3dc514c6ebcf1d95508001c601062d3911fa34fb77ef223d398ab` |
| `/device` | `f598649a5a97fa70a36c11e3806d9d2069ff225a0f3e3806fd1007f8cc63e948` |
| `/files/user` | `5e207def500cac176a5fd64b07b207ce3a77a2250de9efff4852a3fcba9a4b77` |

No settings values, Wi-Fi credentials, access-point identity, or student-file
contents are included in this evidence.

### Outcome and remaining gate

Phase 4 item 6 is partial. Storage, startup heap, a repeatable initialization
proxy, display transfer performance, idle touch polling, transactional install,
health commit, and protected ownership now have physical measurements. Before
item 6 can close, the startup and solid-fill regressions need an explicit
accept/fix decision, and a person must verify touch coordinates and displayed
colors. A final candidate must then repeat the direct network OTA and recovery
fault/resume matrix. At the end of this earlier session, item 7 was still closed
and `src/lib/pydevices` was still the normal release source.

The board was left running the installed research candidate in healthy IDE
mode so the unobserved manual display/touch checks can be performed without
another transfer. The qualified legacy rollback release remains available in
the ignored hardware workspace.
