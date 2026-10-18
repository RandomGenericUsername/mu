---
id: ops-040
title: "Guard the ticket board: assert INDEX lists every ticket and its status matches"
kind: ops-task
status: done
size: S
lane: direct
links:
  openspec: none
  bmad: none
worktree: .worktrees/ops-040/
branch: ticket/ops-040-index-guard-test
---

# Guard the ticket board: assert INDEX lists every ticket and its status matches

> `ops-task`; no `parent:`.

## Work

Follow-up recommended by `ops-039`: the INDEX had drifted silently several times and
nothing in `make test` caught it (the board lives outside `engine/`).

Added `engine/tests/test_tickets_index.py` (new `engine/tests/` package, so it runs under
`make test`) asserting:

1. every ticket dir (`ticket.md` or `epic.md`, `_`-prefixed dirs excluded) has an INDEX entry;
2. every INDEX line mentioning a ticket carries that ticket's real `status:` token;
3. `INDEX.md` contains no leftover merge-conflict markers.

## Evidence

```
$ uv run python -m pytest engine/tests/ -q
3 passed
$ uv run python -m pytest engine/ -q
382 passed
```

Failing-as-expected (the guard actually bites) — two independent demonstrations:

- **missing entry rule:** creating `ops-040`'s ticket before adding its INDEX line made
  `engine/tests/` fail immediately (`test_index_lists_every_ticket`) — the guard caught its
  own ticket. Green once the entry was added.
- **status rule:** reverting `epic-001`'s INDEX token to the `ops-039` corruption
  (`` `done` `` → `` `proposed` ``) → `pytest engine/tests/ -q` → **1 failed, 2 passed**
  (`INDEX status drifted …`); restored → **3 passed**.

Full suite on the fixed tree: **382 passed**.

## Done-when

The board invariant is enforced by `make test`. ✅
