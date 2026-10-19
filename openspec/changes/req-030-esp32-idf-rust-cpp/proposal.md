# Proposal

## Why

ESP32-CAM is the last board with a thinner language matrix: only C is declared.
C++ needs a `main.cpp` component; Rust needs an ESP-IDF Rust stack. Spike-009
proved both toolchains and a live Rust flash/run, so this is implementation, not
research.

## What Changes

- `esp32cam`: `cpp: idf-cmake`, `rust: esp-idf-rust`.
- `idf-cmake` family accepts `cpp`: emit `main/main.cpp` (`extern "C"
  app_main`) and register it in CMake.
- New `esp-idf-rust` stack (`cargo build`, `espressif/idf-rust:esp32_1.95.0.0`,
  `source /home/esp/export-esp.sh`) and `idf-rust` family
  (`esp-idf-svc`/`esp-idf-hal`, Xtensa target, `build.rs`, `espflash` tasks).
- New `EspflashAdapter` (FlashPort) and per-stack `flash_backend` so C/C++ uses
  esptool (triplet) and Rust uses espflash (ELF).
- e2e builder for `idf-rust`; C++ IDF cell.

## Capabilities

### Modified Capabilities

- `template-generation`: IDf C++ and Rust family.
- `pack-schema`: `cpp`/`rust` stacks for `esp32cam`; per-stack flash backend.

## Impact

- Code: `engine/templates/renderer.py`, `families/idf_*`, `engine/core/stacks.py`,
  `engine/adapters/{esptool,espflash,__init__}.py`, `engine/cli/main.py`,
  `engine/verify/e2e.py`, `packs/esp32cam.yaml`, tests/docs.
- **Out of scope:** WiFi/camera examples beyond the blink/log scaffold, JTAG
  debug (ESP32-CAM has none), other ESP32 variants.

Evidence: spike-009 live results. Verify: `mu create --mcu-config esp32cam
--lang cpp|rust …`.
