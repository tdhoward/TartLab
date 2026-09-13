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
is selected for freezing into the experimental firmware. The first built image
has an earlier helper; the corrected source is currently installed as an
internal `/external_root.py` override and still needs a rebuild. It:

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
- [ ] Flash the new image; verify UART REPL, LVGL/driver imports, large heap,
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
  I/O remains untested.
- [x] Installed missing-card launcher returns to usable REPL after hard reset;
  three missing-card retries with garbage collection also pass.

### 3. Card insertion and SD-root proof

**Deferred by the owner: no microSD card available.** Resume this phase when
the owner supplies a card; continue independent display/touch work meanwhile.

- [ ] Insert a known FAT32 card while powered off. Do not silently format an
  unknown card; record capacity and current format first.
- [ ] Mount/read/write/hash a test file; sync, hard reset, cold boot, and verify
  persistence. Raise SPI clock only after reliable 1 MHz baseline results.
- [ ] Test absent, unformatted, incomplete, and unreadable card startup paths.
- [ ] Install a built, board-selected distribution at card root. Verify imports,
  asset/help access, `/state` writes, `/files/user` saves, and internal rescue
  access. Copying `src/` alone is not a complete packaged installation.
- [ ] Prove boot/main run once and selector precedence holds across soft reset.

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

```powershell
.venv/Scripts/python.exe tools/check_board_catalog.py
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json check
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json checkout --source build/crowpanel-source
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json build --source build/crowpanel-source --copy-to build/crowpanel-firmware.bin
.venv/Scripts/python.exe tools/modern_board_firmware.py --lock firmware/lvgl-modern/elecrow_dis08070h.lock.json inspect --image build/crowpanel-firmware.bin
```

After inspecting the image and entering ROM bootloader:

```powershell
.venv/Scripts/python.exe -m esptool --chip esp32s3 --port COMx flash-id
.venv/Scripts/python.exe -m esptool --chip esp32s3 --port COMx erase-flash
.venv/Scripts/python.exe -m esptool --chip esp32s3 --port COMx --baud 460800 write-flash 0x0 build/crowpanel-firmware.bin
.venv/Scripts/mpremote.exe connect COMx fs cp boards/elecrow_dis08070h/runtime/elecrow_dis08070h_modern.py :hdwconfig.py
.venv/Scripts/mpremote.exe connect COMx run tools/device/board_probe.py
.venv/Scripts/mpremote.exe connect COMx resume run tools/device/rgb_smoke.py
```

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
