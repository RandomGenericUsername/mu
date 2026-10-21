"""Project renderer (req-008).

Pack model in -> project tree out. ``string.Template`` substitution only;
per-core contexts are pre-computed here and dual-core packs render by core
iteration, not template forks (design.md). The renderer consumes the
certified model ONLY (``Device.facets`` for fpu/linker/config-headers,
``Device.openocd`` for flash facts) and never re-reads pack YAML.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from string import Template

from engine.core.model import Core, Device
from engine.core.bootcheck import boot_check_commands
from engine.core.plan import build_plan
from engine.core.stacks import stack_spec
from engine.adapters.toolchain import ensure_registered as _ensure_stacks
from engine.templates.families import RenderOptions, family_for
from engine.templates.vendoring import VendorError, vendor

__all__ = [
    "CPU_BY_CORE",
    "RUST_PINS",
    "SUPPORTED_LANGS",
    "core_context",
    "render",
]

SUPPORTED_LANGS = ("c", "cpp", "rust")

#: Shipped template families (AD-11). The registry is the runtime source of
#: truth; this tuple is for capability discovery/tests.
SUPPORTED_TEMPLATE_FAMILIES = (
    "c-cmsis",
    "rust-cortex",
    "rust-cortex-dual",
    "idf-cmake",
    "esp-idf-rust",
)

# Core name -> gcc -mcpu value (renderer-owned map, no template fork).
CPU_BY_CORE = {
    "M4": "cortex-m4",
    "M7": "cortex-m7",
    "M0+": "cortex-m0plus",
}

# Pinned embedded crates, verified against the crates.io API 2026-10-09
# (max stable: cortex-m 0.7.9, cortex-m-rt 0.7.7, panic-halt 1.0.0;
# flip-link 0.1.12 matches the spike-003 toolchain table). Exact `=` pins
# so re-renders are reproducible. Sibling pins (0.6.x era) predate these
# and are NOT reused.
RUST_PINS = {
    "cortex-m": "=0.7.9",
    "cortex-m-rt": "=0.7.7",
    "panic-halt": "=1.0.0",
}
FLIP_LINK_PIN = "0.1.12"
# Toolchain recon (spike-003): rust stable 1.99.0 carries both thumbv7em
# targets as Tier-2 no_std.
RUST_VERSION = "1.99"


def _fpu_flags(mode: str, variant: str) -> str:
    if mode == "soft" or variant == "none":
        return "-mfloat-abi=soft"
    return f"-mfpu={variant} -mfloat-abi={mode}"


def _define_flags(macros: str | None) -> str:
    """Space-separated pack macros -> ``-D`` flags (dual-core cores need two)."""
    if not macros:
        return ""
    return " ".join(f"-D{m}" for m in macros.split())


def _target_slug(core_name: str) -> str:
    """Shell/make-safe slug of a core name: lowercase alphanumerics, other
    characters dropped (``M0+`` -> ``m0plus``, ``CM4`` -> ``cm4``)."""
    lowered = core_name.lower().replace("+", "plus")
    return "".join(ch for ch in lowered if ch.isalnum())


def _sibling_attach(device: Device) -> tuple[str, str, str] | None:
    """Sibling-core attach facts for a released-sibling pack (bug-030).

    ``make flash`` flashes a ``cpu2_boot`` pack **single-core** (the sibling is
    asleep at reset and its AP writes fail the final reset — bug-021/024), and
    the flash argv deliberately omits ``probe/dual-core.cfg``. So after
    ``make flash`` the second OpenOCD core does not exist. This returns
    ``(slug, core_name, openocd_target)`` of the **first sibling** when the pack
    declares both ``facets.cpu2_boot`` and a target-direct ``dual_core`` OpenOCD
    session (the only case where ``probe/dual-core.cfg`` is emitted, hence the
    only one whose argv can name the second core). ``None`` otherwise.

    The argv sources ``probe/dual-core.cfg`` **before** the target config (the
    target reads ``DUAL_CORE`` while creating the second core) and **never**
    resets: a system reset cannot halt the released sibling (bug-024).
    """
    oc = device.openocd
    if oc is None or not oc.dual_core or oc.board or not device.facets.cpu2_boot:
        return None
    if len(device.cores) < 2:
        return None
    sibling = device.cores[1]
    target = next((name for core, name in oc.targets if core == sibling.name), None)
    if target is None:
        return None
    return _target_slug(sibling.name), sibling.name, target


def _sibling_attach_args(device: Device) -> str:
    """OpenOCD argv for the sibling-attach session (dual-core before target)."""
    oc = device.openocd
    assert oc is not None
    interface, target = oc.config_files()
    return (
        f"-f {interface} -f probe/probe-serial.cfg -f probe/dual-core.cfg -f {target}"
    )


def _oc_cfg_path(device: Device) -> str:
    """Board-vs-target config path, resolved by the model (bug-003)."""
    oc = device.openocd
    if oc is None:
        return "target/stm32f4x.cfg"
    return oc.config_files()[1]


def _oc_flash_args(device: Device) -> str:
    """`openocd -f ...` args for flash-helper targets, from model facts."""
    oc = device.openocd
    if oc is None:
        # No invented fallback (startup lesson, mirrors DeviceFacets.linker_for):
        # a pack without an openocd block is a loud error, never a plausible-
        # but-wrong board default (stlink.cfg/stm32f4x.cfg).
        raise ValueError(
            f"pack {device.id!r} declares no openocd block; cannot derive flash args"
        )
    interface, target = oc.config_files()
    # probe/probe-serial.cfg is renderer-owned layout (written for every
    # project): it pins the probe by serial from MU_PROBE_SERIAL (bug-018).
    args = f"-f {interface} -f probe/probe-serial.cfg"
    if oc.dual_core and not oc.board and not device.facets.cpu2_boot:
        # Target-direct dual-core packs (WL55JC) have no board file to set the
        # flag, and the target cfg reads DUAL_CORE while creating the second
        # core — so it must be sourced BEFORE the target (bug-021).
        # Packs that must *release* their sibling (cpu2_boot) are flashed
        # single-core: the second core is asleep at reset, so its AP writes fail
        # the final reset ("AP write error, reset will not halt"). Flashing the
        # sibling image via cpu0's flash bank works regardless (bug-021).
        args += " -f probe/dual-core.cfg"
    args += f" -f {target}"
    # Flash-only reset override: a sleeping target needs SRST asserted during
    # connect (H755 board cfg uses connect_deassert_srst). Debug configs keep
    # their attach semantics.
    if oc.flash_reset_config:
        args += f" -c 'reset_config {oc.flash_reset_config}'"
    return args


def _oc_target_line(device: Device, core_name: str) -> str:
    """``-c "targets <core>"`` for independent dual-core flash targets.

    A cpu2_boot pack is flashed single-core (the sibling is asleep), so it must
    not select the sibling target. H755 exposes cpu0/cpu1 and needs the
    selection so ``program`` and the PC boot check act on the right core.
    """
    oc = device.openocd
    if oc is None or not oc.targets or device.facets.cpu2_boot:
        return ""
    for name, target in oc.targets:
        if name == core_name:
            return f' -c "targets {target}"'
    return ""


def _boot_check_cmds(device: Device, core_name: str) -> str:
    """`-c '<loop>' -c '<verdict>'` for the flash targets (bug-027).

    The reset at the end of `program … verify reset` leaves the board in a
    *possibly* non-booting state (bug-027), so every flash target appends the
    shared verify-and-retry tail from :mod:`engine.core.bootcheck`. Two
    escaping rules, in order: ``$`` becomes ``$$`` so `make` hands a literal
    ``$`` to the recipe, and the Tcl payload is wrapped in **single** quotes so
    the shell does not expand those variables. The commands themselves are
    built by the shared module, so `make flash` and `mu flash` cannot drift.
    """
    cmds = boot_check_commands(device.memory, core_name)
    return " ".join("-c '" + c.replace("$", "$$") + "'" for c in cmds)


# Delay-loop calibration for the generated examples (bug-015). The NOP loop
# runs at ~5 cycles/iteration on the H755 M7 at -Os; the old divisor of 16
# overestimated it 3x, so the "10 Hz" blink actually ran at ~29 Hz — too fast
# to read as a blink (measured: 17 ms half-period). Target a ~0.25 s
# half-period (~2 Hz), which the eye clearly sees as a blink.
_DELAY_CYCLES_PER_ITER = 5
_DELAY_HALF_PERIOD_S = 0.25


def _cpu2_boot_sections(facets: DeviceFacets) -> tuple[str, str]:
    """(extra includes, main body) that release a sibling core (bug-021/023).

    Device facts only: each ``(addr, value, mask)`` becomes a masked or plain OR
    write, so the primary core boots its sibling (e.g. the STM32WL55 CPU2/CM0+
    needs its reset vector pointed at its own image and ``PWR_CR4.C2BOOT`` set).

    Emitted as a **constructor**, i.e. it runs during C-runtime init *before*
    ``main`` (bug-023): a debug session that halts at the ``main`` entry
    (`runToEntryPoint`) would otherwise leave the sibling unreleased, and the
    sibling's own session could never attach.
    """
    if not facets.cpu2_boot:
        return "", ""
    lines = [
        "/* Release the sibling core before main() so it is up however the\n"
        "   debugger halts (bug-023): point its reset vector at its image, then boot it. */\n"
        "__attribute__((constructor)) static void mu_release_sibling(void)\n"
        "{\n"
    ]
    for addr, value, mask in facets.cpu2_boot:
        if mask:
            lines.append(
                f"    REG32(0x{addr:08X}UL) = (REG32(0x{addr:08X}UL) & ~0x{mask:08X}UL)"
                f" | 0x{value:08X}UL;"
            )
        else:
            lines.append(f"    REG32(0x{addr:08X}UL) |= 0x{value:08X}UL;")
    lines.append("}\n")
    ctor = "\n".join(lines)
    # Preamble only needed where the surrounding includes lack it (the sibling
    # example); the LED example already defines REG32 and includes <stdint.h>.
    preamble = (
        "#include <stdint.h>\n"
        "\n"
        "#define REG32(a)     (*(volatile uint32_t *)(a))\n"
        "\n"
    )
    return preamble, ctor


def _sibling_sections(facets: DeviceFacets) -> tuple[str, str]:
    """(extra includes, main body) for a core with no LED example (ops-018).

    A volatile counter in a timed loop: set a breakpoint on ``counter++`` (or
    watch ``counter``) to prove the core is attached and steppable. No pin is
    touched, so a sibling core can't fight the primary core's LED example.
    """
    clock = facets.example_led.clock_hz if facets.example_led else 16_000_000
    iters = round(_DELAY_HALF_PERIOD_S * clock / _DELAY_CYCLES_PER_ITER)
    includes = (
        "#include <stdint.h>\n"
        "\n"
        f"#define DELAY_ITERS  {iters}UL  /* ~{_DELAY_HALF_PERIOD_S:g} s @{clock} Hz; tune */\n"
        "\n"
        "/* Volatile so it survives -O and is watchable in a debug session. */\n"
        "volatile uint32_t counter = 0;\n"
        "\n"
        "static void delay_loop(void)\n"
        "{\n"
        "    for (volatile uint32_t i = 0; i < DELAY_ITERS; ++i) {\n"
        '        __asm volatile ("nop");\n'
        "    }\n"
        "}\n"
    )
    body = (
        "    /* Sibling-core bring-up: proves this core runs and is debuggable.\n"
        "       Breakpoint on `counter++` (or watch `counter`) — it advances. */\n"
        "    for (;;) {\n"
        "        counter++;\n"
        "        delay_loop();\n"
        "    }\n"
    )
    return includes, body


def _main_sections(facets: DeviceFacets, primary: bool) -> tuple[str, str]:
    """(extra includes, main body) for ``src/main-<core>.c`` (req-014/req-015).

    A pack that declares ``example.led`` gets a self-contained blink of that
    on-board LED (raw registers + NOP half-period delay, no HAL) on the
    **primary** (first) core. Any other core (a dual-core sibling, or a pack
    with no LED fact) gets the ``_sibling_sections`` counter loop instead.
    """
    boot_preamble, boot_ctor = _cpu2_boot_sections(facets) if primary else ("", "")
    led = facets.example_led if primary else None
    if led is None:
        sibling_includes, sibling_body = _sibling_sections(facets)
        return boot_preamble + sibling_includes + "\n" + boot_ctor, sibling_body
    gpio, rcc = led.gpio_base, led.rcc_en_addr
    on_shift, off_shift = (
        (led.pin, led.pin + 16) if led.active == "high" else (led.pin + 16, led.pin)
    )
    iters = round(_DELAY_HALF_PERIOD_S * led.clock_hz / _DELAY_CYCLES_PER_ITER)
    includes = (
        "#include <stdint.h>\n"
        "\n"
        "#define REG32(a)     (*(volatile uint32_t *)(a))\n"
        f"#define RCC_EN       REG32(0x{rcc:08X}UL)\n"
        f"#define GPIO_MODER   REG32(0x{gpio:08X}UL)\n"
        f"#define GPIO_BSRR    REG32(0x{gpio + 0x18:08X}UL)\n"
        "\n"
        f"#define LED_PIN      {led.pin}u\n"
        f"#define BSRR_ON      (1u << {on_shift})\n"
        f"#define BSRR_OFF     (1u << {off_shift})\n"
        f"#define DELAY_ITERS  {iters}UL  /* ~{_DELAY_HALF_PERIOD_S:g} s @{led.clock_hz} Hz, ~2 Hz blink; tune */\n"
        "\n"
        "static void delay_half_period(void)\n"
        "{\n"
        "    for (volatile uint32_t i = 0; i < DELAY_ITERS; ++i) {\n"
        '        __asm volatile ("nop");\n'
        "    }\n"
        "}\n"
    )
    body = (
        f"    /* Example for this pack: blink the on-board LED "
        f"(P{led.port.upper()}{led.pin}, {led.active} active). */\n"
        f"    RCC_EN |= (1u << {led.rcc_en_bit});\n"
        "    GPIO_MODER &= ~(3u << (LED_PIN * 2));\n"
        "    GPIO_MODER |=  (1u << (LED_PIN * 2));\n"
        "\n"
        "    for (;;) {\n"
        "        GPIO_BSRR = BSRR_ON;\n"
        "        delay_half_period();\n"
        "        GPIO_BSRR = BSRR_OFF;\n"
        "        delay_half_period();\n"
        "    }\n"
    )
    # The release constructor precedes main (the LED includes already define REG32).
    return includes + "\n" + boot_ctor, body


def _readme_idf(device: Device, lang: str = "c") -> str:
    """ESP-IDF project README: build/flash over UART — no OpenOCD, no SVDs."""
    led = device.facets.block_for("example_led") or {}
    gpio = led.get("gpio")
    cores = ", ".join(f"`{core.name}`" for core in device.cores)
    led_line = (
        f"- example: on-board LED on GPIO{gpio} ({led.get('active', 'high')} active)\n"
        if gpio is not None
        else ""
    )
    return f"""# {device.id}

Generated by **mu** from the `{device.id}` pack (v{device.version}), {lang}.

- cores: {cores}
{led_line}
## Build and flash

From the host — no toolchain needed, runs in the pinned image:

```sh
mu build --project-dir .
mu dev   --project-dir .     # interactive shell in the same image
```

This device has **no JTAG/probe**: flashing uses the ROM serial bootloader over
UART0, so `mu debug` is not available (AD-12).

1. Enter download mode: tie **GPIO0 to GND**, then pulse **RST**.
2. Flash the built images — the offsets come from the pack's `partitions` block:

```sh
mu flash --project-dir . \\
  --files build/bootloader/bootloader.bin \\
          build/partition_table/partition-table.bin \\
          build/{device.id}.bin
```

To watch the log, read the port as-is (`--no-reset`): this board has no
auto-reset circuit, so `idf.py monitor`'s reset attempt fails against a running
app. Press **RST** yourself to catch the boot banner:

```sh
idf.py -p /dev/ttyUSB0 monitor --no-reset
```

**Stop the monitor before flashing** (`Ctrl+]`): a monitor holds the serial port,
and `Flash` then fails with `Could not open /dev/ttyUSB0, the port is busy`.
Monitoring is deliberately its **own** task for that reason — a task that flashed
and then monitored would leave the port held, blocking the next flash.

## Expected behaviour

- The on-board LED blinks at ~2 Hz.
- The app logs over UART0 at 115200 8-N-1.
"""


def core_context(device: Device, core: Core, lang: str) -> dict:
    """Per-core substitution context (renderer-computed, template renders)."""
    facets = device.facets
    cpu = CPU_BY_CORE.get(core.name, core.name.lower())
    header = facets.config_header
    guard = re.sub(r"\W", "_", header).upper()
    example_includes, main_body = _main_sections(
        facets, device.cores[0].name == core.name
    )
    return {
        "project": device.id,
        "device_id": device.id,
        "version": device.version,
        "core": core.name,
        "arch": core.arch,
        "cpu": cpu,
        "cpu_flags": f"-mcpu={cpu} -mthumb",
        "fpu_flags": _fpu_flags(facets.fpu_mode, facets.fpu_variant),
        "define_flags": _define_flags(facets.define_for(core.name)),
        "linker_script": facets.linker_for(core.name, device.id),
        "cmsis_include": "vendor/CMSIS/CMSIS/Core/Include",
        "device_include": f"vendor/cmsis-device-{device.id}/Include",
        "startup_s": (
            f"vendor/cmsis-device-{device.id}/Source/Templates/gcc"
            f"/{facets.startup_for(core.name, device.id)}"
        ),
        "system_c": (
            f"vendor/cmsis-device-{device.id}/Source/Templates"
            f"/{facets.system_for(core.name, device.id)}"
        ),
        "config_header": header,
        "config_guard": guard,
        "config_library": facets.config_library,
        "config_defaults_source": facets.config_defaults_source,
        "lib_upper": re.sub(r"\W", "_", facets.config_library).upper(),
        # Stack compiler: link fallback for a core with no C++ sources.
        "compiler": "$(CXX)" if lang == "cpp" else "$(CC)",
        # req-032: the generated entry point follows the stack language, so a
        # cpp project gets src/main-<core>.cpp (compiled/linked as C++).
        "main_ext": "cpp" if lang == "cpp" else "c",
        # C++ flags are separate from CFLAGS_<core> so .c sources always
        # compile with $(CC) even on the cpp stack (req-031).
        "cxx_flags": " -std=c++17 -fno-exceptions -fno-rtti",
        "oc_interface": device.openocd.interface if device.openocd else "stlink.cfg",
        "oc_cfg_path": _oc_cfg_path(device),
        "oc_flash_args": _oc_flash_args(device),
        # Independent dual-core packs expose cpu0/cpu1; select this core for
        # program + boot check. cpu2_boot packs stay single-core (bug-032).
        "oc_target_line": _oc_target_line(device, core.name),
        # bug-027: the trailing reset is not reliable, so the flash recipe
        # carries the shared verify-and-retry tail for this core's flash bank.
        # A released sibling (cpu2_boot) cannot run until the primary releases
        # it, so its flash target must not claim "DID NOT BOOT" (bug-032).
        "boot_check_cmds": (
            ""
            if device.facets.cpu2_boot and device.cores[0].name != core.name
            else _boot_check_cmds(device, core.name)
        ),
        "oc_dual": bool(device.openocd and device.openocd.dual_core),
        "probe_transport": device.probe_ref.transport,
        "probe_address": device.probe_ref.address,
        "lang": lang,
        "example_includes": example_includes,
        "main_body": main_body,
    }


# --- C/C++ templates (authored fresh; sibling outputs were checklists) ---

_MAKEFILE_HEAD = Template(
    "# Makefile for $project — generated from pack $device_id v$version; do not edit by hand.\n"
    "# Toolchain: arm-none-eabi-gcc (see req-007 image). Per-core sections below;\n"
    "# `make build` / `make flash` / `make clean` drive every core.\n"
    "CC = arm-none-eabi-gcc\n"
    "CXX = arm-none-eabi-g++\n"
    "OBJCOPY = arm-none-eabi-objcopy\n"
    "SIZE = arm-none-eabi-size\n"
    "OPENOCD ?= openocd\n"
    "CMSIS_INC = -Ivendor/CMSIS/CMSIS/Core/Include -I$device_include\n"
    "CONFIG_INC = -Iconfig\n"
    "CONFIG_DEF = -DUSE_$config_guard\n"
    "\n"
    "# Project-owned extra/library sources (optional; never generated).\n"
    "#   EXTRA_SRCS_<core>     = third_party/lib/src/isr.cpp\n"
    "#   EXTRA_INC_<core>      = -Ithird_party/lib/include\n"
    "#   EXTRA_CFLAGS_<core>   = -DLIB_C_ONLY\n"
    "#   EXTRA_CXXFLAGS_<core> = -DLIB_CPP_ONLY\n"
    "# Included with -include so a project without the file still builds.\n"
    "-include config/sources.mk\n"
    "\n"
    "# Recursive wildcard: src/<core>/**/*.c at any depth. GNU make's own\n"
    "# wildcard treats ** as a single path segment, so recurse explicitly.\n"
    "rwildcard = $$(foreach d,$$(wildcard $$(1)*),$$(call rwildcard,$$(d)/,$$(2))"
    "$$(filter $$(subst *,%,$$(2)),$$(d)))\n"
    "\n"
)

_MAKEFILE_CORE = Template(
    "# --- core $core ($arch) ---\n"
    "TARGET_$core = $project-$core\n"
    "OUT_$core = build/$core/$$(TARGET_$core)\n"
    "CPU_FLAGS_$core = $cpu_flags\n"
    "FPU_FLAGS_$core = $fpu_flags\n"
    "EXTRA_SRCS_$core ?=\n"
    "# req-032: library include paths and per-suffix flags come from\n"
    "# config/sources.mk and are appended after the base flags. EXTRA_INC is\n"
    "# shared by C and C++ (it flows through CFLAGS); the suffix-specific\n"
    "# variables apply only to their compile rule.\n"
    "EXTRA_INC_$core ?=\n"
    "EXTRA_CFLAGS_$core ?=\n"
    "EXTRA_CXXFLAGS_$core ?=\n"
    "COMMON_FLAGS_$core = $$(CPU_FLAGS_$core) $$(FPU_FLAGS_$core) $define_flags "
    "$$(CMSIS_INC) $$(CONFIG_INC) $$(CONFIG_DEF) -Os -ffunction-sections -fdata-sections -g3 -Wall "
    "$$(EXTRA_INC_$core)\n"
    "CFLAGS_$core = $$(COMMON_FLAGS_$core) $$(EXTRA_CFLAGS_$core)\n"
    "CXXFLAGS_$core = $$(COMMON_FLAGS_$core)$cxx_flags $$(EXTRA_CXXFLAGS_$core)\n"
    "LDSCRIPT_$core = linker/$linker_script\n"
    "STARTUP_$core = $startup_s\n"
    "SYSTEM_C_$core = $system_c\n"
    "# Per-core discovery: the generated main file, this core's src/<core>/ tree,\n"
    "# the shared src/common/ tree, then project/library sources from\n"
    "# config/sources.mk. Deliberately no global src/* glob: dual-core packs must\n"
    "# never leak one core's sources into its sibling.\n"
    "SRCS_$core = src/main-$core.$main_ext \\\n"
    "            $$(call rwildcard,src/$core/,*.c) \\\n"
    "            $$(call rwildcard,src/$core/,*.cpp) \\\n"
    "            $$(call rwildcard,src/common/,*.c) \\\n"
    "            $$(call rwildcard,src/common/,*.cpp) \\\n"
    "            $$(EXTRA_SRCS_$core)\n"
    "# Objects mirror the full source path under build/$core/ (so src/M4/a.c ->\n"
    "# build/<core>/src/M4/a.o, and library sources keep their own path).\n"
    "OBJS_$core := $$(patsubst %.cpp,build/$core/%.o,$$(patsubst %.c,build/$core/%.o,"
    "$$(SRCS_$core))) build/$core/startup-$core.o build/$core/system-$core.o\n"
    "\n"
    "LINK_$core = $$(if $$(filter %.cpp,$$(SRCS_$core)),$$(CXX),$compiler)\n"
    "\n"
    "# Project sources: .c compiles with CC, .cpp with CXX. One target pattern\n"
    "# per suffix covers per-core, common, and extra sources outside src/.\n"
    "build/$core/%.o: %.c config/$config_header\n"
    "\t@mkdir -p $$(@D)\n"
    "\t$$(CC) $$(CFLAGS_$core) -c -o $$@ $$<\n"
    "\n"
    "build/$core/%.o: %.cpp config/$config_header\n"
    "\t@mkdir -p $$(@D)\n"
    "\t$$(CXX) $$(CXXFLAGS_$core) -c -o $$@ $$<\n"
    "\n"
    "# Vendor startup assembly stays in its submodule (see Startup/NOTE.md);\n"
    "# this rule assembles it straight from vendor/ — never copied.\n"
    "build/$core/startup-$core.o: $$(STARTUP_$core)\n"
    "\t@mkdir -p $$(@D)\n"
    "\t$$(CC) $$(CFLAGS_$core) -c -o $$@ $$<\n"
    "\n"
    "# Vendor system file (SystemInit) compiles from its submodule likewise.\n"
    "build/$core/system-$core.o: $$(SYSTEM_C_$core)\n"
    "\t@mkdir -p $$(@D)\n"
    "\t$$(CC) $$(CFLAGS_$core) -c -o $$@ $$<\n"
    "\n"
    "# Final artifacts land under build/$core/ — nothing generated at the root.\n"
    "$$(OUT_$core).elf: $$(OBJS_$core) $$(LDSCRIPT_$core)\n"
    "\t@mkdir -p $$(@D)\n"
    "\t$$(LINK_$core) $$(COMMON_FLAGS_$core) -T$$(LDSCRIPT_$core) -Wl,--gc-sections "
    "-Wl,-Map=$$(@:.elf=.map) --specs=nano.specs -o $$@ $$(OBJS_$core)\n"
    "\n"
    "$$(OUT_$core).hex: $$(OUT_$core).elf\n"
    "\t$$(OBJCOPY) -O ihex $$< $$@\n"
    "\n"
    "$$(OUT_$core).bin: $$(OUT_$core).elf\n"
    "\t$$(OBJCOPY) -O binary $$< $$@\n"
    "\n"
    "build-$core: $$(OUT_$core).elf $$(OUT_$core).hex $$(OUT_$core).bin\n"
    "\t$$(SIZE) $$(OUT_$core).elf\n"
    "\n"
    "flash-$core: build-$core\n"
    "\t$$(OPENOCD) $oc_flash_args$oc_target_line -c \"program $$(OUT_$core).elf verify reset\""
    " $boot_check_cmds -c \"exit\"\n"
    "\n"
    "clean-$core:\n"
    "\trm -rf build/$core\n"
    "\n"
)

_MAKEFILE_FOOT = Template(
    "${debug_section}"
    "ALL_BUILD = $build_targets\n"
    "ALL_FLASH = $flash_targets\n"
    "ALL_CLEAN = $clean_targets\n"
    "\n"
    "all: build\n"
    "\n"
    "build: $$(ALL_BUILD)\n"
    "\n"
    "flash: $$(ALL_FLASH)\n"
    "\n"
    "clean: $$(ALL_CLEAN)\n"
    "\n"
    ".PHONY: all build flash clean $phony\n"
)


def _sibling_debug_section(device: Device) -> str:
    """``make debug-<sibling>``: attach the released sibling (bug-030).

    A ``cpu2_boot`` pack is flashed single-core, so after ``make flash`` the
    second OpenOCD core does not exist. This target sources
    ``probe/dual-core.cfg`` **before** the target config and then **attaches**
    — examine + halt + reg, never ``reset``: a system reset cannot halt the
    released sibling (``AP write error, reset will not halt``, bug-024), and the
    primary's own release constructor has already released it (no boot bit is
    written here — bug-031).

    The argv is the measured working sequence. ``targets <t>`` selects the
    sibling as the current target so the generic commands (``halt``, ``reg``,
    ``resume``) act on it — they always act on the *first* target otherwise —
    and ``poll`` puts the target in a known state first, without which ``halt``
    reports "target was in unknown state". The run **resumes** and exits, so
    checking the sibling does not leave it stopped; drop the trailing ``resume``
    and ``exit`` (and run ``arm-none-eabi-gdb`` on
    ``build/<core>/<pack>-<core>.elf``) for an interactive session.
    """
    facts = _sibling_attach(device)
    if facts is None:
        return ""
    slug, sibling, target = facts
    args = _sibling_attach_args(device)
    elf = f"build/{sibling}/{device.id}-{sibling}.elf"
    return (
        "# --- attach the released sibling (bug-023/024/030) ---\n"
        "# `make flash` flashes single-core (the sibling is asleep at reset), so\n"
        f"# {target} does not exist afterwards. probe/dual-core.cfg must be\n"
        "# sourced BEFORE the target config (it reads DUAL_CORE while creating the\n"
        "# second core). ATTACH ONLY -- no reset: a system reset cannot halt the\n"
        "# released sibling (bug-024). Nothing here writes the boot bit: the\n"
        "# primary's release code (`mu_release_sibling` in C/C++, `__pre_init`\n"
        "# in Rust) already released the sibling (bug-031). `targets` selects the\n"
        "# sibling (the generic halt/reg/resume\n"
        "# otherwise act on the first target) and `poll` puts it in a known state\n"
        "# before halting. It resumes again on the way out, so this check leaves\n"
        f"# the board running; drop `resume`/`exit` to gdb {elf} instead.\n"
        f"SIBLING_OPENOCD = {args}\n"
        "\n"
        f"debug-{slug}:\n"
        f'\t$(OPENOCD) $(SIBLING_OPENOCD) -c "init" -c "{target} arp_examine" '
        f'-c "targets {target}" -c "poll" -c "halt" -c "reg pc" '
        '-c "resume" -c "exit"\n'
        "\n"
    )

_MAIN_C = Template(
    "/* $project / $core ($arch) — generated bring-up. */\n"
    "/* Reset flow: the vendor startup file ($startup_s, assembled from its\n"
    "   submodule — see Startup/NOTE.md) provides Reset_Handler, which runs\n"
    "   SystemInit and then calls main() below. This file owns application\n"
    "   init only. */\n"
    '#include "$config_header"\n'
    "$example_includes"
    "\n"
    "#ifndef USE_$config_guard\n"
    '#error "pack config header missing: build with -Iconfig (see config/OVERRIDES.md)"\n'
    "#endif\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "$main_body"
    "}\n"
)

_LINKER = Template(
    "/* $project / $core ($arch) — generated from the pack memory map. */\n"
    "/* Entry comes from the vendor startup file (see Startup/NOTE.md). */\n"
    "OUTPUT_FORMAT(\"elf32-littlearm\", \"elf32-bigarm\", \"elf32-littlearm\")\n"
    "OUTPUT_ARCH(arm)\n"
    "ENTRY(Reset_Handler)\n"
    "\n"
    "MEMORY\n"
    "{\n"
    "$regions\n"
    "}\n"
    "\n"
    "/* Stack top: end of the first RAM region. */\n"
    "_estack = ORIGIN($ram_region) + LENGTH($ram_region);\n"
    "_stack_start = _estack;\n"
    "\n"
    "SECTIONS\n"
    "{\n"
    "    .isr_vector :\n"
    "    {\n"
    "        KEEP(*(.isr_vector))\n"
    "        KEEP(*(.vectors))\n"
    "    } >$flash_region\n"
    "\n"
    "    /* Constructor/destructor arrays (bug-026). Placed after .isr_vector\n"
    "       and before .text so .data's LMA (AT(LOADADDR(.text) +\n"
    "       SIZEOF(.text))) does not overlap them. KEEP() survives\n"
    "       -Wl,--gc-sections, so __libc_init_array() still walks the\n"
    "       constructors (e.g. the cpu2_boot sibling release). */\n"
    "    .preinit_array :\n"
    "    {\n"
    "        PROVIDE_HIDDEN(__preinit_array_start = .);\n"
    "        KEEP(*(.preinit_array*))\n"
    "        PROVIDE_HIDDEN(__preinit_array_end = .);\n"
    "    } >$flash_region\n"
    "\n"
    "    .init_array :\n"
    "    {\n"
    "        PROVIDE_HIDDEN(__init_array_start = .);\n"
    "        KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))\n"
    "        KEEP(*(.init_array*))\n"
    "        PROVIDE_HIDDEN(__init_array_end = .);\n"
    "    } >$flash_region\n"
    "\n"
    "    .fini_array :\n"
    "    {\n"
    "        PROVIDE_HIDDEN(__fini_array_start = .);\n"
    "        KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*)))\n"
    "        KEEP(*(.fini_array*))\n"
    "        PROVIDE_HIDDEN(__fini_array_end = .);\n"
    "    } >$flash_region\n"
    "\n"
    "    .text :\n"
    "    {\n"
    "        *(.text*)\n"
    "        KEEP(*(.init))\n"
    "        KEEP(*(.fini))\n"
    "        *(.rodata*)\n"
    "        *(.ARM*)\n"
    "        . = ALIGN(4);\n"
    "    } >$flash_region\n"
    "\n"
    "    .data : AT(LOADADDR(.text) + SIZEOF(.text))\n"
    "    {\n"
    "        . = ALIGN(4);\n"
    "        _sdata = .;\n"
    "        *(.data*)\n"
    "        . = ALIGN(4);\n"
    "        _edata = .;\n"
    "        _sidata = LOADADDR(.data);\n"
    "    } >$ram_region\n"
    "\n"
    "    .bss :\n"
    "    {\n"
    "        . = ALIGN(4);\n"
    "        _sbss = .;\n"
    "        *(.bss*)\n"
    "        *(COMMON)\n"
    "        . = ALIGN(4);\n"
    "        _ebss = .;\n"
    "    } >$ram_region\n"
    "}\n"
)

_STARTUP_NOTE = Template(
    "# Startup assembly for $project\n"
    "\n"
    "The Reset_Handler / vector table live in ST's CMSIS-device startup file,\n"
    "which stays in its vendored submodule (disciplined vendoring, spike-002:\n"
    "submodule trees stay pristine — nothing is copied into this project).\n"
    "The Makefile assembles it in place via `STARTUP_<CORE>` and links the\n"
    "object with the application.\n"
    "\n"
    "## Per-core sources (pick the exact file the submodule ships)\n"
    "\n"
    "$rows\n"
    "Submodule filenames vary by family (e.g. `...xe.s` vs `...xg.s`); if the\n"
    "path above does not match, update the one `STARTUP_<CORE>` line in the\n"
    "Makefile — no other change is needed.\n"
    "\n"
    "## Reset flow\n"
    "\n"
    "`Reset_Handler` (startup) -> `SystemInit` (CMSIS system file) -> `main()`\n"
    "(`src/main-<CORE>.c`, or `.cpp` on a C++ stack). The linker script\n"
    "(`linker/`) places `.isr_vector` at the flash origin via\n"
    "`ENTRY(Reset_Handler)`.\n"
)

_CONFIG_H = Template(
    "/* $config_library defaults for $project — pack-owned copy, project wins. */\n"
    "/* Source of these defaults: $defaults_source (informational). To tune a\n"
    "   value, define it in your own project header BEFORE this file is read\n"
    "   (see config/OVERRIDES.md); every default below is guarded so a prior\n"
    "   definition always takes precedence. */\n"
    "#pragma once\n"
    "\n"
    "#ifndef $header_guard\n"
    "#define $header_guard\n"
    "\n"
    "#define ${lib_upper}_CONFIG_VERSION 1\n"
    "\n"
    "/* SysTick rate assumed by pack delay helpers. */\n"
    "#ifndef ${lib_upper}_TICK_HZ\n"
    "#define ${lib_upper}_TICK_HZ 1000\n"
    "#endif\n"
    "\n"
    "/* HSE crystal value assumed by the pack clock setup. */\n"
    "#ifndef ${lib_upper}_HSE_VALUE\n"
    "#define ${lib_upper}_HSE_VALUE 8000000\n"
    "#endif\n"
    "\n"
    "#endif /* $header_guard */\n"
)

_OVERRIDES = Template(
    "# Config overrides for $project\n"
    "\n"
    "Pack library: `$config_library` — defaults in `config/$config_header`\n"
    "(copied from `$defaults_source` at render time).\n"
    "\n"
    "## Order (project-file-wins)\n"
    "\n"
    "1. Your project header / definitions (highest precedence).\n"
    "2. Pack defaults in `config/$config_header` (fill the rest).\n"
    "\n"
    "Every default in the pack header is `#ifndef`-guarded, so defining a\n"
    "symbol first always wins — never edit the generated default in place\n"
    "for a whole-source replacement, hand the build your own header instead.\n"
    "\n"
    "## Wiring\n"
    "\n"
    "- C/C++: `-Iconfig` comes FIRST on the command line (before any vendor\n"
    "  include dir), so `#include \"$config_header\"` resolves here.\n"
    "  `-DUSE_$config_guard` selects this pack's config (the Makefile sets\n"
    "  both; `src/main-*` fails fast without the `-D`).\n"
    "- Rust: `build.rs` re-tracks `config/$config_header`\n"
    "  (`cargo:rerun-if-changed`) and declares `cfg($rust_cfg)` for\n"
    "  project-level selection; set it via `RUSTFLAGS=\"--cfg $rust_cfg\"`\n"
    "  when the project overrides a default. The header itself is\n"
    "  informational for Rust builds — the source of truth stays in code.\n"
)

# --- Rust templates (authored fresh; sibling outputs were checklists) ---

_CARGO = Template(
    "[package]\n"
    'name = "$project"\n'
    'version = "0.1.0"\n'
    'edition = "2021"\n'
    'rust-version = "$rust_version"\n'
    'build = "build.rs"\n'
    "\n"
    "# Pinned embedded deps (see RUST_PINS in the renderer; versions verified\n"
    "# against crates.io — exact `=` pins for reproducible renders).\n"
    "[dependencies]\n"
    'cortex-m = "$pin_cortex_m"\n'
    'cortex-m-rt = "$pin_cortex_m_rt"\n'
    'panic-halt = "$pin_panic_halt"\n'
    "\n"
    "[build-dependencies]\n"
    'flip-link = "$flip_link"\n'
    "\n"
    "[profile.dev]\n"
    "# no_std targets cannot unwind: abort is required on stable (bug-002).\n"
    'panic = "abort"\n'
    "opt-level = 0\n"
    "debug = true\n"
    "\n"
    "[profile.release]\n"
    'panic = "abort"\n'
    'opt-level = "z"\n'
    "codegen-units = 1\n"
    "lto = true\n"
    "debug = true\n"
    "\n"
    "# Flash via probe-rs (single-core) or OpenOCD (see probe/openocd.cfg):\n"
    "#   probe-rs run --chip <exact-part> target/$arch/release/$project\n"
)

_CARGO_CONFIG = Template(
    "# Generated by mu — pins cargo to this pack's Cortex-M target so that\n"
    "# `mu build` / `cargo build` select the right target with no extra flags.\n"
    "[build]\n"
    'target = "$arch"\n'
)

_MEMORY_X = Template(
    "/* $project memory.x — generated from the pack memory map. */\n"
    "/* cortex-m-rt's link script requires FLASH + RAM regions; dual-bank\n"
    "   packs keep their per-bank regions and gain same-origin aliases. */\n"
    "MEMORY\n"
    "{\n"
    "$regions\n"
    "}\n"
    "\n"
    "/* Stack top: end of RAM. */\n"
    "_stack_start = ORIGIN(RAM) + LENGTH(RAM);\n"
)

_BUILD_RS = Template(
    "//! $project build.rs — memory.x placement + link args + config wiring.\n"
    "//! Authored fresh (stdlib only, no build-script helpers needed).\n"
    "use std::env;\n"
    "use std::fs;\n"
    "use std::path::PathBuf;\n"
    "\n"
    "fn main() {\n"
    "    // Place memory.x where the linker always finds it (required for\n"
    "    // workspaces / non-trivial layouts; harmless otherwise).\n"
    "    let out = PathBuf::from(env::var(\"OUT_DIR\").unwrap());\n"
    "    fs::copy(\"memory.x\", out.join(\"memory.x\")).unwrap();\n"
    "    println!(\"cargo:rustc-link-search={}\", out.display());\n"
    "    // cortex-m-rt provides link.x; flip-link (see Cargo.toml) moves the\n"
    "    // stack below .bss at link time.\n"
    "    println!(\"cargo:rustc-link-arg=-Tlink.x\");\n"
    "    // Rebuild when the memory map or the pack config header changes.\n"
    "    println!(\"cargo:rerun-if-changed=memory.x\");\n"
    "    println!(\"cargo:rerun-if-changed=config/$config_header\");\n"
    "    // Declared project-level cfg for config selection (set it with\n"
    "    // RUSTFLAGS=\"--cfg $rust_cfg\" when overriding a pack default;\n"
    "    // see config/OVERRIDES.md).\n"
    "    println!(\"cargo:rustc-check-cfg=cfg($rust_cfg)\");\n"
    "}\n"
)

_MAIN_RS = Template(
    "//! $project ($arch) — generated no_std bring-up.\n"
    "//! Reset flow: cortex-m-rt links memory.x with this entry; the vector\n"
    "//! table comes from cortex-m-rt, the stack top from `_stack_start`.\n"
    "//! Pack config defaults live in config/$config_header (informational\n"
    "//! for Rust builds — see config/OVERRIDES.md).\n"
    "#![no_std]\n"
    "#![no_main]\n"
    "\n"
    "use cortex_m_rt::entry;\n"
    "use panic_halt as _;\n"
    "\n"
    "#[entry]\n"
    "fn main() -> ! {\n"
    "    // TODO: peripheral init.\n"
    "    loop {\n"
    "        cortex_m::asm::wfi();\n"
    "    }\n"
    "}\n"
)

def _probe_serial(device: Device) -> str:
    """``probe/probe-serial.cfg``: pin the probe by serial from MU_PROBE_SERIAL.

    Plain string (not ``Template``) because the TCL ``$::env`` would trip
    ``string.Template``. bug-018: containers pass the whole USB bus, so this is
    what selects the right probe when more than one is attached; unset/empty
    means "let OpenOCD pick" (single probe).
    """
    return (
        f"# {device.id} probe/probe-serial.cfg — pin the probe by serial (bug-018).\n"
        "# mu resolves a probe and sets MU_PROBE_SERIAL; the container passes the\n"
        "# whole USB bus, so this is what selects the right probe when more than one\n"
        "# is attached. Unset/empty means 'let OpenOCD pick' (single probe).\n"
        'if {[info exists ::env(MU_PROBE_SERIAL)] && $::env(MU_PROBE_SERIAL) ne ""} {\n'
        "    adapter serial $::env(MU_PROBE_SERIAL)\n"
        "}\n"
    )


def _readme(device: Device, lang: str, template_family: str = "") -> str:
    """Generated ``README.md``: the project's own build/flash/debug guide.

    Self-contained — the project may live outside the repo — so it restates the
    build/flash flow, expected behaviour, and troubleshooting instead of
    linking the repo docs. Dispatches on the resolved template family, so a
    stack documents its own tooling (AD-11).
    """
    if template_family == "idf-cmake":
        return _readme_idf(device, lang)
    cores = ", ".join(f"`{c.name}` ({c.arch})" for c in device.cores)
    primary = device.cores[0].name
    led = device.facets.example_led
    multi = len(device.cores) > 1

    head = [
        f"# {device.id}",
        "",
        f"Generated by **mu** from the `{device.id}` pack (v{device.version}), {lang}.",
        "",
        f"- cores: {cores}",
    ]
    if lang in ("c", "cpp"):
        if led is not None:
            head.append(
                f"- example: on-board LED P{led.port.upper()}{led.pin} "
                f"({led.active} active), blinking on `{primary}`"
            )
        if multi:
            head.append(
                "- sibling cores run a `volatile uint32_t counter` loop — watch it in "
                "the debugger (the LED example is primary-core only)"
            )
    head.append("")

    # bug-030: a released-sibling pack has no way to reach the sibling after
    # `make flash` (flashing is single-core, so the second OpenOCD core does not
    # exist). Document the generated attach target here.
    sibling = _sibling_attach(device) if lang in ("c", "cpp") else None
    if sibling is not None:
        slug, sibling_core, target = sibling
        attach_row = f"| Attach {sibling_core} | `make debug-{slug}` |"
        targets_extra = [attach_row]
        sibling_section = f"""
## Attaching the sibling core (`{sibling_core}`)

`make flash` programs this pack **single-core**: the `{sibling_core}` is asleep at
reset, so its AP writes would fail the flash reset. Two consequences:

- OpenOCD only creates `{target}` when `DUAL_CORE` is set, and
  `probe/dual-core.cfg` must be sourced **before** `{_oc_cfg_path(device)}` (the
  target reads `DUAL_CORE` while creating the second core). The `make flash`
  targets deliberately omit it, so after flashing `{target}` does not exist.
- The `{primary}` **releases** the sibling from its own `mu_release_sibling`
  constructor, so nothing here writes the boot bit: the sibling is attachable
  only *after* the `{primary}` has booted.

`make debug-{slug}` does exactly that — it sources `probe/dual-core.cfg` first and
then **attaches without any reset** (a system reset cannot halt the released
sibling, so the session is attach-only):

```sh
make debug-{slug}
```

The same session by hand, if you want a gdb server on it:

```sh
openocd {_sibling_attach_args(device)} -c "init" \\
  -c "{target} arp_examine" -c "targets {target}" -c "poll"
arm-none-eabi-gdb build/{sibling_core}/{device.id}-{sibling_core}.elf
```

`targets {target}` selects the sibling for the commands that follow — OpenOCD's
generic `halt`, `reg` and friends always act on the first target, which is the
`{primary}` — and `poll` puts it in a known state before halting.

Do **not** add `reset run` to either form: on a released sibling it fails with
`AP write error, reset will not halt` and OpenOCD then reports the probe as
lost (STLINK status `0x11`). In VS Code use `Debug {sibling_core} (OpenOCD)`,
which is attach-only for this pack.
"""
    else:
        targets_extra = []
        sibling_section = ""

    if lang in ("c", "cpp"):
        main_ext = "cpp" if lang == "cpp" else "c"
        main_compiler = "$(CXX)" if lang == "cpp" else "$(CC)"
        targets = "\n".join(
            [f"| Build | `make build` |", f"| Clean | `make clean` |", f"| Flash | `make flash` |"]
            + [f"| Flash {c.name} | `make flash-{c.name}` |" for c in device.cores]
            + targets_extra
        )
        body = f"""## Adding project sources

The generated Makefile discovers sources per core — no Makefile edit is needed:

| Path | Compiled into |
| --- | --- |
| `src/<core>/**/*.c`, `src/<core>/**/*.cpp` | that core only |
| `src/common/**/*.c`, `src/common/**/*.cpp` | every core |
| `src/main-<core>.{main_ext}` | that core (generated entry point) |

This is a `{lang}` project, so the generated entry point is
`src/main-<core>.{main_ext}` and it is compiled with `{main_compiler}`.
`.c` files compile with `$(CC)` and `.cpp` files with `$(CXX)`; a core that
contains a `.cpp` source is linked with `$(CXX)`. Sources never cross cores: a
file under `src/M4/` is not compiled into the M0+ (or M7) image.

For sources outside `src/` — a library ISR, for example — create the
project-owned `config/sources.mk`. `mu create` never writes or overwrites this
file (it is picked up with `-include`, so it is optional). It also carries
per-core include paths and flags, applied after the base flags:

```make
# config/sources.mk
EXTRA_SRCS_M4     = third_party/stm32-hw/src/drivers/adc_irq_wl55.cpp
EXTRA_INC_M4      = -Ithird_party/stm32-hw/include
EXTRA_CFLAGS_M4   = -DLIB_C_ONLY
EXTRA_CXXFLAGS_M4 = -DLIB_CPP_ONLY
```

- `EXTRA_SRCS_<core>` adds library source files for that core.
- `EXTRA_INC_<core>` adds include paths (`-I...`) to **both** C and C++ compiles.
- `EXTRA_CFLAGS_<core>` adds flags to `.c` compiles only.
- `EXTRA_CXXFLAGS_<core>` adds flags to `.cpp` compiles only.

Use the core's exact name in each variable (`EXTRA_SRCS_<core>`, ...), and
repeat the lines for each core that needs them. Objects land under
`build/<core>/`, mirroring the source path.

## Build and flash

In the dev container (this is what the VS Code tasks run):

| Task | Command |
| --- | --- |
{targets}

From the host — no toolchain needed, runs in the pinned image:

```sh
mu build --project-dir .
mu flash --project-dir . --serial <probe-serial>
```

## Debug in VS Code

`mu create --vscode` wrote `.vscode/`. Attach a window to the dev container
(*Dev Containers: Attach to Running Container*), open this folder, then `F5`:

| Config | What |
| --- | --- |
{chr(10).join(f"| `Debug {c.name} (OpenOCD)` | core `{c.name}` |" for c in device.cores)}
{'| `Debug ' + '+'.join(c.name for c in device.cores) + ' (OpenOCD)` | all cores at once (chained) |' if multi else ''}

Keys (VS Code defaults): `F5` continue · `F9` breakpoint · `F10` step over ·
`F11` step into · `Shift+F11` step out · `Shift+F5` stop · `Ctrl+Shift+F5` restart.
End a session with **Disconnect** (not Stop) to leave the firmware running.

The **Peripherals** view uses the pinned SVD in `probe/`.
{sibling_section}
## Expected behaviour

- The on-board LED blinks at **~2 Hz** (the delay is calibrated for a visible rate).
- Step **over** the delay loop (`F10`), not into it: it runs ~10^5–10^6 NOP
  iterations, so `F11` appears stuck.

## Probe selection

The dev container is given the whole USB bus, so the probe is selected by
**serial**: `mu` resolves it and sets `MU_PROBE_SERIAL`, which
`probe/probe-serial.cfg` turns into `adapter serial`. With several boards
attached, pass `--serial` (or `--vid/--pid`) — `mu` refuses to guess.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `GDB Server Quit Unexpectedly` | board unplugged, or a stale container — recreate it (`mu dev`) |
| `Protocol error with Rcmd: 01` on launch | regenerate with a current `mu` (HLA packs reject `cortex_m maskisr`) |
| `make: …: No such file or directory` (`Error 127`) | rebuild the image (`make images`); login shells need the PATH fix |
| debug attaches but source/step is wrong, or stepping never advances | regenerate with a current `mu` (per-core targeting / step fix) |

Regenerating means re-running `mu create --vscode` — the fixes live in the
generator, not in this project.
"""
    else:
        body = """## Build

```sh
mu build --project-dir .          # cargo build in the pinned image
```

## Notes

- The Rust path is bring-up only today (`#[entry]` + `wfi` loop); the VS Code
  integration (tasks, launch configs, register view) is C/C++-first.
- `memory.x` is generated from the pack memory map; `config/OVERRIDES.md`
  explains the config-header flow.
"""

    return "\n".join(head) + "\n" + body


def _dual_core_cfg(device: Device) -> str:
    """``probe/dual-core.cfg``: enable the pack's second OpenOCD core (bug-021).

    Sourced *before* the target config, which reads ``DUAL_CORE`` while creating
    the second core. Target-direct dual-core packs have no board file to set it,
    and emitting ``-c "set DUAL_CORE 1"`` after the target was too late — the
    second core never existed.
    """
    return (
        f"# {device.id} probe/dual-core.cfg — enable the second core (bug-021).\n"
        "# Sourced BEFORE the target config (it reads DUAL_CORE while creating\n"
        "# the second core); target-direct packs have no board file to set it.\n"
        "set DUAL_CORE 1\n"
    )


_OPENOCD = Template(
    "# $project probe/openocd.cfg — generated from pack openocd facts (spike-001).\n"
    "# Probe: $probe_transport ($probe_address).\n"
    "# Flash helper: openocd $oc_flash_args -c \"program <elf> verify reset exit\"\n"
    "source [find $interface]\n"
    "$dual_line$target_line\n"
)


def _render_openocd(device: Device) -> str:
    oc = device.openocd
    if oc is None:
        interface, target = "interface/stlink.cfg", "target/stm32f4x.cfg"
    else:
        interface, target = oc.config_files()
    dual = bool(oc and oc.dual_core)
    if dual and not (oc and oc.board):
        # Target-direct dual sessions (WL55JC): the target file only creates
        # the second core when DUAL_CORE is set (spike-001 finding 3).
        dual_line = "set DUAL_CORE 1\n"
    elif dual:
        dual_line = "# board cfg drives both cores (DUAL_CORE set by the board file)\n"
    else:
        dual_line = "# single-core session\n"
    return _OPENOCD.substitute(
        project=device.id,
        probe_transport=device.probe_ref.transport,
        probe_address=device.probe_ref.address,
        interface=interface,
        oc_flash_args=_oc_flash_args(device),
        dual_line=dual_line,
        target_line=f"source [find {target}]",
    )


def _regions_for(device: Device, core_name: str | None = None) -> tuple[MemoryRegion, ...]:
    """Memory regions visible to ``core_name`` (bug-014).

    A region tagged ``cores:`` belongs only to those cores; untagged regions are
    shared by every core, so single-core packs are unaffected. ``None`` returns
    every region (used by the Rust single-tree ``memory.x``).
    """
    if core_name is None:
        return tuple(device.memory)
    return tuple(m for m in device.memory if m.applies_to(core_name))


def _ld_regions(device: Device, core_name: str | None = None) -> str:
    lines = []
    for m in _regions_for(device, core_name):
        access = "rx" if "flash" in m.name.lower() else "rwx"
        lines.append(f"  {m.name.upper()} ({access}) : ORIGIN = 0x{m.origin:08X}, LENGTH = {m.size}")
    return "\n".join(lines)


def _first_region(regions: tuple[MemoryRegion, ...], want: str, fallback: str) -> str:
    for m in regions:
        if want in m.name.lower():
            return m.name.upper()
    return fallback


def _core_region(device: Device, core_name: str, want: str, fallback: str) -> str:
    """Per-core region: prefer a ``want`` region naming the core (M4 ->
    flash_m4 on dual-bank packs), else the first ``want`` region the core can
    see (shared single-region packs). Mirrors ``engine.verify.e2e.pick_region``."""
    regions = _regions_for(device, core_name)
    for m in regions:
        if want in m.name.lower() and core_name.lower() in m.name.lower():
            return m.name.upper()
    return _first_region(regions, want, fallback)


def _memoryx_regions(device: Device) -> str:
    regions = _regions_for(device)
    names = {m.name.upper() for m in regions}
    lines = [_ld_regions(device)]
    # cortex-m-rt link.x requires FLASH + RAM: alias the first matching bank
    # when no region carries the exact name (e.g. dual-bank H755).
    if "FLASH" not in names:
        first = _first_region(regions, "flash", regions[0].name.upper())
        src = next(m for m in regions if m.name.upper() == first)
        lines.append(f"  FLASH (rx) : ORIGIN = 0x{src.origin:08X}, LENGTH = {src.size}")
    if "RAM" not in names:
        first = _first_region(regions, "ram", regions[0].name.upper())
        src = next(m for m in regions if m.name.upper() == first)
        lines.append(f"  RAM (rwx) : ORIGIN = 0x{src.origin:08X}, LENGTH = {src.size}")
    return "\n".join(lines)


def _config_ctx(device: Device) -> dict:
    facets = device.facets
    header = facets.config_header
    return {
        "project": device.id,
        "config_library": facets.config_library,
        "config_header": header,
        "config_guard": re.sub(r"\W", "_", header).upper(),
        "header_guard": (re.sub(r"\W", "_", header).upper() + "_"),
        "lib_upper": re.sub(r"\W", "_", facets.config_library).upper(),
        "defaults_source": facets.config_defaults_source,
        "rust_cfg": re.sub(r"\W", "_", facets.config_library).lower() + "_project_config",
    }


_GITIGNORE = (
    "# Generated by mu — build outputs and tool logs.\n"
    "build/\n"
    ".mu/\n"
)

def _resume_on_detach(device: Device) -> str:
    """OpenOCD config that resumes the target when the debugger detaches.

    Stock OpenOCD leaves Cortex-M halted on detach (cortex-debug #894). F4-style
    target configs define ``_TARGETNAME`` (guarded so an undefined variable is a
    no-op, not an error that kills the server — bug-009); dual-core packs declare
    their OpenOCD target names (``openocd.targets``, bug-006), so the event is
    set on each explicitly.
    """
    header = (
        "# Generated by mu — resume the target when the debugger detaches.\n"
        "# Stock OpenOCD leaves Cortex-M halted on detach (cortex-debug #894).\n"
        "# End the session with 'Disconnect' (detach) to keep the firmware running;\n"
        "# plain 'Stop' disconnects without detach and leaves it halted.\n"
    )
    targets = [name for _core, name in device.openocd.targets] if device.openocd else []
    if targets:
        body = "".join(
            f"{name} configure -event gdb-detach {{ resume }}\n" for name in targets
        )
    else:
        body = (
            "# Guarded: some target configs (H7 DAP, WL) define no _TARGETNAME —\n"
            "# a no-op there rather than an error that quits the server.\n"
            "if {[info exists _TARGETNAME]} {\n"
            "    $_TARGETNAME configure -event gdb-detach { resume }\n"
            "}\n"
        )
    return header + body

_GCC_PROBLEM_MATCHER = {
    "owner": "cpp",
    "fileLocation": ["relative", "${workspaceFolder}"],
    "pattern": {
        "regexp": "^(.*):(\\d+):(\\d+):\\s+(warning|error):\\s+(.*)$",
        "file": 1,
        "line": 2,
        "column": 3,
        "severity": 4,
        "message": 5,
    },
}


#: Pinned SVD source (Apache-2.0), commit-pinned for reproducibility (req-017).
SVD_REPO = "modm-io/cmsis-svd-stm32"
SVD_SHA = "e79021accd49bf19bd0b16065f5471fb073ff3ac"


def _svd_local_name(path: str) -> str:
    return Path(path).name


def _svd_file_for(device: Device, core_name: str) -> str | None:
    for name, path in device.facets.svd:
        if name == core_name:
            return f"probe/{_svd_local_name(path)}"
    return None


def fetch_svds(device: Device, out_dir: str | Path, *, opener=None) -> list[Path]:
    """Download the pack's pinned SVD files into ``probe/`` (req-017)."""
    opener = opener or urllib.request.urlopen
    out = Path(out_dir)
    written: list[Path] = []
    for _core, path in device.facets.svd:
        dest = out / "probe" / _svd_local_name(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/{SVD_REPO}/{SVD_SHA}/{path}"
        try:
            with opener(url) as resp:
                dest.write_bytes(resp.read())
        except Exception as exc:
            raise VendorError(f"svd: failed to fetch {path} ({url}): {exc}") from exc
        written.append(dest)
    return written


# Cortex-M Rust target triples. OpenOCD's ``cortex_m`` command group (used by
# the bug-011 single-step workaround) only exists for Cortex-M targets, so the
# workaround must not be emitted for other architectures (bug-012).
_CORTEX_M_ARCH_PREFIXES = ("thumbv6m", "thumbv7m", "thumbv7em", "thumbv8m")


def _is_cortex_m(arch: str) -> bool:
    """True when ``arch`` is a Cortex-M Rust target triple."""
    return arch.startswith(_CORTEX_M_ARCH_PREFIXES)


def _processor_index(device: Device, core: Core, index: int) -> int:
    """OpenOCD processor index for ``core`` (bug-013).

    Prefers the pack's declared OpenOCD target name (``…cpuN``); falls back to
    the core's position in ``device.cores``, which matches OpenOCD's cpu0/cpu1
    creation order for the packs we ship.
    """
    oc = device.openocd
    if oc is not None:
        for name, target_name in oc.targets:
            if name == core.name:
                match = re.search(r"(\d+)$", target_name)
                if match:
                    return int(match.group(1))
    return index


def _cortex_m_maskisr_available(device: Device) -> bool:
    """True when the OpenOCD target is a ``cortex_m`` (DAP) target (bug-016).

    The bug-011 workaround uses ``cortex_m maskisr``, which only exists on
    DAP-based targets. HLA interfaces (``stlink.cfg`` -> ``hla_target``) reject
    it — ``invalid command name "cortex_m"`` — which aborts the gdb launch
    ("Protocol error with Rcmd: 01"). HLA targets don't need it either: their
    single-step already works.
    """
    interface = device.openocd.interface if device.openocd else ""
    return "dap" in interface.lower()


def _vscode_files(device: Device) -> dict[str, str]:
    """Generated ``.vscode/`` for the container-attached flow (req-016/017).

    Tool paths are the **in-container** locations (the window is attached to the
    ``mu dev`` container). ``launch.json`` is per-core, with the pack's resolved
    OpenOCD config files, each core's ELF, and its SVD for the register view.
    Built as JSON, never string-templated, so the output is always valid.
    """
    oc = device.openocd
    if oc is None:
        # No invented fallback (mirrors _oc_flash_args / linker_for).
        raise ValueError(
            f"pack {device.id!r} declares no openocd block; cannot render .vscode/"
        )
    iface, target = oc.config_files()
    gdb = "/opt/arm-gnu-toolchain/bin/arm-none-eabi-gdb"
    openocd = "/usr/local/bin/openocd"

    cores = list(device.cores)
    multi_core = len(cores) > 1

    # bug-023/024: a pack that must *release* its sibling (cpu2_boot) is debugged
    # by **attach only**. Launching runs `monitor reset halt`, and a system reset
    # cannot halt the sibling (`AP write error, reset will not halt`) — OpenOCD
    # then errors the whole command, and cortex-debug aborts with
    # 'Protocol error with Rcmd'. Attach (`monitor halt`) touches neither core's
    # reset state, so the released sibling stays accessible.
    attach_only = bool(device.facets.cpu2_boot)

    configurations = []
    for index, core in enumerate(device.cores):
        elf = f"build/{core.name}/{device.id}-{core.name}.elf"
        config = {
            "name": f"Debug {core.name} (OpenOCD)",
            "type": "cortex-debug",
            "request": "launch",
            "servertype": "openocd",
            "cwd": "${workspaceFolder}",
            "executable": "${workspaceFolder}/" + elf,
            "runToEntryPoint": "main",
            "configFiles": [
                iface,
                "probe/probe-serial.cfg",
                *(["probe/dual-core.cfg"] if oc.dual_core and not oc.board else []),
                target,
                # bug-031: no `probe/cpu2-boot.cfg` any more. It set the
                # sibling boot bit on examine-end, so the sibling looked
                # released in every session — masking bug-027 and invalidating
                # sibling-release measurements. The primary's release
                # constructor alone does it, and C2BOOT is a boot-request bit,
                # not a live gate. Attach-only (below) is what makes the
                # sibling reachable.
                "probe/resume-on-detach.cfg",
            ],
            "openocdPath": openocd,
            "gdbPath": gdb,
        }
        if attach_only:
            config["request"] = "attach"
            del config["runToEntryPoint"]
        # ops-022: F5 = build (+ flash) + debug. The primary does the real work —
        # attach configs never program the target, so they run the Flash task
        # first (its reset also releases the sibling); launch configs flash via
        # gdb `load` and only need a build. Siblings only build: they are also the
        # compound's chained children, and a chained child runs its own
        # preLaunchTask, so a Flash there would re-program and disturb the parent.
        config["preLaunchTask"] = ("Flash" if attach_only else "Build") if index == 0 else "Build"
        if multi_core:
            # bug-013: OpenOCD exposes one gdb server per core (…cpu0, …cpu1);
            # cortex-debug connects to the port for `targetProcessor`, so a
            # per-core config without it would attach every session to cpu0.
            config["numberOfProcessors"] = len(cores)
            config["targetProcessor"] = _processor_index(device, core, index)
        if _is_cortex_m(core.arch) and _cortex_m_maskisr_available(device):
            # bug-011: OpenOCD never advances the PC on a Cortex-M single-step
            # unless interrupts are masked for the duration of the step
            # (J-Link/ST-Link GDB servers do this by default; OpenOCD must be
            # told). `steponly` masks only during a step, so normal run keeps
            # interrupts enabled. These commands run after OpenOCD's
            # `reset halt` (target halted) and before `runToEntryPoint`.
            # bug-012: gated to Cortex-M — the `cortex_m` command group does
            # not exist on other architectures (e.g. RISC-V), where it would
            # error and abort the launch.
            # bug-016: and gated to DAP targets — HLA (`stlink.cfg` ->
            # `hla_target`) has no `cortex_m` group, so the command fails with
            # 'invalid command name "cortex_m"' and the launch aborts.
            # bug-023: attach configs run postAttachCommands, not postLaunchCommands.
            maskisr = ["monitor cortex_m maskisr steponly"]
            if config["request"] == "attach":
                config["postAttachCommands"] = maskisr
            else:
                config["postLaunchCommands"] = maskisr
        svd = _svd_file_for(device, core.name)
        if svd is not None:
            config["svdFile"] = "${workspaceFolder}/" + svd
        configurations.append(config)

    if multi_core:
        # bug-013: a compound config that starts OpenOCD once (primary = the
        # boot core, cores[0]) and shares it with the other cores, so both can
        # be debugged at once. OpenOCD shares one gdb server across the device's
        # cores, so the chained launches stay attached (`detached` false).
        compound = dict(configurations[0])
        compound["name"] = "Debug " + "+".join(c.name for c in cores) + " (OpenOCD)"
        compound["chainedConfigurations"] = {
            "enabled": True,
            "waitOnEvent": "postInit",
            "detached": False,
            "lifecycleManagedByParent": True,
            "launches": [
                {
                    "name": f"Debug {core.name} (OpenOCD)",
                    # bug-023: give the primary a moment to release the sibling
                    # before its attach config runs.
                    **({"delayMs": 1000} if attach_only else {}),
                }
                for core in cores[1:]
            ],
        }
        configurations.append(compound)

    tasks = [
        {
            "label": "Build",
            "type": "process",
            "command": "make",
            "args": ["build"],
            "group": {"kind": "build", "isDefault": True},
            "problemMatcher": _GCC_PROBLEM_MATCHER,
        },
        {
            "label": "Clean",
            "type": "process",
            "command": "make",
            "args": ["clean"],
            "problemMatcher": [],
        },
        {
            "label": "Flash",
            "type": "process",
            "command": "make",
            "args": ["flash"],
            "dependsOrder": "sequence",
            "dependsOn": ["Clean", "Build"],
        },
    ]
    for core in device.cores:
        tasks.append(
            {
                "label": f"Flash {core.name}",
                "type": "process",
                "command": "make",
                "args": [f"flash-{core.name}"],
                "problemMatcher": [],
            }
        )

    def j(obj: object) -> str:
        return json.dumps(obj, indent=2) + "\n"

    return {
        ".vscode/launch.json": j({"version": "0.2.0", "configurations": configurations}),
        ".vscode/tasks.json": j({"version": "2.0.0", "tasks": tasks}),
        ".vscode/settings.json": j(
            {"cortex-debug.gdbPath": gdb, "cortex-debug.openocdPath": openocd}
        ),
        ".vscode/extensions.json": j(
            {"recommendations": ["marus25.cortex-debug", "ms-vscode.cpptools"]}
        ),
    }


_IDF_ROOT_CMAKE = Template(
    "# $project project — generated by mu from the pack (task-015).\n"
    "cmake_minimum_required(VERSION 3.16)\n"
    "include($$ENV{IDF_PATH}/tools/cmake/project.cmake)\n"
    "project($project)\n"
)

_IDF_MAIN_CMAKE = Template(
    '# $project app component — generated by mu from the pack (task-015).\n'
    'idf_component_register(SRCS "$source"\n'
    '                       INCLUDE_DIRS ".")\n'
)

_IDF_MAIN_C = Template(
    "/* $project: on-board LED blink on GPIO$led_gpio ($led_active active).\n"
    " * Generated by mu from the pack (task-015); ESP-IDF app entry is app_main(). */\n"
    "#include <stdio.h>\n"
    '#include "freertos/FreeRTOS.h"\n'
    '#include "freertos/task.h"\n'
    '#include "driver/gpio.h"\n'
    "\n"
    "#define LED_GPIO $led_gpio\n"
    "\n"
    "void app_main(void)\n"
    "{\n"
    "    gpio_config_t io = {\n"
    "        .pin_bit_mask = (1ULL << LED_GPIO),\n"
    "        .mode = GPIO_MODE_OUTPUT,\n"
    "        .pull_up_en = GPIO_PULLUP_DISABLE,\n"
    "        .pull_down_en = GPIO_PULLDOWN_DISABLE,\n"
    "        .intr_type = GPIO_INTR_DISABLE,\n"
    "    };\n"
    "    gpio_config(&io);\n"
    "    printf(\"$project: blink on GPIO$led_gpio\\n\");\n"
    "    int n = 0;\n"
    "    while (1) {\n"
    "        gpio_set_level(LED_GPIO, $on_level);  /* on */\n"
    "        vTaskDelay(pdMS_TO_TICKS(500));\n"
    "        gpio_set_level(LED_GPIO, $off_level); /* off */\n"
    "        vTaskDelay(pdMS_TO_TICKS(500));\n"
    "        printf(\"$project: blink %d\\n\", ++n);\n"
    "    }\n"
    "}\n"
)

_IDF_MAIN_CPP = Template(
    "/* $project: on-board LED blink on GPIO$led_gpio ($led_active active).\n"
    " * Generated by mu from the pack (req-030); ESP-IDF app entry is app_main(). */\n"
    "#include <cstdio>\n"
    '#include "freertos/FreeRTOS.h"\n'
    '#include "freertos/task.h"\n'
    '#include "driver/gpio.h"\n'
    "\n"
    "#define LED_GPIO $led_gpio\n"
    "\n"
    'extern "C" void app_main(void)\n'
    "{\n"
    "    gpio_config_t io = {};\n"
    "    io.pin_bit_mask = (1ULL << LED_GPIO);\n"
    "    io.mode = GPIO_MODE_OUTPUT;\n"
    "    io.pull_up_en = GPIO_PULLUP_DISABLE;\n"
    "    io.pull_down_en = GPIO_PULLDOWN_DISABLE;\n"
    "    io.intr_type = GPIO_INTR_DISABLE;\n"
    "    gpio_config(&io);\n"
    "    std::printf(\"$project: blink on GPIO$led_gpio\\n\");\n"
    "    int n = 0;\n"
    "    while (true) {\n"
    "        gpio_set_level(static_cast<gpio_num_t>(LED_GPIO), $on_level);\n"
    "        vTaskDelay(pdMS_TO_TICKS(500));\n"
    "        gpio_set_level(static_cast<gpio_num_t>(LED_GPIO), $off_level);\n"
    "        vTaskDelay(pdMS_TO_TICKS(500));\n"
    "        std::printf(\"$project: blink %d\\n\", ++n);\n"
    "    }\n"
    "}\n"
)

_IDF_SDKCONFIG = Template(
    "# $project sdkconfig defaults — generated by mu from the pack (task-015).\n"
    'CONFIG_IDF_TARGET="$target"\n'
    "$flash_size_line"
)


def _vscode_files_idf(device: Device) -> dict[str, str]:
    """``.vscode/`` for the ESP-IDF flow (task-018): build / flash / monitor.

    Deliberately **no launch.json**: the classic ESP32 has no attach without
    external JTAG wired to the SD pins, so this flow is log-based
    (``req-022`` non-goals). The tasks drive ``idf.py`` in the dev container,
    which carries the IDF toolchain.
    """
    port = device.probe_ref.address
    # This board class has no auto-reset circuit, so `idf.py monitor`'s attempt
    # to reset the chip through the ROM fails and aborts the task (the sync gets
    # no answer while the app is running). Read the port as-is instead and press
    # RST yourself to catch the boot log.
    monitor = f"idf.py -p {port} monitor --no-reset"

    def j(obj: object) -> str:
        return json.dumps(obj, indent=2) + "\n"

    tasks = {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "Build",
                "type": "shell",
                "command": "idf.py build",
                "group": {"kind": "build", "isDefault": True},
                "problemMatcher": [],
            },
            {
                "label": "Flash",
                "type": "shell",
                "command": f"idf.py -p {port} flash",
                "problemMatcher": [],
            },
            {
                "label": "Monitor",
                "type": "shell",
                "command": monitor,
                "problemMatcher": [],
            },
            {
                "label": "Build + Flash",
                "type": "shell",
                "command": f"idf.py build && idf.py -p {port} flash",
                "problemMatcher": [],
            },
        ],
    }
    return {
        ".vscode/tasks.json": j(tasks),
        ".vscode/extensions.json": j({"recommendations": ["ms-vscode.cpptools"]}),
    }


def render(
    pack_model: Device, lang: str, out_dir: str | Path, *, vscode: bool = False
) -> list[Path]:
    """Render a project tree through the registered template family (req-028).

    The plan is derived once from the device; the family is selected by the
    resolved stack. No per-language branch lives here.
    """
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported lang {lang!r}; expected one of {SUPPORTED_LANGS}")
    stack_id = pack_model.stack_for(lang)
    if stack_id is None:
        declared = [declared_lang for declared_lang, _ in pack_model.stacks]
        raise ValueError(
            f"pack {pack_model.id!r} declares no build stack for language {lang!r} "
            f"(declared: {declared or 'none'})"
        )
    _ensure_stacks()
    stack = stack_spec(stack_id)
    plan = build_plan(pack_model)
    family = family_for(stack.template_family)
    return family.emit(
        pack_model, plan, Path(out_dir), RenderOptions(lang=lang, vscode=vscode)
    )


def _render_legacy(
    pack_model: Device, lang: str, out_dir: str | Path, *, vscode: bool = False
) -> list[Path]:
    """Legacy family body, temporarily retained behind the family port."""
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported lang {lang!r}; expected one of {SUPPORTED_LANGS}")
    # AD-11: the pack declares which build stack this language uses; the
    # resolved stack — not the language string — selects the template family.
    stack_id = pack_model.stack_for(lang)
    if stack_id is None:
        declared = [declared_lang for declared_lang, _ in pack_model.stacks]
        raise ValueError(
            f"pack {pack_model.id!r} declares no build stack for language {lang!r} "
            f"(declared: {declared or 'none'})"
        )
    _ensure_stacks()
    stack = stack_spec(stack_id)
    out = Path(out_dir)
    cfg = _config_ctx(pack_model)
    written: list[Path] = []

    def write(rel: str, text: str) -> None:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)

    # Resolved build stack (AD-11): persisted so verbs that load no pack
    # (`build`, `dev`) resolve the same image/build command.
    write(".mu/stack", stack_id + "\n")
    write(".gitignore", _GITIGNORE)
    write("README.md", _readme(pack_model, lang, stack.template_family))
    # AD-14: emit a tool artifact only when the model carries the fact.
    oc = pack_model.openocd
    if oc is not None:
        write("probe/openocd.cfg", _render_openocd(pack_model))
        # bug-018: containers pass the whole USB bus (replugs no longer break
        # them), so the probe is selected by serial from MU_PROBE_SERIAL. The
        # Makefile flash targets source it too.
        write("probe/probe-serial.cfg", _probe_serial(pack_model))
        if oc.dual_core and not oc.board:
            write("probe/dual-core.cfg", _dual_core_cfg(pack_model))
    # bug-031: probe/cpu2-boot.cfg is deliberately NOT emitted. It wrote the
    # sibling boot bit (C2BOOT) on the primary's examine-end, so every session
    # reported the sibling released even when the primary never booted — that
    # masked bug-027 and corrupted every sibling-release measurement. The
    # primary's mu_release_sibling constructor alone releases the sibling
    # (measured), and C2BOOT is a boot-request bit, not a live gate.
    # The VS Code flow is cortex-debug + OpenOCD for the Cortex stacks; the
    # ESP-IDF stack gets its own build/flash/monitor tasks (no debug).
    if vscode and lang in ("c", "cpp"):
        if oc is not None:
            written.extend(fetch_svds(pack_model, out))
            write("probe/resume-on-detach.cfg", _resume_on_detach(pack_model))
            for rel, text in _vscode_files(pack_model).items():
                write(rel, text)
        elif stack.template_family == "idf-cmake":
            for rel, text in _vscode_files_idf(pack_model).items():
                write(rel, text)
    # Config headers are a family-declared fact (the pack's config_headers block).
    if pack_model.facets.block_for("config_headers") is not None:
        write("config/OVERRIDES.md", _OVERRIDES.substitute(cfg))
        write(f"config/{cfg['config_header']}", _CONFIG_H.substitute(cfg))

    if stack.template_family == "c-cmsis":
        # req-032: cpp stacks get a C++ entry point; the same extension is used
        # by SRCS_<core>, so the .cpp rule compiles and links it with $(CXX).
        ext = "cpp" if lang == "cpp" else "c"
        sections: list[str] = []
        rows: list[str] = []
        for core in pack_model.cores:  # dual-core via iteration, no fork
            ctx = core_context(pack_model, core, lang)
            sections.append(_MAKEFILE_CORE.substitute(ctx))
            rows.append(f"- `{core.name}`: `{ctx['startup_s']}`")
            write(f"src/main-{core.name}.{ext}", _MAIN_C.substitute(ctx))
            # req-031: the documented source roots exist from the start, so a
            # user can drop src/<core>/foo.cpp or src/common/foo.c straight in.
            (out / "src" / core.name).mkdir(parents=True, exist_ok=True)
            flash_region = _core_region(pack_model, core.name, "flash", pack_model.memory[0].name.upper())
            ram_region = _core_region(pack_model, core.name, "ram", pack_model.memory[0].name.upper())
            write(
                f"linker/{ctx['linker_script']}",
                _LINKER.substitute(
                    project=ctx["project"],
                    core=ctx["core"],
                    arch=ctx["arch"],
                    regions=_ld_regions(pack_model, core.name),
                    flash_region=flash_region,
                    ram_region=ram_region,
                ),
            )
        (out / "src" / "common").mkdir(parents=True, exist_ok=True)
        head_ctx = core_context(pack_model, pack_model.cores[0], lang)
        # bug-023: flash the sibling(s) BEFORE the primary. The primary's reset
        # runs the release constructor, so flashing it first would boot the
        # sibling into a not-yet-programmed image (it double-faults and locks up).
        flash_order = (
            list(pack_model.cores[1:]) + [pack_model.cores[0]]
            if pack_model.facets.cpu2_boot
            else list(pack_model.cores)
        )
        sibling = _sibling_attach(pack_model)
        build_targets = " ".join(f"build-{c.name}" for c in pack_model.cores)
        flash_targets = " ".join(f"flash-{c.name}" for c in flash_order)
        clean_targets = " ".join(f"clean-{c.name}" for c in pack_model.cores)
        debug_targets = f"debug-{sibling[0]}" if sibling else ""
        write("Makefile", _MAKEFILE_HEAD.substitute(head_ctx) + "\n".join(sections) + _MAKEFILE_FOOT.substitute(
            build_targets=build_targets,
            flash_targets=flash_targets,
            clean_targets=clean_targets,
            phony=f"{build_targets} {flash_targets} {clean_targets} {debug_targets}".strip(),
            debug_section=_sibling_debug_section(pack_model),
        ))
        write("Startup/NOTE.md", _STARTUP_NOTE.substitute(project=pack_model.id, rows="\n".join(rows) + "\n"))
        # Vendor tree only when the pack declares vendored vendor files (a
        # family-declared fact, AD-14) — never inferred from the pack-id prefix.
        if pack_model.facets.startup:
            vendor(pack_model.id, pack_model.family, out)
    elif stack.template_family == "rust-cortex":  # single tree; memory.x covers every region
        arch = pack_model.cores[0].arch
        # bug-025: pin the build target so `mu build`/`cargo build` compile for
        # the Cortex-M arch instead of the host (the harness passed --target).
        write(".cargo/config.toml", _CARGO_CONFIG.substitute(arch=arch))
        write(
            "Cargo.toml",
            _CARGO.substitute(
                project=pack_model.id,
                arch=arch,
                rust_version=RUST_VERSION,
                pin_cortex_m=RUST_PINS["cortex-m"],
                pin_cortex_m_rt=RUST_PINS["cortex-m-rt"],
                pin_panic_halt=RUST_PINS["panic-halt"],
                flip_link=FLIP_LINK_PIN,
            ),
        )
        write("memory.x", _MEMORY_X.substitute(project=pack_model.id, regions=_memoryx_regions(pack_model)))
        write(
            "build.rs",
            _BUILD_RS.substitute(project=pack_model.id, config_header=cfg["config_header"], rust_cfg=cfg["rust_cfg"]),
        )
        write(
            "src/main.rs",
            _MAIN_RS.substitute(project=pack_model.id, arch=arch, config_header=cfg["config_header"]),
        )
    elif stack.template_family == "idf-cmake":
        # ESP-IDF app tree (task-015): CMake + sdkconfig, no CMSIS/OpenOCD.
        led = pack_model.facets.block_for("example_led") or {}
        gpio = led.get("gpio", 0)
        active = led.get("active", "high")
        on_level, off_level = (0, 1) if active == "low" else (1, 0)
        target = (pack_model.facets.block_for("sdkconfig") or {}).get("target", "")
        flash_size = (pack_model.facets.block_for("sdkconfig") or {}).get("flash_size", "")
        flash_size_line = (
            f"CONFIG_ESPTOOLPY_FLASHSIZE_{flash_size}=y\n" if flash_size else ""
        )
        ext = "cpp" if lang == "cpp" else "c"
        write("CMakeLists.txt", _IDF_ROOT_CMAKE.substitute(project=pack_model.id))
        write(
            "main/CMakeLists.txt",
            _IDF_MAIN_CMAKE.substitute(project=pack_model.id, source=f"main.{ext}"),
        )
        write(
            f"main/main.{ext}",
            (_IDF_MAIN_CPP if lang == "cpp" else _IDF_MAIN_C).substitute(
                project=pack_model.id,
                led_gpio=gpio,
                led_active=active,
                on_level=on_level,
                off_level=off_level,
            ),
        )
        write(
            "sdkconfig.defaults",
            _IDF_SDKCONFIG.substitute(
                project=pack_model.id, target=target, flash_size_line=flash_size_line
            ),
        )
    else:
        raise ValueError(
            f"no template family {stack.template_family!r} for build stack {stack_id!r}"
        )

    return sorted(written)


# Register the shipped families. Legacy modules import this module only inside
# ``emit``, so these bottom imports do not create a load-time cycle.
from engine.templates.families import idf_rust as _idf_rust_family  # noqa: E402,F401
from engine.templates.families import legacy as _legacy_families  # noqa: E402,F401
from engine.templates.families import rust_cortex_dual as _rust_dual_family  # noqa: E402,F401
from engine.templates.families import rust_cortex_single as _rust_single_family  # noqa: E402,F401
