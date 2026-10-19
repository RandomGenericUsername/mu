"""OpenOCD adapter tests (req-006, groups 1.1-1.2).

Subprocess is always faked: no ``openocd`` binary required. Fixture
transcripts come from :mod:`engine.adapters.openocd` (marked FIXTURE,
never live runs). Pack vectors load the repo's corrected packs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from engine.adapters import PieceResult, ProbeAdapter
from engine.adapters.openocd import (
    DUAL_CORE_FIXTURE,
    DUAL_CORE_TCL,
    VERIFY_OK_FIXTURE,
    OpenOCDAdapter,
    Transcript,
    parse_transcript,
    session_names,
)
from engine.core.loader import load_file
from engine.core.model import (
    Core,
    Device,
    DeviceView,
    Endpoint,
    MemoryRegion,
    OpenocdConfig,
)

PACKS = Path(__file__).resolve().parents[3] / "packs"


def _device_view(**kw) -> DeviceView:
    base = dict(
        id="generic-board",
        version="1.0.0",
        source_hash="sha256:test",
        cores=[Core(name="core0", arch="generic-arch")],
        memory=[MemoryRegion(name="flash", origin_hex="0x08000000", size=64 * 1024)],
        probe_ref=Endpoint(transport="generic-probe", address="usb:0"),
        proof_rung="frame",
        openocd=OpenocdConfig(interface="iface.cfg", target="board.cfg", board="board.cfg"),
    )
    base.update(kw)
    return DeviceView.of(Device(**base))


def _endpoint(address: str = "/dev/node-0") -> Endpoint:
    return Endpoint(transport="generic-probe", address=address)


def _fake_runner(text: str, rc: int = 0, calls: list | None = None):
    def run(argv: Sequence[str]) -> Transcript:
        if calls is not None:
            calls.append(list(argv))
        return Transcript(argv=tuple(argv), returncode=rc, stdout=text)

    return run


def test_openocd_adapter_satisfies_probe_port():
    assert isinstance(OpenOCDAdapter(runner=_fake_runner("")), ProbeAdapter)


def test_openocd_argv_renders_from_model_fields_only():
    adapter = OpenOCDAdapter(runner=_fake_runner(""))
    argv = adapter.render_argv(_device_view(), _endpoint(), ["alpha", "beta"])
    assert argv[:5] == ["openocd", "-f", "interface/iface.cfg", "-f", "board/board.cfg"]
    assert DUAL_CORE_TCL not in argv  # single-core: no session flag
    assert "set PROBE_ADDRESS" not in " ".join(argv)
    assert "program alpha verify reset" in argv
    assert "program beta verify reset" in argv
    # bug-006: still exactly one `exit`, and it is last (not a per-piece tail).
    assert argv[-1] == "exit"
    assert argv.count("exit") == 1


def test_openocd_argv_dual_core_selects_target_per_piece():
    """bug-006: two pieces → each core's target selected; exit only on the last."""
    view = DeviceView.of(load_file(PACKS / "stm32h755.yaml"))
    argv = OpenOCDAdapter(runner=_fake_runner("")).render_argv(
        view, _endpoint(), ["build/M7/x.elf", "build/M4/y.elf"]
    )
    joined = " ".join(argv)
    assert "targets stm32h7x.cpu0" in joined and "targets stm32h7x.cpu1" in joined
    assert "program build/M7/x.elf verify reset" in joined
    assert "program build/M4/y.elf verify reset" in joined
    assert argv[-1] == "exit"
    assert argv.count("exit") == 1


def test_openocd_argv_target_only_pack_uses_target_prefix():
    view = _device_view(openocd=OpenocdConfig(interface="i.cfg", target="t.cfg"))
    argv = OpenOCDAdapter(runner=_fake_runner("")).render_argv(view, _endpoint(), [])
    assert "interface/i.cfg" in argv and "target/t.cfg" in argv


def test_openocd_argv_bare_serial_selector_pins_probe():
    view = _device_view()
    argv = OpenOCDAdapter(runner=_fake_runner("")).render_argv(
        view, _endpoint("STL-1"), []
    )
    assert "adapter serial STL-1" in argv


def test_openocd_argv_path_address_is_not_a_selector():
    view = _device_view()
    argv = OpenOCDAdapter(runner=_fake_runner("")).render_argv(
        view, _endpoint("/dev/ttyACM0"), []
    )
    assert all("adapter serial" not in a for a in argv)


def test_openocd_argv_dual_core_adds_session_flag():
    view = _device_view(
        openocd=OpenocdConfig(interface="i.cfg", target="t.cfg", dual_core=True)
    )
    argv = OpenOCDAdapter(runner=_fake_runner("")).render_argv(view, _endpoint(), [])
    assert "interface/i.cfg" in argv and "target/t.cfg" in argv
    assert DUAL_CORE_TCL in argv


def test_openocd_argv_missing_openocd_facts_raise():
    view = DeviceView.of(
        Device(
            id="bare",
            version="1.0.0",
            source_hash="sha256:x",
            cores=[Core(name="c", arch="a")],
            memory=[MemoryRegion(name="m", origin_hex="0x0", size=8)],
            probe_ref=_endpoint(),
            proof_rung="frame",
        )
    )
    import pytest

    with pytest.raises(ValueError, match="openocd"):
        OpenOCDAdapter(runner=_fake_runner("")).render_argv(view, _endpoint(), ["p"])


def test_openocd_flash_verify_ok_fixture_per_piece():
    calls: list = []
    adapter = OpenOCDAdapter(runner=_fake_runner(VERIFY_OK_FIXTURE, calls=calls))
    results = adapter.flash(_device_view(), _endpoint(), ["app"])
    assert [r.name for r in results] == ["app"]
    assert all(isinstance(r, PieceResult) and r.ok for r in results)
    sent = calls[0]
    assert sent[:5] == ["openocd", "-f", "interface/iface.cfg", "-f", "board/board.cfg"]


def test_openocd_flash_partial_and_failed_transcripts():
    adapter = OpenOCDAdapter(runner=_fake_runner(VERIFY_OK_FIXTURE))
    partial = adapter.flash(_device_view(), _endpoint(), ["a", "b", "c"])
    assert [r.ok for r in partial] == [True, False, False]
    failed = OpenOCDAdapter(runner=_fake_runner("boom", rc=1)).flash(
        _device_view(), _endpoint(), ["a"]
    )
    assert failed[0].ok is False and "rc=1" in failed[0].detail


def test_openocd_flash_empty_pieces_runs_nothing():
    calls: list = []
    adapter = OpenOCDAdapter(runner=_fake_runner(VERIFY_OK_FIXTURE, calls=calls))
    assert adapter.flash(_device_view(), _endpoint(), []) == ()
    assert calls == []


def test_openocd_debug_binds_shim_endpoint():
    endpoint = _endpoint()
    handle = OpenOCDAdapter(runner=_fake_runner("")).debug(_device_view(), endpoint)
    assert handle.endpoint == endpoint
    assert handle.session_id.startswith("openocd:")


def test_openocd_source_carries_no_board_names():
    src = (Path(__file__).resolve().parent.parent / "openocd.py").read_text()
    hits = re.findall(r"nucleo|f411|h755|wl55", src, re.IGNORECASE)
    assert hits == [], f"board/chip names leaked into adapter: {hits}"


def test_openocd_parse_transcript_counts_verified_ok():
    tx = Transcript(argv=("openocd",), returncode=0, stdout=VERIFY_OK_FIXTURE)
    (only,) = parse_transcript(["solo"], tx)
    assert only.ok and only.detail == "verified-ok"
    assert session_names(tx) == ()


def test_openocd_dual_core_fixture_session_lines():
    tx = Transcript(argv=("openocd",), returncode=0, stdout=DUAL_CORE_FIXTURE)
    assert session_names(tx) == ("core0", "core1")
    results = parse_transcript(["first", "second"], tx)
    assert [r.ok for r in results] == [True, True]


def test_proof_single_core_payload_fills_core_struct():
    from engine.core.model import ProofResult

    view = _device_view()
    tx = Transcript(argv=("openocd",), returncode=0, stdout=VERIFY_OK_FIXTURE)
    results = parse_transcript(["solo"], tx)
    proof = OpenOCDAdapter(runner=_fake_runner("")).proof_for(view, results, tx)
    assert isinstance(proof, ProofResult)
    assert proof.rung == "frame"
    assert proof.as_dict() == {
        "pieces": "solo=ok",
        "verified": "1/1",
        "sessions": "",
    }


def test_proof_loader_carries_openocd_block_facts():
    single = DeviceView.of(load_file(PACKS / "stm32f411re.yaml"))
    assert (single.openocd_interface, single.openocd_target) == (
        "stlink.cfg",
        "st_nucleo_f4.cfg",
    )
    assert single.openocd_dual_core is False
    dual_board = DeviceView.of(load_file(PACKS / "stm32h755.yaml"))
    assert dual_board.openocd_dual_core is True
    assert dual_board.openocd_interface == "stlink-dap.cfg"
    dual_target = DeviceView.of(load_file(PACKS / "stm32wl55jc.yaml"))
    assert (dual_target.openocd_interface, dual_target.openocd_target) == (
        "stlink-dap.cfg",  # bug-021: HLA cannot do multicore
        "stm32wlx.cfg",
    )
    assert dual_target.openocd_dual_core is True


def test_proof_dual_session_vectors_fill_per_core_pieces():
    view = DeviceView.of(load_file(PACKS / "stm32h755.yaml"))
    assert [c.name for c in view.cores] == ["M7", "M4"]
    assert view.proof_rung == "readback-m7-m4"
    calls: list = []
    adapter = OpenOCDAdapter(runner=_fake_runner(DUAL_CORE_FIXTURE, calls=calls))
    endpoint = Endpoint(transport=view.probe_transport, address="/dev/node-0")
    results = adapter.flash(view, endpoint, ["flash_m7", "flash_m4"])
    assert [r.ok for r in results] == [True, True]
    argv = calls[0]
    assert "interface/stlink-dap.cfg" in argv and DUAL_CORE_TCL in argv
    proof = adapter.proof_for(
        view, results, Transcript(tuple(argv), 0, DUAL_CORE_FIXTURE)
    )
    assert proof.rung == "readback-m7-m4"
    assert proof.as_dict() == {
        "pieces": "flash_m7=ok,flash_m4=ok",
        "verified": "2/2",
        "sessions": "core0,core1",
    }


def test_cpu2_boot_pack_flashes_single_core_sibling_first():
    """req-028: a released sibling cannot be reset; program both pieces
    through cpu0, without DUAL_CORE/per-core targets, and check the primary."""
    view = DeviceView.of(load_file(PACKS / "stm32wl55jc.yaml"))
    assert view.flash_single_core is True
    adapter = OpenOCDAdapter(runner=_fake_runner(""))
    argv = adapter.render_argv(
        view, _endpoint(), ["build/M0+/x.elf", "build/M4/y.elf"]
    )
    joined = " ".join(argv)
    assert "targets" not in argv, "no per-core target selection for cpu2_boot"
    assert "program build/M0+/x.elf verify reset" in argv
    assert "program build/M4/y.elf verify reset" in argv
    # The primary owns the release/boot state; check its window (not cpu1's).
    assert "$mu_pc >= 0x8000000 && $mu_pc < 0x8020000" in joined
    assert "stm32wlx.cpu1" not in joined
