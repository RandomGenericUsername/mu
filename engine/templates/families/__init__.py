"""Template-family port + registry (req-028).

A family is a rendering adapter over the domain ``ProjectPlan``. Registering a
family is how a new template family joins without editing ``render()`` — the
same open/closed mechanism as ``StackSpec`` and ``build_cell`` (AD-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from engine.core.model import Device
from engine.core.plan import ProjectPlan

__all__ = [
    "RenderOptions",
    "TemplateFamily",
    "family_for",
    "register_template_family",
    "registered_families",
]


@dataclass(frozen=True)
class RenderOptions:
    """Per-render options that are not device facts."""

    lang: str
    vscode: bool = False


class TemplateFamily(Protocol):
    """Renderer port: emit a project tree from the plan."""

    def emit(
        self,
        device: Device,
        plan: ProjectPlan,
        out: Path,
        options: RenderOptions,
    ) -> list[Path]:
        ...


_REGISTRY: dict[str, TemplateFamily] = {}


def register_template_family(family_id: str, family: TemplateFamily) -> None:
    if not family_id:
        raise ValueError("template family id must be non-empty")
    existing = _REGISTRY.get(family_id)
    if existing is not None and existing is not family:
        raise ValueError(f"template family {family_id!r} already registered")
    _REGISTRY[family_id] = family


def family_for(family_id: str) -> TemplateFamily:
    try:
        return _REGISTRY[family_id]
    except KeyError:
        raise ValueError(
            f"no template family registered for {family_id!r}; "
            f"registered: {sorted(_REGISTRY)}"
        ) from None


def registered_families() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
