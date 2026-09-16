"""The store: one JSON file per record, one directory per kind, no database.

`docs/company_os_v1_bootstrap.md` puts "no vector DB" in scope and constitution
rule 17 says prove need before building. At bootstrap the store holds tens of
records, every one of which is retrieved by kind and id or swept in full. A
directory of files answers both in microseconds, and it brings three things a
database would take away:

- it diffs. A knowledge change shows up in `git diff` as the sentence that
  changed, reviewable in the same pass as the code that motivated it;
- it merges. Two sessions adding records touch different files;
- it is legible with no tooling. The next session reads a record with `cat`.

Semantic retrieval is a real future need and this layout does not block it: an
index built over these files can be added later without moving the records.
Building it now would be building for a corpus that does not exist.

## Determinism

Writes go through `ai_platform.serde.dumps`, which sorts keys, so the same
record produces the same bytes on any machine. `load_all` sorts by id, so a
sweep is order-stable regardless of what the filesystem returns. Nothing here
reads the clock except `stale()`, which takes `today` and only defaults to the
real date at that one boundary.

## The decision ledger

`DecisionLedger` is a thin view over the decision records, and its three
transitions - reconsider, roll back, supersede - change `status` and add a
reason. They never rewrite `why`, `evidence`, `alternatives`, `risks`,
`reconsider_if` or `rollback`, because the value of the ledger is showing what
was believed and planned at the time the decision was made. A ledger that
edits its own history is a worse version of the git log.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from ai_platform.references import assert_text
from ai_platform.serde import read_json, write_json
from knowledge.company_os.freshness import is_stale
from knowledge.company_os.records import (
    DECAYING_TYPES,
    RECORD_TYPES,
    Decision,
    DecisionStatus,
    KnowledgeError,
)

DEFAULT_ROOT = Path(__file__).resolve().parent / "records"


class KnowledgeStore:
    """A directory of knowledge records, addressed by (kind, id)."""

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)

    def path_for(self, kind: str, record_id: str) -> Path:
        if kind not in RECORD_TYPES:
            raise KnowledgeError(f"unknown record kind {kind!r}; expected one of {sorted(RECORD_TYPES)}")
        return self.root / kind / f"{record_id}.json"

    def add(self, record: Any, *, overwrite: bool = False) -> Path:
        """Write a record. Refuses to overwrite silently - history is the point."""
        kind = getattr(record, "kind", None)
        if kind not in RECORD_TYPES:
            raise KnowledgeError(f"not a knowledge record: {type(record).__name__}")
        path = self.path_for(kind, record.id)
        if path.exists() and not overwrite:
            raise KnowledgeError(
                f"{kind}/{record.id} already exists. Supersede it with a new record, "
                "or pass overwrite=True if you are correcting a write."
            )
        return write_json(path, record)

    def get(self, kind: str, record_id: str) -> Any:
        path = self.path_for(kind, record_id)
        if not path.exists():
            raise KnowledgeError(f"no {kind} record {record_id!r} at {path}")
        return RECORD_TYPES[kind].from_dict(read_json(path))

    def load_all(self, kind: str | None = None) -> tuple[Any, ...]:
        """Every record, or every record of one kind, in a stable order."""
        kinds = [kind] if kind else sorted(RECORD_TYPES)
        out: list[Any] = []
        for k in kinds:
            directory = self.root / k
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                out.append(RECORD_TYPES[k].from_dict(read_json(path)))
        return tuple(out)

    def stale(self, today: dt.date | None = None, kind: str | None = None) -> tuple[Any, ...]:
        """Records past their recheck date, oldest due date first.

        This is the one place the real clock is read, and only when the caller
        supplies nothing.
        """
        when = today or dt.date.today()
        return stale_records(self.load_all(kind), when)

    def needing_revalidation(self, today: dt.date | None = None) -> tuple[Any, ...]:
        """Stale records plus any already flagged, as one work list."""
        from knowledge.company_os.records import RecordStatus

        when = today or dt.date.today()
        flagged = tuple(
            r
            for r in self.load_all()
            if getattr(r, "status", None) is RecordStatus.NEEDS_REVALIDATION
        )
        stale = self.stale(when)
        seen: dict[tuple[str, str], Any] = {}
        for record in (*stale, *flagged):
            seen[(record.kind, record.id)] = record
        return tuple(seen[key] for key in sorted(seen))

    def contradictions(self) -> tuple[tuple[str, str], ...]:
        """Every declared contradiction, as (record id, contradicted id) pairs.

        Declared, not detected: finding contradictions between two sentences is
        a reasoning task, and this is the deterministic half - surfacing the
        ones an author already noticed so a reader cannot miss them.
        """
        pairs: list[tuple[str, str]] = []
        for record in self.load_all():
            for other in getattr(record, "contradicts", ()):
                pairs.append((record.id, other))
        return tuple(sorted(set(pairs)))


def stale_records(records: Iterable[Any], today: dt.date) -> tuple[Any, ...]:
    """Filter records to those past their recheck date. Pure, for testing."""
    out = [
        record
        for record in records
        if isinstance(record, DECAYING_TYPES)
        and is_stale(record.freshness, record.created, record.recheck_on, today)
    ]
    out.sort(key=lambda r: (r.recheck_on or r.created, r.kind, r.id))
    return tuple(out)


class DecisionLedger:
    """Decisions, and the three transitions that never lose what they recorded."""

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def record(self, decision: Decision, *, overwrite: bool = False) -> Path:
        return self.store.add(decision, overwrite=overwrite)

    def get(self, decision_id: str) -> Decision:
        return self.store.get(Decision.kind, decision_id)

    def all(self) -> tuple[Decision, ...]:
        return tuple(self.store.load_all(Decision.kind))

    def active(self) -> tuple[Decision, ...]:
        return tuple(d for d in self.all() if d.status is DecisionStatus.ACTIVE)

    def reconsider(self, decision_id: str, reason: str, *, persist: bool = True) -> Decision:
        """Flag a decision for review. Everything it recorded stays as written."""
        assert_text(reason, "reconsideration reason")
        updated = replace(
            self.get(decision_id),
            status=DecisionStatus.UNDER_RECONSIDERATION,
            reconsideration_reason=reason,
        )
        if persist:
            self.store.add(updated, overwrite=True)
        return updated

    def roll_back(self, decision_id: str, reason: str, *, persist: bool = True) -> Decision:
        """Record that the rollback plan was executed, keeping the plan itself."""
        assert_text(reason, "rollback reason")
        updated = replace(
            self.get(decision_id),
            status=DecisionStatus.ROLLED_BACK,
            rollback_reason=reason,
        )
        if persist:
            self.store.add(updated, overwrite=True)
        return updated

    def supersede(
        self, decision_id: str, successor: Decision, *, persist: bool = True
    ) -> tuple[Decision, Decision]:
        """Replace a decision with a new one, leaving a forward pointer."""
        if successor.id == decision_id:
            raise KnowledgeError("a decision cannot supersede itself")
        superseded = replace(
            self.get(decision_id),
            status=DecisionStatus.SUPERSEDED,
            superseded_by=successor.id,
        )
        if persist:
            self.store.add(superseded, overwrite=True)
            self.store.add(successor)
        return superseded, successor
