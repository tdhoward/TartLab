# Repository architecture rules

- Never place board-specific values, pin numbers, electrical polarity, panel
  geometry, bus wiring, controller quirks, or board identities in shared files.
- Each board runtime payload must expose one hard-coded `BOARD_CONFIG` object
  containing its board-specific parameters. Shared startup and platform code
  must discover behavior through that object.
- Represent useful GPIOs in `BOARD_CONFIG["pins"]` as typed entries (for
  example `BUTTON`, `BACKLIGHT`, `DISPLAY_RESET`, or `TOUCH_INTERRUPT`) so
  shared code can look them up by purpose instead of knowing a board model.
- Board payloads are declarative configuration only. They may reference the
  appropriate driver or reusable adapter, but must not implement driver,
  transport, rendering, or ownership logic.
- Put behavior that can apply to more than one board in shared modules and
  eliminate duplicated factory or adapter code wherever practical.
