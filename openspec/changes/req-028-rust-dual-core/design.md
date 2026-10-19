# Design

## Context

See `proposal.md`. The domain already has the facts: `Device.cores`,
`Device.memory` with per-core tags, `DeviceFacets.example_led`, `cpu2_boot`,
`openocd.targets`, `svd`, `probe_settings`. The C++ family already consumes all
of them; the Rust family does not. The problem is duplication and a monolith,
not missing device facts.

## Goals / Non-Goals

**Goals:** one plan shared by C++ and Rust; a registry of template families;
Rust dual-core parity on WL55JC and H755; single-core Rust preserved; existing
outputs unchanged.

**Non-Goals:** Embassy/HAL, radio/LoRa, ESP32CAM Rust, H755 live proof,
replacing the C++ Makefile or OpenOCD flash path.

## Decisions

- **D1 — `ProjectPlan` is the single source of truth.**
  `engine/core/plan.py` derives:
  `CorePlan` (name, slug, arch, flash/ram, example, release writes, openocd
  target, svd), `SiblingPlan` (attach facts), `FlashPlan` (piece order, session
  mode, boot-check core), `DebugPlan` (attach-only, per-core processor ids),
  `ConfigPlan`, `ProbePlan`. Families consume it; they never re-read `Device`
  semantics.
  Evidence: the C++ branch duplicates this logic today
  (`renderer.py:1103-1128,1613-1660`).
- **D2 — `TemplateFamily` is a port + registry.**
  `emit(plan, options) -> list[Path]`; `register_template_family(id, family)`.
  `render()` resolves the stack then dispatches. Mirrors `StackSpec` and
  `register_build_cell` (AD-1).
- **D3 — Rust dual layout: one package per core + generated Makefile.**
  Cargo cannot select two `--target`s in one invocation. A Makefile is the
  existing mu build pattern (C++), keeps task names uniform, and each core is
  still a normal crate (`cd m4 && cargo build`). Phase 0 built exactly this
  layout in `lang-rust:1.99.0`.
  Evidence: Phase 0 build; `cargo-xtask`/Embassy patterns were investigated but
  add an orchestration layer without improving the generated project.
- **D4 — CPU2 release is `#[no_mangle] extern "C" fn __pre_init()`.**
  `#[pre_init]` is deprecated in `cortex-m-rt` 0.7.7. The hand-written function
  is called by `Reset` before `.data`/`.bss` init; it uses only raw register
  addresses (no statics). Generated from `CorePlan.release_writes` (the pack's
  `example.cpu2_boot` triples).
  Evidence: Phase 0 `nm`/`readelf` + live `PWR_CR4=0x8000`.
- **D5 — Flash on OpenOCD, debug on probe-rs.**
  The generated Makefile keeps the proven sibling-first OpenOCD flash with the
  `bug-027` verify-and-retry tail. `--vscode` emits `probe-rs-debug` with
  `coreConfigs` (per-core `programBinary`/`svdFile`, `request: attach` for
  `cpu2_boot` packs, `flashingEnabled: false`, `preLaunchTask: Flash`), because
  the Rust image has no GDB and probe-rs is already present.
  Evidence: GDB absence in `lang-rust:1.99.0`; `probe-rs chip info` cores
  `cm4`/`cm0p`; Phase 0 live flash/retry.
- **D6 — Dev profile `opt-level = "s"`, `flip-link` wired.**
  `opt-level = 0` makes the NOP blink delay several seconds; `s` restores the
  visible blink (C++ uses `-Os`). `flip-link` is currently declared but unused;
  wiring it via `[target.<triple>] linker = "flip-link"` was validated.
  Evidence: Phase 0 ODR samples.
- **D7 — Rust image adds `thumbv6m-none-eabi`.**
  The M0+ target is not installed. Runtime `rustup target add` built the M0+
  ELF; the image must carry it.
- **D8 — Fix `mu flash` for `cpu2_boot`.**
  Current argv emits `targets stm32wlx.cpu1` without `DUAL_CORE` and checks the
  wrong core. For `cpu2_boot` packs, flash pieces single-core, sibling-first,
  and boot-check the primary. The same `FlashPlan` feeds this and the Makefile.

## Risks / Trade-offs

- **Byte-identical refactor risk.** Mitigation: characterization tests render
  every existing (pack, lang) before/after; the refactor lands first without
  behavior change.
- **Makefile in Rust.** Trade-off accepted for exact parity and because Cargo
  cannot multi-target; each package remains independently buildable.
- **probe-rs-debug attachment on WL55.** Phase 0 validated OpenOCD and
  `probe-rs chip info`; live VS Code attach is a remaining hardware check.
- **`__pre_init` constraints.** No statics; generated code uses only literals +
  volatile accesses. A test asserts the emitted function body.

## Verification plan

- Unit: `pytest -k plan`, `-k families`, `-k characterization`.
- Render: WL55/H755/F411RE rust file lists, per-core `memory.x` origins,
  `__pre_init` body, Makefile targets, `launch.json` `coreConfigs`.
- Parity: same `ProjectPlan` for C++ and Rust (cores, regions, targets,
  release, flash order).
- Build: `mu build` for WL55 + H755 in `lang-rust:1.99.0`; two ELFs each.
- Live WL55: flash M0+ then M4, `Verified OK` x2; `PWR_CR4=0x8000`; M0+ counter
  advances; PB15 toggles.
- `make test`, `openspec validate req-028-rust-dual-core`.

## Open Questions

- H755 live proof is build/e2e only (board not attached).
- probe-rs-debug VS Code attach on WL55 is checked live in Phase 0 follow-up.
