"""Toolchain adapters (task-009, AD-8): register build stacks against the core registry.

One stack per toolchain family. Registration — never a core edit — is how a
toolchain joins (AD-1): ``core/`` owns the mechanism (:mod:`engine.core.stacks`),
adapters own the specs (image, build command, template family). A pack's
``stacks`` map selects among them by source language.
"""

from __future__ import annotations

from engine.core.stacks import StackSpec, register_stack

__all__ = [
    "CARGO_CORTEX",
    "CARGO_CORTEX_DUAL",
    "IDF_CMAKE",
    "MAKE_CMSIS",
    "ensure_registered",
]

#: ARM GCC + CMSIS device trees, built with make (C and C++).
MAKE_CMSIS = StackSpec(
    stack_id="make-cmsis",
    template_family="c-cmsis",
    build_argv=("make", "build"),
    image="ghcr.io/randomgenericusername/lang-cpp:15.3.rel2",
)

#: Rust on Cortex-M, built with cargo.
CARGO_CORTEX = StackSpec(
    stack_id="cargo-cortex",
    template_family="rust-cortex",
    build_argv=("cargo", "build"),
    image="ghcr.io/randomgenericusername/lang-rust:1.99.0",
)

#: Rust dual-core: one cargo package per core, driven by the generated
#: Makefile (Cargo cannot select two `--target`s in one invocation).
CARGO_CORTEX_DUAL = StackSpec(
    stack_id="cargo-cortex-dual",
    template_family="rust-cortex-dual",
    build_argv=("make", "build"),
    image="ghcr.io/randomgenericusername/lang-rust:1.99.0",
)

#: ESP-IDF (xtensa + CMake/Ninja), built with ``idf.py``. Image digest pinned
#: from spike-007 (``docker buildx imagetools inspect espressif/idf:v6.1``,
#: amd64 + arm64); the template family renders in E3.
IDF_CMAKE = StackSpec(
    stack_id="idf-cmake",
    template_family="idf-cmake",
    build_argv=("idf.py", "build"),
    image=(
        "espressif/idf:v6.1"
        "@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c"
    ),
    # The espressif image enables IDF in its ENTRYPOINT only, so a shell we
    # start ourselves (or one VS Code opens) must source it.
    env_setup=". /opt/esp/idf/export.sh",
)

_SHIPPED = (MAKE_CMSIS, CARGO_CORTEX, CARGO_CORTEX_DUAL, IDF_CMAKE)


def ensure_registered() -> None:
    """Register every shipped stack (idempotent; safe after ``stacks.clear``)."""
    for spec in _SHIPPED:
        register_stack(spec)
