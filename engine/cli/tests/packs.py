"""Pick a shipped pack the CLI can fully drive today.

Packs whose build stack is recognised but whose template family or probe backend
has not shipped yet are skipped, so tests that need a working pack select one by
capability rather than by name — which keeps this module free of hardware
knowledge (see ``test_no_hardware_knowledge``).
"""

from __future__ import annotations

from pathlib import Path

from engine.adapters import get_adapter
from engine.adapters.toolchain import ensure_registered
from engine.cli.main import PACKS_DIR
from engine.core.loader import load_file
from engine.core.stacks import UnknownStackError, stack_spec
from engine.templates.renderer import SUPPORTED_TEMPLATE_FAMILIES

__all__ = ["first_supported_pack"]


def first_supported_pack() -> tuple[str, Path]:
    """(id, path) of a shipped pack the renderer + probe registry support today.

    Prefer a ``c-cmsis`` pack so CLI tests exercise the Makefile flow; other
    shipped families (e.g. ESP-IDF's CMake) are a fallback.
    """
    ensure_registered()
    fallback: tuple[str, Path] | None = None
    for path in sorted(Path(PACKS_DIR).glob("*.yaml")):
        device = load_file(path)
        stack_id = device.stack_for("c")
        if stack_id is None:
            continue
        try:
            family = stack_spec(stack_id).template_family
        except UnknownStackError:
            continue  # stack declared, its toolchain adapter not shipped yet
        if family not in SUPPORTED_TEMPLATE_FAMILIES:
            continue
        if device.probe_backend:
            try:
                get_adapter(device.probe_backend)
            except ValueError:
                continue  # backend not shipped yet
        if family == "c-cmsis":
            return device.id, path
        if fallback is None:
            fallback = (device.id, path)
    if fallback is not None:
        return fallback
    raise AssertionError("no fully supported shipped pack found")
