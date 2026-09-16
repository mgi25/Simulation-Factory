"""The cross-record checks no single record can run on itself.

## Why these are separate from the constructors

Every record in this package validates itself at construction, and that catches
the failures visible from inside one record: a learning with no evidence, a rate
with no denominator, a causal claim from an observational design.

What a record cannot see is the rest of the store. An observation cannot know
that another observation claims a different value for the same metric at the
same instant. A learning cannot know that the result it cites is not there. A
postmortem cannot know that its hypothesis was never created. Those are the
checks here, and they run over a whole store.

## Section 24, as a list of functions

The brief's learning-quality list is eight items. Five are enforced at
construction and are listed in `CONSTRUCTION_ENFORCED` below with the type that
raises, so a reader can find them; the remaining three need the store, and are
`_dangling_references`, `_contradictory_observations` and
`_unsupported_promotions`.

Keeping the enforced list in code rather than in a comment means the suite can
assert it: if somebody relaxes a constructor, the test that walks this table
fails rather than the guarantee quietly disappearing.

## Problems are strings, sorted, and reported together

Same contract as `company/org_intelligence/integrity.py` and
`company/finance/integrity.py`: `check_integrity` returns every problem it can
prove, sorted, and `assert_integrity` raises one error carrying all of them. A
caller fixing data wants the whole list, not the first item eleven times.
"""

from __future__ import annotations

from collections import defaultdict
from .errors import (
    AnalyticsIntegrityError,
    EvidenceRequired,
    LedgerViolation,
    OverclaimRefused,
    ProvenanceViolation,
)
from .learning import HypothesisState
from .observations import MetricObservation
from .results import Verdict
from .store import AnalyticsStore

# The section 24 items enforced at construction, with what raises them. Asserted
# by the suite, so relaxing a constructor breaks a test rather than a promise.
CONSTRUCTION_ENFORCED: tuple[tuple[str, type[Exception]], ...] = (
    ("learning with no evidence", EvidenceRequired),
    ("learning from one observation claiming universality", OverclaimRefused),
    ("causal claim from a non-controlled comparison", OverclaimRefused),
    ("hypothesis promoted without experiment evidence", OverclaimRefused),
    ("private metric on a source that cannot observe it", ProvenanceViolation),
    ("overwritten historical observation", LedgerViolation),
)


def check_integrity(store: AnalyticsStore) -> tuple[str, ...]:
    """Every cross-record violation the store can prove, sorted."""
    problems: list[str] = []
    problems.extend(_dangling_references(store))
    problems.extend(_contradictory_observations(store))
    problems.extend(_unsupported_promotions(store))
    problems.extend(_orphaned_deliverables(store))
    return tuple(sorted(problems))


def assert_integrity(store: AnalyticsStore) -> None:
    """Raise one error carrying every problem, or return cleanly."""
    problems = check_integrity(store)
    if problems:
        raise AnalyticsIntegrityError(
            f"{len(problems)} analytics integrity problem(s):\n  "
            + "\n  ".join(problems)
        )


def _dangling_references(store: AnalyticsStore) -> list[str]:
    """A record citing an id that is not in the store.

    A learning whose result id does not resolve is a learning whose evidence
    cannot be checked, which is the same as a learning with no evidence - it
    just takes two records to see it.
    """
    out: list[str] = []
    known = {kind: set(store.ids(kind)) for kind in
             ("observation", "result", "experiment", "learning", "hypothesis",
              "postmortem", "deliverable")}

    for result in store.list("result"):
        for observation_id in result.observation_ids:
            if observation_id not in known["observation"]:
                out.append(
                    f"result {result.result_id}: names observation "
                    f"{observation_id!r}, which is not in the store"
                )
        if result.experiment_id not in known["experiment"]:
            out.append(
                f"result {result.result_id}: names experiment "
                f"{result.experiment_id!r}, which is not in the store"
            )

    for learning in store.list("learning"):
        for field_name, kind in (
            ("observation_ids", "observation"),
            ("result_ids", "result"),
            ("postmortem_ids", "postmortem"),
        ):
            for record_id in getattr(learning, field_name):
                if record_id not in known[kind]:
                    out.append(
                        f"learning {learning.learning_id}: cites {kind} {record_id!r}, "
                        "which is not in the store, so the claim cannot be rechecked"
                    )
        if (
            learning.source_hypothesis_id
            and learning.source_hypothesis_id not in known["hypothesis"]
        ):
            out.append(
                f"learning {learning.learning_id}: names source hypothesis "
                f"{learning.source_hypothesis_id!r}, which is not in the store"
            )

    for postmortem in store.list("postmortem"):
        if postmortem.deliverable_id not in known["deliverable"]:
            out.append(
                f"postmortem {postmortem.postmortem_id}: is about deliverable "
                f"{postmortem.deliverable_id!r}, which is not in the store"
            )
        for result_id in postmortem.experiment_result_ids:
            if result_id not in known["result"]:
                out.append(
                    f"postmortem {postmortem.postmortem_id}: names result "
                    f"{result_id!r}, which is not in the store"
                )
        if (
            postmortem.durable_learning_id
            and postmortem.durable_learning_id not in known["learning"]
        ):
            out.append(
                f"postmortem {postmortem.postmortem_id}: names learning "
                f"{postmortem.durable_learning_id!r}, which is not in the store"
            )
        if (
            postmortem.next_hypothesis_id
            and postmortem.next_hypothesis_id not in known["hypothesis"]
        ):
            out.append(
                f"postmortem {postmortem.postmortem_id}: names hypothesis "
                f"{postmortem.next_hypothesis_id!r}, which is not in the store"
            )
    return out


def _contradictory_observations(store: AnalyticsStore) -> list[str]:
    """Two readings of the same thing at the same instant with different values.

    The store's append-only guard stops one observation id being rewritten. It
    cannot stop a second observation, under a new id, claiming a different
    number for the same metric of the same deliverable at the same moment. One
    of the two is wrong, and a silent disagreement is worse than either.
    """
    by_snapshot: dict[str, list[MetricObservation]] = defaultdict(list)
    for observation in store.list("observation"):
        by_snapshot[observation.snapshot_key].append(observation)

    out: list[str] = []
    for key, readings in sorted(by_snapshot.items()):
        values = {r.value for r in readings}
        if len(values) > 1:
            ids = ", ".join(sorted(r.observation_id for r in readings))
            out.append(
                f"{key}: {len(values)} different values recorded for the same metric at "
                f"the same instant ({ids}). One of these readings is wrong; a "
                "correction supersedes an earlier record rather than sitting beside it"
            )
    return out


def _unsupported_promotions(store: AnalyticsStore) -> list[str]:
    """A hypothesis marked supported by a result that did not support it.

    The constructor requires a result id; only the store can check what that
    result actually concluded.
    """
    out: list[str] = []
    results = {r.result_id: r for r in store.list("result")}
    for hypothesis in store.list("hypothesis"):
        if hypothesis.state is not HypothesisState.SUPPORTED:
            continue
        supporting = [
            results[rid]
            for rid in hypothesis.result_ids
            if rid in results and results[rid].verdict is Verdict.SUPPORTS_HYPOTHESIS
        ]
        if not supporting:
            cited = ", ".join(hypothesis.result_ids) or "none"
            out.append(
                f"hypothesis {hypothesis.hypothesis_id}: marked supported, but no "
                f"result it cites ({cited}) returned a supporting verdict"
            )
    return out


def _orphaned_deliverables(store: AnalyticsStore) -> list[str]:
    """An observation about a deliverable the store does not have.

    Not fatal in itself - readings sometimes land before the deliverable record
    does - but it means the reading has no publication instant behind it, so its
    age cannot be rechecked and it cannot enter a comparison.
    """
    known = set(store.ids("deliverable"))
    seen: set[str] = set()
    out: list[str] = []
    for observation in store.list("observation"):
        if observation.deliverable_id in known or observation.deliverable_id in seen:
            continue
        seen.add(observation.deliverable_id)
        out.append(
            f"observation {observation.observation_id}: is about deliverable "
            f"{observation.deliverable_id!r}, which is not in the store, so its age "
            "cannot be verified and it cannot enter a comparison"
        )
    return out
