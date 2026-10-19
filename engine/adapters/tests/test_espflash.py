"""espflash backend tests (req-030)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from engine.adapters import get_adapter
from engine.adapters.espflash import (
    EspflashAdapter,
    Transcript,
    parse_transcript,
)
from engine.core.loader import load_file
from engine.core.model import DeviceView, Endpoint

PACKS = Path(__file__).resolve().parents[3] / "packs"


def _view():
    return DeviceView.of(load_file(PACKS / "esp32cam.yaml"))


def _endpoint() -> Endpoint:
    return Endpoint(transport="uart-serial", address="/dev/ttyUSB0")


def _runner(text: str, rc: int = 0):
    def run(argv: Sequence[str]) -> Transcript:
        return Transcript(argv=tuple(argv), returncode=rc, stdout=text)

    return run


def test_espflash_argv_is_one_elf() -> None:
    argv = EspflashAdapter(runner=_runner("")).render_argv(
        _view(), _endpoint(), ["target/xtensa-esp32-espidf/debug/esp32cam"]
    )
    assert argv == [
        "espflash",
        "flash",
        "--port",
        "/dev/ttyUSB0",
        "--chip",
        "esp32",
        "target/xtensa-esp32-espidf/debug/esp32cam",
    ]


def test_espflash_rejects_multiple_pieces() -> None:
    with pytest.raises(ValueError, match="one ELF"):
        EspflashAdapter(runner=_runner("")).render_argv(
            _view(), _endpoint(), ["a", "b"]
        )


def test_espflash_parse_completed() -> None:
    t = _runner("[INFO] Flashing has completed!\n")
    result = parse_transcript(["app"], t([]))
    assert result[0].ok and result[0].detail == "flashing-completed"


def test_espflash_is_registered() -> None:
    assert isinstance(get_adapter("espflash", runner=_runner("")), EspflashAdapter)
