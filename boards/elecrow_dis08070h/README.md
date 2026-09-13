# Elecrow CrowPanel Basic 7-inch

Order SKU **DIS08070H001**; vendor module **DIS08070H**, store SKU
**DIS08070H-1**. This is the 800 x 480 N4R8 Basic board, not CrowPanel Advance.

Lifecycle: **bringup**, not a supported TartLab installation target.

Start with [BRINGUP_PLAN.md](BRINGUP_PLAN.md) and the measured
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md). The declarative
[runtime payload](runtime/elecrow_dis08070h_modern.py) records RGB, touch, and
SPI SD wiring. The shared TartLab factory still needs an RGB transport adapter;
the payload currently serves standalone bench tools only.

The experimental [firmware lock](../../firmware/lvgl-modern/elecrow_dis08070h.lock.json)
uses the existing pinned modern source graph, 4 MiB flash, octal PSRAM, a
3 MiB app partition, RGBDisplay, GT911, and a UART0 console. The catalog's
firmware and qualification fields deliberately remain null until integration
and reproducibility gates are complete.
