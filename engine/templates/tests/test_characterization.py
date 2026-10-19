"""Characterization: the family dispatcher preserves legacy output (req-028)."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.core.loader import load_file
from engine.templates.renderer import _render_legacy, render

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch) -> None:
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda *_a: [])
    monkeypatch.setattr("engine.templates.renderer.fetch_svds", lambda _d, _o: [])


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize(
    "pack,lang",
    [
        ("stm32f411re", "c"),
        ("stm32h755", "cpp"),
        ("stm32wl55jc", "c"),
        ("esp32cam", "c"),
    ],
)
def test_dispatcher_matches_legacy(pack: str, lang: str, tmp_path: Path) -> None:
    device = load_file(PACKS_DIR / f"{pack}.yaml")
    new = tmp_path / "new"
    old = tmp_path / "old"
    render(device, lang, new)
    _render_legacy(device, lang, old)
    assert _tree(new) == _tree(old)
