# Phase 3 focused physical smoke

This document records the focused Tier 3 physical check for the TartLab
hardware-abstraction change. It is not a stable-release qualification and does
not replace the complete Tier 4 gate in `PHASE2_HARDWARE.md`.

## Session: 2026-08-12

Status: **the automated boot, update, protected-state, mode-routing, display
driver, and network checks passed. A physical button press and human visual
color-fidelity observation were not completed. The candidate will not be
promoted.**

### Candidate identity

- Candidate commit: `ae9c861b84039d6e7d60bf9db93999327c5f67c2`
  (clean CI source tree).
- Successful CI run:
  <https://github.com/tdhoward/TartLab/actions/runs/31625015183>.
- Artifact: `legacy-mp123-ae9c861b84039d6e7d60bf9db93999327c5f67c2`,
  artifact ID `9152798806`.
- Downloaded artifact ZIP SHA-256:
  `19c1b4d321bd31283fa6bb56340cfcf82f2a472a84b7add227c7ff8b12f916c4`.
- Manifest SHA-256:
  `1011bc99c8bba17e7089f9009c7f17db58e7d16af71cffec899a5012b679bee7`.
- All 17 artifact entries matched `checksums.json`. The release contains 11
  packages, 195 distribution files, 1,361,920 archive bytes, and 1,143,019
  expanded bytes.

### Target and installation

- Target: the LilyGO T-Display-S3 Pro used for the Phase 2 hardware session,
  exposed on `COM6`.
- Runtime probe: MicroPython v1.23.0 dated 2024-06-02 on the generic ESP32-S3
  octal-SPIRAM build.
- Starting TartLab version: `phase2-candidate-a42bedc1367d`.
- Installed smoke version: `phase3-smoke-ae9c861`.
- The artifact was transferred directly over raw REPL because exposing the
  candidate through a host hotspot HTTP server was not appropriate. The final
  transfer used acknowledged 1,536-byte chunks and verified each completed
  file on-device with SHA-256 before installation.
- The manifest and every package passed both host-side and on-device hash and
  tar validation. The recovery installer then installed all 11 packages.
- The first binary-streaming transfer experiment timed out while writing only
  disposable `/tmp/recovery` staging data. No install marker or managed-file
  modification had begun; the existing candidate remained bootable. The next
  attempt cleared staging and completed with acknowledged chunks.

### Results

1. The first candidate boot began with update status `pending_health`. The IDE
   server started, boot health became `healthy`, and the pending version
   committed exactly once. Final update state was empty.
2. The first boot could not associate with the configured station and correctly
   entered fallback open-AP mode at `192.168.4.1`. Boot health remained healthy.
   A clean retry joined the configured station network and served the IDE at
   `192.168.137.192` with HTTP 200 and a 5,569-byte response.
3. A one-shot `APP` startup launched the preserved selected application,
   recorded healthy APP boot state, and automatically restored
   `STARTUP_MODE=BUTTON`. A reset with GPIO 12 unpressed returned to healthy IDE
   mode and HTTP 200.
4. The physical ST7796 driver completed red, green, blue, white, and black fill
   calls without an exception. This run did not include a human assertion of
   color fidelity; that remains a Tier 4 responsibility.
5. The interactive GPIO watcher observed the normal unpressed values `[1, 1]`
   but no press/release transition during its 15-second window. The real
   platform's unpressed GPIO 12 path was exercised by normal IDE selection, but
   pressed-button brightness/APP selection is not claimed by this session.
6. Final boot state was `healthy`, mode `IDE`, with zero consecutive failures.
   Heap and filesystem probes remained within the established legacy envelope.

### Protected-state comparison

The following pre-install and post-smoke digests were identical:

| Path | SHA-256 |
| --- | --- |
| `/app.py` | `e37866f2ca02e0aaaa66358e037101b54c8057cd747af57fd567c7df932af1f9` |
| `/hdwconfig.py` | `49d36afa0627c30c930bc9db642d20dedb3252340f9079ce27fc62eefccdab06` |
| `/state/selected_app.json` | `1e720e1ecff3dc514c6ebcf1d95508001c601062d3911fa34fb77ef223d398ab` |
| `/device` | `f598649a5a97fa70a36c11e3806d9d2069ff225a0f3e3806fd1007f8cc63e948` |
| `/files/user` | `5e207def500cac176a5fd64b07b207ce3a77a2250de9efff4852a3fcba9a4b77` |

No settings values, Wi-Fi credentials, generated access-point name, or student
file contents are included in this record.

### Outcome and next step

This focused run provides physical evidence that the legacy platform adapter
did not regress the tested boot/update transaction, protected ownership,
IDE/APP routing, display-driver calls, or AP/station network paths. It does not
authorize promotion. A future stable candidate still requires the complete
Tier 4 release gate, including observed GPIO press/release, brightness behavior,
touch, browser editing, visual display checks, reset/fault cases, and direct
OTA/recovery qualification.

The next development phase is Phase 4: inventory and prune the embedded
PyDevices runtime behind the now-smoked platform boundary.
