"""Structured, explainable retrieval - and the discipline to say "no precedent".

No embedding, no text similarity, no learned score. A query is built from the
current work order's decision-time fields; a precedent matches on structure
the repository can prove; every match says why; and a query with nothing
sufficiently related abstains instead of returning the nearest bad match.

## The objective text is never read

Two objectives can share every word and touch unrelated subsystems, and the
repository's own history has objectives that are near-duplicates by design
(a matched benchmark re-runs one task under several strategies). Words are the
cheapest thing to match and the least evidence of relevance, so retrieval
reads none of them. It reads where the work was authorized to act and which
suites the contract asked for.

## Four signals, each a named set

| signal | what it is | computed from |
|---|---|---|
| `writable_targets` | files the precedent changed that this task may write | the precedent's observed changes, the task's write scope |
| `shared_tests` | required suites both work orders named | the two work orders |
| `import_links` | precedent changes one direct import away from this task's modules | P6B's current graph |
| `shared_capsules` | capsules governing both, under today's contracts | today's capsule store |

Capsules are recomputed at query time for both sides rather than read from
the episode. The episode's own capture-time anchors answer a different
question (has anything moved? see `repository.evaluate_validity`), and using
them to match would compare today's task against yesterday's contract.

## Gates before signals

A precedent is **incompatible** - never scored - when:

- its **risk** is lower than the task's. A precedent held to less scrutiny
  than this task needs is not evidence about how to do this task, and using
  it would be learning lowering a risk class by the back door. The rule is
  deliberately one-sided: a precedent that passed *more* scrutiny than the
  task needs is still evidence, and reusing it lowers nothing - the task
  keeps its own risk, its own review and its own gate;
- its **reasoning-class ceiling** differs;
- its **specialist domain** differs - security work is not precedent for
  routine work, nor the reverse.

`review_capability` is deliberately *not* a gate. The replay over this
repository's own history showed it splits every precedent at 2026-09-21:
before review separation every work order asked for `software_architecture`,
after it most ask for `code_review`. It records a policy change, not the
nature of the work; the part of it that is about the work - an architecture
domain - is already in `specialist_domain`. (First replay: 16 of 34
decisions abstained as incompatible, most on this field alone.)

## The support floor, and why it is a rule rather than a threshold

- an **accepted** precedent must share a governing capsule with the task *and*
  have changed at least one file the task may write now - a precedent whose
  every change is outside today's write scope did something this task is not
  authorized to repeat;
- a **correction** warning must share a governing capsule *and* either a
  writable target or a required suite.

A rule has no dial to tune until the replay looks good. Below the floor is
`no_match`, whatever else is shared.

## Ranking

Lexicographic, descending, on the four signal sizes in the order of the table,
then more recent settlement, then experience id ascending. Every component is
reported with its members, so a reader can check a ranking by hand, and the
final key makes two runs over one store order identically.

## Abstention

`status` is `abstain` whenever no accepted precedent survives, with the most
specific reason available: `no_history`, `experience_unavailable`, `no_match`,
`incompatible_only`, `stale_only`, `correction_only`. Correction warnings can
accompany an abstention - "nothing like this succeeded, and here is how
something like it failed" is a legitimate answer; "here is the nearest thing"
is not.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import datetime as dt
from pathlib import Path
from typing import Any

from knowledge.company_os.capsules import normalise_path

from .capture import GovernanceFacts, governance_facts, governed_class, verify_pointers
from .model import DecisionFeatures, ExperienceEpisode, PrecedentClass
from .repository import RepositoryView, Validity, ValidityReport, covers, evaluate_validity
from .store import ExperienceStore, StoreScan


MAX_PRECEDENTS = 3
MAX_WARNINGS = 3
MAX_HISTORICAL = 3

# The routing inputs a precedent must share with the task to be compared at all.
COMPATIBILITY_FIELDS: tuple[str, ...] = (
    "reasoning_class_ceiling",
    "specialist_domain",
)

# `ai_platform.resource_classes.Risk`, in ascending order. A precedent's risk
# must be at least the task's; an unknown value on either side is incompatible.
RISK_ORDER: tuple[str, ...] = ("low", "medium", "high", "critical")

ABSTENTION_CODES: tuple[str, ...] = (
    "no_history",
    "experience_unavailable",
    "no_match",
    "incompatible_only",
    "stale_only",
    "correction_only",
)


@dataclass(frozen=True)
class ExperienceQuery:
    """What the current task is, in decision-time terms only."""

    work_order_id: str
    attempt: int
    write_paths: tuple[str, ...]
    read_paths: tuple[str, ...]
    forbidden_read_paths: tuple[str, ...]
    required_tests: tuple[str, ...]
    risk: str
    reasoning_class_ceiling: str
    specialist_domain: str
    review_capability: str
    # Replay only: episodes settled on or after this day did not exist yet.
    decided_on: dt.date | None = None

    @classmethod
    def from_features(
        cls, work_order_id: str, features: DecisionFeatures, *, decided_on: dt.date | None = None
    ) -> "ExperienceQuery":
        return cls(
            work_order_id=work_order_id,
            attempt=features.attempt,
            write_paths=features.write_paths,
            read_paths=features.read_paths,
            forbidden_read_paths=features.forbidden_read_paths,
            required_tests=features.required_tests,
            risk=features.risk,
            reasoning_class_ceiling=features.reasoning_class_ceiling,
            specialist_domain=features.specialist_domain,
            review_capability=features.review_capability,
            decided_on=decided_on,
        )

    @classmethod
    def from_work_order(
        cls, order: Any, *, attempt: int = 1, decided_on: dt.date | None = None
    ) -> "ExperienceQuery":
        from .model import decision_features

        return cls.from_features(
            order.work_order_id, decision_features(order, attempt=attempt), decided_on=decided_on
        )


@dataclass(frozen=True)
class MatchSignals:
    writable_targets: tuple[str, ...] = ()
    shared_tests: tuple[str, ...] = ()
    import_links: tuple[str, ...] = ()
    shared_capsules: tuple[str, ...] = ()

    def explain(self) -> tuple[str, ...]:
        out = []
        if self.writable_targets:
            out.append(
                f"{len(self.writable_targets)} changed file(s) inside this task's write scope: "
                + ", ".join(self.writable_targets[:4])
            )
        if self.shared_tests:
            out.append(f"shares {len(self.shared_tests)} required suite(s): " + ", ".join(self.shared_tests[:3]))
        if self.import_links:
            out.append(
                f"{len(self.import_links)} change(s) one import away from this task's modules: "
                + ", ".join(self.import_links[:3])
            )
        if self.shared_capsules:
            out.append("governed by the same capsule(s): " + ", ".join(self.shared_capsules[:3]))
        return tuple(out)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "writable_targets": list(self.writable_targets),
            "shared_tests": list(self.shared_tests),
            "import_links": list(self.import_links),
            "shared_capsules": list(self.shared_capsules),
        }


@dataclass(frozen=True)
class Candidate:
    """One episode, judged against one query. Every verdict carries its reason."""

    episode: ExperienceEpisode
    precedent_class: PrecedentClass
    governance: tuple[str, ...]
    validity: ValidityReport
    signals: MatchSignals
    incompatible: tuple[str, ...]
    above_floor: bool

    @property
    def experience_id(self) -> str:
        return self.episode.experience_id

    def rank_key(self) -> tuple[Any, ...]:
        s = self.signals
        return (
            -len(s.writable_targets),
            -len(s.shared_tests),
            -len(s.import_links),
            -len(s.shared_capsules),
            -self.episode.settled_on.toordinal(),
            self.episode.experience_id,
        )

    def why(self) -> tuple[str, ...]:
        return self.signals.explain() + (f"settled {self.episode.settled_on.isoformat()}",)


@dataclass(frozen=True)
class RetrievalResult:
    status: str
    abstention: str
    detail: str
    precedents: tuple[Candidate, ...]
    warnings: tuple[Candidate, ...]
    historical: tuple[Candidate, ...]
    episodes_in_store: int
    considered: int
    excluded: Mapping[str, int] = field(default_factory=dict)
    store_problems: tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return self.status == "precedent"


# --- signals -------------------------------------------------------------------


def _in_scope(path: str, rules: Sequence[str]) -> bool:
    return any(covers(rule, path) or covers(path, rule) for rule in rules)


def incompatibilities(query: ExperienceQuery, features: DecisionFeatures) -> tuple[str, ...]:
    out = []
    if features.risk not in RISK_ORDER or query.risk not in RISK_ORDER:
        out.append(f"risk: precedent {features.risk or 'none'}, task {query.risk or 'none'} (unknown)")
    elif RISK_ORDER.index(features.risk) < RISK_ORDER.index(query.risk):
        out.append(f"risk: precedent {features.risk} is below task {query.risk}")
    for name in COMPATIBILITY_FIELDS:
        theirs, ours = getattr(features, name), getattr(query, name)
        if theirs != ours:
            out.append(f"{name}: precedent {theirs or 'none'!s}, task {ours or 'none'!s}")
    return tuple(out)


def structural_signals(query: ExperienceQuery, episode: ExperienceEpisode, view: RepositoryView) -> MatchSignals:
    """Every signal except the import graph, which is only paid for when needed."""
    targets = tuple(normalise_path(p) for p in episode.targets())
    writable = tuple(sorted(p for p in targets if _in_scope(p, query.write_paths)))
    tests = tuple(sorted(set(normalise_path(t) for t in query.required_tests) & set(normalise_path(t) for t in episode.features.required_tests)))
    ours = set(view.governing_all(query.write_paths))
    theirs = set(view.governing_all(targets))
    return MatchSignals(writable_targets=writable, shared_tests=tests, shared_capsules=tuple(sorted(ours & theirs)))


def task_modules(query: ExperienceQuery, view: RepositoryView) -> tuple[str, ...]:
    """The modules this task acts on: its writable modules, and what its writable tests import.

    A task whose whole write scope is a test file is about the modules that
    test imports, so those are its modules for every graph question.
    """
    graph = view.graph
    if graph is None:
        return ()
    modules: set[str] = set()
    for rule in query.write_paths:
        for module in view.modules_under(rule):
            if graph.is_test(module):
                modules.update(m for m in graph.direct_dependencies(module) if not graph.is_test(m))
            else:
                modules.add(module)
    return tuple(sorted(modules))


def import_links(
    query: ExperienceQuery, episode: ExperienceEpisode, view: RepositoryView, modules: Sequence[str]
) -> tuple[str, ...]:
    graph = view.graph
    if graph is None or not modules:
        return ()
    neighbourhood: set[str] = set()
    for module in modules:
        neighbourhood.update(graph.direct_dependencies(module))
        neighbourhood.update(graph.direct_dependents(module))
    return tuple(
        sorted(
            p
            for p in (normalise_path(t) for t in episode.targets())
            if p in neighbourhood and not _in_scope(p, query.write_paths)
        )
    )


def _above_floor(klass: PrecedentClass, signals: MatchSignals) -> bool:
    if not signals.shared_capsules:
        return False
    if klass is PrecedentClass.ACCEPTED:
        return bool(signals.writable_targets)
    return bool(signals.writable_targets or signals.shared_tests)


# --- retrieval -------------------------------------------------------------------


def retrieve(
    query: ExperienceQuery,
    view: RepositoryView,
    *,
    scan: StoreScan,
    resolve_source: Callable[[str], Path | None],
) -> RetrievalResult:
    """Judge every episode against the query and keep only what earns its place."""
    if not scan.available:
        return _abstain("experience_unavailable", "; ".join(scan.problems[:2]) or "the experience store is unreadable", scan)
    if not scan.episodes:
        return _abstain("no_history", "the experience store holds no episodes", scan)

    excluded: dict[str, int] = {}

    def skip(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    judged: list[Candidate] = []
    for episode in scan.episodes:
        if query.decided_on is not None and not episode.settled_on < query.decided_on:
            skip("not_yet_settled")
            continue
        if episode.work_order_id == query.work_order_id:
            skip("same_work_order")
            continue
        klass_base = episode.engineering_class()
        if klass_base is PrecedentClass.INCOMPLETE:
            skip("incomplete")
            continue
        signals = structural_signals(query, episode, view)
        klass, governance = klass_base, ()
        if klass_base is PrecedentClass.ACCEPTED:
            facts = _facts(episode, resolve_source, query.decided_on)
            if not facts.available:
                skip("unresolved")
                continue
            klass, governance = governed_class(episode, facts)
        if not _above_floor(klass, signals):
            skip("below_floor")
            continue
        incompatible = incompatibilities(query, episode.features)
        source_dir = resolve_source(episode.source)
        pointer_problems = (
            verify_pointers(episode, source_dir) if source_dir is not None else (f"source {episode.source!r} is not resolvable",)
        )
        validity = evaluate_validity(episode, view, pointer_problems=pointer_problems)
        judged.append(
            Candidate(
                episode=episode,
                precedent_class=klass,
                governance=governance,
                validity=validity,
                signals=signals,
                incompatible=incompatible,
                above_floor=True,
            )
        )

    compatible = [c for c in judged if not c.incompatible]
    for candidate in judged:
        if candidate.incompatible:
            skip("incompatible")
    current = [c for c in compatible if c.validity.status is Validity.CURRENT]
    for candidate in compatible:
        if candidate.validity.status is Validity.STALE:
            skip("stale")
        elif candidate.validity.status is Validity.INVALID:
            skip("invalid")

    accepted = [c for c in current if c.precedent_class is PrecedentClass.ACCEPTED]
    corrections = [c for c in current if c.precedent_class is PrecedentClass.CORRECTION]
    if accepted or corrections:
        modules = task_modules(query, view)
        accepted = [_with_links(c, query, view, modules) for c in accepted]
        corrections = [_with_links(c, query, view, modules) for c in corrections]
    accepted.sort(key=Candidate.rank_key)
    corrections.sort(key=Candidate.rank_key)
    historical = sorted(
        (c for c in compatible if c.validity.status is not Validity.CURRENT),
        key=Candidate.rank_key,
    )[:MAX_HISTORICAL]

    common = dict(
        warnings=tuple(corrections[:MAX_WARNINGS]),
        historical=tuple(historical),
        episodes_in_store=len(scan.episodes),
        considered=len(judged),
        excluded=dict(sorted(excluded.items())),
        store_problems=scan.problems,
    )
    if accepted:
        return RetrievalResult(
            status="precedent", abstention="", detail="", precedents=tuple(accepted[:MAX_PRECEDENTS]), **common
        )
    if corrections:
        code, detail = "correction_only", "similar work exists only as corrections; they are warnings, not precedent"
    elif any(c.validity.status is not Validity.CURRENT for c in compatible):
        code, detail = "stale_only", "every related precedent is stale or unresolved against the current repository"
    elif judged:
        code, detail = "incompatible_only", "related precedents differ from this task in " + "; ".join(
            sorted({reason.split(":", 1)[0] for c in judged for reason in c.incompatible})
        )
    else:
        code, detail = "no_match", "no episode shares both a governing capsule and a writable target or required suite"
    return RetrievalResult(status="abstain", abstention=code, detail=detail, precedents=(), **common)


def _facts(episode: ExperienceEpisode, resolve_source: Callable[[str], Path | None], before: dt.date | None) -> GovernanceFacts:
    source_dir = resolve_source(episode.source)
    if source_dir is None:
        return GovernanceFacts(available=False, problem=f"source {episode.source!r} is not resolvable")
    return governance_facts(source_dir, episode, before=before)


def _with_links(candidate: Candidate, query: ExperienceQuery, view: RepositoryView, modules: Sequence[str]) -> Candidate:
    links = import_links(query, candidate.episode, view, modules)
    if not links:
        return candidate
    s = candidate.signals
    return Candidate(
        episode=candidate.episode,
        precedent_class=candidate.precedent_class,
        governance=candidate.governance,
        validity=candidate.validity,
        signals=MatchSignals(
            writable_targets=s.writable_targets,
            shared_tests=s.shared_tests,
            import_links=links,
            shared_capsules=s.shared_capsules,
        ),
        incompatible=candidate.incompatible,
        above_floor=candidate.above_floor,
    )


def _abstain(code: str, detail: str, scan: StoreScan) -> RetrievalResult:
    return RetrievalResult(
        status="abstain",
        abstention=code,
        detail=detail,
        precedents=(),
        warnings=(),
        historical=(),
        episodes_in_store=len(scan.episodes),
        considered=0,
        excluded={},
        store_problems=scan.problems,
    )


def retrieve_from(
    query: ExperienceQuery,
    view: RepositoryView,
    store: ExperienceStore,
    *,
    sources: Mapping[str, Path] | None = None,
) -> RetrievalResult:
    """Convenience: scan a store whose episodes resolve in its own state directory."""
    mapping = dict(sources or {"local": store.state_dir})
    return retrieve(query, view, scan=store.scan(), resolve_source=lambda label: mapping.get(label))


__all__ = [
    "ABSTENTION_CODES",
    "COMPATIBILITY_FIELDS",
    "RISK_ORDER",
    "Candidate",
    "ExperienceQuery",
    "MatchSignals",
    "RetrievalResult",
    "import_links",
    "incompatibilities",
    "retrieve",
    "retrieve_from",
    "structural_signals",
    "task_modules",
]
