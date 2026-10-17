---
id: bug-027
title: "M4 app starts only ~2/6 times after an OpenOCD reset (sits in ROM at 0x1fff2cc0)"
kind: bug
status: done
lane: direct
severity: S2
links:
  openspec: none
  bmad: []
worktree: .worktrees/bug-027/
branch: ticket/bug-027-reset-retry
repro: "flash a generated WL55JC project, then run openocd 'reset run' six times in a row, reading RCC_AHB2ENR (0x5800004c) and PWR_CR4 each time"
observed: "iterations 0 and 3 run main (AHB2ENR=0x00000002, PWR_CR4=0x00008000); iterations 1,2,4,5 do not (AHB2ENR=0x00000003, PWR_CR4=0x00000000). In the failed state DHCSR=0x01010001 (core running) but PC=0x1fff2cc0 (system ROM) — it never jumps to flash. Same ratio with and without the bug-026 fix."
expected: "after a reset the generated app always starts from its vector table (AHB2ENR shows the GPIO enable, PWR_CR4 gets written by the ctor)"
---

# M4 app starts only ~2/6 times after an OpenOCD reset

## Repro

```sh
# with the generated project flashed, in the container:
openocd -f interface/stlink-dap.cfg -f probe/probe-serial.cfg -f target/stm32wlx.cfg \
  -c 'init' -c 'targets stm32wlx.cpu0' \
  -c 'reset run' -c 'mdw 0x5800004c 1' -c 'mdw 0x5800040c 1' -c 'exit'   # repeat ~6x
```

## Observed

```
iter 0: PWR_CR4=0x00008000  AHB2ENR=0x00000002   # booted (main ran)
iter 1: PWR_CR4=0x00000000  AHB2ENR=0x00000003   # NOT booted
iter 2: PWR_CR4=0x00000000  AHB2ENR=0x00000003   # NOT booted
iter 3: PWR_CR4=0x00008000  AHB2ENR=0x00000002   # booted
iter 4: PWR_CR4=0x00000000  …                    # NOT booted
iter 5: PWR_CR4=0x00000000  …                    # NOT booted
```

In the failed state `DHCSR=0x01010001` (core is running) yet the PC sits at
`0x1fff2cc0` (system/ROM memory) — the core never jumps to the flash reset vector.
Forcing the PC (`reg pc 0x0800019c` + `resume`) always starts the app. Tried:
`reset run`, `reset halt`+`resume`, `reset halt`+gdb `continue`. **Independent of
bug-026** — the same ratio occurs with the unfixed image.

## Expected

After a reset the app always starts from its vector table.

## Fix notes

Needs a physical NRST / power-on reset (not reachable from this bench) to decide
whether this is an STLINK-V3/dapdirect reset artefact or a genuine boot-mode /
reset-vector problem. Note `bug-026` makes the M4's release ctor fire only when the
app runs, so this is the likely reason the earlier WL55 observations (bug-021/023/024,
spike-006) were non-reproducible. Also test whether halting inside the ROM window
(e.g. landing at the flash vector) is what makes the one working case work.
## Investigation update (2026-10-16)

Characterised: **pooled boot rate ≈ 53% (18/34)** — not the 2/6 first estimated.
It is a **real device-level boot-selection problem**, not an OpenOCD/STLINK artefact:

- Measured **at the reset vector, before anything runs**: `pc = 0x1fff2cc0` (system
  memory) vs `pc = 0x0800025c` (= `Reset_Handler`) — the boot-mode decision itself is
  non-deterministic. Flash contents are intact at that moment.
- **Not the reset method / driver**: forcing an nSRST pulse
  (`reset_config srst_only srst_open_drain`) gives the same rate (4/6 vs 4/6), and
  **probe-rs 0.32.0 reproduces it** (a completely different stack): pc flips between
  `0x080001e8` (booted, `PWR_CR4=0x8000`) and `0x1fff2ba2` (ROM).
- Failure forensics: `RCC_CSR = 0` (no reset-cause flags); `OPTR (0x58004020) = 0x3ffff0aa`
  (`nBOOT0=1`, `BOOT_LOCK=0`, `C2BOOT_LOCK=0`) — so `nBOOT0=1` yet it boots from
  system memory, which is inconsistent and needs RM0453's boot-mode chapter.
- Failure state persists until the next reset; the core spins forever at `0x1fff2b9e`
  (semihosting trap + RCC-touching ROM helper in the region).
- **`probe/cpu2-boot.cfg` masks this bug** (it sets C2BOOT on every attach, so a stuck
  board looks healthy) — see `bug-031`.

**Resolved the "blocked" question (2026-10-17).** The physical-reset test was run at the
bench: **NRST ×10 = 10/10 booted; USB power-cycle ×10 = 10/10 booted.** Debugger-issued
resets stayed intermittent (`reset run` scored 8/8, 7/10 and 5/10 across runs;
`reset halt`+`resume` 4/8; `reset_config srst_only srst_open_drain` was worse at 2/8).
Conclusion: the board and the program are fine; the failure is specific to
**debugger-issued resets**. The escalation-to-ST path is therefore **closed**.

## Fixed (2026-10-17) — verify-and-retry

The underlying boot-latch cause is not needed for the fix: the failure is intermittent
per reset, so retrying the reset converges.

- `engine/core/bootcheck.py` — after a reset, verify the app actually started (read a
  marker only a running program writes) and retry the reset, bounded.
- Wired into **both** reset sites: `engine/adapters/openocd.py` (`mu flash`) and the
  generated Makefile flash targets (`engine/templates/renderer.py`).
- +18 tests (378 total).

### Same-harness flash reliability (NUCLEO-WL55JC)

| | running after flash |
|---|---|
| before (main, no retry) | **5 / 10** |
| after (this fix) | **20 / 20** |

```
# before: create/build from main, then 10x `make flash` + read RCC_AHB2ENR  -> 5/10
# after:  same loop on this branch                                          -> 20/20
```

**Honesty note:** our V1 flash evidence (`ops-027`/`ops-028`, "`Verified OK` + LED
blinking") recorded a **lucky boot** — weaker than it reads. The retry makes that claim
honest going forward.

Verify: `uv run python -m pytest engine/ -q` → 378 passed.
