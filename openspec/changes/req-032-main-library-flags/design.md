# Design

## Context

See `proposal.md`. req-031 added `-include config/sources.mk`, per-core
`SRCS_<core>`, and suffix rules. The include sits in `_MAKEFILE_HEAD`, before
the core `CFLAGS` definitions, so a project cannot add `-I` for a library from
the config file. The C/C++ family also always renders `src/main-<core>.c`;
the `.c` rule always uses `$(CC)`.

## Goals / Non-Goals

**Goals:** per-core extra include paths and flags; C++ main for `--lang cpp`;
C behavior unchanged; real library integration proven on F411RE/H755/WL55.

**Non-Goals:** moving main into `src/<core>/`; changing packs; library code;
Rust/ESP-IDF.

## Decisions

- **D1 — `EXTRA_INC_<core>`, `EXTRA_CFLAGS_<core>`,
  `EXTRA_CXXFLAGS_<core>` are the hook.**
  All are optional and set from `config/sources.mk`. `EXTRA_INC` is applied to
  both C and C++ compiles; `EXTRA_CFLAGS` only to C; `EXTRA_CXXFLAGS` only to
  C++. The config include can stay where it is because the core variables are
  recursively expanded after it.

- **D2 — Apply extras after the base flags.**
  ```make
  CFLAGS_<core>   = <base> $(EXTRA_INC_<core>) $(EXTRA_CFLAGS_<core>)
  CXXFLAGS_<core> = $(CFLAGS_<core>) <cxx flags> $(EXTRA_CXXFLAGS_<core>)
  ```
  `EXTRA_INC` is placed before source-specific flags so a library include can
  be overridden by a project include if needed.

- **D3 — `--lang cpp` renders `src/main-<core>.cpp`.**
  The renderer emits the main with the language extension (`cpp` for the cpp
  stack, `c` for C), and `SRCS_<core>` uses the same extension. This removes
  the collision with `src/<core>/main.cpp` and lets the entry point contain
  C++ code. The generated C body is valid C++.

- **D4 — Keep C projects byte-shape compatible.**
  `--lang c` keeps `src/main-<core>.c`, `$(CC)`, and the existing object paths
  except for the req-031 per-core discovery.

- **D5 — Proof recipe must force references.**
  The three-pack test calls the extra/common/library functions from `main` or
  uses `--undefined`; `nm` on an ELF after `--gc-sections` is not enough.

## Makefile shape

```make
# head
-include config/sources.mk

# core
EXTRA_SRCS_<core>     ?=
EXTRA_INC_<core>      ?=
EXTRA_CFLAGS_<core>   ?=
EXTRA_CXXFLAGS_<core> ?=

CFLAGS_<core>   = <existing> $(EXTRA_INC_<core>) $(EXTRA_CFLAGS_<core>)
CXXFLAGS_<core> = $(CFLAGS_<core>) <cxx flags> $(EXTRA_CXXFLAGS_<core>)

SRCS_<core> = src/main-<core>.<ext> \
              $(call rwildcard,src/<core>/,*.c) \
              $(call rwildcard,src/<core>/,*.cpp) \
              $(call rwildcard,src/common/,*.c) \
              $(call rwildcard,src/common/,*.cpp) \
              $(EXTRA_SRCS_<core>)
```

The main extension `<ext>` is `cpp` for `--lang cpp`, `c` otherwise.

## Risks / Trade-offs

- **Breaking regeneration for cpp projects:** newly rendered projects use
  `main-<core>.cpp`; existing `main-<core>.c` is ignored after regeneration.
  Document it in the ticket/release note; this is a generated-tree change.
- **Flags from config can weaken the build:** `EXTRA_CFLAGS` is user-owned; keep
  it appended, not replacing base flags.
- **C++ main on M0+:** the WL55 M0+ main becomes `.cpp` and is compiled with
  `$(CXX)`; the `cargo`/C stack is unaffected. The generated body must stay
  standard C++ (it already uses raw C constructs).
- **Make include order:** `config/sources.mk` remains before core variables;
  only recursive (`=`) flags may reference its variables. Do not switch
  `CFLAGS`/`CXXFLAGS` to `:=`.
- **Library source paths:** `EXTRA_INC` is relative to the project root, like
  `EXTRA_SRCS`.

## Verification plan

1. Unit: render cpp/c projects; assert main extension, `SRCS`, `EXTRA_INC`,
   `EXTRA_CXXFLAGS`, link driver; `make -n` shows the include.
2. Real library: create F411RE cpp, H755 c, WL55 cpp; add
   `stm32-hw` submodule at tag `adc-driver-isr`; config `EXTRA_SRCS` +
   `EXTRA_INC` for the family ISR; call the driver init from the main; build.
3. Assertions: `ADC_IRQHandler` strong; WL55 vector `0x88` points at it;
   H755 M7 link `$(CC)`, M4 link `$(CXX)`; no cross-core leak.
4. Regression: `uv run pytest engine -q`;
   `uv run openspec validate req-032-main-library-flags`.

## Handoff

- Worktree/branch: `.worktrees/req-032/`, `ticket/req-032-main-library-flags`.
- Exact three-board recipe is in the ticket.
- Do not hand-edit generated project Makefiles as the fix.
