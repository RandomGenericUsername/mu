# E2E build evidence (req-009) — 12/12 cells green

Rendered trees compile in the pinned images with zero host deps.
C/C++ cells inject harness-owned vendor stubs (see module docstring);
warnings are recorded per cell and never fail (warn-only policy).

## stm32f411re / c — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M4/stm32f411re-M4.elf; exits=0,0; artifacts=; fits=flash=616/524288,ram=36/131072`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32f411re-M4.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32f411re/Source/Templates/gcc/startup_stm32f411xe.s
- `build/M4/stm32f411re-M4.elf`: text=608 data=8 bss=28
  - flash: used 616 / avail 524288 (flash)
  - ram: used 36 / avail 131072 (ram)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32f411re-M4.elf has a LOAD segment with RWX permissions

## stm32f411re / cpp — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M4/stm32f411re-M4.elf; exits=0,0; artifacts=; fits=flash=616/524288,ram=36/131072`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32f411re-M4.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32f411re/Source/Templates/gcc/startup_stm32f411xe.s
- `build/M4/stm32f411re-M4.elf`: text=608 data=8 bss=28
  - flash: used 616 / avail 524288 (flash)
  - ram: used 36 / avail 131072 (ram)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32f411re-M4.elf has a LOAD segment with RWX permissions

## stm32f411re / rust — PASS

- image: `ghcr.io/randomgenericusername/lang-rust:1.99.0`
- stack: `cargo-cortex` (template family `rust-cortex`)
- build evidence: `stack=cargo-cortex; template_family=rust-cortex; commands=cargo build --target thumbv7em-none-eabihf (in ghcr.io/randomgenericusername/lang-rust:1.99.0); exits=0; artifacts=target/thumbv7em-none-eabihf/debug/stm32f411re=814328; fits=`
- cmd `cargo build --target thumbv7em-none-eabihf (in ghcr.io/randomgenericusername/lang-rust:1.99.0)` -> exit 0
- note: FLASH: origin=0x08000000 length=524288 matches pack; RAM: origin=0x20000000 length=131072 matches pack
- `target/thumbv7em-none-eabihf/debug/stm32f411re`: 814328 bytes (host stat, informational)
- warnings:
    (none)

## stm32h755 / c — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M7/stm32h755-M7.elf | arm-none-eabi-size -B build/M4/stm32h755-M4.elf; exits=0,0,0; artifacts=; fits=flash_m7=820/1048576,flash_m4=576/1048576,ram_m7=36/524288,ram_m4=40/294912`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M7/stm32h755-M7.elf` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32h755-M4.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32h755/Source/Templates/gcc/startup_stm32h755xx.s, vendor/cmsis-device-stm32h755/Source/Templates/gcc/startup_stm32h755xx.s
- `build/M7/stm32h755-M7.elf`: text=812 data=8 bss=28
  - flash: used 820 / avail 1048576 (flash_m7)
  - ram: used 36 / avail 524288 (ram_m7)
- `build/M4/stm32h755-M4.elf`: text=568 data=8 bss=32
  - flash: used 576 / avail 1048576 (flash_m4)
  - ram: used 40 / avail 294912 (ram_m4)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M7/stm32h755-M7.elf has a LOAD segment with RWX permissions
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32h755-M4.elf has a LOAD segment with RWX permissions

## stm32h755 / cpp — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M7/stm32h755-M7.elf | arm-none-eabi-size -B build/M4/stm32h755-M4.elf; exits=0,0,0; artifacts=; fits=flash_m7=820/1048576,flash_m4=576/1048576,ram_m7=36/524288,ram_m4=40/294912`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M7/stm32h755-M7.elf` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32h755-M4.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32h755/Source/Templates/gcc/startup_stm32h755xx.s, vendor/cmsis-device-stm32h755/Source/Templates/gcc/startup_stm32h755xx.s
- `build/M7/stm32h755-M7.elf`: text=812 data=8 bss=28
  - flash: used 820 / avail 1048576 (flash_m7)
  - ram: used 36 / avail 524288 (ram_m7)
- `build/M4/stm32h755-M4.elf`: text=568 data=8 bss=32
  - flash: used 576 / avail 1048576 (flash_m4)
  - ram: used 40 / avail 294912 (ram_m4)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M7/stm32h755-M7.elf has a LOAD segment with RWX permissions
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32h755-M4.elf has a LOAD segment with RWX permissions

## stm32h755 / rust — PASS

- image: `ghcr.io/randomgenericusername/lang-rust:1.99.0`
- stack: `cargo-cortex-dual` (template family `rust-cortex-dual`)
- build evidence: `stack=cargo-cortex-dual; template_family=rust-cortex-dual; commands=make build (in ghcr.io/randomgenericusername/lang-rust:1.99.0) | size -B build/M7/stm32h755-M7.elf | size -B build/M4/stm32h755-M4.elf; exits=0,0,0; artifacts=; fits=flash_m7=1216/1048576,flash_m4=1172/1048576,ram_m7=0/524288,ram_m4=4/294912`
- cmd `make build (in ghcr.io/randomgenericusername/lang-rust:1.99.0)` -> exit 0
- cmd `size -B build/M7/stm32h755-M7.elf` -> exit 0
- cmd `size -B build/M4/stm32h755-M4.elf` -> exit 0
- note: M7/FLASH: origin=0x08000000 length=1048576; M7/RAM: origin=0x24000000 length=524288; M4/FLASH: origin=0x08100000 length=1048576; M4/RAM: origin=0x30000000 length=294912
- `build/M7/stm32h755-M7.elf`: text=1216 data=0 bss=0
  - flash: used 1216 / avail 1048576 (flash_m7)
  - ram: used 0 / avail 524288 (ram_m7)
- `build/M4/stm32h755-M4.elf`: text=1172 data=0 bss=4
  - flash: used 1172 / avail 1048576 (flash_m4)
  - ram: used 4 / avail 294912 (ram_m4)
- warnings:
    (none)

## stm32wl55jc / c — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M4/stm32wl55jc-M4.elf | arm-none-eabi-size -B build/M0+/stm32wl55jc-M0+.elf; exits=0,0,0; artifacts=; fits=flash_m4=612/131072,flash_m0plus=512/131072,ram_m4=40/49152,ram_m0plus=40/16384`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32wl55jc-M4.elf` -> exit 0
- cmd `arm-none-eabi-size -B build/M0+/stm32wl55jc-M0+.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32wl55jc/Source/Templates/gcc/startup_stm32wl55xx_cm4.s, vendor/cmsis-device-stm32wl55jc/Source/Templates/gcc/startup_stm32wl55xx_cm0plus.s
- `build/M4/stm32wl55jc-M4.elf`: text=600 data=12 bss=28
  - flash: used 612 / avail 131072 (flash_m4)
  - ram: used 40 / avail 49152 (ram_m4)
- `build/M0+/stm32wl55jc-M0+.elf`: text=504 data=8 bss=32
  - flash: used 512 / avail 131072 (flash_m0plus)
  - ram: used 40 / avail 16384 (ram_m0plus)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32wl55jc-M4.elf has a LOAD segment with RWX permissions
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M0+/stm32wl55jc-M0+.elf has a LOAD segment with RWX permissions

## stm32wl55jc / cpp — PASS

- image: `ghcr.io/randomgenericusername/lang-cpp:15.3.rel2`
- stack: `make-cmsis` (template family `c-cmsis`)
- build evidence: `stack=make-cmsis; template_family=c-cmsis; commands=make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2) | arm-none-eabi-size -B build/M4/stm32wl55jc-M4.elf | arm-none-eabi-size -B build/M0+/stm32wl55jc-M0+.elf; exits=0,0,0; artifacts=; fits=flash_m4=612/131072,flash_m0plus=512/131072,ram_m4=40/49152,ram_m0plus=40/16384`
- cmd `make build (in ghcr.io/randomgenericusername/lang-cpp:15.3.rel2)` -> exit 0
- cmd `arm-none-eabi-size -B build/M4/stm32wl55jc-M4.elf` -> exit 0
- cmd `arm-none-eabi-size -B build/M0+/stm32wl55jc-M0+.elf` -> exit 0
- note: vendor stubs injected: vendor/cmsis-device-stm32wl55jc/Source/Templates/gcc/startup_stm32wl55xx_cm4.s, vendor/cmsis-device-stm32wl55jc/Source/Templates/gcc/startup_stm32wl55xx_cm0plus.s
- `build/M4/stm32wl55jc-M4.elf`: text=600 data=12 bss=28
  - flash: used 612 / avail 131072 (flash_m4)
  - ram: used 40 / avail 49152 (ram_m4)
- `build/M0+/stm32wl55jc-M0+.elf`: text=504 data=8 bss=32
  - flash: used 512 / avail 131072 (flash_m0plus)
  - ram: used 40 / avail 16384 (ram_m0plus)
- warnings:
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M4/stm32wl55jc-M4.elf has a LOAD segment with RWX permissions
    /opt/arm-gnu-toolchain/bin/../lib/gcc/arm-none-eabi/15.3.1/../../../../arm-none-eabi/bin/ld: warning: build/M0+/stm32wl55jc-M0+.elf has a LOAD segment with RWX permissions

## stm32wl55jc / rust — PASS

- image: `ghcr.io/randomgenericusername/lang-rust:1.99.0`
- stack: `cargo-cortex-dual` (template family `rust-cortex-dual`)
- build evidence: `stack=cargo-cortex-dual; template_family=rust-cortex-dual; commands=make build (in ghcr.io/randomgenericusername/lang-rust:1.99.0) | size -B build/M4/stm32wl55jc-M4.elf | size -B build/M0+/stm32wl55jc-M0+.elf; exits=0,0,0; artifacts=; fits=flash_m4=1224/131072,flash_m0plus=312/131072,ram_m4=0/49152,ram_m0plus=4/16384`
- cmd `make build (in ghcr.io/randomgenericusername/lang-rust:1.99.0)` -> exit 0
- cmd `size -B build/M4/stm32wl55jc-M4.elf` -> exit 0
- cmd `size -B build/M0+/stm32wl55jc-M0+.elf` -> exit 0
- note: M4/FLASH: origin=0x08000000 length=131072; M4/RAM: origin=0x20000000 length=49152; M0+/FLASH: origin=0x08020000 length=131072; M0+/RAM: origin=0x2000C000 length=16384
- `build/M4/stm32wl55jc-M4.elf`: text=1224 data=0 bss=0
  - flash: used 1224 / avail 131072 (flash_m4)
  - ram: used 0 / avail 49152 (ram_m4)
- `build/M0+/stm32wl55jc-M0+.elf`: text=312 data=0 bss=4
  - flash: used 312 / avail 131072 (flash_m0plus)
  - ram: used 4 / avail 16384 (ram_m0plus)
- warnings:
    (none)

## esp32cam / c — PASS

- image: `espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`
- stack: `idf-cmake` (template family `idf-cmake`)
- build evidence: `stack=idf-cmake; template_family=idf-cmake; commands=idf.py build (in espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c); exits=0; artifacts=build/bootloader/bootloader.bin=26176,build/partition_table/partition-table.bin=3072,build/esp32cam.bin=149168; fits=factory=149168/1048576`
- cmd `idf.py build (in espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c)` -> exit 0
- note: app 149168 B / 1048576 B factory partition; triple: bootloader.bin, partition-table.bin, esp32cam.bin
- `build/bootloader/bootloader.bin`: 26176 bytes (host stat, informational)
- `build/partition_table/partition-table.bin`: 3072 bytes (host stat, informational)
- `build/esp32cam.bin`: text=149168 data=0 bss=0
  - flash: used 149168 / avail 1048576 (factory)
  - ram: used 0 / avail 0 ()
- warnings:
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):

## esp32cam / cpp — PASS

- image: `espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`
- stack: `idf-cmake` (template family `idf-cmake`)
- build evidence: `stack=idf-cmake; template_family=idf-cmake; commands=idf.py build (in espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c); exits=0; artifacts=build/bootloader/bootloader.bin=26176,build/partition_table/partition-table.bin=3072,build/esp32cam.bin=149136; fits=factory=149136/1048576`
- cmd `idf.py build (in espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c)` -> exit 0
- note: app 149136 B / 1048576 B factory partition; triple: bootloader.bin, partition-table.bin, esp32cam.bin
- `build/bootloader/bootloader.bin`: 26176 bytes (host stat, informational)
- `build/partition_table/partition-table.bin`: 3072 bytes (host stat, informational)
- `build/esp32cam.bin`: text=149136 data=0 bss=0
  - flash: used 149136 / avail 1048576 (factory)
  - ram: used 0 / avail 0 ()
- warnings:
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):
    CMake Warning at /opt/esp/idf/tools/cmake/component_validation.cmake:106 (message):

## esp32cam / rust — PASS

- image: `espressif/idf-rust:esp32_1.95.0.0@sha256:1f90203f191cc94d7da1acf4da0e0e87aac128165115c1512f30668359f09dc6`
- stack: `esp-idf-rust` (template family `esp-idf-rust`)
- build evidence: `stack=esp-idf-rust; template_family=esp-idf-rust; commands=cargo build (in espressif/idf-rust:esp32_1.95.0.0@sha256:1f90203f191cc94d7da1acf4da0e0e87aac128165115c1512f30668359f09dc6) | xtensa-esp32-elf-size -B target/xtensa-esp32-espidf/debug/esp32cam; exits=0,0; artifacts=; fits=app=541253/4128768`
- cmd `cargo build (in espressif/idf-rust:esp32_1.95.0.0@sha256:1f90203f191cc94d7da1acf4da0e0e87aac128165115c1512f30668359f09dc6)` -> exit 0
- cmd `xtensa-esp32-elf-size -B target/xtensa-esp32-espidf/debug/esp32cam` -> exit 0
- note: app 541253 B / 4128768 B app bank
- `target/xtensa-esp32-espidf/debug/esp32cam`: text=354235 data=187018 bss=2739
  - flash: used 541253 / avail 4128768 (app)
  - ram: used 0 / avail 0 ()
- warnings:
    (none)
