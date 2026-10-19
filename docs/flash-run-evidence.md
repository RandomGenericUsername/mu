# Flash-run evidence (V1) — per-pack proof

Durable record that each **V1 matrix pack** completes create → build → **flash →
run** from a clean machine with the pack-declared observable proof. The build half
is `docs/e2e-evidence.md` (10/10 cells); this is the live flash/run half. The
proof ladder is probe readback first, LED second, manual register inspection as
fallback (`spec:69`).

| Pack (board) | Probe | OpenOCD target | Flash | Run proof | Recorded |
| --- | --- | --- | --- | --- | --- |
| `stm32f411re` (NUCLEO-F411RE), C/C++ | `0483:3752` | `stlink.cfg` + `board/st_nucleo_f4.cfg` | `Verified OK` | LD2 (PA5) toggles ~1 Hz; PC in `delay_half_period` | 2026-10-14 |
| `stm32f411re` (NUCLEO-F411RE), Rust (req-029) | `0483:3752` | `stlink.cfg` + `board/st_nucleo_f4.cfg` | `Verified OK` | `GPIOA_ODR` bit 5 (PA5/LD2) toggles `0x20 ↔ 0x0`; probe-rs flashes/runs the ELF | 2026-10-19 |
| `stm32h755` (NUCLEO-H755ZI-Q), C/C++ | `0483:3754` | `stlink-dap.cfg` + `board/st_nucleo_h745zi.cfg` (+ `DUAL_CORE`) | `Verified OK` ×2 (both banks) | M7 LD2 toggles; M4 `counter` increments | 2026-10-14 |
| `stm32h755` (NUCLEO-H755ZI-Q), Rust dual (ops-041) | `0483:3754` | `stlink-dap.cfg` + `board/st_nucleo_h745zi.cfg` (`connect_assert_srst`) | `Verified OK` ×2 (M7 then M4) | M7 `GPIOE_ODR` toggles `0x2 ↔ 0x0`; M4 `pc=0x08100474`, `COUNTER=0x2E3`; probe-rs cores `cm7`/`cm4` | 2026-10-19 |
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

H755 Rust dual (ops-041) reproduction — the pack carries a flash-only
`reset_config ... connect_assert_srst` (a sleeping H755 cannot be examined with
the board cfg's `connect_deassert_srst`), and each flash target selects its own
OpenOCD core (`cpu0` M7 / `cpu1` M4):

```sh
mu create --mcu-config stm32h755 --lang rust --name h755-rust --path /tmp/opencode/h755
cd /tmp/opencode/h755/h755-rust
docker run --rm --device-cgroup-rule 'c 189:* rmw' -v /dev/bus/usb:/dev/bus/usb \
  -v "$PWD":/work -w /work -e MU_PROBE_SERIAL=0023004B3132511438363431 \
  ghcr.io/randomgenericusername/lang-rust:1.99.0 make flash
# → ** Verified OK ** (M7) then ** Verified OK ** (M4); both mu-boot: verified

openocd -f interface/stlink-dap.cfg -f probe/probe-serial.cfg \
  -f board/st_nucleo_h745zi.cfg -c 'init' -c 'targets stm32h7x.cpu1' \
  -c 'halt' -c 'reg pc' -c 'mdw 0x30047ff8 1' -c 'resume' -c 'shutdown'
# → pc 0x08100474; COUNTER 0x000002e3
```

F411RE Rust (req-029) reproduction — single-core, probe-rs debug config:

```sh
mu create --mcu-config stm32f411re --lang rust --name f411-rust --path /tmp/opencode/f411 --vscode
mu build --project-dir /tmp/opencode/f411/f411-rust
# flash via OpenOCD (proven) or probe-rs:
docker run --rm --device-cgroup-rule 'c 189:* rmw' -v /dev/bus/usb:/dev/bus/usb \
  -v "$PWD":/work -w /work -e MU_PROBE_SERIAL=0672FF515250898367070638 \
  ghcr.io/randomgenericusername/lang-rust:1.99.0 bash -lc \
  'openocd -f interface/stlink.cfg -f probe/probe-serial.cfg -f board/st_nucleo_f4.cfg \
     -c "program target/thumbv7em-none-eabihf/debug/stm32f411re verify reset" -c exit'
# → ** Verified OK **; GPIOA_ODR (0x40020014) samples: 0x00000000 / 0x00000020 / 0x00000000
# probe-rs chip info STM32F411RE -> one core; `probe-rs run --chip STM32F411RE --probe …` flashes/runs.
```

## ESP32-CAM (req-030)

Rust (ESP-IDF, `esp-idf-rust` stack) — GPIO0→GND + RESET for download mode,
then release GPIO0 + RESET to run:

```sh
mu create --mcu-config esp32cam --lang rust --name esp32-rust --path /tmp/opencode/esp32 --vscode
mu build --project-dir /tmp/opencode/esp32/esp32-rust
mu flash --lang rust --mcu-config esp32cam --project-dir /tmp/opencode/esp32/esp32-rust \
  --files target/xtensa-esp32-espidf/debug/esp32cam --device /dev/ttyUSB0
# → Flashing has completed! / flash verdict: 1/1 OK
# serial 115200 → I (...) esp32cam: esp32cam: blink 9..14
```

C++ (`idf-cmake`) — same GPIO0 ritual:

```sh
mu flash --lang cpp --mcu-config esp32cam --project-dir /tmp/opencode/esp32/esp32-cpp \
  --files build/bootloader/bootloader.bin build/partition_table/partition-table.bin \
          build/esp32cam.bin --device /dev/ttyUSB0
# → 3/3 OK (bootloader + partition table + app), all hash-verified
# serial 115200 → esp32cam: blink 10..16
```

## Scope note

**F411RE single-core Rust is now live-proven** (req-029): the generated Rust
project blinks PA5 (`GPIOA_ODR` bit 5 toggles). The **dual-core Rust** path
(req-028) is flash/run proven on WL55JC and H755: both images verify, the
primary LED blinks, the sibling counter advances, and WL55 CPU2 is released by
the M4's `__pre_init` (`PWR_CR4=0x8000`). ESP32CAM has no Rust stack. The build
half of every cell is in `docs/e2e-evidence.md` (10/10).

## Sources

- `tickets/ops-020-clean-test-doc/ticket.md` + `docs/vscode-debug.md` §9 — F411RE, H755ZI-Q.
- `tickets/ops-027-wl55-clean-run/ticket.md` — WL55JC.
- `tickets/ops-023-e2e-matrix/ticket.md` + `docs/e2e-evidence.md` — the build half.
- `tickets/spike-008-rust-flash-run/ticket.md` — Rust scope.
