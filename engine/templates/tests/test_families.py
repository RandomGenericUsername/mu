"""Template-family registry and Rust dual-core render tests (req-028)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.core.loader import load_file
from engine.core.plan import build_plan
from engine.templates.families import family_for, registered_families
from engine.templates.renderer import render

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch) -> None:
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda *_a: [])
    monkeypatch.setattr("engine.templates.renderer.fetch_svds", lambda _d, _o: [])


def _device(pack: str):
    return load_file(PACKS_DIR / f"{pack}.yaml")


def test_families_are_registered() -> None:
    assert {
        "c-cmsis",
        "rust-cortex",
        "rust-cortex-dual",
        "idf-cmake",
    } <= set(registered_families())
    assert family_for("rust-cortex-dual")


def test_wl55_rust_dual_layout(tmp_path: Path) -> None:
    device = _device("stm32wl55jc")
    written = render(device, "rust", tmp_path, vscode=True)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert "Makefile" in names
    assert "m4/src/main.rs" in names and "m0plus/src/main.rs" in names
    assert "m4/Cargo.toml" in names and "m0plus/Cargo.toml" in names
    assert "m4/memory.x" in names and "m0plus/memory.x" in names
    assert "src/main.rs" not in names
    assert "Cargo.toml" not in names

    m4 = (tmp_path / "m4/src/main.rs").read_text()
    m0 = (tmp_path / "m0plus/src/main.rs").read_text()
    assert "__pre_init" in m4 and "0x5800040C" in m4
    assert "delay_half_period" in m4 and "GPIO" not in m4  # raw addresses, no HAL
    assert "COUNTER" in m0

    makefile = (tmp_path / "Makefile").read_text()
    assert "ALL_FLASH = flash-M0+ flash-M4" in makefile
    assert "mu-boot" in makefile
    assert "debug-m0plus" in makefile

    m4x = (tmp_path / "m4/memory.x").read_text()
    m0x = (tmp_path / "m0plus/memory.x").read_text()
    assert "0x08000000" in m4x and "0x20000000" in m4x
    assert "0x08020000" in m0x and "0x2000C000" in m0x
    assert "FLASH_M4" not in m4x and "FLASH_M0PLUS" not in m0x


def test_wl55_vscode_uses_probe_rs_core_configs(tmp_path: Path) -> None:
    device = _device("stm32wl55jc")
    render(device, "rust", tmp_path, vscode=True)
    launch = json.loads((tmp_path / ".vscode/launch.json").read_text())
    configs = launch["configurations"]
    assert configs[0]["type"] == "probe-rs-debug"
    assert configs[0]["request"] == "attach"
    assert configs[0]["flashingConfig"]["flashingEnabled"] is False
    combined = next(c for c in configs if c["name"] == "Debug M4+M0+ (probe-rs)")
    assert [c["coreIndex"] for c in combined["coreConfigs"]] == [0, 1]
    assert combined["coreConfigs"][0]["svdFile"].endswith("STM32WL5x_CM4.svd")
    assert combined["coreConfigs"][1]["svdFile"].endswith("STM32WL5x_CM0P.svd")
    ext = json.loads((tmp_path / ".vscode/extensions.json").read_text())
    assert "probe-rs.probe-rs-debugger" in ext["recommendations"]


def test_h755_rust_dual_layout(tmp_path: Path) -> None:
    device = _device("stm32h755")
    render(device, "rust", tmp_path)
    assert (tmp_path / "m7/src/main.rs").is_file()
    assert (tmp_path / "m4/src/main.rs").is_file()
    assert "__pre_init" not in (tmp_path / "m7/src/main.rs").read_text()
    makefile = (tmp_path / "Makefile").read_text()
    assert "ALL_FLASH = flash-M7 flash-M4" in makefile


def test_single_core_rust_is_unchanged(tmp_path: Path) -> None:
    device = _device("stm32f411re")
    render(device, "rust", tmp_path)
    assert (tmp_path / "src/main.rs").is_file()
    assert (tmp_path / "memory.x").is_file()
    assert not (tmp_path / "Makefile").exists()


def test_cpp_and_rust_share_the_plan(tmp_path: Path) -> None:
    for pack in ("stm32h755", "stm32wl55jc"):
        device = _device(pack)
        plan = build_plan(device)
        render(device, "cpp", tmp_path / pack / "cpp")
        render(device, "rust", tmp_path / pack / "rust")
        for core in plan.cores:
            linker = (
                tmp_path / pack / "cpp" / "linker"
                / device.facets.linker_for(core.name, device.id)
            ).read_text()
            assert f"{core.flash.name.upper()} (rx)" in linker
            assert f"{core.ram.name.upper()} (rwx)" in linker
            memx = (tmp_path / pack / "rust" / core.slug / "memory.x").read_text()
            assert f"0x{core.flash.origin:08X}" in memx
            assert f"0x{core.ram.origin:08X}" in memx
            assert str(core.flash.size) in memx
            assert str(core.ram.size) in memx
