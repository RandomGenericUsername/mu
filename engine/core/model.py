"""Canonical certified device model (req-003, group 1).

All structs are frozen dataclasses: construction validates field shapes,
mutation raises :class:`dataclasses.FrozenInstanceError`. ``origin_hex``
accepts ``"0x..."`` strings or ints and normalises to int.

Reader views (``DeviceView``, ``CoreView``, ``MemoryRegionView``) are the
only adapter-facing access: read-only facts, no pack paths, no raw YAML,
no loader reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence, Tuple

__all__ = [
    "Core",
    "CoreView",
    "Device",
    "DeviceFacets",
    "DeviceView",
    "Endpoint",
    "ExampleLed",
    "MemoryRegion",
    "MemoryRegionView",
    "OpenocdConfig",
    "ProofResult",
]


def _coerce_origin(value: str | int) -> int:
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"origin must be non-negative, got {value}")
        return value
    if isinstance(value, str):
        try:
            parsed = int(value, 16 if value.lower().startswith("0x") else 10)
        except ValueError:
            raise ValueError(f"origin_hex must be a hex/int literal, got {value!r}")
        if parsed < 0:
            raise ValueError(f"origin must be non-negative, got {value!r}")
        return parsed
    raise TypeError(f"origin_hex must be str or int, got {type(value).__name__}")


@dataclass(frozen=True)
class Core:
    """One CPU core on the device."""

    name: str
    arch: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Core.name must be non-empty")
        if not self.arch:
            raise ValueError("Core.arch must be non-empty")


@dataclass(frozen=True)
class MemoryRegion:
    """One addressable memory region; origin normalised to int."""

    name: str
    origin_hex: str | int
    size: int
    origin: int = field(init=False)
    #: Core names this region belongs to; empty = shared by every core (bug-014).
    cores: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("MemoryRegion.name must be non-empty")
        if not isinstance(self.size, int) or isinstance(self.size, bool) or self.size <= 0:
            raise ValueError(f"MemoryRegion.size must be a positive int, got {self.size!r}")
        declared = tuple(self.cores)
        for core in declared:
            if not isinstance(core, str) or not core:
                raise ValueError("MemoryRegion.cores entries must be non-empty strings")
        object.__setattr__(self, "cores", declared)
        object.__setattr__(self, "origin", _coerce_origin(self.origin_hex))

    def applies_to(self, core_name: str) -> bool:
        """True when this region is visible to ``core_name`` (bug-014)."""
        return not self.cores or core_name in self.cores


@dataclass(frozen=True)
class Endpoint:
    """Probe endpoint vocabulary: transport + address (core-owned, adapters fill)."""

    transport: str
    address: str

    def __post_init__(self) -> None:
        if not self.transport:
            raise ValueError("Endpoint.transport must be non-empty")
        if not self.address:
            raise ValueError("Endpoint.address must be non-empty")


@dataclass(frozen=True)
class OpenocdConfig:
    """Certified OpenOCD facts from the pack's ``openocd`` block (req-006).

    ``target`` is the board-or-target config file (registry accepts
    ``board`` or ``target``; the loader normalises to ``target``).
    ``board`` keeps the raw ``board`` key (None when the pack declares a
    ``target`` key instead) so renderers can pick the ``board/`` vs
    ``target/`` config path (req-008). ``dual_core`` selects the
    dual-session flag rendering.
    """

    interface: str
    target: str
    dual_core: bool = False
    board: str | None = None
    #: Optional core -> OpenOCD target name map (for per-core multi-piece flash).
    targets: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.interface:
            raise ValueError("OpenocdConfig.interface must be non-empty")
        if not self.target:
            raise ValueError("OpenocdConfig.target must be non-empty")
        if not isinstance(self.dual_core, bool):
            raise ValueError("OpenocdConfig.dual_core must be a bool")
        if self.board is not None and not self.board:
            raise ValueError("OpenocdConfig.board must be a non-empty string or None")
        pairs = tuple(sorted(self.targets.items())) if isinstance(self.targets, dict) else tuple(self.targets)
        for core, name in pairs:
            if not isinstance(core, str) or not core or not isinstance(name, str) or not name:
                raise ValueError("OpenocdConfig.targets entries must be non-empty (core, name) strings")
        object.__setattr__(self, "targets", pairs)

    def config_files(self) -> tuple[str, str]:
        """Resolved ``-f`` config paths: interface first, then board|target.

        Single source of truth for the ``interface/`` + ``board/``|``target/``
        prefix decision (bug-003): renderers and adapters both consume this and
        must not re-derive it. A value already containing ``/`` is left as-is.
        """
        interface = self.interface if "/" in self.interface else f"interface/{self.interface}"
        raw = self.board if self.board else self.target
        folder = "board" if self.board else "target"
        target = raw if "/" in raw else f"{folder}/{raw}"
        return (interface, target)


@dataclass(frozen=True)
class ProofResult:
    """Proof verdict for one rung: rung name + comparable evidence payload."""

    rung: str
    payload: Tuple[Tuple[str, str], ...]

    def __init__(self, rung: str, payload: dict[str, str] | Sequence[tuple[str, str] | list[str]]) -> None:
        if not rung:
            raise ValueError("ProofResult.rung must be non-empty")
        if isinstance(payload, dict):
            items = tuple(sorted(payload.items()))
        else:
            items = tuple(sorted((str(k), str(v)) for k, v in payload))
        object.__setattr__(self, "rung", rung)
        object.__setattr__(self, "payload", items)

    def as_dict(self) -> dict[str, str]:
        return dict(self.payload)


@dataclass(frozen=True)
class ExampleLed:
    """On-board LED example fact (req-014/req-015).

    Board/MCU facts to drive the LED with raw registers: port letter, pin,
    active level, and the family register facts — GPIO port base plus the RCC
    clock-enable register address and bit (F4: AHB1ENR; H7: AHB4ENR).
    """

    port: str
    pin: int
    active: str
    gpio_base: int
    rcc_en_addr: int
    rcc_en_bit: int
    clock_hz: int

    def __post_init__(self) -> None:
        if not isinstance(self.port, str) or len(self.port) != 1 or not self.port.isalpha():
            raise ValueError("ExampleLed.port must be a single letter A-Z")
        if not isinstance(self.pin, int) or isinstance(self.pin, bool) or not 0 <= self.pin <= 15:
            raise ValueError("ExampleLed.pin must be an int 0..15")
        if self.active not in ("high", "low"):
            raise ValueError("ExampleLed.active must be 'high' or 'low'")
        for name in ("gpio_base", "rcc_en_addr", "clock_hz"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"ExampleLed.{name} must be a positive int")
        if not isinstance(self.rcc_en_bit, int) or isinstance(self.rcc_en_bit, bool) or not 0 <= self.rcc_en_bit <= 31:
            raise ValueError("ExampleLed.rcc_en_bit must be an int 0..31")


@dataclass(frozen=True)
class DeviceFacets:
    """Validated family-block facts attached to a Device (req-008, group 2).

    Populated by the loader from ``blocks`` (fpu/linker/config_headers) after
    registry validation, so the renderer consumes the model only and never
    re-reads pack YAML. All fields have pack-agnostic defaults; a missing
    block leaves its default in place.
    """

    fpu_mode: str = "soft"
    fpu_variant: str = "none"
    linker: Tuple[Tuple[str, str], ...] = ()
    startup: Tuple[Tuple[str, str], ...] = ()
    system: Tuple[Tuple[str, str], ...] = ()
    defines: Tuple[Tuple[str, str], ...] = ()
    config_library: str = "stm32hal"
    config_header: str = "stm32_config.h"
    config_defaults_source: str = "pack/defaults.h"
    probe_settings: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = ()
    #: Optional on-board LED example fact (req-014/req-015) or None.
    example_led: ExampleLed | None = None
    #: Optional sibling-core release sequence (bug-021): ``(addr, value, mask)``
    #: register writes the primary core performs to boot a sibling (e.g. the
    #: STM32WL55 CPU2/CM0+). Empty when the pack needs none.
    cpu2_boot: Tuple[Tuple[int, int, int | None], ...] = ()
    #: Per-core SVD source paths for the register view (req-017): (core, path).
    svd: Tuple[Tuple[str, str], ...] = ()
    #: Every validated family block, generically attached (task-008, AD-13):
    #: ``(block_name, payload)`` pairs sorted by name. A new family's blocks —
    #: validated by that family's own module — reach renderers/adapters here
    #: without any ``core/`` change.
    blocks: Tuple[Tuple[str, Any], ...] = ()

    def block_for(self, name: str) -> Any | None:
        """Validated payload for family block ``name`` (or ``None``)."""
        for block_name, payload in self.blocks:
            if block_name == name:
                return payload
        return None

    def linker_for(self, core_name: str, device_id: str) -> str:
        # No invented fallback (startup lesson): an undeclared core is a loud
        # error, never a plausible-but-absent filename.
        for name, script in self.linker:
            if name == core_name:
                return script
        raise ValueError(
            f"pack {device_id!r} declares no linker script for core {core_name!r}"
        )

    def startup_for(self, core_name: str, device_id: str) -> str:
        # No invented fallback (bug-002 class): an undeclared core is a loud
        # error, never a plausible-but-absent filename.
        for name, script in self.startup:
            if name == core_name:
                return script
        raise ValueError(
            f"pack {device_id!r} declares no startup file for core {core_name!r}"
        )

    def system_for(self, core_name: str, device_id: str) -> str:
        # Same no-fallback rule: the vendor system file must be declared.
        for name, script in self.system:
            if name == core_name:
                return script
        raise ValueError(
            f"pack {device_id!r} declares no system file for core {core_name!r}"
        )

    def define_for(self, core_name: str) -> str | None:
        for name, macro in self.defines:
            if name == core_name:
                return macro
        return None

    def probe_setting(self, backend: str, key: str) -> str | None:
        for name, settings in self.probe_settings:
            if name == backend:
                for k, v in settings:
                    if k == key:
                        return v
        return None


@dataclass(frozen=True)
class Device:
    """Certified device: immutable facts + provenance (pack id + version + source hash)."""

    id: str
    version: str
    source_hash: str
    cores: Tuple[Core, ...]
    memory: Tuple[MemoryRegion, ...]
    probe_ref: Endpoint
    proof_rung: str
    openocd: OpenocdConfig | None = None
    provenance: Tuple[Tuple[str, str], ...] = ()
    facets: DeviceFacets | None = None
    #: Frame ``stacks`` map (AD-11): source language -> build-stack id,
    #: sorted by language. The resolved stack, never the language flag,
    #: selects the template family, image, and build command.
    stacks: Tuple[Tuple[str, str], ...] = ()
    #: Frame ``family`` (AD-13/AD-14): the device family id the pack declares.
    #: Family-owned facts (vendor sources, probe ids) key off this, never a
    #: pack-id prefix.
    family: str = ""

    def __init__(
        self,
        id: str,
        version: str,
        source_hash: str,
        cores: Sequence[Core],
        memory: Sequence[MemoryRegion],
        probe_ref: Endpoint,
        proof_rung: str,
        openocd: OpenocdConfig | None = None,
        provenance: dict[str, str] | Sequence[tuple[str, str] | list[str]] = (),
        facets: DeviceFacets | None = None,
        probe_backend: str | None = None,
        stacks: Sequence[tuple[str, str]] | dict[str, str] = (),
        family: str = "",
    ) -> None:
        if not id:
            raise ValueError("Device.id must be non-empty")
        if not version:
            raise ValueError("Device.version must be non-empty")
        if not source_hash:
            raise ValueError("Device.source_hash must be non-empty")
        core_t = tuple(cores)
        mem_t = tuple(memory)
        if not core_t:
            raise ValueError("Device.cores must be non-empty")
        if not mem_t:
            raise ValueError("Device.memory must be non-empty")
        if not all(isinstance(c, Core) for c in core_t):
            raise TypeError("Device.cores must all be Core")
        if not all(isinstance(m, MemoryRegion) for m in mem_t):
            raise TypeError("Device.memory must all be MemoryRegion")
        if not isinstance(probe_ref, Endpoint):
            raise TypeError("Device.probe_ref must be an Endpoint")
        if not proof_rung:
            raise ValueError("Device.proof_rung must be non-empty")
        if openocd is not None and not isinstance(openocd, OpenocdConfig):
            raise TypeError("Device.openocd must be an OpenocdConfig or None")
        if facets is not None and not isinstance(facets, DeviceFacets):
            raise TypeError("Device.facets must be a DeviceFacets or None")
        if probe_backend is not None and (not probe_backend or not isinstance(probe_backend, str)):
            raise ValueError("Device.probe_backend must be a non-empty backend name or None")
        prov = tuple(sorted(provenance.items())) if isinstance(provenance, dict) else tuple(sorted((str(k), str(v)) for k, v in provenance))
        # Provenance always traces to inputs: pack id + version are mandatory facts.
        base = {"pack_id": id, "pack_version": version}
        base.update(dict(prov))
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "source_hash", source_hash)
        object.__setattr__(self, "cores", core_t)
        object.__setattr__(self, "memory", mem_t)
        object.__setattr__(self, "probe_ref", probe_ref)
        object.__setattr__(self, "proof_rung", proof_rung)
        object.__setattr__(self, "openocd", openocd)
        object.__setattr__(self, "probe_backend", probe_backend)
        object.__setattr__(self, "facets", facets if facets is not None else DeviceFacets())
        object.__setattr__(self, "provenance", tuple(sorted(base.items())))
        stack_pairs = (
            tuple(sorted(stacks.items())) if isinstance(stacks, dict) else tuple(sorted(tuple(s) for s in stacks))
        )
        for lang, stack_id in stack_pairs:
            if not isinstance(lang, str) or not lang:
                raise ValueError("Device.stacks keys must be non-empty language strings")
            if not isinstance(stack_id, str) or not stack_id:
                raise ValueError("Device.stacks values must be non-empty stack ids")
        object.__setattr__(self, "stacks", stack_pairs)
        object.__setattr__(self, "family", family)

    def stack_for(self, lang: str) -> str | None:
        """Build-stack id the pack declares for ``lang`` (or ``None``)."""
        for declared_lang, stack_id in self.stacks:
            if declared_lang == lang:
                return stack_id
        return None


# --- Adapter-facing reader views (facts only, no loader/pack-path access) ---


@dataclass(frozen=True)
class CoreView:
    name: str
    arch: str

    @classmethod
    def of(cls, core: Core) -> CoreView:
        return cls(name=core.name, arch=core.arch)


@dataclass(frozen=True)
class MemoryRegionView:
    name: str
    origin: int
    size: int
    cores: Tuple[str, ...] = ()

    @classmethod
    def of(cls, region: MemoryRegion) -> MemoryRegionView:
        return cls(
            name=region.name,
            origin=region.origin,
            size=region.size,
            cores=region.cores,
        )


@dataclass(frozen=True)
class DeviceView:
    """Read-only adapter view of a Device. No loader, no paths, no raw YAML."""

    id: str
    version: str
    source_hash: str
    cores: Tuple[CoreView, ...]
    memory: Tuple[MemoryRegionView, ...]
    probe_transport: str
    probe_address: str
    proof_rung: str
    openocd_interface: str | None = None
    openocd_target: str | None = None
    openocd_dual_core: bool = False
    #: True when the pack must be flashed single-core, sibling-first (a
    #: released sibling cannot be reset; req-028 / bug-021/023/024).
    flash_single_core: bool = False
    openocd_config_files: Tuple[str, str] | None = None
    openocd_targets: Tuple[Tuple[str, str], ...] = ()
    probe_settings: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = ()
    example_led: ExampleLed | None = None
    svd: Tuple[Tuple[str, str], ...] = ()
    #: Frame family id (AD-13/AD-14) — family-owned facts key off this.
    family: str = ""
    #: Validated family blocks, passed through generically (AD-2/AD-13): an
    #: adapter renders the facts *its* family declares, without core knowing
    #: those block names.
    blocks: Tuple[Tuple[str, Any], ...] = ()

    def probe_setting(self, backend: str, key: str) -> str | None:
        for name, settings in self.probe_settings:
            if name == backend:
                for k, v in settings:
                    if k == key:
                        return v
        return None

    def block_for(self, name: str) -> Any | None:
        """Validated payload for family block ``name`` (or ``None``)."""
        for block_name, payload in self.blocks:
            if block_name == name:
                return payload
        return None

    @classmethod
    def of(cls, device: Device) -> DeviceView:
        return cls(
            id=device.id,
            version=device.version,
            source_hash=device.source_hash,
            cores=tuple(CoreView.of(c) for c in device.cores),
            memory=tuple(MemoryRegionView.of(m) for m in device.memory),
            probe_transport=device.probe_ref.transport,
            probe_address=device.probe_ref.address,
            proof_rung=device.proof_rung,
            openocd_interface=device.openocd.interface if device.openocd else None,
            openocd_target=device.openocd.target if device.openocd else None,
            openocd_dual_core=device.openocd.dual_core if device.openocd else False,
            flash_single_core=bool(device.facets.cpu2_boot),
            openocd_config_files=device.openocd.config_files() if device.openocd else None,
            openocd_targets=device.openocd.targets if device.openocd else (),
            probe_settings=device.facets.probe_settings if device.facets else (),
            example_led=device.facets.example_led if device.facets else None,
            svd=device.facets.svd if device.facets else (),
            family=device.family,
            blocks=device.facets.blocks if device.facets else (),
        )

    def __iter__(self) -> Iterator[str]:
        yield from ("id", "version", "cores", "memory", "probe", "proof_rung")
