# Grid puzzle device and operator workflow

Use the modern platform. Keep the complete workload matrix and actual failed or
pending observations. The benchmark and installation commands use COM18 by
default; neither flashes firmware or writes student files/selected-app settings.
Serial work temporarily interrupts the running app and restores normal startup
when finished. Installation is a development update, not release qualification.

## Measure and resume

```powershell
python tools/grid_puzzle_benchmark.py run --port COM18 --output build/grid_puzzle/device
python tools/grid_puzzle_benchmark.py status --output build/grid_puzzle/device
```

The default is 120 samples per case, 50 ms frames, and all eleven workloads in
normal/debug modes. `--frame-ms 60` tests the other proposed fixed cadence.
`--samples 40` is the minimum diagnostic run. The recorded Phase 5 run used 40
samples at `build/grid_puzzle/com18-phase5`; its performance result is **failed**.

The tool stages verified probe-owned files under `/_grid_puzzle_benchmark`,
loads the actual editable engine, and temporarily loads the working canvas
module in memory. It derives board identity, dimensions, rotation, capabilities,
installed-runtime hashes, startup/heap statistics and frame timings. It preserves
`report.json` and individual logs after each completed case. Rerun the same
command to resume; successful cases are skipped. Changed source, assets, sample
settings or device identity require a fresh output directory.

For a focused diagnosis, `--cases 07-normal 08-normal` selects the dense rooms.
Every omitted case remains pending and a partial matrix cannot pass. Repeat the
command without `--cases` to finish the matrix. A zero median or a room freezing
after death is not evidence of adequate moving performance: reports retain the
maximum, deadline/drop counters and playing/frozen sample counts.

## Development install

```powershell
python tools/grid_puzzle_benchmark.py install --port COM18 --output build/grid_puzzle/device
```

This rebuilds and installs the IDE browser assets with JSON text-tab support,
installs the game source, level data, guide, atlas and required canvas helper,
then merges only the three game Help entries into the existing manifest.
The build log is retained as `ide-build.log`. A build failure stops installation
before serial access. Browser assets use the normal distribution's compression.
Writes are staged and hash-verified before renaming. Prior existing bytes are
saved under `device-backup`; `install.json` records old/new hashes. Existing
student experiments and selected-app settings are untouched. Open **Grid puzzle**
under **Help / Examples** after normal startup, save a user copy and run it using
the existing editor flow.
After an IDE update, hard-refresh the browser with Ctrl+Shift+R (or Cmd+Shift+R)
and reopen the file; the server normally permits cached assets for an hour.

## Supply actual observations

Open generated `operator.ini`. Enter observer and the actual completion time as
an ISO UTC timestamp, for example `2026-09-11T20:00:00Z`. Each section has its
procedure, a pending status and space for notes. Set `passed` only after doing
that check; record unsuccessful checks as `failed`. Keep unperformed checks
pending. Status validates binding, identity fields, each result and observation
notes, and also reports unfinished measurements/performance failures.

The form covers:

- Full-room art/readability, water edges, all hazard states and hidden features.
- All four touch directions, hold/release, hint acknowledgement, pause, restart
  and return to UI; repeat after death and room changes.
- DBG overlays and removal, selecting and paging cells, and paused single-step.
  Choose a direction while paused, release it, then Step. Fresh inspector steps
  are idle until a direction is selected. Hints require acknowledgement first.
- Help-open/save-renamed-copy/reopen for Python and JSON, including JSON's lack
  of Run/Set as App; explicit JSON path and independent rule/room edits.
- IDE and selected-app launches, broken-code/blocked-loop recovery using the
  guide's existing interrupt/reset routes, and independent restoration from Help.

Use the focused hazard rooms in `tests/fixtures/grid_puzzle/hazards.json` as
custom JSON when observing each hazard; they include intentional deaths and are
not a solved campaign. Keep the previous Phase 3/4 observation details alongside
the form. Machine timings cannot establish control comfort, fairness, visible
clarity or whether a human completed an editing/recovery exercise.

For an eventual modern release, start with
[RELEASE_QUALIFICATION.md](../RELEASE_QUALIFICATION.md). Its candidate-bound
qualification forms and applicable shared-platform gates remain separate.
