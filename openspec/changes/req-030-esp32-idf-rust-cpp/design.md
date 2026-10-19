# Design

## Context

Spike-009 validated:
- `espressif/idf:v6.1` builds `main.cpp` and `idf.py flash` verifies the triplet.
- `espressif/idf-rust:esp32_1.95.0.0` builds `esp-idf-svc 0.53` /
  `esp-idf-hal 0.47` / `esp-idf-sys 0.38.1` against IDF v6.1; `espflash`
  flashes the ELF and the app runs (`esp32rust: blink 15..20`).
- The CAM has no auto-reset; GPIO0→GND + RESET is a board ritual, not a tool
  problem.

## Goals / Non-Goals

**Goals:** C++ `idf-cmake`, Rust `esp-idf-rust`, correct flash backend, e2e/live.
**Non-Goals:** camera/WiFi examples, JTAG debug, other ESP32 variants.

## Decisions

- **D1 — C++ is a language delta of `idf-cmake`.** Emit `main/main.cpp`
  (`extern "C" void app_main(void)`), CMake `SRCS "main.cpp"`. Same image/build/
  flash as C.
- **D2 — Rust uses the official `espressif/idf-rust:esp32_1.95.0.0` image.**
  It has Rust 1.95 nightly + espflash 4.4.0 + Xtensa GCC; `esp-idf-sys` downloads
  IDF v6.1 into the project (`.embuild`, gitignored). `StackSpec.env_setup =
  "source /home/esp/export-esp.sh"`.
- **D3 — `idf-rust` family.** `Cargo.toml` (`esp-idf-svc 0.53`, `esp-idf-hal`,
  `log`, `embuild`), `build.rs` (`embuild::espidf::sysenv::output()`),
  `.cargo/config.toml` (`xtensa-esp32-espidf`, `ldproxy`, `espflash flash
  --monitor`, `MCU=esp32`, `ESP_IDF_VERSION=v6.1`, `build-std`), `src/main.rs`
  GPIO33 blink + log, `.vscode` Build/Flash/Monitor tasks.
- **D4 — Per-stack `flash_backend`.** Add `flash_backend` to `StackSpec`
  (`esptool` C/C++, `espflash` Rust), resolved by the CLI before the pack
  default. New `EspflashAdapter` renders `espflash flash --port <tty> --chip
  <target> <ELF>` and parses `Flashing has completed!`.
- **D5 — e2e:** `build_idf_cell` for C++; new `build_idf_rust_cell` for Rust
  (`cargo build`, `xtensa-esp32-elf-size`, app fits the 4 MB partition).

## Risks / Trade-offs

- Rust image lacks IDF/cmake; first build downloads ~5 G into the project
  `.embuild`. Gitignore it; document the first-build cost. A shared `lang-idf`
  image is a future optimization.
- USB permissions: the image runs as `esp` (UID 1000); `/dev/ttyUSB0` is
  `root:uucp`. `mu flash` may need to run the adapter as root/with the `uucp`
  group; the generated README documents the board ritual. (Spike used
  `--user 0` for espflash.)
- No auto-reset: GPIO0→GND + RESET for flashing; release + RESET to run.

## Verification plan

- Unit: ESP32 cpp/rust render, stack mapping, `EspflashAdapter` argv/parse,
  per-stack backend selection.
- Build: `idf.py build` (C++), `cargo build` (Rust) in their images.
- Live: C++ and Rust flash/run; GPIO33 blink + serial lines.
- `make test`, e2e, `openspec validate req-030`.
