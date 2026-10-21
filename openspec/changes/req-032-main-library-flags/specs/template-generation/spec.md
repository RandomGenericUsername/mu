# Spec Delta

## Purpose

Generated C/C++ projects can consume a real library: per-core include/flags from
`config/sources.mk`, and a native C++ entry point for `--lang cpp`.

## ADDED Requirements

### Requirement: Per-core extra include paths and flags

`config/sources.mk` SHALL support `EXTRA_INC_<core>`, `EXTRA_CFLAGS_<core>`,
and `EXTRA_CXXFLAGS_<core>`. `EXTRA_INC` SHALL apply to C and C++ compiles;
the other two to their suffix only.

Evidence: req-031 `config/sources.mk` cannot add `-I`; generated README
suggests a library source but the header is not found.
Verify: `make -n build-M4` shows `-Ithird_party/stm32-hw/include`.

#### Scenario: library include

- **WHEN** `EXTRA_INC_M4 = -Ithird_party/stm32-hw/include`
- **THEN** both C and C++ M4 compiles receive that include path

#### Scenario: suffix flags

- **WHEN** `EXTRA_CXXFLAGS_M4 = -DFOO` and `EXTRA_CFLAGS_M4 = -DBAR`
- **THEN** `.cpp` gets `-DFOO` and `.c` gets `-DBAR`

### Requirement: C++ entry point for `--lang cpp`

A `--lang cpp` project SHALL render `src/main-<core>.cpp`, compile it with
`$(CXX)`, and link with `$(CXX)`. A `--lang c` project SHALL keep
`src/main-<core>.c` and `$(CC)`.

Evidence: `renderer.py` hardcodes `src/main-$core.c`; the `.c` rule uses
`$(CC)`, so a C++ entry point is impossible today.
Verify: render cpp/c projects; inspect source and Makefile.

#### Scenario: cpp main

- **WHEN** `stm32wl55jc` renders with `--lang cpp`
- **THEN** `src/main-M4.cpp` and `src/main-M0+.cpp` exist and compile with
  `$(CXX)`

#### Scenario: C main preserved

- **WHEN** `stm32f411re` renders with `--lang c`
- **THEN** `src/main-M4.c` exists and compiles with `$(CC)`

### Requirement: Real library integration

A generated project SHALL build with a library source outside `src/` and the
library include path supplied only through `config/sources.mk`.

Evidence: `stm32-hw` ADC ISR at
`third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp`; header
`<stm32/drivers/wl55.hpp>`.
Verify: `mu create` + `mu build` with `EXTRA_SRCS_M4` and `EXTRA_INC_M4`.

#### Scenario: WL55 ADC library

- **WHEN** a WL55 cpp project adds the ADC ISR and `stm32-hw` include
- **THEN** it builds, `ADC_IRQHandler` is strong, and vector `0x88` points at it

#### Scenario: F411RE and H755

- **WHEN** F411RE cpp and H755 c projects add their family ADC ISR/include
- **THEN** both build; H755 M7 links with `$(CC)` and M4 with `$(CXX)`

### Requirement: Generated docs describe the hooks

The generated README SHALL document `EXTRA_INC_<core>` and the C++ main file.

Evidence: req-031 README recommends `EXTRA_SRCS` without an include path.
Verify: `rg -n "EXTRA_INC|main-<core>\.cpp" <render>/README.md`.

#### Scenario: user reads the README

- **WHEN** a C/C++ project is rendered
- **THEN** the README explains how to add a library include and which main file
  is compiled
