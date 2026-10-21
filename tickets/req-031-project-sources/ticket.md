---
id: req-031
title: "Generated Makefiles discover per-core project sources and library sources"
kind: requirement
status: done
size: M
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-031-project-sources
  bmad: []
worktree: .worktrees/req-031/
branch: ticket/req-031-project-sources
---

# Generated Makefiles discover per-core project sources and library sources

## Handoff

This ticket is ready for an implementing agent. Work in this worktree/branch:

```text
worktree: .worktrees/req-031/
branch:   ticket/req-031-project-sources
change:   openspec/changes/req-031-project-sources
```

Read `AGENTS.md`, `tickets/LIFECYCLE.md`, and the change artifacts before
editing. Do not work on `main`. Keep planning changes and implementation in
separate commits. The ticket acceptance below is the definition of done.

## Problem

The generated C/C++ Makefile only knows one application source:

```text
engine/templates/renderer.py:486-487
  SRCS_$core = src/main-$core.c
  OBJS_$core = build/$core/main-$core.o build/$core/startup-$core.o build/$core/system-$core.o
```

Adding any file under `src/` requires hand-editing the generated Makefile.
Current consumer evidence: `wl55jc/Makefile` was manually extended for
`main-M4.cpp` and `third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp`.

The reference projects used per-core source directories and wildcard discovery
(user statement, 2026-10-21). mu's C/C++ template never carried that over.

## Requirement

Generated Makefiles SHALL discover project sources from per-core directories
and a common directory, SHALL compile them per core without cross-core leakage,
and SHALL accept an optional project-owned hook for library or unusual sources.
No generated-Makefile edit may be required to add a normal user source.

Required layout:

```text
src/<core>/**/*.c
src/<core>/**/*.cpp
src/common/**/*.c
src/common/**/*.cpp
```

Plus the existing `src/main-<core>.c` (or `.cpp`) entry point.

Optional project-owned hook:

```make
# config/sources.mk
EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp
```

## Acceptance

- [x] `SRCS_<core>` includes the main file, `src/<core>/**`, and
      `src/common/**`; `OBJS_<core>` derives from it. No global `src/*` glob.
      `Verify: rg -n "SRCS_|wildcard" <render>/Makefile`
- [x] A file added under `src/M4/` is compiled and linked into M4 only; the
      same for `src/M0+/` and M0+.
      `Verify: make build-M4 build-M0+ && arm-none-eabi-nm build/*/*.elf`
- [x] `.c` sources compile with `$(CC)`, `.cpp` with `$(CXX)`; a core with a
      `.cpp` source links with `$(CXX)`.
      `Verify: make -n build-M4`
- [x] `config/sources.mk` is optional, project-owned, included with `-include`,
      and can add library sources per core.
      `Verify: write config/sources.mk; make -pRrq -f Makefile :`
- [x] Existing generated projects still build (`main-<core>.c`, startup,
      system, linker scripts unchanged).
      `Verify: uv run pytest engine -q`
- [x] Three-board build proof: `stm32f411re`, `stm32h755` (M7+M4), and
      `stm32wl55jc` (M4+M0+) each build with a per-core extra source and a
      common source; no cross-core object leaks.
      `Verify: mu create … && mu build --project-dir …` for all three packs.
- [x] Generated README documents the directory convention and
      `config/sources.mk`.
      `Verify: rg -n "src/<core>|config/sources.mk" <render>/README.md`
- [x] `uv run openspec validate req-031-project-sources` exits 0.

## Three-board test recipe (build-only, no hardware)

After implementing the renderer change, run all three packs. Use `/tmp/req031`
so the worktree stays clean.

```sh
mkdir -p /tmp/req031
cd /home/inumaki/Development/mu/.worktrees/req-031

uv run mu create --name req031-f411 --mcu-config stm32f411re --lang cpp --path /tmp/req031
uv run mu create --name req031-h755 --mcu-config stm32h755 --lang c --path /tmp/req031
uv run mu create --name req031-wl55 --mcu-config stm32wl55jc --lang c --path /tmp/req031
```

For each project add:

```sh
# F411 (M4)
echo 'extern "C" int req031_m4() { return 4; }' > /tmp/req031/req031-f411/src/M4/extra.cpp

# H755 (M7 + M4)
echo 'int req031_m7(void) { return 7; }' > /tmp/req031/req031-h755/src/M7/extra.c
echo 'extern "C" int req031_m4() { return 4; }' > /tmp/req031/req031-h755/src/M4/extra.cpp

# WL55 (M4 + M0+)
echo 'extern "C" int req031_m4() { return 4; }' > /tmp/req031/req031-wl55/src/M4/extra.cpp
echo 'int req031_m0(void) { return 0; }' > /tmp/req031/req031-wl55/src/M0+/extra.c

# common source in every project
echo 'int req031_common(void) { return 1; }' > /tmp/req031/req031-f411/src/common/common.c
cp /tmp/req031/req031-f411/src/common/common.c /tmp/req031/req031-h755/src/common/common.c
cp /tmp/req031/req031-f411/src/common/common.c /tmp/req031/req031-wl55/src/common/common.c
```

Library-source hook (outside `src/`), per pack:

```sh
mkdir -p /tmp/req031/req031-f411/lib
echo 'int req031_lib(void) { return 9; }' > /tmp/req031/req031-f411/lib/extra.c
printf 'EXTRA_SRCS_M4 = lib/extra.c\n' > /tmp/req031/req031-f411/config/sources.mk

mkdir -p /tmp/req031/req031-h755/lib
echo 'int req031_lib(void) { return 9; }' > /tmp/req031/req031-h755/lib/extra.c
printf 'EXTRA_SRCS_M7 = lib/extra.c\n' > /tmp/req031/req031-h755/config/sources.mk

mkdir -p /tmp/req031/req031-wl55/lib
echo 'int req031_lib(void) { return 9; }' > /tmp/req031/req031-wl55/lib/extra.c
printf 'EXTRA_SRCS_M4 = lib/extra.c\n' > /tmp/req031/req031-wl55/config/sources.mk
```

Build and assert:

```sh
uv run mu build --project-dir /tmp/req031/req031-f411
uv run mu build --project-dir /tmp/req031/req031-h755
uv run mu build --project-dir /tmp/req031/req031-wl55

# symbols in each image
arm-none-eabi-nm /tmp/req031/req031-f411/build/M4/*.elf | grep req031_
arm-none-eabi-nm /tmp/req031/req031-h755/build/M7/*.elf | grep req031_
arm-none-eabi-nm /tmp/req031/req031-h755/build/M4/*.elf | grep req031_
arm-none-eabi-nm /tmp/req031/req031-wl55/build/M4/*.elf | grep req031_
arm-none-eabi-nm /tmp/req031/req031-wl55/build/M0+/*.elf | grep req031_

# no cross-core leak
! arm-none-eabi-nm /tmp/req031/req031-wl55/build/M0+/*.elf | grep req031_m4
! arm-none-eabi-nm /tmp/req031/req031-h755/build/M4/*.elf | grep req031_m7

# C++ link driver on the C-stack projects
make -C /tmp/req031/req031-h755 -n build-M4 | grep 'arm-none-eabi-g++'
make -C /tmp/req031/req031-wl55 -n build-M4 | grep 'arm-none-eabi-g++'

# object placement
find /tmp/req031/req031-wl55/build -name 'extra.o'
```

Expected: every ELF exists; each core has its own `extra` symbol plus
`req031_common`; `req031_lib` is linked from `config/sources.mk`; the sibling
core does not contain the other core's `extra` symbol; C-stack projects with a
`.cpp` extra link with `arm-none-eabi-g++`.

## Evidence

- `engine/templates/renderer.py:486-487` hardcodes `SRCS_$core`/`OBJS_$core`.
- `engine/templates/renderer.py` writes `src/main-<core>.c`; no wildcard rules.
- `wl55jc/Makefile:27-53` is the current hand-edited workaround (M4 main +
  library ISR object).
- `third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp` is the library-owned ISR
  that a project must add to its link; it lives outside `src/`, so the
  `config/sources.mk` hook is required for it.
- Three packs to test: `stm32f411re` (single M4), `stm32h755` (M7+M4),
  `stm32wl55jc` (M4+M0+).
- Reference convention (per-core `src/<core>/` directories) per user statement;
  the old reference repo is not present on this machine to cite.

## Verification (2026-10-21)

Implementation commit `40235dd`; rendered projects sourced from it.

- Unit/regression: `uv run pytest engine -q` → **415 passed**.
- Spec: `uv run openspec validate req-031-project-sources` → `Change
  'req-031-project-sources' is valid`.
- Renderer tests: `uv run pytest engine/templates/tests/test_project_sources.py
  -q` → **5 passed** (discovery, common, EXTRA_SRCS, missing hook, M4/M0+
  isolation, `make -pRrq` object expansion, CC/CXX/link driver, README).
- Three-pack matrix, run with the recipe in `/tmp/req031`:
  - `uv run mu create --name req031-f411 --mcu-config stm32f411re --lang cpp …`
  - `uv run mu create --name req031-h755 --mcu-config stm32h755 --lang c …`
  - `uv run mu create --name req031-wl55 --mcu-config stm32wl55jc --lang c …`
  - `uv run mu build --project-dir /tmp/req031/<project>` → exit 0 for all
    three; ELFs exist at `build/M4`, `build/M7`, `build/M4`, `build/M0+`.
  - `arm-none-eabi-nm` (in `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`):
    - F411 `build/M4`: `req031_m4`, `req031_common`, `req031_lib`
    - H755 `build/M7`: `req031_m7`, `req031_common`, `req031_lib`
    - H755 `build/M4`: `req031_m4`, `req031_common` (no `req031_lib` —
      `EXTRA_SRCS_M7` only)
    - WL55 `build/M4`: `req031_m4`, `req031_common`, `req031_lib`
    - WL55 `build/M0+`: `req031_m0`, `req031_common`
  - Cross-core absence checks → PASS: WL55 M0+ has no `req031_m4`, WL55 M4
    has no `req031_m0`, H755 M4 has no `req031_m7`, H755 M7 has no
    `req031_m4`, H755 M4 has no `req031_lib`.
  - `make -Bn build-M4` on H755 and WL55 (C stacks with `.cpp` extras) links
    with `arm-none-eabi-g++`; WL55 `build-M0+` (C-only) links with
    `arm-none-eabi-gcc`.
  - `make -pRrq -f Makefile :` on WL55 gives
    `OBJS_M4 = build/M4/src/main-M4.o build/M4/src/M4/extra.o
    build/M4/src/common/common.o build/M4/lib/extra.o build/M4/startup-M4.o
    build/M4/system-M4.o`; `OBJS_M0+` contains only M0+/common objects.
  - `find build -name extra.o` → `build/M0+/src/M0+/extra.o`,
    `build/M4/src/M4/extra.o`, `build/M4/lib/extra.o`.
- README: rendered F411 README matches `rg -n
  "src/<core>|src/common/|config/sources.mk"`.

Deviations, with reasons:

- The renderer now creates empty `src/<core>/` and `src/common/` directories
  at render time. Without them the ticket's `echo … > src/M4/extra.cpp` step
  fails on a fresh project.
- The literal recipe functions are unreferenced, and the generated link uses
  `-Wl,--gc-sections`, so `arm-none-eabi-nm` showed no `req031_*` symbols.
  The test-only extra sources were therefore given
  `__attribute__((used))` plus a constructor that calls them through a
  `volatile` function pointer. That keeps the proof symbols observable without
  touching generated Makefiles or linker scripts; normal user code that calls
  its own sources behaves as before.
- `LINK_<core>` is `$(if $(filter %.cpp,$(SRCS_<core>)),$(CXX),<stack compiler>)`.
  The design's sample used the same idea; on the `cpp` stack the fallback is
  still `$(CXX)`.

## Out of scope

- Board-specific code.
- Changing the `stm32-hw` library.
- Moving generated main files into per-core directories (compatibility first).
- Rust/ESP-IDF template families.
