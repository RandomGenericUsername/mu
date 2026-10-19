# Spec Delta

## Purpose

Template families emit from one domain plan; Rust produces the same per-core
bring-up as C++ on dual-core packs.

## ADDED Requirements

### Requirement: Rust dual-core projects are per-core

`mu create --lang rust` on a pack declaring `cargo-cortex-dual` SHALL emit one
cargo package per core, each with its own `Cargo.toml`,
`.cargo/config.toml` (`target = <core.arch>`), `build.rs`, `memory.x`
(that core's flash/RAM only), and `src/main.rs`.

Evidence: Phase 0 built `m4` + `m0plus` in `lang-rust:1.99.0`; vectors at
`0x08000000`/`0x08020000`.
Verify: `mu create --mcu-config stm32wl55jc --lang rust … && find`.

#### Scenario: WL55JC

- **WHEN** `stm32wl55jc` renders with `--lang rust`
- **THEN** `m4/` links at `0x08000000`/48K RAM and `m0plus/` at
  `0x08020000`/16K RAM

#### Scenario: H755

- **WHEN** `stm32h755` renders with `--lang rust`
- **THEN** `m7/` links at `0x08000000`/512K AXI RAM and `m4/` at
  `0x08100000`/288K D2 RAM

#### Scenario: single-core preserved

- **WHEN** `stm32f411re` renders with `--lang rust`
- **THEN** the existing single-package project is emitted

### Requirement: CPU2 release is emitted on the primary

When the pack declares `example.cpu2_boot`, the primary core SHALL emit a
`#[no_mangle] extern "C" fn __pre_init()` performing the pack's masked writes
before `main`.

Evidence: `cortex-m-rt` 0.7.7 deprecates `#[pre_init]`; Phase 0 live
`PWR_CR4=0x8000` and `SRRVR=0xfeff8000`.
Verify: generated source grep + live readback.

#### Scenario: WL55JC primary releases CPU2

- **WHEN** `stm32wl55jc` renders with `--lang rust`
- **THEN** the M4 source contains `__pre_init` with the pack's `SBRV` and
  `C2BOOT` writes

### Requirement: Rust dual projects have runnable examples

The primary SHALL blink the pack LED using `example.led` raw registers; the
sibling SHALL run a watchable counter. The dev profile SHALL use
`opt-level = "s"` so the delay is visible.

Evidence: Phase 0 ODR toggles; `opt-level = 0` was several seconds slow.
Verify: live ODR samples.

#### Scenario: primary blinks, sibling counts

- **WHEN** the generated WL55JC project runs
- **THEN** `GPIOB_ODR` toggles PB15 and the M0+ counter advances

### Requirement: Rust dual projects build and flash all cores

A generated Makefile SHALL provide `build`, `build-<core>`, `flash`,
`flash-<core>`, `clean`, and `debug-<sibling>`; `flash` SHALL program the
sibling first when `cpu2_boot` is declared, and SHALL append the shared boot
verify-and-retry tail.

Evidence: Phase 0 sibling-first OpenOCD flash, `Verified OK` x2, retry needed.
Verify: `make build`; `make flash`; `mu build --project-dir …`.

#### Scenario: build all cores

- **WHEN** `mu build` runs on a generated dual Rust project
- **THEN** both `build/<core>/<project>-<core>.elf` images exist

#### Scenario: sibling-first flash

- **WHEN** `make flash` runs on a `cpu2_boot` pack
- **THEN** the M0+ image is programmed before the M4 image

### Requirement: Rust debug uses probe-rs-debug

`--vscode` on a Rust dual project SHALL emit `probe-rs-debug` with `coreConfigs`
(per-core `coreIndex`, `programBinary`, `svdFile`); `cpu2_boot` packs SHALL use
`request: attach`, `flashingEnabled: false`, and `preLaunchTask: Flash`.

Evidence: Rust image has no GDB; `probe-rs chip info` cores `cm4`/`cm0p`.
Verify: `grep coreConfigs .vscode/launch.json` + live attach.

#### Scenario: per-core configs

- **WHEN** `stm32wl55jc` renders with `--lang rust --vscode`
- **THEN** `launch.json` contains `coreConfigs` for M4 (`coreIndex 0`) and M0+
  (`coreIndex 1`) with their SVDs

### Requirement: Plan parity

C++ and Rust SHALL consume the same `ProjectPlan` facts: core names,
per-core flash/RAM origins+lengths, OpenOCD targets, release writes, and flash
order.

Evidence: current C++/Rust divergence (`renderer.py:1661-1686`).
Verify: `pytest -k parity`.

#### Scenario: same plan for both languages

- **WHEN** the same pack renders as C++ and as Rust
- **THEN** both `ProjectPlan`s carry the same cores, regions, OpenOCD targets,
  release writes, and flash order
