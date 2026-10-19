# Spec Delta

## Purpose

Single-core Rust projects emit the pack LED and probe-rs debug config, matching
C/C++ behaviour on F411RE.

## ADDED Requirements

### Requirement: Single-core Rust emits the pack LED

`mu create --lang rust` on a single-core pack with `example.led` SHALL emit a
raw-register blink of that LED (not a `wfi` loop), with the dev profile at
`opt-level = "s"` and `flip-link` wired through `.cargo/config.toml`.

Evidence: req-028 proved the LED/opt-level/flip-link combination on WL55;
F411RE LED facts are in the pack (`example.led` PA5).
Verify: `mu create --mcu-config stm32f411re --lang rust … && grep -n 'GPIOA\|delay_half_period' src/main.rs`.

#### Scenario: F411RE PA5 blink

- **WHEN** `stm32f411re` renders with `--lang rust`
- **THEN** `src/main.rs` contains the PA5 GPIOA/RCC/BSRR writes and a delay loop

#### Scenario: no-LED pack fallback

- **WHEN** a single-core pack has no `example.led`
- **THEN** the primary falls back to a watchable `COUNTER` loop

### Requirement: Single-core Rust debug uses probe-rs

`--vscode` SHALL emit a `probe-rs-debug` config with one `coreConfig`
(`coreIndex 0`, native cargo `programBinary`, the pack SVD), plus build/clean/
flash tasks. The launch config SHALL flash (`flashingEnabled: true`) and run.

Evidence: Rust image has probe-rs and no GDB; `spike-008` proved probe-rs
flashes/runs the F411RE Rust ELF.
Verify: `grep -n 'probe-rs-debug\|coreConfigs' .vscode/launch.json`.

#### Scenario: F411RE debug

- **WHEN** `stm32f411re` renders with `--lang rust --vscode`
- **THEN** `launch.json` has a probe-rs config with the F411 SVD
