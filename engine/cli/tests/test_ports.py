"""Port conformance tests (req-005, group 1.1): stubs honor the ABCs."""

import pytest

from engine.adapters import (
    DebugHandle,
    DefaultImageLookup,
    PieceResult,
    ProbeAdapter,
)
from engine.cli.tests.stubs import StubProbeAdapter, make_device_view, make_endpoint


def test_stub_is_a_probe_adapter():
    assert isinstance(StubProbeAdapter(), ProbeAdapter)


def test_ports_flash_returns_one_result_per_piece_in_order():
    stub = StubProbeAdapter()
    device, endpoint = make_device_view(), make_endpoint()
    results = stub.flash(device, endpoint, ["boot", "app", "data"])
    assert [r.name for r in results] == ["boot", "app", "data"]
    assert all(isinstance(r, PieceResult) and r.ok for r in results)
    assert stub.flashed == [("boot", "app", "data")]


def test_ports_flash_reports_per_piece_failure():
    stub = StubProbeAdapter(outcomes={"app": False})
    results = stub.flash(make_device_view(), make_endpoint(), ["boot", "app", "data"])
    by_name = {r.name: r.ok for r in results}
    assert by_name == {"boot": True, "app": False, "data": True}


def test_ports_debug_returns_handle_bound_to_endpoint():
    stub = StubProbeAdapter(session_id="session-9")
    handle = stub.debug(make_device_view(), make_endpoint())
    assert isinstance(handle, DebugHandle)
    assert handle.session_id == "session-9"
    assert handle.endpoint == make_endpoint()
    assert stub.debugged == 1


def test_ports_image_lookup_maps_stacks():
    lookup = DefaultImageLookup()
    assert lookup.image_for("make-cmsis")
    assert lookup.image_for("cargo-cortex")
    assert lookup.image_for("cargo-cortex-dual")
    assert lookup.image_for("esp-idf-rust")
    assert set(lookup.supported_stacks()) == {
        "make-cmsis",
        "cargo-cortex",
        "cargo-cortex-dual",
        "idf-cmake",
        "esp-idf-rust",
    }
    with pytest.raises(ValueError):
        lookup.image_for("nope")
