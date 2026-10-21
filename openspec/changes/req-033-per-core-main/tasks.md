# Tasks

## 1. Planning

- [x] 1.1 Ticket + OpenSpec change for per-core main files.
      Verify: `openspec validate req-033-per-core-main`; index guard.

## 2. Renderer

- [x] 2.1 Write `src/<core>/main.<ext>` and stop writing
      `src/main-<core>.<ext>`.
      Verify: `find src -maxdepth 2 -name 'main.*'`.
      Status: three-pack render shows only `src/<core>/main.*`.
- [x] 2.2 `SRCS_<core>` uses the per-core main and filters it out of the
      wildcard (one main object).
      Verify: `make -pRrq -f Makefile :`.
      Status: `OBJS_M4` has one `main.o` with `src/M4/extra.cpp` present.
- [x] 2.3 Update `_readme` table/paths.
      Verify: `rg -n "src/<core>/main" <render>/README.md`.
      Status: rendered README documents `src/<core>/main.<ext>`.

## 3. Tests

- [x] 3.1 Renderer unit tests for C/C++ main paths and no root main.
      Verify: `uv run pytest engine/templates/tests -q`.
      Status: 111 template tests pass.
- [x] 3.2 Three-pack matrix: F411RE cpp, H755 c, WL55 cpp; `find src`,
      no root main, build all cores.
      Exact recipe: ticket `## Three-board recipe`.
      Status: built; paths/evidence recorded in the ticket.
- [x] 3.3 Extra-source coexistence on WL55: add `src/M4/extra.cpp`; build; one
      `main.o`, one `extra.o`.
      Status: `build/M4/src/M4/{main,extra}.o`, one each.
- [x] 3.4 Regression: `uv run pytest engine -q`.
      Status: 425 passed.

## 4. Close

- [ ] 4.1 Update README/INDEX, tick acceptance, merge/close.
      Verify: `openspec validate` + merge commit.
