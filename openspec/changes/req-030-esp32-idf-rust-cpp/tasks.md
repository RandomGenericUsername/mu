# Tasks

## 1. C++ parity

- [x] 1.1 `esp32cam` `cpp: idf-cmake`; render `main/main.cpp` with `extern "C"
      app_main`; CMake `SRCS "main.cpp"`. Verify: `mu create/build`.
- [x] 1.2 ESP32 cpp render test + e2e cell. Verify: `pytest`, e2e.
- [x] 1.3 Live C++ flash/run (GPIO33 + serial). Verify: `idf.py flash`.

## 2. Rust stack

- [x] 2.1 Add `esp-idf-rust` StackSpec (cargo, idf-rust image, env setup);
      `esp32cam` `rust: esp-idf-rust`. Verify: stack tests.
- [x] 2.2 `idf-rust` family: `Cargo.toml`, `build.rs`, `.cargo/config.toml`,
      `src/main.rs` (GPIO33 blink + log), `.vscode` tasks, README.
      Verify: render file list.
- [x] 2.3 `EspflashAdapter` + per-stack `flash_backend`; CLI resolves it.
      Verify: argv/parse tests.
- [x] 2.4 e2e `idf-rust` builder + pack cell. Verify: `pytest`, e2e.
- [x] 2.5 Live Rust flash/run via `mu`/`espflash`. Verify: serial log.
- [x] 2.6 Docs/evidence; `make test` + `openspec validate`; merge.
