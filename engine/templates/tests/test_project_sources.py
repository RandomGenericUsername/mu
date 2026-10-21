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
    # Existing shape stays: main (now per-core), startup, system.
    assert "build/M4/src/M4/main.o" in m4
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

    main = next(c for c in commands if "-o build/M4/src/M4/main.o" in c)
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
    assert "build/M4/src/M4/main.o" in objs
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


# --- req-032: per-core library flags and C++ entry point ---


def test_cpp_lang_renders_per_core_cpp_main_compiled_and_linked_with_cxx(tmp_path) -> None:
    """`--lang cpp` emits src/<core>/main.cpp; SRCS and the .cpp rule use it."""
    _render("stm32f411re", "cpp", tmp_path)
    assert (tmp_path / "src/M4/main.cpp").is_file()
    assert not (tmp_path / "src/M4/main.c").exists()
    assert not (tmp_path / "src/main-M4.cpp").exists()
    assert list((tmp_path / "src").glob("main-*")) == []

    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M4")
    assert "build/M4/src/M4/main.o" in _var(db, "OBJS_M4").split()
    assert "src/M4/main.cpp" in (tmp_path / "Makefile").read_text()

    done = subprocess.run(
        ["make", "-n", "build-M4"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    commands = done.stdout.splitlines()
    main = next(c for c in commands if "-o build/M4/src/M4/main.o" in c)
    link = next(c for c in commands if "-o build/M4/stm32f411re-M4.elf" in c)
    assert main.startswith("arm-none-eabi-g++ "), main
    assert "-std=c++17" in main
    assert link.startswith("arm-none-eabi-g++ "), link


def test_c_lang_renders_per_core_c_main_compiled_and_linked_with_cc(tmp_path) -> None:
    """`--lang c` keeps the C entry point: src/<core>/main.c via $(CC)."""
    _render("stm32f411re", "c", tmp_path)
    assert (tmp_path / "src/M4/main.c").is_file()
    assert not (tmp_path / "src/M4/main.cpp").exists()
    assert not (tmp_path / "src/main-M4.c").exists()
    assert list((tmp_path / "src").glob("main-*")) == []

    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M4")
    done = subprocess.run(
        ["make", "-n", "build-M4"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    commands = done.stdout.splitlines()
    main = next(c for c in commands if "-o build/M4/src/M4/main.o" in c)
    link = next(c for c in commands if "-o build/M4/stm32f411re-M4.elf" in c)
    assert main.startswith("arm-none-eabi-gcc "), main
    assert " -std=c++17" not in main
    assert link.startswith("arm-none-eabi-gcc "), link


@pytest.mark.parametrize(
    "pack_id,lang,expected",
    [
        ("stm32f411re", "cpp", ["src/M4/main.cpp"]),
        ("stm32h755", "c", ["src/M7/main.c", "src/M4/main.c"]),
        ("stm32wl55jc", "cpp", ["src/M4/main.cpp", "src/M0+/main.cpp"]),
    ],
)
def test_per_core_main_paths_and_no_root_main(pack_id, lang, expected, tmp_path) -> None:
    """req-033: one entry point per core dir; nothing at the src/ root."""
    _render(pack_id, lang, tmp_path)
    found = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in (tmp_path / "src").glob("*/main.*")
    )
    assert found == sorted(expected)
    assert list((tmp_path / "src").glob("main-*")) == []
    makefile = (tmp_path / "Makefile").read_text()
    assert "src/main-" not in makefile
    for rel in expected:
        assert rel in makefile


def test_extra_source_next_to_main_does_not_duplicate_main_object(tmp_path) -> None:
    """req-033: src/M4/extra.cpp coexists with one and only one main object."""
    _render("stm32wl55jc", "cpp", tmp_path)
    _write(tmp_path / "src/M4/extra.cpp", 'extern "C" int req033_extra(){return 3;}\n')
    db = _make_db(tmp_path)
    m4 = _var(db, "OBJS_M4").split()
    assert m4.count("build/M4/src/M4/main.o") == 1
    assert m4.count("build/M4/src/M4/extra.o") == 1
    assert [obj for obj in m4 if obj.endswith("/main.o")] == ["build/M4/src/M4/main.o"]
    # The explicit MAIN_<core> variable is what the wildcard filter removes.
    assert _var(db, "MAIN_M4") == "src/M4/main.cpp"


def test_extra_inc_and_suffix_flags_from_config_sources(tmp_path) -> None:
    """EXTRA_INC reaches C and C++; EXTRA_CFLAGS only .c, EXTRA_CXXFLAGS only .cpp."""
    _render("stm32f411re", "c", tmp_path)
    _write(tmp_path / "src/M4/a.c", "int a(void) { return 1; }\n")
    _write(tmp_path / "src/M4/b.cpp", 'extern "C" int b(void) { return 2; }\n')
    _write(
        tmp_path / "config/sources.mk",
        "EXTRA_INC_M4 = -Ithird_party/lib/include\n"
        "EXTRA_CFLAGS_M4 = -DEXTRA_C_ONLY\n"
        "EXTRA_CXXFLAGS_M4 = -DEXTRA_CXX_ONLY\n",
    )
    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M4")

    done = subprocess.run(
        ["make", "-n", "build-M4"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    commands = done.stdout.splitlines()
    c_cmd = next(c for c in commands if "-o build/M4/src/M4/a.o" in c)
    cpp_cmd = next(c for c in commands if "-o build/M4/src/M4/b.o" in c)
    link = next(c for c in commands if "-o build/M4/stm32f411re-M4.elf" in c)

    # EXTRA_INC is shared, after the base flags.
    assert "-Ithird_party/lib/include" in c_cmd
    assert "-Ithird_party/lib/include" in cpp_cmd
    assert c_cmd.index("-Wall") < c_cmd.index("-Ithird_party/lib/include")
    assert cpp_cmd.index("-Wall") < cpp_cmd.index("-Ithird_party/lib/include")

    # Suffix-specific flags never cross over.
    assert "-DEXTRA_C_ONLY" in c_cmd
    assert "-DEXTRA_C_ONLY" not in cpp_cmd
    assert "-DEXTRA_CXX_ONLY" in cpp_cmd
    assert "-DEXTRA_CXX_ONLY" not in c_cmd

    # Link carries common flags (include path), not compile-only C flags.
    assert "-Ithird_party/lib/include" in link
    assert "-DEXTRA_C_ONLY" not in link
    assert "-DEXTRA_CXX_ONLY" not in link


def test_extra_hook_is_a_noop_without_config_sources(tmp_path) -> None:
    """No config/sources.mk: the extra variables expand empty, no stray flags."""
    _render("stm32f411re", "c", tmp_path)
    assert not (tmp_path / "config/sources.mk").exists()
    makefile = (tmp_path / "Makefile").read_text()
    for var in ("EXTRA_INC_M4 ?=", "EXTRA_CFLAGS_M4 ?=", "EXTRA_CXXFLAGS_M4 ?="):
        assert var in makefile

    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M4")
    done = subprocess.run(
        ["make", "-n", "build-M4"], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert "EXTRA_" not in done.stdout


def test_h755_m7_links_with_cc_and_m4_with_cxx(tmp_path) -> None:
    """A .cpp library source on M4 alone switches only M4's link driver to CXX."""
    _render("stm32h755", "c", tmp_path)
    _write(
        tmp_path / "third_party/lib/src/isr.cpp",
        'extern "C" int lib_isr(void) { return 3; }\n',
    )
    _write(
        tmp_path / "config/sources.mk",
        "EXTRA_SRCS_M4 = third_party/lib/src/isr.cpp\n"
        "EXTRA_INC_M4 = -Ithird_party/lib/include\n",
    )
    db = _make_db(tmp_path)
    _stub_vendor_inputs(tmp_path, db, "M7")
    _stub_vendor_inputs(tmp_path, db, "M4")

    # The library source lands only in M4's object list.
    assert "build/M4/third_party/lib/src/isr.o" in _var(db, "OBJS_M4").split()
    assert "third_party" not in _var(db, "OBJS_M7")

    for core, driver in (("M7", "arm-none-eabi-gcc"), ("M4", "arm-none-eabi-g++")):
        done = subprocess.run(
            ["make", "-n", f"build-{core}"], cwd=tmp_path, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        link = next(
            c for c in done.stdout.splitlines()
            if f"-o build/{core}/stm32h755-{core}.elf" in c
        )
        assert link.startswith(f"{driver} "), (core, link)


def test_readme_documents_extra_inc_and_per_core_main(tmp_path) -> None:
    _render("stm32wl55jc", "cpp", tmp_path)
    readme = (tmp_path / "README.md").read_text()
    assert "EXTRA_INC_<core>" in readme
    assert "EXTRA_CFLAGS_<core>" in readme
    assert "EXTRA_CXXFLAGS_<core>" in readme
    assert "src/<core>/main.cpp" in readme
    assert "src/main-<core>" not in readme
    assert "$(CXX)" in readme

    _render("stm32wl55jc", "c", tmp_path / "c")
    c_readme = (tmp_path / "c/README.md").read_text()
    assert "src/<core>/main.c" in c_readme
    assert "src/main-<core>" not in c_readme

