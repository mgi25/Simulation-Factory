"""Choose the capsules a task needs, from explicit task metadata, deterministically.

This is the piece the rest of the layer exists for. A session is about to be
given context. It has a handful of facts about its own task - the paths it will
touch, the capability it needs, sometimes a capsule it was told to read - and
from those it must end up with the two or three capsules that matter and none
of the forty that do not.

## It returns references, not bodies

`CapsuleSelection.refs()` hands back `ContextRef` objects pointing at capsule
ids. Expanding a capsule into a manifest is a second, explicit step, and
`knowledge_refs()` is a third: a task that needs the decision behind a boundary
asks for it, and a task that does not never pays for it. Anything else and the
selector becomes the bloat it was written to prevent.

## Filters and signals are different things

`types` and `owner` are *filters*: a capsule that fails them is out, whatever
else matches. `paths`, `capabilities` and `capsule_ids` are *signals*: they
score, and a capsule that matches nothing scores zero and is not selected.
Keeping the two apart is what makes an empty result legible - the rejection
list says which of the two happened, per capsule.

## Determinism, and why the score is coarse

Ranking is `(-score, id)`, and the score is a small integer sum of matched
signals: an explicit id is worth more than any number of incidental tag hits,
and every other signal is worth the same as every other. A finer weighting
would be a guess about relevance dressed up as arithmetic, and nobody could
reproduce it by hand from the query. This one anybody can.

## The budget is a real refusal

`max_capsules` truncates the ranked list, and the capsules that fall off appear
in `rejected` marked `by_budget`. That count is the honest measure of whether
the query was too broad, and it is reported rather than silently applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ai_platform.context_manifest import ContextKind, ContextRef
from knowledge.company_os.capsules.budget import DEFAULT_BUDGET
from knowledge.company_os.capsules.capsule import Capsule, CapsuleType
from knowledge.company_os.capsules.index import CapsuleIndex, path_related

# An explicit id outranks any accumulation of incidental matches.
_SCORE_EXPLICIT_ID = 100
_SCORE_SIGNAL = 10
# Pulled in only because something selected depends on it.
_SCORE_DEPENDENCY = 1

# A knowledge record kind -> the manifest group it belongs in. Both learning
# kinds map to EXPERIMENT: `ContextKind` is a shared contract in `ai_platform`,
# and widening it for one caller would be the wrong direction of change.
_KNOWLEDGE_KINDS: dict[str, ContextKind] = {
    "fact": ContextKind.FACT,
    "decision": ContextKind.DECISION,
    "experiment_learning": ContextKind.EXPERIMENT,
    "failure_learning": ContextKind.EXPERIMENT,
}


@dataclass(frozen=True)
class TaskQuery:
    """What a task can say about itself without anybody reading its code."""

    paths: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    capsule_ids: tuple[str, ...] = ()
    types: tuple[CapsuleType, ...] = ()
    owner: str = ""
    include_dependencies: bool = True
    max_capsules: int = 6

    def __post_init__(self) -> None:
        if self.max_capsules < 1:
            raise ValueError(f"max_capsules must be at least 1, got {self.max_capsules}")

    def has_signal(self) -> bool:
        return bool(self.paths or self.capabilities or self.capsule_ids)


@dataclass(frozen=True)
class CapsuleMatch:
    """A selected capsule, its score, and the signals that earned it."""

    capsule: Capsule
    score: int
    reasons: tuple[str, ...]

    def reason_text(self) -> str:
        return "; ".join(self.reasons)


@dataclass(frozen=True)
class Rejection:
    """A capsule that was considered and left out, with which of the two reasons."""

    capsule_id: str
    reason: str
    by_budget: bool = False


@dataclass(frozen=True)
class SelectionMetrics:
    """Deterministic measurements of one selection. No provider token counts.

    `chars` is the summed canonical JSON of the selected capsules - reproducible
    from the files, comparable across sessions, and deliberately not called a
    token estimate, because it is not one.
    """

    capsules_considered: int
    capsules_selected: int
    capsules_rejected: int
    rejected_by_budget: int
    chars: int
    references: int
    duplicate_references: tuple[str, ...]
    knowledge_links: int


@dataclass(frozen=True)
class CapsuleSelection:
    """The result: what was chosen, what was not, and what it costs to send."""

    query: TaskQuery
    matches: tuple[CapsuleMatch, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    considered: int = 0

    @property
    def capsules(self) -> tuple[Capsule, ...]:
        return tuple(match.capsule for match in self.matches)

    def ids(self) -> tuple[str, ...]:
        return tuple(match.capsule.id for match in self.matches)

    def refs(self) -> tuple[ContextRef, ...]:
        """The selection as manifest references - ids, never expanded capsules.

        `MODULE_CONTRACT` is the right kind: the context policy in
        `ai_platform/README.md` asks a request to carry the relevant module
        contract, and a capsule is exactly that, written down.
        """
        return tuple(
            ContextRef(
                kind=ContextKind.MODULE_CONTRACT,
                ref=f"capsule:{match.capsule.id}",
                reason=match.reason_text(),
            )
            for match in self.matches
        )

    def knowledge_refs(self) -> tuple[ContextRef, ...]:
        """The linked facts, decisions and learnings - only when asked for.

        De-duplicated across capsules, in selection order, because two capsules
        citing one decision is one decision (constitution rule 15).
        """
        out: list[ContextRef] = []
        seen: set[str] = set()
        for match in self.matches:
            for record_kind, record_id in match.capsule.knowledge_links():
                ref = f"{record_kind}:{record_id}"
                if ref in seen:
                    continue
                seen.add(ref)
                out.append(
                    ContextRef(
                        kind=_KNOWLEDGE_KINDS[record_kind],
                        ref=ref,
                        reason=f"linked by capsule {match.capsule.id}",
                    )
                )
        return tuple(out)

    def test_refs(self) -> tuple[ContextRef, ...]:
        """The tests that cover the selected boundaries, de-duplicated."""
        out: list[ContextRef] = []
        seen: set[str] = set()
        for match in self.matches:
            for kind, refs in (
                (ContextKind.TEST, match.capsule.tests),
                (ContextKind.BENCHMARK, match.capsule.benchmarks),
            ):
                for ref in refs:
                    if ref in seen:
                        continue
                    seen.add(ref)
                    out.append(
                        ContextRef(
                            kind=kind, ref=ref, reason=f"covers capsule {match.capsule.id}"
                        )
                    )
        return tuple(out)

    def metrics(self) -> SelectionMetrics:
        counts: dict[str, int] = {}
        for capsule in self.capsules:
            for ref in capsule.references():
                counts[ref] = counts.get(ref, 0) + 1
        return SelectionMetrics(
            capsules_considered=self.considered,
            capsules_selected=len(self.matches),
            capsules_rejected=len(self.rejected),
            rejected_by_budget=sum(1 for r in self.rejected if r.by_budget),
            chars=sum(capsule.size_chars() for capsule in self.capsules),
            references=sum(len(capsule.references()) for capsule in self.capsules),
            duplicate_references=tuple(
                sorted(ref for ref, count in counts.items() if count > 1)
            ),
            knowledge_links=len(self.knowledge_refs()),
        )


def select_capsules(index: CapsuleIndex, query: TaskQuery) -> CapsuleSelection:
    """Rank the index against `query` and cut it to the capsule budget.

    Three passes, in order: filter by type and owner, score the survivors
    against the query signals, then pull in the dependency closure of whatever
    scored. Ranking is `(-score, id)` throughout, so the result is the same on
    any machine on any day.
    """
    rejected: list[Rejection] = []
    scored: dict[str, CapsuleMatch] = {}
    considered = len(index)

    allowed = {c.id: c for c in index.all() if _passes_filters(c, query, rejected)}

    for capsule in allowed.values():
        score, reasons = _score(capsule, query)
        if score:
            scored[capsule.id] = CapsuleMatch(capsule, score, tuple(reasons))
        else:
            rejected.append(
                Rejection(capsule.id, "no query signal matched its paths, tags or id")
            )

    if query.include_dependencies:
        for capsule_id in sorted(scored):
            for dependency in index.dependency_closure(capsule_id):
                if dependency in scored or dependency not in allowed:
                    continue
                scored[dependency] = CapsuleMatch(
                    allowed[dependency],
                    _SCORE_DEPENDENCY,
                    (f"dependency of {capsule_id}",),
                )
                rejected = [r for r in rejected if r.capsule_id != dependency]

    ranked = sorted(scored.values(), key=lambda m: (-m.score, m.capsule.id))
    kept, overflow = ranked[: query.max_capsules], ranked[query.max_capsules :]
    for match in overflow:
        rejected.append(
            Rejection(
                match.capsule.id,
                f"context budget: max_capsules={query.max_capsules} already met",
                by_budget=True,
            )
        )

    return CapsuleSelection(
        query=query,
        matches=tuple(kept),
        rejected=tuple(sorted(rejected, key=lambda r: (r.by_budget, r.capsule_id))),
        considered=considered,
    )


def _passes_filters(capsule: Capsule, query: TaskQuery, rejected: list[Rejection]) -> bool:
    if query.types and capsule.type not in query.types:
        wanted = "/".join(sorted(t.value for t in query.types))
        rejected.append(Rejection(capsule.id, f"type {capsule.type.value} is not {wanted}"))
        return False
    if query.owner and capsule.owner != query.owner:
        rejected.append(Rejection(capsule.id, f"owner {capsule.owner!r} is not {query.owner!r}"))
        return False
    return True


def _score(capsule: Capsule, query: TaskQuery) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if capsule.id in query.capsule_ids:
        score += _SCORE_EXPLICIT_ID
        reasons.append("requested by id")

    for path in query.paths:
        owned = [p for p in capsule.owns_paths if path_related(p, path)]
        if owned:
            score += _SCORE_SIGNAL
            reasons.append(f"owns {owned[0]} for task path {path}")

    for tag in query.capabilities:
        if tag in capsule.capabilities:
            score += _SCORE_SIGNAL
            reasons.append(f"capability {tag}")

    return score, reasons


def refs_for_task(
    index: CapsuleIndex,
    paths: Iterable[str] = (),
    capabilities: Iterable[str] = (),
    max_capsules: int = 6,
) -> tuple[ContextRef, ...]:
    """The one-line form: task metadata in, manifest references out.

    Exists so the common case - "I am touching these paths and need this
    capability" - is one call and cannot accidentally expand anything.
    """
    query = TaskQuery(
        paths=tuple(paths), capabilities=tuple(capabilities), max_capsules=max_capsules
    )
    return select_capsules(index, query).refs()


# Re-exported so callers tuning `max_capsules` can see the per-capsule ceiling
# it multiplies against without importing two modules.
MAX_CAPSULE_CHARS = DEFAULT_BUDGET.max_capsule_chars

__all__ = [
    "MAX_CAPSULE_CHARS",
    "CapsuleMatch",
    "CapsuleSelection",
    "Rejection",
    "SelectionMetrics",
    "TaskQuery",
    "refs_for_task",
    "select_capsules",
]
