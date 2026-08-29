# Phase 3 legacy platform smoke

This is the focused Tier 3 check for the TartLab hardware-platform abstraction.
It is not a stable-release qualification.

## Checkpoint and result

- Session: 2026-08-12.
- Candidate commit:
  `ae9c861b84039d6e7d60bf9db93999327c5f67c2`.
- CI run: <https://github.com/tdhoward/TartLab/actions/runs/31625015183>.
- Artifact ZIP SHA-256:
  `19c1b4d321bd31283fa6bb56340cfcf82f2a472a84b7add227c7ff8b12f916c4`.
- Target: the qualified T-Display-S3 Pro and MicroPython 1.23.0
  octal-SPIRAM runtime.
- Result: automated boot/update, ownership, mode routing, driver calls, and
  network checks passed. The candidate was not promoted.

The recovery installer verified and installed all packages, kept the candidate
pending until the IDE was healthy, and committed it once. Fallback AP and
station modes both served HTTP 200. APP mode ran the preserved selected app and
returned to healthy IDE mode. Display fill calls completed for all test colors,
and heap/filesystem measurements stayed within the legacy envelope.

Pre/post digests for `/app.py`, `/hdwconfig.py`,
`/state/selected_app.json`, `/device`, and `/files/user` were identical.
No credential or student-file contents were retained.

This smoke did not observe a physical button transition, touch behavior, or
human color fidelity. Those remain Tier 4 claims and must be repeated for a
release candidate.
