---
id: req-032
title: "Library include flags and C++ main entry in generated projects"
kind: requirement
status: in-progress
size: M
lane: openspec-single
links:
  openspec:
    - openspec/changes/req-032-main-library-flags
  bmad: []
worktree: .worktrees/req-032/
branch: ticket/req-032-main-library-flags
---

# Library include flags and C++ main entry in generated projects

## Handoff

Work in this worktree/branch:

```text
worktree: .worktrees/req-032/
branch:   ticket/req-032-main-library-flags
change:   openspec/changes/req-032-main-library-flags
```

Read `AGENTS.md`, `tickets/LIFECYCLE.md`, and the change artifacts first.
Do not work on `main`. Keep planning and implementation commits separate.

## Problem

req-031 added per-core source discovery and `config/sources.mk` for extra
sources, but real library use is still blocked:

1. **No include/flags hook.** `config/sources.mk` is included before the
   per-core `CFLAGS_<core>`/`CXXFLAGS_<core>` are defined, and there is no
   `EXTRA_INC_<core>`/`EXTRA_CFLAGS_<core>` variable. The generated README
   suggests:

   ```make
   EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp
   ```

   but the build then fails with:

   ```text
   fatal error: stm32/drivers/wl55.hpp: No such file or directory
   ```

   It only works after hand-editing `CXXFLAGS_M4` in the generated Makefile.

2. **C++ main is not supported.** `--lang cpp` still renders
   `src/main-<core>.c`, and the pattern rule compiles `.c` with `$(CC)`.
   Putting the entry point in `src/<core>/main.cpp` collides with the generated
   `main`. The application cannot have a C++ main without a workaround.

3. **Proof recipe drops symbols.** The req-031 three-pack recipe checks `nm` on
   ELFs, but unused test functions are removed by `--gc-sections`; the recipe
   needs forced references or object-level checks.

Evidence from the independent req-031 test (2026-10-21):

- Generated `wl55-regen` (WL55, `--lang cpp`) has
  `src/main-M4.c`; its Makefile compiles it with `arm-none-eabi-gcc`.
- Adding `src/M4/adc_check.cpp` including `<stm32/drivers/wl55.hpp>` fails
  until `-Ithird_party/stm32-hw/include` is added manually to `CXXFLAGS_M4`.
- After that: `ADC_IRQHandler` is a strong `T` at `0x080003d4`, and vector
  `0x08000088` = `0x080003d5` (WL55 `ADC_IRQn = 18`).
- F411RE (C stack) + `.cpp` extra links with `arm-none-eabi-g++`; H755 M7
  (no `.cpp`) links with `arm-none-eabi-gcc`, M4 (`.cpp`) with `g++`.
- Test projects: `/tmp/opencode/req031-regen/` (ephemeral; commands below).

## Requirement

`config/sources.mk` SHALL support per-core extra include paths and flags, and
`--lang cpp` SHALL generate a C++ entry point compiled as C++.

Required hook:

```make
# config/sources.mk
EXTRA_SRCS_M4     = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp
EXTRA_INC_M4      = -Ithird_party/stm32-hw/include
EXTRA_CFLAGS_M4   =
EXTRA_CXXFLAGS_M4 =
```

- `EXTRA_INC_<core>` is added to both C and C++ compile flags for that core.
- `EXTRA_CFLAGS_<core>` is added to C compiles.
- `EXTRA_CXXFLAGS_<core>` is added to C++ compiles.
- Values are applied after the base flags; no generated-Makefile edit.

C++ entry point:

- `--lang cpp` SHALL render `src/main-<core>.cpp`, include it in
  `SRCS_<core>`, compile it with `$(CXX)`, and link with `$(CXX)`.
- `--lang c` SHALL keep `src/main-<core>.c` and `$(CC)`.
- Existing C projects keep their shape.

## Acceptance

- [ ] `EXTRA_INC_<core>`, `EXTRA_CFLAGS_<core>`, `EXTRA_CXXFLAGS_<core>` are
      honoured from `config/sources.mk` after the base flags.
      `Verify: make -n build-M4` shows `-Ithird_party/stm32-hw/include`.
- [ ] `--lang cpp` emits `src/main-<core>.cpp`; the main compiles with
      `$(CXX)`, links with `$(CXX)`, and can use C++ code.
      `Verify: render a cpp project; inspect Makefile/SRCS; build`.
- [ ] `--lang c` keeps `src/main-<core>.c` and `$(CC)`.
      `Verify: render an F411RE c project; build`.
- [ ] A WL55 cpp project builds with the real `stm32-hw` library:
      `EXTRA_SRCS_M4` = ADC ISR, `EXTRA_INC_M4` = library include; strong
      `ADC_IRQHandler`; vector `0x88` points at it.
      `Verify: `arm-none-eabi-nm` + `objdump -s -j .isr_vector``.
- [ ] F411RE cpp and H755 c builds with the library headers/ISR compile and
      the correct link driver; M7 (no `.cpp`) stays `$(CC)`, M4 (`.cpp`) uses
      `$(CXX)`; no cross-core leak.
- [ ] Three-pack matrix is green: F411RE, H755, WL55JC.
- [ ] `uv run pytest engine -q` and
      `uv run openspec validate req-032-main-library-flags` pass.
- [ ] Generated README documents `EXTRA_INC_<core>` and the C++ main behavior.

## Three-board test recipe

Use `/tmp/req032` and the saved library tag `adc-driver-isr`
(commit `c3a5e14`).

```sh
mkdir -p /tmp/req032
cd /home/inumaki/Development/mu/.worktrees/req-032

uv run mu create --name f411 --mcu-config stm32f411re --lang cpp --path /tmp/req032
uv run mu create --name h755 --mcu-config stm32h755 --lang c --path /tmp/req032
uv run mu create --name wl55 --mcu-config stm32wl55jc --lang cpp --path /tmp/req032

# add the library to each project
for p in f411 h755 wl55; do
  git -C /tmp/req032/$p -c protocol.file.allow=always submodule add \
    /home/inumaki/Development/stm32-hw third_party/stm32-hw
done
```

WL55 (cpp main + ADC ISR + include flags):

```sh
cat > /tmp/req032/wl55/src/M4/adc_check.cpp <<'EOF'
#include <stm32/drivers/wl55.hpp>
extern "C" void adc_check() {
    stm32::drivers::wl55::Adc1::init();
}
EOF
cat > /tmp/req032/wl55/config/sources.mk <<'EOF'
EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp
EXTRA_INC_M4  = -Ithird_party/stm32-hw/include
EOF
# call adc_check() from the generated src/main-M4.cpp (cpp main)
```

F411RE (cpp main + F4 ADC ISR):

```sh
cat > /tmp/req032/f411/src/M4/adc_check.cpp <<'EOF'
#include <stm32/drivers/f4.hpp>
extern "C" void adc_check() {
    stm32::drivers::f4::Adc1::init();
}
EOF
cat > /tmp/req032/f411/config/sources.mk <<'EOF'
EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_f4.cpp
EXTRA_INC_M4  = -Ithird_party/stm32-hw/include
EOF
# call adc_check() from src/main-M4.cpp
```

H755 (C main + H7 ADC ISR; M4 include flags):

```sh
cat > /tmp/req032/h755/src/M4/adc_check.cpp <<'EOF'
#include <stm32/drivers/h7.hpp>
extern "C" void adc_check() {
    stm32::drivers::h7::Adc1::init();
}
EOF
cat > /tmp/req032/h755/config/sources.mk <<'EOF'
EXTRA_SRCS_M4 = third_party/stm32-hw/src/drivers/adc_irq_h7.cpp
EXTRA_INC_M4  = -Ithird_party/stm32-hw/include
EOF
# call adc_check() from src/main-M4.c
```

Build and assert:

```sh
uv run mu build --project-dir /tmp/req032/f411
uv run mu build --project-dir /tmp/req032/h755
uv run mu build --project-dir /tmp/req032/wl55

arm-none-eabi-nm /tmp/req032/wl55/build/M4/*.elf | grep ADC_IRQHandler
arm-none-eabi-objdump -s -j .isr_vector /tmp/req032/wl55/build/M4/*.elf | grep 8000080
arm-none-eabi-nm /tmp/req032/f411/build/M4/*.elf | grep ADC_IRQHandler
arm-none-eabi-nm /tmp/req032/h755/build/M4/*.elf | grep ADC_IRQHandler
```

Expected: all three build; the C++ mains compile with `$(CXX)`; the library
ISR is strong in the vector; `EXTRA_INC` is present in the compile command;
H755 M7 links with `$(CC)` and M4 with `$(CXX)`; no cross-core leak.

## Out of scope

- Moving the generated main into `src/<core>/`.
- Changing `stm32-hw` itself.
- Board wiring / ADC application behavior.
- Rust/ESP-IDF families.
