"""STM32 family block validators (relocated from ``core/registry.py`` by task-008).

Device truth for the STM32 families lives here (AD-13); ``core/`` keeps only the
registry mechanism. Every validator is registered against the family ids it
belongs to, so a pack may only declare blocks its own family registered.
"""

from __future__ import annotations

from typing import Any

from engine.core.registry import register
from engine.core.probe_ids import register_probe_vids

__all__ = ["STM32_FAMILIES", "register_stm32_families"]

#: Family ids this module owns (the ``family`` a pack declares).
STM32_FAMILIES = ("stm32f4", "stm32h7", "stm32wl")

#: USB vendor id every ST-Link probe presents (AD-14: device truth, not a
#: hardcoded list in the host shim).
STM32_PROBE_VIDS = ("0483",)

_FPU_MODES = ("soft", "softfp", "hard")
_CONFIG_HEADER_KEYS = ("library", "header", "defaults_source")
_EXAMPLE_ACTIVE = ("high", "low")


def _validate_openocd(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("openocd block must be a non-empty mapping")
    iface = payload.get("interface")
    if not isinstance(iface, str) or not iface:
        raise ValueError("openocd block must declare non-empty 'interface'")
    boardish = ("board", "target")
    if not any(k in payload for k in boardish):
        raise ValueError("openocd block must declare one of 'board'/'target'")
    for key in boardish:
        if key in payload and (not isinstance(payload[key], str) or not payload[key]):
            raise ValueError(f"openocd block {key!r} must be a non-empty string")
    if "dual_core" in payload and not isinstance(payload["dual_core"], bool):
        raise ValueError("openocd block 'dual_core' flag must be a bool")
    if "flash_reset_config" in payload:
        value = payload["flash_reset_config"]
        if not isinstance(value, str) or not value:
            raise ValueError(
                "openocd block 'flash_reset_config' must be a non-empty string"
            )
    if "targets" in payload:
        targets = payload["targets"]
        if not isinstance(targets, dict) or not targets:
            raise ValueError("openocd block 'targets' must be a non-empty mapping core -> target name")
        for core, name in targets.items():
            if not isinstance(core, str) or not core or not isinstance(name, str) or not name:
                raise ValueError("openocd 'targets' entries must be non-empty (core, name) strings")


def _validate_fpu(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("fpu block must be a non-empty mapping")
    mode = payload.get("mode")
    if not isinstance(mode, str) or not mode:
        raise ValueError("fpu block must declare non-empty 'mode'")
    if mode not in _FPU_MODES:
        raise ValueError(f"fpu block 'mode' must be one of {_FPU_MODES}, got {mode!r}")
    variant = payload.get("variant")
    if not isinstance(variant, str) or not variant:
        raise ValueError("fpu block must declare non-empty 'variant'")


def _validate_linker(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("linker block must be a non-empty mapping of core name -> script")
    for core, script in payload.items():
        if not isinstance(core, str) or not core:
            raise ValueError(f"linker block core name must be a non-empty string, got {core!r}")
        if not isinstance(script, str) or not script:
            raise ValueError(f"linker block script for core {core!r} must be a non-empty string")


def _validate_startup(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("startup block must be a non-empty mapping of core name -> vendor file")
    for core, script in payload.items():
        if not isinstance(core, str) or not core:
            raise ValueError(f"startup block core name must be a non-empty string, got {core!r}")
        if not isinstance(script, str) or not script:
            raise ValueError(f"startup block file for core {core!r} must be a non-empty string")


def _validate_system(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("system block must be a non-empty mapping of core name -> vendor file")
    for core, script in payload.items():
        if not isinstance(core, str) or not core:
            raise ValueError(f"system block core name must be a non-empty string, got {core!r}")
        if not isinstance(script, str) or not script:
            raise ValueError(f"system block file for core {core!r} must be a non-empty string")


def _validate_defines(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("defines block must be a non-empty mapping of core name -> device macro")
    for core, macro in payload.items():
        if not isinstance(core, str) or not core:
            raise ValueError(f"defines block core name must be a non-empty string, got {core!r}")
        if not isinstance(macro, str) or not macro:
            raise ValueError(f"defines block macro for core {core!r} must be a non-empty string")


def _validate_config_headers(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("config_headers block must be a non-empty mapping")
    for key in _CONFIG_HEADER_KEYS:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"config_headers block must declare non-empty {key!r}")


def _validate_probe_settings(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("probe_settings block must be a non-empty mapping of backend -> settings")
    for backend, settings in payload.items():
        if not isinstance(backend, str) or not backend:
            raise ValueError(f"probe_settings backend name must be a non-empty string, got {backend!r}")
        if not isinstance(settings, dict) or not settings:
            raise ValueError(f"probe_settings for backend {backend!r} must be a non-empty mapping")
        for key, value in settings.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"probe_settings key for backend {backend!r} must be a non-empty string")
            if not isinstance(value, str) or not value:
                raise ValueError(f"probe_settings[{backend}][{key}] must be a non-empty string")


def _is_addr(value: Any) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0
    if isinstance(value, str):
        try:
            return int(value, 0) > 0
        except ValueError:
            return False
    return False


def _validate_example(payload: Any) -> None:
    """On-board LED example fact (req-014/req-015): ``{led: {port,pin,active,
    gpio_base,rcc_en_addr,rcc_en_bit}}``."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("example block must be a non-empty mapping")
    led = payload.get("led")
    if not isinstance(led, dict):
        raise ValueError("example block must declare a 'led' mapping")
    port = led.get("port")
    if not isinstance(port, str) or len(port) != 1 or not port.isalpha():
        raise ValueError("example.led.port must be a single letter A-Z")
    pin = led.get("pin")
    if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= 15:
        raise ValueError("example.led.pin must be an int 0..15")
    active = led.get("active", "high")
    if active not in _EXAMPLE_ACTIVE:
        raise ValueError(
            f"example.led.active must be one of {_EXAMPLE_ACTIVE}, got {active!r}"
        )
    for key in ("gpio_base", "rcc_en_addr"):
        if not _is_addr(led.get(key)):
            raise ValueError(f"example.led.{key} must be a positive int address")
    if not _is_addr(led.get("clock_hz")):
        raise ValueError("example.led.clock_hz must be a positive int (Hz)")
    bit = led.get("rcc_en_bit")
    if not isinstance(bit, int) or isinstance(bit, bool) or not 0 <= bit <= 31:
        raise ValueError("example.led.rcc_en_bit must be an int 0..31")
    # bug-021: optional "release the sibling core" sequence (e.g. STM32WL55
    # CPU2/CM0+ needs PWR_CR4.C2BOOT + its reset vector). Device facts only.
    cpu2 = payload.get("cpu2_boot")
    if cpu2 is None:
        return
    if not isinstance(cpu2, dict):
        raise ValueError("example.cpu2_boot must be a mapping")
    if not isinstance(cpu2.get("core"), str) or not cpu2["core"]:
        raise ValueError("example.cpu2_boot.core must be a non-empty core name")
    writes = cpu2.get("writes")
    if not isinstance(writes, list) or not writes:
        raise ValueError("example.cpu2_boot.writes must be a non-empty list")
    for write in writes:
        if not isinstance(write, dict) or not _is_addr(write.get("addr")):
            raise ValueError("example.cpu2_boot.writes[].addr must be a positive int address")
        for key in ("value", "mask"):
            v = write.get(key)
            if key == "mask" and v is None:
                continue
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"example.cpu2_boot.writes[].{key} must be a non-negative int")


def _validate_svd(payload: Any) -> None:
    """Per-core SVD file paths for the Cortex-Debug register view (req-017)."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("svd block must be a non-empty mapping of core -> svd path")
    for core, path in payload.items():
        if not isinstance(core, str) or not core:
            raise ValueError(f"svd block core name must be a non-empty string, got {core!r}")
        if not isinstance(path, str) or not path:
            raise ValueError(f"svd block path for core {core!r} must be a non-empty string")


#: block name -> validator, for every STM32 family this module owns.
_STM32_BLOCKS = {
    "openocd": _validate_openocd,
    "fpu": _validate_fpu,
    "linker": _validate_linker,
    "startup": _validate_startup,
    "system": _validate_system,
    "defines": _validate_defines,
    "config_headers": _validate_config_headers,
    "probe_settings": _validate_probe_settings,
    "example": _validate_example,
    "svd": _validate_svd,
}


def register_stm32_families() -> None:
    """Register every STM32 block against every STM32 family (idempotent)."""
    for block_name, validator in _STM32_BLOCKS.items():
        register(block_name, validator, families=STM32_FAMILIES)
    for family in STM32_FAMILIES:
        register_probe_vids(family, STM32_PROBE_VIDS)
