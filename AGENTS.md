# Process efficiency

- Optimize every process we develop for low AI token usage and few agent/user
  exchanges. Put routine orchestration, validation, hashing, and reporting in
  deterministic tools; use the agent for decisions, exceptions, and fixes.
- Provide a short entry point, sensible defaults, resumable state, and concise
  status/error output. Keep full logs in artifacts; inspect relevant failed
  steps instead of repeatedly reading transcripts or rerunning successful work.
- Generate operator forms for physical observations and judgment calls. Derive
  machine-known values automatically and validate completed forms. Never infer
  a pass, fabricate observations, or reduce required coverage to save tokens.
- For modern release qualification, start with `RELEASE_QUALIFICATION.md` and
  `tools/qualification_session.py`; consult detailed policy/tooling docs when
  the summary or an exception requires them.

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
- Keep `src/lib/tartlabutils` app-agnostic. Shared module names, public APIs,
  state, and terminology must describe reusable capabilities rather than a
  particular help app, game, or demo.
- Keep app rules, app-specific state, rendering policy, and visual geometry in
  the app. Before promoting code into `tartlabutils`, remove those concerns and
  make sure the resulting API has plausible uses in multiple applications.
