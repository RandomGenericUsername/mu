"""Build-stack registry *mechanism* (task-009, AD-11, AD-8).

Core owns the mechanism; toolchain adapters register their stacks. A pack
declares a ``stacks`` map (source language -> stack id) in the shared frame;
the resolved stack — never the language flag — selects the template family, the
toolchain image, and the build command.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "StackSpec",
    "UnknownStackError",
    "clear",
    "register_stack",
    "registered_stacks",
    "stack_spec",
]


@dataclass(frozen=True)
class StackSpec:
    """One build stack: template family + build command + toolchain image."""

    stack_id: str
    template_family: str
    build_argv: tuple[str, ...]
    image: str
    #: Shell fragment enabling the toolchain in a fresh shell (e.g.
    #: ``. /opt/esp/idf/export.sh``). Empty when the image already puts its
    #: toolchain on PATH for every shell.
    env_setup: str = ""
    #: Probe backend that programs this stack's artifacts, when it differs
    #: from the pack's ``probe_backend`` (e.g. esptool triplet vs espflash ELF).
    flash_backend: str = ""
    #: Container user for the toolchain image (empty = image default). Needed
    #: when the image's default user cannot open the forwarded serial device
    #: (e.g. esp-idf-rust's ``esp`` user vs a host ``uucp`` tty).
    container_user: str = ""

    def __post_init__(self) -> None:
        for name in ("stack_id", "template_family", "image"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"StackSpec.{name} must be a non-empty string")
        argv = tuple(self.build_argv)
        if not argv or not all(isinstance(arg, str) and arg for arg in argv):
            raise ValueError("StackSpec.build_argv must be a non-empty sequence of non-empty strings")
        object.__setattr__(self, "build_argv", argv)
        if not isinstance(self.flash_backend, str):
            raise ValueError("StackSpec.flash_backend must be a string")
        if not isinstance(self.container_user, str):
            raise ValueError("StackSpec.container_user must be a string")


_REGISTRY: dict[str, StackSpec] = {}


class UnknownStackError(ValueError):
    """Raised when a stack id has no registered spec."""


def register_stack(spec: StackSpec) -> None:
    """Register a stack (idempotent for an identical spec; conflict otherwise)."""
    if not isinstance(spec, StackSpec):
        raise TypeError("register_stack expects a StackSpec")
    existing = _REGISTRY.get(spec.stack_id)
    if existing is not None and existing != spec:
        raise ValueError(f"stack {spec.stack_id!r} already registered with a different spec")
    _REGISTRY[spec.stack_id] = spec


def stack_spec(stack_id: str) -> StackSpec:
    try:
        return _REGISTRY[stack_id]
    except KeyError:
        raise UnknownStackError(
            f"unknown build stack: {stack_id!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def registered_stacks() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def clear() -> None:
    """Reset the registry (tests only); re-register via the toolchain adapters."""
    _REGISTRY.clear()
