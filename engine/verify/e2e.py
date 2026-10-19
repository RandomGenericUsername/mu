"""E2E build-proof harness (req-009): render all 9 cells, compile in images.

Mechanic (design.md, AD-7 stateless exec): render each ``(pack, lang)`` cell
to a scratch dir via :func:`engine.templates.renderer.render`, then
``docker run --platform linux/amd64`` per cell — ``make build`` in the
``lang-cpp`` image for C/C++, ``cargo build --target <arch>`` in the
``lang-rust`` image for Rust. Size assertions use the pack map loaded via
the loader (single source of truth, no duplicated numbers).

Vendor-stub note: rendered C/C++ trees reference the vendored CMSIS-device
startup assembly in place (disciplined vendoring — the submodule is never
copied, see ``Startup/NOTE.md``). The submodule is absent in scratch, so the
harness injects a minimal freestanding stub at each ``STARTUP_<CORE>`` path
(vector table + ``Reset_Handler`` -> ``SystemInit`` -> ``main``). Stubs stand
in for the external submodule only; application sources, flags, linker
scripts, and config headers under test are the genuine render output. Each
evidence-log cell records that stubs were injected.

Warnings policy: warn-only — recorded per cell, never failing a cell
(``docs/warnings-policy.md`` is the authoritative statement).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from engine.adapters import DefaultImageLookup, ImageLookup
from engine.adapters.toolchain import ensure_registered as _ensure_stacks
from engine.core.envelope import CONTAINER_PLATFORM, CONTAINER_RUNTIME
from engine.core.build_cells import (
    BuildEvidence,
    UnknownBuildCellError,
    build_cell_for,
    register_build_cell,
)
from engine.core.loader import load_file
from engine.core.model import Device, MemoryRegion
from engine.core.plan import build_plan
from engine.core.stacks import stack_spec
from engine.templates.renderer import core_context, render

__all__ = [
    "CELLS",
    "CellFailure",
    "CellResult",
    "ElfInfo",
    "assert_fits",
    "build_cpp_cell",
    "build_idf_cell",
    "build_idf_rust_cell",
    "build_rust_cell",
    "build_rust_dual_cell",
    "check_memory_x",
    "docker_run",
    "inject_vendor_stubs",
    "main",
    "parse_memory_x",
    "parse_size_output",
    "pick_region",
    "run_all",
    "write_evidence",
]
PACK_IDS = ("stm32f411re", "stm32h755", "stm32wl55jc", "esp32cam")
LANGS = ("c", "cpp", "rust")

PACKS_DIR = Path(__file__).resolve().parents[2] / "packs"
DEFAULT_EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "e2e-evidence.md"


def _declared_cells() -> tuple[tuple[str, str], ...]:
    """(pack, language) for every language a pack declares a stack for (AD-11).

    Derived from the packs' ``stacks`` maps rather than a fixed language list,
    so a pack that ships one language contributes one cell.
    """
    cells: list[tuple[str, str]] = []
    for pack_id in PACK_IDS:
        device = load_file(PACKS_DIR / f"{pack_id}.yaml")
        for lang in LANGS:
            if device.stack_for(lang):
                cells.append((pack_id, lang))
    return tuple(cells)


CELLS = _declared_cells()

DOCKER_PLATFORM = CONTAINER_PLATFORM
DOCKER_TIMEOUT_S = 1200  # amd64 emulation on ARM64 hosts is slow; per-cell budget

WARNING_RE = re.compile(r"warning", re.IGNORECASE)


class CellFailure(Exception):
    """A cell failed to build or to fit its pack map (names the cell)."""


@dataclass
class ElfInfo:
    path: str
    text: int = 0
    data: int = 0
    bss: int = 0
    flash_used: int = 0
    flash_avail: int = 0
    flash_region: str = ""
    ram_used: int = 0
    ram_avail: int = 0
    ram_region: str = ""
    # Rust cells: no in-image size run; host byte length, informational only.
    file_bytes: int | None = None


@dataclass
class CellResult:
    pack: str
    lang: str
    image: str
    #: Resolved build stack + its template family (AD-11/AD-15).
    stack: str = ""
    template_family: str = ""
    #: Shared, stack-neutral build evidence (AD-15); None until a build runs.
    build_evidence: "BuildEvidence | None" = None
    commands: list[str] = field(default_factory=list)
    exits: list[int] = field(default_factory=list)
    elfs: list[ElfInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = False
    note: str = ""


# --- vendor stubs (harness-owned stand-ins for the absent submodule) ---

VENDOR_STUB_S = """\
.syntax unified
.thumb
/* Harness stub for the vendored CMSIS-device startup file (req-009 e2e only).
   The real submodule provides Reset_Handler/SystemInit; this stands in so
   `make build` links without hardware vendor trees. */
.section .isr_vector,"a",%progbits
.word _estack
.word Reset_Handler
.text
.thumb_func
.weak SystemInit
.type SystemInit,%function
SystemInit:
bx lr
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
bl SystemInit
bl main
b .
"""


def inject_vendor_stubs(device: Device, out_dir: str | Path) -> list[str]:
    """Write one stub ``.s`` per core at its rendered ``STARTUP_<CORE>`` path."""
    out = Path(out_dir)
    stubs = []
    for core in device.cores:
        rel = core_context(device, core, "c")["startup_s"]
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(VENDOR_STUB_S)
        stubs.append(rel)
    return stubs


# --- size parsing + fit assertions (C/C++, pack map via loader) ---

_SIZE_LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*$")


def parse_size_output(output: str) -> tuple[int, int, int]:
    """Parse ``arm-none-eabi-size`` (Berkeley) output -> ``(text, data, bss)``."""
    for line in output.splitlines():
        match = _SIZE_LINE_RE.match(line)
        if match:
            return int(match.group(1)), int(match.group(2)), int(match.group(3))
    raise CellFailure(f"could not parse size output:\n{output.strip()[-500:]}")


def pick_region(memory: tuple[MemoryRegion, ...], core: str, want: str) -> MemoryRegion:
    """Map a core to its pack region: prefer a ``want`` region naming the core
    (e.g. M4 -> flash_m4 on dual-bank packs), else the first ``want`` region the
    core can see (single shared region packs). Honours per-core ``cores:``
    tagging so two cores never share one region (bug-014)."""
    cands = [m for m in memory if want in m.name.lower() and m.applies_to(core)]
    if not cands:
        raise CellFailure(f"pack has no {want!r} region for core {core!r}")
    for region in cands:
        if core.lower() in region.name.lower():
            return region
    return cands[0]


def assert_fits(device: Device, core: str, text: int, data: int, bss: int) -> ElfInfo:
    """Check ``text+data`` vs flash and ``data+bss`` vs RAM for one core ELF."""
    flash_used, ram_used = text + data, data + bss
    flash = pick_region(device.memory, core, "flash")
    ram = pick_region(device.memory, core, "ram")
    if flash_used > flash.size:
        raise CellFailure(
            f"{device.id}/{core}: flash overflow: used {flash_used} > "
            f"available {flash.size} ({flash.name})"
        )
    if ram_used > ram.size:
        raise CellFailure(
            f"{device.id}/{core}: ram overflow: used {ram_used} > "
            f"available {ram.size} ({ram.name})"
        )
    return ElfInfo(
        path=f"build/{core}/{device.id}-{core}.elf",
        text=text,
        data=data,
        bss=bss,
        flash_used=flash_used,
        flash_avail=flash.size,
        flash_region=flash.name,
        ram_used=ram_used,
        ram_avail=ram.size,
        ram_region=ram.name,
    )


# --- memory.x consistency (Rust, pack origins/lengths via loader) ---

_MEMX_RE = re.compile(
    r"(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*,"
    r"\s*LENGTH\s*=\s*(0x[0-9A-Fa-f]+|\d+)"
)


def _num(lit: str) -> int:
    return int(lit, 16 if lit.lower().startswith("0x") else 10)


def parse_memory_x(text: str) -> dict[str, tuple[int, int]]:
    """Parse a ``MEMORY {}`` block -> ``{REGION: (origin, length)}``."""
    regions = {}
    for match in _MEMX_RE.finditer(text):
        regions[match.group(1).upper()] = (_num(match.group(2)), _num(match.group(3)))
    return regions


def check_core_memory_x(device: Device, core: str, memx_text: str) -> list[str]:
    """A dual-core Rust ``memory.x`` carries only that core's FLASH/RAM."""
    got = parse_memory_x(memx_text)
    flash = pick_region(device.memory, core, "flash")
    ram = pick_region(device.memory, core, "ram")
    expected = {
        "FLASH": (flash.origin, flash.size),
        "RAM": (ram.origin, ram.size),
    }
    report = []
    for name, values in expected.items():
        if name not in got:
            raise CellFailure(f"{device.id}/{core}: memory.x missing {name}")
        if got[name] != values:
            raise CellFailure(
                f"{device.id}/{core}: memory.x {name} mismatch: got "
                f"origin=0x{got[name][0]:08X} length={got[name][1]}, pack has "
                f"origin=0x{values[0]:08X} length={values[1]}"
            )
        report.append(f"{core}/{name}: origin=0x{values[0]:08X} length={values[1]}")
    extra = set(got) - set(expected)
    if extra:
        raise CellFailure(
            f"{device.id}/{core}: memory.x carries foreign regions {sorted(extra)}"
        )
    return report


def check_memory_x(device: Device, memx_text: str) -> list[str]:
    """Every pack region SHALL appear in memory.x with identical origin/length;
    extra entries (FLASH/RAM aliases) SHALL duplicate a pack region's values."""
    got = parse_memory_x(memx_text)
    if not got:
        raise CellFailure(f"{device.id}: memory.x has no parseable MEMORY regions")
    report = []
    pack_names = {m.name.upper() for m in device.memory}
    pack_vals = {(m.origin, m.size) for m in device.memory}
    for region in device.memory:
        key = region.name.upper()
        if key not in got:
            raise CellFailure(f"{device.id}: memory.x missing region {key}")
        origin, length = got[key]
        if (origin, length) != (region.origin, region.size):
            raise CellFailure(
                f"{device.id}: memory.x {key} mismatch: got "
                f"origin=0x{origin:08X} length={length}, pack has "
                f"origin=0x{region.origin:08X} length={region.size}"
            )
        report.append(f"{key}: origin=0x{origin:08X} length={length} matches pack")
    for name, vals in got.items():
        if name not in pack_names and vals not in pack_vals:
            raise CellFailure(
                f"{device.id}: memory.x alias {name} matches no pack region"
            )
    return report


# --- docker execution ---


def docker_run(image: str, project_dir: str | Path, args: list[str],
               timeout: int = DOCKER_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    cmd = [
        CONTAINER_RUNTIME, "run", "--rm", "--platform", DOCKER_PLATFORM,
        "-v", f"{Path(project_dir).resolve()}:/work", "-w", "/work", image, *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _combined(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def _warnings(text: str) -> list[str]:
    return [line for line in text.splitlines() if WARNING_RE.search(line)]


# --- per-cell builders ---


def render_cell(pack_id: str, lang: str, root: str | Path) -> tuple[Device, Path]:
    device = load_file(PACKS_DIR / f"{pack_id}.yaml")
    out = Path(root) / f"{pack_id}-{lang}"
    if out.exists():
        shutil.rmtree(out)
    render(device, lang, out)
    return device, out


def build_cpp_cell(device: Device, out: Path, image: str) -> CellResult:
    res = CellResult(pack=device.id, lang="", image=image)
    stubs = inject_vendor_stubs(device, out)
    res.note = f"vendor stubs injected: {', '.join(stubs)}"
    proc = docker_run(image, out, ["make", "build"])
    res.commands.append(f"make build (in {image})")
    res.exits.append(proc.returncode)
    combined = _combined(proc)
    res.warnings.extend(_warnings(combined))
    if proc.returncode != 0:
        res.note += f"; BUILD FAILED:\n{combined.strip()[-3000:]}"
        return res
    for core in device.cores:
        elf = f"build/{core.name}/{device.id}-{core.name}.elf"
        size_proc = docker_run(image, out, ["arm-none-eabi-size", "-B", elf])
        res.commands.append(f"arm-none-eabi-size -B {elf}")
        res.exits.append(size_proc.returncode)
        if size_proc.returncode != 0:
            raise CellFailure(f"{device.id}/{core.name}: size failed: {_combined(size_proc).strip()[-500:]}")
        text, data, bss = parse_size_output(_combined(size_proc))
        res.elfs.append(assert_fits(device, core.name, text, data, bss))
    res.ok = True
    return res


def build_rust_cell(device: Device, out: Path, image: str) -> CellResult:
    res = CellResult(pack=device.id, lang="", image=image)
    target = device.cores[0].arch
    proc = docker_run(image, out, ["cargo", "build", "--target", target])
    res.commands.append(f"cargo build --target {target} (in {image})")
    res.exits.append(proc.returncode)
    combined = _combined(proc)
    res.warnings.extend(_warnings(combined))
    if proc.returncode != 0:
        res.note = f"BUILD FAILED:\n{combined.strip()[-3000:]}"
        return res
    elf = out / "target" / target / "debug" / device.id
    if not elf.is_file():
        raise CellFailure(f"{device.id}: expected ELF {elf.relative_to(out)} missing after build")
    rel = elf.relative_to(out).as_posix()
    res.elfs.append(ElfInfo(path=rel, file_bytes=elf.stat().st_size))
    res.note = "; ".join(check_memory_x(device, (out / "memory.x").read_text()))
    res.ok = True
    return res


def build_rust_dual_cell(device: Device, out: Path, image: str) -> CellResult:
    """Build every core package via the generated Makefile (req-028)."""
    res = CellResult(pack=device.id, lang="", image=image)
    proc = docker_run(image, out, ["make", "build"])
    res.commands.append(f"make build (in {image})")
    res.exits.append(proc.returncode)
    combined = _combined(proc)
    res.warnings.extend(_warnings(combined))
    if proc.returncode != 0:
        res.note = f"BUILD FAILED:\n{combined.strip()[-3000:]}"
        return res

    reports: list[str] = []
    for core in build_plan(device).cores:
        elf_rel = f"build/{core.name}/{device.id}-{core.name}.elf"
        elf = out / elf_rel
        if not elf.is_file():
            raise CellFailure(f"{device.id}/{core.name}: expected ELF {elf_rel} missing")
        size_proc = docker_run(image, out, ["size", "-B", elf_rel])
        res.commands.append(f"size -B {elf_rel}")
        res.exits.append(size_proc.returncode)
        if size_proc.returncode != 0:
            raise CellFailure(
                f"{device.id}/{core.name}: size failed: "
                f"{_combined(size_proc).strip()[-500:]}"
            )
        text, data, bss = parse_size_output(_combined(size_proc))
        res.elfs.append(assert_fits(device, core.name, text, data, bss))
        reports += check_core_memory_x(
            device, core.name, (out / core.slug / "memory.x").read_text()
        )
    res.note = "; ".join(reports)
    res.ok = True
    return res


#: IDF reports the factory partition size in its build output; that is the
#: authoritative fit bound (no ``arm-none-eabi-size`` for an xtensa app).
_APP_PARTITION_RE = re.compile(r"Smallest app partition is (0x[0-9A-Fa-f]+) bytes")

#: ESP32-CAM app bank: 4 MiB flash minus the 0x10000 app offset (same value
#: espflash reports: 4,128,768 B).
_IDF_RUST_APP_AVAIL = 4 * 1024 * 1024 - 0x10000


def build_idf_cell(device: Device, out: Path, image: str) -> CellResult:
    """Build an ESP-IDF app in its stack image (AD-15): assert the triple + fit.

    The ESP32 artifacts are ``.bin`` images, so the fit check is partition
    offsets/sizes (from IDF's own report), never ELF section sizes.
    """
    res = CellResult(pack=device.id, lang="", image=image)
    proc = docker_run(image, out, ["bash", "-lc", "idf.py build"])
    res.commands.append(f"idf.py build (in {image})")
    res.exits.append(proc.returncode)
    combined = _combined(proc)
    res.warnings.extend(_warnings(combined))
    if proc.returncode != 0:
        res.note = f"BUILD FAILED:\n{combined.strip()[-3000:]}"
        return res

    artifacts = {
        "bootloader": out / "build" / "bootloader" / "bootloader.bin",
        "partition_table": out / "build" / "partition_table" / "partition-table.bin",
        "app": out / "build" / f"{device.id}.bin",
    }
    for name, path in artifacts.items():
        if not path.is_file():
            raise CellFailure(
                f"{device.id}: expected {name} artifact missing: "
                f"{path.relative_to(out).as_posix()}"
            )

    match = _APP_PARTITION_RE.search(combined)
    if match is None:
        raise CellFailure(f"{device.id}: IDF did not report the app partition size")
    app_avail = int(match.group(1), 16)
    app_size = artifacts["app"].stat().st_size
    if app_size > app_avail:
        raise CellFailure(
            f"{device.id}: app overflow: {app_size} > {app_avail} (factory partition)"
        )

    for name, path in artifacts.items():
        rel = path.relative_to(out).as_posix()
        size = path.stat().st_size
        if name == "app":
            res.elfs.append(
                ElfInfo(
                    path=rel,
                    text=size,
                    file_bytes=size,
                    flash_used=size,
                    flash_avail=app_avail,
                    flash_region="factory",
                )
            )
        else:
            res.elfs.append(ElfInfo(path=rel, file_bytes=size))
    res.note = (
        f"app {app_size} B / {app_avail} B factory partition; "
        f"triple: {', '.join(path.name for path in artifacts.values())}"
    )
    res.ok = True
    return res


def build_idf_rust_cell(device: Device, out: Path, image: str) -> CellResult:
    """Build an ESP-IDF Rust app and check it fits the app bank (req-030)."""
    res = CellResult(pack=device.id, lang="", image=image)
    env = ". /home/esp/export-esp.sh"
    proc = docker_run(image, out, ["bash", "-lc", f"{env}; cargo build"])
    res.commands.append(f"cargo build (in {image})")
    res.exits.append(proc.returncode)
    combined = _combined(proc)
    res.warnings.extend(_warnings(combined))
    if proc.returncode != 0:
        res.note = f"BUILD FAILED:\n{combined.strip()[-3000:]}"
        return res

    target = "xtensa-esp32-espidf"
    elf_rel = f"target/{target}/debug/{device.id}"
    elf = out / elf_rel
    if not elf.is_file():
        raise CellFailure(f"{device.id}: expected ELF {elf_rel} missing after build")

    size_proc = docker_run(
        image, out, ["bash", "-lc", f'{env}; xtensa-esp32-elf-size -B "{elf_rel}"']
    )
    res.commands.append(f"xtensa-esp32-elf-size -B {elf_rel}")
    res.exits.append(size_proc.returncode)
    if size_proc.returncode != 0:
        raise CellFailure(
            f"{device.id}: size failed: {_combined(size_proc).strip()[-500:]}"
        )
    text, data, bss = parse_size_output(_combined(size_proc))
    used = text + data
    if used > _IDF_RUST_APP_AVAIL:
        raise CellFailure(
            f"{device.id}: app overflow: {used} > {_IDF_RUST_APP_AVAIL} (app bank)"
        )
    res.elfs.append(
        ElfInfo(
            path=elf_rel,
            text=text,
            data=data,
            bss=bss,
            flash_used=used,
            flash_avail=_IDF_RUST_APP_AVAIL,
            flash_region="app",
        )
    )
    res.note = f"app {used} B / {_IDF_RUST_APP_AVAIL} B app bank"
    res.ok = True
    return res


# AD-15: the shipped stacks register their builders — the harness owns the build
# mechanics, core owns the registry. A third build system registers here (or in
# its own module) and never edits ``run_all``.
register_build_cell("c-cmsis", build_cpp_cell)
register_build_cell("rust-cortex", build_rust_cell)
register_build_cell("rust-cortex-dual", build_rust_dual_cell)
register_build_cell("idf-cmake", build_idf_cell)
register_build_cell("esp-idf-rust", build_idf_rust_cell)


def _envelope(res: CellResult, stack_id: str, template_family: str) -> BuildEvidence:
    """Assemble the shared, stack-neutral build evidence for a cell (AD-15)."""
    artifacts = tuple(
        (elf.path, elf.file_bytes)
        for elf in res.elfs
        if elf.file_bytes is not None
    )
    fits = tuple(
        (elf.flash_region, f"{elf.flash_used}/{elf.flash_avail}")
        for elf in res.elfs
        if elf.flash_avail
    ) + tuple(
        (elf.ram_region, f"{elf.ram_used}/{elf.ram_avail}")
        for elf in res.elfs
        if elf.ram_avail
    )
    return BuildEvidence(
        stack=stack_id,
        template_family=template_family,
        commands=tuple(res.commands),
        exits=tuple(res.exits),
        artifacts=artifacts,
        fits=fits,
    )


def run_all(
    root: str | Path,
    lookup: ImageLookup | None = None,
    *,
    only: tuple[str, ...] | None = None,
) -> list[CellResult]:
    lookup = lookup or DefaultImageLookup()
    _ensure_stacks()
    results = []
    for pack_id, lang in CELLS:
        if only is not None and pack_id not in only:
            continue
        device, out = render_cell(pack_id, lang, root)
        # AD-11: the pack-declared stack resolves the toolchain image.
        stack_id = device.stack_for(lang)
        image = lookup.image_for(stack_id)
        template_family = stack_spec(stack_id).template_family
        try:
            # AD-15: the builder is selected by the stack's template family, so
            # a third build system registers rather than editing this dispatch.
            builder = build_cell_for(template_family)
            res = builder(device, out, image)
            res.lang = lang
            res.stack = stack_id
            res.template_family = template_family
            if res.ok:
                res.build_evidence = _envelope(res, stack_id, template_family)
        except CellFailure as exc:
            res = CellResult(pack=pack_id, lang=lang, image=image, stack=stack_id,
                             template_family=template_family, ok=False, note=str(exc))
        except UnknownBuildCellError as exc:
            res = CellResult(pack=pack_id, lang=lang, image=image, stack=stack_id,
                             template_family=template_family, ok=False, note=str(exc))
        except subprocess.TimeoutExpired:
            res = CellResult(pack=pack_id, lang=lang, image=image, stack=stack_id,
                             template_family=template_family, ok=False,
                             note=f"cell timed out after {DOCKER_TIMEOUT_S}s")
        results.append(res)
    return results


# --- evidence log ---


def write_evidence(results: list[CellResult], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    green = sum(1 for r in results if r.ok)
    lines = [
        f"# E2E build evidence (req-009) — {green}/{len(results)} cells green",
        "",
        "Rendered trees compile in the pinned images with zero host deps.",
        "C/C++ cells inject harness-owned vendor stubs (see module docstring);",
        "warnings are recorded per cell and never fail (warn-only policy).",
        "",
    ]
    for res in results:
        status = "PASS" if res.ok else "FAIL"
        lines += [f"## {res.pack} / {res.lang} — {status}", ""]
        lines += [f"- image: `{res.image}`"]
        if res.stack:
            lines.append(f"- stack: `{res.stack}` (template family `{res.template_family}`)")
        if res.build_evidence is not None:
            evidence = "; ".join(f"{k}={v}" for k, v in res.build_evidence.as_dict().items())
            lines.append(f"- build evidence: `{evidence}`")
        for cmd, code in zip(res.commands, res.exits):
            lines.append(f"- cmd `{cmd}` -> exit {code}")
        if res.note:
            lines.append(f"- note: {res.note.splitlines()[0]}")
        for elf in res.elfs:
            if elf.file_bytes is not None and not elf.flash_avail:
                lines.append(f"- `{elf.path}`: {elf.file_bytes} bytes (host stat, informational)")
            else:
                lines += [
                    f"- `{elf.path}`: text={elf.text} data={elf.data} bss={elf.bss}",
                    f"  - flash: used {elf.flash_used} / avail {elf.flash_avail} ({elf.flash_region})",
                    f"  - ram: used {elf.ram_used} / avail {elf.ram_avail} ({elf.ram_region})",
                ]
        warn_block = "\n".join(f"    {w}" for w in res.warnings) or "    (none)"
        lines += ["- warnings:", warn_block, ""]
        if not res.ok and "\n" in res.note:
            lines += ["<details><summary>failure log</summary>", "", "```",
                      res.note, "```", "</details>", ""]
    out.write_text("\n".join(lines))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="e2e build proof: render every declared cell, compile in its stack image"
    )
    parser.add_argument("--workdir", default=None, help="scratch root (default: fresh mkdtemp)")
    parser.add_argument("--only", default=None, help="comma-separated pack ids to run")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE), help="evidence markdown path")
    parser.add_argument("--keep", action="store_true", help="keep scratch trees")
    args = parser.parse_args(argv)
    tmp = args.workdir or tempfile.mkdtemp(prefix="req009-e2e-")
    only = tuple(p for p in (args.only or "").split(",") if p) or None
    results = run_all(tmp, only=only)
    write_evidence(results, args.evidence)
    for res in results:
        print(f"[{'PASS' if res.ok else 'FAIL'}] {res.pack}/{res.lang} "
              f"exits={res.exits} elfs={[e.path for e in res.elfs]} warnings={len(res.warnings)}")
    if not args.keep and not args.workdir:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [f"{r.pack}/{r.lang}" for r in results if not r.ok]
    if failed:
        print(f"FAILED cells: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"{len(results)}/{len(results)} green; evidence -> {args.evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
