"""Legacy template-family adapters (req-028).

The C/C++, single-core Rust, and ESP-IDF implementations still live in
``renderer.py`` during the extraction. They are registered as families so
``render()`` is already a dispatcher; moving their bodies into dedicated modules
is a behavior-preserving follow-up.
"""

from __future__ import annotations

from pathlib import Path

from engine.core.model import Device
from engine.core.plan import ProjectPlan
from engine.templates.families import (
    RenderOptions,
    register_template_family,
)

__all__ = []


class _LegacyFamily:
    def emit(
        self,
        device: Device,
        plan: ProjectPlan,
        out: Path,
        options: RenderOptions,
    ) -> list[Path]:
        # Late import: renderer imports the family registry at module load.
        from engine.templates.renderer import _render_legacy

        return _render_legacy(device, options.lang, out, vscode=options.vscode)


_LEGACY = _LegacyFamily()
for _family_id in ("c-cmsis", "rust-cortex", "idf-cmake"):
    register_template_family(_family_id, _LEGACY)
