"""req-031: generated Makefiles discover per-core and common project sources.

The Makefile is the unit under test: these tests render real pack models (with
vendoring stubbed), add source trees, and ask GNU make to expand the variables
(``make -pRrq``) or print the commands it would run (``make -n``). No ARM
toolchain is needed — recipes are only inspected.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.core.loader import load_file
from engine.templates.renderer import render

from .test_cells import PACKS_DIR


@pytest.fixture(autouse=True)
def _stub_vendoring(monkeypatch) -> None:
    """Unit renders do not clone the pinned submodules (see test_renderer)."""
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda *a, **k: [])
    monkeypatch.setattr("engine.templates.renderer.fetch_svds", lambda *a, **k: [])


def _render(pack_id: str, lang: str, out: Path) -> list[Path]:
    return render(load_file(PACKS_DIR / f"{pack_id}.yaml"), lang, out)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _make_db(root: Path) -> str:
    """GNU make's parsed database, with simple variables already expanded.

    ``OBJS_<core>`` is a ``:=`` variable so ``make -pRrq`` prints the expanded
    object list — the ticket's object-expansion check.
    """
    make = shutil.which("make")
    if make is None:
        pytest.skip("GNU make is required for the generated-Makefile checks")
    done = subprocess.run(
        [make, "-pRrq", "-f", "Makefile", ":"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert "OBJS_M4" in done.stdout or "OBJS_M0+" in done.stdout, done.stderr
    return done.stdout


def _var(db: str, name: str) -> str:
    for prefix in (f"{name} :=", f"{name} =", f"{name} ?="):
        for line in db.splitlines():
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip()
    raise AssertionError(f"{name} not found in make database")


def _stub_vendor_inputs(root: Path, db: str, core: str) -> None:
    """Empty vendor startup/system files so ``make -n`` can resolve prereqs."""
    for var in (f"STARTUP_{core}", f"SYSTEM_C_{core}"):
        rel = _var(db, var)
        _write(root / rel, "")


def test_per_core_discovery_common_sources_and_extra_hook(tmp_path) -> None:
    """src/<core>/**, src/common/**, and EXTRA_SRCS_<core> reach the object list."""
    _render("stm32wl55jc", "c", tmp_path)
    # The documented roots exist immediately (drop-in source dirs).
    assert (tmp_path / "src/M4").is_dir()
    assert (tmp_path / "src/M0+").is_dir()
    assert (tmp_path / "src/common").is_dir()
    _write(tmp_path / "src/M4/extra.c", "int m4_extra(void) { return 4; }\n")
    _write(tmp_path / "src/M4/nested/deep.cpp", 'extern "C" int deep(void) { return 5; }\n')
    _write(tmp_path / "src/M0+/sibling.c", "int m0_extra(void) { return 0; }\n")
    _write(tmp_path / "src/common/common.c", "int common(void) { return 1; }\n")
    _write(tmp_path / "src/common/config/common.cpp", 'extern "C" int common2(void) { return 2; }\n')
    _write(tmp_path / "lib/extra.c", "int lib_extra(void) { return 9; }\n")
    _write(tmp_path / "third_party/isr.cpp", 'extern "C" int lib_isr(void) { return 3; }\n')
    _write(
        tmp_path / "config/sources.mk",
        "EXTRA_SRCS_M4 = lib/extra.c third_party/isr.cpp\n",
    )

    db = _make_db(tmp_path)
    m4 = _var(db, "OBJS_M4").split()
    m0 = _var(db, "OBJS_M0+").split()

    # Core, nested core, common, and library sources all map under build/<core>.
    assert "build/M4/src/M4/extra.o" in m4
    assert "build/M4/src/M4/nested/deep.o" in m4
    assert "build/M4/src/common/common.o" in m4
    assert "build/M4/src/common/config/common.o" in m4
    assert "build/M4/lib/extra.o" in m4
    assert "build/M4/third_party/isr.o" in m4
    # Existing shape stays: main, startup, system.
    assert "build/M4/src/main-M4.o" in m4
    assert "build/M4/startup-M4.o" in m4
    assert "build/M4/system-M4.o" in m4

    # M0+ gets its own sources and the common ones, never M4's.
    assert "build/M0+/src/M0+/sibling.o" in m0
    assert "build/M0+/src/common/common.o" in m0
    assert "build/M0+/src/common/config/common.o" in m0
    assert not any("src/M4/" in obj for obj in m0)
    assert not any("lib/extra" in obj or "third_party" in obj for obj in m0)

    # No global src/* glob: discovery is per-core + common only.
    makefile = (tmp_path / "Makefile").read_text()
    assert "wildcard src/*" not in makefile
    assert "$(call rwildcard,src/M4/" in makefile
    assert "$(call rwildcard,src/M0+/" in makefile
    assert "$(call rwildcard,src/common/" in makefile
    assert "M0+" not in _var(db, "SRCS_M4")
    assert "src/M4/" not in _var(db, "SRCS_M0+")


def test_c_sources_use_cc_and_cpp_uses_cxx_with_cxx_link(tmp_path) -> None:
    """A C-stack project with a C++ extra compiles .c with CC, .cpp with CXX,
    and links the core with CXX (req-031 decision D4/D5)."""
    _render("stm32f411re", "c", tmp_path)
    _write(tmp_path / "src/M4/extra.cpp", 'extern "C" int extra(void) { return 4; }\n')
    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M4")

    done = subprocess.run(
        ["make", "-n", "build-M4"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    commands = done.stdout.splitlines()

    main = next(c for c in commands if "-o build/M4/src/main-M4.o" in c)
    extra = next(c for c in commands if "-o build/M4/src/M4/extra.o" in c)
    link = next(c for c in commands if "-o build/M4/stm32f411re-M4.elf" in c)

    assert main.startswith("arm-none-eabi-gcc ")
    assert " -std=c++17" not in main, "C source must not get C++ flags"
    assert extra.startswith("arm-none-eabi-g++ ")
    assert "-std=c++17" in extra
    assert link.startswith("arm-none-eabi-g++ ")


def test_c_only_core_keeps_stack_c_link_driver(tmp_path) -> None:
    """WL55 M0+ has no .cpp source, so it links with the stack compiler (CC)."""
    _render("stm32wl55jc", "c", tmp_path)
    _write(tmp_path / "src/M0+/extra.c", "int m0_extra(void) { return 0; }\n")
    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M0+")

    done = subprocess.run(
        ["make", "-n", "build-M0+"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    link = next(
        c for c in done.stdout.splitlines()
        if "-o build/M0+/stm32wl55jc-M0+.elf" in c
    )
    assert link.startswith("arm-none-eabi-gcc ")


def test_sources_hook_is_optional_and_project_owned(tmp_path) -> None:
    """A missing config/sources.mk is ignored; a present one is never rewritten."""
    written = _render("stm32f411re", "c", tmp_path)
    sources = tmp_path / "config/sources.mk"
    assert not sources.exists()
    assert all(p.name != "sources.mk" for p in written)
    assert "-include config/sources.mk" in (tmp_path / "Makefile").read_text()

    # No file: make still parses and keeps the existing main/startup/system list.
    db = _make_db(tmp_path)
    objs = _var(db, "OBJS_M4").split()
    assert "build/M4/src/main-M4.o" in objs
    assert "build/M4/startup-M4.o" in objs
    assert "build/M4/system-M4.o" in objs

    # Present: the generated file wins nothing — re-rendering leaves it intact.
    sources.write_text("EXTRA_SRCS_M4 = lib/library.c\n")
    _write(tmp_path / "lib/library.c", "int library(void) { return 9; }\n")
    _render("stm32f411re", "c", tmp_path)
    assert sources.read_text() == "EXTRA_SRCS_M4 = lib/library.c\n"
    assert "build/M4/lib/library.o" in _var(_make_db(tmp_path), "OBJS_M4").split()


def test_readme_documents_source_layout_and_hook(tmp_path) -> None:
    _render("stm32f411re", "c", tmp_path)
    readme = (tmp_path / "README.md").read_text()
    assert "src/<core>/" in readme
    assert "src/common/" in readme
    assert "config/sources.mk" in readme
    assert "EXTRA_SRCS_<core>" in readme
    assert "-include" in readme
    assert "$(CC)" in readme and "$(CXX)" in readme
