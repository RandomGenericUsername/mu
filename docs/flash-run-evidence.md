# Flash-run evidence (V1) — per-pack proof

Durable record that each **V1 matrix pack** completes create → build → **flash →
run** from a clean machine with the pack-declared observable proof. The build half
is `docs/e2e-evidence.md` (10/10 cells); this is the live flash/run half. The
proof ladder is probe readback first, LED second, manual register inspection as
fallback (`spec:69`).

| Pack (board) | Probe | OpenOCD target | Flash | Run proof | Recorded |
| --- | --- | --- | --- | --- | --- |
| `stm32f411re` (NUCLEO-F411RE) | `0483:3752` | `stlink.cfg` + `board/st_nucleo_f4.cfg` | `Verified OK` | LD2 (PA5) toggles ~1 Hz; PC in `delay_half_period` | 2026-10-14 |
| `stm32h755` (NUCLEO-H755ZI-Q) | `0483:3754` | `stlink-dap.cfg` + `board/st_nucleo_h745zi.cfg` (+ `DUAL_CORE`) | `Verified OK` ×2 (both banks) | M7 LD2 toggles; M4 `counter` increments | 2026-10-14 |
| `stm32wl55jc` (NUCLEO-WL55JC), C/C++ | `0483:374e` | `stlink-dap.cfg` + `target/stm32wlx.cfg` | `Verified OK` ×2 (M0+ then M4) | M4 LD1 (PB15) toggles; `GPIOB_ODR` bit 15 flips | 2026-10-16 |
| `stm32wl55jc` (NUCLEO-WL55JC), Rust dual (req-028) | `0483:374e` | `stlink-dap.cfg` + `target/stm32wlx.cfg` | `Verified OK` ×2 (M0+ then M4) | M4 `GPIOB_ODR` toggles; M0+ `pc=0x0802010c`, `COUNTER=0xA7`; `PWR_CR4=0x8000`, `SRRVR=0xfeff8000` | 2026-10-19 |

## How each was reproduced

Fresh project + fresh container, probe pinned by serial (containers get the whole
USB bus — bug-018):

```sh
# F411RE / H755ZI-Q: see docs/vscode-debug.md §9
mu create --name f411-clean --path ~/Desktop --mcu-config stm32f411re --lang c --vscode
docker run -d --name mu-f411 --device-cgroup-rule 'c 189:* rmw' \
  -v /dev/bus/usb:/dev/bus/usb -v ~/Desktop/f411-clean:/project \
  -e MU_PROBE_SERIAL=<serial> -w /project ghcr.io/randomgenericusername/lang-cpp:15.3.rel2 sleep infinity
docker exec mu-f411 bash -lc 'cd /project && make flash'

# WL55JC: dual-core, sibling-first flash (M0+ then M4 — bug-023)
mu create --mcu-config stm32wl55jc --lang c --name wl55-clean --path /tmp/opencode/wl55
mu build --project-dir /tmp/opencode/wl55/wl55-clean
docker run --rm --device-cgroup-rule 'c 189:* rmw' -v /dev/bus/usb:/dev/bus/usb \
  -v /tmp/opencode/wl55/wl55-clean:/project -w /project \
  -e MU_PROBE_SERIAL=001C00374741500220383733 \
  ghcr.io/randomgenericusername/lang-cpp:15.3.rel2 make flash
```

Probe readback (WL55JC run proof — the M4 LED pin, `0x48000414` = GPIOB_ODR):

```sh
openocd -f interface/stlink-dap.cfg -f probe/probe-serial.cfg -f target/stm32wlx.cfg \
  -c 'init' -c 'targets stm32wlx.cpu0' -c 'reset run' \
  -c 'mdw 0x48000414 1' -c 'sleep 260' -c 'mdw 0x48000414 1' ...
# → 0x48000414: 00008000 / 00008000 / 00008000 / 00000000 / 00000000  (PB15 toggles)
```

Rust dual-core (req-028) reproduction — generated project, pinned Rust image,
OpenOCD flash (probe-rs is the debug backend):

```sh
mu create --mcu-config stm32wl55jc --lang rust --name wl55-rust --path /tmp/opencode/wl55
cd /tmp/opencode/wl55/wl55-rust
docker run --rm --device-cgroup-rule 'c 189:* rmw' -v /dev/bus/usb:/dev/bus/usb \
  -v "$PWD":/work -w /work -e MU_PROBE_SERIAL=001C00374741500220383733 \
  ghcr.io/randomgenericusername/lang-rust:1.99.0 make flash
# → ** Verified OK ** (M0+) then ** Verified OK ** (M4), "mu-boot: verified"

# CPU2 release + sibling proof (attach-only; no reset)
openocd -f interface/stlink-dap.cfg -f probe/probe-serial.cfg \
  -f probe/dual-core.cfg -f target/stm32wlx.cfg \
  -c 'init' -c 'stm32wlx.cpu1 arp_examine' -c 'targets stm32wlx.cpu1' \
  -c 'poll' -c 'halt' -c 'reg pc' -c 'mdw 0x2000fff8 1' \
  -c 'mdw 0x5800040c 1' -c 'mdw 0x58004084 1' -c 'resume' -c 'shutdown'
# → pc 0x0802010c; COUNTER 0x000000a7; PWR_CR4 0x00008000; SRRVR 0xfeff8000

# M4 LED proof
openocd -f interface/stlink-dap.cfg -f probe/probe-serial.cfg -f target/stm32wlx.cfg \
  -c 'init' -c 'targets stm32wlx.cpu0' -c 'halt' -c 'mdw 0x48000414 1' \
  -c 'resume' -c 'sleep 260' -c 'halt' -c 'mdw 0x48000414 1' -c 'resume' -c 'shutdown'
# → 0x48000414: 00008000 / 00000000  (PB15 toggles)
```

## Scope note

**Single-core Rust remains build-parity only** (`spike-008` decision, option c):
the generated single-core example is a bare `wfi` loop with no observable proof.
The **dual-core Rust** path (req-028) is flash/run proven on WL55JC: both images
verify, the M4 blinks PB15, the M0+ counter advances, and CPU2 is released by
the M4's `__pre_init` (`PWR_CR4=0x8000`). F411RE/H755 Rust live proof is **not**
claimed. The build half of every cell is in `docs/e2e-evidence.md` (10/10).

## Sources

- `tickets/ops-020-clean-test-doc/ticket.md` + `docs/vscode-debug.md` §9 — F411RE, H755ZI-Q.
- `tickets/ops-027-wl55-clean-run/ticket.md` — WL55JC.
- `tickets/ops-023-e2e-matrix/ticket.md` + `docs/e2e-evidence.md` — the build half.
- `tickets/spike-008-rust-flash-run/ticket.md` — Rust scope.
