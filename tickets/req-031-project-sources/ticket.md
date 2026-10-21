---
id: req-031
title: "Per-core project-owned sources in generated Makefiles"
kind: requirement
status: in-progress
size: S
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-031-project-sources
  bmad: []
worktree: .worktrees/req-031/
branch: ticket/req-031-project-sources
---

# Per-core project-owned sources in generated Makefiles

## Requirement

The generated C/C++ Makefile currently builds only `src/main-<core>.c`, the
vendored startup, and the system file. A project-owned second translation unit
(e.g. `src/app.cpp` holding an `extern "C" EXTI0_IRQHandler`) is silently
ignored, so the link fails with an undefined reference or the handler never
reaches the vector table.

The generated Makefile SHALL compile per-core project-owned sources declared in
an optional, project-owned `config/sources.mk` via `EXTRA_SRCS_<core>`, using
`$(CC)` for `.c` and `$(CXX)` for `.cpp`, and SHALL link with `$(CXX)` when the
core's sources contain a `.cpp` file. Per-core variables SHALL NOT leak between
cores. The hook SHALL be opt-in: with no `config/sources.mk`, the generated
output keeps its current shape (main + startup + system only).

## Acceptance

- [ ] Generated Makefiles contain `-include config/sources.mk` and
      `EXTRA_SRCS_<core> ?=`; `SRCS_<core>` drives `OBJS_<core>`.
      `Verify: rg -n "sources.mk|EXTRA_SRCS_|SRCS_M4|OBJS_M4" <render>/Makefile`
- [ ] A rendered C project with `config/sources.mk` containing
      `EXTRA_SRCS_M4 = src/app.cpp` builds `src/app.cpp` with `$(CXX)` and links
      with `$(CXX)`; the ELF contains the app symbol.
      `Verify: make build-M4 && arm-none-eabi-nm build/M4/*.elf | grep app_`
- [ ] On a dual-core pack, `EXTRA_SRCS_M4` does not add objects to `M0+` and
      vice versa. `Verify: make -pRrq -f Makefile : | grep '^OBJS_'`
- [ ] With no `config/sources.mk`, existing rendered projects build unchanged.
      `Verify: uv run pytest engine -q`
- [ ] The generated README documents the `config/sources.mk` hook.
      `Verify: rg -n "config/sources.mk" <render>/README.md`
- [ ] `openspec validate req-031-project-sources` exits 0.
- [ ] `uv run pytest engine -q` is green.

## Evidence

- Investigation (2026-10-20): a pristine render has
  `SRCS_$core = src/main-$core.c` but `OBJS_$core` hardcodes main/startup/system
  (`engine/templates/renderer.py:486-487`). Adding `src/app.cpp` and calling it
  from `src/main-M4.c` fails with `undefined reference to app_init`.
- The current `wl55jc` project works only because its Makefile was hand-edited
  to add `src/app.cpp` + `app.o` (non-durable; `mu create` regenerates the file
  from the 137-line template).
- Strong `extern "C"` handlers override ST's weak aliases correctly once the TU
  is linked: vector word at `0x08000058` (`EXTI0_IRQn = 6`) points at
  `EXTI0_IRQHandler`, not `Default_Handler`
  (`vendor/cmsis-device-stm32wl55jc/Source/Templates/gcc/startup_stm32wl55xx_cm4.s:154,266-267`).
- Out of scope: `CORE_CM0PLUS` pack define for M0+ IRQ names (separate ticket);
  wildcard source discovery; sources outside `src/`; generating/overwriting
  `config/sources.mk`; Rust/ESP-IDF template families.
