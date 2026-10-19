# Tasks

## 1. Shared helpers

- [ ] 1.1 Extract `pre_init(core)` and `main_rs(core)` from
      `families/rust_cortex_dual.py` into module functions; dual family calls
      them. Verify: `pytest -k families`.
- [ ] 1.2 Add `families/rust_cortex_single.py` (single-package layout, LED,
      `flip-link`, `opt-level = "s"`). Register it for `rust-cortex`.
      Verify: F411RE render file list.

## 2. Debug + config

- [ ] 2.1 `--vscode`: `probe-rs-debug` one `coreConfig` (SVD, native cargo ELF),
      tasks Build/Clean/Flash; fetch the pinned F411 SVD.
      Verify: JSON + `probe/STM32F411.svd`.
- [ ] 2.2 README for the single-core Rust flow (build, probe-rs flash/debug,
      expected PA5 blink). Verify: text.

## 3. Tests + live

- [ ] 3.1 Update cell/renderer tests for the LED/`flip-link`/`.vscode` changes;
      remove the old `wfi`/no-LED assertions. Verify: `pytest`.
- [ ] 3.2 Live F411RE: `mu create --vscode`, `mu build`, probe-rs flash/run,
      read `GPIOA_ODR` (PA5 toggles). Verify: `docs/flash-run-evidence.md`.
- [ ] 3.3 `make test`, e2e F411RE cell, `openspec validate`; merge.
