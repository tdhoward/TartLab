# Legacy vendor payload lock

`legacy-pydevices.lock.json` records two different historical facts:

- the normalized content of the PyDevices source snapshot currently tracked in
  `src/lib/pydevices`; and
- the exact 145-file, 729,986-byte minified payload captured from the deployed
  MicroPython 1.23.0 baseline.

They intentionally have different identifiers. The historical build output was
stale and omitted one later tracked PyDevices source file. The original
distillation script named the upstream `PyDevices/pydisplay` repository but did
not record its commit, so the provenance status remains
`incomplete-historical-snapshot`; do not invent an upstream revision.

Run `python tools/vendor_lock.py` in CI or before building. Only use
`python tools/vendor_lock.py --write` after reviewing an intentional vendor
change and its upstream license/provenance. Phase 4 must replace the missing
upstream revision with a pinned source and allowlist before changing this
historical snapshot.
