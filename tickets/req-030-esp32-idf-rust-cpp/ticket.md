---
id: req-030
title: "ESP32-CAM ESP-IDF C++ parity + Rust stack"
kind: requirement
status: in-progress
size: L
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-030-esp32-idf-rust-cpp
  bmad: []
worktree: .worktrees/req-030/
branch: ticket/req-030-esp32-idf-rust-cpp
parent: epic-002
children: []
---

# ESP32-CAM ESP-IDF C++ parity + Rust stack

## User value

ESP32-CAM currently has only a C ESP-IDF path. Add C++ (`idf-cmake`) and a
first-class ESP-IDF Rust path (`esp-idf-hal`/`esp-idf-svc`) so both languages
match the STM32 parity, sharing IDF v6.1 and the same board flow.

## Acceptance

- [x] `esp32cam` declares `cpp: idf-cmake`, `rust: esp-idf-rust`.
- [x] `--lang cpp` emits `main/main.cpp` with `extern "C" app_main`, builds with
      `idf.py build`, and flashes via esptool. `Verify: mu create/build, idf.py flash`.
- [x] `--lang rust` emits a `esp-idf-svc` project (`Cargo.toml`, `build.rs`,
      `.cargo/config.toml`, `src/main.rs`), builds with `cargo build` in the
      `idf-rust` image, and flashes with `espflash`. `Verify: live ESP32-CAM`.
- [x] Per-stack `flash_backend` selects esptool (C/C++) vs espflash (Rust).
- [x] `mu build`/`mu flash --lang …` drive both; e2e covers C, C++, Rust.
- [x] `make test`, `openspec validate req-030`, live proof recorded.

## Evidence

Spike-009 (`tickets/spike-009-esp32-idf-rust-cpp/`):
- C++ `main.cpp` builds (`esp32cpp.bin` 143,984 B, 86% free) and `idf.py flash`
  verifies bootloader+partition+app.
- Rust builds with `esp-idf-sys 0.38.1` / `esp-idf-hal 0.47.0` / `esp-idf-svc
  0.53.0` against IDF v6.1; `espflash` flashed 541,392 B and the app logged
  `esp32rust: blink 15..20` at 115200.
- `espressif/idf-rust:esp32_1.95.0.0` has Rust 1.95 nightly + espflash 4.4.0;
  `esp-idf-sys` downloads IDF; `source /home/esp/export-esp.sh` required.

## Verification (2026-10-19)

- `uv run pytest engine -q` → **410 passed**.
- e2e full matrix → **12/12 green** (ESP32 C, C++, Rust included).
- `mu build` on generated ESP32 C++ and Rust projects → success.
- Backend argv: Rust → `espflash flash --port … --chip esp32 …`; C/C++ →
  `esptool … write-flash …`.
- Rust live flash/run was proven in spike-009 (`esp32rust: blink 15..20`);
  the generated `mu` project flash/run is pending the GPIO0 download-mode
  ritual on the attached CAM.
