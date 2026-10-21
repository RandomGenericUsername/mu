# Proposal

## Why

A mu-generated C/C++ project cannot add a source file without hand-editing the
generated Makefile. The template hardcodes one application source:

```python
# engine/templates/renderer.py:486-487
"SRCS_$core = src/main-$core.c\n"
"OBJS_$core = build/$core/main-$core.o build/$core/startup-$core.o build/$core/system-$core.o\n"
```

Consequences:

- the current `wl55jc/Makefile` is hand-edited for `src/main-M4.cpp` and
  `third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp`;
- `mu create` regenerates the file and loses those edits;
- the reference projects used per-core source directories with wildcard
  discovery, but mu's C/C++ template never carried that over.

The fix must also cover library-owned compiled sources, which live outside the
project's `src/` tree (example: the ADC ISR in `stm32-hw`).

Evidence: `engine/templates/renderer.py:486-487`;
`wl55jc/Makefile:27-53`; user statement about the reference convention.
Verify: render a project, add `src/M4/foo.cpp`, run `make build-M4` — it is
ignored/undefined today.

## What Changes

- Per-core project source discovery:
  - `src/<core>/**/*.c`, `src/<core>/**/*.cpp`
  - `src/common/**/*.c`, `src/common/**/*.cpp`
  - plus the existing `src/main-<core>.c` / `.cpp`
  - no global `src/*` glob (dual-core packs must not leak sources)
- `SRCS_<core>` drives `OBJS_<core>`; pattern rules compile `.c` with `$(CC)`
  and `.cpp` with `$(CXX)`.
- Link with `$(CXX)` when the core's source list contains a `.cpp`; otherwise
  keep the stack's compiler.
- Optional project-owned `config/sources.mk` with `EXTRA_SRCS_<core>` for
  library/unusual sources; included with `-include` and never generated.
- Generated README documents both mechanisms.
- Tests cover F411RE (M4), H755 (M7+M4), WL55 (M4+M0+).

## Capabilities

### Modified Capabilities

- `template-generation`: generated C/C++ Makefiles discover per-core project
  sources and optional extra/library sources.

## Impact

- `engine/templates/renderer.py` (`_MAKEFILE_HEAD`, `_MAKEFILE_CORE`,
  `_readme`).
- `engine/templates/tests/test_renderer.py` and/or new tests.
- `engine/verify/e2e.py` (three-board build cells) if the e2e harness is the
  right place for the cross-pack proof.
- Generated project README and Makefile.
- No pack-schema change.

**Out of scope:** changing the `stm32-hw` library, board-specific code, moving
generated main files into per-core directories, Rust/ESP-IDF families.

Verify: `uv run pytest engine -q`;
`mu create --mcu-config stm32f411re|stm32h755|stm32wl55jc --lang cpp …`;
`mu build --project-dir …`; `uv run openspec validate req-031-project-sources`.
