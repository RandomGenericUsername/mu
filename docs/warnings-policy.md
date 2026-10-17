# Compiler-warnings policy

**Status:** decided — `ops-033` (2026-10-17). This file is the single
authoritative statement of the policy; the verify harness and the evidence log
point here.

## Policy: warn-only

A build cell **never fails on warnings**. Any line matching `/warning/i` in a
cell's combined build output is recorded for that cell and surfaced in the
evidence log (`docs/e2e-evidence.md`, the `- warnings:` block per cell).
Pass/fail is decided **only** by:

- the build command's exit code (non-zero fails the cell), and
- the cell's fit/consistency assertions — ELF size vs the pack's flash/RAM map,
  the ESP32 app vs its factory partition, and `memory.x` vs the pack map.

Warnings are informational: not counted, not gated on, and never allowed to
change a cell's PASS/FAIL.

### Not in scope (default)

`-Werror` is **not** enabled anywhere — neither in the rendered templates nor in
the harness. An opt-in strict mode that promotes warnings to errors is a
possible future enhancement, **deferred**; it would be a new, separately
verified behaviour, not a change to this default. See
`tickets/ops-033-warnings-policy/ticket.md` → "Follow-up".

## Why

The e2e harness exercises *rendered* projects in pinned images where vendor and
toolchain sources legitimately warn — e.g. `flip-link` "missing a lib target" in
the Rust cells, and ESP-IDF's `component_validation.cmake` in the esp32cam cell.
Those warnings are not defects in mu's output, so failing on them would block on
upstream text rather than on mu's own contract.

## Evidence

- `engine/verify/e2e.py:296-297` — `_warnings()` only *collects* lines matching
  `WARNING_RE`; nothing compares that list to the pass condition.
- `engine/verify/e2e.py:320,344,374` — each builder does
  `res.warnings.extend(...)` beside (not into) the exit-code check.
- `engine/verify/e2e.py:321-323,345-347,375-377` — a cell fails only when
  `proc.returncode != 0`; warnings never enter that branch.
- `engine/verify/e2e.py:537-538` — `write_evidence` always emits the
  `- warnings:` block and never touches `res.ok`.
- `docs/e2e-evidence.md:36-44` — `stm32f411re/rust` is **PASS** yet records a
  `warning:` for `flip-link`.
- `docs/e2e-evidence.md:140-157` — `esp32cam/c` is **PASS** yet records ESP-IDF
  CMake warnings.
- `engine/verify/tests/test_e2e.py::test_warnings_are_recorded_and_do_not_fail_the_cell`
  — warning output + exit 0 yields `res.ok is True` with non-empty `res.warnings`.

**Verify:** `uv run python -m pytest engine/verify/tests/test_e2e.py -q`
