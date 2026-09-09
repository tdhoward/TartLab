# Image decoder and driver package physical smoke

On 2026-09-08, the disposable fixture on COM18 was identified through its
protected `/device/board.json` as `elecrow_dle06235b`. Its existing firmware
reported `3.4.0; MicroPython 78ff170de9-dirty on 2026-09-05` and ST77922 touch
firmware 3, geometry 320 x 480, five hardware contact slots. Firmware was not
reflashed or read back for a binary hash comparison.

The current working-tree filesystem was built with:

```text
python makedist.py --output build/device-image-smoke-20260908/dist --skip-web-build --board elecrow_dle06235b
```

The build used Python minification and the existing generated web bundle.
Its 69 files total 489,690 bytes; the build inventory SHA-256 is
`d746db253e63e43966f03d99799bc987313b1f2a53edb4ec6fb5348e0800fb41`.
All 69 device files were verified against their individual SHA-256 hashes.
Obsolete files in the replaced runtime, board, examples, and library trees were
removed. The protected device identity and selector were retained. This was a
serial filesystem installation for testing, not a release promotion or OTA test.

## Results

- The new `tartlabdrivers.display.st77922` adapter was selected successfully.
  Initial reset started the HTTP server and reported `HEALTHY mode=IDE`.
- 101 on-device assertions passed: TS16/QOI binary-alpha equivalence, alpha
  preservation, the alpha-128 cutoff, RGB888 background compositing before
  RGB565 quantization, overlapping one-pass batch extraction, custom decoder
  consumption, scaling, flipping, clipping, malformed QOI tail rejection,
  full-frame seeding, partial transfer completion, and repeated-extraction heap.
- All twelve Warrior frames prepared successfully, retaining 59,552 bytes of
  span data. Thirty-six animated, unaligned partial display updates completed
  in 38,056–47,258 microseconds each, with no pending transfer at completion.
- Twenty repeated QOI extraction batches had 7,407,984 bytes free initially
  and 7,407,680 bytes free finally, including the probe's growing sample list.
  This establishes a bounded smoke result, not a long-duration leak claim.
- The operator confirmed that the first two TS16/QOI rows matched, the
  composited row faded from blue to red, and the Warrior sprites and labeled
  red/green/blue/white/black bars looked correct.
- The second touch capture recorded logical points near all four corners:
  `(28,37)`, `(301,20)`, `(306,459)`, `(305,459)`, and `(36,457)`. The initial
  capture returned no contacts; its timing relative to the operator's taps was
  uncertain. The center was not captured.
- The installed `display_qoi.py`, `display_ts16.py`, and `sprite.py` examples
  completed in 2,636 ms, 1,867 ms, and 5,851 ms respectively. The animation's
  touch-reader method was temporarily bounded in memory to exit after five
  polls; installed source files were not modified.
- Racer loaded ten prepared sprites and thirty glyphs, then rendered 25 frames
  using its actual dirty-region renderer in 991 ms total. The bounded probe
  bypassed the interactive main loop and did not qualify gameplay or pacing.
- Twenty-five UI/direct/UI cycles completed with full-frame reseeding. Each
  final ownership check reported UI ownership and no pending transfer.
- Five same-runtime initialization/teardown cycles completed without errors.
  Post-teardown free heap ranged from 7,463,056 to 7,456,144 bytes; the final
  two samples differed by 64 bytes. These include probe and runtime overhead.
- After cleanup, a final hardware reset reached the HTTP server and
  `HEALTHY mode=IDE update_committed=False` without a traceback. The board was
  left running the IDE. Firmware and protected board selection were unchanged.

## Guided repeat

The operator requested a repeat with clearer visual instructions. All 101
on-device assertions passed again. The operator then explicitly confirmed that
the first two rows matched with an abrupt alpha-128 cutoff, and that the third
row blended from blue through purple to red with the supplied background.

Five yellow touch targets provided live green feedback. All five registered:
top left `(21,5)`, top right `(302,17)`, bottom right `(305,465)`, bottom left
`(20,459)`, and the central target `(169,296)` near its requested `(160,300)`
position. This supersedes the missing central contact in the first capture;
it is a functional target check, not a calibrated touch-accuracy measurement.
Repeat transcripts are `device_smoke.py.txt` and `touch-repeat.txt` in the local
evidence directory.

## Scope and retained evidence

The Elecrow fixture exercises the moved ST77922 adapter, its required full-frame
seed, aligned partial transfers, and the format-independent image/sprite code.
This session does not physically qualify the moved ST7796 adapter on LilyGO,
center-touch accuracy, browser interaction, sustained memory behavior, or
OTA/recovery interruption handling.

Raw serial transcripts, the complete file inventory, installation helper, and
device probes are retained locally under
`hardware_test_artifacts/image-driver-com18/`. Temporary device image fixtures
were removed, leaving only `hello.py` under `/files/user`. Final boot results
are recorded in `final-boot.txt` in that directory.
