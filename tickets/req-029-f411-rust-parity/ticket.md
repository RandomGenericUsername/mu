---
id: req-029
title: "F411RE Rust single-core parity: LED, probe-rs debug, live proof"
kind: requirement
status: done
size: S
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-029-f411-rust-parity
  bmad: []
worktree: .worktrees/req-029/
branch: ticket/req-029-f411-rust-parity
parent: epic-002
children: []
---

# F411RE Rust single-core parity

## User value

The last non-ESP32 board still has a thinner Rust path than C/C++: F411RE Rust
builds a bare `wfi` image with no LED, no `.vscode`, and no SVD. This closes that
gap by making the single-core Rust family consume the same `ProjectPlan` as the
dual-core family.

## Acceptance

- [x] `stm32f411re --lang rust` emits a PA5 blink (raw registers) instead of
      `wfi`. `Verify: mu create … && grep GPIO src/main.rs`
- [x] `--vscode` emits a `probe-rs-debug` launch config with the F411 SVD.
      `Verify: grep coreConfigs .vscode/launch.json`
- [x] `flip-link` is wired via `.cargo/config.toml`; the dev profile is
      `opt-level = "s"`; the unused build-dependency is gone.
- [x] `mu build` succeeds in the pinned Rust image.
- [x] Live: flash the F411RE (`0483:3752:0672FF515250898367070638`); PA5
      `GPIOA_ODR` toggles.
- [x] `make test`, `openspec validate req-029-f411-rust-parity`, e2e green.

## Evidence

- Probe: `probe-rs list` → `0483:3752:0672FF515250898367070638`.
- C++ F411RE is already live-proven (`docs/flash-run-evidence.md`).
- `spike-008` proved probe-rs flashes/runs the generated Rust ELF on F411RE.

## Verification (2026-10-19)

- `mu create --mcu-config stm32f411re --lang rust --vscode` → PA5 blink source,
  `probe-rs-debug` launch, `probe/STM32F411.svd`.
- `mu build` → `target/thumbv7em-none-eabihf/debug/stm32f411re` in the pinned
  image.
- Flash: `openocd … -c "program … verify reset"` → `** Verified OK **`.
- Live: `GPIOA_ODR` (`0x40020014`) samples `0x00000000 / 0x00000020 / 0x00000000`
  (PA5/LD2 toggles). `probe-rs chip info STM32F411RE` → one core; `probe-rs run`
  flashes/runs the ELF.
- `uv run pytest engine -q` → **401 passed**.
