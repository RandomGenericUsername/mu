---
id: ops-033
title: "Formalize the compiler-warnings policy"
kind: ops-task
status: done
size: XS
lane: direct
links:
  openspec: none
  bmad: none
worktree: .worktrees/ops-033/
branch: ticket/ops-033-warnings-policy
---

# Formalize the compiler-warnings policy

> `ops-task`; no `parent:`.

## Work

`HANDOFF.md:42-45` lists "warnings policy" as an open thread. In practice the e2e
harness already records warnings per cell and never fails on them — `docs/e2e-evidence.md:5`
("warnings are recorded per cell and never fail (warn-only policy)"). But no explicit
decision is recorded in one place.

- Record the policy (currently: **warn-only**, warnings surfaced in the evidence, build
  does not fail) in the harness doc / a one-line policy note.
- Decide whether an opt-in strict mode (`-Werror`) is wanted; if so, file it as a small
  requirement rather than silently changing the build.

## Done-when

The warnings policy is stated in one place and referenced by the verify harness;
the `HANDOFF.md` open thread is closed.

## Decision (2026-10-17)

**Warn-only — confirmed, unchanged.** Warnings are recorded per cell in the
evidence log and never fail a cell. The policy now lives in exactly one
authoritative place, `docs/warnings-policy.md`; the verify harness references it
from its module docstring.

### Confirm: the code implements warn-only

`rg -n "warn" engine/verify/e2e.py`:

- `engine/verify/e2e.py:296-297` — `_warnings()` collects lines matching
  `WARNING_RE` and returns them; no failure side effect.
- `engine/verify/e2e.py:320,344,374` — each builder does
  `res.warnings.extend(...)`.
- `engine/verify/e2e.py:321-323,345-347,375-377` — the only failure branch is
  `proc.returncode != 0`; `res.warnings` is never consulted.
- `engine/verify/e2e.py:537-538` — `write_evidence` always emits the
  `- warnings:` block; `res.ok` is untouched.
- No `-Werror` anywhere in the repo (templates or harness).

A warning-bearing cell still PASSes:
`docs/e2e-evidence.md:36-44` (`stm32f411re/rust` PASS + `flip-link` warning) and
`docs/e2e-evidence.md:140-157` (`esp32cam/c` PASS + CMake warnings).

Regression test added:
`engine/verify/tests/test_e2e.py::test_warnings_are_recorded_and_do_not_fail_the_cell`.

### `-Werror` strict mode — deferred (follow-up)

Default stays warn-only. An opt-in strict mode that promotes warnings to errors
is recorded here as a possible future enhancement rather than implemented: it
would need a flag threaded through every template family **and** the harness and
verified on the docker-backed e2e matrix — out of scope for this record task.
No build flags changed.

## Evidence

- `docs/warnings-policy.md` — authoritative policy statement (created here).
- `engine/verify/e2e.py:19-20` — harness docstring: "Warnings policy: warn-only
  — recorded per cell, never failing a cell (`docs/warnings-policy.md` is the
  authoritative statement)."
- `engine/verify/e2e.py` `_warnings` / builders / `write_evidence` — code shows
  warnings never gate pass/fail (lines above).
- `engine/verify/tests/test_e2e.py::test_warnings_are_recorded_and_do_not_fail_the_cell`
  — warning text + exit 0 → `res.ok is True`, `res.warnings` non-empty.
- `HANDOFF.md:43-52` — warnings-policy open thread closed.

Commands:

- `rg -n "warn" engine/verify/e2e.py` — confirms the collection-only paths.
- `uv run python -m pytest engine/verify/tests/test_e2e.py -q` → `14 passed`
  (was 13; one new regression test).
- `uv run python -m pytest engine/ -q` → `379 passed` (was 378).

Verify: `uv run python -m pytest engine/ -q`
