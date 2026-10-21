# Design

## Context

See `proposal.md`. The generated Makefile owns the object list; the renderer
hardcodes `main`, `startup`, and `system` (`renderer.py:486-487`). The
reference project layout used per-core source directories, but the mu C/C++
template does not. The current consumer project works only because its Makefile
was hand-extended.

## Goals / Non-Goals

**Goals:** per-core discovery; common sources; opt-in library-source hook;
no cross-core leakage; `.c`/`.cpp` compiler selection; C++ link driver; all
three packs build; generated project remains buildable without hand edits.

**Non-Goals:** moving main files into per-core directories; changing packs;
Rust/ESP-IDF templates; hardware/driver code.

## Decisions

- **D1 — Per-core directories are the primary mechanism.**
  `src/<core>/` and `src/common/` are globbed per core. This matches the
  reference convention and avoids the dual-core contamination of a single
  `src/*` glob.

- **D2 — Keep the existing main entry point.**
  Continue to render `src/main-<core>.c` (or `.cpp`) and add wildcard discovery
  beside it. Moving main into `src/<core>/` is a later layout change; not needed
  to fix the workflow, and it would churn every generated project.

- **D3 — `SRCS_<core>` drives `OBJS_<core>`.**
  Derive objects from the source list with `patsubst`; keep startup/system as
  explicit objects. This removes the hardcoded object list.

- **D4 — Suffix-based compiler selection.**
  `.c` uses `$(CC) $(CFLAGS_<core>)`; `.cpp` uses
  `$(CXX) $(CXXFLAGS_<core>)`. `CXXFLAGS_<core>` defaults to
  `CFLAGS_<core> -std=c++17 -fno-exceptions -fno-rtti` on the C stack;
  the `cpp` stack already carries the C++ flags.

- **D5 — Conditional link driver.**
  `LINK_<core> = $(if $(filter %.cpp,$(SRCS_<core>)),$(CXX),<compiler>)`.
  A C stack with a `.cpp` extra links with `$(CXX)`; C-only projects keep
  `$(CC)`; the `cpp` stack keeps `$(CXX)`.

- **D6 — `config/sources.mk` is the escape hatch for library sources.**
  `-include config/sources.mk`; `EXTRA_SRCS_<core>` is added to
  `SRCS_<core>`. The file is project-owned and never emitted/overwritten.
  Example: `EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp`.

- **D7 — Documentation is part of the contract.**
  The generated README names `src/<core>/`, `src/common/`, and
  `config/sources.mk`; otherwise users fall back to editing the Makefile.

- **D8 — Render the source roots.**
  `mu create` creates `src/<core>/` and `src/common/` so the documented
  drop-in paths exist immediately. The directories stay empty until the user
  adds sources (git does not track them).

## Makefile shape

```make
-include config/sources.mk

# recursive wildcard (GNU make's ** is one segment)
rwildcard = $(foreach d,$(wildcard $(1)*),$(call rwildcard,$(d)/,$(2))\
             $(filter $(subst *,%,$(2)),$(d)))

# per core:
EXTRA_SRCS_$core ?=
SRCS_$core = src/main-$core.c \
             $(call rwildcard,src/$core/,*.c) \
             $(call rwildcard,src/$core/,*.cpp) \
             $(call rwildcard,src/common/,*.c) \
             $(call rwildcard,src/common/,*.cpp) \
             $(EXTRA_SRCS_$core)
OBJS_$core := $(patsubst %.cpp,build/$core/%.o, \
              $(patsubst %.c,build/$core/%.o,$(SRCS_$core))) \
              build/$core/startup-$core.o build/$core/system-$core.o
LINK_$core = $(if $(filter %.cpp,$(SRCS_$core)),$(CXX),<stack compiler>)
```

Objects mirror the full source path under `build/<core>/` (for example
`src/M4/a.c` → `build/M4/src/M4/a.o`, `lib/extra.c` →
`build/M4/lib/extra.o`), so every source maps to exactly one object, including
library sources outside `src/`.

## Risks / Trade-offs

- **Dual-core contamination:** a global `src/*` glob is forbidden; only
  `src/<core>/` and `src/common/`.
- **Basename collisions:** two sources with the same stem map to the same
  object. Document the limitation or include relative subpaths in the object
  name.
- **C++ link driver:** linking a C stack with `$(CXX)` may pull libstdc++ if the
  TU uses runtime features. The C++ stack already does this; the build tests
  cover the intended no-runtime case.
- **Library sources outside `src/`:** the `config/sources.mk` hook is required;
  a wildcard alone cannot find them.
- **Generated-file churn:** the Makefile text changes for every project;
  update characterization tests deliberately rather than pinning old bytes.
- **`M0+` in Make variables:** the core name contains `+`; existing generated
  files already use `CFLAGS_M0+`, so keep the same convention.

## Verification plan

1. Unit renderer tests:
   - hook lines and wildcard per core;
   - no `src/*` global wildcard;
   - `make -pRrq` object expansion with `src/M4/app.cpp`,
     `src/common/util.c`, and `EXTRA_SRCS_M4`;
   - M4/M0+ isolation.
2. Build matrix (no hardware required):
   - `stm32f411re` C and C++ projects;
   - `stm32h755` M7+M4;
   - `stm32wl55jc` M4+M0+;
   - add `src/<core>/extra.cpp`, `src/common/common.c`, and a library source via
     `config/sources.mk`; `mu build --project-dir …`; assert all ELFs and
     object placement.
3. Regression: `uv run pytest engine -q`; existing e2e cells.
4. Spec: `uv run openspec validate req-031-project-sources`.

## Handoff notes

- Worktree/branch: `.worktrees/req-031/`, `ticket/req-031-project-sources`.
- Do not hand-edit generated project Makefiles as the fix; change the renderer
  and tests.
- Keep planning and implementation commits separate.
- The consumer `wl55jc` is a useful manual check but not the source of truth;
  the three packs above are.
