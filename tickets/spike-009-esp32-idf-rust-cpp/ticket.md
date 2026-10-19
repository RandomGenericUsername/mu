---
id: spike-009
title: "ESP32-CAM ESP-IDF Rust + C++ toolchain feasibility"
kind: spike
status: reported
lane: bmad-advisory
timebox: "3h"
questions:
  - "Does espressif/idf-rust:esp32_1.95.0.0 build a minimal esp-idf-hal app for ESP32?"
  - "Which ESP-IDF version does esp-idf-sys use, and does it match the espressif/idf:v6.1 C/C++ image?"
  - "Does espflash flash the ESP32-CAM over the PL2303 and run it?"
  - "Does espressif/idf:v6.1 build a C++ main.cpp app with the same blink/print?"
  - "What stack/flash-backend model does mu need for espflash (ELF) vs esptool (triplet)?"
answered:
  - "YES: espressif/idf-rust:esp32_1.95.0.0 builds a minimal esp-idf-hal app; esp-idf-sys downloads IDF v6.1 + tools; debug build 3m19s, ELF 13.7 MB."
  - "IDF v6.1 for both: espressif/idf:v6.1 (C++) and esp-idf-sys (Rust)."
  - "espressif/idf:v6.1 builds a C++ main.cpp app; idf.py flash verifies bootloader+partition+app."
  - "espflash exists; live flash is blocked only by the board not being in download mode (no auto-reset on the CAM)."
  - "Model: per-stack flash_backend (esptool for C/C++, espflash for Rust) + a shared lang-idf image."
open:
  - "Live Rust flash/run: put the ESP32-CAM in download mode (GPIO0→GND, reset), flash with espflash, release GPIO0 and reset."
  - "Live C++ run proof (GPIO33 LED / serial boot log) pending the same manual boot-mode check."
links:
  openspec: none
  bmad: none
worktree: .worktrees/spike-009/
branch: ticket/spike-009-esp32-idf-rust-cpp
---

# ESP32-CAM ESP-IDF Rust + C++ toolchain feasibility

## Questions

- Does `espressif/idf-rust:esp32_1.95.0.0` build a minimal `esp-idf-hal` app for ESP32?
- Which ESP-IDF version does `esp-idf-sys` use, and does it match the
  `espressif/idf:v6.1` C/C++ image?
- Does `espflash` flash the ESP32-CAM over the PL2303 and run it?
- Does `espressif/idf:v6.1` build a C++ `main.cpp` app with the same blink/print?
- What stack/flash-backend model does mu need for `espflash` (ELF) vs `esptool`
  (bootloader + partition-table + app)?

## Findings

### Answered

- **Rust build: PASS.** `cargo build` in `espressif/idf-rust:esp32_1.95.0.0`
  compiled `esp-idf-sys 0.38.1` / `esp-idf-hal 0.47.0` / `esp-idf-svc 0.53.0`
  against IDF v6.1; `target/xtensa-esp32-espidf/debug/esp32rust` = 13,728,768 B
  (debug). The first failure was a truncated toolchain from the disk-full run;
  a clean `.embuild` fixed it.
- **espflash live flash blocked by board boot mode.** `espflash flash --port
  /dev/ttyUSB0 --chip esp32 <ELF>` → `Error while connecting to device`; the
  CAM has no auto-reset, so GPIO0 must be grounded + RESET for download mode.
- **idf-rust image exists and is usable as the Rust toolchain base.**
  `docker pull espressif/idf-rust:esp32_1.95.0.0` → Rust 1.95 nightly (`esp`
  toolchain), `espflash 4.4.0`, Xtensa GCC via espup
  (`xtensa-esp-elf/esp-15.2.0_20250920`). It has **no `idf.py`, `IDF_PATH`,
  `cmake`**; `esp-idf-sys` is expected to download/configure ESP-IDF + tools.
  Must `source /home/esp/export-esp.sh` in login shells.
- **C++ IDF builds.** In `espressif/idf:v6.1`, a minimal `main/main.cpp`
  (GPIO33 blink + `printf`, `extern "C" app_main`) builds: `esp32cpp.bin`
  143,984 B, 86% of the 1 MiB app partition free.
- **C++ IDF flashes.** `idf.py -p /dev/ttyUSB0 -b 460800 flash` → bootloader,
  partition table, app all verify; hard reset via RTS.
- **Serial run proof is not yet captured.** `idf.py monitor` requires a TTY
  (container stdin is not a TTY); a `script -qec` pseudo-TTY satisfied the
  monitor but showed no boot/app lines. After the hard reset esptool cannot
  re-enter download mode (`No serial data received`), consistent with GPIO0
  released / the app running. Need the user to confirm the GPIO33 LED or fix
  the serial RX path; `idf.py flash` itself verified all three images.
- **Rust build first attempt failed on host disk, not the toolchain.**
  `/tmp` is a 7.7 G tmpfs and hit 100%; `esp-idf-sys` failed while checking out
  IDF. The workspace was moved to `/home/inumaki/.cache/opencode/` and the
  build is retried there (132 G free). Evidence: `df -h /tmp` -> 100% used;
  log `failed to run custom build command for esp-idf-sys ...` after the
  submodule checkout.
- **Flash-backend model:** the current pack-level `probe_backend` cannot serve
  C/C++ (esptool triplet) and Rust (`espflash <ELF>`) at once. The reusable
  design is a `flash_backend` fact on the build `StackSpec` (AD-11), falling
  back to the pack's `probe_backend`; a small `EspflashAdapter` then flashes the
  Rust ELF. `espflash 4.4.0` is in the idf-rust image.
- **Rust build failure was a corrupted toolchain from the disk-full run.**
  `esp-idf-sys` downloaded IDF v6.1 and its own Xtensa GCC
  (`esp-15.2.0_20251204`), but the compiler could not execute `cc1`
  (`posix_spawnp: No such file or directory`) — the extraction was truncated
  when `/tmp` filled. Removed `.embuild` (5 G) and retried on `/home`; not a
  toolchain-version incompatibility.
- **`espflash flash <ELF>`** converts the ELF to bootloader + partition table +
  app and writes all three, with DTR/RTS reset. It fits the proposed
  `EspflashAdapter` (single piece, not the esptool triplet).

### Open

- Does the Rust `esp-idf-sys` build complete with the image's Xtensa toolchain,
  and which IDF version does it download?
- Does `espflash` flash the ESP32-CAM over the PL2303, and does the Rust app
  print/blink?
- Is the C++ run proof visible on the board (GPIO33 LED)?

> Spike stops at the box and reports `answered:` / `open:`. Implementation output
> from a spike is a failure. No second box without an explicit user call.
