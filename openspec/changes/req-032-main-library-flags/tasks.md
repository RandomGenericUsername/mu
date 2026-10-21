# Tasks

## 1. Planning

- [x] 1.1 Ticket + OpenSpec change for library flags and C++ main.
      Verify: `openspec validate req-032-main-library-flags`; index guard.

## 2. Renderer

- [x] 2.1 Add `EXTRA_INC_<core>`, `EXTRA_CFLAGS_<core>`,
      `EXTRA_CXXFLAGS_<core>` to `_MAKEFILE_CORE`; apply after base flags.
      Verify: `make -n build-M4` shows `EXTRA_INC`.
- [x] 2.2 Render `src/main-<core>.cpp` for `--lang cpp`, `.c` for `--lang c`;
      use the same extension in `SRCS_<core>` and the compile rule.
      Verify: render and inspect the Makefile/source tree.
- [x] 2.3 Update `_readme` with `EXTRA_INC` and the C++ main behavior.
      Verify: rendered README contains both.

## 3. Tests

- [x] 3.1 Renderer unit tests: cpp main path, C main path, extra flags
      placement, link driver, no-op without config.
      Verify: `uv run pytest engine/templates/tests/test_project_sources.py -q`.
- [x] 3.2 Three-pack real-library matrix:
      - F411RE cpp, H755 c, WL55 cpp;
      - add `stm32-hw` at tag `adc-driver-isr`;
      - `EXTRA_SRCS_<core>` = family ISR, `EXTRA_INC_<core>` = library include;
      - call driver init from the generated main;
      - build and assert strong `ADC_IRQHandler`, vector, link drivers,
        isolation.
      Exact recipe: ticket `## Three-board test recipe`.
- [x] 3.3 Regression: existing C projects, `uv run pytest engine -q`.

## 4. Close

- [ ] 4.1 Update README/INDEX, tick acceptance, merge the ticket branch, close.
      Verify: `openspec validate` + merge commit.
      Status: acceptance ticked and verification recorded on the branch; merge
      to `main` intentionally not performed by the implementation agent (the
      handoff rule is "never work on main").
