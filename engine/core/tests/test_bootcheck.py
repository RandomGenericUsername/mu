"""Boot verify-and-retry helpers (bug-027).

Covers the pure logic: flash-window resolution from the certified memory map,
the emitted jimsh loop, and the verdict command (including the measured
"jimsh `exit 1` never reaches OpenOCD's rc" constraint). No hardware here; the
live numbers live in the ticket.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.core.bootcheck import (
    BOOT_CHECK_ATTEMPTS,
    BOOT_CHECK_SETTLE_MS,
    PLACEHOLDER_GUARD,
    boot_check_command,
    boot_check_commands,
    boot_check_verdict_command,
    flash_window,
)
from engine.core.loader import load_file
from engine.core.model import MemoryRegion

PACKS = Path(__file__).resolve().parents[3] / "packs"


def _regions(*triples):
    return [
        MemoryRegion(name=n, origin_hex=hex(o), size=s, cores=c)
        for n, o, s, c in triples
    ]


def test_flash_window_prefers_region_naming_the_core():
    """H755-style split banks: each core is checked against ITS own flash."""
    memory = _regions(("flash_m7", 0x08000000, 1024 * 1024, ("M7",)),
                      ("flash_m4", 0x08100000, 1024 * 1024, ("M4",)))
    assert flash_window(memory, "M7") == (0x08000000, 0x08100000)
    assert flash_window(memory, "M4") == (0x08100000, 0x08200000)


def test_flash_window_falls_back_to_visible_region():
    """Single shared flash bank (F411) → the only flash window."""
    memory = _regions(("flash", 0x08000000, 512 * 1024, ()),
                      ("ram", 0x20000000, 128 * 1024, ()))
    assert flash_window(memory, "M4") == (0x08000000, 0x08080000)


def test_flash_window_raises_when_no_flash_region():
    """A pack with no flash has no honest window → loud error, never a guess."""
    with pytest.raises(ValueError, match="no flash region"):
        flash_window(_regions(("sram", 0x20000000, 64 * 1024, ())), "M4")


def test_boot_check_command_retries_resets_until_pc_is_in_flash():
    cmd = boot_check_command(0x08000000, 0x08020000)
    # a bounded retry loop, not a single reset
    assert cmd.startswith("for {set mu_try 0} {$mu_try < ")
    assert f"< {BOOT_CHECK_ATTEMPTS}" in cmd
    assert cmd.count("reset run") == 1  # once per iteration, not unrolled
    assert f"sleep {BOOT_CHECK_SETTLE_MS}" in cmd
    # generic boot signal: the PC, compared against the pack's flash window
    assert 'capture "reg pc"' in cmd
    assert "$mu_pc >= 0x8000000 && $mu_pc < 0x8020000" in cmd
    # board is left running no matter how the loop ends
    assert cmd.rindex("resume") > cmd.index("halt")
    assert "break" in cmd


def test_boot_check_command_has_no_device_specific_facts():
    """Pack-independence: no chip/register/magic address beyond the window."""
    cmd = boot_check_command(0x08000000, 0x08020000)
    for forbidden in ("stm32", "RCC", "0x5800", "boot0", "SRST"):
        assert forbidden.lower() not in cmd.lower()


def test_verdict_is_loud_but_not_fatal():
    """Measured on the bench: jimsh `exit 1` leaves OpenOCD's rc at 0."""
    verdict = boot_check_verdict_command(0x08000000, 0x08020000)
    assert "mu-boot: verified" in verdict
    assert "DID NOT BOOT" in verdict
    assert f"after {BOOT_CHECK_ATTEMPTS} attempts" in verdict
    assert "exit 1" not in verdict, (
        "the verdict must not pretend to fail the process — jimsh exit codes do "
        "not reach OpenOCD's return code (bug-027, measured)"
    )


def test_boot_check_commands_are_loop_then_verdict():
    cmds = boot_check_commands(_regions(("flash", 0x08000000, 512 * 1024, ())), "M4")
    assert len(cmds) == 2
    assert cmds[0].startswith("for {set mu_try 0}")
    assert cmds[1].startswith("if {$mu_pc >= 0x8000000")


def test_wl55jc_pack_windows_match_the_bench_board():
    view = load_file(PACKS / "stm32wl55jc.yaml")
    assert flash_window(view.memory, "M4") == (0x08000000, 0x08020000)
    assert flash_window(view.memory, "M0+") == (0x08020000, 0x08040000)


def test_placeholder_guard_ignores_only_the_boot_check_tcl_vars():
    """The generated Makefile legitimately contains `$$mu_try` (bug-027)."""
    assert PLACEHOLDER_GUARD.search("x $$mu_try $$mu_out $$mu_pc") is None
    assert PLACEHOLDER_GUARD.search("all: $(ALL_FLASH)") is None
    assert PLACEHOLDER_GUARD.search("oops $core left in") is not None
    assert PLACEHOLDER_GUARD.search("oops ${project} left in") is not None
    assert PLACEHOLDER_GUARD.search("oops $mu_whatever left in") is not None
