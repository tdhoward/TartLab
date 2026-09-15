# Elecrow CrowPanel Basic 7-inch

Order SKU **DIS08070H001**; vendor module **DIS08070H**, store SKU
**DIS08070H-1**. This is the 800 x 480 N4R8 Basic board, not CrowPanel Advance.

Lifecycle: **bringup**, not a supported TartLab installation target.

Start with [BRINGUP_PLAN.md](BRINGUP_PLAN.md) and the measured
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md). The declarative
[runtime payload](runtime/elecrow_dis08070h_modern.py) records RGB, touch, and
SPI SD wiring. The shared TartLab factory still needs an RGB transport adapter;
the payload currently serves standalone bench tools only.

The 32 GB FAT32 card now passes verified file writes, hard-reset persistence,
and SD-as-root/internal-at-`/flash` checks at 1 MHz. The revised firmware also
passes native SD lifecycle and full diagnostic soft-reset checks; see
[NATIVE_RESET.md](NATIVE_RESET.md) for the repair.
The packaged TartLab payload can be staged with
[`stage_sd_bench.py`](../../tools/stage_sd_bench.py); its explicit diagnostic
entry points do not enable the unfinished TartLab RGB platform.

On the September 13 native-reset image, ten native close/reopen/GC cycles,
three full soft resets, and eight 1 MiB copy/readback cycles with RGB refresh,
AP activity, and Wi-Fi
scans passed. All 98 installed/baseline/new-output hashes matched after reset.
Visual behavior during load remains unobserved. The board is left at
`SD root OK` with UART REPL available; the firmware and tests have finished.

September 14 continuation reverified all 98 hashes and diagnostic startup.
After the requested power cycle, the owner confirmed an aligned, stable screen;
the device reported power-on reset and boot/main counters both 26.
Touch SDA remains low with the line released;
explicit pin initialization and nine bus-clear clocks did not recover it.
The new `sd_bringup.py touch` action records line levels and validates controller
identity without writing controller registers. Touch bus isolation is next;
see the continuation in
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).

The subsequent UART-only comparison image explicitly disables ESP-IDF's
secondary USB console. It passes generated-console and image inspection,
captured diagnostic startup, three soft resets, and all 98 file hashes. The
owner observed no display problems, but touch remains unresponsive and SDA
still reads low.
After a full power cycle, all 98 hashes passed again. The owner's meter reads
SCL 3.2 V and SDA 0.6 V, confirming a physically low data line. Those voltages
persisted with MCU outputs disabled and no external I2C device connected.
With the P4 touch ribbon disconnected and power restored, both lines read high.
After the owner reseated the ribbon and closed its latch, both lines stayed high.
Releasing USB pad ownership then revealed the GT911 at `0x14` (800 x 480) and
the reset expander address `0x18`. The board configuration now selects hardware
I2C host 0 at 10 kHz, whose initialization releases USB ownership automatically.
After reset, a two-minute visual test captured 19 presses across the panel,
all within 800 x 480; the owner confirmed touch works. All 98 SD hashes passed
against the updated inventory. A subsequent full power cycle initialized touch
automatically and captured seven more presses; SD root and the saved payload
were verified, with boot/main counters both 42. No failed component has been
identified. Shared TartLab RGB integration and remaining qualification gates
are still open.
Its exact build and current comparison results are recorded in the results
document; the SD payload and internal rescue files were preserved.

The experimental [firmware lock](../../firmware/lvgl-modern/elecrow_dis08070h.lock.json)
uses the existing pinned modern source graph, 4 MiB flash, octal PSRAM, a
3 MiB app partition, RGBDisplay, GT911, and a UART0 console. The catalog's
firmware and qualification fields deliberately remain null until integration
and reproducibility gates are complete.
