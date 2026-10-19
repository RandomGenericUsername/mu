"""Adapter ports (req-005, group 1; split by task-007): device-agnostic contracts only.

Programming and sessions are separate ports (AD-12): :class:`FlashPort`
(``render_argv``/``flash``/``proof_for``) is implemented by every probe
backend; :class:`DebugPort` (``debug``) only by backends whose device
supports attach. :class:`ProbeAdapter` is the composite for backends that do
both. The image-lookup port maps language -> container image. Real
implementations arrive later; stubs live in :mod:`engine.cli.tests.stubs`.
Core types are read-only views — ports never touch packs, paths, or raw YAML.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Sequence

from engine.core.model import DeviceView, Endpoint, ProofResult

__all__ = [
    "DebugHandle",
    "DebugPort",
    "DefaultImageLookup",
    "FlashPort",
    "ImageLookup",
    "PieceResult",
    "ProbeAdapter",
    "default_backend_name",
    "get_adapter",
    "register_backend",
]


@dataclass(frozen=True)
class PieceResult:
    """Outcome for one programmed piece: piece name + pass/fail + detail."""

    name: str
    ok: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PieceResult.name must be non-empty")


@dataclass(frozen=True)
class DebugHandle:
    """Handle for an attached debug session: id + prepared endpoint."""

    session_id: str
    endpoint: Endpoint

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("DebugHandle.session_id must be non-empty")
        if not isinstance(self.endpoint, Endpoint):
            raise TypeError("DebugHandle.endpoint must be an Endpoint")


class FlashPort(ABC):
    """Programming port (AD-12): tool argv, flashing, and proof.

    Every probe backend implements this port — including programming-only
    devices with no attach (e.g. ESP32 over UART). :meth:`proof_for` fills the
    core-owned proof struct for the rungs this port can certify (write and
    readback rungs); attach-derived rungs belong to :class:`DebugPort`.
    """

    #: Transcript of the most recent :meth:`flash` (backend-native shape), or
    #: ``None``; feeds :meth:`proof_for` so verdicts carry proof.
    last_transcript: object | None

    @abstractmethod
    def render_argv(
        self,
        device: DeviceView,
        endpoint: Endpoint,
        pieces: Sequence[str],
    ) -> list[str]:
        """Build the programming tool argv (no execution)."""

    @abstractmethod
    def flash(
        self,
        device: DeviceView,
        endpoint: Endpoint,
        pieces: Sequence[str],
    ) -> Sequence[PieceResult]:
        """Program each named piece; return one result per piece, in order."""

    @abstractmethod
    def proof_for(
        self,
        device: DeviceView,
        results: Sequence[PieceResult],
        transcript: object,
    ) -> ProofResult:
        """Fill the core-owned proof struct from a completed flash."""


class DebugPort(ABC):
    """Session port (AD-12): attach / monitor.

    Implemented only where the device supports attach; the CLI fails the
    ``debug`` verb when the resolved backend does not implement it, rather
    than fabricating a handle.
    """

    @abstractmethod
    def debug(self, device: DeviceView, endpoint: Endpoint) -> DebugHandle:
        """Attach a session; return its handle."""


class ProbeAdapter(FlashPort, DebugPort):
    """Composite port for backends that both program *and* attach.

    Compatibility alias: the two STM32 backends implement it. A
    programming-only backend implements :class:`FlashPort` alone.
    """


_BACKEND_FACTORIES: dict[str, Callable[[], FlashPort]] = {}


def register_backend(name: str, factory: Callable[[], FlashPort]) -> None:
    """Register a probe backend factory (adapters own backend vocabulary)."""
    _BACKEND_FACTORIES[name] = factory


def default_backend_name() -> str:
    """Backend used when the invocation names none."""
    return "openocd"


def _ensure_builtin_backends() -> None:
    # Deferred imports: backend modules import the ABCs above, so importing
    # them at package top would be circular.
    if "openocd" not in _BACKEND_FACTORIES:
        from engine.adapters.openocd import OpenOCDAdapter

        _BACKEND_FACTORIES["openocd"] = OpenOCDAdapter
    if "probe-rs" not in _BACKEND_FACTORIES:
        from engine.adapters.probe_rs import ProbeRsAdapter

        _BACKEND_FACTORIES["probe-rs"] = ProbeRsAdapter
    if "esptool" not in _BACKEND_FACTORIES:
        from engine.adapters.esptool import EsptoolAdapter

        _BACKEND_FACTORIES["esptool"] = EsptoolAdapter
    if "espflash" not in _BACKEND_FACTORIES:
        from engine.adapters.espflash import EspflashAdapter

        _BACKEND_FACTORIES["espflash"] = EspflashAdapter


def get_adapter(name: str | None = None, **kwargs) -> FlashPort:
    """Instantiate a registered probe backend (default when unnamed).

    Callers never name backend modules — adding a backend touches this
    registry only, never CLI code. The returned object is guaranteed to be a
    :class:`FlashPort`; callers needing sessions check ``isinstance(…,
    DebugPort)`` (AD-12). Extra kwargs (``stream``, ``log_path``) pass to the
    backend constructor.
    """
    _ensure_builtin_backends()
    key = name or default_backend_name()
    try:
        return _BACKEND_FACTORIES[key](**kwargs)
    except KeyError:
        raise ValueError(
            f"unknown probe backend {key!r}; registered: {sorted(_BACKEND_FACTORIES)}"
        ) from None


class ImageLookup(ABC):
    """Port mapping a resolved build stack -> container image reference (AD-8)."""

    @abstractmethod
    def image_for(self, stack_id: str) -> str:
        """Return the image reference for ``stack_id``; an unknown stack raises."""

    @abstractmethod
    def supported_stacks(self) -> tuple[str, ...]:
        """Build stacks with a known image."""


class DefaultImageLookup(ImageLookup):
    """Core-owned default: the registered build stacks (AD-8, AD-11).

    No toolchain data lives here — the toolchain adapters register their stacks
    against the core registry (:mod:`engine.core.stacks`), so adding a stack is
    a registration, never a core edit (AD-1).
    """

    def image_for(self, stack_id: str) -> str:
        from engine.adapters.toolchain import ensure_registered
        from engine.core.stacks import stack_spec

        ensure_registered()
        return stack_spec(stack_id).image

    def supported_stacks(self) -> tuple[str, ...]:
        from engine.adapters.toolchain import ensure_registered
        from engine.core.stacks import registered_stacks

        ensure_registered()
        return registered_stacks()
