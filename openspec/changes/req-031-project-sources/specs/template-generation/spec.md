# Spec Delta

## Purpose

Generated C/C++ projects can add project-owned source files without editing the
generated Makefile, and per-core builds stay isolated.

## ADDED Requirements

### Requirement: Generated Makefiles compile per-core project sources

A generated C/C++ Makefile SHALL include an optional, project-owned
`config/sources.mk` and SHALL compile every source listed in
`EXTRA_SRCS_<core>` for that core.

Evidence: `engine/templates/renderer.py:486-487` hardcodes `OBJS_$core`; the
`wl55jc` Makefile hand-edits it (repro: `undefined app_init`).

Verify: `make -pRrq -f Makefile :` shows `build/<core>/app.o` in
`OBJS_<core>` after adding `EXTRA_SRCS_<core> = src/app.cpp`.

#### Scenario: C++ TU in a C-stack project

- **WHEN** a C-stack project declares `EXTRA_SRCS_M4 = src/app.cpp` and calls
  the C-linkage function from `src/main-M4.c`
- **THEN** `build/M4/app.o` is built and the symbol is present in the image

#### Scenario: no project sources

- **WHEN** `config/sources.mk` is absent
- **THEN** `OBJS_<core>` contains only `main-<core>.o`, `startup-<core>.o`, and
  `system-<core>.o`

#### Scenario: per-core isolation

- **WHEN** a dual-core project sets `EXTRA_SRCS_M4` and `EXTRA_SRCS_M0+` to
  different files
- **THEN** `OBJS_M4` contains only the M4 extra object and `OBJS_M0+` only the
  M0+ extra object

### Requirement: Sources compile with their language's compiler

`.c` sources SHALL compile with `$(CC)` and `.cpp` sources with `$(CXX)`.

Evidence: the C++ stack already compiles every source with `$(CXX)`
(`engine/templates/renderer.py:432`); the C stack needs the suffix split only
for project-owned sources.

Verify: `make -n build-M4` shows `$(CC)` for `.c` and `$(CXX)` for `.cpp`.

#### Scenario: mixed sources

- **WHEN** a core lists both `.c` and `.cpp` sources
- **THEN** the `.c` objects are compiled with `$(CC)` and the `.cpp` objects
  with `$(CXX)`

### Requirement: Link driver follows the source language

A core SHALL link with `$(CXX)` when its source list contains a `.cpp` file;
otherwise it SHALL keep the stack's compiler (`$(CC)` for the C stack,
`$(CXX)` for the C++ stack).

Evidence: the `cpp` stack already links with `$(CXX)`
(`engine/templates/renderer.py:432`); a C stack with a `.cpp` extra needs the
same driver.

Verify: `make -pRrq -f Makefile :` shows `LINK_<core>` expanding to `$(CXX)`
with a `.cpp` extra and to `$(CC)` without one.

#### Scenario: C stack with a C++ TU

- **WHEN** `EXTRA_SRCS_M4` contains a `.cpp` file
- **THEN** the M4 link recipe uses `$(CXX)`

#### Scenario: C stack with only C sources

- **WHEN** `EXTRA_SRCS_M4` is empty or contains only `.c` files
- **THEN** the M4 link recipe uses `$(CC)`

### Requirement: The source hook is durable and documented

`config/sources.mk` SHALL be project-owned: the renderer SHALL NOT emit,
overwrite, or delete it. The generated README SHALL name the file, the
per-core `EXTRA_SRCS_<core>` variables, and the supported `src/` layout.

Evidence: `mu create` regenerates the Makefile from
`engine/templates/renderer.py`; the current consumer hand edit is lost on
regeneration.

Verify: `rg -n "config/sources.mk" <render>/README.md`; run `mu create` twice
and confirm a pre-existing `config/sources.mk` is untouched.

#### Scenario: regeneration preserves the file

- **WHEN** a project with `config/sources.mk` is rendered again
- **THEN** the file still exists with its original contents

#### Scenario: README documents the hook

- **WHEN** a C/C++ project is rendered
- **THEN** `README.md` names `config/sources.mk` and `EXTRA_SRCS_<core>`
