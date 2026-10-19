"""YAML pack loader + frame validator (req-003, group 2.1).

Frame keys: id, version, cores, memory, probe, proof_rung, optional blocks.
``blocks`` maps block_name -> payload; each name must be registered
(unknown = hard error naming the block). Returns a certified
:class:`engine.core.model.Device` with ``source_hash`` = sha256 of raw bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from engine.core.model import Core, Device, DeviceFacets, Endpoint, ExampleLed, MemoryRegion, OpenocdConfig
from engine.core.registry import UnknownBlockError, validate_block
from engine.packs import ensure_registered

__all__ = ["FRAME_KEYS", "FrameError", "load_file", "load_text", "validate_frame"]

FRAME_KEYS = ("id", "version", "family", "cores", "memory", "probe", "proof_rung", "stacks")


class FrameError(ValueError):
    """Raised when a pack fails frame validation."""


def _source_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _as_int(value: object) -> int:
    """Coerce a YAML int or ``0x``/decimal string to int (address facts)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(str(value), 0)


def validate_frame(doc: dict) -> Device:
    if not isinstance(doc, dict):
        raise FrameError(f"pack must be a mapping, got {type(doc).__name__}")
    for key in FRAME_KEYS:
        if key not in doc:
            raise FrameError(f"pack missing required frame key: {key!r}")
    # Shipped families register their own block validators (task-008, AD-13).
    ensure_registered()
    family = doc["family"]
    if not isinstance(family, str) or not family:
        raise FrameError("pack 'family' must be a non-empty string")
    # AD-11: the frame declares which build stack each source language uses.
    stacks = doc["stacks"]
    if not isinstance(stacks, dict) or not stacks:
        raise FrameError("'stacks' must be a non-empty mapping of language -> build-stack id")
    for lang, stack_id in stacks.items():
        if not isinstance(lang, str) or not lang:
            raise FrameError("'stacks' keys must be non-empty language strings")
        if not isinstance(stack_id, str) or not stack_id:
            raise FrameError(f"'stacks[{lang!r}]' must be a non-empty build-stack id")
    try:
        cores = tuple(Core(name=c["name"], arch=c["arch"]) for c in doc["cores"])
    except (TypeError, KeyError, AttributeError) as exc:
        raise FrameError(f"invalid 'cores' section: {exc}") from exc
    try:
        memory = tuple(
            MemoryRegion(
                name=m["name"],
                origin_hex=m.get("origin_hex", m.get("origin")),
                size=m["size"],
                cores=tuple(m.get("cores") or ()),
            )
            for m in doc["memory"]
        )
    except (TypeError, KeyError, AttributeError) as exc:
        raise FrameError(f"invalid 'memory' section: {exc}") from exc
    try:
        probe = Endpoint(transport=doc["probe"]["transport"], address=doc["probe"]["address"])
    except (TypeError, KeyError, AttributeError) as exc:
        raise FrameError(f"invalid 'probe' section: {exc}") from exc
    blocks = doc.get("blocks", {})
    if not isinstance(blocks, dict):
        raise FrameError("'blocks' must be a mapping of block_name -> payload")
    for name, payload in blocks.items():
        try:
            validate_block(name, payload, family=family)
        except UnknownBlockError:
            raise
        except ValueError as exc:
            raise FrameError(f"family block {name!r} invalid: {exc}") from exc
    openocd: OpenocdConfig | None = None
    if "openocd" in blocks:
        raw_block = blocks["openocd"]
        target = raw_block.get("target", raw_block.get("board"))
        openocd = OpenocdConfig(
            interface=raw_block["interface"],
            target=target,
            dual_core=bool(raw_block.get("dual_core", False)),
            board=raw_block.get("board"),
            flash_reset_config=raw_block.get("flash_reset_config"),
            targets=raw_block.get("targets", {}),
        )
    # Attach validated family blocks as model facets (req-008 group 2):
    # registry validators already certified shapes above, so direct reads
    # here are safe. A missing block leaves the DeviceFacets default.
    fpu_block = blocks.get("fpu", {})
    linker_block = blocks.get("linker", {})
    cfg_block = blocks.get("config_headers", {})
    startup_block = blocks.get("startup", {})
    system_block = blocks.get("system", {})
    defines_block = blocks.get("defines", {})
    probe_settings_block = blocks.get("probe_settings", {})
    svd_block = blocks.get("svd", {})
    example_block = blocks.get("example", {})
    led = example_block.get("led") if isinstance(example_block, dict) else None
    example_led = (
        ExampleLed(
            port=led["port"],
            pin=_as_int(led["pin"]),
            active=led.get("active", "high"),
            gpio_base=_as_int(led["gpio_base"]),
            rcc_en_addr=_as_int(led["rcc_en_addr"]),
            rcc_en_bit=_as_int(led["rcc_en_bit"]),
            clock_hz=_as_int(led["clock_hz"]),
        )
        if led
        else None
    )
    cpu2 = example_block.get("cpu2_boot") if isinstance(example_block, dict) else None
    cpu2_boot = (
        tuple(
            (_as_int(w["addr"]), _as_int(w["value"]), _as_int(w["mask"]) if "mask" in w else None)
            for w in cpu2["writes"]
        )
        if cpu2
        else ()
    )
    facets = DeviceFacets(
        fpu_mode=fpu_block.get("mode", "soft"),
        fpu_variant=fpu_block.get("variant", "none"),
        linker=tuple(sorted(linker_block.items())),
        startup=tuple(sorted(startup_block.items())),
        system=tuple(sorted(system_block.items())),
        defines=tuple(sorted(defines_block.items())),
        config_library=cfg_block.get("library", "stm32hal"),
        config_header=cfg_block.get("header", "stm32_config.h"),
        config_defaults_source=cfg_block.get("defaults_source", "pack/defaults.h"),
        probe_settings=tuple(
            sorted(
                (backend, tuple(sorted(settings.items())))
                for backend, settings in probe_settings_block.items()
            )
        ),
        example_led=example_led,
        cpu2_boot=cpu2_boot,
        svd=tuple(sorted(svd_block.items())),
        # Every validated block, generically attached (task-008, AD-13): a new
        # family's blocks reach consumers without a core change.
        blocks=tuple(sorted(blocks.items())),
    )
    return Device(
        id=doc["id"],
        version=str(doc["version"]),
        source_hash=doc["_source_hash"],
        cores=cores,
        memory=memory,
        probe_ref=probe,
        proof_rung=doc["proof_rung"],
        openocd=openocd,
        provenance={"pack_id": doc["id"], "pack_version": str(doc["version"])},
        facets=facets,
        probe_backend=doc.get("probe_backend"),
        stacks=stacks,
        family=family,
    )


def load_text(text: str, raw: bytes | None = None) -> Device:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise FrameError(f"pack must be a mapping, got {type(doc).__name__}")
    doc["_source_hash"] = _source_hash(raw if raw is not None else text.encode())
    return validate_frame(doc)


def load_file(path: str | Path) -> Device:
    raw = Path(path).read_bytes()
    return load_text(raw.decode(), raw)
