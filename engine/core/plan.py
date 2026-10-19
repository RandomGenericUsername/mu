"""Project plan: the domain facts every template family emits from (req-028).

The plan is derived once from the certified ``Device``. It carries the per-core
memory/example/release/debug facts, the released-sibling attach facts, and the
flash order — so the C/C++ and Rust families cannot drift. No tool names, paths,
or raw YAML live here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from engine.core.model import Device, ExampleLed, MemoryRegion

__all__ = [
    "CorePlan",
    "DebugCorePlan",
    "DebugPlan",
    "ConfigPlan",
    "FlashPlan",
    "ProbePlan",
    "ProjectPlan",
    "SiblingPlan",
    "build_plan",
    "core_slug",
]


def core_slug(name: str) -> str:
    """Shell/dir-safe core slug: ``M0+`` -> ``m0plus``, ``CM4`` -> ``cm4``."""
    lowered = name.lower().replace("+", "plus")
    return "".join(ch for ch in lowered if ch.isalnum())


def _regions_for(device: Device, core: str) -> tuple[MemoryRegion, ...]:
    return tuple(r for r in device.memory if r.applies_to(core))


def _region_for(device: Device, core: str, want: str) -> MemoryRegion | None:
    """Per-core ``want`` region: a region naming the core wins, else first visible.

    Families that need a flash/RAM pairing raise when it is absent; families
    that do not (e.g. ESP-IDF) still get a plan.
    """
    candidates = [r for r in _regions_for(device, core) if want in r.name.lower()]
    if not candidates:
        return None
    for region in candidates:
        if core.lower() in region.name.lower():
            return region
    return candidates[0]


def _target_for(device: Device, core: str) -> str | None:
    if device.openocd is None:
        return None
    for name, target in device.openocd.targets:
        if name == core:
            return target
    return None


def _processor_index(device: Device, core: str, fallback: int) -> int:
    target = _target_for(device, core)
    if target is not None:
        match = re.search(r"(\d+)$", target)
        if match:
            return int(match.group(1))
    return fallback


def _svd_for(device: Device, core: str) -> str | None:
    for name, path in device.facets.svd:
        if name == core:
            return path
    return None


@dataclass(frozen=True)
class CorePlan:
    name: str
    slug: str
    arch: str
    flash: MemoryRegion | None
    ram: MemoryRegion | None
    is_primary: bool
    example_led: ExampleLed | None
    release_writes: tuple[tuple[int, int, int | None], ...]
    openocd_target: str | None
    processor_index: int
    svd_path: str | None


@dataclass(frozen=True)
class SiblingPlan:
    slug: str
    core: str
    openocd_target: str


@dataclass(frozen=True)
class FlashPlan:
    order: tuple[str, ...]
    single_core: bool
    boot_check_core: str
    dual_core: bool


@dataclass(frozen=True)
class DebugCorePlan:
    core: str
    processor_index: int
    svd_path: str | None
    elf: str


@dataclass(frozen=True)
class DebugPlan:
    attach_only: bool
    config_files: tuple[str, str] | None
    cores: tuple[DebugCorePlan, ...]


@dataclass(frozen=True)
class ConfigPlan:
    library: str
    header: str
    defaults_source: str


@dataclass(frozen=True)
class ProbePlan:
    transport: str
    address: str


@dataclass(frozen=True)
class ProjectPlan:
    device_id: str
    version: str
    family: str
    cores: tuple[CorePlan, ...]
    sibling: SiblingPlan | None
    flash: FlashPlan
    debug: DebugPlan
    config: ConfigPlan
    probe: ProbePlan

    @property
    def primary(self) -> CorePlan:
        return self.cores[0]

    @property
    def siblings(self) -> tuple[CorePlan, ...]:
        return self.cores[1:]


def _sibling(device: Device) -> SiblingPlan | None:
    oc = device.openocd
    if oc is None or not oc.dual_core or oc.board or not device.facets.cpu2_boot:
        return None
    if len(device.cores) < 2:
        return None
    sibling = device.cores[1]
    target = _target_for(device, sibling.name)
    if target is None:
        return None
    return SiblingPlan(core_slug(sibling.name), sibling.name, target)


def build_plan(device: Device) -> ProjectPlan:
    """Derive the immutable project plan from the certified device."""
    primary = device.cores[0].name
    cores: list[CorePlan] = []
    for index, core in enumerate(device.cores):
        cores.append(
            CorePlan(
                name=core.name,
                slug=core_slug(core.name),
                arch=core.arch,
                flash=_region_for(device, core.name, "flash"),
                ram=_region_for(device, core.name, "ram"),
                is_primary=index == 0,
                example_led=device.facets.example_led if index == 0 else None,
                release_writes=(
                    tuple(device.facets.cpu2_boot) if index == 0 else ()
                ),
                openocd_target=_target_for(device, core.name),
                processor_index=_processor_index(device, core.name, index),
                svd_path=_svd_for(device, core.name),
            )
        )

    order = (
        tuple(c.name for c in device.cores[1:]) + (primary,)
        if device.facets.cpu2_boot
        else tuple(c.name for c in device.cores)
    )
    flash = FlashPlan(
        order=order,
        single_core=bool(device.facets.cpu2_boot),
        boot_check_core=order[-1],
        dual_core=bool(device.openocd and device.openocd.dual_core),
    )
    debug = DebugPlan(
        attach_only=bool(device.facets.cpu2_boot),
        config_files=device.openocd.config_files() if device.openocd else None,
        cores=tuple(
            DebugCorePlan(
                core=c.name,
                processor_index=c.processor_index,
                svd_path=c.svd_path,
                elf=f"build/{c.name}/{device.id}-{c.name}.elf",
            )
            for c in cores
        ),
    )
    return ProjectPlan(
        device_id=device.id,
        version=device.version,
        family=device.family,
        cores=tuple(cores),
        sibling=_sibling(device),
        flash=flash,
        debug=debug,
        config=ConfigPlan(
            library=device.facets.config_library,
            header=device.facets.config_header,
            defaults_source=device.facets.config_defaults_source,
        ),
        probe=ProbePlan(
            transport=device.probe_ref.transport,
            address=device.probe_ref.address,
        ),
    )
