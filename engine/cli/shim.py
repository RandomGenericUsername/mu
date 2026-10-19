"""Shim helpers (req-005, groups 1-2; task-003 container fix): language ->
image, container argv, per-OS probe mapping.

``build_container_argv`` is the single place that turns a verb invocation
into the exact container command. ``--dry-run`` prints it without touching
the container runtime, so it works with no runtime installed.

Container contract (task-003, narrowed task-004): images ship toolchains only — no ``mu``,
no engine. So the container side runs ``python3 -m engine`` with exactly two
read-only mounts — the ``engine`` package and ``packs/`` — plus the project
read-write at ``/project`` (working dir). Container paths mirror the checkout
layout (``/opt/mu/{engine,packs}``) so ``__file__``-derived resolution
works unchanged. The project mount uses an absolute host path (relative paths
are invalid for the runtime).

Probe binding (shim only): selectors resolve to a ``ProbeBinding`` — a backend
selector plus the host device nodes to forward. Linux passes each host device as
``--device <node>:<node>`` (the USB node for a USB probe); macOS (Docker Desktop)
cannot forward USB nodes, so none are emitted there — run with ``--mode local``
on macOS. Explicit ``--device`` always wins over VID/PID/serial selectors.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, replace
from pathlib import Path

import engine
from engine.adapters import DefaultImageLookup, ImageLookup
from engine.core.envelope import (
    CONTAINER_RUNTIME,
    SYSFS_USB,
    USB_BUS_ROOT,
    USB_CGROUP_RULE,
)
from engine.core.model import Endpoint

__all__ = [
    "ProbeBinding",
    "ShimRequest",
    "build_container_argv",
    "build_probe_argv",
    "describe_mount_failure",
    "engine_root",
    "format_argv",
    "interactive_args",
    "parse_mount_failure",
    "probe_endpoint",
    "repo_root",
    "resolve_probe_binding",
]

MODES = ("auto", "local")

#: Container path of the read-only repo mount (engine + packs resolve under it).
CONTAINER_REPO = "/opt/mu"

#: Container path of the read-write project mount (also the working dir).
CONTAINER_PROJECT = "/project"

#: Default sysfs root for USB device enumeration (overridable in tests).
_SYSFS_USB = Path(SYSFS_USB)

from engine.core.probe_ids import known_probe_vids

#: USB vendor ids treated as probes come from the device families (AD-14),
#: not a hardcoded list here: an unknown id is never silently claimed.
_PROBE_VIDS = known_probe_vids


@dataclass(frozen=True)
class ShimRequest:
    verb: str
    lang: str = "c"
    mode: str = "auto"
    project_dir: str = "."
    extra: tuple[str, ...] = ()
    device: str | None = None
    vid: str | None = None
    pid: str | None = None
    serial: str | None = None
    os_name: str = "linux"
    interactive: bool = False
    mcu_config: str | None = None
    #: Resolved build stack (AD-11) — the image key; never the language flag.
    stack: str = ""
    #: The pack's declared probe transport (AD-9): ``uart-serial`` needs its tty
    #: forwarded; everything else keeps the USB-bus behaviour.
    probe_transport: str = ""
    #: ``dev`` only: start a **detached**, long-running container (``-d --name``)
    #: so an editor can attach to it, instead of an interactive shell.
    detach: bool = False
    #: Container name used when ``detach`` is set.
    name: str = ""
    #: Shell fragment enabling the toolchain in shells we start (from the stack).
    env_setup: str = ""
    #: ``docker run --user`` value (empty = image default). Some toolchain
    #: images need root to open a host-owned serial tty.
    container_user: str = ""


def engine_root() -> Path:
    """Directory containing the ``engine`` package (source checkout)."""
    return Path(engine.__file__).resolve().parent


def repo_root() -> Path:
    """Checkout root: parent of the ``engine`` package directory."""
    return engine_root().parent


def packs_dir() -> Path:
    """Shipped packs directory (single source; ``main.PACKS_DIR`` aliases this)."""
    return repo_root() / "packs"


@dataclass(frozen=True)
class ProbeBinding:
    """Resolved probe: backend selector + host device nodes for the container.

    ``selector`` is what a backend uses to pick the probe (USB serial or
    ``VID:PID``); ``host_devices`` are the host paths the container must be
    given (the USB device node) so a USB probe is reachable through libusb.
    ``serial`` is the USB serial when known, forwarded to the container as
    ``MU_PROBE_SERIAL`` so the backend can pin the probe by serial (bug-018)
    even when the whole USB bus is passed through.
    """

    selector: str
    host_devices: tuple[str, ...] = ()
    serial: str | None = None


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _usb_device_node(entry: Path) -> str | None:
    """``/dev/bus/usb/<bus>/<dev>`` for a sysfs USB device dir, if resolvable."""
    bus, dev = _read_text(entry / "busnum"), _read_text(entry / "devnum")
    if bus.isdigit() and dev.isdigit():
        return f"{USB_BUS_ROOT}/{int(bus):03d}/{int(dev):03d}"
    return None


def _tty_for_usb(entry: Path) -> str | None:
    """``/dev/ttyUSB0`` when a USB device's interface bound a serial tty.

    A USB-UART bridge is reached differently from a libusb probe: the kernel
    creates a **tty** node (major 188) for it, and the container's private
    ``/dev`` does not have that node — so it must be forwarded, unlike a
    libusb device (major 189) reached through the USB bus. The tty's name is
    whatever sysfs exposes under the interface's ``tty`` class dir.
    """
    for interface in sorted(entry.parent.glob(f"{entry.name}:*")):
        for tty_class in sorted(interface.glob("tty*")):
            tty_dir = tty_class / "tty"
            if not tty_dir.is_dir():
                continue
            for name in sorted(tty_dir.iterdir()):
                return f"/dev/{name.name}"
    return None


def _binding_from_entry(
    entry: Path,
    *,
    is_mac: bool,
    transport: str,
    vid: str,
    pid: str,
    serial: str | None,
) -> ProbeBinding:
    """Binding for a matched USB device, per transport (AD-9).

    A ``uart-serial`` device is reached through its tty (forwarded with
    ``--device``); every other probe keeps the USB-node/bus behaviour.
    """
    if is_mac:
        return ProbeBinding(selector=serial or f"{vid}:{pid}", host_devices=(), serial=serial or None)
    if transport == "uart-serial":
        tty = _tty_for_usb(entry)
        if tty is not None:
            # The tty is the backend's port *and* the node the container needs.
            return ProbeBinding(selector=tty, host_devices=(tty,), serial=serial or None)
    node = _usb_device_node(entry)
    return ProbeBinding(
        selector=serial or f"{vid}:{pid}",
        host_devices=(node,) if node else (),
        serial=serial or None,
    )


def _serial_for_usb_node(sysfs_root: Path, node: str) -> str | None:
    """USB serial for a ``/dev/bus/usb/<bus>/<dev>`` node (bug-018).

    Lets an explicit ``--device`` node still be pinned by serial inside the
    container (whose whole USB bus is passed through).
    """
    if not sysfs_root.is_dir():
        return None
    for entry in sorted(sysfs_root.iterdir()):
        if _usb_device_node(entry) == node:
            return _read_text(entry / "serial") or None
    return None


def _match_usb(sysfs_root: Path, vid: str | None, pid: str | None, serial: str | None):
    """First sysfs USB device matching the selectors: ``(entry, vid, pid, serial)`` or ``None``."""
    if not sysfs_root.is_dir():
        return None
    for entry in sorted(sysfs_root.iterdir()):
        if not (entry / "idVendor").is_file():
            continue  # interfaces (e.g. "3-9:1.0") carry no idVendor
        v = _read_text(entry / "idVendor").lower()
        p = _read_text(entry / "idProduct").lower()
        s = _read_text(entry / "serial")
        if vid and v != vid.lower():
            continue
        if pid and p != pid.lower():
            continue
        if serial and s != serial:
            continue
        return entry, v, p, s
    return None


def _autodetect(
    *, is_mac: bool, sysfs_root: Path | str | None, transport: str = ""
) -> ProbeBinding | None:
    """Binding for the single attached probe, or ``None`` when none is attached.

    Raises when more than one probe is attached (ambiguous — the caller must
    pass a selector).
    """
    root = Path(sysfs_root) if sysfs_root else _SYSFS_USB
    found = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if (entry / "idVendor").is_file() and _read_text(entry / "idVendor").lower() in _PROBE_VIDS():
                found.append(entry)
    if not found:
        return None
    if len(found) > 1:
        desc = ", ".join(
            f"{_read_text(e / 'idVendor')}:{_read_text(e / 'idProduct')}"
            f"({_read_text(e / 'serial') or 'no serial'})"
            for e in found
        )
        raise ValueError(
            f"{len(found)} probes attached ({desc}); pass --serial or --vid/--pid to select one"
        )
    entry = found[0]
    v = _read_text(entry / "idVendor").lower()
    p = _read_text(entry / "idProduct").lower()
    s = _read_text(entry / "serial")
    return _binding_from_entry(
        entry, is_mac=is_mac, transport=transport, vid=v, pid=p, serial=s or None
    )


def resolve_probe_binding(
    *,
    os_name: str,
    device: str | None = None,
    vid: str | None = None,
    pid: str | None = None,
    serial: str | None = None,
    sysfs_root: Path | str | None = None,
    transport: str = "",
) -> ProbeBinding | None:
    """Resolve a probe selector to a binding (shim only).

    Explicit ``device`` wins and is used verbatim as both the selector and the
    host device. VID/PID/serial selectors enumerate sysfs to find the USB device
    and derive its ``/dev/bus/usb/<bus>/<dev>`` node; the backend selector is
    the device serial when present, else ``VID:PID``. With **no selector**, a
    single attached probe is auto-detected (``None`` when none is attached; a
    ``ValueError`` when several are). macOS (Docker Desktop) cannot forward USB
    nodes, so ``host_devices`` is empty there (use ``--mode local``).
    """
    is_mac = os_name.lower().startswith(("darwin", "mac"))
    root = Path(sysfs_root) if sysfs_root else _SYSFS_USB
    if device:
        # Explicit node: still resolve its serial when it is a USB node, so the
        # container can pin the probe with `adapter serial` (bug-018).
        return ProbeBinding(
            selector=device,
            host_devices=() if is_mac else (device,),
            serial=None if is_mac else _serial_for_usb_node(root, device),
        )
    if not (vid or pid or serial):
        return _autodetect(is_mac=is_mac, sysfs_root=sysfs_root, transport=transport)
    if is_mac and not serial:
        raise ValueError(
            "macOS probe limit: automatic VID/PID mapping unsupported; "
            "pass --device /dev/(cu|tty).usb* explicitly or use --mode local"
        )
    match = _match_usb(root, vid, pid, serial)
    if match is None:
        # No sysfs match (unplugged/unknown): keep a usable selector so the
        # backend single-probe default still applies; nothing to forward.
        selector = serial or (f"{vid}:{pid}" if vid and pid else (vid or pid or "probe"))
        return ProbeBinding(selector=selector, host_devices=(), serial=serial or None)
    entry, v, p, s = match
    return _binding_from_entry(
        entry, is_mac=is_mac, transport=transport, vid=v, pid=p, serial=s or None
    )


def probe_endpoint(
    *,
    os_name: str,
    device: str | None = None,
    vid: str | None = None,
    pid: str | None = None,
    serial: str | None = None,
    sysfs_root: Path | str | None = None,
    transport: str = "",
) -> Endpoint | None:
    """Prepare the endpoint struct handed to core/adapters (shim only).

    ``address`` carries the backend selector (serial / ``VID:PID`` / explicit
    device), never a synthesized serial path for a USB probe.
    """
    binding = resolve_probe_binding(
        os_name=os_name,
        device=device,
        vid=vid,
        pid=pid,
        serial=serial,
        sysfs_root=sysfs_root,
        transport=transport,
    )
    if binding is None:
        return None
    return Endpoint(transport="probe", address=binding.selector)


def _container_prefix(
    request: ShimRequest, *, lookup: ImageLookup | None = None
) -> tuple[list[str], str, ProbeBinding | None]:
    """Shared ``docker run`` prefix + image + probe binding for argv builders.

    Covers everything up to and including the image: runtime flags, probe
    device forwarding, the three mounts (project read-write at
    ``/project``, ``engine`` + ``packs`` read-only), env, and working dir.
    Validation matches :func:`build_container_argv` (``local`` mode and empty
    verbs raise :class:`ValueError`).
    """
    if request.mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {request.mode!r}")
    if request.mode == "local":
        raise ValueError("local mode executes in-process; no container argv exists")
    if not request.verb:
        raise ValueError("verb must be non-empty")
    if not request.stack:
        raise ValueError("stack must be non-empty (resolve it from the pack or the project)")
    image = (lookup or DefaultImageLookup()).image_for(request.stack)
    project_abs = Path(request.project_dir).resolve()
    # Probe resolution only for verbs that use the probe: build/create don't, and
    # forwarding --device into `build` is an unrecognised arg (bug-010).
    binding = (
        resolve_probe_binding(
            os_name=request.os_name,
            device=request.device,
            vid=request.vid,
            pid=request.pid,
            serial=request.serial,
            transport=request.probe_transport,
        )
        if request.verb in ("flash", "debug", "dev")
        else None
    )
    docker_devices: list[str] = []
    if binding is not None:
        # USB probes: pass the whole bus, not one node number. Docker binds
        # devices at container creation, so a per-node --device goes stale the
        # moment the board is replugged (the node number changes) and the
        # backend cannot open the probe (bug-018). With the bus visible,
        # MU_PROBE_SERIAL is what selects the right probe.
        usb_nodes = [n for n in binding.host_devices if n.startswith(USB_BUS_ROOT + "/")]
        if usb_nodes:
            docker_devices += [
                "--device-cgroup-rule",
                USB_CGROUP_RULE,
                "-v",
                f"{USB_BUS_ROOT}:{USB_BUS_ROOT}",
            ]
        for node in binding.host_devices:
            if node not in usb_nodes:  # non-USB (e.g. a serial tty) keeps --device
                docker_devices += ["--device", f"{node}:{node}"]
    env_args: list[str] = ["-e", "PYTHONPATH=/opt/mu"]
    if binding is not None and binding.serial:
        # The container sees every probe; the serial is how the backend picks ours.
        env_args += ["-e", f"MU_PROBE_SERIAL={binding.serial}"]
    detach = request.detach and request.verb == "dev"
    if detach and not request.name:
        raise ValueError("detached dev requires a container name")
    prefix = [
        CONTAINER_RUNTIME,
        "run",
        *(["-d", "--name", request.name] if detach else ["--rm", *interactive_args(request)]),
        *(["--user", request.container_user] if request.container_user else []),
        *docker_devices,
        "-v",
        f"{project_abs}:{CONTAINER_PROJECT}:rw",
        "-v",
        f"{engine_root()}:{CONTAINER_REPO}/engine:ro",
        "-v",
        f"{packs_dir()}:{CONTAINER_REPO}/packs:ro",
        *env_args,
        "-w",
        CONTAINER_PROJECT,
    ]
    return prefix, image, binding


def detach_command(env_setup: str) -> str:
    """Shell that keeps the container up **and** gives every shell the toolchain.

    ``sleep infinity`` is only a liveness placeholder: an editor attaches by
    exec-ing into the container, and an exec'd shell never runs the image's
    ENTRYPOINT — so a stack whose image sets its toolchain up there (rather than
    on PATH) must expose it through the shell profile instead.
    """
    setup = ""
    if env_setup:
        setup = (
            "mkdir -p /etc/profile.d; "
            f"printf '%s\\n' '{env_setup} >/dev/null 2>&1' > /etc/profile.d/zz-mu-env.sh; "
            "if [ -f /root/.bashrc ] && ! grep -q zz-mu-env /root/.bashrc; then "
            "printf '%s\\n' '. /etc/profile.d/zz-mu-env.sh' >> /root/.bashrc; fi; "
        )
    return setup + "exec sleep infinity"


def build_container_argv(
    request: ShimRequest, *, lookup: ImageLookup | None = None
) -> list[str]:
    """Return the exact ``docker run`` argv for ``request``.

    The image carries toolchains only, so the container side runs the engine
    from the read-only repo mount: ``python3 -m engine <verb> ... --mode
    local`` with ``--project-dir /project``. The probe binding resolves on the
    host: its USB device node(s) become docker ``--device`` flags, and the
    selector forwards into the container as ``--device`` (pack ids resolve via
    the mounted repo; ``--mcu-config`` files must live under the project —
    enforced by the caller).
    ``local`` mode executes in-process and never builds argv: it raises
    :class:`ValueError`. Unknown mode/lang raises :class:`ValueError`.
    """
    lookup = lookup or DefaultImageLookup()
    prefix, image, binding = _container_prefix(request, lookup=lookup)
    inner: list[str] = ["python3", "-m", "engine"]
    if request.verb == "dev":
        inner = (
            ["bash", "-lc", detach_command(request.env_setup)]
            if request.detach
            else ["/bin/bash"]
        )
    else:
        inner += [request.verb, "--lang", request.lang, "--mode", "local"]
        inner += ["--project-dir", CONTAINER_PROJECT]
        if request.mcu_config is not None:
            inner += ["--mcu-config", request.mcu_config]
        if binding is not None:
            inner += ["--device", binding.selector]
        inner += list(request.extra)
    return [*prefix, image, *inner]


def build_probe_argv(
    request: ShimRequest, *, lookup: ImageLookup | None = None
) -> list[str]:
    """Return a mount-preflight probe argv for ``request`` (bug-022).

    Same ``docker run`` prefix (flags, devices, the three mounts, env, work
    dir) and image as :func:`build_container_argv`, but non-interactive and
    running ``true`` instead of the verb. Mounts are created at container
    creation, so one probe run ground-truths every mount at once — no
    blocklists, no guessing which roots a runtime shares. ``local`` mode,
    unknown mode/lang raise :class:`ValueError` like the run argv.
    """
    prefix, image, _ = _container_prefix(
        replace(request, interactive=False, detach=False), lookup=lookup
    )
    return [*prefix, image, "true"]


_MOUNT_SOURCE_RE = re.compile(r"error while creating mount source path '([^']+)'")


def parse_mount_failure(stderr_text: str) -> str | None:
    """Host path of the rejected mount source in daemon stderr, if any (bug-022).

    Matches the daemon's ``error while creating mount source path ...`` and
    maps runtime-side prefixes back to host paths (Docker Desktop on macOS
    reports ``/host_mnt/<host path>``). Returns ``None`` when the text is not
    a mount failure.
    """
    match = _MOUNT_SOURCE_RE.search(stderr_text or "")
    if match is None:
        return None
    node = match.group(1)
    if node.startswith("/host_mnt/"):
        return "/" + node[len("/host_mnt/") :]
    return node


def describe_mount_failure(host_path: str) -> str:
    """Friendly rendering of a rejected mount source (bug-022)."""
    return (
        f"mu: error: the container runtime cannot mount '{host_path}'\n"
        f"  fix: move it somewhere the runtime can share (e.g. /tmp or ~/projects), "
        f"repair its ownership/permissions, or (Docker Desktop) add it under "
        f"Settings -> Resources -> File Sharing"
    )


def interactive_args(request: ShimRequest) -> list[str]:
    """``-it`` exactly when the verb needs an interactive terminal."""
    return ["-it"] if request.interactive else []


def format_argv(argv: list[str]) -> str:
    """Shell-quoted rendering of argv for ``--dry-run`` output."""
    return shlex.join(argv)
