# Proposal

## Why

The generated C/C++ Makefile cannot build a project-owned translation unit.
`engine/templates/renderer.py:486-487` defines `SRCS_$core = src/main-$core.c`
but never uses it; `OBJS_$core` hardcodes only `main`, `startup`, and `system`.
Any extra source is silently ignored.

Consequence: an application that needs a C++ TU for a C++ library (or any
second C file) must hand-edit the generated Makefile. The current
`wl55jc/Makefile` does exactly that (adds `src/app.cpp`, `build/M4/app.o`, and a
rule). `mu create` regenerates the Makefile from the template, so the edit is
lost on the next render.

The vector-table half already works: ST's vendored startup declares weak IRQ
aliases, and a strong `extern "C" void EXTI0_IRQHandler(void)` overrides them
(the vector word at `0x08000058` points at the strong handler, not
`Default_Handler`). The only missing piece is compiling and linking the project
source.

Evidence: investigation (2026-10-20) pristine render + `src/app.cpp` ->
`undefined reference to app_init`;
`engine/templates/renderer.py:486-487`;
`Vendor/.../startup_stm32wl55xx_cm4.s:154,266-267`.
Verify: render a project, add `src/app.cpp`, call it from `main-M4.c`, build.

## What Changes

- Generated C/C++ Makefiles get an opt-in, project-owned source hook:
  - `-include config/sources.mk` (optional file, never generated/overwritten);
  - `EXTRA_SRCS_<core>` per core, added to `SRCS_<core>`;
  - `OBJS_<core>` derives from `SRCS_<core>` (no wildcard, no cross-core leakage);
  - pattern rules `build/<core>/%.o: src/%.c` (`$(CC)`) and
    `build/<core>/%.o: src/%.cpp` (`$(CXX)`);
  - `CXXFLAGS_<core>` for C-stack projects that add a `.cpp`;
  - link driver `$(CXX)` when the core's sources contain a `.cpp`
    (the `cpp` stack keeps `$(CXX)`).
- The generated README documents the hook.
- Tests cover the hook, per-core isolation, and a real build with a `.cpp` TU.

## Capabilities

### Modified Capabilities

- `template-generation`: generated Makefiles build per-core project-owned
  sources from `config/sources.mk`; generated README documents it.

## Impact

- `engine/templates/renderer.py` (`_MAKEFILE_HEAD`, `_MAKEFILE_CORE`, `_readme`).
- `engine/templates/tests/test_renderer.py` (new tests).
- Generated project README output.
- No pack-schema change.

**Out of scope:** the WL55 `CORE_CM0PLUS` M0+ IRQ-name define (separate
ticket), wildcard discovery, sources outside `src/`, generating or overwriting
`config/sources.mk`, Rust/ESP-IDF families, and regenerating the consumer
`wl55jc` project.

Verify: `uv run pytest engine -q`; `uv run openspec validate
req-031-project-sources`.
