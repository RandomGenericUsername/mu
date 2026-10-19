---
id: ops-041
title: "H755ZI-Q Rust dual-core live proof (create → build → flash → run)"
kind: ops-task
status: done
lane: direct
links:
  openspec: none
  bmad: none
worktree: .worktrees/ops-041/
branch: ticket/ops-041-h755-rust-live
---

# H755ZI-Q Rust dual-core live proof

> `ops-task`; no `parent:`.

## Work

Exercise the req-028 Rust dual-core path on the attached NUCLEO-H755ZI-Q
(STLINK-V3 `0483:3754` serial `0023004B3132511438363431`):

- `mu create --mcu-config stm32h755 --lang rust --vscode`;
- `mu build` (both M7/M4 ELFs);
- `make flash` (M7 then M4) and/or `mu flash`;
- run proof: M7 LD2 (PE1) toggles, M4 `COUNTER` advances;
- debug proof: attach to cpu0/cpu1 (OpenOCD) and probe-rs core indices;
- record evidence in `docs/flash-run-evidence.md`.

If the flow exposes a bug, fix it with a regression test in this branch and
record it; otherwise file a follow-up ticket.

## Done-when

- [x] Fresh project builds both cores: `build/M7/…-M7.elf`, `build/M4/…-M4.elf`.
- [x] `make flash` / `mu flash` verifies both banks.
- [x] Live: M7 PE1 toggles and M4 `COUNTER` advances; PCs inside their loops.
- [x] `probe-rs` sees/uses the expected per-core indices.
- [x] `docs/flash-run-evidence.md` + this ticket record commands and observed output.
- [x] `make test` green; branch merged to `main`.

## Evidence

Probe: `lsusb` → `0483:3754 STLINK-V3`; `probe-rs list` →
`0023004B3132511438363431`.

**Flow + fixes**

- `mu create --mcu-config stm32h755 --lang rust --vscode` → `m7/` + `m4/`.
- `mu build` → `build/M7/stm32h755-M7.elf`, `build/M4/stm32h755-M4.elf`.
- First flash failed: `[stm32h7x.ap2] Examination failed` — the board was in a
  low-power image and the board cfg's `connect_deassert_srst` cannot examine it.
  Fixed in this branch:
  - pack `openocd.flash_reset_config` (H755:
    `srst_only srst_open_drain connect_assert_srst`), emitted in the Makefile
    and `mu flash` argv; debug configs unchanged;
  - per-core `targets stm32h7x.cpu0/cpu1` in each flash target, so `program` and
    the boot check act on the right core (previously `flash-M4` checked cpu0's
    PC and printed a false `DID NOT BOOT`).
- `make flash`: `** Verified OK **` ×2; `mu-boot: verified` on both.
- Live: M4 `pc=0x08100474`, `COUNTER=0x2E3`; M7 `GPIOE_ODR` toggles
  `0x00000002 ↔ 0x00000000`; `probe-rs chip info STM32H755ZI` → `cm7`, `cm4`.
- `uv run pytest engine -q` → **399 passed** (new reset_config + target tests).
- `uv run python -m engine.verify.e2e` → 10/10 (H755 Rust dual already green).

