# TartLab PyDevices compatibility surface

These files are TartLab-owned inputs to the generated Phase 4 candidate. They
are copied after the exact upstream sources and are hash-pinned individually by
`vendor/pydevices-candidate.lock.json`.

The adapters preserve only the legacy imports exercised by TartLab's platform
boundary and shipped examples: `graphics`, `bmp565`, `touch_keypad`,
`eventsys.keys.Keys`, and the protected T-Display-S3 Pro board path. The local
QOI decoder is retained because the reviewed upstream repositories have no
equivalent. New application APIs must not be added here merely to mirror the
entire historical PyDevices tree.

The board-path adapter keeps the legacy application-driven `broker.poll()`
contract. It creates the current touch device without enabling the upstream
auto-service timer, whose `hard=False` keyword is not supported by the pinned
MicroPython 1.23 ESP32 `machine.Timer` implementation.

The generated candidate remains research-only. These adapters establish a
host- and MicroPython-compatible import/API boundary; they do not establish
physical display, touch, timing, RAM, or OTA behavior.
