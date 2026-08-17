# PyDevices candidate compatibility patches

Compatibility patches for the generated Phase 4 candidate belong here as
strict JSON patch manifests. The candidate lock records each patch path and
SHA-256; unlisted files are never applied.

Each patch manifest has `schema: 1` and an `operations` list. Every operation
names an allowlisted runtime destination, pins its complete preimage and result
SHA-256 values, and contains exact text replacements with an expected match
count. The vendor tool rejects fuzzy matches, unselected paths, stale hashes,
and unexpected dependencies introduced by a patch.

The approved MicroPython 1.23 displaydev patch changes only adjacent formatted
string literals that the pinned parser rejects; preimage and result hashes pin
the complete upstream file. The T-Display-S3 Pro patch removes an upstream
CircuitPython `cp` metadata argument that the selected MicroPython
`BusDisplay` contract does not accept; all actual display parameters remain as
explicit constructor arguments. The native-framebuffer patch makes the
MicroPython runtime prefer its built-in C `framebuf` as the base for the
current extended `FrameBuffer`; desktop/package builds retain the bundled
pure-Python fallback. The first ST7796 patch restores the panel-qualified
RAM-continue solid-fill path without changing the generic `BusDisplay`
behavior used by panels that require a fresh window per strip. The second
ST7796 patch sends bounded 16 KiB chunks and fills its cached buffer without a
temporary repeated-bytes allocation, removing both per-strip overhead and
garbage-collection spikes observed on the physical board. The pinned
MicroPython 1.23 SPI patch retains the constructor-configured ESP GPIO matrix
while updating transfer parameters, matching the qualified legacy backend and
avoiding pin reconfiguration on every command. The item 5 TartLab adapters are
hash-pinned source inputs under
`vendor/compatibility/pydevices-candidate`, so they remain separate from both
upstream selection and upstream modifications.
