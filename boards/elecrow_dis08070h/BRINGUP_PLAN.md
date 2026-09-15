# CrowPanel 7-inch MicroPython + LVGL + SD TartLab bring-up

Started 2026-09-12. Status: **experimental bring-up**, not release qualification.
Measured results and current device state: [BRINGUP_RESULTS.md](BRINGUP_RESULTS.md).
This plan supersedes the 7-inch sequencing and storage investigation in the
[earlier Elecrow research](../elecrow/ESP32_S3_BRINGUP_PLAN.md).

## Decision and scope

Pursue a dedicated **4 MiB firmware plus SD-root installation**. SD provides
filesystem capacity; native MicroPython, LVGL, and ESP-IDF code still execute
from the flash application partition. PSRAM provides working memory, not
persistent storage. An RGB565 frame is 768,000 bytes; two are 1,536,000 bytes,
before LVGL drawing buffers, Python heap, DMA bounce buffers, and networking.

Keep the existing MicroPython 1.27.0 / LVGL 9.4.0 / ESP-IDF 5.5.1 source graph.
Do not combine bring-up with a runtime upgrade or flash a 16 MiB image here.
The vendor's example uses LVGL 8 APIs and is wiring/reference material, not
the TartLab application ABI.

The owner authorized experiments and erasure and reported no valuable device
content. A private full-flash backup was nevertheless obtained. No SD card was
present at the start. Unique identifiers, COM assignments, dumps, and full logs
stay in ignored `hardware_test_artifacts/` and `build/` directories.

## Hardware facts and unknowns

- Order SKU DIS08070H001 corresponds to vendor DIS08070H / DIS08070H-1,
  CrowPanel **Basic**, 800 x 480, ESP32-S3 N4R8.
- ROM probe confirms 4 MiB quad flash and an ESP32-S3 with 8 MiB embedded
  PSRAM. Runtime heap evidence is a separate gate.
- USB connects through UART0. Enable UART REPL and disable CDC and USB
  Serial/JTAG REPL. GPIO19/20 serve touch I2C.
- RGB bus, active-high backlight, GT911 I2C, and SPI SD pins are exclusively
  in the declarative [BOARD_CONFIG](runtime/elecrow_dis08070h_modern.py).
- Reproduce the pinned factory timing first: 15 MHz pixel clock and its
  porch/pulse/polarity values. Do not substitute a similarly named CYD config.
  That baseline rendered correct colors but horizontally wrapped on the tested
  unit. The current bring-up payload requests 10 MHz with the same porches;
  the owner confirmed correct edges and labels. Sustained-load stability is
  still pending. See the measured results for the comparison.
- The owner physically confirmed **V3.0** on 2026-09-12. V3 adds PCA9557 at I2C 0x18;
  its bit 0 resets touch and bit 1 controls the GT911 interrupt/address phase.
  The probe preserves unrelated expander outputs and runs the sequence only
  if that address responds. An I2C address alone is not a PCB revision proof.
- GPIO0 is LCD PCLK after boot. Do not treat BOOT as a normal runtime button
  or use it as a recovery gesture while scanout is active. ROM BOOT+RESET
  recovery remains available with panel driving stopped.

## Flash budget

The explicit single-application recipe requests:

| Region | Start | Size |
| --- | --- | --- |
| Bootloader / partition-table area | 0x000000 | 0x009000 |
| NVS | 0x009000 | 0x006000 |
| PHY init | 0x00f000 | 0x001000 |
| Factory application | 0x010000 | 0x300000 (3 MiB) |
| Internal filesystem | 0x310000 | 0x0f0000 (960 KiB) |
| Physical end | 0x400000 | — |

Parse the generated partition table and application header before flashing.
Record actual image size, app headroom, flash header, hashes, and runtime
filesystem capacity. A source lock is not evidence of reproducible output;
two independent clean matching builds remain a promotion gate.

This layout has no second native firmware OTA slot. TartLab filesystem updates
on SD and native firmware updates are different operations. Initially native
firmware is serviced over USB/UART. Do not advertise production OTA or rollback
until SD interruption and recovery semantics have been separately qualified.

## Storage and startup design

Proposed FAT card layout is the normal TartLab distribution **at the card
root**, including `/boot.py`, `/main.py`, `/lib`, `/ide`, `/files`, `/defaults`,
`/recovery`, `/board`, `/device`, and `/state`. A directory `/sd/TartLab` plus
`chdir()` does not redirect TartLab's absolute paths.

Internal flash contains the declarative selector as `/hdwconfig.py` and the
small [experimental launcher](../../tools/device/sd_root_main.py) as `/main.py`.
The reusable [external_root helper](../../firmware/lvgl-modern/drivers/external_root.py)
is frozen into the revised experimental firmware. The first image needed an
internal `/external_root.py` override; that file is now retained as
`/flash/external_root.previous.py` so startup uses the corrected frozen module.
The helper:

1. Opens native SPI `machine.SDCard` using the payload's pins and a conservative
   clock. The pinned LVGL fork replaces stock MicroPython's constructor:
   create `machine.SPI.Bus(host=..., sck=..., mosi=..., miso=...)`, then
   `machine.SDCard(spi_bus=bus, cs=..., freq=...)`. Retain the bus for the card's
   lifetime and check `ioctl(1, 0)` before mounting. Stock `slot/sck/mosi/miso`
   arguments are incompatible with this fork. Mounts the existing FAT volume
   temporarily at `/sd`; never formats it.
2. Checks required boot and identity files before changing the root mount.
3. Unmounts the temporary SD mount and internal root, remounts internal storage
   at `/flash`, mounts SD at `/`, and changes the working directory to `/`.
4. Restores internal `/` if switching fails. Missing/unreadable cards leave an
   error and a serial REPL, with no automatic reboot or formatting loop.
5. Clears the cached bootstrap selector, then runs the SD boot gate and main.

The prototype leaves application state on SD and preserves internal rescue
files at `/flash`. Promotion must decide which device identity, boot-health,
and rescue state belongs on internal flash, and protect the bootstrap from
filesystem update packages. A removable card is trusted executable content.
Existing provisioning assumes internal-root storage and must not be used for
this board unchanged.

## Ordered execution and exit gates

### 1. Inventory and reversible firmware experiment

- [x] ROM flash/chip/security probe; secure boot and flash encryption disabled.
- [x] Read full original flash and record SHA-256 privately.
- [x] Owner confirmed PCB V3.0; module topology also agrees with the ROM probe.
- [x] Build and inspect the dedicated combined image and partitions.
- [x] Flash the new image; verify UART REPL, LVGL/driver imports, large heap,
  persistent file writes, and repeated soft/hard reset recovery.
- [x] Exercise Wi-Fi scan without recording credentials (14 networks detected).
- [ ] Exercise AP start/stop and simultaneous display/network load.

### 2. Standalone RGB, touch, and no-card behavior

- [ ] Read GT911 product/geometry after the revision-appropriate reset.
- [ ] Render colors, all corner labels, and touch feedback in native landscape.
- [ ] Human observations: correct RGB order, orientation, edges, text, brightness,
  press/release behavior, flicker/tearing, and cold-boot stability.
- [ ] Measure heap and display buffer allocation; preserve DMA/internal-memory
  headroom while Wi-Fi is active.
- [ ] Audit ESP-IDF's secondary USB console independently of the MicroPython
  REPL flags. The first generated sdkconfig retains secondary USB logging even
  though the MicroPython USB REPL is off; verify touch and cold-start behavior.
- [x] Root switching with a RAM FAT volume: external `/` read, internal `/flash`
  access, and restoration of the original internal `/` all passed. Actual SD
  I/O subsequently passed with the physical card on September 13.
- [x] Installed missing-card launcher returns to usable REPL after hard reset;
  three missing-card retries with garbage collection also pass.

### 3. Card insertion and SD-root proof

**Active since 2026-09-13:** the owner inserted a 32 GB microSD card. Read-only
inspection found an existing FAT32 partition; no formatting was needed.

- [x] Record card capacity and existing format without formatting. Power state
  during insertion was not observed; do not infer that it was powered off.
- [x] Mount/read/write/hash files; sync, hard reset, and verify persistence at
  1 MHz. Sizes 0, 511, 513, 8,193, and 1,048,576 bytes passed host-derived hashes.
- [x] Prove physical SD at `/`, internal storage at `/flash`, and root restoration.
- [x] Physical cold boot and persistence verification. Keep SPI at 1 MHz until
  combined display/storage/network and repeatability checks pass.
- [ ] Test absent, unformatted, incomplete, and unreadable card startup paths.
- [ ] Install a built, board-selected distribution at card root. Verify imports,
  asset/help access, `/state` writes, `/files/user` saves, and internal rescue
  access. Copying `src/` alone is not a complete packaged installation.
- [x] Prove diagnostic boot/main run once and selector precedence holds across
  soft reset. The revised native firmware passed three cycles, with counters
  19 -> 20 -> 21 -> 22 and soft-reset cause each time. The initial firmware
  failed SPI reconstruction; the repair also resets RGB and LVGL resources.

The diagnostic installation now contains a hash-verified packaged payload with
separate bench entry points. Its first hard-reset startup ran boot/main once,
selected `/device/hdwconfig.py`, imported TartLab from `/lib`, accessed assets
and help, and wrote state/user files while preserving `/flash`. A 1 MiB SD
copy/readback with RGB refresh and repeated GC also passed. Normal TartLab
entry points and full application behavior remain unchecked above. Diagnostic
soft reset now passes on the revised image; normal TartLab ownership and reset
behavior still require phase 4.
The owner subsequently confirmed a full power cycle and the correctly aligned
diagnostic's return. All 91 installed/test/output files reverified afterward;
boot/main counters each increased exactly once, from 1 to 2.

Use `tools/sd_bringup.py` for the baseline. The first write attempt exposed a
pinned native SD finalizer bug: closing one card object, opening another, and
collecting the first makes the second stop reading. The corrected helper keeps
one native card and bus per host until reset, releases initialization via
`ioctl(2, 0)`, and rejects concurrent leases or changed wiring/clock settings.
The revised firmware freezes this helper and also repairs the native lifetime
and reset behavior; see [NATIVE_RESET.md](NATIVE_RESET.md).

`tools/stage_sd_bench.py` stages a built board-selected payload with resumable
hash verification and preserves unrelated card files. Bench `/boot.py` and
`/main.py` exercise startup and standalone RGB; original packaged entry points
are retained at `/.tartlab-bench/packaged-boot.py` and `packaged-main.py`.
This is a diagnostic installation. Normal TartLab startup awaits phase 4.

### 4. TartLab runtime integration

- [ ] Add reusable RGB transport/ownership support selected by BOARD_CONFIG.
  Keep board values out of the shared factory and app modules.
- [ ] Establish completion semantics for RGB scanout versus SPI/I8080 transfers;
  qualify UI/direct-surface handover, dirty rectangles, color byte order,
  display teardown, and repeated soft/hard resets.
- [ ] Measure launcher, IDE, representative games, network traffic, and SD I/O
  together at 800 x 480. Record frame time and free internal/PSRAM memory.
- [ ] Validate touch coordinate transforms against labeled corner targets.

### 5. Provisioning, recovery, and promotion

- [ ] Build resumable SD installation tooling with file hashes and a protected
  internal bootstrap; budget space for update staging and rollback on the card.
- [ ] Audit filesystem update assumptions and FAT rename/power-loss behavior.
- [ ] Recover from interrupted writes, failed app/import, full/removed card,
  bad identity, and three failed startup attempts without destroying user files.
- [ ] Freeze rescue path and update contracts; independently reproduce firmware.
- [ ] Follow [RELEASE_QUALIFICATION.md](../../RELEASE_QUALIFICATION.md) and
  `tools/qualification_session.py`; promote lifecycle only with complete evidence.

## Short bench entry points

Commands below use `COMx` as an explicit operator-supplied port; no default
fixture is stored in the catalog. Python, esptool 5.x, and mpremote are already
available in the repository venv.

For SD checks, use one session name for write, reset, verify, and root. Inspect
first; write refuses an existing test directory. A failed partial test is
preserved and a fresh session name starts another attempt. Baseline actions
expect the internal root and no other mounts. After diagnostic startup has
made SD the root, use `status` instead of reopening the active card.

```powershell
.venv/Scripts/python.exe tools/sd_bringup.py inspect --port COMx --session hardware_test_artifacts/sd-session
.venv/Scripts/python.exe tools/sd_bringup.py write --port COMx --session hardware_test_artifacts/sd-session
.venv/Scripts/python.exe tools/sd_bringup.py reset --port COMx --session hardware_test_artifacts/sd-session
.venv/Scripts/python.exe tools/sd_bringup.py verify --port COMx --session hardware_test_artifacts/sd-session
.venv/Scripts/python.exe tools/sd_bringup.py root --port COMx --session hardware_test_artifacts/sd-session
.venv/Scripts/python.exe makedist.py --output build/sd-dist --skip-web-build --board elecrow_dis08070h
.venv/Scripts/python.exe tools/stage_sd_bench.py --port COMx --board elecrow_dis08070h --distribution build/sd-dist --session hardware_test_artifacts/sd-session
```

The staging tool verifies the board, checks all collisions before writing,
and installs the selector last. Rerun the same command to resume the same
payload. Local journals, serial logs, and operator observation forms stay in
the session directory. Existing complete or partial files outside the journal
are never overwritten merely to make an installation proceed.
New sessions also place an installation marker on the card; resumption can
replace only an unfinished file owned by the matching session, never a file
changed after a verified transfer.

After the card's diagnostic has booted and displayed `SD root OK`, run
`tools/sd_bringup.py load --port COMx --session hardware_test_artifacts/sd-session`
using the same session name as the baseline write. This copies and verifies
its 1 MiB pattern while RGB refreshes, then displays `SD load PASS` after sync.
Only then request physical power removal/reconnection and record the operator's
observations; serial completion alone does not certify alignment or flicker.

For an installed diagnostic, use the successful baseline write's session name
and the staging journal (which may live in its parent directory):

```powershell
.venv/Scripts/python.exe tools/sd_bringup.py status --port COMx --session hardware_test_artifacts/sd-session --inventory hardware_test_artifacts/sd-session/sd-stage.json
.venv/Scripts/python.exe tools/sd_bringup.py soak --port COMx --session hardware_test_artifacts/sd-session --cycles 8 --wifi
.venv/Scripts/python.exe tools/sd_bringup.py status --port COMx --session hardware_test_artifacts/sd-session --inventory hardware_test_artifacts/sd-session/sd-stage.json --load-evidence PATH-TO-SOAK.json
```

For touch fault isolation while SD remains mounted, use:

```powershell
.venv/Scripts/python.exe tools/sd_bringup.py touch --port COMx --session hardware_test_artifacts/touch-session
```

This bounded software-I2C inspection records released SDA/SCL levels and
validates GT911 identity/geometry without controller register writes. Low
lines and all-address acknowledgements fail before controller reads. A pass
only establishes readable identity/geometry; physical input and coordinate
checks remain separate. The older `board_probe.py` also rejects invalid buses
before its reset-expander transactions. September 14 found SDA still low after
nine recovery clocks and again after the owner's requested power cycle. The
screen remained aligned/stable. On September 15, reseating P4 removed the
released-line fault; releasing USB pad ownership restored controller identity
reads. The board payload now uses hardware I2C host 0, which claims those pads
during initialization. Visual captures then recorded 19 presses after reset
and seven after a full power cycle. Touch communication and finger response
now pass; integration and remaining qualification gates stay open. The `touch`
action deliberately uses software I2C for its line-isolation check; reset the
board before resuming a hardware-I2C visual fixture after this action.

`soak` keeps a separate 1 MiB output for every cycle, refuses collisions, and
saves verified progress after each cycle. `--wifi` exercises AP start/stop and
station scans, with RGB and AP active during copy/readback; it does not measure
network throughput. Both interfaces must initially be inactive. Generated AP
credentials stay in RAM; logs contain only network counts. An interrupted run
can continue with `soak --resume PATH-TO-SOAK.json` plus the same port/session.
It checks earlier outputs, retains partial files, and writes a new continuation
journal; completed cycles are not rewritten. Physical observations remain in
the operator form and never follow automatically from a hash pass.

`soft-reset --cycles 3` captures startup and checks that boot/main each advance
exactly once with the protected selector. The revised binary passes this check.
After a failure, use `reset` to recover, then `status` to verify SD persistence.
`reset` captures startup but does not itself certify file integrity. Use explicit
reset capture for evidence and `mpremote resume` for commands within a boot.

```powershell
.venv/Scripts/python.exe tools/check_board_catalog.py
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json check
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json checkout --source build/crowpanel-source
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json build --source build/crowpanel-source --copy-to build/crowpanel-firmware.bin
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json inspect-console --sdkconfig build/crowpanel-source/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/sdkconfig
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json inspect --image build/crowpanel-firmware.bin
```

The UART-only recipe explicitly selects `CONFIG_ESP_CONSOLE_SECONDARY_NONE=y`
and disables the secondary USB Serial/JTAG console. MicroPython's REPL flags
alone did not disable ESP-IDF's secondary console in the previous image.
`inspect-console` checks the final generated sdkconfig, including the primary
UART and disabled USB consoles; the intermediate `submodules/sdkconfig` is
generated before the board overrides and is not the final build configuration.

After inspecting the image and entering ROM bootloader:

```powershell
.venv/Scripts/python.exe -m esptool --chip esp32s3 --port COMx flash-id
.venv/Scripts/python.exe -m esptool --chip esp32s3 --port COMx --baud 115200 write-flash 0x0 build/crowpanel-firmware.bin
.venv/Scripts/mpremote.exe connect COMx fs cp boards/elecrow_dis08070h/runtime/elecrow_dis08070h_modern.py :hdwconfig.py
.venv/Scripts/mpremote.exe connect COMx run tools/device/board_probe.py
.venv/Scripts/mpremote.exe connect COMx resume run tools/device/rgb_smoke.py
```

For firmware replacement, preserve the existing internal filesystem and rescue
launcher; do not erase the whole flash. The measured replacement write verified
at 115200 baud. Retain a current full-flash backup before a new experiment.

Use a hard reset before repeating the display fixture. Run the probe before
the fixture on the same boot to perform touch reset. Save stdout to an ignored
session directory. `visual_pass: null` is intentional until an operator records
observations; a successful serial command cannot certify the screen.

## Sources

- [Elecrow product specifications](https://www.elecrow.com/esp32-display-7-inch-hmi-display-rgb-tft-lcd-touch-screen-support-lvgl.html)
- [Elecrow wiki and revision notes](https://www.elecrow.com/wiki/esp32-display-702727-intelligent-touch-screen-wi-fi26ble-800480-hmi-display.html)
- [Pinned vendor factory source](https://github.com/Elecrow-RD/CrowPanel-7.0-HMI-ESP32-Display-800x480/blob/f7fba3ab566f67123200c1a20a12cc0312ae7814/factory_sourecode/LvglWidgets-LVGL-7.0-3.0/LvglWidgets-LVGL-7.0-3.0.ino)
- [Pinned vendor SD example](https://github.com/Elecrow-RD/CrowPanel-7.0-HMI-ESP32-Display-800x480/blob/f7fba3ab566f67123200c1a20a12cc0312ae7814/example/V3.0/Micropython/Example4_SD/Example4_SD.py)
- [MicroPython 1.27 SDCard](https://docs.micropython.org/en/v1.27.0/library/machine.SDCard.html)
- [MicroPython 1.27 VFS](https://docs.micropython.org/en/v1.27.0/library/vfs.html)
- [Pinned LVGL MicroPython source](https://github.com/lvgl-micropython/lvgl_micropython/tree/d2d26467fa4cb9e99e569d899709043d086f7a6f)
