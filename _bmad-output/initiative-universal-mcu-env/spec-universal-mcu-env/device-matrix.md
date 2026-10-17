# device-matrix

Day-one shippable matrix. Each C/C++ cell must complete create → build → flash → observable proof from a clean machine; each Rust cell must complete create → build to a flashable ELF (build-parity).

> **Amended 2026-10-17 — see `tickets/spike-008-rust-flash-run/ticket.md`.** This originally read "Each cell must complete create → build → flash → observable proof". The V1 scope was narrowed on 2026-10-16 (decision option c): the flash/run + observable-proof gate rests on the **C/C++** cells; **Rust** cells are **build-to-ELF parity** only, because the generated example is a bare `wfi` loop with no observable output (Rust's live flash/run works via `probe-rs` but certifies no proof — `docs/flash-run-evidence.md` §"Scope note").

| Pack (board) | Cores | C | C++ | Rust | Probe backends shipped |
|---|---|---|---|---|---|
| Nucleo-F411RE (stm32f411re) | cortex-m4 | yes | yes | yes | openocd (`stlink.cfg` + `stm32f4x.cfg`) |
| Nucleo-H755ZI-Q (stm32h755) | cortex-m7 + cortex-m4 | yes | yes | yes | openocd (per-core cfgs; M4 target under review — sibling used `stm32f4x.cfg`, suspect) |
| Nucleo-WL55JC (stm32wl55jc) | cortex-m4 + cortex-m4 | yes | yes | yes | openocd (targets under review — sibling cfgs suspect, see source brief lineage) |
| ESP32-CAM (esp32cam) — first non-STM32, post-V1 | xtensa-lx6 (dual-core) | yes (`idf-cmake`) | — | — | esptool (UART, no probe; `0x1000`/`0x8000`/`0x10000`) |

Notes:
- Sibling reference: `mcu-configs/*.yml` field shapes (target, per-core core/architecture/memory/openocd) carry over; exact openocd targets re-verified per pack before V1.
- Proof ritual per pack: LED, RTT, or UART output — declared in each pack, pending Open Question resolution.
- Languages beyond C/C++/Rust and vendors beyond STM32 are later packs against the same engine; matrix grows, engine does not change. The ESP32 row is the first proof of that claim (CAP-7): it must land with zero `engine/core` diffs (AD-1). But it is **not** a drop-in — the post-development needs it surfaced (a build-stack axis, programming-only devices, non-CMSIS templates, a third verify stack) mean the engine must first be *generalised* (R1–R6), after which the ESP32 family is a pure addition. A family that cannot be added without core diffs is evidence the engine needs improving, not that the family should be special-cased (AD-1).
