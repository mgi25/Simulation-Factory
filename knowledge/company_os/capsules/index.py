"""The index: deterministic lookup over capsules, and the checks that keep it honest.

A directory of JSON files, loaded in sorted order, held in a dict. That is the
whole storage design, for the reason `ledger.py` gives for the knowledge store:
at bootstrap there are single-digit capsules, every lookup is by an explicit
field, and a directory of files diffs, merges and reads with `cat`. An index
that needs a build step is an index that will be stale.

## Deterministic means reproducible, not merely sorted

Every method here returns a tuple in a stable order, and the order never
depends on filesystem enumeration, insertion order or a hash seed. Two sessions
that load the same directory get the same answers in the same sequence, which
is what makes a selection reproducible and therefore reviewable.

## No fuzzy matching, anywhere

Lookup is by capsule id, type, owner, capability tag, repository path or
knowledge-record id. Path lookup is segment-aware prefix matching in both
directions - a capsule owning `company/runtime` answers a query about
`company/runtime/routing.py`, and one owning `company/runtime/routing.py`
answers a query about `company/runtime` - because both are the same question
asked from different altitudes. Nothing here scores string similarity, and
`company/run` does not match `company/runtime`.

## Integrity is the single-source-of-truth check

`integrity()` reports what a capsule cannot notice about itself: two capsules
claiming the same path, a dependency on a capsule id nobody defines, a link to
a knowledge record that is not in the store, a path that no longer exists. It
deliberately does not look for contradictions between two English sentences -
that is a reasoning task, and `ledger.KnowledgeStore.contradictions` already
draws the same line.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from ai_platform.serde import read_json, write_json
from knowledge.company_os.capsules.budget import CapsuleError
from knowledge.company_os.capsules.capsule import Capsule, CapsuleType
from knowledge.company_os.ledger import KnowledgeStore
from knowledge.company_os.records import DecisionStatus, KnowledgeError, RecordStatus

SEED_ROOT = Path(__file__).resolve().parent / "seeds"
REPO_ROOT = Path(__file__).resolve().parents[3]

# Fields whose paths must exist on disk. `may_read`, `may_write` and
# `must_not_modify` are permission surfaces, often broad and often naming
# things that do not exist yet on purpose, so checking them would report noise.
_EXISTENCE_CHECKED: tuple[str, ...] = ("owns_paths", "tests", "benchmarks")


def normalise_path(value: str) -> str:
    """Reduce a path-ish reference to the form path comparisons are done in.

    Strips a `::node` test suffix, a `#L10-L20` span, a trailing glob segment
    and a trailing slash, and normalises separators. What remains is the part
    two references have in common when they are talking about the same place.
    """
    text = value.replace("\\", "/").strip()
    for cut in ("::", "#"):
        if cut in text:
            text = text.split(cut, 1)[0]
    while text.endswith(("/**", "/*")):
        text = text.rsplit("/", 1)[0]
    if text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def path_related(left: str, right: str) -> bool:
    """True when two paths name the same place, or one contains the other.

    Segment-aware in both directions: `company/run` and `company/runtime` are
    unrelated, `company/runtime` and `company/runtime/routing.py` are not.
    """
    a, b = normalise_path(left), normalise_path(right)
    if not a or not b:
        return False
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


@dataclass(frozen=True)
class CapsuleStaleness:
    """Why one capsule should be revalidated, in machine-checkable reasons."""

    capsule_id: str
    reasons: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.reasons)


class CapsuleIndex:
    """Capsules, addressed by every field the selector needs."""

    def __init__(self, capsules: Iterable[Capsule]) -> None:
        by_id: dict[str, Capsule] = {}
        for capsule in capsules:
            if capsule.id in by_id:
                raise CapsuleError(
                    f"duplicate capsule id {capsule.id!r}. A capsule id is the single "
                    "name for one boundary; two of them means two answers to the same "
                    "question and no way to tell which is authoritative."
                )
            by_id[capsule.id] = capsule
        self._by_id = by_id

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, root: Path | str = SEED_ROOT) -> CapsuleIndex:
        """Load every `*.json` under `root`, in filename order."""
        directory = Path(root)
        if not directory.is_dir():
            return cls(())
        return cls(Capsule.from_dict(read_json(path)) for path in sorted(directory.glob("*.json")))

    @staticmethod
    def write(capsule: Capsule, root: Path | str = SEED_ROOT) -> Path:
        """Write one capsule as canonical JSON at `<root>/<id>.json`."""
        return write_json(Path(root) / f"{capsule.id}.json", capsule)

    # -- lookup -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, capsule_id: object) -> bool:
        return capsule_id in self._by_id

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    def all(self) -> tuple[Capsule, ...]:
        return tuple(self._by_id[key] for key in self.ids())

    def get(self, capsule_id: str) -> Capsule:
        if capsule_id not in self._by_id:
            raise CapsuleError(f"no capsule {capsule_id!r}; known ids: {', '.join(self.ids())}")
        return self._by_id[capsule_id]

    def by_type(self, capsule_type: CapsuleType) -> tuple[Capsule, ...]:
        return tuple(c for c in self.all() if c.type is capsule_type)

    def by_owner(self, owner: str) -> tuple[Capsule, ...]:
        return tuple(c for c in self.all() if c.owner == owner)

    def by_capability(self, tag: str) -> tuple[Capsule, ...]:
        return tuple(c for c in self.all() if tag in c.capabilities)

    def by_path(self, path: str) -> tuple[Capsule, ...]:
        """Capsules owning a path related to `path`, in id order."""
        return tuple(
            c for c in self.all() if any(path_related(owned, path) for owned in c.owns_paths)
        )

    def by_decision(self, decision_id: str) -> tuple[Capsule, ...]:
        return tuple(c for c in self.all() if decision_id in c.decisions)

    def by_knowledge(self, record_id: str) -> tuple[Capsule, ...]:
        """Capsules linking `record_id` as a fact, decision or learning."""
        return tuple(
            c for c in self.all() if any(rid == record_id for _kind, rid in c.knowledge_links())
        )

    def dependency_closure(self, capsule_id: str) -> tuple[str, ...]:
        """Every capsule `capsule_id` depends on, transitively, in id order.

        Breadth-first over sorted dependencies, so the walk is reproducible;
        unknown ids are skipped here and reported by `integrity()`, because a
        dangling dependency should not make a selection fail at request time.
        """
        seen: set[str] = set()
        frontier = [capsule_id]
        while frontier:
            current = frontier.pop(0)
            if current not in self._by_id:
                continue
            for dependency in sorted(self._by_id[current].dependencies):
                if dependency not in seen and dependency != capsule_id:
                    seen.add(dependency)
                    frontier.append(dependency)
        return tuple(sorted(seen))

    # -- measurement ------------------------------------------------------

    def total_chars(self) -> int:
        return sum(capsule.size_chars() for capsule in self.all())

    # -- integrity --------------------------------------------------------

    def integrity(
        self,
        store: KnowledgeStore | None = None,
        repo_root: Path | str | None = None,
    ) -> tuple[str, ...]:
        """Every single-source-of-truth violation the index can prove, sorted.

        `store` enables the knowledge-link checks and `repo_root` the path
        checks; both are optional so the structural checks can run with neither
        a store nor a checkout.
        """
        problems: list[str] = []
        problems.extend(self._dangling_dependencies())
        problems.extend(self._duplicate_path_claims())
        if store is not None:
            problems.extend(self._missing_knowledge(store))
        if repo_root is not None:
            problems.extend(self._missing_paths(Path(repo_root)))
        return tuple(sorted(problems))

    def _dangling_dependencies(self) -> list[str]:
        out = []
        for capsule in self.all():
            for dependency in capsule.dependencies:
                if dependency not in self._by_id:
                    out.append(
                        f"{capsule.id}: depends on capsule {dependency!r}, which does not exist"
                    )
        return out

    def _duplicate_path_claims(self) -> list[str]:
        """A path owned by two capsules has two owners, which is no owner."""
        claims: dict[str, list[str]] = {}
        for capsule in self.all():
            for owned in capsule.owns_paths:
                claims.setdefault(normalise_path(owned), []).append(capsule.id)
        return [
            f"path {path!r} is owned by {len(owners)} capsules: {', '.join(sorted(owners))}"
            for path, owners in claims.items()
            if len(owners) > 1
        ]

    def _missing_knowledge(self, store: KnowledgeStore) -> list[str]:
        out = []
        for capsule in self.all():
            for record_kind, record_id in capsule.knowledge_links():
                try:
                    store.get(record_kind, record_id)
                except KnowledgeError:
                    out.append(
                        f"{capsule.id}: links {record_kind} {record_id!r}, "
                        "which is not in the knowledge store"
                    )
        return out

    def _missing_paths(self, repo_root: Path) -> list[str]:
        out = []
        for capsule in self.all():
            for field in _EXISTENCE_CHECKED:
                for ref in getattr(capsule, field):
                    if not _exists(repo_root, ref):
                        out.append(f"{capsule.id}.{field}: {ref!r} does not exist in the repository")
        return out

    # -- freshness --------------------------------------------------------

    def staleness(
        self,
        today: dt.date,
        store: KnowledgeStore | None = None,
        observed_digests: Mapping[str, str] | None = None,
    ) -> tuple[CapsuleStaleness, ...]:
        """Capsules with at least one revalidation reason, in id order.

        The four conditions from the bootstrap spec, each a pure function of
        data the caller supplies: the review expired, a recorded source path
        changed, a linked decision was superseded or rolled back, or somebody
        flagged it. Nothing here watches git; `observed_digests` is how the
        caller reports what it saw.
        """
        out: list[CapsuleStaleness] = []
        for capsule in self.all():
            reasons: list[str] = []
            if capsule.is_stale(today):
                reasons.append(f"review overdue: recheck was due {capsule.recheck_on}")
            if capsule.is_flagged():
                reasons.append(f"flagged: {capsule.revalidation_reason or 'no reason given'}")
            if observed_digests is not None:
                for path in capsule.changed_sources(observed_digests):
                    reasons.append(f"source changed: {path}")
            if store is not None:
                reasons.extend(_superseded_decisions(capsule, store))
            if reasons:
                out.append(CapsuleStaleness(capsule.id, tuple(reasons)))
        return tuple(out)

    def needing_revalidation(
        self,
        today: dt.date,
        store: KnowledgeStore | None = None,
        observed_digests: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        """Just the ids, for a work list."""
        return tuple(s.capsule_id for s in self.staleness(today, store, observed_digests))


def _superseded_decisions(capsule: Capsule, store: KnowledgeStore) -> list[str]:
    out = []
    for decision_id in capsule.decisions:
        try:
            decision = store.get("decision", decision_id)
        except KnowledgeError:
            continue  # reported by integrity(), not twice
        if decision.status in (DecisionStatus.SUPERSEDED, DecisionStatus.ROLLED_BACK):
            successor = f" -> {decision.superseded_by}" if decision.superseded_by else ""
            out.append(f"decision {decision_id} is {decision.status.value}{successor}")
    for record_kind, record_id in capsule.knowledge_links():
        if record_kind == "decision":
            continue
        try:
            record = store.get(record_kind, record_id)
        except KnowledgeError:
            continue
        if getattr(record, "status", None) in (RecordStatus.SUPERSEDED, RecordStatus.RETIRED):
            out.append(f"{record_kind} {record_id} is {record.status.value}")
    return out


def _exists(repo_root: Path, ref: str) -> bool:
    """Does a pointer resolve to something in the checkout?

    Globs resolve if they match at least one entry. A test node id resolves if
    its file does - whether the node itself exists is pytest's answer to give,
    not this module's.
    """
    cleaned = normalise_path(ref)
    if not cleaned:
        return False
    if "*" in ref:
        pattern = ref.replace("\\", "/").split("::", 1)[0]
        return any(True for _ in repo_root.glob(pattern))
    return (repo_root / cleaned).exists()
