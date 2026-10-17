---
id: spike-008
title: "Rust live flash/run: is it a V1 gate, and does probe-rs flash F411RE/H755?"
kind: spike
status: reported
lane: direct
timebox: 3h
questions:
  - "Does the V1 success signal ('each matrix cell ... flash and the board runs', spec:65-67) require a live Rust flash/run proof, or does build-to-ELF parity (ops-023) suffice?"
  - "Does probe-rs (pinned 0.32.0) flash + run the generated Rust images on NUCLEO-F411RE and NUCLEO-H755ZI-Q?"
  - "If required, what is the concrete per-board proof command, and does the pack already declare the probe-rs chip?"
answered:
  - "Q1 (gate): NO — for V1, Rust is build-parity only; the flash/run gate rests on the C/C++ LED proof per board. User decision 2026-10-16 (option c)."
  - "Q2: YES — probe-rs 0.32.0 flashes, verifies and runs the generated Rust ELFs on both boards."
  - "Q3: proof command is `probe-rs run --chip <CHIP> --probe <VID:PID:SERIAL> <elf>`; both chips are pack-declared."
  - "Blocker: `mu build` (Rust) omits `--target`; filed as bug-025 and still needed so build-parity actually works."
open: []
links:
  openspec: none
  bmad: none
worktree: .worktrees/spike-008/
branch: ticket/spike-008-rust-flash-decision
---

# Rust live flash/run: is it a V1 gate, and does probe-rs flash F411RE/H755?

## Questions

- Does the V1 success signal require a live Rust flash/run proof, or does
  build-to-ELF parity (`tickets/ops-023-e2e-matrix/ticket.md`) suffice?
- Does `probe-rs` (pinned `0.32.0`) flash + run the generated Rust images on
  NUCLEO-F411RE and NUCLEO-H755ZI-Q?
- If required, what is the concrete per-board proof command, and is the chip
  pack-declared?

## Findings

### Answered

**Q2 — probe-rs flashes + runs both boards: YES.** (2026-10-16, both probes attached.)

- `probe-rs list` → `STLink V2-1 -- 0483:3752:0672FF515250898367070638` (F411RE),
  `STLink V3 -- 0483:3754:0023004B3132511438363431` (H755ZI);
  `probe-rs chip list` carries `STM32F411RE` and `STM32H755ZI`.
- **F411RE**: `probe-rs download --chip STM32F411RE --probe 0483:3752:<serial> <elf>`
  → `Finished in 0.68s`; `probe-rs verify …` → `Verification successful`;
  `probe-rs run …` → `Finished in 0.67s` then attached until SIGTERM (no fault/halt).
- **H755ZI**: `download --verify` → `Finished in 2.06s`; `verify` →
  `Verification successful`; `run` → attached until SIGTERM.
- ELFs: `target/thumbv7em-none-eabihf/debug/stm32f411re` (825612 B),
  `…/stm32h755` (825596 B).

**Q3 — proof command + pack facts.** `probe-rs run --chip <CHIP> --probe
<VID:PID:SERIAL> <elf>`; chips pack-declared (`packs/stm32f411re.yaml:62`
`STM32F411RE`, `packs/stm32h755.yaml:93` `STM32H755ZI`).

**Blocker found (not a spike artifact): `mu build` does not set the target.**
`cargo-cortex`'s `build_argv` is `("cargo","build")` (`engine/adapters/toolchain/__init__.py:27`)
with no `--target`, and no `.cargo/config.toml` is rendered — so `mu build`
compiles for the x86_64 host and fails (`rust-lld: error: undefined symbol:
Reset` … `libcore-…x86_64-unknown-linux-gnu`). The verify harness works only
because it passes `--target` itself (`engine/verify/e2e.py:340`). Filed as
`bug-025`; ELFs here were produced with the harness command
`cargo build --target thumbv7em-none-eabihf`.

### Resolved (decision 2026-10-16)

- **Q1 (the gate question) — answered: Rust is build-parity only for V1 (option c).**
  Rationale on record: the generated `src/main.rs` is a bare
  `#[entry] fn main() -> ! { loop { cortex_m::asm::wfi() } }`
  (`engine/templates/renderer.py:670`) — no LED/RTT/UART — so "the board runs" is
  not observable from the Rust image, and the pack proof ritual wants LED/RTT/UART
  (`device-matrix.md:14`, `spec:69`). Making Rust a first-class flash ritual would
  need both an LED port (like C/C++ req-014/req-015) *and* the bug-025 fix; the
  user chose to keep V1's flash/run gate on the C/C++ LED proof per board and
  scope Rust to build-to-ELF parity (as `ops-023` recorded). Revisit as a
  post-V1 follow-up.
- **Consequence:** `bug-025` still matters — build-parity is the Rust V1 evidence,
  and `mu build` currently fails without a workaround. Fix it so the documented
  path matches the harness.
- **Discrepancy to reconcile (flagged, not edited here):** the spec success signal
  ("each matrix cell ... flash and the board runs", `spec:65-67`) and the generated
  Rust `README.md` ("on-board LED PA5 … blinking on M4") both overstate Rust's V1
  scope — the README is aspirational vs the `wfi` code. Needs a spec/README
  clarification (BMAD/OpenSpec territory).
  - **Reconciled (2026-10-17) — spec half only:** `ops-032` amended `spec`
    §Success signal + CAP-3 and `device-matrix.md:3` to state **C/C++ = flash/run +
    observable proof; Rust = build-to-ELF parity** (dated amendment notes link back
    here; evidence `docs/flash-run-evidence.md` §"Scope note"). The generated Rust
    `README.md` LED claim was already fixed by `bug-025` (regression-tested in
    `engine/templates/tests/test_renderer.py`), so no README work remains here.
- **Nuance (debug attach):** after a *detached* run (`probe-rs reset`, session torn
  down), a reconnect on F411RE failed with `JtagNoDeviceConnected` — consistent
  with the bare `wfi` sleep stopping the core clock with default DBGMCU.
  `probe-rs run` (which stays attached) works; a post-V1 Rust flow should keep the
  session or configure DBGMCU.

> Spike stops at the box. No implementation here beyond the workaround builds;
> the `mu build` fix is `bug-025` (separate ticket).
