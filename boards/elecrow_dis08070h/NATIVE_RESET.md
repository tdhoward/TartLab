# Experimental native reset repair

The first firmware fails friendly-REPL soft reset while reconstructing
`SPI.Bus`. Its Python SD lease cache prevents within-boot finalizer failures,
but cannot repair native pointers retained across interpreter resets.

The experimental recipe selects
[`container_prepare_storage.py`](../../firmware/lvgl-modern/container_prepare_storage.py),
which adds the following changes to the same pinned upstream graph. The
existing qualified build wrapper remains unchanged. Both wrappers and the
frozen helper are explicit hash-bound inputs in this board's lock.

- SPI bus registrations are VM GC roots. Device registration stores the actual
  device pointer; duplicate registration and removal of an absent device leave
  the registry intact. Deinitialization marks resources inactive before a
  later finalizer can run.
- An SD object's embedded SPI device starts at the allocation's GC head, so
  the bus registry retains the whole card allocation. Native release clears
  the slot handle, card flags, and active state; closed cards reject further
  initialization/read operations. The host's transaction slot is the handle
  returned by ESP-IDF, rather than an assumed SPI host number.
- Before the ESP32 interpreter sweeps its heap, it closes native SPI resources
  and stops RGB scanout. RGB cleanup waits for its copy task to exit before
  destroying panel buffers and synchronization objects. Its registry is also
  rooted and its removal loop handles a shrinking list.
- The generated LVGL binding initializes its global state from the current
  VM root table. Custom roots survive `mp_init()`, so reset cleanup explicitly
  clears both LVGL roots and its exported global pointer. The display framework
  calls `is_initialized()` before `init()`; neither copy may retain the old VM.

The existing Python lease cache remains compatible and intentionally reserves
the SD device for a boot's lifetime. The native regression bypasses it to test
the repaired constructor/deinit/finalizer behavior directly.

The September 20 candidate additionally balances the generated LVGL callback
nesting counter using MicroPython NLR unwind callbacks. Normal return and
exception propagation both release the callback scope; interpreter teardown
also clears the counter after native resources stop. Exceptions still propagate.
This does not promise safe continuation of an interrupted LVGL operation in the
same interpreter: the task handler's failure policy and touch transport recovery
remain separate concerns. The isolated callback probe requires a fresh timer to
run after soft reset and never repairs state by writing the counter from Python.

## Verification

[`test_native_storage_patch.py`](../../tests/test_native_storage_patch.py)
compiles the patch's actual registration/release functions with deterministic
native-resource stubs. Run it in the pinned container to include AddressSanitizer
and UndefinedBehaviorSanitizer. A host without a C compiler explicitly skips
that test; a host-only run does not establish native test success.
The callback regression also covers return values, nested exception unwinding,
an exception caught inside an outer callback, and teardown reset. All five tests
passed in the pinned container on September 20 with ASan and UBSan enabled.
The reset-hook test also rejects duplicate application after an interrupted
build. Start native builds from a fresh verified checkout.

On the board, retain the existing rollback image and inspect the new image's
partitions, physical bounds, checksums, and application headroom. The owner
has requested no unnecessary fresh backups of this disposable fixture. Flash the
combined image without erasing the internal filesystem. Retain the original
image and recipe separately for rollback and comparison.

After diagnostic startup, `sd_bringup.py soft-reset --cycles 3` checks that
boot/main each advance once, the selected board and import paths agree,
and reset cause remains a soft reset. It records per-region internal DMA heap
statistics and preserves complete startup logs. Panic output or an unexpected
ROM boot fails the capture even if the diagnostic later returns. A hard reset is recovery,
not a substitute for a passing soft-reset check.

For direct native lifecycle checks, enter raw REPL and send Ctrl-D there; this
resets the interpreter while deliberately skipping `main.py`. Then run:

```powershell
.venv/Scripts/python.exe tools/sd_bringup.py native-lifecycle --port COMx --session hardware_test_artifacts/sd-session --cycles 10
```

The fixture requires internal root with no SD mount. It only reads sector zero,
compares its hash across opens, verifies closed-object guards, and forces GC
after reopening. Return to the diagnostic with a friendly reset and verify the
installed and baseline file hashes. Repeat the bounded SD/RGB/radio soak on
the new image. Physical alignment/flicker/tearing need separate observations.

This is bringup evidence, not qualification of normal TartLab display ownership,
touch, arbitrary media failures, network throughput, or reproducible firmware.
Measured results and the current device state belong in
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).
