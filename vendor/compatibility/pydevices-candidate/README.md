# TartLab PyDevices compatibility surface

These hash-pinned TartLab-owned files preserve only the legacy imports used by
the platform boundary and shipped examples: `graphics`, `bmp565`,
`touch_keypad`, `eventsys.keys.Keys`, and the protected T-Display-S3 Pro board
path. The local QOI reader remains because the reviewed upstream repositories
have no equivalent.

The board adapter translates current list-based event polling to the legacy
scalar `broker.poll()` contract and avoids the unsupported MicroPython 1.23
auto-service timer keyword. Do not expand this directory to mirror the old
PyDevices tree; new code should use stable TartLab APIs.

These adapters are part of the exact generated payload qualified in
`tests/PHASE4_HARDWARE.md`. Any change requires new identities, compatibility
checks, and the applicable physical gate.
