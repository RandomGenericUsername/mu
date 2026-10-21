# Spec Delta

## Purpose

Generated C/C++ projects place the entry point inside each core directory, with
exactly one main object and no root-level main.

## ADDED Requirements

### Requirement: Per-core main file path

A generated project SHALL write `src/<core>/main.<ext>` and SHALL NOT write
`src/main-<core>.<ext>`. `--lang cpp` uses `.cpp`; `--lang c` uses `.c`.

Evidence: req-032 still writes `src/main-<core>.<ext>`; current `wl55jc` has
root mains and empty `src/M4`/`src/M0+`.
Verify: `find src -maxdepth 2 -name 'main.*'`; no `src/main-*`.

#### Scenario: cpp project

- **WHEN** `stm32wl55jc` renders with `--lang cpp`
- **THEN** `src/M4/main.cpp` and `src/M0+/main.cpp` exist, no root main

#### Scenario: C project

- **WHEN** `stm32h755` renders with `--lang c`
- **THEN** `src/M7/main.c` and `src/M4/main.c` exist, no root main

### Requirement: Exactly one main object

`SRCS_<core>` SHALL include the per-core main once; adding files under
`src/<core>/` SHALL NOT duplicate the main object.

Evidence: wildcard scans `src/<core>/`, where main now lives.
Verify: `make -pRrq -f Makefile :`; build `src/M4/extra.cpp`.

#### Scenario: extra source alongside main

- **WHEN** `src/M4/extra.cpp` is added next to `src/M4/main.cpp`
- **THEN** the build has one main object and one extra object

### Requirement: Compiler and link behavior preserved

`.c` mains SHALL compile with `$(CC)`; `.cpp` mains with `$(CXX)`. A core
containing a `.cpp` SHALL link with `$(CXX)`; C-only cores keep `$(CC)`.

Evidence: req-032 behavior must not regress.
Verify: `make -n build-M4` on C and C++ projects.

#### Scenario: C stack

- **WHEN** H755 renders with `--lang c`
- **THEN** M7/M4 mains compile with `$(CC)` and link with `$(CC)`

#### Scenario: C++ stack

- **WHEN** WL55 renders with `--lang cpp`
- **THEN** M4/M0+ mains compile with `$(CXX)` and link with `$(CXX)`

### Requirement: Three-pack build proof

F411RE cpp, H755 c, and WL55 cpp SHALL build with the per-core main layout.

Evidence: single-core and dual-core layouts; req-032 matrix.
Verify: `mu create` + `mu build` for all three.

#### Scenario: WL55 extra source

- **WHEN** WL55 adds `src/M4/extra.cpp`
- **THEN** both cores build and the M4 image contains main and extra

### Requirement: Generated README documents the layout

The README SHALL show `src/<core>/main.<ext>` and no root main.

Evidence: users read the source table to add files.
Verify: `rg -n "src/<core>/main" <render>/README.md`.

#### Scenario: user reads the table

- **WHEN** a C/C++ project is rendered
- **THEN** the entry point is documented inside `src/<core>/`
