"""Regression: the flash path must verify the boot and retry (bug-027).

`make flash` (renderer) and `mu flash` (adapter) both end a piece with a reset
that intermittently leaves the core latched in system memory, while OpenOCD
still prints `** Verified OK **`. Both sites must therefore carry the shared
verify-and-retry tail from :mod:`engine.core.bootcheck`, and — because the two
are separate implementations of one behaviour — must emit the *same* commands.

No hardware here (fakes only); the bench numbers live in the ticket.
"""

from __future__ import annotations

import re
from pathlib import Path

from engine.adapters.openocd import OpenOCDAdapter
from engine.core.bootcheck import boot_check_commands
from engine.core.loader import load_file
from engine.core.model import DeviceView, Endpoint
from engine.templates.renderer import render

PACKS = Path(__file__).resolve().parents[3] / "packs"


def _endpoint() -> Endpoint:
    return Endpoint(transport="stlink", address="openocd:stlink")


def _adapter() -> OpenOCDAdapter:
    def run(argv):
        raise AssertionError("argv-only helper must never run a probe")

    return OpenOCDAdapter(runner=run)


def _argv(pack: str, pieces: list[str]) -> list[str]:
    view = DeviceView.of(load_file(PACKS / f"{pack}.yaml"))
    return _adapter().render_argv(view, _endpoint(), pieces)


def _makefile(pack: str, tmp_path: Path) -> str:
    out = tmp_path / pack
    render(load_file(PACKS / f"{pack}.yaml"), "c", out)
    return (out / "Makefile").read_text()


# --- adapter (`mu flash`) ----------------------------------------------------


def test_adapter_appends_boot_check_before_exit():
    argv = _argv("stm32wl55jc", ["build/M4/app.elf"])
    assert argv[-1] == "exit"
    cmds = [a for a in argv if a != "-c"]  # the `-c` payloads, in order
    loop, verdict = cmds[-3], cmds[-2]
    assert loop.startswith("for {set mu_try 0}")
    assert "reset run" in loop and 'capture "reg pc"' in loop
    assert verdict.startswith("if {$mu_pc >=")
    # the loop comes AFTER the program step: programming first, then boot.
    assert argv.index("program build/M4/app.elf verify reset") < argv.index(loop)


def test_adapter_boot_check_window_is_the_pieces_own_flash_bank():
    """The checked window must be the bank that piece was programmed into."""
    argv = _argv("stm32h755", ["build/M7/x.elf", "build/M4/y.elf"])
    loop = [a for a in argv if a.startswith("for {set mu_try")][0]
    # last piece = M4 -> flash_m4 (0x08100000..), not the M7 bank.
    assert "$mu_pc >= 0x8100000 && $mu_pc < 0x8200000" in loop


def test_adapter_checks_the_boot_once_for_multi_piece():
    """bug-006 must not regress: exit only at the end, one loop, all pieces run."""
    argv = _argv("stm32h755", ["build/M7/x.elf", "build/M4/y.elf"])
    assert argv.count("program build/M7/x.elf verify reset") == 1
    assert argv.count("program build/M4/y.elf verify reset") == 1
    assert argv.count("exit") == 1 and argv[-1] == "exit"
    assert sum(1 for a in argv if a.startswith("for {set mu_try")) == 1


def test_adapter_without_pieces_emits_no_boot_check():
    """No pieces → no session tail at all (no dangling exit / undefined var)."""
    argv = _argv("stm32f411re", [])
    assert "exit" not in argv
    assert not any(a.startswith("for {set mu_try") for a in argv)


def test_adapter_loud_verdict_when_no_core_boots():
    """A non-converged boot is reported, not hidden (bug-027's core complaint)."""
    argv = _argv("stm32f411re", ["app.elf"])
    joined = " ".join(argv)
    assert "mu-boot: verified" in joined
    assert "DID NOT BOOT" in joined


# --- renderer (`make flash`) -------------------------------------------------


def test_makefile_flash_target_appends_boot_check(tmp_path):
    text = _makefile("stm32wl55jc", tmp_path)
    assert "reset exit" not in text
    assert "-c \"exit\"" in text
    # single-quoted Tcl payload: the shell must not expand the Tcl variables.
    assert "-c 'for {set mu_try 0}" in text
    # every `$mu_*` reaches make doubled (make hands a literal `$` to the shell,
    # and the single quotes stop the shell from expanding it).
    assert re.search(r"(?<!\$)\$mu_(try|out|pc)", text) is None


def test_makefile_per_core_targets_check_their_own_flash_bank(tmp_path):
    text = _makefile("stm32wl55jc", tmp_path)
    m4 = re.search(r"^flash-M4:.*\n\t.*$", text, re.MULTILINE)
    m0 = re.search(r"^flash-M0\+:.*\n\t.*$", text, re.MULTILINE)
    assert m4 and m0
    assert "0x8000000 && $$mu_pc < 0x8020000" in m4.group()
    assert "0x8020000 && $$mu_pc < 0x8040000" in m0.group()


def test_makefile_boot_check_follows_the_program_step(tmp_path):
    text = _makefile("stm32f411re", tmp_path)
    line = re.search(r"^\t.*program \$\(OUT_M4\)\.elf verify reset.*$", text, re.MULTILINE)
    assert line, "flash recipe must program first"
    recipe = line.group()
    assert recipe.index("program") < recipe.index("for {set mu_try")
    assert recipe.rindex("for {set mu_try") < recipe.index('-c "exit"')


# --- one behaviour, one source of truth -------------------------------------


def test_both_flash_sites_emit_the_same_boot_check_commands(tmp_path):
    """`make flash` and `mu flash` must not drift: same commands, same window.

    The Makefile doubles `$` for make and single-quotes for the shell; undoing
    that must reproduce the adapter's `-c` payloads byte for byte.
    """
    for pack in ("stm32f411re", "stm32h755", "stm32wl55jc"):
        text = _makefile(pack, tmp_path)
        payloads = re.findall(r"-c '([^']*)'", text)
        for pack_core in {c.name for c in load_file(PACKS / f"{pack}.yaml").cores}:
            expected = boot_check_commands(
                load_file(PACKS / f"{pack}.yaml").memory, pack_core
            )
            rendered = [p.replace("$$", "$") for p in payloads]
            assert expected[0] in rendered, f"{pack}/{pack_core}: loop drifted"
            assert expected[1] in rendered, f"{pack}/{pack_core}: verdict drifted"
