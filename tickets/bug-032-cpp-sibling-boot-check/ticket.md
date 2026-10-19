---
id: bug-032
title: "C++ WL55 `flash-M0+` prints a false `DID NOT BOOT` (sibling not released yet)"
kind: bug
status: done
lane: direct
severity: S3
links:
  openspec: none
  bmad: none
worktree: .worktrees/bug-032/
branch: ticket/bug-032-cpp-sibling-boot-check
repro: "mu create --mcu-config stm32wl55jc --lang cpp --name wl55 --path /tmp && cd /tmp/wl55/wl55 && make flash"
observed: "flash-M0+ ends with `mu-boot: DID NOT BOOT after 10 attempts (last pc=0x1fff...)`; make continues, flash-M4 then verifies and the board runs"
expected: "flash-M0+ prints only `** Verified OK **`; the verify-and-retry check runs on the primary (or after CPU2 is released)"
---

# C++ WL55 `flash-M0+` prints a false `DID NOT BOOT`

## Repro

```sh
mu create --mcu-config stm32wl55jc --lang cpp --name wl55 --path /tmp
cd /tmp/wl55/wl55
make flash
```

## Observed

`flash-M0+` programs and verifies the M0+ image, then its per-core boot check
runs 10 resets and prints:

```
mu-boot: DID NOT BOOT after 10 attempts (last pc=0x1fff29a0, expected inside 0x8020000)
```

`make` continues to `flash-M4`, which verifies and prints
`mu-boot: verified`. The board runs (M4 LED, M0+ counter), so the sibling
message is a false negative: CPU2 is still in reset until the M4 runs.

## Expected

The sibling flash target should not claim it booted. The verify-and-retry check
belongs to the primary (the piece whose reset decides the board state).

## Fix notes

- `engine/templates/renderer.py` `core_context`: when
  `facets.cpu2_boot` is present, set `boot_check_cmds = ""` for every
  non-primary core; keep it for the primary.
- `engine/templates/tests/test_bug027_boot_retry.py`: assert the sibling target
  has no `mu-boot` loop and the primary does.
- The Rust dual family already omits sibling boot checks
  (`families/rust_cortex_dual.py`), so this aligns C++ with the validated Rust
  behavior. Re-run the WL55 live flash and `docs/flash-run-evidence.md`.

Evidence: live 2026-10-19, NUCLEO-WL55JC (`0483:374e` serial
`001C00374741500220383733`); `make flash` output above.

## Fix implemented (2026-10-19)

- `engine/templates/renderer.py` `core_context`: for a `cpu2_boot` pack, the
  non-primary core's `boot_check_cmds` is empty; only the primary carries the
  verify-and-retry loop.
- `engine/templates/tests/test_bug027_boot_retry.py`: regression asserts
  `flash-M0+` has no `mu-boot` and `flash-M4` keeps the M4 window; the
  `make flash` / `mu flash` parity test checks only the primary for
  `cpu2_boot` packs.
- Generated WL55 C++ Makefile now has:
  `flash-M0+: ... -c "program … verify reset" -c "exit"` (no boot loop) and
  `flash-M4+: ... <mu-boot loop>`.

Evidence: `uv run pytest engine -q` -> **401 passed**; rendered Makefile grep
above. **Live re-check pending:** the WL55JC is not attached (only F411RE
`0483:3752` is enumerated), so the original `make flash` repro cannot be
re-run here. The regression covers the generated recipe; re-run the repro on
the WL55 to flip this to `done`.

## Live verification (2026-10-19, NUCLEO-WL55JC)

Probe: STLINK-V3 `0483:374e` serial `001C00374741500220383733`.

Repro: fresh `mu create --mcu-config stm32wl55jc --lang cpp`, `mu build`,
then `make flash` in `lang-cpp:15.3.rel2` with `MU_PROBE_SERIAL`.

Observed:

```
flash-M0+ ... ** Programming Finished ** / ** Verified OK **
            (no mu-boot loop — the fix)
flash-M4  ... ** Programming Finished ** / ** Verified OK **
mu-boot: attempt 0/10 pc=0x80001e2
mu-boot: RUNNING from flash
mu-boot: verified
```

Post-flash readback: M0+ `counter` (`0x2000c01c`) = `0x0000000c`; M4
`GPIOB_ODR` (`0x48000414`) = `0x00008000`. Board is running.

**Status: done.**
