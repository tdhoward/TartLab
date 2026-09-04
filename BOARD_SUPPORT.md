# TartLab modern board support

TartLab treats a runtime profile, a physical board, and a release as separate
things:

- a **runtime profile** defines the common MicroPython, LVGL, filesystem, OTA,
  and recovery contract;
- a **board descriptor** identifies one hardware family/revision and binds it
  to its selector, firmware, capabilities, and qualification evidence; and
- a **release** contains shared TartLab filesystem packages plus an explicit
  compatibility matrix of accepted board and firmware identities.

This separation lets many boards share `lvgl-modern` without copying the IDE,
updater, recovery code, or release pipeline for each board. It also prevents an
experimental port from silently becoming a supported target.

## Repository layout

The intended layout is:

```text
boards/
  <board_id>/
    board.json                 Host-side identity and lifecycle record
    runtime/
      <selector_module>.py     One declarative BOARD_CONFIG object
src/
  lib/
    tartlabutils/
      board.py                 Typed-pin and board-reference helpers
      platform.py              Stable application-facing platform boundary
      modern.py                Shared LVGL/direct-surface implementation
      modern_factory.py        Shared declarative board constructor
firmware/lvgl-modern/
  pydevices/runtime/           Non-production comparison adapters
  boards/
    <board_id>/                Board-only native overlays, locks, and provenance
tests/
  boards/
    <board_id>/                Board contract tests and sanitized evidence
```

Board runtime source belongs beside its descriptor. It is not copied into
`src/lib/tartlabutils`, and experimental comparison adapters do not live under
`src` at all. A distribution build must name its board IDs explicitly; the
builder stages only those runtime directories beneath `dist/board/<board_id>`.

`boards/<board_id>/board.json` is the source of truth for board-specific host
tooling. The catalog is discovered by directory scan, so adding a board does
not require editing a central Python list. Run:

```text
python tools/check_board_catalog.py
```

The checker rejects duplicate IDs/selectors, missing files, malformed hardware
records, invalid firmware hashes, and lifecycle records that claim more support
than their artifacts justify.

## Board lifecycle

Each descriptor has one of these states:

| State | Meaning | Required descriptor fields |
| --- | --- | --- |
| `bringup` | Hardware research or an unqualified bench prototype | Hardware and documentation |
| `candidate` | Complete adapter and reproducible firmware awaiting physical qualification | Selector and firmware identity |
| `qualified` | Supported by a promoted, board-bound release record | Selector, firmware, and qualification evidence |
| `retired` | No longer offered for new installation; retained for update/recovery policy | Its last known identities and retirement policy documentation |

Changing a word in a descriptor does not advance the lifecycle. A candidate
becomes qualified only after the exact firmware and release candidate pass the
physical gates and their sanitized evidence is promoted.

## Runtime boundary

Student programs, the IDE, launcher, updater, and recovery code use
`tartlabutils.platform`; they must never import board pins or panel drivers.
Every modern board adapter exposes the same capabilities:

- Wi-Fi station and setup access point;
- an LVGL status/UI mode;
- touch or pointer input when present;
- brightness and delay;
- IDE-button behavior, including an explicit no-button policy if necessary;
- an `RGB565_BE` direct dirty-rectangle surface; and
- exclusive, completion-signaled ownership between LVGL and direct rendering.

Each board module contains one hard-coded `BOARD_CONFIG` object and no runtime
implementation. Its typed `pins` entries describe GPIO purpose, number, and
electrical polarity; its display and touch records reference the appropriate
drivers and any reusable adapter. Shared factory code constructs buses,
displays, input devices, and reset/backlight policy from that object.
Controller-specific behavior that can apply to another board, such as QSPI
command packing or dirty-rectangle alignment, belongs in a shared driver
adapter rather than the board payload, games, or IDE.

Optional display accelerators follow the same boundary. The public canvas
operation must have a correct software implementation on every board. A
`BOARD_CONFIG` display record may declaratively select a reusable accelerator
adapter and provide unavoidable hardware constraints, while shared surface code
negotiates whether a concrete operation is supported. Capabilities such as
panel scanout scrolling must be reported in final logical coordinates after
panel and canvas rotation; they must not be inferred from a board ID, display
resolution, or driver name. Register commands, wraparound address translation,
transfer serialization, and ownership cleanup belong in the reusable adapter
and shared controller code.

The early recovery gate reads this same object through the protected selector
to turn off a typed `BACKLIGHT` pin. Shared startup code therefore never
contains a board ID, board-specific GPIO number, or per-board lookup table.

The selector stored at `/device/hdwconfig.py` remains a protected local device
property. It contains only a generated comment and an import of the module
named by the descriptor. Before importing it, `tartlabutils.platform` reads the
protected `/device/board.json` identity and adds only `/board/<board_id>` to the
module search path. That protected board path precedes the release root and
`/files/user`, so student modules cannot shadow the selected hardware shim. OTA
may update that board-owned directory and shared runtime, but it must not
overwrite the selector, identity, or local calibration.

## Compatibility and releases

The published `modern-v0.14.8` profile predates the board catalog and contains
one firmware identity. New candidate builds dual-write that legacy firmware
alias and a schema-2 compatibility matrix keyed by `board_id`. The alias
preserves manifest-format compatibility with the published lab reference; no
field-deployed device depends on it. New updater and recovery code select the
board-specific matrix entry. Each entry binds:

- accepted PCB revisions or an explicit revision policy;
- flash and PSRAM requirements;
- selector module;
- exact firmware SHA-256, flash offset, build lock, and provenance; and
- the release's shared runtime-profile and filesystem contract.

Candidate qualification evidence is a separate schema-2 aggregate keyed by the
same board IDs. Protected promotion requires its board set and firmware hashes
to match the release matrix exactly, so a multi-board release cannot inherit
evidence from only the default board.

Shared filesystem packages are built once. Modern releases additionally carry
one authenticated `board-support.tar` with one top-level directory per board in
the compatibility matrix. Its manifest entry uses the
`board-id-subtree` selection policy. Provisioning, normal OTA, and recovery all
download and validate the complete archive, cross-check release state against
protected `/device/board.json`, clear the dedicated `/board` destination, and
extract only the matching subtree. An absent, malformed, incompatible, or
conflicting board identity fails closed before active board files are changed.
The full archive remains simple to publish and authenticate while an individual
device stores only its own shim and board defaults. Authenticated per-board
expanded-size metadata makes the install-space check reserve room for the
selected subtree rather than every board in the archive; download-space checks
still account for the complete archive. A missing or invalid size for the
protected board identity rejects the manifest; it must not fall back to the
compressed size of the complete archive.

The modern platform remains in early alpha and has no field-deployed devices.
Consequently, the first supported modern alpha may include multiple boards in
`board-support.tar` without an intermediate single-board bridge. The candidate
itself must contain the selection-aware updater and recovery path, and its
schema-2 evidence must qualify every included board. If any modern version is
field-deployed before that release is promoted, re-evaluate this assumption and
design an explicit compatibility path before publishing a selection behavior
that an installed updater cannot interpret. Device OTA continues to update
filesystem content only. Firmware changes remain an authenticated adult
provisioning operation.

Provisioning must select a descriptor explicitly, verify its support state,
check observable hardware properties before erase, and install only the bound
firmware and selector. When a board cannot be identified uniquely in software,
the tool must require an explicit adult confirmation rather than guessing.
The selected identity is stored in protected `/device/board.json`, the
repository state, and the resumable provisioning journal. The protected value
is authoritative; a mismatch with repository state rejects an update. Use
`--board` for provisioning and repeat `--board` when building both the
distribution and candidate that deliberately contain more than one candidate
or qualified board.

## Adding a board

The repeatable path is:

1. Create `boards/<board_id>/board.json` in `bringup` state and link its research
   or bring-up document. Use a stable lowercase underscore ID; do not encode a
   temporary COM port or an individual unit serial number.
2. Pass stock-MicroPython gates for console recovery, flash, PSRAM, filesystem,
   Wi-Fi, reset, and power.
3. Prove display and input independently on TartLab's pinned runtime. Record
   geometry, orientation, transport, clocks, buffering, color order, touch,
   heap, reset behavior, all controller constraints, and any optional
   acceleration claimed by the board. Qualify an accelerator independently for
   every advertised orientation and fallback case.
4. Add `boards/<board_id>/runtime/<selector_module>.py` containing only one
   `BOARD_CONFIG` assignment, and declare its runtime source and
   `/board/<board_id>` target in the descriptor. Put pins, bus parameters,
   driver references, geometry, rotation, electrical policy, and true
   board-specific quirks in that object. Put construction, UI, ownership,
   transport, and driver behavior in reusable `tartlabutils` modules.
5. Add a reproducible firmware overlay only when the board needs native changes.
   Pin every source and license and record a unique firmware identity even when
   most of the source graph is shared.
6. Exercise the complete TartLab filesystem, including at least 100 transitions
   between LVGL and direct rendering, representative examples, Wi-Fi, browser
   UI, reset cycles, and resource margins. Modern touchscreen candidates also
   follow `tests/MODERN_TOUCHSCREEN_QUALIFICATION.md`.
7. Change the descriptor to `candidate`, run the catalog and hardware-free
   suites, and build the exact candidate release.
8. Run clean provisioning, interruption/resume, OTA, recovery, rollback,
   protected-state, feed-isolation, and future-update physical gates.
9. Attach sanitized board-bound evidence and change the descriptor to
   `qualified` only as part of protected promotion.

The physical gates remain deliberate because they protect classroom devices.
The catalog, shared probes, generated selectors, compatibility matrix, and one
release pipeline are what keep the routine parts from becoming repetitive.

## Review rules

- A new board should normally add one descriptor, one declarative payload,
  focused tests, and—only if needed—a reusable driver adapter or firmware
  overlay.
- Do not fork the IDE, updater, recovery flow, or release repository per board.
- Do not use display resolution or flash size as a unique board identity.
- Do not infer or special-case an optional hardware accelerator from board
  identity, geometry, or controller name; select and qualify a reusable adapter
  through the declarative payload.
- Do not let an unqualified descriptor appear in provisioning defaults or a
  stable compatibility matrix.
- Do not copy board payloads or comparison-only adapters into
  `src/lib/tartlabutils`.
- Do not derive the installed board subtree from student settings, archive
  names, or hardware guesses; use the protected provisioned identity.
- Do not edit historical evidence to match current structure; add new evidence
  for the new candidate.
- Keep raw logs, dumps, credentials, USB mappings, and unit identifiers out of
  descriptors and source control.
