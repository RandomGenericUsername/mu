# Proposal

## Why

req-032 added a C++ entry point but kept it at `src/main-<core>.<ext>`. The
per-core directories were only for extra sources, so a generated project looks
like:

```text
src/main-M4.cpp
src/main-M0+.cpp
src/M4/          (empty)
src/M0+/         (empty)
```

The reference layout puts the entry point inside the core directory:

```text
src/M4/main.cpp
src/M0+/main.cpp
```

Evidence: current `wl55jc` tree; `renderer.py` still writes
`src/main-<core>.<ext>` and `SRCS_<core>` names it explicitly.
Verify: `find src -maxdepth 2 -name 'main.*'` in a generated project.

## What Changes

- The renderer writes `src/<core>/main.<ext>` and no root-level main.
- `SRCS_<core>` uses the per-core main and filters it out of the wildcard (no
  duplicate object).
- `--lang cpp` keeps `.cpp` + `$(CXX)`; `--lang c` keeps `.c` + `$(CC)`.
- README/table and three-pack tests updated.
- No change to req-032 library flags or req-031 extra-source hook.

## Capabilities

### Modified Capabilities

- `template-generation`: per-core entry point path for generated C/C++ projects.

## Impact

- `engine/templates/renderer.py` (`_MAKEFILE_CORE`, main rendering, `_readme`).
- Renderer tests and three-pack build matrix.
- Generated project tree.
- No pack-schema change; no `stm32-hw` change.

**Out of scope:** library flags (req-032), moving application/docs, board code,
Rust/ESP-IDF.

Verify: three-pack `mu create` + `find src` + `mu build`;
`uv run pytest engine -q`; `uv run openspec validate req-033-per-core-main`.
