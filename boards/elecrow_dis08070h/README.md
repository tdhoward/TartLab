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

On the revised image, ten native close/reopen/GC cycles, three full soft resets,
and eight 1 MiB copy/readback cycles with RGB refresh, AP activity, and Wi-Fi
scans passed. All 98 installed/baseline/new-output hashes matched after reset.
Visual behavior during load remains unobserved. The board is left at
`SD root OK` with UART REPL available; the firmware and tests have finished.

The experimental [firmware lock](../../firmware/lvgl-modern/elecrow_dis08070h.lock.json)
uses the existing pinned modern source graph, 4 MiB flash, octal PSRAM, a
3 MiB app partition, RGBDisplay, GT911, and a UART0 console. The catalog's
firmware and qualification fields deliberately remain null until integration
and reproducibility gates are complete.
