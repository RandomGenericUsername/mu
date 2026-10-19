---
id: req-028
title: "Rust dual-core parity: plan-driven template families (WL55JC + H755)"
kind: requirement
status: done
size: L
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-028-rust-dual-core
  bmad: []
worktree: .worktrees/req-028/
branch: ticket/req-028-rust-dual-core
parent: epic-002
children: []
---

# Rust dual-core parity: plan-driven template families

## User value

`mu create --lang cpp` produces a full per-core bring-up for dual-core packs,
while `--lang rust` silently uses only `cores[0]`: on H755 the M4 image is never
built, on WL55JC the M0+ image and CPU2 release are missing, and no Rust project
gets the pack LED example, per-core `memory.x`, VS Code, or SVDs. This closes
that gap with one plan shared by both languages, so the generators cannot drift.

## Acceptance

- [x] A `ProjectPlan` (domain) is derived once from `Device`; C++ and Rust
      families both emit from it. `Verify: pytest -k plan`
- [x] `TemplateFamily` is a port + registry; `render()` dispatches by resolved
      stack, with no per-language `if/elif`. `Verify: pytest -k families`
- [x] Existing C++/C/ESP-IDF output is byte-identical after the refactor.
      `Verify: pytest -k characterization`
- [x] `stm32wl55jc --lang rust` emits `m4/` + `m0plus/` packages, per-core
      `memory.x`, PB15 blink, M0+ counter, `__pre_init` release, Makefile with
      sibling-first flash, and `probe-rs-debug` `coreConfigs` with `--vscode`.
      `Verify: mu create … && find`
- [x] `stm32h755 --lang rust` emits M7 + M4 packages and per-core regions.
      `Verify: same`
- [x] `stm32f411re --lang rust` still emits the single-core project.
      `Verify: same`
- [x] `mu build` builds every core for `cargo-cortex-dual` in the Rust image.
      `Verify: mu build --project-dir … && ls build/*/*.elf`
- [x] Live WL55: both Rust ELFs verify; `PWR_CR4.C2BOOT=0x8000`; M0+ counter
      advances; PB15 toggles. `Verify: docs/flash-run-evidence.md`
- [x] `make test`, `openspec validate req-028-rust-dual-core`, and the dual e2e
      cells are green.

## Evidence

Phase 0 (live, 2026-10-19, NUCLEO-WL55JC, STLINK-V3 `0483:374e` serial
`001C00374741500220383733`):

- Rust M0+ ELF at `0x08020000` + M4 ELF at `0x08000000`: `** Verified OK **` x2
  via OpenOCD, sibling-first.
- `PWR_CR4` (`0x5800040C`) = `0x00008000`; `FLASH_SRRVR` (`0x58004084`) =
  `0xfeff8000` after the M4's `__no_mangle __pre_init`.
- M0+ `pc=0x08020218` (inside its loop), counter increments.
- `GPIOB_ODR` (`0x48000414`) toggles `0x0000 <> 0x8000`; M4 counter advances.
- Bug-027 reproduced: resets 0-2 landed in ROM (`0x1fff...`), reset 3 in flash.
- `#[pre_init]` is deprecated in `cortex-m-rt` 0.7.7; a `#[no_mangle] extern "C"
  fn __pre_init()` is emitted and called (validated with `nm` + `readelf`).
- `opt-level = 0` makes the NOP blink delay several seconds; `opt-level = "s"`
  restores the intended visible blink.
- `probe-rs chip info STM32WL55JC` -> cores `cm4`, `cm0p` (index 0, 1).
- The Rust image has no GDB; probe-rs-debug is the chosen debug backend.
- `thumbv6m-none-eabi` is absent from the Rust image; runtime `rustup target add`
  works, so the image change is required.

## Verification (2026-10-19)

- `uv run pytest engine -q` -> **398 passed** (includes `pytest -k characterization`: 4 passed).
- `uv run python -m engine.verify.e2e` -> **10/10 cells green**
  (WL55/H755 Rust now dual-core; F411RE single-core unchanged).
- `mu build --project-dir /tmp/opencode/req028/stm32wl55jc` ->
  `build/M4/stm32wl55jc-M4.elf` + `build/M0+/stm32wl55jc-M0+.elf`.
- `mu flash --mcu-config stm32wl55jc --files build/M0+/… build/M4/…` ->
  `** Verified OK **` x2, `mu-boot: verified`, `2/2 OK`.
- Live: `PWR_CR4=0x00008000`, `SRRVR=0xfeff8000`, M0+ `pc=0x0802010c`,
  `COUNTER=0xA7`, `GPIOB_ODR` toggles.
- `uv run openspec validate req-028-rust-dual-core` -> valid.
