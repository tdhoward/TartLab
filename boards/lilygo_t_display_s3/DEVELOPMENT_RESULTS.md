# Buttons-only development integration

Date: 2026-09-09. Status: experimental `bringup`, not a qualified release.

This continues the [initial bench results](BRINGUP_RESULTS.md). The fixture now
runs the shared modern platform and TartLab filesystem with a protected
non-Pro board identity and selector. No Pro selector, PyDevices payload,
firmware rebuild, supported release, or promotion was used.

## Implementation

- One declarative `runtime/t_display_s3_modern.py` holds typed GPIOs, power
  sequencing, 16 MHz I80 wiring, BGR/inversion, tested landscape geometry,
  absent touch and the A/B navigation mapping.
- Shared construction chooses SPI or I80 and creates no I2C/touch driver for
  `touch=None`. Purpose-only lookup remains unambiguous; multiple typed buttons
  require distinct names. Existing unnamed single-button boards retain their
  original IDE-button path.
- `tartlabutils.buttons.ButtonInput` provides polled, debounced `(name, pressed)`
  edges. Defaults: 30 ms stability; no repeats; suppress held input through
  release at initialization, page changes, and UI/app transitions.
- `tartlabutils.navigation` drives a native LVGL keypad and page-owned focus
  groups. A advances and wraps; B activates; actions occur on physical release.
  Focus scrolls controls into view. Page replacement deletes groups before
  widgets and clears pending gestures/callbacks. Confirmation starts on Cancel
  or Back; disabled controls cannot activate actions.
- Launcher, chooser and settings reuse their existing actions. Compact labels
  and button hints fit the smaller screen; settings retain a vertical scrolling
  body. Button activity cancels countdown and wakes a dimmed IDE without
  activating the first press/release gesture.
- `platform.read_button_events()` requires direct-rendering ownership. Touch
  remains an honest separate capability; `TouchGrid` raises an explicit
  unsupported-input error. Startup falls back to the IDE using the existing
  app-error route; the IDE explains the missing input and retains its address.
- The modern help menu contains `buttons.py`, a direct-rendered counter with a
  restart action. It belongs to the modern help tree, not legacy help or shared
  runtime. A copy is installed as the local development fixture's selected app.

## Driver and firmware provenance

The device still uses the byte-verified 2,978,512-byte reference firmware:
SHA-256 `187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab`.
Its existing native I80 implementation is sufficient for this stage.

The ST7789 driver and init table are packaged under
`src/lib/tartlabdrivers/display/`, derived from
`api_drivers/common_api_drivers/display/st7789/` at upstream
`lvgl_micropython` commit `d2d26467fa4cb9e99e569d899709043d086f7a6f`.
Both retain the upstream MIT notice. Original source hashes are in the initial
bench record. The only behavioral integration change is package-relative init
lookup; the panel always uses per-region addressing rather than the upstream
full-frame shortcut. No new board-specific native overlay is needed so far.

The modern profile's current-source adapter hashes include the new shared
button/navigation modules. These source integrity checks do not establish new
physical qualification. Published firmware/release evidence was not changed.
The board's firmware/qualification descriptor fields remain null pending the
candidate contract and applicable full qualification; it stays `bringup`.

## Evidence established

| Check | Result / limit |
| --- | --- |
| Full development filesystem boot | Reached `healthy`, mode IDE, zero consecutive boot failures |
| Native keypad API | Create/read/reset, focus groups, wrap and cleanup exercised on the pinned firmware |
| UI/direct display transitions | 100 cycles with actual DMA rectangle writes; navigation disabled in app mode and restored in UI |
| Transition memory | Collected free heap 8,136,560 before, 8,136,688 after; not a long-duration stress test |
| Launcher/chooser | Injected button edges through native LVGL traversed home, chooser, safe Cancel focus, selection persistence callback and IDE route |
| Settings | Native LVGL traversal exercised brightness edit/Save, scrolling to offscreen controls, WiFi/Back, update confirmation with Back initially focused, and busy-state exclusion |
| Dim/wake | Native keypad test consumed the first full B gesture while dimmed; the next B gesture opened Settings |
| Missing touch | Real `TouchGrid` construction raised the intended explicit error; running the actual startup definitions with this failing app returned to the native IDE view and displayed the explanation plus reset hint |
| Wi-Fi/browser | Owner reported the Wi-Fi and browser tests worked; setup AP and browser workflow confirmed. Configured-station association was not independently established |
| Physical navigation follow-up | Owner confirmed navigating using only buttons, entering Settings, adjusting and saving brightness, and opening the WiFi page |
| Physical dim/wake follow-up | Owner confirmed dimming after three minutes and waking with a button without activating Settings |

The native navigation probes replace GPIO events with a deterministic feed;
they exercise real LVGL behavior, not actual button mechanics. Independent
physical press/release and visual panel evidence is in the initial bench
record. Keep that distinction when reusing these observations.

Host validation includes button/polarity/debounce tests, configuration and I80
wiring, countdown cancellation, confirmation defaults, page cleanup,
ownership, wake consumption, existing touch-board behavior, app rendering,
startup, IDE, packaging, provisioning and update/recovery regressions. Both
modern and legacy production filesystem builds pass; modern excludes PyDevices
and legacy excludes the modern driver package and button help example. The
web build reports its existing bundle-size performance warnings.

Final automated result: **347 tests passed**, using:

```text
python -m unittest tests.test_buttons tests.test_button_pages tests.test_t_display_s3 tests.test_phase5 tests.test_platform tests.test_device_settings tests.test_power tests.test_headless_ide tests.test_elecrow_dle06235b tests.test_phase1 tests.test_phase2 tests.test_phase6 tests.test_phase6_provisioning tests.test_board_catalog tests.test_modern_profile tests.test_drivers tests.test_phase4 tests.test_app tests.test_image_examples -q
```

`check_board_catalog.py`, `check_firmware_artifacts.py`,
`check_modern_profile.py`, source parsing and `git diff --check` passed. Modern
and legacy verified builds contain 77 / 213 files and 517,009 / 1,227,758 expanded
bytes respectively. These are filesystem builds, not signed release artifacts.

## Handoff and remaining qualification

The device is a development installation, with `buttons.py` selected. Release
checks use the modern feed and its protected board identity; this board is not
in a supported compatibility matrix. Do not promote the descriptor based on
this development smoke or install a release intended for a different board.

Integration handoff state: mode IDE, `health=healthy`, zero consecutive failures,
boot sequence 5, 8,110,224 collected free heap bytes, touch absent and button
navigation present. The normal IDE server was restarted after inspection.
No saved station network was present; AP/browser evidence must not be reported
as configured-station qualification. The owner subsequently confirmed the
button-only navigation, brightness save, WiFi page and three-minute dim/wake
behavior described above. Counter increments and the app's restart action have
not yet been explicitly confirmed. The earlier physical button and color
results are preserved separately.

The owner reported that the enlarged text-labelled Settings entry crowded the
status text. Restored the original 36 x 32 gear-icon entry while retaining its
button focus, activation and navigation hints. The correction changes only the
entry presentation; saved brightness and network settings are preserved.
The correction was installed on COM5 with a verified file hash and unchanged
settings-file digest. Native LVGL inspection confirmed the gear symbol,
36 x 32 dimensions and button focus. The 30 focused button-page, settings and
power tests passed. After installation, boot sequence 7 was healthy in IDE
mode with zero consecutive failures, and the IDE server was resumed.

Raw logs and temporary host probes remain ignored in
`hardware_test_artifacts/t_display_s3_bringup_20260909/`. The setup AP used for
the browser smoke is `TartLab-Buttons`; no network credentials are checked in.

Still required before support/promotion: PCB revision identification;
authenticated candidate/firmware binding; power-cycle and held-button/reset
campaigns; sustained heap/radio/rendering checks; provisioning interruptions,
OTA/recovery and protected-state qualification; and fresh physical regressions
on existing touch boards affected by shared runtime/UI changes. No such tests
are claimed by host passes. Touch checks are inapplicable because touch is
absent; actual button-navigation evidence must substitute in qualification.
