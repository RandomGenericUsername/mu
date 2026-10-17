"""Boot verification + retry for the flash path (bug-027).

Why this exists (evidence in ``tickets/bug-027-intermittent-reset-boot``):
on a NUCLEO-WL55JC the primary core intermittently latches boot-from-system
memory instead of flash after a debugger-issued reset. Programming still
succeeds (``** Verified OK **``) but the app never runs. The failure is
intermittent per reset, so **retrying the reset converges** — and the one
signal that distinguishes the two states needs no pack-specific register: if
the core is running the app, its PC is inside that core's flash bank, whose
origin and size are already in the pack's memory map.

The emitted command sequence is OpenOCD/jimsh Tcl. One source of truth for
both reset sites (``engine/templates/renderer.py``'s Makefile flash targets
and ``engine/adapters/openocd.py``'s ``mu flash`` argv), so the two cannot
drift.

Design constraints honoured:

* **Pack-independent**: only facts already in the certified model are used
  (the core's flash region). No chip names, no boot register, no magic address.
* **Self-verifying**: the loop stops as soon as the PC is inside flash and
  prints the attempt log, so a flash is no longer silently blind.
* **Leaves the board RUNNING**: the last thing the loop does is ``resume``.

**Known limit (measured, bug-027):** jimsh ``exit 1`` does *not* set OpenOCD's
process return code — ``openocd -c '… exit 1' -c 'exit'`` still exits 0. The
boot verdict therefore cannot be turned into a non-zero rc, and is reported as
a loud ``mu-boot: …`` line instead. Do not "fix" this by adding ``exit 1``
expecting a failing ``make flash``.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol, Sequence

__all__ = [
    "BOOT_CHECK_ATTEMPTS",
    "BOOT_CHECK_SETTLE_MS",
    "PLACEHOLDER_GUARD",
    "TCL_VARS",
    "Region",
    "boot_check_commands",
    "boot_check_command",
    "boot_check_verdict_command",
    "flash_window",
]


class Region(Protocol):
    """The slice of a memory region these helpers read."""

    name: str
    origin: int
    size: int
    cores: Sequence[str]


#: How many ``reset run`` attempts the flash path makes before giving up.
#: Rationale (bug-027): the per-reset boot rate on the bench board is ~30-53%,
#: so an exhausted loop is a ~1e-5..1e-3 event, i.e. the retry turns an
#: intermittent boot latch into a deterministic "board is running" outcome
#: without chasing the (still open) root cause. Each attempt costs
#: ``BOOT_CHECK_SETTLE_MS`` plus reset/halt overhead.
BOOT_CHECK_ATTEMPTS = 10

#: How long the core is given to leave the reset vector before the PC is read.
#: Comfortably longer than the ROM's spin-up; short enough that 10 attempts stay
#: in the low seconds.
BOOT_CHECK_SETTLE_MS = 300

#: The Tcl variables the emitted loop uses. Deliberately prefixed so they cannot
#: collide with a device/pack fact, and quoted here because the generated
#: project's placeholder-leak guard has to exempt exactly these.
TCL_VARS = ("mu_try", "mu_out", "mu_pc")

#: Shared placeholder-leak guard for rendered projects: catches unrendered
#: ``string.Template`` placeholders (``$IDENT`` / ``${IDENT}``; make's
#: ``$(...)`` is legal and excluded) plus the ``{{``/``@@`` syntaxes, while
#: exempting the :data:`TCL_VARS` above — the generated Makefile legitimately
#: contains ``$$mu_try`` (Make hands a literal ``$`` to the recipe). Defined
#: here rather than in each test module so the two guards cannot drift apart.
PLACEHOLDER_GUARD = re.compile(
    r"\$\{(?!(?:" + "|".join(TCL_VARS) + r"))"
    r"|\$(?!(?:" + "|".join(TCL_VARS) + r"))[A-Za-z_]"
    r"|\{\{|@@"
)


def flash_window(memory: Iterable[Region], core_name: str) -> tuple[int, int]:
    """``(origin, end)`` of the boot flash bank for ``core_name``.

    Resolution order mirrors the renderer's per-core region logic: a flash
    region *naming* the core wins (H755 ``flash_m7``/``flash_m4``, WL55JC
    ``flash_m4``/``flash_m0plus``); else the first flash region the core can
    see; else the pack's first flash region. A pack with no flash region at
    all is a loud error, never a plausible-but-wrong default address.
    """
    regions = tuple(memory)
    flash = [r for r in regions if "flash" in r.name.lower()]
    named = [r for r in flash if core_name.lower() in r.name.lower()]
    if named:
        region = named[0]
    else:
        visible = [r for r in flash if not r.cores or core_name in r.cores]
        if not visible:
            raise ValueError(
                f"core {core_name!r} has no flash region: the boot-retry check "
                f"has no address window to compare the PC against"
            )
        region = visible[0]
    return region.origin, region.origin + region.size


def boot_check_command(origin: int, end: int, attempts: int = BOOT_CHECK_ATTEMPTS) -> str:
    """One OpenOCD ``-c`` payload: reset-and-check loop over a flash window.

    Per attempt: ``reset run`` -> settle -> ``halt`` -> read the PC -> ``resume``,
    and ``break`` once the PC is inside ``[origin, end)``. The final ``resume``
    is unconditional, so the board is left running whether or not the loop
    converged. Parsing uses ``capture`` + the *last* word of ``reg pc``
    (``pc (/32): 0x080001ea``) rather than a fixed field position.
    """
    return (
        "for {set mu_try 0} {$mu_try < "
        + str(attempts)
        + "} {incr mu_try} {"
        " reset run; sleep "
        + str(BOOT_CHECK_SETTLE_MS)
        + "; halt;"
        ' set mu_out [capture "reg pc"];'
        " scan [lindex [split $mu_out] end] %x mu_pc;"
        ' echo "mu-boot: attempt $mu_try/'
        + str(attempts)
        + ' pc=0x[format %x $mu_pc]";'
        " resume;"
        " if {$mu_pc >= "
        + hex(origin)
        + " && $mu_pc < "
        + hex(end)
        + '} {echo "mu-boot: RUNNING from flash"; break}'
        " }"
    )


def boot_check_verdict_command(origin: int, end: int, attempts: int = BOOT_CHECK_ATTEMPTS) -> str:
    """The ``-c`` payload that reports the verdict once the loop is done.

    Loud, not fatal: jimsh ``exit 1`` does not reach OpenOCD's return code
    (see the module docstring), so a non-converged boot must stay a diagnostic
    rather than a lying non-zero rc.
    """
    in_flash = "$mu_pc >= " + hex(origin) + " && $mu_pc < " + hex(end)
    return (
        "if {" + in_flash + '}'
        ' {echo "mu-boot: verified"}'
        " else {echo \"mu-boot: DID NOT BOOT after "
        + str(attempts)
        + ' attempts (last pc=0x[format %x $mu_pc], expected inside '
        + hex(origin)
        + ") \"}"
    )


def boot_check_commands(memory: Iterable[Region], core_name: str) -> list[str]:
    """``[loop, verdict]`` for ``core_name`` — the flash path's post-reset tail."""
    origin, end = flash_window(memory, core_name)
    return [boot_check_command(origin, end), boot_check_verdict_command(origin, end)]
