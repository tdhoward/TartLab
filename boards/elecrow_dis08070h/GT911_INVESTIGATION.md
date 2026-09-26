# GT911 timeout investigation

Updated September 20, 2026. Status: **cause unknown; no timeout fix established**.
This is the short research/test entry point. Measurements remain in
[BRINGUP_RESULTS.md](BRINGUP_RESULTS.md). Keep this file current after each
experiment: hypothesis, single change, coverage, result, evidence, next decision.

## What we know

- Actual ETIMEDOUT (116) and ENODEV (19) have occurred inside GT911 polling,
  including during normal Wi-Fi startup. The repaired native LVGL nesting leak
  was a consequence of callback exceptions, not the transport cause.
- GPIO19/20 had a separate, measured electrical/ownership problem: SDA was low;
  reseating the P4 ribbon and releasing USB pad ownership restored communication.
  This history warrants checks, but does not establish the current fault.
- The current image disables USB consoles and uses hardware I2C host 0 at
  10 kHz. Normal factory startup does not execute the declared PCA9557 reset.
- The controlled 10/100 kHz x reset/no-reset comparison passed eight 1 MiB
  SD/RGB/Wi-Fi cycles and 9,901 polls without transport exceptions. Two cycles
  per case are screening evidence, not proof of equivalence or a fix.
- Two of 12 post-interrupt startup checks stalled with nesting zero. Eight
  subsequent enhanced checks passed. The captured transcript shows Ctrl-C can
  interrupt `task_handler._task_handler`. These stalls remain separate from
  proven I2C failures; healthy IDE state alone is insufficient.
- Machine-recorded presses do not establish physical finger response or
  exclude phantom touches. No new physical observations were supplied.

Evidence root: `hardware_test_artifacts/crowpanel7-20260920/gt911/`;
accepted comparisons: `active-config/comparison.json`; startup runs:
`baseline-startups/results.json`, `captured-startups/touch-startup.json`.

## Source audit and online leads

1. **Controller command mismatch worth testing.** The built frozen
   `api_drivers/common_api_drivers/indev/gt911.py` defines `_CMD_READ_DATA=1`
   and writes it to `0x8046` and `0x8040` in `hw_reset()`. Goodix's register map
   describes command 0 as coordinate status and 1 as raw/differential data.
   Treat this as a protocol discrepancy, not an established timeout cause;
   our controller has nevertheless returned coordinates. The same guide
   specifies RESET/INT address selection and a 50 ms wait after INT becomes
   floating input before configuration. Our standalone expander sequence waits
   before releasing INT, with no explicit subsequent settling interval.
   Audit these separately. [Goodix programming guide, sections 3.1 and 4](https://www.lcd-module.de/fileadmin/eng/pdf/zubehoer/GT911_Programming_Guide_Rev.10.pdf).

2. **Same-board report.** ESPHome issue 15356 reports persistent I2C timeouts
   on two DIS08070H V3.0 boards using GPIO19/20 after an ESPHome update. Its
   author suspects USB pad ownership/new-driver behavior. It is open and
   supplies no confirmed fix; our intermittent failure uses a different stack.
   [Report, April 1, 2026](https://github.com/esphome/esphome/issues/15356).
   An older MicroPython report also concerns USB ownership of these pins.
   [MicroPython issue 14217](https://github.com/micropython/micropython/issues/14217).

3. **Timeout does not identify its cause.** The pinned MicroPython build uses
   the legacy IDF I2C path (`MICROPY_HW_ESP_NEW_I2C_DRIVER` defaults to 0,
   no override in its compile command; linked legacy symbols were inspected).
   It maps IDF `ESP_FAIL` to ENODEV and `ESP_ERR_TIMEOUT` to ETIMEDOUT.
   IDF 5.5.1 can return timeout for mutex/event waiting, hardware timeout, or
   arbitration-loss handling; it can reset the I2C state machine before
   returning. A Python-level snapshot can therefore already be post-recovery.
   [Pinned-version IDF implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.5.1/components/driver/i2c/i2c.c).

4. **Comparable symptom, not a transferable fix.** An ESP-IDF report describes
   intermittent ESP32-S3 timeout/no-ACK failures and traces where clocking
   stops after an acknowledged address. It uses a different peripheral and
   IDF 5.0.1; it was closed as cannot reproduce. Its useful lesson is to capture
   the failing waveform, not to copy its timeout-register assumptions.
   [Espressif issue 11397](https://github.com/espressif/esp-idf/issues/11397).

5. **Electrical checks remain relevant.** Espressif documents the interaction
   of pull-up resistance, capacitance, and clock rate. Its current API docs
   describe a different driver from ours; use the electrical guidance without
   assuming those API options apply to this firmware.
   [ESP32-S3 I2C documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/i2c.html).
   Espressif's GT911 implementation provides an independent reset/address and
   coordinate-read reference, not an automatic replacement for our driver.
   [GT911 driver source](https://raw.githubusercontent.com/espressif/esp-bsp/master/components/lcd_touch/esp_lcd_touch_gt911/esp_lcd_touch_gt911.c).

## Next experiments, in order

| ID / status | Test | Evidence and decision |
| --- | --- | --- |
| T1 implemented, running | Bounded transaction recording in the actual normal startup path; host listens without Ctrl-C during the observation window. | Active journal: `passive-t1-v2/passive.json` under the evidence root. First-failure snapshots retain address/register/length/errno/timing/poll/phase/heartbeat and read-only GPIO/USB registers; host interruptions have a separate transcript. |
| T2 implemented, not yet run | Compare existing command 1 with coordinate command 0, using the same reset behavior, clock, firmware and workload. | Count failures per startup, transactions and elapsed time. Validate identity/status and coordinate behavior; a no-error idle run alone is insufficient. Preserve actual writes and hashes for both variants. |
| T3 implemented, not yet run | Compare no expander reset with a fully audited RESET/INT sequence, including direction/readback, resulting address and explicit settling. | Separate MCU hard/soft reset from GT911 reset and actual power removal. Do not combine this change with T2. An address change or wrong expander direction narrows the cause. |
| T4 planned if needed | Isolate load: touch alone; add RGB; then Wi-Fi start, scan and AP separately; then SD copy/readback. Include no-touch idle dwell. | Preserve identical initialization and polling. Exercise normal startup transitions, not only the shared-runtime load fixture. Correlation with Wi-Fi could be power, driver scheduling, or flash/NVS activity, not proof of radio interference. |
| T5 conditional | Instrument the exact legacy IDF failure branches if T1 cannot explain a reproduced failure. | Record raw error/interrupt status, arbitration/timeout/ACK classification, controller state and timing before IDF recovery. Rebuild only this diagnostic change against the pinned source graph. |
| T6 physical, last | Capture SCL/SDA and, if accessible, RESET/INT with a logic analyzer; measure touch supply and signal rise times with a scope. | Match captures to failure timestamps. Compare existing power/cable with a known-good supply; cold-cycle and record deliberate taps versus hands-off behavior. Request one bundled operator session after software tests. |

T1 should use a small preallocated RAM history, aggregate counters and sparse
UART output, not per-poll printing or SD writes in the input callback. Preserve
the original exception behavior and mark every transport exception as a failure.
Read GPIO/USB routing state without reinitializing pins. After the first snapshot,
stop further touch polling and collect any additional diagnostics explicitly;
even a scan can change bus state. Read PCA9557 state only if the bus permits it.
Any later retry/recovery experiment needs its own labeled result.

Default screening bound: 20 normal startups per variant, interleaved A/B with
equal hard/soft counts and a fixed 60-second passive window after healthy startup.
Also record failures before that marker. Journal completed runs and source/config
hashes; resume only the same contract. If neither variant reproduces, report
"inconclusive" and change the diagnostic method instead of repeating indefinitely.
Try to capture three independent failures for classification, with a fixed run
cap; preserve the first even if no more occur. The passive recorder and
comparison runner are now implemented in `tools/touch_passive_probe.py` and
`tools/device/touch_flight_recorder.py`. They temporarily instrument the installed
main/IDE sources, verify upload hashes, and restore the original bytes afterward.
GT911 initialization and transport calls still use the frozen driver. The command
comparison changes only its two command-write values; the reset comparison keeps
the original command and audits PCA9557 separately. Existing
`tools/touch_startup_probe.py` remains useful but samples after interruption.

Run from the repository root (use a fresh session for each experiment):

```powershell
python tools/touch_passive_probe.py --port COM20 --config boards/elecrow_dis08070h/gt911_diagnostic.json --session hardware_test_artifacts/gt911-next --experiment command
python tools/touch_passive_probe.py status --session hardware_test_artifacts/gt911-next
```

Experiments are `baseline` (at most 20 startups, stop after three captured
transport failures), `command` and `reset` (20 startups per variant, interleaved
A-hard/B-hard/A-soft/B-soft). Each successful startup gets a full 60-second
passive healthy window; failures before healthy are retained with a 90-second
startup bound. `--resume` requires the same source/config contract, firmware
partition fingerprint, active board configuration and original source hashes.
Counts sampled at sparse heartbeats are lower bounds. Physical results remain
unset; a screen pass is not a causal or touch qualification result.

The first preparation attempt (`passive-t1/`) stopped before device changes
because the installed IDE was minified. Syntax-based phase hooks fixed that
assumption. The active T1 run archives its exact earlier recorder/runner/config;
subsequent tooling enhancements do not change that running experiment.

Reset audit detail: read PCA9557 input/output/polarity/configuration registers,
preserve unrelated bits, confirm driven RESET/INT levels through input readback
(accounting for polarity inversion), and verify each output/direction write.
Release RESET with INT low, retain the board's declared delay, float INT, then
wait another 50 ms. P0 is open-drain, so the output latch alone cannot establish
a high RESET level. See the [TI PCA9557 datasheet](https://www.ti.com/lit/ds/symlink/pca9557.pdf)
and the Goodix guide linked above. Physical waveform timing remains unverified.

## Interpreting the first failure

| Observation | Lead it supports; follow-up |
| --- | --- |
| Both GT911 and expander unreachable, SDA or SCL low | Shared electrical/ownership or controller-state issue; inspect pad routing and waveform before reinitializing anything. |
| Expander reachable, GT911 missing or changes address | GT911 reset/power/address selection; capture RESET/INT and supply. |
| Clock/address ACK succeeds, then transfer stops | Clock stretching, master state/interrupt handling or electrical disturbance; distinguish with native status and waveform. |
| Clean bus transaction but software reports timeout | Driver/event/interrupt path deserves priority; capture its exact return branch. |
| I2C keeps working but LVGL heartbeat stops | Scheduler/callback problem; do not count it as a transport timeout. |

These are discriminators, not proofs. A cause is established by a repeatable
failure signature plus a targeted change that removes it under the same trigger,
preferably with an A/B/A reversal. Then repeat normal startup, SD/RGB/radio load,
soft-reset recovery and physical touch checks. Retries or a larger timeout may
be useful recovery policy later, but cannot alone establish the cause.

Research-only update on September 20: no device changes or new hardware tests.
Keep firmware/pin/geometry choices in BOARD_CONFIG; any eventual reusable
transport or reset behavior belongs in a shared driver/adapter.
