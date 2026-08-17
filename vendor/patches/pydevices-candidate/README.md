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
the complete upstream file. The item 5 TartLab adapters are hash-pinned source
inputs under `vendor/compatibility/pydevices-candidate`, so they remain separate
from both upstream selection and upstream modifications.
