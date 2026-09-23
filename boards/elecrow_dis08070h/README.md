# Elecrow CrowPanel Basic 7-inch

Order SKU **DIS08070H001**; vendor module **DIS08070H**, store SKU
**DIS08070H-1**. This is the 800 x 480 N4R8 Basic board, not CrowPanel Advance.

Lifecycle: **bringup**, not a supported TartLab installation target.

**Latest, September 20:** the native callback cleanup repair is built and flashed.
Its deliberate exception/soft-reset regression passes, as do ten native SD
lifecycle cycles, eight combined SD/RGB/Wi-Fi cycles, five normal soft resets,
and all 95 checked persistence hashes. Intermittent GT911 I2C timeouts remain
unresolved; physical cold-boot confirmation for this image remains pending.
See the latest section of [BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).
The owner subsequently confirmed stable display, responsive touch and Settings
navigation. Brightness exposed a missing PWM declaration; the board payload now
enables PWM dimming. The owner confirmed that brightness adjustment now works.
The subsequent GT911 investigation compared 10/100 kHz with and without the
expander reset: eight SD/RGB/radio cycles and 9,901 touch polls had no transport
errors. This does not establish a timeout fix. Repeated startup exposed
post-interrupt scheduler stalls despite healthy IDE state and zero nesting.
See the latest investigation in [BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).
The [GT911 investigation notes](GT911_INVESTIGATION.md) track online sources,
known facts, hypotheses and the ordered test plan.

Start with [BRINGUP_PLAN.md](BRINGUP_PLAN.md) and the measured
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md). The declarative
[runtime payload](runtime/elecrow_dis08070h_modern.py) records RGB, touch, and
SPI SD wiring. The shared factory now creates the RGB platform through a
reusable [scanout adapter](../../src/lib/tartlabdrivers/display/rgb.py).
Normal TartLab boot/main are installed on SD: the launcher reaches the IDE,
and the display initially looked normal. Horizontal shifting/wrapping later
appeared at 10 MHz. The board now requests **8 MHz**: all 99 file hashes passed
under that comparison, and the owner reported that the display worked normally.
Normal startup also passes a soft reset and a full power cycle; the owner
confirmed the launcher IDE tap and stable alignment after that cold boot.
The shared runtime also passes eight 1 MiB SD copy/readback cycles with Wi-Fi
radio activity and 72 touch presses; the owner confirmed normal display behavior.
All 107 checked file hashes matched after restart; normal IDE startup was restored.
This bounded test required a hard restart to recover stalled LVGL input state.
The unattended continuation passed 16 additional SD/radio cycles across a
12-cycle run and four resumed cycles, with progressing LVGL callbacks and
5.92 MB minimum sampled free Python heap. This run has no physical touch or
visual observations. The reusable [runtime bench](../../tools/sd_runtime_bench.py)
journals load, reset and integrity evidence and provides a separate operator
form. The third normal soft-reset check failed with LVGL nesting stuck at 1.
An isolated probe reproduces native callback-exception leakage across soft
reset; a recovery boot also captured a GT911 I2C timeout inside an LVGL callback.
That result identified native callback/reset recovery as a blocker. Healthy IDE boot state
alone does not establish a working input scheduler. See the results for the
failed checks and retained evidence; recovery qualification remains open.
All 103 checked files survived that continuation. The repair prepared at the
September 19 stopping point has since passed the September 20 checks above;
the earlier failed checks remain recorded.
This does not promote the board to a supported target.

The 32 GB FAT32 card now passes verified file writes, hard-reset persistence,
and SD-as-root/internal-at-`/flash` checks at 1 MHz. The revised firmware also
passes native SD lifecycle and full diagnostic soft-reset checks; see
[NATIVE_RESET.md](NATIVE_RESET.md) for the repair.
The packaged TartLab payload can be staged with
[`stage_sd_bench.py`](../../tools/stage_sd_bench.py); its explicit diagnostic
entry points exercise standalone hardware. The current unit has subsequently
switched to normal packaged entry points, with diagnostic backups retained.

On the September 13 native-reset image, ten native close/reopen/GC cycles,
three full soft resets, and eight 1 MiB copy/readback cycles with RGB refresh,
AP activity, and Wi-Fi
scans passed. All 98 installed/baseline/new-output hashes matched after reset.
Visual behavior during that load remained unobserved. At that milestone the
board was left at `SD root OK`; normal startup has subsequently replaced it.

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
identified. The subsequent shared RGB integration now starts the launcher and
IDE; remaining integration and qualification gates are recorded in the plan.
Its exact build and current comparison results are recorded in the results
document; the SD payload and internal rescue files were preserved.

The experimental [firmware lock](../../firmware/lvgl-modern/elecrow_dis08070h.lock.json)
uses the existing pinned modern source graph, 4 MiB flash, octal PSRAM, a
3 MiB app partition, RGBDisplay, GT911, and a UART0 console. The catalog's
firmware and qualification fields deliberately remain null until integration
and reproducibility gates are complete.
