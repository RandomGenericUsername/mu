"""Fast tests for the e2e assertion helpers (req-009, group 1.2).

No docker: size parsing, flash/RAM fit vs the pack map, memory.x
consistency, vendor-stub placement, and the negative overflow tests
(fixtures that MUST fail the cell).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.core.loader import load_file
from engine.core.model import Core, Device, Endpoint, MemoryRegion
from engine.templates.renderer import core_context, render
from engine.verify.e2e import (
    CellFailure,
    VENDOR_STUB_S,
    assert_fits,
    build_cpp_cell,
    check_memory_x,
    inject_vendor_stubs,
    parse_memory_x,
    parse_size_output,
    pick_region,
)

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"


def _tiny_device() -> Device:
    return Device(
        id="tiny",
        version="1",
        source_hash="0" * 64,
        cores=(Core(name="M4", arch="thumbv7em-none-eabihf"),),
        memory=(
            MemoryRegion(name="flash", origin_hex="0x08000000", size=1024),
            MemoryRegion(name="ram", origin_hex="0x20000000", size=512),
        ),
        probe_ref=Endpoint(transport="stlink", address="addr"),
        proof_rung="readback",
    )


def test_parse_size_output() -> None:
    out = "   text\t   data\t    bss\t    dec\t    hex\tfilename\n    200\t      8\t     16\t    224\t     e0\ttiny-M4.elf\n"
    assert parse_size_output(out) == (200, 8, 16)


def test_parse_size_output_garbage() -> None:
    with pytest.raises(CellFailure):
        parse_size_output("no size here\n")


def test_assert_fits_ok_real_pack() -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    info = assert_fits(device, "M4", 200, 0, 0)
    assert info.flash_used == 200 and info.flash_avail == 524288
    assert info.flash_region == "flash" and info.ram_region == "ram"


def test_assert_fits_flash_overflow_negative() -> None:
    with pytest.raises(CellFailure, match="flash overflow.*used 1124.*available 1024"):
        assert_fits(_tiny_device(), "M4", 1024, 100, 0)


def test_assert_fits_ram_overflow_negative() -> None:
    with pytest.raises(CellFailure, match="ram overflow.*used 600.*available 512"):
        assert_fits(_tiny_device(), "M4", 100, 100, 500)


def test_pick_region_prefers_core_bank() -> None:
    device = load_file(PACKS_DIR / "stm32h755.yaml")
    assert pick_region(device.memory, "M4", "flash").name == "flash_m4"
    assert pick_region(device.memory, "M7", "flash").name == "flash_m7"
    # bug-014: RAM resolves per core too, and the two never coincide.
    m7 = pick_region(device.memory, "M7", "ram")
    m4 = pick_region(device.memory, "M4", "ram")
    assert m7.name == "ram_m7" and m4.name == "ram_m4"
    assert (m7.origin, m7.size) != (m4.origin, m4.size)


def test_check_memory_x_ok(tmp_path: Path) -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    render(device, "rust", tmp_path)
    report = check_memory_x(device, (tmp_path / "memory.x").read_text())
    assert any("FLASH" in line for line in report)


def test_check_memory_x_aliases_ok() -> None:
    device = load_file(PACKS_DIR / "stm32h755.yaml")
    tmp = Path("/tmp/req009-h755-memx")
    tmp.mkdir(exist_ok=True)
    render(device, "rust", tmp)
    report = check_memory_x(device, (tmp / "memory.x").read_text())
    assert len(report) == 4  # flash_m7 + flash_m4 + ram_m7 + ram_m4, aliases accepted


def test_check_memory_x_mismatch_negative(tmp_path: Path) -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    render(device, "rust", tmp_path)
    bad = (tmp_path / "memory.x").read_text().replace("LENGTH = 524288", "LENGTH = 123")
    with pytest.raises(CellFailure, match="FLASH mismatch"):
        check_memory_x(device, bad)


def test_check_memory_x_missing_region_negative() -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    with pytest.raises(CellFailure, match="missing region"):
        check_memory_x(device, "MEMORY { RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 131072 }")


def test_vendor_stubs_land_on_startup_paths(tmp_path: Path, monkeypatch) -> None:
    # req-011: render() strictly vendors C/C++; stub it (non-repo tmp, no network).
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda _pack_id, _family, _out: [])
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    render(device, "c", tmp_path)
    stubs = inject_vendor_stubs(device, tmp_path)
    assert len(stubs) == 2
    for core in device.cores:
        rel = core_context(device, core, "c")["startup_s"]
        assert rel in stubs
        text = (tmp_path / rel).read_text()
        assert "Reset_Handler" in text and "SystemInit" in text


def test_parse_memory_x_hex() -> None:
    got = parse_memory_x("MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 524288 }")
    assert got == {"FLASH": (0x08000000, 524288)}


def test_vendor_stub_gas_syntax() -> None:
    # Regression: doubled %% leaked into the stub and GAS rejected it
    # (all 6 C/C++ cells failed with "junk at end of line ... '%'").
    assert "%%" not in VENDOR_STUB_S
    assert "%progbits" in VENDOR_STUB_S and "%function" in VENDOR_STUB_S


def test_warnings_are_recorded_and_do_not_fail_the_cell(tmp_path: Path, monkeypatch) -> None:
    """ops-033: warn-only policy — warning lines are recorded per cell and the
    cell still passes (authoritative statement: docs/warnings-policy.md)."""
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    size_out = (
        "   text\t   data\t    bss\t    dec\t    hex\tfilename\n"
        "    200\t      8\t     16\t    224\t     e0\tstm32f411re-M4.elf\n"
    )

    def fake_docker_run(image, project_dir, args, timeout=0):
        if args[0] == "make":  # the build itself emits a warning, then succeeds
            return subprocess.CompletedProcess(
                args, 0, "warning: deprecated foo [-Wdeprecated]\nbuilt ok\n", ""
            )
        return subprocess.CompletedProcess(args, 0, size_out, "")

    monkeypatch.setattr("engine.verify.e2e.docker_run", fake_docker_run)
    res = build_cpp_cell(device, tmp_path, "img")
    assert res.ok is True
    assert any("deprecated" in w for w in res.warnings)
