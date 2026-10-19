# Proposal

## Why

After req-028, dual-core Rust matches C++ on WL55/H755. F411RE is the remaining
non-ESP32 board: C++ blinks PA5 and ships `.vscode`/SVD, while Rust still emits a
bare `wfi` image with no debug integration. The new `ProjectPlan` already carries
the LED/SVD/debug facts; the single-core Rust family just doesn't consume them.

## What Changes

- Make `rust-cortex` a plan-driven family (`families/rust_cortex_single.py`)
  instead of the legacy `wfi` branch.
- Emit the pack LED blink (PA5) with raw registers, `opt-level = "s"`, and
  `flip-link` wired through `.cargo/config.toml`.
- `--vscode` emits `probe-rs-debug` (one `coreConfig`, F411 SVD) and
  build/clean/flash tasks.
- Preserve the single-package layout (`Cargo.toml`, `src/main.rs`, `memory.x`).

## Capabilities

### Modified Capabilities

- `template-generation`: single-core Rust consumes `ProjectPlan`; LED + probe-rs
  debug + SVD.

## Impact

- Code: `engine/templates/families/rust_cortex_single.py`,
  `families/rust_cortex_dual.py` (shared LED/pre-init helpers),
  `families/legacy.py`, tests.
- **Out of scope:** ESP32CAM Rust, HAL/Embassy, radio.

Evidence: req-028 live dual-core proof; F411RE C++ live proof; probe visible.
Verify: `mu create --mcu-config stm32f411re --lang rust --vscode …`.
