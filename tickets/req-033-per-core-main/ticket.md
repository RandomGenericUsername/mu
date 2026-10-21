---
id: req-033
title: "Per-core main files in generated C/C++ projects"
kind: requirement
status: in-progress
size: S
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-033-per-core-main
  bmad: []
worktree: .worktrees/req-033/
branch: ticket/req-033-per-core-main
---

# Per-core main files in generated C/C++ projects

## Handoff

Work in this worktree/branch:

```text
worktree: .worktrees/req-033/
branch:   ticket/req-033-per-core-main
change:   openspec/changes/req-033-per-core-main
```

Read `AGENTS.md`, `tickets/LIFECYCLE.md`, and the change artifacts first. Do not
work on `main`. Keep planning and implementation commits separate.

## Problem

req-032 added a native C++ entry point but left it at the top-level path:

```text
src/main-M4.cpp
src/main-M0+.cpp
```

The per-core directories (`src/M4/`, `src/M0+/`) only collect extra sources.
This is the wrong shape: the reference layout puts the entry point inside each
core directory.

Current generated Makefile:

```make
SRCS_M4 = src/main-M4.cpp \
          $(call rwildcard,src/M4/,*.c) ...
```

Expected:

```text
src/M4/main.cpp
src/M0+/main.cpp
src/common/...
```

Evidence: current `wl55jc` tree (2026-10-21) has `src/main-M4.cpp` and
`src/main-M0+.cpp` at the root and empty `src/M4/` / `src/M0+/` directories.
`engine/templates/renderer.py` still writes `src/main-<core>.<ext>`.

## Requirement

A generated project SHALL place the entry point in the core directory:

```text
src/<core>/main.cpp   (--lang cpp)
src/<core>/main.c     (--lang c)
```

It SHALL NOT generate `src/main-<core>.cpp` / `.c` at the `src/` root.

`SRCS_<core>` SHALL include exactly one main object, with no duplicate when the
wildcard also scans `src/<core>/`. C++ mains compile/link with `$(CXX)`; C mains
with `$(CC)`. Extra sources in `src/<core>/` and `src/common/` keep working.

## Acceptance

- [ ] F411RE cpp renders `src/M4/main.cpp`; no `src/main-M4.cpp`; builds.
      `Verify: find src -maxdepth 2 -name 'main.*'; mu build`
- [ ] H755 c renders `src/M7/main.c` and `src/M4/main.c`; no root mains;
      builds both cores.
      `Verify: find src -maxdepth 2 -name 'main.*'; mu build`
- [ ] WL55 cpp renders `src/M4/main.cpp` and `src/M0+/main.cpp`; no root
      mains; builds both cores.
      `Verify: find src -maxdepth 2 -name 'main.*'; mu build`
- [ ] Adding `src/M4/extra.cpp` does not duplicate the main object.
      `Verify: make -pRrq -f Makefile : | grep 'src/M4/main'`
- [ ] Generated README shows `src/<core>/main.<ext>`.
      `Verify: rg -n "src/<core>/main|src/main-<core>" <render>/README.md`
- [ ] `uv run pytest engine -q` green;
      `uv run openspec validate req-033-per-core-main` exits 0.

## Three-board recipe

```sh
mkdir -p /tmp/req033
cd /home/inumaki/Development/mu/.worktrees/req-033

uv run mu create --name f411 --mcu-config stm32f411re --lang cpp --path /tmp/req033
uv run mu create --name h755 --mcu-config stm32h755 --lang c --path /tmp/req033
uv run mu create --name wl55 --mcu-config stm32wl55jc --lang cpp --path /tmp/req033

for p in f411 h755 wl55; do
  echo "--- $p ---"
  find /tmp/req033/$p/src -maxdepth 2 -name 'main.*' | sort
  ! find /tmp/req033/$p/src -maxdepth 1 -name 'main-*' | grep .
done

uv run mu build --project-dir /tmp/req033/f411
uv run mu build --project-dir /tmp/req033/h755
uv run mu build --project-dir /tmp/req033/wl55
```

Expected main files:

```text
f411: src/M4/main.cpp
h755: src/M7/main.c, src/M4/main.c
wl55: src/M4/main.cpp, src/M0+/main.cpp
```

Add an extra source to WL55 and rebuild:

```sh
echo 'extern "C" int req033_extra(){return 3;}' \
  > /tmp/req033/wl55/src/M4/extra.cpp
uv run mu build --project-dir /tmp/req033/wl55
find /tmp/req033/wl55/build/M4 -name 'main.o' -o -name 'extra.o'
```

## Evidence

- `engine/templates/renderer.py` writes `src/main-<core>.<ext>` and
  `SRCS_<core>` names that path explicitly (req-032).
- The per-core dirs exist but are empty in the current `wl55jc`.
- The reference layout uses `src/<core>/main.<ext>` (user statement).

## Out of scope

- Library include flags (req-032, already implemented).
- Moving docs or application code.
- Board wiring.
- Rust/ESP-IDF families.
