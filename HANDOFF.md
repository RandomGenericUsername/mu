# Handoff — mu (2026-10-13)

Continue here with another agent. Read this whole file first, then
`AGENTS.md` (repo contract), then `tickets/INDEX.md` (work board).

## What this is

Greenfield unified STM32 dev environment (C/C++/Rust), replacing two stale
2023–2024 sibling repos (`../ArmDevelopmentEnvironment`,
`../rust-embedded-environment` — lessons only, never copy blindly).
Hexagonal Python engine (`engine/`), YAML hardware packs (`packs/`),
thin CLI verbs (`mu`), probe adapters, per-toolchain OCI images
(`images/`), Jinja-free templates. Specs: `openspec/specs/`
(ticket-system, task-router, worktree-discipline). Design: brief + spec +
spine under `_bmad-output/initiative-universal-mcu-env/`.

## How work happens here (non-negotiable)

- **Evidence rule** (`AGENTS.md` §1): every technical claim carries
  `Evidence:` (path:lines, SHA, URL+quote, or command+output) and a
  one-command `Verify:`. No air. Reproduce others' claims before trusting.
- **Tickets** (`tickets/`): all work starts as a ticket (kinds: epic,
  requirement, bug, ops-task, spike, task). `INDEX.md` is the board —
  keep it current; recount rollups from files, never mental math.
- **Git discipline**: never work on main; `scripts/worktree-guard.sh create
  <id> <slug>` scaffolds `ticket/<id>-<slug>` + worktree, aborts on dirty
  main. Merge with `--no-ff`, push, remove worktree, delete branch.
- **Tests**: `make test` (228 green at handoff) is the merge gate. Unit
  green ≠ done: live proofs (container builds, readelf-vs-pack checks)
  caught every real defect so far.
- Subagents execute; the orchestrator verifies (re-runs their commands),
  commits, merges, pushes. Fix drift on sight, including theirs.

## State at handoff (main @ see log, all pushed, tree clean)

- Epic-001: **31/31 children done** (`ops-029`). The done-when caveat recorded
  here ("no probe has ever touched silicon") is **superseded**: live
  flash/run is proven for the V1 packs — `ops-027`, `ops-028`,
  `docs/flash-run-evidence.md`.
- 191→228 tests green. Images built+smoked (cpp:15.3.rel2, rust:1.99.0).
- `mu create/build` proven live to ELF (F411RE C; Rust F411RE+H755 to ARM
  ELF32). 9/9 cells compile; 5/5 C ELFs from real vendor trees.
- Open threads: Windows lane; H755 dual-core boot semantics (HW decides);
  linker_for fallback already removed.
  **Resolved since this handoff:** warnings policy (done — `ops-033`: warn-only,
  stated once in `docs/warnings-policy.md`); registry visibility (done —
  `ops-034`: GHCR packages stay PRIVATE/auth-required); HW flash/run (done —
  `ops-027`, `ops-028`, `docs/flash-run-evidence.md`); CubeCLT verdict (done —
  `req-027`: exclude from images, optional host tool; SLA0048 permits
  redistribution with conditions, not a prohibition); IDE attach (done —
  `req-016`, `docs/vscode-debug.md`); registry push (done — `ops-030`, images
  on GHCR).
- Known machine quirk (dev box): Docker Desktop shares `/tmp` but NOT
  `~/Desktop` — mounts fail with `mkdir /host_mnt/...: operation not
  permitted`. Run docker-backed verification from `/tmp` clones there.

## Pinned facts (verified, do not re-derive)

- ARM GNU 15.3.rel2 (new gitlab host; old developer.arm.com URL dead).
- Rust 1.99.0, probe-rs 0.32.0, flip-link 0.1.12, cargo-generate 0.25.0.
- ST OpenOCD fork `openocd-cubeide-r7` @ `c8d973b`, tag v0.12.0.
- Correct OpenOCD targets: F411RE `stlink + st_nucleo_f4`; H755
  `stlink-dap + st_nucleo_h745zi` + DUAL_CORE (HLA can't do multicore);
  WL55JC `stlink + stm32wlx` + DUAL_CORE (HLA single-core flash only).
- Sibling bugs confirmed present: H755-M4 `stm32f4x.cfg` in checked-in
  example; WL55JC wrong targets in `mcu-configs/*.yml`; swapped
  interface/target prompts in Rust `cargo-generate.toml`.
- Templates: `panic = "abort"` required in Rust profiles; `_sidata` +
  `SystemInit` + device defines (`STM32F411xE`, `STM32H755xx` +
  `CORE_CM7/CM4`, `STM32WL55xx`) all pack-declared; CMSIS include is
  `vendor/CMSIS/CMSIS/Core/Include` (nested!); cmsis_device repos ship
  NO linker scripts (generated from pack maps).

## Tonight's mission (flash on Linux)

Full procedure: `docs/flash-stm32-linux.md` (udev without relogin,
tty access, per-board commands, common failures). Save ALL output —
success or failure both come back as evidence (open a bug ticket for
any failure with repro/observed/expected).
