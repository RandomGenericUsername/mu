# Design

## Context

See `proposal.md`. req-032 generates `src/main-<core>.<ext>` and `SRCS_<core>`
names it. The per-core directories exist (`src/M4`, `src/M0+`, `src/M7`) but
only collect extra sources. The reference layout has the entry point in the
core directory.

## Goals / Non-Goals

**Goals:** `src/<core>/main.<ext>`; no root main; one main object; C/C++
compiler behavior preserved; three packs build.

**Non-Goals:** req-032 flags, docs, app code, Rust/ESP-IDF.

## Decisions

- **D1 — Path.** Generate `src/<core>/main.<ext>`:
  - cpp → `main.cpp`, compiled/linked with `$(CXX)`
  - c → `main.c`, compiled with `$(CC)`
  - no `src/main-<core>.<ext>`.

- **D2 — No duplicate main.** `SRCS_<core>` lists the per-core main explicitly
  and filters it out of the wildcard:
  ```make
  MAIN_<core> = src/<core>/main.<ext>
  SRCS_<core> = $(MAIN_<core>) \
                $(filter-out $(MAIN_<core>), $(call rwildcard,src/<core>/,*.c)) \
                $(filter-out $(MAIN_<core>), $(call rwildcard,src/<core>/,*.cpp)) \
                $(call rwildcard,src/common/,*.c) \
                $(call rwildcard,src/common/,*.cpp) \
                $(EXTRA_SRCS_<core>)
  ```
  This keeps one main object even when `extra.cpp` is added.

- **D3 — C/C++ behavior.** Reuse req-032: `.c` → `$(CC)`, `.cpp` → `$(CXX)`,
  conditional `$(CXX)` link when a core has a C++ source.

- **D4 — Regeneration.** New projects only get the per-core main. Existing
  projects may have a stale root main; `mu create` into a fresh tree avoids it.
  Document the layout in the README.

- **D5 — Tests.** Three-pack render/build matrix checks `find src`, no root
  `main-*`, one main object, extra source coexistence.

## Risks / Trade-offs

- **Duplicate object** if the wildcard is not filtered; D2 handles it.
- **Old projects** with a hand-written root main are not automatically migrated;
  the ticket keeps migration out of scope.
- **C++ main on M0+/M4 sibling** must stay valid C++ (req-032 body is).
- **Empty-dir tracking** in git is a project concern (`.gitkeep`), not the
  renderer.

## Verification plan

1. Render F411RE cpp, H755 c, WL55 cpp; `find src -maxdepth 2 -name 'main.*'`;
   assert no `src/main-*`.
2. Build all three with `mu build`.
3. Add `src/M4/extra.cpp` to WL55; build; assert one `main.o` and one
   `extra.o` under `build/M4`.
4. `uv run pytest engine -q`; `uv run openspec validate req-033-per-core-main`.

## Handoff

- Worktree/branch: `.worktrees/req-033/`, `ticket/req-033-per-core-main`.
- Exact three-board recipe in the ticket.
- Do not hand-edit generated project Makefiles as the fix.
