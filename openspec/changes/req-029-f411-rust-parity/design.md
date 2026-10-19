# Design

## Context

`ProjectPlan` (req-028) already has `CorePlan.example_led`, `CorePlan.svd_path`,
`DebugPlan` and the per-core memory. The dual family emits LED/counter,
`__pre_init`, Makefile and `probe-rs-debug`. The single-core Rust family is still
the legacy `wfi` branch.

## Goals / Non-Goals

**Goals:** F411RE Rust blinks PA5; `--vscode` gives probe-rs debug + SVD; the
single-package layout is preserved; live proof.

**Non-Goals:** Makefile for single-core (Cargo is sufficient), ESP32CAM Rust,
HAL/radio.

## Decisions

- **D1 — Reuse the dual family’s code-generation helpers.** Extract
  `pre_init(core)` and `main_rs(core)` from `rust_cortex_dual.py`; both families
  call them. One source for the LED/counter/target code.
- **D2 — Keep the single-package layout.** F411RE has one core; a `src/main.rs`
  + root `Cargo.toml` is the natural shape and avoids a needless `m4/` directory.
- **D3 — Wire `flip-link` properly.** `[target.<arch>] linker = "flip-link"` in
  `.cargo/config.toml`; remove the unused `build-dependencies` entry (it caused
  the known warning).
- **D4 — `opt-level = "s"` dev.** The C++ path uses `-Os`; `0` makes the NOP
  blink visibly wrong (proved on WL55 in req-028).
- **D5 — probe-rs debug.** One `coreConfig` with `coreIndex 0`, native cargo ELF
  path, SVD; `flashingEnabled: true` + `preLaunchTask: Build` (single-core has no
  released-sibling/reset constraint). `mu build` remains the host path.
- **D6 — No Makefile.** Single-core Rust keeps `cargo build`; `mu build` and
  `probe-rs` cover flash/debug. This avoids introducing a Makefile where the C++
  generator used one only because it has no cargo.

## Risks / Trade-offs

- [Risk] `probe-rs-debug` flashing on F411RE vs OpenOCD: `spike-008` proved
  probe-rs flashes/runs the generated Rust ELF on F411RE. Use it.
- [Risk] Delay calibration changes with `opt-level = "s"`; live PA5 readback is
  the check.

## Verification plan

- Unit: F411RE render has LED markers, no `wfi`, `flip-link`, `opt-level = "s"`,
  `.vscode` `coreConfig` + SVD.
- Build: `mu build` in `lang-rust:1.99.0`.
- Live: `probe-rs` flash/run; `GPIOA_ODR` bit 5 toggles.
- `make test`, e2e (F411RE cell), `openspec validate`.
