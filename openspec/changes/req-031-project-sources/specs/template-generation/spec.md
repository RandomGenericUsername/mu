# Spec Delta

## Purpose

Generated C/C++ Makefiles discover project sources per core, support library
sources, and build the same way on single- and dual-core STM32 packs.

## ADDED Requirements

### Requirement: Per-core project source discovery

A generated Makefile SHALL include `src/<core>/**` and `src/common/**` sources
in `SRCS_<core>`; it SHALL NOT use a global `src/*` glob.

Evidence: `renderer.py:486-487` hardcodes only the main file.
Verify: add `src/M4/foo.cpp`; `make -pRrq -f Makefile :` shows its object.

#### Scenario: core-specific source

- **WHEN** a file is added under `src/M4/`
- **THEN** it is compiled and linked into M4 only

#### Scenario: common source

- **WHEN** a file is added under `src/common/`
- **THEN** it is compiled and linked into every core

#### Scenario: dual-core isolation

- **WHEN** `stm32h755` or `stm32wl55jc` renders
- **THEN** `src/M4` objects never appear in the M0+/M4 sibling object list

### Requirement: Compiler and link driver follow the sources

`.c` sources SHALL compile with `$(CC)`; `.cpp` sources with `$(CXX)`. A core
containing a `.cpp` source SHALL link with `$(CXX)`; otherwise it SHALL keep the
stack compiler.

Evidence: the `cpp` stack already links with `$(CXX)` (`renderer.py:432`).
Verify: `make -n build-M4` on a C stack with a `.cpp` extra.

#### Scenario: C stack plus C++ user source

- **WHEN** `src/M4/foo.cpp` is discovered on a C-stack project
- **THEN** `foo.cpp` compiles with `$(CXX)` and the ELF links with `$(CXX)`

### Requirement: Optional extra/library source hook

`config/sources.mk` SHALL be optional and project-owned. The Makefile SHALL
`-include` it and add `EXTRA_SRCS_<core>` to `SRCS_<core>`.

Evidence: library ISR `third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp` is
outside `src/` and must be linkable.
Verify: `make -pRrq -f Makefile :` after defining `EXTRA_SRCS_M4`.

#### Scenario: library source

- **WHEN** `config/sources.mk` sets `EXTRA_SRCS_M4` to a library `.cpp`
- **THEN** that object is built for M4 and linked

#### Scenario: regeneration preserves the file

- **WHEN** a project with `config/sources.mk` is rendered again
- **THEN** the file and its contents are untouched

### Requirement: Existing project shape remains buildable

The main entry point (`src/main-<core>.c` or `.cpp`), startup, system file and
linker scripts SHALL keep their current names and build behavior.

Evidence: current `wl55jc` and existing e2e cells depend on this shape.
Verify: `uv run pytest engine -q`; render a project with no extra sources.

#### Scenario: no extra sources

- **WHEN** no per-core or common sources exist
- **THEN** the object list still contains main, startup, and system

### Requirement: Three-pack build proof

The rendered projects SHALL build for `stm32f411re` (M4), `stm32h755`
(M7+M4), and `stm32wl55jc` (M4+M0+) with a core-specific source, a common
source, and a library source from `config/sources.mk`.

Evidence: the three packs cover single-core, dual-core same-flash, and
dual-core split-flash layouts.
Verify: `mu create` + `mu build` for each; assert every ELF and object path.

#### Scenario: WL55

- **WHEN** the WL55 project adds `src/M4/extra.cpp` and `EXTRA_SRCS_M4`
- **THEN** M4 builds with `$(CXX)` and M0+ remains unchanged

### Requirement: Generated README documents the convention

The generated README SHALL name `src/<core>/`, `src/common/`, and
`config/sources.mk`.

Evidence: users otherwise edit the generated Makefile, as `wl55jc` did.
Verify: `rg -n "src/<core>|config/sources.mk" <render>/README.md`.

#### Scenario: user reads the README

- **WHEN** a C/C++ project is rendered
- **THEN** the README explains how to add a source without editing the Makefile
