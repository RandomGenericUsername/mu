---
id: ops-032
title: "Amend the spec success signal for the Rust build-parity decision"
kind: ops-task
status: in-progress
size: XS
lane: direct
links:
  openspec: none
  bmad: none
worktree: .worktrees/ops-032/
branch: ticket/ops-032-rust-spec-wording
---

# Amend the spec success signal for the Rust build-parity decision

> `ops-task`; no `parent:`.

## Work

The `spike-008` decision (2026-10-16) made **Rust build-parity for V1** — the flash/run
gate rests on the C/C++ LED proof per board. But the product artifacts still say every
cell flashes + runs:

- `_bmad-output/…/spec-universal-mcu-env/spec-universal-mcu-env.md:65-67` — "each V1
  matrix cell (3 STM32 boards × 3 languages) completes create → build → **flash** and
  the board runs".
- `_bmad-output/…/spec-universal-mcu-env/device-matrix.md:3` — "Each cell must complete
  create → build → **flash** → observable proof".

Amend both to reflect: **C/C++ = flash/run + observable proof; Rust = build-to-ELF
parity** (per `spike-008`, `docs/flash-run-evidence.md` "Scope note"). This edits a
finalized BMAD spec artifact — do it as a deliberate spec amendment (broad-scope rule),
not a silent doc tweak.

## Done-when

`spec:65-67` and `device-matrix.md:3` state the C/C++-vs-Rust distinction, and
`spike-008` links to the amendment.

## Evidence

Worktree `.worktrees/ops-032/`, branch `ticket/ops-032-rust-spec-wording` (created from
clean `main` `85f7f08`). Edits (all deliberate, dated amendments — no silent rewrites):

- `_bmad-output/…/spec-universal-mcu-env/spec-universal-mcu-env.md:29` (CAP-3 `success`):
  - **before:** `Clean machine runs build → flash → observable run proof for every matrix cell.`
  - **after:** `Clean machine runs build → flash → observable run proof for every C/C++ matrix cell, and build-to-ELF parity for every Rust cell (amended 2026-10-17 — see `spike-008`).`
- `…/spec-universal-mcu-env.md:67` (Success signal):
  - **before:** `From a clean machine, each **V1 matrix cell** (3 STM32 boards × 3 languages) completes create → build → flash and the board runs its program with the pack-defined observable proof.`
  - **after:** `From a clean machine, each **C/C++ V1 matrix cell** (3 STM32 boards × 2 languages) completes create → build → flash and the board runs its program with the pack-defined observable proof; each **Rust V1 matrix cell** completes create → build to a flashable ELF (build-parity).`
  - plus a dated amendment blockquote at `…/spec-universal-mcu-env.md:71` quoting the old wording, cross-linking `tickets/spike-008-rust-flash-run/ticket.md` and `docs/flash-run-evidence.md` §"Scope note".
- `_bmad-output/…/spec-universal-mcu-env/device-matrix.md:3`:
  - **before:** `Day-one shippable matrix. Each cell must complete create → build → flash → observable proof from a clean machine.`
  - **after:** `Day-one shippable matrix. Each C/C++ cell must complete create → build → flash → observable proof from a clean machine; each Rust cell must complete create → build to a flashable ELF (build-parity).`
  - plus a dated amendment blockquote at `device-matrix.md:5` (same cross-links).
- `tickets/spike-008-rust-flash-run/ticket.md` — "Discrepancy to reconcile" bullet now
  records the spec half as **Reconciled (2026-10-17)** by this ticket (back-link).
- `HANDOFF.md` untouched (owned by `ops-033`). No product behaviour or engine code changed.

Evidence JD: only docs/markdown changed; no code paths affected.
`Verify:` `git -C .worktrees/ops-032 diff --stat` and
`git -C .worktrees/ops-032 log -1 --stat` (expect 5 files, all `.md`).
