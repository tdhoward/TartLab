# Button navigation and non-touch device support

Status: Planned. No modern non-touch board support is implemented or qualified
by this document.

## Objective and scope

Make TartLab useful on devices with a display and physical navigation buttons,
starting with the LilyGO T-Display-S3 (non-Pro, non-touch version) available for
bench development. The primary value is browser-based MicroPython programming,
local app selection, and running display-oriented student projects.

The first milestone must provide:

- Startup access to the IDE, the selected app, and the local app chooser.
- Button navigation through folders, app selection, confirmation, and cancel.
- Access to device settings, including brightness, dim timeout, saved-network
  removal, and update checks and confirmation.
- Normal browser IDE access, including the Wi-Fi setup access-point workflow.
- A small display example that demonstrates button input and a dependable
  return to the IDE. Reset to the normal IDE startup route is an acceptable
  initial escape path; document it and verify it on hardware.

Existing example-app compatibility is not a completion requirement. Racer is
an optional follow-up because its controls already reduce to left and right.
Snake, Testris, calculator, and other touch-oriented apps may remain unsupported
on non-touch devices. Do not expand this project into a general app-control
redesign, button-driven pointer emulation, or on-device text entry. Wi-Fi
credential entry remains a browser workflow.

## Navigation contract

Use a simple initial two-button interaction:

- Button A advances focus to the next enabled control and wraps at the end.
- Button B activates the focused control.
- Every nested page has an explicit focusable Back or Cancel control.

Show a clear focus indicator and concise button hints. Focus order must follow
the visible reading order, skip unavailable controls, and scroll the focused
control into view. Opening a page must establish predictable focus; replacing
or deleting a page must release its previous focus objects and callbacks.
Confirmation pages must initially focus the non-destructive choice.

Any navigation input cancels the launcher countdown. After dimming, the first
button press wakes the display without activating a control; consume the whole
press/release gesture so its release cannot trigger an action. Held buttons
must not cause duplicate selections or leak an activation across page or
UI/app transitions. Implement debounce and explicit press/release handling.
Long presses, chords, and reverse navigation are optional later improvements,
not prerequisites for reaching any essential function.

Prefer LVGL keypad input and focus groups for the existing launcher and settings
widgets. Settings already use buttons for increment/decrement and navigation;
reuse their actions and deferred service execution. Verify the required APIs
against the pinned MicroPython/LVGL binding before committing to an adapter.
LVGL describes the underlying model in its [focus-group documentation](https://lvgl.io/docs/open/9.5/main-modules/indev/groups.html).

## Architecture work

The current implementation has several assumptions to remove deliberately:

- `src/lib/tartlabutils/board.py` requires a touch driver and permits only one
  entry per pin type. Define an explicit absent-touch representation and a
  compatible way to identify multiple typed buttons. Preserve existing board
  payloads and unique-purpose pin lookup; do not simply allow ambiguous matches.
- `src/lib/tartlabutils/factory.py` always constructs SPI and touch hardware.
  Select transport and optional input from declarative configuration instead.
- Runtime capabilities already distinguish touch presence, but startup selects
  the touchscreen launcher based on LVGL availability. Keep UI availability,
  pointer availability, and button navigation distinct through startup, IDE
  settings, power management, and app execution.
- `TouchGrid` requires touch input. Keep that contract honest and expose reusable
  physical-button input separately; a keypad must not masquerade as a pointer.

Each board runtime must remain one hard-coded, declarative `BOARD_CONFIG`.
GPIO numbers, polarity, power sequencing parameters, bus wiring, panel geometry,
and controller quirks belong in that payload. Shared code discovers capabilities
and purpose from configuration, never from board identities. Reusable transport,
driver, debounce, and input-ownership behavior belongs in shared modules.

Keep generic button events and focus support app-agnostic. The launcher and IDE
own their focus order, page actions, and layout; individual apps own gameplay
mappings. Define input ownership alongside the existing LVGL/direct-rendering
ownership transitions, including cleanup and stale-event suppression. Preserve
touch navigation on existing boards and legacy startup-button behavior.

For touch-only apps, provide a clear unsupported-input message and a usable IDE
fallback rather than an unexplained startup failure. Do not require a new app
manifest system or retrofit every example to accomplish this.

## Initial board investigation

Treat the non-Pro T-Display-S3 as a separate modern port. The older
[`src/configs/t_display_s3.py`](src/configs/t_display_s3.py) and
[PyDevices board configuration](src/lib/pydevices/board_configs/t_display_s3/board_config.py)
are reference material, not modern support or qualification evidence. Modern
distributions must continue to exclude the legacy PyDevices payload.

Confirm the exact unit against [LilyGO's hardware documentation](https://github.com/Xinyuan-LilyGO/T-Display-S3).
Investigate its parallel ST7789 display path, display power/reset behavior,
button behavior during reset, and available firmware drivers. One navigation
button also serves as BOOT, so normal navigation must not depend on holding it
through reset. Verify readable launcher, status, and settings layouts on the
smaller display, including scrolled content and confirmation pages.

Record concrete hardware values in the eventual board payload and board-local
bring-up notes. Use the existing board lifecycle and firmware provenance process
in [`BOARD_SUPPORT.md`](BOARD_SUPPORT.md); retain experimental status until the
required artifacts and evidence exist.

## Development sequence and completion evidence

1. **Establish the board path.** Create a `bringup` catalog entry with verified
   hardware references. Determine the reproducible modern firmware/driver path
   and implement the reusable transport additions needed for display output.
   Check display, backlight, buttons, and reset on the physical unit before
   investing in app adaptations.
2. **Implement capability-based input.** Extend configuration validation,
   optional-touch construction, multiple-button input, and ownership handling.
   Add host coverage for absent touch, existing touch boards, debounce,
   press/release behavior, and capability reporting.
3. **Complete core navigation.** Integrate focus into launcher, chooser, and
   settings; adapt layouts where needed. Cover countdown cancellation,
   scrolling, Back/Cancel, confirmation, disabled/busy controls, page cleanup,
   and wake-press consumption in host tests and focused physical checks.
4. **Demonstrate the programming workflow.** On the new board, connect through
   the setup AP and configured Wi-Fi, edit/save/run from the browser, select
   and launch a simple app locally, exercise buttons, and return to the IDE.
   Verify the touch-only app fallback. Record usability observations and
   memory/display limitations. This establishes the experimental milestone.
5. **Qualify before promotion.** Complete new-board firmware, provisioning,
   update/recovery, reset, and resource qualification under the existing release
   policy. Run fresh regressions on existing boards for affected shared input,
   startup, power, and display behavior. The experimental milestone alone does
   not establish supported-board status.

Use [`tests/TEST_TIERS.md`](tests/TEST_TIERS.md) to select the smallest test
environment that establishes each claim. Extend capability-specific tests and
qualification tooling to represent absent touch explicitly; record touch-only
checks as inapplicable with a reason and substitute actual button-navigation
evidence. Never report a touch pass for hardware without touch, or silently
drop required board qualification gates.

After the core milestone, assess navigation comfort and ongoing board-support
cost before adding convenience gestures or example adaptations. Racer may be
used as a further demonstration, but its implementation and qualification must
not block completion of basic non-touch support.
