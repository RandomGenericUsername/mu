# Tasks

## 1. Planning

- [x] 1.1 Ticket + OpenSpec change with the per-core discovery requirement and
      the three-board test matrix.
      Verify: `openspec validate req-031-project-sources`; index guard test.

## 2. Renderer

- [ ] 2.1 `_MAKEFILE_HEAD`: add the optional `-include config/sources.mk` seam.
      Verify: rendered `Makefile` contains the include; a missing file is
      ignored.
- [ ] 2.2 `_MAKEFILE_CORE`: build `SRCS_<core>` from the main file,
      `src/<core>/**`, `src/common/**`, and `EXTRA_SRCS_<core>`; derive
      `OBJS_<core>`. No global `src/*` wildcard.
      Verify: `make -pRrq -f Makefile :` shows the expected objects.
- [ ] 2.3 Add suffix rules for `.c` (`$(CC)`) and `.cpp` (`$(CXX)`); add
      `CXXFLAGS_<core>` and conditional `LINK_<core>`.
      Verify: `make -n build-M4` on a C stack with a `.cpp` extra.
- [ ] 2.4 `_readme`: document `src/<core>/`, `src/common/`, and
      `config/sources.mk`.
      Verify: rendered `README.md` contains all three.

## 3. Tests

- [ ] 3.1 Renderer unit test: per-core discovery, common sources, extra source,
      object expansion, M4/M0+ isolation.
      Verify: `uv run pytest engine/templates/tests/test_renderer.py -q`.
- [ ] 3.2 Compile-only build check for a C-stack project with a `.cpp` extra;
      link driver is `$(CXX)`.
      Verify: `make build-M4` in the toolchain image.
- [ ] 3.3 Three-pack build matrix (build only; no hardware):
      - `stm32f411re` (M4)
      - `stm32h755` (M7 + M4)
      - `stm32wl55jc` (M4 + M0+)
      Add `src/<core>/extra.cpp`, `src/common/common.c`, and a library source
      via `config/sources.mk`; assert every expected ELF exists and objects
      stay in their core directory.
      Exact recipe: ticket `## Three-board test recipe`.
      Verify: `mu create … && mu build --project-dir …` for each pack.
- [ ] 3.4 Regression: existing generated projects still build; full suite.
      Verify: `uv run pytest engine -q`.

## 4. Close

- [ ] 4.1 Update README/docs, tick acceptance, update INDEX, merge the ticket
      branch, close. `Verify: openspec validate` + merge commit.
