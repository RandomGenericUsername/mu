---
id: ops-039
title: "Repair INDEX corruption (epic-001 line, req-026 nested status, task-005/006 mangle)"
kind: ops-task
status: done
size: S
lane: direct
links:
  openspec: none
  bmad: none
worktree: .worktrees/ops-039/
branch: ticket/ops-039-fix-index-epic001-line
---

# Repair INDEX corruption

> `ops-task`; no `parent:`.

## Work

Found while answering "is V1 closed?" — the `tickets/INDEX.md` board was corrupted in three places:

1. **`epic-001` line mangled** (`done` → `proposed`, and a stray epic-002 rollup spliced in:
   `` `proposed` | 1/4 children done| 31/31 children done ``). Introduced in `1952c71`
   (the req-027 doc worker, recounting epic-002's rollup). Now:
   `` `done` | 31/31 children done ``.
2. **`req-026` nested entry** under epic-002 still `in-progress` while the ticket is `done`
   (`ops-038` updated only the Requirements-section copy, not the nested one).
3. **`task-005`/`task-006` pre-existing mangle**: `task-005`'s entry had lost its title and
   status entirely, and that text had leaked into `task-006`'s line (duplicated fields).
   Both restored from their ticket titles.

## Evidence

Consistency scan — every ticket dir has an INDEX entry, and every INDEX line mentioning a
dir carries that ticket's real status:

```
dirs checked: 121
missing: none
mismatches: none
```
(before the fix: 1 status mismatch + 1 missing-status line; `epic-001` also misreported
`proposed` while its ticket said `done`.)

## Follow-up (recommended)

There is **no automated INDEX guard**, so this drift is only caught by hand. A small test
(vendor-free: parse `tickets/*/{ticket,epic}.md` + `INDEX.md`, assert every dir is listed
and the status token matches) would catch it in `make test`. File as a follow-up `task`
under the ticket system rather than bundling it into this repair.
