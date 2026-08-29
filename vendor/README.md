# Legacy PyDevices vendor model

TartLab keeps three separate records so historical evidence, upstream research,
and the release payload are not confused.

## Historical lock

`legacy-pydevices.lock.json` identifies both the source snapshot tracked under
`src/lib/pydevices` and the 145-file payload captured from deployed
MicroPython 1.23 devices. Their hashes intentionally differ because the old
distribution omitted one later tracked source file. The original upstream
commit was never recorded; its provenance remains incomplete and must not be
invented.

Validate with:

```text
python tools/vendor_lock.py
```

Use `--write` only after reviewing an intentional historical-lock change.

## Reachability and upstream audit

`legacy-pydevices.imports.json` partitions every historical payload file from
the core/IDE, T-Display-S3 Pro adapter, and shipped-example roots. It records 39
statically reachable files and 107 retained but unreachable files. Dynamic
string imports and non-Python resources require explicit review.

`legacy-pydevices.upstream.json` maps the reachable set to exact commits in
`pydisplay`, canonical `pydevices`, `pygraphics`, and `palettes`, including
license hashes. Thirty-eight files have maintained equivalents; TartLab's QOI
reader does not. None is a drop-in legacy replacement.

Validate these records with:

```text
python tools/pydevices_inventory.py
python tools/pydevices_inventory.py --dist build/legacy/dist
python tools/pydevices_upstream.py
```

The audit is evidence and does not itself change release content.

## Generated release payload

`pydevices-candidate.lock.json` pins 65 upstream files, five TartLab
compatibility adapters, the retained QOI reader, four upstream MIT licenses,
and TartLab's GPL license. There are no source globs. Strict patch manifests
pin complete input/output hashes and replacement counts.

Generate the payload from exact Git objects with:

```text
python tools/vendor_pydevices.py --fetch --output build/vendor/pydevices-candidate --clean
```

The output contains the 71-file runtime, licenses, deterministic provenance, and
a size report. At the promoted pins its source identifier is
`sha256:277bc307b4e20dc07afd61580e737800f639a161ac2a9a341c4febef981fe23c`.
After minification and MicroPython 1.23 `xtensawin` compilation, the packaged
identifier is
`sha256:409eda4922f6b66c7fde8cdbca75489d15813749e6ef607ed94e4f81d67dc034`.

`tools/build_promoted_release.py` accepts only those physically qualified
identities from `profiles/legacy-mp123.json`. The historical tree remains an
audited fallback/input; it is not the normal release payload.
`tools/build_phase4_test_release.py` always creates a research-only comparison.
Physical evidence is summarized in `tests/PHASE4_HARDWARE.md`.
