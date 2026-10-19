# mu

One CLI from zero to a running program on supported MCUs: scaffold projects
from prebuilt hardware packs (or your own config), hack in a containerized
dev environment, and build/flash from a bare host with zero toolchain setup.

Day-one packs: Nucleo-F411RE, Nucleo-H755ZI-Q, Nucleo-WL55JC — in C, C++,
Rust. Linux/macOS hosts. Windows: deferred lane.

## Install (host prerequisites: Git, Docker, `python3 >= 3.11`, `uv`)

```sh
git clone https://github.com/RandomGenericUsername/mu.git
cd mu
make sync      # Python env (uv, locked)
make test      # engine suite, no Docker needed
make images    # build cpp + rust toolchain images (needs Docker + network)
make smoke     # version probes inside both images
make install   # install the `mu` CLI globally (editable uv tool → ~/.local/bin/mu)
```

`make install` runs `uv tool install --editable .`, so `mu` is on your PATH
(`~/.local/bin`) with no venv activation — and it tracks your checkout live.
Remove it with `make uninstall`. Without it, use `uv run mu …` from this
checkout instead.

## Quickstart

```sh
# Scaffold (works offline after clone; needs git + network for CMSIS submodules)
uv run mu create --mcu-config stm32f411re --lang c --name demo --path .
# Build transparently in the pinned toolchain image (no host toolchain needed)
uv run mu build --project-dir ./demo
# Inspect what any command will do without running it
uv run mu build --project-dir ./demo --dry-run
# Interactive dev shell in the same image
uv run mu dev
```

`mu create --help` lists packs (`stm32f411re`, `stm32h755`, `stm32wl55jc`),
languages (`c`, `cpp`, `rust`), and the `--config` escape hatch for your own
device files (one source per invocation: `--mcu-config` XOR `--mcu`).

## Flashing (needs a probe + board)

```sh
uv run mu flash --mcu-config stm32f411re --project-dir ./demo \
  --vid 0483 --pid 3752 --files build/M4/stm32f411re-M4.elf
```

Per-board OpenOCD configs ship in each generated project (`probe/openocd.cfg`,
verified against the ST OpenOCD fork). Flash/run is proven live on
NUCLEO-F411RE and NUCLEO-H755ZI-Q (dual core) — see `tickets/` for the per-item
evidence.

## Debugging in VS Code

`mu create --vscode` + `mu dev` + *Dev Containers: Attach to Running Container*
gives tasks (build/flash) and launch configs (per-core, plus a compound
dual-core one), a peripheral register view from the pinned SVD, and probe
selection by serial. Full walkthrough, expected behaviour, and troubleshooting:
[`docs/vscode-debug.md`](docs/vscode-debug.md).

## Repo map

- `engine/` — hexagonal core: model, packs loader, thin CLI verbs, probe
  adapters, templates, verify harness. `make test` runs the suite.
- `packs/` — the three STM32 device packs (validated YAML).
- `images/` — pinned toolchain Dockerfiles + build/smoke/push commands.
- `docs/` — user-facing how-tos (`vscode-debug.md`, `flash-stm32-linux.md`).
- `tickets/` — the work index (`INDEX.md` board, per-kind lifecycles).
- `openspec/` + `_bmad-output/` — specs, proposals, brief, spec, architecture.

## Status

Active development toward V1 (create → build → flash → run per matrix cell).
`make test` green is the merge gate; every technical claim in planning
artifacts carries evidence per `AGENTS.md`.

Rust dual-core (WL55JC/H755) is at C++ parity for **bare-metal bring-up**
(per-core images, CPU2 release, LED/counter, flash/debug); single-core Rust
remains build-to-ELF parity. See `tickets/req-028-rust-dual-core/`.
