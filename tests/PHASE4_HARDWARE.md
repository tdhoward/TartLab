# Phase 4 generated PyDevices qualification

This record compares the pinned generated PyDevices payload with the qualified
legacy payload. It authorizes only the exact vendor identities used by the
normal legacy builder; it is not a stable TartLab release gate.

## Qualified candidate

- Session: 2026-08-17.
- Board/runtime: T-Display-S3 Pro PCB v1.1 on the qualified MicroPython 1.23.0
  octal-SPIRAM image.
- Generated runtime: 71 files, identifier
  `sha256:277bc307b4e20dc07afd61580e737800f639a161ac2a9a341c4febef981fe23c`.
- Packaged `xtensawin` runtime: 71 modules, identifier
  `sha256:409eda4922f6b66c7fde8cdbca75489d15813749e6ef607ed94e4f81d67dc034`.
- Pinned `mpy-cross` SHA-256:
  `923ee05d103f76b6693e1e6fc3396240c63fc89ed08bd10cd7863e9f6328da9d`.
- Installed research version: `phase4-candidate9-6d930fd`.
- Result: Phase 4 physical comparison passed; the remaining bounded performance
  regressions were accepted for this vendor-migration gate.

Two build directories were byte-identical, host and MicroPython compatibility
checks passed, and the exact identities above were subsequently pinned in
`profiles/legacy-mp123.json`. A normal legacy release builder rejects drift.

## Physical comparison

| Measurement | Qualified legacy | Candidate 9 | Change |
| --- | ---: | ---: | ---: |
| Complete release archive | 1,361,920 B | 716,800 B | 47.4% smaller |
| PyDevices expanded | 728,479 B | 146,227 B | 79.9% smaller |
| Device filesystem free | 3,760,128 B | 4,956,160 B | 1,196,032 B more |
| Heap before framebuffer | 7,882,368 B | 7,813,152 B | 0.9% less |
| Reset to healthy IDE | 22.234 s | 25.281 s | 13.7% slower |
| Full-screen solid fill | ~74.1 ms | 59.172 ms | ~20.1% faster |
| Full-frame blit | ~70.6 ms | 77.571 ms | ~9.8% slower |
| Idle touch poll | ~3.6 ms | ~3.8 ms | Near parity |

The operator confirmed correct red/green/blue/white/black output and touches in
all four corners and the center. Direct network OTA, hash/TAR/space/write
failures, real install interruption, offline recovery resume, repeated-health
recovery, exactly-once commit, and protected-state preservation all passed.

An earlier 2026-08-16 candidate had severe startup and fill regressions and
incomplete manual/fault observations. It was rejected and has no continuing
release role.

Stable publication still requires the exact current release candidate to pass
the complete protected legacy promotion gate.
