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

These audit pins alone are not a runtime vendor lock or authorization to replace
or prune the historical payload. The generated candidate below defines the
separate runtime allowlist and compatibility surface; physical comparison and
promotion gates still precede any release-content change.

## Phase 4 generated candidate pipeline

`pydevices-candidate.lock.json` is the noninteractive, pinned allowlist for the
next migration stage. It cross-checks all four repository pins and all 47
audited equivalent source paths against `legacy-pydevices.upstream.json`, then
adds 18 explicit dependency files. There are no globs: all 65 upstream source
and destination paths are reviewed individually.

The lock separately pins five TartLab-owned compatibility adapters and the
retained local QOI reader under `compatibility/pydevices-candidate`. They expose
the legacy names used by the TartLab platform boundary and shipped examples
without changing upstream sources: `graphics`, `bmp565`, `touch_keypad`,
`eventsys.keys.Keys`, and the protected
`board_configs.t_display_s3_pro.board_config` path. The board adapter translates
the current `eventsys.Runtime` list-based polling contract back to the scalar
legacy `broker.poll()` result. The candidate also retains TartLab's GPL license
alongside the four upstream MIT licenses.

`tools/vendor_pydevices.py` reads file and license content from the pinned git
objects, so checkout line-ending settings cannot change its output. It compiles
every selected Python file with the host parser, requires the exact reviewed
sets of external and dynamic import sources, and generates:

- `runtime/`: the 71-file native-layout candidate;
- `licenses/`: four reviewed upstream MIT licenses and TartLab's GPL license;
- `provenance.json`: repository, source, destination, patch, content-hash, and
  runtime-identifier records; and
- `size-report.json`: totals grouped by repository and runtime top-level path.

Build from already-pinned local checkouts:

```text
python tools/vendor_pydevices.py --checkout-root build/upstream-audit --output build/vendor/pydevices-candidate --clean
```

Or let the tool fetch only the locked commits into a temporary build workspace:

```text
python tools/vendor_pydevices.py --fetch --output build/vendor/pydevices-candidate --clean
```

Changes to selected upstream files must be strict JSON patch manifests under
`patches/pydevices-candidate`. Each operation pins its complete input and output
hashes and exact replacement counts. The five approved patches cover the
MicroPython 1.23 parser, the selected display constructor contract, native
framebuffer selection, ST7796 solid fills, and ESP32 SPI transfer
configuration. TartLab compatibility files remain separate, source- and
hash-pinned inputs rather than patches disguised as upstream code.

At the current pins the generated runtime is 71 files and 521,163 normalized
source bytes, with runtime identifier
`sha256:090f9bd96352cfd8730e1bf3448112129f12e9f4954efbf5feb237b639783984`.
`tests/pydevices_candidate_compat.py` checks the legacy surface without board
hardware, and the pinned MicroPython 1.23 tier compiles every candidate module
for the ESP32 `xtensawin` emitter before running the same probe.

`tools/build_phase4_test_release.py` can produce an exact hardware-comparison
artifact from a normal legacy distribution and a generated candidate. It
verifies the source provenance, applies the locked Python minifier, and marks
the artifact `research-only-not-for-promotion`; the ordinary release path still
rejects a non-legacy vendor inventory. `tests/PHASE4_HARDWARE.md` records the
first physical result. Storage and full-frame transfer results are promising,
but startup and solid-fill regressions plus unobserved touch/color and OTA fault
cases keep item 6 partial. The checked-in historical payload remains the
release source.
