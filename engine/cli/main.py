"""``mu`` entry point (req-005, groups 1-2; task-003 verb wiring): five thin
verbs over argparse.

``create`` renders a project tree locally from a pack (loader + renderer).
``build`` runs the language toolchain locally (``make``/``cargo``);
``flash``/``debug`` resolve the pack + probe endpoint and drive the default
probe backend; ``dev`` spawns an interactive shell. ``--mode auto`` wraps
the same invocation for a container (engine mounted read-only, project
read-write); ``--mode local`` executes in-process — never re-execs ``mu``.
``--dry-run`` prints the exact command without executing (container argv in
``auto``, local toolchain command in ``local``) and needs no runtime.
Verbs carry no device knowledge.
One-source rule: ``--mcu-config`` XOR individual flags (``--mcu``,
``--device``/``--vid``/``--pid``/``--serial``); mixing exits 2.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from engine.adapters import DebugPort, DefaultImageLookup, FlashPort, get_adapter
from engine.adapters.toolchain import ensure_registered as _ensure_stacks
from engine.core.envelope import CONTAINER_RUNTIME, HOST_GIT
from engine.core.stacks import stack_spec
from engine.cli.shim import (
    MODES,
    ShimRequest,
    build_container_argv,
    build_probe_argv,
    describe_mount_failure,
    format_argv,
    packs_dir,
    parse_mount_failure,
    probe_endpoint,
)
from engine.cli.verdict import render_flash_verdict
from engine.core.loader import FrameError, load_file
from engine.core.model import Device, DeviceView, Endpoint
from engine.templates.renderer import SUPPORTED_LANGS, render
from engine.templates.vendoring import VendorError

__all__ = ["VERBS", "build_parser", "main", "probe_os"]

VERBS = ("create", "dev", "build", "flash", "debug")

# Individual HARDWARE-description flags, XOR with --mcu-config (task-003 was
# green; bug-001 fixed this tuple): probe selectors (device/vid/pid/serial)
# are RUN config and MUST compose with --mcu-config (flash needs both).
INDIVIDUAL_FLAGS = ("mcu",)

# Packs shipped with the repo: single-sourced from the shim (container paths
# mirror this layout, so pack ids resolve identically inside and outside).
PACKS_DIR = packs_dir()


def probe_os() -> str:
    """Host OS key for probe mapping: ``linux`` or ``darwin``."""
    sys_name = platform.system().lower()
    if sys_name.startswith("darwin"):
        return "darwin"
    return "linux"


def _add_common(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--lang", default="c", help="source language (image lookup key)")
    sub.add_argument("--mode", default="auto", choices=MODES, help="exec mode")
    sub.add_argument("--project-dir", default=".", help="project root to mount")
    sub.add_argument(
        "--dry-run",
        action="store_true",
        help="print the exact container argv and exit",
    )
    sub.add_argument("--mcu-config", default=None, help="single-source config file")
    sub.add_argument("--mcu", default=None, help="individual selector (XOR --mcu-config)")


def _add_probe_selectors(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--device", default=None, help="explicit probe device node")
    sub.add_argument("--vid", default=None, help="probe USB vendor id selector")
    sub.add_argument("--pid", default=None, help="probe USB product id selector")
    sub.add_argument("--serial", default=None, help="probe USB serial selector")


def _add_probe_flags(sub: argparse.ArgumentParser) -> None:
    _add_probe_selectors(sub)
    sub.add_argument(
        "--verbose",
        action="store_true",
        help="preserve the complete raw tool log under <project>/.mu/logs/",
    )


def _one_source_violation(args: argparse.Namespace) -> str | None:
    if args.mcu_config is None:
        return None
    mixed = [f"--{name}" for name in INDIVIDUAL_FLAGS if getattr(args, name, None)]
    if mixed:
        return (
            f"--mcu-config cannot be mixed with individual flag(s): "
            f"{', '.join(mixed)} (one source per invocation)"
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mu", description="device-agnostic MCU verbs")
    subs = parser.add_subparsers(dest="verb", required=True, metavar="verb")
    create = subs.add_parser("create", help="scaffold a project tree skeleton")
    create.add_argument("--name", required=True, help="project name")
    create.add_argument("--path", default=".", help="parent dir; project renders to <path>/<name>")
    create.add_argument(
        "--vscode",
        action="store_true",
        help="also generate .vscode/ (tasks, launch, settings, extensions)",
    )
    _add_common(create)
    for verb, help_text in (
        ("dev", "containerized interactive dev env"),
        ("build", "transparent container build"),
        ("flash", "program pieces via the probe port + verdict (default backend)"),
        ("debug", "attach a debug session via the probe port (default backend)"),
    ):
        sub = subs.add_parser(verb, help=help_text)
        _add_common(sub)
        if verb in ("flash", "debug"):
            _add_probe_flags(sub)
            sub.add_argument(
                "--probe",
                default=None,
                metavar="BACKEND",
                help="probe backend: overrides the pack default",
            )
        elif verb == "dev":
            # Probe selectors so the dev container gets the probe's USB node
            # (req-019) — same resolution flash/debug use.
            _add_probe_selectors(sub)
            sub.add_argument(
                "--detach",
                action="store_true",
                help="start an attachable dev container and exit (for an editor to attach to)",
            )
        if verb == "flash":
            sub.add_argument(
                "--files",
                nargs="*",
                default=[],
                metavar="ELF",
                help="firmware image(s) to program, in order",
            )
    return parser


def _available_pack_ids() -> list[str]:
    if not PACKS_DIR.is_dir():
        return []
    return sorted(p.stem for p in PACKS_DIR.glob("*.yaml"))


def _resolve_pack(ref: str) -> Device:
    """Load a pack by file path or by shipped pack id."""
    candidate = Path(ref)
    if candidate.is_file():
        return load_file(candidate)
    by_id = PACKS_DIR / (ref[:-5] if ref.endswith(".yaml") else ref)
    by_id = by_id.with_suffix(".yaml")
    if by_id.is_file():
        return load_file(by_id)
    known = _available_pack_ids()
    hint = f" (known packs: {', '.join(known)})" if known else ""
    raise FileNotFoundError(f"unknown pack {ref!r}; not a file and no shipped pack by that id{hint}")


def _run_create(args: argparse.Namespace) -> int:
    if args.mcu_config is None:
        individual = [f"--{name}" for name in INDIVIDUAL_FLAGS if getattr(args, name, None)]
        if individual:
            print(
                "mu: error: the individual-flags path "
                f"({', '.join(individual)}) is not wired yet (follow-up); "
                "pass a single source via --mcu-config <pack-id-or-file>",
                file=sys.stderr,
            )
        else:
            print("mu: error: create requires --mcu-config <pack-id-or-file>", file=sys.stderr)
        return 2
    if args.lang not in SUPPORTED_LANGS:
        print(f"mu: error: unsupported lang {args.lang!r}; expected one of {SUPPORTED_LANGS}", file=sys.stderr)
        return 2
    try:
        device = _resolve_pack(args.mcu_config)
    except FileNotFoundError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    except (FrameError, ValueError, OSError) as exc:
        print(f"mu: error: invalid pack {args.mcu_config!r}: {exc}", file=sys.stderr)
        return 1
    out = Path(args.path) / args.name
    if args.dry_run:
        print(f"would render {device.id} ({args.lang}) to {out}/")
        print("next: mu build --project-dir " + str(out))
        return 0
    try:
        written = render(device, args.lang, out, vscode=getattr(args, "vscode", False))
    except VendorError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    print(f"created {len(written)} files in {out}/")
    for path in written:
        print(f"  {path}")
    print("next steps:")
    print(f"  cd {out} && mu build --project-dir .")
    return 0


def _project_stack(project_dir: str) -> str | None:
    """Resolved build stack persisted in a rendered tree (AD-11), or ``None``."""
    path = Path(project_dir) / ".mu" / "stack"
    if path.is_file():
        return path.read_text().strip() or None
    return None


def _stack_id_for(args: argparse.Namespace) -> tuple[str, Device | None]:
    """Resolve the build stack for this invocation (AD-11, AD-8).

    A pack declares the stack per source language; a rendered project persists
    its resolved stack, so verbs that load no pack resolve identically. Never
    derived from the language flag.
    """
    if args.mcu_config is not None:
        device = _resolve_pack(args.mcu_config)
        stack_id = device.stack_for(args.lang)
        if stack_id is None:
            declared = [lang for lang, _ in device.stacks]
            raise ValueError(
                f"pack {device.id!r} declares no build stack for language {args.lang!r} "
                f"(declared: {declared or 'none'})"
            )
        return stack_id, device
    stack_id = _project_stack(args.project_dir)
    if stack_id is None:
        raise ValueError(
            f"no build stack for {args.project_dir!r}: not a mu project (no .mu/stack) "
            "and no --mcu-config; run `mu create` first"
        )
    return stack_id, None


def _stack_build_argv(stack_id: str) -> list[str]:
    """The stack's build command (AD-8); toolchain adapters own the spec."""
    _ensure_stacks()
    return list(stack_spec(stack_id).build_argv)


def _run_tool(cmd: list[str], cwd: str) -> int:
    """Run a toolchain command in ``cwd``; missing tool is exit 1, else passthrough."""
    try:
        completed = subprocess.run(cmd, cwd=cwd)
    except FileNotFoundError:
        print(
            f"mu: error: build tool not found: {cmd[0]} "
            f"(run inside the toolchain image or install it)",
            file=sys.stderr,
        )
        return 1
    return completed.returncode


def _run_build_local(args: argparse.Namespace) -> int:
    try:
        stack_id, _device = _stack_id_for(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    cmd = _stack_build_argv(stack_id)
    if args.dry_run:
        print(f"cd {args.project_dir} && {format_argv(cmd)}")
        return 0
    return _run_tool(cmd, args.project_dir)


def _load_pack_or_exit(ref: str) -> Device | None:
    """Load a pack, printing usage errors; None means the caller already reported."""
    try:
        return _resolve_pack(ref)
    except FileNotFoundError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return None
    except (FrameError, ValueError, OSError) as exc:
        print(f"mu: error: invalid pack {ref!r}: {exc}", file=sys.stderr)
        return None


def _prepare_flash(args: argparse.Namespace) -> tuple[Device, Endpoint, FlashPort] | None:
    """Resolve pack + endpoint for flash/debug; None means already reported."""
    if args.mcu_config is None:
        print("mu: error: this verb requires --mcu-config <pack-id-or-file>", file=sys.stderr)
        return None
    device = _load_pack_or_exit(args.mcu_config)
    if device is None:
        return None
    try:
        endpoint = probe_endpoint(
            os_name=probe_os(),
            device=getattr(args, "device", None),
            vid=getattr(args, "vid", None),
            pid=getattr(args, "pid", None),
            serial=getattr(args, "serial", None),
            transport=device.probe_ref.transport,
        )
    except ValueError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return None
    if endpoint is None:
        print(
            "mu: error: no debug probe found; attach a board "
            "(or pass --device/--vid/--pid/--serial)",
            file=sys.stderr,
        )
        return None
    # AD-11: the resolved stack may pin its own flash backend; the pack
    # default is the fallback.
    backend = getattr(args, "probe", None)
    if not backend:
        try:
            _ensure_stacks()
            stack_id, _ = _stack_id_for(args)
            backend = stack_spec(stack_id).flash_backend or device.probe_backend
        except (ValueError, FileNotFoundError):
            backend = device.probe_backend
    try:
        adapter = get_adapter(
            backend,
            stream=True,
            log_path=_verbose_log_path(args) if getattr(args, "verbose", False) else None,
        )
    except ValueError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return None
    return device, endpoint, adapter


def _verbose_log_path(args: argparse.Namespace) -> str:
    """Per-run raw-log path for ``--verbose`` (created on first write)."""
    import time

    stamp = time.strftime("%Y%m%d-%H%M%S")
    logdir = Path(args.project_dir).resolve() / ".mu" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    return str(logdir / f"{args.verb}-{stamp}.log")


def _dev_container_name(project_dir: str) -> str:
    """Stable container name for ``dev --detach`` (one per project)."""
    base = Path(project_dir).resolve().name or "project"
    return "mu-dev-" + re.sub(r"[^A-Za-z0-9_.-]", "-", base)


def _stack_env_setup(stack_id: str) -> str:
    """Shell fragment that enables the stack's toolchain (from StackSpec)."""
    _ensure_stacks()
    return stack_spec(stack_id).env_setup


def _stack_container_user(stack_id: str) -> str:
    """Container user override for the stack (empty = image default)."""
    _ensure_stacks()
    return stack_spec(stack_id).container_user


def _wait_dev_ready(name: str, binary: str, *, timeout_s: float = 30.0) -> bool:
    """Wait until a login shell in the container resolves the stack's build tool.

    ``docker run -d`` returns the moment the container starts, which can be
    before the entrypoint has finished enabling the toolchain — attaching then
    would show a shell without ``idf.py``/``make``/``cargo``.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        probe = subprocess.run(
            [CONTAINER_RUNTIME, "exec", name, "bash", "-lc", f"command -v {binary}"],
            capture_output=True,
        )
        if probe.returncode == 0:
            return True
        time.sleep(0.5)
    return False


def _run_dev_detach(args: argparse.Namespace, stack_id: str, device: Device | None) -> int:
    """Start an attachable dev container (``-d``, kept alive) and report how to attach."""
    if args.mode != "auto":
        print(
            "mu: error: --detach starts a container; --mode local has none",
            file=sys.stderr,
        )
        return 2
    name = _dev_container_name(args.project_dir)
    request = ShimRequest(
        verb="dev",
        lang=args.lang,
        mode=args.mode,
        project_dir=args.project_dir,
        device=getattr(args, "device", None),
        vid=getattr(args, "vid", None),
        pid=getattr(args, "pid", None),
        serial=getattr(args, "serial", None),
        os_name=probe_os(),
        interactive=False,
        mcu_config=args.mcu_config,
        stack=stack_id,
        probe_transport=device.probe_ref.transport if device is not None else "",
        detach=True,
        name=name,
        env_setup=_stack_env_setup(stack_id),
        container_user=_stack_container_user(stack_id),
    )
    try:
        argv = build_container_argv(request, lookup=DefaultImageLookup())
    except ValueError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(format_argv(argv))
        return 0
    if shutil.which(CONTAINER_RUNTIME) is None:
        print(
            f"mu: error: container runtime '{CONTAINER_RUNTIME}' not found; "
            "install it or re-run with --dry-run",
            file=sys.stderr,
        )
        return 1
    image = DefaultImageLookup().image_for(stack_id)
    if subprocess.run(
        [CONTAINER_RUNTIME, "image", "inspect", image], capture_output=True
    ).returncode != 0:
        print(
            f"mu: error: image {image} not present locally; "
            f"run `make images` or `docker pull {image}` first",
            file=sys.stderr,
        )
        return 1
    # One dev container per project: replace any previous one so re-running works.
    subprocess.run([CONTAINER_RUNTIME, "rm", "-f", name], capture_output=True)
    completed = subprocess.run(argv, capture_output=True, text=True)
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or "")
        return completed.returncode
    binary = _stack_build_argv(stack_id)[0]
    if not _wait_dev_ready(name, binary):
        print(
            f"mu: warning: '{name}' is up but a shell did not resolve {binary!r} "
            f"within 30s; attach anyway and check the log: "
            f"{CONTAINER_RUNTIME} logs {name}",
            file=sys.stderr,
        )
    print(f"dev container '{name}' is running and attachable.")
    print("  VS Code: Command Palette -> Dev Containers: Attach to Running Container")
    print(f"           -> {name}  (then File > Open Folder > /project)")
    print(f"  stop it: docker rm -f {name}")
    return 0


def _run_flash_local(args: argparse.Namespace) -> int:
    prepared = _prepare_flash(args)
    if prepared is None:
        return 2
    device, endpoint, adapter = prepared
    if not args.files:
        print("mu: error: flash requires --files <elf...>", file=sys.stderr)
        return 2
    view = DeviceView.of(device)
    if args.dry_run:
        print(format_argv(adapter.render_argv(view, endpoint, args.files)))
        return 0
    try:
        results = adapter.flash(view, endpoint, args.files)
    except FileNotFoundError:
        print("mu: error: probe tool not found (run inside the toolchain image)", file=sys.stderr)
        return 1
    transcript = adapter.last_transcript
    proof = adapter.proof_for(view, results, transcript) if transcript is not None else None
    print(render_flash_verdict(results, proof))
    return 0 if all(r.ok for r in results) else 1


def _run_debug_local(args: argparse.Namespace) -> int:
    prepared = _prepare_flash(args)
    if prepared is None:
        return 2
    device, endpoint, adapter = prepared
    # AD-12: a backend that implements no DebugPort (a programming-only
    # device, no attach) must fail the verb rather than fabricate a handle.
    if not isinstance(adapter, DebugPort):
        print(
            f"mu: error: backend {args.probe or device.probe_backend or 'default'!r} "
            "implements no debug port (AD-12); this device has no attach — "
            "use `mu flash` to program it",
            file=sys.stderr,
        )
        return 2
    view = DeviceView.of(device)
    if args.dry_run:
        print(format_argv(adapter.render_argv(view, endpoint, ())))
        return 0
    handle = adapter.debug(view, endpoint)
    print(f"debug session: {handle.session_id} on {handle.endpoint.address}")
    print("note: live attach stays OPEN (no probe claim); session parameters above are reviewable")
    return 0


def _run_dev_local(args: argparse.Namespace) -> int:
    shell = os.environ.get("SHELL", "/bin/sh")
    if args.dry_run:
        print(shell)
        return 0
    try:
        completed = subprocess.run([shell])
    except FileNotFoundError:
        print(f"mu: error: shell not found: {shell}", file=sys.stderr)
        return 1
    return completed.returncode


def _run_with_tee(argv: list[str]) -> tuple[int, str]:
    """Run ``argv`` with stdout inherited and stderr streamed live + captured.

    Returns ``(exit code, captured stderr)`` so the caller can match daemon
    failures (bug-022) without buffering the build log.
    """
    proc = subprocess.Popen(argv, stderr=subprocess.PIPE, text=True)
    chunks: list[str] = []
    assert proc.stderr is not None
    for line in proc.stderr:
        sys.stderr.write(line)
        chunks.append(line)
    return proc.wait(), "".join(chunks)


def _report_mount_failure(stderr_text: str) -> bool:
    """Print the friendly hint when ``stderr_text`` is a mount failure (bug-022)."""
    bad = parse_mount_failure(stderr_text)
    if bad is None:
        return False
    print(describe_mount_failure(bad), file=sys.stderr)
    return True


def _run_local(args: argparse.Namespace) -> int:
    """Execute the verb in-process (never re-execs ``mu``)."""
    if args.verb == "build":
        return _run_build_local(args)
    if args.verb == "flash":
        return _run_flash_local(args)
    if args.verb == "debug":
        return _run_debug_local(args)
    if args.verb == "dev":
        return _run_dev_local(args)
    raise AssertionError(f"unhandled verb: {args.verb}")


def _mcu_config_outside_project(args: argparse.Namespace) -> str | None:
    """Reject ``--mcu-config`` files the container mount cannot see.

    Pack ids always resolve via the mounted repo; only on-host files outside
    the project mount are unusable in ``auto`` mode (``local`` reads host
    paths directly, so it is exempt).
    """
    ref = args.mcu_config
    if ref is None:
        return None
    candidate = Path(ref)
    if not candidate.is_file():
        return None
    try:
        candidate.resolve().relative_to(Path(args.project_dir).resolve())
    except ValueError:
        return (
            f"--mcu-config file {candidate} is outside --project-dir "
            f"{args.project_dir}; the container mounts only the project — "
            "place the file under the project or pass a pack id"
        )
    return None


def _run_verb(args: argparse.Namespace) -> int:
    violation = _one_source_violation(args)
    if violation is not None:
        build_parser().print_usage(sys.stderr)
        print(f"mu: error: {violation}", file=sys.stderr)
        return 2
    if args.verb == "create":
        return _run_create(args)
    if args.lang not in SUPPORTED_LANGS:
        print(
            f"mu: error: unknown language {args.lang!r}; supported: {sorted(SUPPORTED_LANGS)}",
            file=sys.stderr,
        )
        return 2
    # AD-11: resolve the build stack (pack-declared, or the project's persisted
    # stack) — the language flag never selects the toolchain.
    if args.mode != "local":
        outside = _mcu_config_outside_project(args)
        if outside is not None:
            print(f"mu: error: {outside}", file=sys.stderr)
            return 2
    try:
        stack_id, device = _stack_id_for(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    if args.verb == "dev" and getattr(args, "detach", False):
        return _run_dev_detach(args, stack_id, device)
    if args.mode == "local":
        return _run_local(args)
    extra: list[str] = []
    if args.verb == "flash" and getattr(args, "files", None):
        extra = ["--files", *args.files]
    if args.verb in ("flash", "debug") and getattr(args, "verbose", False):
        # Forward --verbose so the in-container run writes <project>/.mu/logs/
        # (bug-007: auto mode silently ignored it).
        extra.append("--verbose")
    request = ShimRequest(
        verb=args.verb,
        lang=args.lang,
        mode=args.mode,
        project_dir=args.project_dir,
        extra=tuple(extra),
        device=getattr(args, "device", None),
        vid=getattr(args, "vid", None),
        pid=getattr(args, "pid", None),
        serial=getattr(args, "serial", None),
        os_name=probe_os(),
        interactive=(args.verb == "dev"),
        mcu_config=args.mcu_config,
        stack=stack_id,
        probe_transport=device.probe_ref.transport if device is not None else "",
        container_user=_stack_container_user(stack_id),
    )
    try:
        argv = build_container_argv(request, lookup=DefaultImageLookup())
    except ValueError as exc:
        print(f"mu: error: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(format_argv(argv))
        return 0
    if args.mode != "local" and shutil.which(CONTAINER_RUNTIME) is None:
        print(
            "mu: error: container runtime 'docker' not found; "
            "install it or re-run with --dry-run to review the command",
            file=sys.stderr,
        )
        return 1
    image = DefaultImageLookup().image_for(stack_id)
    inspected = subprocess.run(
        [CONTAINER_RUNTIME, "image", "inspect", image],
        capture_output=True,
    )
    if inspected.returncode != 0:
        print(
            f"mu: error: image {image} not present locally; "
            f"run `make images` or `docker pull {image}` first",
            file=sys.stderr,
        )
        return 1
    # Mount preflight (bug-022): one probe run with the same mounts fails fast
    # with a friendly hint instead of the raw daemon error from the real run.
    probe = build_probe_argv(request, lookup=DefaultImageLookup())
    probed = subprocess.run(probe, capture_output=True, text=True)
    if probed.returncode != 0:
        if not _report_mount_failure(probed.stderr or ""):
            sys.stderr.write(probed.stderr or "")
        return 1
    try:
        code, err_text = _run_with_tee(argv)
    except FileNotFoundError:
        print(f"mu: error: executable not found: {argv[0]}", file=sys.stderr)
        return 1
    if code != 0:
        # Fallback for races the probe misses (unshared between probe and run).
        _report_mount_failure(err_text)
    return code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _run_verb(args)


if __name__ == "__main__":
    raise SystemExit(main())
