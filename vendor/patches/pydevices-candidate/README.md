# PyDevices candidate compatibility patches

Compatibility patches for the generated Phase 4 candidate belong here as
strict JSON patch manifests. The candidate lock records each patch path and
SHA-256; unlisted files are never applied.

Each patch manifest has `schema: 1` and an `operations` list. Every operation
names an allowlisted runtime destination, pins its complete preimage and result
SHA-256 values, and contains exact text replacements with an expected match
count. The vendor tool rejects fuzzy matches, unselected paths, stale hashes,
and unexpected dependencies introduced by a patch.

No compatibility patch is approved yet. Item 5 will add only the adapters
required by the MicroPython 1.23 legacy profile and will keep them separate from
the upstream source selection.
