---
id: bug-032
title: "C++ WL55 `flash-M0+` prints a false `DID NOT BOOT` (sibling not released yet)"
kind: bug
status: triage
lane: direct
severity: S3
links:
  openspec: none
  bmad: none
worktree: none
branch: none
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
