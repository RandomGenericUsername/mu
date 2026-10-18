"""Regression guard for the ticket board (`tickets/INDEX.md`).

The INDEX has drifted silently more than once (a mangled `epic-001` line, a stale
nested child status, and a pre-existing `task-005`/`task-006` mangle — repaired in
`ops-039`). None of it was caught by `make test`, because the ticket board lives
outside `engine/`. This module pulls the invariant into the suite.

Rules enforced (from `tickets/LIFECYCLE.md` / the INDEX header):

- every ticket directory carries an INDEX entry;
- every INDEX line that mentions a ticket shows that ticket's real `status:`;
- the INDEX contains no leftover merge-conflict markers.

Counting rule: directories starting with `_` (`_template`, `_fixtures`) are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

__all__ = ["test_index_lists_every_ticket", "test_index_status_matches_ticket", "test_index_has_no_conflict_markers"]

_TICKETS = Path(__file__).resolve().parents[2] / "tickets"
_INDEX = _TICKETS / "INDEX.md"
_STATUS_RE = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)
#: Status tokens are written as `` `done` `` / `` `in-progress` `` etc. in INDEX lines.
_TOKEN_RE = re.compile(r"`([a-z][a-z-]*)`")


def _item_files() -> Iterator[tuple[str, Path]]:
    """(dir-name, item-file) for every ticket dir, earliest kind wins."""
    for d in sorted(_TICKETS.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for name in ("ticket.md", "epic.md"):
            f = d / name
            if f.is_file():
                yield d.name, f
                break


def _index_lines() -> list[str]:
    return _INDEX.read_text().splitlines()


def _status(item: Path) -> str | None:
    m = _STATUS_RE.search(item.read_text())
    return m.group(1) if m else None


def test_index_lists_every_ticket() -> None:
    idx = _INDEX.read_text()
    missing = [name for name, _ in _item_files() if f"(./{name}/" not in idx]
    assert not missing, (
        "these ticket dirs have no INDEX entry (add one, or they are untracked work): "
        f"{missing}"
    )


def test_index_status_matches_ticket() -> None:
    lines = _index_lines()
    bad: list[str] = []
    for name, item in _item_files():
        status = _status(item)
        if status is None:
            continue
        hits = [ln for ln in lines if f"(./{name}/" in ln]
        for ln in hits:
            if status not in _TOKEN_RE.findall(ln):
                bad.append(f"{name}: ticket says {status!r}, INDEX line: {ln.strip()[:100]}")
    assert not bad, "INDEX status drifted from the ticket files:\n" + "\n".join(bad)


def test_index_has_no_conflict_markers() -> None:
    idx = _INDEX.read_text()
    for marker in ("<<<<<<<", ">>>>>>>", "======="):
        assert marker not in idx, f"INDEX.md contains a leftover merge marker: {marker!r}"
