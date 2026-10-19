# Proposal

## Why

The renderer is a 1,700-line module with per-family `if/elif` branches. The
C++ branch iterates `device.cores` (per-core sources, linkers, flash order,
CPU2 release, sibling attach, VS Code/SVD); the Rust branch takes
`pack_model.cores[0]` and emits one `wfi` image. Result: H755 builds only the
M7, WL55JC builds only the M4 (no M0+, no release), and even F411RE Rust has no
LED example or debug integration.

The fix must be reusable and extensible, not a second Rust branch bolted into
the monolith. The repo already has the right patterns: registry-based stacks
(`StackSpec`), build cells (`register_build_cell`), a model-only renderer, and
adapter ports. This change extracts the shared **plan** (domain) and makes
template families **ports/adapters** over it.

## What Changes

- New domain `ProjectPlan` in `engine/core/plan.py`, derived once from `Device`:
  per-core regions/arch/example/release writes/openocd target/svd, sibling
  attach facts, flash order, debug facts.
- New `TemplateFamily` port + registry in `engine/templates/`; `render()` becomes
  a thin dispatcher. Existing families move to `families/` modules.
- New `rust-cortex-dual` family (bare metal, no Embassy/HAL):
  - one cargo package per core (`m4/`, `m0plus/`), per-core `.cargo/config.toml`,
    `build.rs`, `memory.x`, `src/main.rs`;
  - PB15 blink on the primary; watchable counter on the sibling;
  - `#[no_mangle] extern "C" fn __pre_init()` CPU2 release (not the deprecated
    `#[pre_init]`), with `opt-level = "s"` dev profile and wired `flip-link`;
  - generated Makefile with C++-shaped targets and sibling-first flash + boot
    retry;
  - `probe-rs-debug` `coreConfigs` with per-core `programBinary`/`svdFile` for
    `--vscode`; flash stays on OpenOCD (proven retry path).
- New stack `cargo-cortex-dual`; `stm32wl55jc` and `stm32h755` declare it.
- Rust image adds `thumbv6m-none-eabi`.
- `FlashPlan` is shared by the generated Makefile and `mu flash`; the current
  `cpu2_boot` flash argv bug is fixed (single-core, sibling-first, no
  `DUAL_CORE`/per-core targets).

## Capabilities

### Modified Capabilities

- `template-generation`: plan-driven families; Rust dual-core projects;
  per-core artifacts; probe-rs debug configs.
- `pack-schema`: packs may declare `cargo-cortex-dual` for Rust.

## Impact

- Code: `engine/core/plan.py` (new), `engine/core/model.py` (view additions if
  needed), `engine/templates/renderer.py` + `families/`, `engine/adapters/
  toolchain/__init__.py`, `engine/adapters/openocd.py`, `engine/verify/e2e.py`,
  `images/rust.Dockerfile`, packs, tests.
- **Out of scope:** ESP32CAM Rust (no stack declared), Embassy/HAL, radio/LoRa
  stacks, H755 live proof (build/e2e only), non-ST families.

Evidence: Phase 0 live results in `tickets/req-028-rust-dual-core/ticket.md`.
Verify: `make test`; `mu create --mcu-config stm32wl55jc --lang rust …`;
`openspec validate req-028-rust-dual-core`.
