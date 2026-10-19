# Tasks

## 1. Domain plan (behavior-preserving)

- [x] 1.1 Add `engine/core/plan.py`: `CorePlan`, `SiblingPlan`, `FlashPlan`,
      `DebugPlan`, `ProjectPlan`, `build_plan(device)`.
      Verify: `pytest -k plan`.
- [x] 1.2 Characterization tests: render every `(pack, lang)` before the
      refactor and assert byte-identical output after.
      Verify: `pytest -k characterization`.

## 2. Template family port

- [x] 2.1 Add `engine/templates/ports.py` (`TemplateFamily`,
      `register_template_family`, `family_for`) and a registry.
      Verify: `pytest -k families`.
- [x] 2.2 Move the existing C/C++ and ESP-IDF branches into
      `families/c_cmsis.py` / `families/idf_cmake.py`, consuming `ProjectPlan`;
      keep output byte-identical. Verify: characterization tests.
- [x] 2.3 Keep the single-core Rust family in `families/rust_cortex.py`.
      Verify: F411RE/H755/WL55 single-core render tests.

## 3. Rust dual family

- [x] 3.1 Add `families/rust_cortex_dual.py`: per-core packages
      (`Cargo.toml`, `.cargo/config.toml`, `build.rs`, `memory.x`,
      `src/main.rs`), `opt-level = "s"`, wired `flip-link`.
      Verify: render file list + `readelf` origins.
- [x] 3.2 Primary PB15 blink + sibling counter from `CorePlan`.
      Verify: generated source greps + live ODR.
- [x] 3.3 `#[no_mangle] __pre_init()` from `CorePlan.release_writes`.
      Verify: generated body + live `PWR_CR4=0x8000`.
- [x] 3.4 Generated Makefile: `build`, `build-<core>`, `flash`, `flash-<core>`,
      `clean`, `debug-<sibling>`; sibling-first order; boot-check tail.
      Verify: `make build` + live `make flash`.
- [x] 3.5 `--vscode`: `probe-rs-debug` `coreConfigs` with per-core
      `programBinary`/`svdFile`, attach-only for `cpu2_boot`, `preLaunchTask`.
      Verify: JSON + live attach.

## 4. Stack, packs, image

- [x] 4.1 Add `cargo-cortex-dual` `StackSpec` (`make build`, Rust image).
      Verify: `mu build --dry-run`.
- [x] 4.2 Map `stm32wl55jc` and `stm32h755` to `cargo-cortex-dual`.
      Verify: pack tests.
- [x] 4.3 Add `thumbv6m-none-eabi` to `images/rust.Dockerfile`; rebuild and
      record the digest. Verify: `rustup target list --installed`.

## 5. Flash parity + verification

- [x] 5.1 `FlashPlan` drives `make flash` and `mu flash`; fix `cpu2_boot`
      single-core, sibling-first, primary boot-check. Verify: argv tests.
- [x] 5.2 Dual Rust e2e cell: build both ELFs, per-core `memory.x`, size check.
      Verify: `python -m engine.verify.e2e --only stm32wl55jc,stm32h755`.
- [x] 5.3 Parity test: C++ and Rust plans agree on cores, regions, targets,
      release, flash order. Verify: `pytest -k parity`.
- [x] 5.4 Live WL55 proof: flash M0+ then M4, `PWR_CR4`, counter, PB15.
      Verify: `docs/flash-run-evidence.md`.
- [x] 5.5 Update README/docs/index/ticket; `make test` + `openspec validate`.
      Verify: both green.
