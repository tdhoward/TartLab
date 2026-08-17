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

## Phase 4 import and payload inventory

`legacy-pydevices.imports.json` is the reviewed, machine-readable partition of
the legacy payload. `tools/pydevices_inventory.py` conservatively follows every
static import, including conditional and function-local imports, from three
separate root groups:

- TartLab core startup and IDE display rendering;
- the default T-Display-S3 Pro legacy adapter; and
- all shipped Python examples.

Shared files are assigned to the first category that reaches them. The
`hdwconfig` import is a deliberate boundary between core/example code and the
board-adapter category. MicroPython's built-in `framebuf` and `micropython`
modules take precedence over same-named historical add-on files. Imports built
from runtime strings are outside static analysis and must be represented by an
explicit root if introduced. Non-Python resources are not inferred from imports
and remain in the explicitly retained partition until separately reviewed.

The initial inventory records 39 reachable Python files and 107 files retained
from the historical payload without a static path from those roots. This is
evidence for later pruning, not authorization to remove the retained files.
Verify source and reachability with:

```text
python tools/pydevices_inventory.py
```

After building a distribution, also compare its exact vendor paths with the
reviewed payload partition:

```text
python tools/pydevices_inventory.py --dist build/legacy/dist
```

Only use `--write` after reviewing an intentional root, import, category, or
payload change. Updating the file is an explicit allowlist decision; it must not
be used merely to make a failing check pass.

## Phase 4 current-upstream mapping

`legacy-pydevices.upstream.json` maps every one of the 39 reviewed reachable
files to exact paths in current official upstream trees. The audit pins full
commits for `pydisplay`, `pydevices` (the canonical destination of the former
`micropython-hardware` repository), `pygraphics`, and the separately maintained
`palettes` package. It also records each repository's MIT license content.

The mapping found maintained equivalents for 38 files. TartLab's QOI reader has
no current equivalent in those trees. None of the 39 files is marked drop-in
compatible: packages and paths moved, and the display, event, timer, graphics,
and board APIs have materially evolved. In particular, a maintained
T-Display-S3 Pro board configuration exists upstream, but it does not expose
the legacy `Broker`-based board contract used by this snapshot.

Verify the mapping's schema, repository pins, and exact inventory coverage with:

```text
python tools/pydevices_upstream.py
```

When the four pinned repositories are already checked out beneath a directory,
the optional checkout check also verifies each git HEAD, mapped path, and
license hash without fetching from the network:

```text
python tools/pydevices_upstream.py --checkout-root build/upstream-audit
```

These are research pins, not a runtime vendor lock or authorization to replace
or prune the historical payload. Phase 4 must still define and validate the
legacy compatibility adapters and generated allowlist before changing release
contents.
