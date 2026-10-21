# Tasks

## 1. Planning

- [x] 1.1 Create the ticket (lane 2, worktree/branch recorded) and the
      OpenSpec change. Verify: `openspec validate req-031-project-sources`.

## 2. Renderer

- [ ] 2.1 `_MAKEFILE_HEAD`: add the optional `-include config/sources.mk` seam.
      Verify: rendered `Makefile` contains the include and a missing file is
      ignored.
- [ ] 2.2 `_MAKEFILE_CORE`: add `EXTRA_SRCS_<core> ?=`, make `SRCS_<core>`
      drive `OBJS_<core>`, add `CXXFLAGS_<core>` and `LINK_<core>`, and the
      `src/%.c` / `src/%.cpp` pattern rules.
      Verify: `make -pRrq -f Makefile :` shows the expected `OBJS_<core>`.
- [ ] 2.3 `_readme`: document `config/sources.mk` and the per-core variable.
      Verify: rendered `README.md` contains the section.

## 3. Tests

- [ ] 3.1 Renderer unit test: hook lines present; no extra sources keeps the
      original three objects; `EXTRA_SRCS_M4` adds only `build/M4/...`.
      Verify: `uv run pytest engine/templates/tests/test_renderer.py -q`.
- [ ] 3.2 Dual-core isolation test: `EXTRA_SRCS_M4` does not affect `M0+` and
      vice versa. Verify: `make -pRrq` assertions.
- [ ] 3.3 Real build: rendered C project + `src/app.cpp` + `EXTRA_SRCS_M4`;
      `make build-M4` in the pinned image; `arm-none-eabi-nm` shows the symbol.
      Verify: command output recorded in the ticket.

## 4. Verification and close

- [ ] 4.1 `uv run pytest engine -q` green (all existing cells included).
- [ ] 4.2 `uv run openspec validate req-031-project-sources` exits 0.
- [ ] 4.3 Tick acceptance boxes, update INDEX status, merge the ticket branch,
      and close. Verify: `bash scripts/worktree-guard.sh --check-clean` on main
      plus the merge commit.
