---
id: ops-034
title: "Decide GHCR image package visibility (public vs auth-required)"
kind: ops-task
status: done
size: XS
lane: direct
links:
  openspec: none
  bmad: none
worktree: none
branch: none
---

# Decide GHCR image package visibility (public vs auth-required)

> `ops-task`; no `parent:`.

## Work

`ops-030` recorded that the pinned images are published to `ghcr.io` but the package is
**auth-required** (anonymous pull denied; `RepoDigests` prove registry presence). So a
clean host must `docker login ghcr.io` or build locally (`make images`).

- Decide: make the package **public** (clean-machine `docker pull` needs no login) or
  keep it private (login/`make images`). Not a V1 blocker either way.
- Record the decision and reflect it in `README.md` (install section) and
  `docs/vscode-debug.md` §9.

## Done-when

The visibility decision is recorded and the docs match it; the `HANDOFF.md` registry
thread stays closed.

## Decision (2026-10-17)

**Keep the GHCR packages PRIVATE** (no change from the current state). Rationale: the
images are author/personal-project distribution for now; a clean machine either
`docker login ghcr.io` (token with `read:packages`) or builds locally with `make images`.

Docs already match this — no edits needed:

- `docs/vscode-debug.md:154-156` — "an **auth-required** package: `docker login ghcr.io`
  first … or build it locally with `make images`".
- `README.md:17` — `make images` is the from-scratch path.

No GitHub-side change required (the earlier "make public" idea was dropped). Note: flipping
to public would need a token with `write:packages` (`gh` here lacks even `read:packages`).
