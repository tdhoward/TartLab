# CST226 upstream contribution recommendations

Date: 2026-08-31

This note preserves the recommended follow-up for
[lvgl-micropython PR #575](https://github.com/lvgl-micropython/lvgl_micropython/pull/575).
It is planning guidance only. TartLab does not depend on the PR being changed or
merged, and no upstream repository or pull request was modified while preparing
this note.

## Observed behavior

The T-Display-S3 Pro fixture identifies its touch controller as a CST226SE at
I2C address `0x5A`. PR #575 already writes `0x01` to register `0xFE` once during
driver initialization with the intent of disabling controller autosleep.

During TartLab's IDE power testing:

- normal touch, launcher selection, and short dim/wake cycles worked;
- after roughly one minute of continuous inactivity, the controller stopped
  reporting touches even though the driver continued polling touch status;
- an isolated 85-second probe reproduced the long-idle failure; and
- reasserting `0xFE = 0x01` every ten seconds kept touch observable, including
  a real IDE wake after more than 65 seconds idle.

This establishes that the periodic write is an effective keepalive on the
tested board/controller. It does not establish why the one-time write becomes
ineffective, whether `0xFE` can be read back reliably, or whether every CST226
variant has the same behavior. Upstream documentation should therefore call it
an empirically verified CST226SE keepalive rather than claiming a universal
controller defect.

## Recommended PR update

Keep PR #575 open and add a follow-up commit instead of replacing or
force-pushing its original commit. Put the keepalive in the CST226 driver's
normal polling path rather than adding an asynchronous task or depending on an
application framework.

The driver can:

1. Define a ten-second keepalive interval.
2. Track the last write with `time.ticks_ms()`.
3. Compare elapsed time with wrap-safe `time.ticks_diff()`.
4. Reassert `0xFE = 0x01` when due at the beginning of `_get_coords()`.
5. Perform the initial write through the same helper after leaving command
   mode.

For example:

```python
_KEEP_AWAKE_INTERVAL_MS = const(10000)


def _refresh_keep_awake(self):
    now = time.ticks_ms()
    if (
        self._last_keep_awake_ms is None
        or time.ticks_diff(now, self._last_keep_awake_ms)
        >= _KEEP_AWAKE_INTERVAL_MS
    ):
        self._write_reg(_DIS_AUTO_SLEEP_REG, 0x01)
        self._last_keep_awake_ms = now
```

Initialize `_last_keep_awake_ms` to `None`, call the helper once during
initialization, and call it before reading the touch report in `_get_coords()`.
This keeps all I2C operations in the existing pointer-polling context and adds
only one two-byte write every ten seconds.

PR #575 already unconditionally attempts to disable autosleep, so periodic
reassertion preserves its existing intended behavior. If maintainers prefer an
explicit low-power policy, the interval could later become an optional
constructor argument; that is not required for the minimal corrective commit.

## Recommended PR evidence

Update the PR description or add a comment containing:

- the tested board and controller: T-Display-S3 Pro / CST226SE / `0x5A`;
- the approximate time to failure with only the initialization write;
- confirmation that continuous status polling alone did not prevent it;
- the successful ten-second reassertion interval;
- the greater-than-65-second real IDE dim/wake result; and
- a note that the result is physical evidence from one fixture, not yet a
  claim covering every CST226 board or firmware revision.

A single polite maintainer ping after pushing the evidence-backed commit is
reasonable. The long-idle finding is materially new information rather than a
status-only bump.

## Changes that do not belong in the CST226 PR

Two other TartLab findings are integration issues, not CST226 driver fixes:

- Pointer coordinates must not be pre-rotated when LVGL will apply the display
  rotation. TartLab corrected how it constructs the driver; the driver's
  `startup_rotation` support does not need a PR change for that finding.
- TartLab's pinned LVGL binding lacks `indev_get_next()`. Falling back to the
  platform's native input object belongs to TartLab's IDE power controller,
  not the CST226 driver.

TartLab's IDE brightness timeout and consumption of the first wake touch are
also application policies and should remain outside the upstream driver.

## TartLab local disposition

TartLab keeps the tested ten-second schedule in the T-Display-S3 Pro
application adapter and IDE power controller. The frozen CST226 firmware driver
and qualified firmware lock remain unchanged. This preserves the qualified
firmware identity while allowing TartLab to proceed independently of PR #575.

The local choice and its physical evidence are recorded in
[PROJECT_NOTES.md](PROJECT_NOTES.md) and the
[modern touchscreen qualification notes](tests/MODERN_TOUCHSCREEN_QUALIFICATION.md).
