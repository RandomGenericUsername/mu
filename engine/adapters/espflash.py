"""espflash probe backend (req-030): ESP-family ELF flashing.

`espflash` converts an ELF into the ESP32 bootloader + partition table + app
and writes all three. It is the Rust IDF flow; C/C++ keep esptool's explicit
triplet. FlashPort only (no JTAG attach).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from engine.adapters import FlashPort, PieceResult
from engine.core.model import DeviceView, Endpoint, ProofResult

__all__ = [
    "EspflashAdapter",
    "Runner",
    "Transcript",
    "parse_transcript",
    "subprocess_runner",
]

_DONE_RE = re.compile(r"Flashing has completed!")


@dataclass(frozen=True)
class Transcript:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[[Sequence[str]], Transcript]


def subprocess_runner(
    argv: Sequence[str],
    *,
    stream: bool = False,
    log_path: str | Path | None = None,
) -> Transcript:
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
        argv=tuple(argv), returncode=proc.wait(), stdout="".join(chunks), stderr=""
    )


def parse_transcript(
    pieces: Sequence[str], transcript: Transcript
) -> tuple[PieceResult, ...]:
    completed = bool(_DONE_RE.search(transcript.stdout))
    results = []
    for index, name in enumerate(pieces):
        ok = transcript.returncode == 0 and completed and index == 0
        results.append(
            PieceResult(
                name=name,
                ok=ok,
                detail=(
                    "flashing-completed"
                    if ok
                    else (
                        f"exit rc={transcript.returncode}"
                        if transcript.returncode != 0
                        else "missing 'Flashing has completed!' line"
                    )
                ),
            )
        )
    return tuple(results)


class EspflashAdapter(FlashPort):
    """``FlashPort`` via ``espflash flash --port <tty> --chip <target> <ELF>``."""

    def __init__(
        self,
        runner: Runner | None = None,
        *,
        stream: bool = False,
        log_path: str | Path | None = None,
    ) -> None:
        self._runner = runner if runner is not None else subprocess_runner
        self._stream = stream
        self._log_path = log_path
        self.last_transcript: Transcript | None = None

    def render_argv(
        self,
        device: DeviceView,
        endpoint: Endpoint,
        pieces: Sequence[str],
    ) -> list[str]:
        pieces = tuple(pieces)
        if len(pieces) != 1:
            raise ValueError(
                f"espflash flashes one ELF image; got {len(pieces)} pieces"
            )
        sdk = device.block_for("sdkconfig") or {}
        chip = sdk.get("target") if isinstance(sdk, dict) else None
        if not chip:
            raise ValueError(
                f"pack {device.id!r} declares no sdkconfig.target; cannot derive "
                "the espflash chip"
            )
        return [
            "espflash",
            "flash",
            "--port",
            endpoint.address,
            "--chip",
            str(chip),
            pieces[0],
        ]

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
            transcript = subprocess_runner(
                argv, stream=self._stream, log_path=self._log_path
            )
        else:
            transcript = self._runner(argv)
        self.last_transcript = transcript
        return parse_transcript(pieces, transcript)

    def proof_for(
        self,
        device: DeviceView,
        results: Sequence[PieceResult],
        transcript: object,
    ) -> ProofResult:
        results = tuple(results)
        passed = sum(1 for result in results if result.ok)
        return ProofResult(
            rung=device.proof_rung,
            payload={
                "pieces": ",".join(
                    f"{result.name}={'ok' if result.ok else 'fail'}"
                    for result in results
                ),
                "verified": f"{passed}/{len(results)}",
                "sessions": "",
            },
        )
