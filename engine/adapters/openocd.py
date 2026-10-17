"""OpenOCD probe backend (req-006, groups 1.1-1.2): model-only rendering.

Argv is built strictly from certified model fields (interface/target/
dual-core flag via :class:`engine.core.model.DeviceView` + endpoint
address from the shim) — no board or chip names appear in this module.

Subprocess boundary: :class:`OpenOCDAdapter` shells the ``openocd``
binary through an injectable runner seam (a ``Callable[[argv],
Transcript]``). Tests inject fakes; production passes
:func:`subprocess_runner` (real ``subprocess``). No binary is required
at test time.

Transcript fixtures below are authored from documented output formats
(OpenOCD User's Guide: ``** Verified OK **`` programming lines,
``Info : <target> examined`` session lines) — they are marked
FIXTURE and are never live-probe claims. Live runs stay OPEN.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Sequence

from engine.adapters import DebugHandle, PieceResult, ProbeAdapter
from engine.core.bootcheck import boot_check_commands
from engine.core.model import DeviceView, Endpoint, ProofResult

__all__ = [
    "DUAL_CORE_FIXTURE",
    "OpenOCDAdapter",
    "Runner",
    "Transcript",
    "VERIFY_OK_FIXTURE",
    "parse_transcript",
    "session_names",
    "subprocess_runner",
]

#: Extra ``-c`` command rendered when the model carries DUAL_CORE: lists
#: session targets so each core's session line lands in the transcript.
DUAL_CORE_TCL = "targets"

#: OpenOCD flash-programming success line (User's Guide format).
_VERIFY_OK_RE = re.compile(r"\*\* Verified OK \*\*")

#: OpenOCD session line format: ``Info : <name> examined``.
_SESSION_RE = re.compile(r"^Info\s*:\s*(\S+)\s+examined", re.MULTILINE)


@dataclass(frozen=True)
class Transcript:
    """Captured tool run: argv + exit code + text streams."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str = ""


#: Runner seam: argv in, transcript out. Fake in tests, subprocess in prod.
Runner = Callable[[Sequence[str]], Transcript]


def subprocess_runner(
    argv: Sequence[str],
    *,
    stream: bool = False,
    log_path: str | Path | None = None,
) -> Transcript:
    """Production runner: exec argv via ``subprocess``, capture output.

    ``stream=True`` additionally passes tool output through to the terminal
    live (merged stdout+stderr) while still capturing the transcript;
    ``log_path`` tees the same bytes to a file. Plain calls behave exactly
    as before (capture only), so injected test fakes are unaffected.
    """
    if not stream and log_path is None:
        completed = subprocess.run(list(argv), capture_output=True, text=True)
        return Transcript(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    proc = subprocess.Popen(
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    chunks: list[str] = []
    log_fh = open(str(log_path), "a") if log_path is not None else None
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            chunks.append(line)
            if log_fh is not None:
                log_fh.write(line)
    finally:
        if log_fh is not None:
            log_fh.close()
    return Transcript(
        argv=tuple(argv),
        returncode=proc.wait(),
        stdout="".join(chunks),
        stderr="",
    )


# --- FIXTURE (not a live run): single-core verify-OK transcript. --------
# Format per OpenOCD User's Guide ("** Programming Started **" /
# "** Verified OK **" flash programming lines).
VERIFY_OK_FIXTURE = """\
Open On-Chip Debugger
** Programming Started **
** Programming Finished **
** Verified OK **
shutdown command invoked
"""

# --- FIXTURE (not a live run): dual-core session transcript. ------------
# Session lines per OpenOCD "Info : <target> examined" format, one
# "** Verified OK **" programming line per core session.
DUAL_CORE_FIXTURE = """\
Open On-Chip Debugger
Info : core0 examined
Info : core1 examined
** Programming Started **
** Verified OK **
** Programming Started **
** Verified OK **
shutdown command invoked
"""


def session_names(transcript: Transcript) -> tuple[str, ...]:
    """Target names from ``Info : <name> examined`` session lines, in order."""
    return tuple(_SESSION_RE.findall(transcript.stdout))


def parse_transcript(
    pieces: Sequence[str], transcript: Transcript
) -> tuple[PieceResult, ...]:
    """Map one transcript to per-piece results, in piece order.

    Piece ``i`` passes iff the run exited 0 and at least ``i+1``
    ``** Verified OK **`` lines are present.
    """
    verified = len(_VERIFY_OK_RE.findall(transcript.stdout))
    results: list[PieceResult] = []
    for index, name in enumerate(pieces):
        ok = transcript.returncode == 0 and index < verified
        if ok:
            detail = "verified-ok"
        elif transcript.returncode != 0:
            detail = f"exit rc={transcript.returncode}"
        else:
            detail = "missing Verified OK line"
        results.append(PieceResult(name=name, ok=ok, detail=detail))
    return tuple(results)


def _serial_selector(address: str) -> str | None:
    """Return a bare adapter-serial selector, or ``None``.

    OpenOCD pins a probe via ``adapter serial <serial>``. A filesystem path or
    a ``VID:PID`` pair is not a serial, so those fall through to the tool's
    default discovery (single attached probe).
    """
    if not address or address.startswith("/") or ":" in address:
        return None
    return address


def _piece_target(device: DeviceView, index: int, count: int) -> str | None:
    """OpenOCD target name for piece ``index`` (dual-core multi-piece flash).

    Selected only when the model is dual-core, the pack maps cores to target
    names, and one piece is supplied per core (in core order). Otherwise the
    tool's default target is used.
    """
    if not device.openocd_dual_core or not device.openocd_targets:
        return None
    if count != len(device.cores):
        return None
    core = device.cores[index].name
    for name, target in device.openocd_targets:
        if name == core:
            return target
    return None


def _boot_check_argv(
    device: DeviceView, pieces: Sequence[str], last: int
) -> list[str]:
    """`-c <loop> -c <verdict>` for the piece that runs last (bug-027).

    Only the **last** piece's boot check is emitted: it is the one whose reset
    decides the board's final state, and an extra check per piece would halt
    cores that were just programmed. The core is resolved the same way
    :func:`_piece_target` resolves the target, so the checked flash bank is the
    bank that piece was programmed into. Falls back to the first core when the
    pack declares no per-piece targets (single-core packs).
    """
    index = last if _piece_target(device, last, len(pieces)) is not None else 0
    if index >= len(device.cores):
        index = 0
    core = device.cores[index].name
    out: list[str] = []
    for command in boot_check_commands(device.memory, core):
        out += ["-c", command]
    return out


class OpenOCDAdapter(ProbeAdapter):
    """``ProbeAdapter`` via ``openocd -f <interface> -f <target>``."""

    def __init__(self, runner: Runner | None = None, *, stream: bool = False, log_path: str | Path | None = None) -> None:
        self._runner = runner if runner is not None else subprocess_runner
        self._stream = stream
        self._log_path = log_path
        #: Transcript of the most recent :meth:`flash` (else ``None``); feeds
        #: :meth:`proof_for` so verdicts carry proof without widening the ABC.
        self.last_transcript: Transcript | None = None

    def render_argv(
        self,
        device: DeviceView,
        endpoint: Endpoint,
        pieces: Sequence[str],
    ) -> list[str]:
        """Build argv strictly from model fields + shim endpoint.

        ``-f`` files come from the model's resolved config-file paths
        (``interface/…`` + ``board/…|target/…``, bug-003); each piece adds a
        ``program <piece> verify reset`` step; DUAL_CORE models add the
        session-listing command. Probe selection is emitted only when the
        endpoint carries a bare serial selector. Missing facts raise.

        A single ``exit`` closes the session, after a boot verify-and-retry
        loop for the last piece's core (bug-027) — the trailing reset that
        ``program … verify reset exit`` used to end on is not reliable, and
        ``** Verified OK **` does not mean the app is running.
        """
        config_files = device.openocd_config_files
        if not config_files:
            raise ValueError("device model carries no openocd config-file facts")
        argv = ["openocd", "-f", config_files[0], "-f", config_files[1]]
        if device.openocd_dual_core:
            argv += ["-c", DUAL_CORE_TCL]
        serial = _serial_selector(endpoint.address)
        if serial is not None:
            argv += ["-c", f"adapter serial {serial}"]
        last = len(pieces) - 1
        for index, piece in enumerate(pieces):
            target = _piece_target(device, index, len(pieces))
            if target is not None:
                argv += ["-c", f"targets {target}"]
            # Reset after each piece, but `exit` only on the last: a bare
            # `reset exit` (or an early per-piece `exit`) makes OpenOCD return
            # non-zero / drop later pieces (bug-006).
            argv += ["-c", f"program {piece} verify reset"]
        if pieces:
            # bug-027: that trailing reset intermittently latches the core
            # into boot-from-system-memory, and `** Verified OK **` still
            # prints — so append the shared verify-and-retry tail for the LAST
            # piece's core (the one whose reset decides the final board state).
            # Same commands the generated Makefile emits (engine.core.bootcheck).
            argv += _boot_check_argv(device, pieces, last)
            argv += ["-c", "exit"]
        return argv

    def flash(
        self,
        device: DeviceView,
        endpoint: Endpoint,
        pieces: Sequence[str],
    ) -> Sequence[PieceResult]:
        pieces = tuple(pieces)
        if not pieces:
            return ()
        argv = self.render_argv(device, endpoint, pieces)
        if self._stream or self._log_path is not None:
            if self._runner is not subprocess_runner:
                raise ValueError(
                    "streaming requires the default subprocess runner "
                    "(injected fakes capture instead)"
                )
            transcript = subprocess_runner(argv, stream=self._stream, log_path=self._log_path)
        else:
            transcript = self._runner(argv)
        self.last_transcript = transcript
        return parse_transcript(pieces, transcript)

    def debug(self, device: DeviceView, endpoint: Endpoint) -> DebugHandle:
        # No live attach here (no probe claim): deterministic handle
        # bound to the shim endpoint; live sessions stay OPEN.
        self.render_argv(device, endpoint, ())
        return DebugHandle(session_id=f"openocd:{endpoint.address}", endpoint=endpoint)

    def proof_for(
        self,
        device: DeviceView,
        results: Sequence[PieceResult],
        transcript: Transcript,
    ) -> ProofResult:
        """Fill the core-owned proof struct for ``device.proof_rung``.

        Payload keys (generic, backend-comparable): ``pieces`` per-piece
        verdicts, ``verified`` ok/total count, ``sessions`` examined
        session names ("" when none).
        """
        results = tuple(results)
        passed = sum(1 for r in results if r.ok)
        payload = {
            "pieces": ",".join(f"{r.name}={'ok' if r.ok else 'fail'}" for r in results),
            "verified": f"{passed}/{len(results)}",
            "sessions": ",".join(session_names(transcript)),
        }
        return ProofResult(rung=device.proof_rung, payload=payload)
