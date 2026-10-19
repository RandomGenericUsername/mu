# Spec Delta

## Purpose

ESP32-CAM supports C++ (`idf-cmake`) and Rust (`esp-idf-rust`) with the correct
flash backend.

## ADDED Requirements

### Requirement: ESP-IDF C++ projects

`mu create --mcu-config esp32cam --lang cpp` SHALL emit an ESP-IDF component
`main/main.cpp` with `extern "C" void app_main(void)` and a CMake source entry,
built by `idf.py build` in `espressif/idf:v6.1` and flashed by esptool.

Evidence: spike-009 C++ build+flash (143,984 B app).
Verify: `mu create/build`; `idf.py flash`.

#### Scenario: C++ cell

- **WHEN** `esp32cam` renders with `--lang cpp`
- **THEN** `CMakeLists.txt`, `main/CMakeLists.txt`, `main/main.cpp`, and
  `sdkconfig.defaults` exist; `main.cpp` has `extern "C" app_main`

### Requirement: ESP-IDF Rust projects

`mu create --mcu-config esp32cam --lang rust` SHALL emit an `esp-idf-svc` /
`esp-idf-hal` project targeting `xtensa-esp32-espidf`, built by `cargo build` in
`espressif/idf-rust:esp32_1.95.0.0` with `ESP_IDF_VERSION=v6.1`, and flashed by
`espflash`.

Evidence: spike-009 Rust build/flash/run (`esp32rust: blink 15..20`).
Verify: `mu create/build`; `espflash flash`.

#### Scenario: Rust cell

- **WHEN** `esp32cam` renders with `--lang rust`
- **THEN** `Cargo.toml`, `build.rs`, `.cargo/config.toml`, and `src/main.rs`
  exist; the target is `xtensa-esp32-espidf`; `esp-idf-svc` is a dependency

### Requirement: Per-stack flash backend

The resolved build stack SHALL select the flash backend: `esptool` for
`idf-cmake` (C/C++), `espflash` for `esp-idf-rust`. The pack default remains a
fallback.

Evidence: spike-009 `espflash flash <ELF>` vs esptool triplet.
Verify: `mu flash --dry-run` for each lang.

#### Scenario: Rust flash argv

- **WHEN** flashing an `esp32cam --lang rust` project
- **THEN** the argv is `espflash flash --port <tty> --chip esp32 <ELF>`
