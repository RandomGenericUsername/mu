"""Structural render harness (req-008): 9 cells, 3 packs x c/cpp/rust.

Each cell asserts the expected file list, zero unrendered placeholders
(``string.Template`` ``$``-leftovers, ``{{``, ``@@``), pack-derived greps
(flags/linker/CMSIS for c/cpp; pins + memory.x origins for rust), and
group-2 full-content greps (build/clean/flash targets, linker sections,
startup note, Cargo pins, build.rs link glue, corrected openocd paths,
config/ wiring).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from engine.core.loader import load_file
from engine.core.bootcheck import PLACEHOLDER_GUARD
from engine.templates.renderer import RUST_PINS, render

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"
PACK_IDS = ("stm32f411re", "stm32h755", "stm32wl55jc")
LANGS = ("c", "cpp", "rust")

# Placeholder leak: $IDENT / ${IDENT} leftovers (make `$(...)` is legal and
# excluded), plus {{ and @@ syntaxes. bug-027's boot-check Tcl variables are
# exempted by the shared guard (engine/core/bootcheck.py:PLACEHOLDER_GUARD).
PLACEHOLDER_RE = PLACEHOLDER_GUARD

SRC_EXT = {"c": "c", "cpp": "c", "rust": "rs"}

# Corrected openocd config paths per spike-001 (board/ vs target/ split).
EXPECTED_OC = {
    "stm32f411re": ("interface/stlink.cfg", "board/st_nucleo_f4.cfg", False),
    "stm32h755": ("interface/stlink-dap.cfg", "board/st_nucleo_h745zi.cfg", True),
    "stm32wl55jc": ("interface/stlink-dap.cfg", "target/stm32wlx.cfg", True),
}


@pytest.fixture(autouse=True)
def _stub_vendoring(monkeypatch) -> None:
    """req-011: render() strictly vendors C/C++ via git; unit renders stub it
    (tmp dirs are non-repos, no network). Wiring is covered in test_vendoring."""
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda _pack_id, _family, _out: [])


def _pack_doc(pack_id: str) -> dict:
    return yaml.safe_load((PACKS_DIR / f"{pack_id}.yaml").read_text())


def _core_slug(name: str) -> str:
    lowered = name.lower().replace("+", "plus")
    return "".join(ch for ch in lowered if ch.isalnum())


def expected_files(pack_id: str, lang: str) -> list[str]:
    """Checklist-encoded file list per cell (literals, not renderer-derived)."""
    doc = _pack_doc(pack_id)
    linker = doc["blocks"]["linker"]
    header = doc["blocks"]["config_headers"]["header"]
    base = ["Makefile" if lang in ("c", "cpp") else "Cargo.toml"]
    if lang in ("c", "cpp"):
        files = list(base)
        for core in doc["cores"]:
            files.append(f"src/main-{core['name']}.c")
            files.append(f"linker/{linker[core['name']]}")
        files.append("Startup/NOTE.md")
    elif doc.get("stacks", {}).get("rust") == "cargo-cortex-dual":
        files = ["Makefile"]
        for core in doc["cores"]:
            slug = _core_slug(core["name"])
            files += [
                f"{slug}/Cargo.toml",
                f"{slug}/.cargo/config.toml",
                f"{slug}/build.rs",
                f"{slug}/memory.x",
                f"{slug}/src/main.rs",
            ]
    else:
        files = [*base, ".cargo/config.toml", "memory.x", "build.rs", "src/main.rs"]
    files += [
        ".gitignore",
        ".mu/stack",
        "README.md",
        "probe/openocd.cfg",
        "probe/probe-serial.cfg",
        f"config/{header}",
        "config/OVERRIDES.md",
    ]
    # bug-021: target-direct dual-core packs get a DUAL_CORE cfg (sourced before
    # the target); board cfgs (H7) set the flag themselves.
    oc = doc["blocks"].get("openocd", {})
    if oc.get("dual_core") and "board" not in oc:
        files.append("probe/dual-core.cfg")
    # bug-031: probe/cpu2-boot.cfg is no longer emitted (it wrote the sibling
    # boot bit on examine-end, masking bug-027).
    return sorted(files)


def _render_cell(pack_id: str, lang: str, tmp_path: Path) -> Path:
    device = load_file(PACKS_DIR / f"{pack_id}.yaml")
    out = tmp_path / pack_id / lang
    written = render(device, lang, out)
    assert [p.relative_to(out).as_posix() for p in written] == expected_files(pack_id, lang)
    return out


def _assert_no_placeholders(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hit = PLACEHOLDER_RE.search(path.read_text())
            assert hit is None, f"{path.relative_to(root)}: unrendered placeholder {hit.group()!r}"


@pytest.mark.parametrize("pack_id", PACK_IDS)
@pytest.mark.parametrize("lang", LANGS)
def test_cells(pack_id: str, lang: str, tmp_path: Path) -> None:
    out = _render_cell(pack_id, lang, tmp_path)
    _assert_no_placeholders(out)
    doc = _pack_doc(pack_id)
    header = doc["blocks"]["config_headers"]["header"]
    if lang in ("c", "cpp"):
        text = (out / "Makefile").read_text()
        for index, core in enumerate(doc["cores"]):
            assert core["arch"] in text, f"arch {core['arch']} missing"
            assert doc["blocks"]["linker"][core["name"]] in text, "linker ref missing"
            assert f"build-{core['name']}" in text, "build target missing"
            for macro in doc["blocks"]["defines"][core["name"]].split():
                assert f"-D{macro}" in text, f"device define {macro} missing"
            assert f"SYSTEM_C_{core['name']}" in text, "system file ref missing"
            assert f"clean-{core['name']}" in text, "clean target missing"
            assert f"flash-{core['name']}" in text, "flash-helper target missing"
            assert f"OUT_{core['name']} = build/{core['name']}/" in text, "artifact dir missing"
            main = (out / f"src/main-{core['name']}.c").read_text()
            assert header in main, "config header include missing"
            if "example" in doc.get("blocks", {}) and index == 0:
                assert (
                    "GPIO_BSRR" in main and "delay_half_period" in main and "LED_PIN" in main
                ), "example blink missing on primary core"
            else:
                # ops-018: non-primary cores get a debuggable counter loop.
                assert "counter" in main and "delay_loop" in main, "sibling example missing"
            linker = (out / f"linker/{doc['blocks']['linker'][core['name']]}").read_text()
            assert "ENTRY(Reset_Handler)" in linker and "MEMORY" in linker
            for sym in ("_estack", "_sdata", "_edata", "_sbss", "_ebss", "_sidata"):
                assert sym in linker, f"startup-required symbol {sym} missing"
            # bug-026: __libc_init_array needs .init_array + its bounds symbols,
            # and KEEP() keeps the constructors out of --gc-sections' reach.
            for sym in (
                "__preinit_array_start",
                "__preinit_array_end",
                "__init_array_start",
                "__init_array_end",
                "__fini_array_start",
                "__fini_array_end",
            ):
                assert sym in linker, f"constructor-array symbol {sym} missing"
            assert "KEEP(*(.init_array*))" in linker, ".init_array must be KEEP()"
            # Ordering: after .isr_vector, before .text, so .data's LMA
            # (AT(LOADADDR(.text) + SIZEOF(.text))) does not overlap them.
            assert linker.index(".isr_vector") < linker.index(".init_array")
            assert linker.index(".init_array") < linker.index(".text :")
        if pack_id == "stm32h755":
            # Independent dual-core: per-core flash selects its OpenOCD target.
            assert "targets stm32h7x.cpu0" in text
            assert "targets stm32h7x.cpu1" in text
        fpu = doc["blocks"]["fpu"]
        assert ("-mfloat-abi=soft" if fpu["mode"] == "soft" else fpu["variant"]) in text
        assert "vendor/CMSIS/CMSIS/Core/Include" in text and "-Iconfig" in text
        # bug-027: the trailing reset is followed by the boot verify-and-retry
        # loop, so `reset exit` no longer appears (the session `exit` is its own
        # `-c` after the loop).
        assert "verify reset" in text, "flash helper must verify+reset"
        assert "reset exit" not in text, "reset must be followed by the boot check"
        assert "mu-boot" in text, "flash helper must carry the boot verify-and-retry"
        assert "Reset_Handler" in (out / "Startup/NOTE.md").read_text()
        if lang == "cpp":
            assert "-std=c++17" in text
    else:
        is_dual = doc.get("stacks", {}).get("rust") == "cargo-cortex-dual"
        if is_dual:
            text = (out / "Makefile").read_text()
            for index, core in enumerate(doc["cores"]):
                slug = _core_slug(core["name"])
                assert f"build-{core['name']}" in text, "per-core build target missing"
                assert f"flash-{core['name']}" in text, "per-core flash target missing"
                assert f"clean-{core['name']}" in text, "per-core clean target missing"
                cargo = (out / slug / "Cargo.toml").read_text()
                for crate, pin in RUST_PINS.items():
                    assert f'{crate} = "{pin}"' in cargo, f"pin {crate} missing"
                assert cargo.count('panic = "abort"') >= 2
                assert 'opt-level = "s"' in cargo, "C++ parity: dev profile must be -Os-like"
                cargo_cfg = (out / slug / ".cargo/config.toml").read_text()
                assert f'target = "{core["arch"]}"' in cargo_cfg
                assert 'linker = "flip-link"' in cargo_cfg
                memx = (out / slug / "memory.x").read_text()
                assert "FLASH" in memx and "RAM" in memx and "_stack_start" in memx
                flash = next(
                    r for r in doc["memory"]
                    if "flash" in r["name"] and core["name"] in r.get("cores", [core["name"]])
                )
                assert f"0x{int(flash['origin_hex'], 16):08X}" in memx
                build_rs = (out / slug / "build.rs").read_text()
                assert "-Tlink.x" in build_rs and "rerun-if-changed" in build_rs
                main = (out / slug / "src/main.rs").read_text()
                assert "#[entry]" in main
                if index == 0:
                    assert "delay_half_period" in main, "primary LED example missing"
                    if doc.get("blocks", {}).get("example", {}).get("cpu2_boot"):
                        assert "__pre_init" in main and "0x5800040C" in main
                else:
                    assert "COUNTER" in main, "sibling counter missing"
            assert "mu-boot" in text, "flash target must carry the boot retry"
            if doc.get("blocks", {}).get("example", {}).get("cpu2_boot"):
                assert "ALL_FLASH = flash-M0+ flash-M4" in text
        else:
            cargo = (out / "Cargo.toml").read_text()
            for crate, pin in RUST_PINS.items():
                assert f'{crate} = "{pin}"' in cargo, f"pin {crate} missing"
            # req-029: flip-link is a linker (config), not an unused build-dep;
            # the dev profile is -Os-like so the blink delay is calibrated.
            assert 'flip-link = "0.1.12"' not in cargo
            assert 'opt-level = "s"' in cargo
            # bug-002: no_std targets cannot unwind — both profiles must abort.
            assert cargo.count('panic = "abort"') >= 2, "panic=abort missing from profiles"
            memx = (out / "memory.x").read_text()
            for region in doc["memory"]:
                origin = int(region["origin_hex"], 16)
                assert f"0x{origin:08X}" in memx, f"region {region['name']} origin missing"
                assert str(region["size"]) in memx, f"region {region['name']} size missing"
            assert "_stack_start" in memx
            build_rs = (out / "build.rs").read_text()
            assert "-Tlink.x" in build_rs and "rerun-if-changed" in build_rs
            main_rs = (out / "src/main.rs").read_text()
            assert "#[entry]" in main_rs
            # req-029: a pack with example.led blinks it instead of wfi.
            assert "delay_half_period" in main_rs
            assert "wfi" not in main_rs
            # bug-025: cargo must pin the pack arch as the build target, or
            # `mu build`/`cargo build` compile for the host and fail to link.
            cargo_cfg = (out / ".cargo/config.toml").read_text()
            assert f'target = "{doc["cores"][0]["arch"]}"' in cargo_cfg, (
                "cargo build target not pinned to the pack arch"
            )
            assert 'linker = "flip-link"' in cargo_cfg
    oc_text = (out / "probe" / "openocd.cfg").read_text()
    iface, cfg_path, dual = EXPECTED_OC[pack_id]
    assert iface in oc_text and cfg_path in oc_text, "corrected openocd path missing"
    if dual and cfg_path.startswith("target/"):
        assert "set DUAL_CORE 1" in oc_text
    overrides = (out / "config/OVERRIDES.md").read_text()
    assert "project" in overrides and "-Iconfig" in overrides, "override doc incomplete"
    assert doc["blocks"]["config_headers"]["library"] in overrides
