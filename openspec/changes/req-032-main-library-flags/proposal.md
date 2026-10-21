# Proposal

## Why

req-031 made generated Makefiles discover `src/<core>/` and `src/common/`, and
added `config/sources.mk` for extra sources. Two gaps remain before a real
library can be consumed:

1. **No include/flags hook.** `config/sources.mk` is included before
   `CFLAGS_<core>`/`CXXFLAGS_<core>` are defined. There is no
   `EXTRA_INC_<core>` variable. The generated README recommends
   `EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp`, but the
   build fails with `stm32/drivers/wl55.hpp: No such file or directory` until
   the user hand-edits the Makefile.

2. **No C++ main.** `--lang cpp` renders `src/main-<core>.c`; the `.c` pattern
   compiles with `$(CC)`. A user cannot put the entry point in
   `src/<core>/main.cpp` without colliding with the generated `main`.

Evidence: independent req-031 test of generated F411RE/H755/WL55 projects
(2026-10-21); generated `wl55-regen` Makefile includes `config/sources.mk` at
line 16 and `CXXFLAGS_M4` without any extra include. After a manual
`-Ithird_party/stm32-hw/include`, the ADC ISR links strongly and the vector
entry is correct.
Verify: render a WL55 cpp project, add the library include and ISR via
`config/sources.mk`, run `mu build` — fails before this change, builds after.

## What Changes

- `config/sources.mk` gains per-core flags:
  ```make
  EXTRA_INC_<core>      = -Ithird_party/stm32-hw/include
  EXTRA_CFLAGS_<core>   =
  EXTRA_CXXFLAGS_<core> =
  ```
  `EXTRA_INC` is added to both C and C++ compiles; the other two are
  suffix-specific. All are applied after the base flags.
- `--lang cpp` renders `src/main-<core>.cpp` and compiles/links it as C++;
  `--lang c` keeps `src/main-<core>.c` and `$(CC)`.
- The generated README documents both.
- The three-pack proof recipe uses forced symbol references or object checks so
  `--gc-sections` does not hide failures.

## Capabilities

### Modified Capabilities

- `template-generation`: per-core extra include/flags from `config/sources.mk`;
  C++ entry point for `--lang cpp`.

## Impact

- `engine/templates/renderer.py` (`_MAKEFILE_HEAD`, `_MAKEFILE_CORE`,
  `_readme`, main rendering).
- Renderer tests + three-pack build matrix.
- Generated project README/Makefile.
- No pack-schema change; no `stm32-hw` change.

**Out of scope:** moving main into `src/<core>/`, board code, Rust/ESP-IDF
families.

Verify: `uv run pytest engine -q`; three-pack `mu create` + `mu build` with
`stm32-hw` at tag `adc-driver-isr`; `uv run openspec validate
req-032-main-library-flags`.
