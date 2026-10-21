# Design

## Context

See `proposal.md`. The generated Makefile already names the vendor startup and
system objects and assembles them in place. The missing capability is a
project-owned source seam that survives regeneration. `mu create` owns the
Makefile (`engine/templates/renderer.py:475-526`), so hand edits are not a
contract.

## Goals / Non-Goals

**Goals:** per-core project sources; optional and durable opt-in; C and C++
sources; correct link driver; no behavior change when unused.

**Non-Goals:** wildcard source discovery; sources outside `src/`; generating
`config/sources.mk`; changing the startup/vector table; `CORE_CM0PLUS` for
M0+ IRQ names.

## Decisions

- **D1 — `config/sources.mk` is the durable seam.**
  The Makefile carries `-include config/sources.mk`. The file is project-owned
  and not emitted by the renderer, so regeneration cannot clobber it.
  Evidence: `mu create` rewrites generated files; the current `wl55jc/Makefile`
  hand edit proves the need.
- **D2 — `EXTRA_SRCS_<core>` is per core, and `OBJS_<core>` derives from
  `SRCS_<core>`.**
  No `src/*.c` wildcard: on a dual-core pack that would pull `main-M0+.c` into
  the M4 image. The existing `SRCS_<core>` variable becomes the single source
  list.
  Evidence: `renderer.py:486-487`; the dual-core `M0+` name and per-core flags.
- **D3 — Pattern rules only under `src/`.**
  `build/<core>/%.o: src/%.c` and `: src/%.cpp`. The explicit `main-<core>.o`
  rule stays and takes precedence. Sources outside `src/` are out of scope
  (the hook is for project code, not vendored trees).
- **D4 — Compiler per suffix.**
  `.c` uses `$(CC) $(CFLAGS_<core>)`; `.cpp` uses
  `$(CXX) $(CXXFLAGS_<core>)`; `CXXFLAGS_<core> = CFLAGS_<core> +
  -std=c++17 -fno-exceptions -fno-rtti` (idempotent on the `cpp` stack).
- **D5 — Link driver is conditional.**
  `LINK_<core> = $(if $(filter %.cpp,$(SRCS_<core>)),$(CXX),<compiler>)`;
  `<compiler>` is `$(CXX)` for the `cpp` stack and `$(CC)` for the C stack.
  This keeps C-only projects on `$(CC)` and avoids C++ runtime surprises.
- **D6 — Document the seam in the generated README.**
  A short "Adding project sources" section names `config/sources.mk` and the
  per-core variables, because the Makefile is generated and should not be
  edited by hand.

## Risks / Trade-offs

- **Make expansion:** `OBJS` uses nested `patsubst`; a source name collision
  between `.c`/`.cpp` with the same stem maps to the same object. Acceptable;
  document that object names follow the source stem.
- **C++ link driver on a C-stack project:** linking with `$(CXX)` may pull
  libstdc++ if the TU uses runtime features. The template already links `cpp`
  projects with `$(CXX)`, and the current app has no C++ runtime dependencies.
  The build test covers the intended case.
- **`config/sources.mk` is optional:** a missing file is silently ignored by
  `-include`; the README is the discoverability answer.
- **Generated Makefile text changes:** existing tests assert behavior, not a
  byte-identical Makefile; the full suite must stay green.

## Verification plan

- Unit: new renderer test asserts the hook lines, drives `make -pRrq` with a
  fake `config/sources.mk`, and checks `OBJS_<core>` per core (dual-core
  isolation).
- Build: render a C project, add `src/app.cpp` with an `extern "C"` symbol,
  run `make build-M4` in the pinned toolchain image, and confirm the symbol in
  the ELF (`arm-none-eabi-nm`).
- Regression: `uv run pytest engine -q`; the existing characterization/e2e
  cells.
- Spec: `uv run openspec validate req-031-project-sources`.

## Open Questions

- Whether the consumer `wl55jc` should be regenerated onto the hook in this
  ticket or after merge. Current decision: out of scope; it is already green
  with its hand edit.
- `CORE_CM0PLUS` for M0+ IRQ names remains a separate pack/ticket issue.
