"""Renderer unit tests (req-008): API shape, per-core contexts, model-only facets."""

from __future__ import annotations

import pytest

from engine.core.loader import load_file
from engine.core.model import Core, Device, DeviceFacets, Endpoint, MemoryRegion, OpenocdConfig
from engine.templates.renderer import SUPPORTED_LANGS, core_context, render
from engine.templates.renderer import fetch_svds as _real_fetch_svds

from .test_cells import PACK_IDS, PACKS_DIR


@pytest.fixture(autouse=True)
def _stub_vendoring(monkeypatch) -> None:
    """req-011/017: render() vendors C/C++ via git and fetches SVDs; unit
    renders stub both (tmp dirs are non-repos, no network)."""
    monkeypatch.setattr("engine.templates.renderer.vendor", lambda _pack_id, _family, _out: [])
    monkeypatch.setattr(
        "engine.templates.renderer.fetch_svds", lambda _device, _out, **k: []
    )


def test_renderer_bad_lang(tmp_path) -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    with pytest.raises(ValueError, match="unsupported lang"):
        render(device, "zig", tmp_path)


def test_renderer_returns_sorted_written_list(tmp_path) -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    written = render(device, "c", tmp_path)
    assert written == sorted(written)
    assert all(p.is_file() for p in written)


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_renderer_per_core_contexts_cover_every_core(pack_id: str) -> None:
    device = load_file(PACKS_DIR / f"{pack_id}.yaml")
    assert {c.name for c in device.cores} <= {name for name, _ in device.facets.linker}
    for core in device.cores:
        ctx = core_context(device, core, "c")
        assert ctx["arch"] == core.arch
        assert ctx["cpu_flags"].startswith("-mcpu=") and "-mthumb" in ctx["cpu_flags"]
        assert ctx["linker_script"] == device.facets.linker_for(core.name, device.id)


def test_renderer_dual_bank_cores_link_own_flash(tmp_path) -> None:
    """H755 M7 -> FLASH_M7, M4 -> FLASH_M4 (per-core region, not first-bank)."""
    device = load_file(PACKS_DIR / "stm32h755.yaml")
    render(device, "c", tmp_path)
    m7 = (tmp_path / f"linker/{device.facets.linker_for('M7', device.id)}").read_text()
    m4 = (tmp_path / f"linker/{device.facets.linker_for('M4', device.id)}").read_text()
    assert ">FLASH_M7" in m7 and ">FLASH_M4" not in m7
    assert ">FLASH_M4" in m4 and ">FLASH_M7" not in m4
    # bug-014: each core also gets its own RAM region and stack top.
    assert ">RAM_M7" in m7 and ">RAM_M4" not in m7
    assert ">RAM_M4" in m4 and ">RAM_M7" not in m4
    assert "_estack = ORIGIN(RAM_M7)" in m7
    assert "_estack = ORIGIN(RAM_M4)" in m4


def test_renderer_dual_core_ram_does_not_overlap(tmp_path) -> None:
    """bug-014: two cores sharing one RAM region (same _estack) collided at
    boot and the M7 hard-faulted. The regions must be disjoint."""
    import re

    device = load_file(PACKS_DIR / "stm32h755.yaml")
    render(device, "c", tmp_path)

    def ram_span(text: str) -> tuple[int, int]:
        region = re.search(r"_estack = ORIGIN\((\w+)\)", text).group(1)
        match = re.search(
            rf"{region} \(rwx\) : ORIGIN = (0x[0-9A-Fa-f]+), LENGTH = (\d+)", text
        )
        return int(match.group(1), 16), int(match.group(2))

    m7 = (tmp_path / f"linker/{device.facets.linker_for('M7', device.id)}").read_text()
    m4 = (tmp_path / f"linker/{device.facets.linker_for('M4', device.id)}").read_text()
    (o7, l7), (o4, l4) = ram_span(m7), ram_span(m4)
    assert (o7, l7) != (o4, l4), "cores share the same RAM region"
    assert o7 + l7 <= o4 or o4 + l4 <= o7, "core RAM regions overlap"


def test_renderer_supported_langs() -> None:
    assert SUPPORTED_LANGS == ("c", "cpp", "rust")


def test_loader_attaches_facets_to_model() -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    assert isinstance(device.facets, DeviceFacets)
    assert (device.facets.fpu_mode, device.facets.fpu_variant) == ("hard", "fpv4-sp-d16")
    assert device.facets.linker_for("M4", device.id) == "STM32F411RETx_FLASH.ld"
    assert device.facets.config_header == "stm32_config.h"
    assert device.facets.config_library == "stm32hal"
    assert device.openocd is not None and device.openocd.board == "st_nucleo_f4.cfg"
    wl = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    assert wl.openocd is not None and wl.openocd.board is None
    assert wl.openocd.target == "stm32wlx.cfg"
    assert (wl.facets.fpu_mode, wl.facets.fpu_variant) == ("soft", "none")


def _synthetic_device() -> Device:
    """Hand-built model (no pack YAML): proves the renderer is model-only."""
    return Device(
        id="synthetic",
        version="9.9.9",
        source_hash="sha256:synthetic",
        cores=[Core(name="M4", arch="thumbv7em-none-eabihf")],
        memory=[
            MemoryRegion(name="flash", origin_hex="0x08000000", size=262144),
            MemoryRegion(name="ram", origin_hex="0x20000000", size=65536),
        ],
        probe_ref=Endpoint(transport="stlink", address="openocd:stlink"),
        proof_rung="readback",
        openocd=OpenocdConfig(interface="stlink.cfg", target="board.cfg", board="synth.cfg"),
        stacks=(("c", "make-cmsis"), ("cpp", "make-cmsis"), ("rust", "cargo-cortex")),
        facets=DeviceFacets(
            fpu_mode="hard",
            fpu_variant="fpv4-sp-d16",
            linker=(("M4", "SYNTH_FLASH.ld"),),
            config_library="synthlib",
            config_header="synth_config.h",
            config_defaults_source="pack/synth.h",
            startup=(("M4", "startup_synth.s"),),
            system=(("M4", "system_synth.c"),),
            # AD-14: the model carries the config-header fact as a block.
            blocks=((
                "config_headers",
                {"library": "synthlib", "header": "synth_config.h",
                 "defaults_source": "pack/synth.h"},
            ),),
        ),
    )


@pytest.mark.parametrize("lang", SUPPORTED_LANGS)
def test_renderer_consumes_model_only(lang: str, tmp_path) -> None:
    written = render(_synthetic_device(), lang, tmp_path)
    assert written, "expected files for synthetic model"
    if lang in ("c", "cpp"):
        text = (tmp_path / "Makefile").read_text()
        assert "-mfpu=fpv4-sp-d16 -mfloat-abi=hard" in text
        assert "linker/SYNTH_FLASH.ld" in text
        assert "board/synth.cfg" in (tmp_path / "probe" / "openocd.cfg").read_text()
        assert (tmp_path / "config/synth_config.h").is_file()
    else:
        assert "0x08000000" in (tmp_path / "memory.x").read_text()
        assert 'name = "synthetic"' in (tmp_path / "Cargo.toml").read_text()


def test_render_persists_resolved_stack(tmp_path) -> None:
    """AD-11: the rendered tree records its build stack for pack-less verbs."""
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    render(device, "rust", tmp_path)
    assert (tmp_path / ".mu" / "stack").read_text().strip() == "cargo-cortex"


def test_render_uses_pack_declared_stack_not_language(tmp_path) -> None:
    """AD-11: a pack may map language 'c' to a non-C stack; the stack decides."""
    import dataclasses

    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    dev = dataclasses.replace(device, stacks=(("c", "cargo-cortex"),))
    written = render(dev, "c", tmp_path)
    names = [p.relative_to(tmp_path).as_posix() for p in written]
    assert "Cargo.toml" in names and "memory.x" in names
    assert "Makefile" not in names


def test_render_errors_when_pack_declares_no_stack_for_language(tmp_path) -> None:
    import dataclasses

    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    dev = dataclasses.replace(device, stacks=(("rust", "cargo-cortex"),))
    with pytest.raises(ValueError, match="no build stack for language 'c'"):
        render(dev, "c", tmp_path)


def test_render_emits_no_openocd_or_cmsis_artifacts_without_the_facts(tmp_path) -> None:
    """AD-14: a model without the STM32 facts gets no OpenOCD/CMSIS artifacts."""
    device = Device(
        id="bare-1",
        version="1.0.0",
        source_hash="sha256:bare",
        cores=[Core(name="C0", arch="generic")],
        memory=[
            MemoryRegion(name="flash", origin_hex="0x0", size=4096),
            MemoryRegion(name="ram", origin_hex="0x20000000", size=1024),
        ],
        probe_ref=Endpoint(transport="t", address="a"),
        proof_rung="rung",
        stacks=(("rust", "cargo-cortex"),),
        family="barefam",
        # No openocd block, no config_headers block, no vendor files.
        facets=DeviceFacets(),
    )
    written = render(device, "rust", tmp_path)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert "Cargo.toml" in names, "expected the project skeleton"
    assert not {n for n in names if n.startswith("probe/")}
    assert not {n for n in names if n.startswith("config/")}
    assert not (tmp_path / "vendor").exists()


def test_render_emits_no_config_artifacts_without_the_config_block(tmp_path, monkeypatch) -> None:
    """AD-14: the config header is emitted only when the pack declares it."""
    import dataclasses

    monkeypatch.setattr("engine.templates.renderer.vendor", lambda *_a: [])
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    dev = dataclasses.replace(device, facets=dataclasses.replace(device.facets, blocks=()))
    written = render(dev, "rust", tmp_path)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert not {n for n in names if n.startswith("config/")}
    assert {n for n in names if n.startswith("probe/")} == {"probe/openocd.cfg", "probe/probe-serial.cfg"}


def test_renderer_writes_project_readme(tmp_path) -> None:
    """ops-021: every project documents its own build/flash/debug flow."""
    device = load_file(PACKS_DIR / "stm32h755.yaml")
    render(device, "c", tmp_path)
    text = (tmp_path / "README.md").read_text()
    assert text.startswith("# stm32h755")
    assert "`M7`" in text and "`M4`" in text          # cores from the pack
    assert "make flash-M4" in text                    # per-core targets
    assert "Debug M7+M4 (OpenOCD)" in text            # compound dual-core config
    assert "MU_PROBE_SERIAL" in text                  # probe-by-serial


def test_renderer_readme_rust_has_no_make_targets(tmp_path) -> None:
    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    render(device, "rust", tmp_path)
    text = (tmp_path / "README.md").read_text()
    assert "mu build --project-dir ." in text
    assert "make flash" not in text                   # cargo path, not make
    # req-029: the single-core Rust example now blinks the pack LED, so the
    # README may (and must) say so.
    assert "on-board LED" in text


def test_render_vscode_generates_valid_configs(tmp_path) -> None:
    import json

    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    render(device, "c", tmp_path, vscode=True)
    cfg = json.loads((tmp_path / ".vscode/launch.json").read_text())["configurations"][0]
    assert cfg["type"] == "cortex-debug"
    assert cfg["executable"].endswith("build/M4/stm32f411re-M4.elf")
    assert cfg["configFiles"] == [
        "interface/stlink.cfg",
        "probe/probe-serial.cfg",
        "board/st_nucleo_f4.cfg",
        "probe/resume-on-detach.cfg",
    ]
    # bug-018: probe pinning by serial (containers pass the whole USB bus).
    serial_cfg = (tmp_path / "probe/probe-serial.cfg").read_text()
    assert "MU_PROBE_SERIAL" in serial_cfg and "adapter serial" in serial_cfg
    # bug-016: the F411 uses HLA (stlink.cfg -> hla_target), which has no
    # `cortex_m` command group, so the workaround must NOT be emitted (it would
    # fail the launch with 'invalid command name "cortex_m"').
    assert "postLaunchCommands" not in cfg
    # bug-013: single-core configs need no processor targeting.
    assert "numberOfProcessors" not in cfg and "targetProcessor" not in cfg
    assert (tmp_path / "probe/resume-on-detach.cfg").is_file()
    resume = (tmp_path / "probe/resume-on-detach.cfg").read_text()
    assert "gdb-detach" in resume and "info exists _TARGETNAME" in resume
    assert cfg["gdbPath"].startswith("/opt/arm-gnu-toolchain")
    assert cfg["svdFile"].endswith("probe/STM32F411.svd")
    ext = json.loads((tmp_path / ".vscode/extensions.json").read_text())
    assert "marus25.cortex-debug" in ext["recommendations"]
    tasks = json.loads((tmp_path / ".vscode/tasks.json").read_text())
    assert {"Build", "Clean", "Flash"} <= {t["label"] for t in tasks["tasks"]}


def test_render_vscode_per_core_dual(tmp_path) -> None:
    import json

    device = load_file(PACKS_DIR / "stm32h755.yaml")
    render(device, "c", tmp_path, vscode=True)
    launch = json.loads((tmp_path / ".vscode/launch.json").read_text())
    cfgs = launch["configurations"]
    assert [c["name"] for c in cfgs] == [
        "Debug M7 (OpenOCD)",
        "Debug M4 (OpenOCD)",
        "Debug M7+M4 (OpenOCD)",
    ]
    resume = (tmp_path / "probe/resume-on-detach.cfg").read_text()
    assert "stm32h7x.cpu0 configure -event gdb-detach" in resume
    assert "stm32h7x.cpu1 configure -event gdb-detach" in resume
    # bug-011: every per-core config gets the single-step workaround.
    assert all(
        c["postLaunchCommands"] == ["monitor cortex_m maskisr steponly"]
        for c in cfgs
    )
    # bug-013: each per-core config targets its own OpenOCD processor (cpu0/cpu1)
    m7, m4 = cfgs[0], cfgs[1]
    assert (m7["numberOfProcessors"], m7["targetProcessor"]) == (2, 0)  # M7 -> cpu0
    assert (m4["numberOfProcessors"], m4["targetProcessor"]) == (2, 1)  # M4 -> cpu1
    # ...and a compound config chains the second core off the boot core.
    compound = cfgs[2]
    assert compound["targetProcessor"] == 0
    assert compound["executable"].endswith("build/M7/stm32h755-M7.elf")
    chained = compound["chainedConfigurations"]
    assert chained["detached"] is False
    assert chained["launches"] == [{"name": "Debug M4 (OpenOCD)"}]


def test_vscode_maskisr_gated_to_cortex_m_and_dap() -> None:
    """bug-012/016: the `cortex_m maskisr` workaround is emitted only for
    Cortex-M cores on a DAP target — HLA (stlink.cfg -> hla_target) has no
    `cortex_m` command group and would abort the launch."""
    import json
    from dataclasses import replace

    from engine.templates.renderer import _vscode_files

    def cmds(device) -> list[dict]:
        return json.loads(_vscode_files(device)[".vscode/launch.json"])["configurations"]

    dap = OpenocdConfig(interface="stlink-dap.cfg", target="board.cfg", board="synth.cfg")
    hla = OpenocdConfig(interface="stlink.cfg", target="board.cfg", board="synth.cfg")
    workaround = ["monitor cortex_m maskisr steponly"]

    # Cortex-M + DAP -> present
    assert all(
        c["postLaunchCommands"] == workaround
        for c in cmds(replace(_synthetic_device(), openocd=dap))
    )
    # Cortex-M + HLA -> absent
    assert all(
        "postLaunchCommands" not in c
        for c in cmds(replace(_synthetic_device(), openocd=hla))
    )
    # non-Cortex-M (DAP) -> absent
    riscv = replace(
        _synthetic_device(),
        cores=[Core(name="M4", arch="riscv32imac-unknown-none-elf")],
        openocd=dap,
    )
    assert all("postLaunchCommands" not in c for c in cmds(riscv))


def test_render_vscode_off_by_default(tmp_path) -> None:
    render(load_file(PACKS_DIR / "stm32f411re.yaml"), "c", tmp_path)
    assert not (tmp_path / ".vscode").exists()


def test_fetch_svds_uses_pinned_url(tmp_path) -> None:
    from engine.templates import renderer

    device = load_file(PACKS_DIR / "stm32f411re.yaml")
    seen: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<device/>"

    def opener(url):
        seen["url"] = url
        return _Resp()

    paths = _real_fetch_svds(device, tmp_path, opener=opener)
    assert paths == [tmp_path / "probe" / "STM32F411.svd"]
    assert "modm-io/cmsis-svd-stm32" in seen["url"] and renderer.SVD_SHA in seen["url"]
    assert (tmp_path / "probe" / "STM32F411.svd").read_bytes() == b"<device/>"


def test_cpu2_boot_cfg_is_not_emitted(tmp_path) -> None:
    """bug-031: the generated project must not carry probe/cpu2-boot.cfg.

    It hooked the primary's examine-end and set the sibling boot bit, so
    PWR_CR4 read 0x00008000 in *every* session — even when the M4 never booted.
    That masked bug-027 and made the sibling look released when it was not.
    The primary's mu_release_sibling constructor alone releases the sibling,
    so nothing in the project needs to write the bit.
    """
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    written = render(device, "c", tmp_path, vscode=True)
    assert not (tmp_path / "probe" / "cpu2-boot.cfg").exists()
    assert "probe/cpu2-boot.cfg" not in {p.name for p in written}
    # And nothing may still reference it (it would abort a launch if missing).
    launch = (tmp_path / ".vscode" / "launch.json").read_text()
    assert "cpu2-boot.cfg" not in launch


def test_cpu2_boot_cfg_write_absent_from_every_generated_tool_file(tmp_path) -> None:
    """No generated *tool* file may write the sibling boot register. The
    firmware itself must: the primary's mu_release_sibling constructor is the
    only thing that releases the sibling (bug-031), so src/ is excluded here
    but asserted to still contain the release."""
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    render(device, "c", tmp_path, vscode=True)
    hits = [
        p.relative_to(tmp_path).as_posix()
        for p in tmp_path.rglob("*")
        if p.is_file()
        and p.suffix != ".c"
        and "0x5800040C" in p.read_text()
    ]
    assert hits == []
    assert "0x5800040C" in (tmp_path / "src" / "M4" / "main.c").read_text()


def test_sibling_debug_target_attaches_without_reset(tmp_path) -> None:
    """bug-030: a released-sibling pack must ship a generated way to attach the
    sibling after `make flash` — dual-core sourced BEFORE the target, and no
    reset anywhere (a system reset cannot halt a released sibling, bug-024)."""
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    render(device, "c", tmp_path)
    makefile = (tmp_path / "Makefile").read_text()

    assert "debug-m0plus:" in makefile
    assert "probe/dual-core.cfg -f target/stm32wlx.cfg" in makefile
    assert (
        '-c "init" -c "stm32wlx.cpu1 arp_examine" -c "targets stm32wlx.cpu1" '
        '-c "poll" -c "halt" -c "reg pc" -c "resume" -c "exit"' in makefile
    ), "dual-core before the target, then attach the sibling without reset"
    # The attach recipe must not reset or re-run the target.
    recipe = makefile.split("debug-m0plus:", 1)[1]
    assert "reset" not in recipe
    # It must leave the board as it found it (bug-030): halt, report, resume.
    assert "-c \"resume\" -c \"exit\"" in recipe
    phony = next(ln for ln in makefile.splitlines() if ln.startswith(".PHONY"))
    assert "debug-m0plus" in phony


def test_sibling_debug_target_only_for_released_sibling_dual_core_packs(tmp_path) -> None:
    """Gated on the facts: a pack without cpu2_boot (H755) gets no target, and
    a cpu2_boot pack without a target-direct dual_core openocd block gets none
    either (probe/dual-core.cfg would not exist)."""
    for pack_id in ("stm32f411re", "stm32h755"):
        device = load_file(PACKS_DIR / f"{pack_id}.yaml")
        out = tmp_path / pack_id
        render(device, "c", out)
        assert "debug-" not in (out / "Makefile").read_text()
        assert "Attaching the sibling core" not in (out / "README.md").read_text()

    from dataclasses import replace

    from engine.templates.renderer import _sibling_attach

    wl = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    assert _sibling_attach(wl) == ("m0plus", "M0+", "stm32wlx.cpu1")
    no_cpu2 = replace(wl, facets=replace(wl.facets, cpu2_boot=()))
    assert _sibling_attach(no_cpu2) is None
    no_targets = replace(wl, openocd=replace(wl.openocd, targets=()))
    assert _sibling_attach(no_targets) is None
    board = replace(wl, openocd=replace(wl.openocd, board="board/stm32wl55jc_nucleo.cfg"))
    assert _sibling_attach(board) is None
    single = replace(wl, cores=(wl.cores[0],))
    assert _sibling_attach(single) is None


def test_readme_documents_the_sibling_attach_path(tmp_path) -> None:
    """bug-030: the README is the project's own guide; the attach recipe must
    be in it, with the dual-core-before-target order and the no-reset rule."""
    device = load_file(PACKS_DIR / "stm32wl55jc.yaml")
    render(device, "c", tmp_path)
    readme = (tmp_path / "README.md").read_text()

    assert "## Attaching the sibling core (`M0+`)" in readme
    assert "make debug-m0plus" in readme
    assert (
        "-f probe/dual-core.cfg -f target/stm32wlx.cfg" in readme
    ), "dual-core must be sourced BEFORE the target config"
    assert '-c "stm32wlx.cpu1 arp_examine" -c "targets stm32wlx.cpu1" -c "poll"' in readme
    assert "Do **not** add `reset run`" in readme
    assert "Attach M0+ | `make debug-m0plus`" in readme
