"""ProjectPlan domain tests (req-028)."""

from __future__ import annotations

from pathlib import Path

from engine.core.loader import load_file
from engine.core.plan import build_plan, core_slug

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"


def test_core_slug() -> None:
    assert core_slug("M4") == "m4"
    assert core_slug("M0+") == "m0plus"
    assert core_slug("CM7") == "cm7"


def test_wl55_plan_is_sibling_first() -> None:
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    plan = build_plan(device)
    assert [c.slug for c in plan.cores] == ["m4", "m0plus"]
    assert plan.primary.release_writes
    assert plan.sibling is not None
    assert plan.sibling.slug == "m0plus"
    assert plan.sibling.openocd_target == "stm32wlx.cpu1"
    assert plan.flash.order == ("M0+", "M4")
    assert plan.flash.single_core is True
    assert plan.flash.boot_check_core == "M4"
    assert plan.debug.attach_only is True
    assert [c.processor_index for c in plan.debug.cores] == [0, 1]


def test_wl55_per_core_regions() -> None:
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    plan = build_plan(device)
    m4, m0 = plan.cores
    assert (m4.flash.origin, m4.flash.size) == (0x08000000, 131072)
    assert (m4.ram.origin, m4.ram.size) == (0x20000000, 49152)
    assert (m0.flash.origin, m0.flash.size) == (0x08020000, 131072)
    assert (m0.ram.origin, m0.ram.size) == (0x2000C000, 16384)


def test_h755_plan_is_independent_dual() -> None:
    device = load_file(PACKS_DIR / "stm32h755.yaml")
    plan = build_plan(device)
    assert [c.slug for c in plan.cores] == ["m7", "m4"]
    assert plan.sibling is None
    assert plan.flash.order == ("M7", "M4")
    assert plan.flash.single_core is False
    assert plan.debug.attach_only is False
    assert [c.processor_index for c in plan.debug.cores] == [0, 1]
    m7, m4 = plan.cores
    assert (m7.flash.origin, m7.flash.size) == (0x08000000, 1048576)
    assert (m4.flash.origin, m4.flash.size) == (0x08100000, 1048576)


def test_single_core_plan() -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    plan = build_plan(device)
    assert len(plan.cores) == 1
    assert plan.cores[0].slug == "m4"
    assert plan.sibling is None
    assert plan.flash.order == ("M4",)
    assert plan.debug.attach_only is False
