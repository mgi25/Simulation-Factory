"""One page for whoever has to decide what to make next.

## Seven questions, and nothing else

Section 26 lists them: what was measured, what changed, which experiments are
running, which finished, what we learned, what is still uncertain, what to test
next. The report answers exactly those and stops.

The discipline is in what it refuses. No raw observation dump - a CEO reading
four hundred readings is doing the analysis themselves, which is the job this
layer was built to do for them. So the measurement section reports counts and
coverage: how many deliverables, how many readings, which metrics, how many
deliverables are missing each one.

## No content score, and the absence is load-bearing

There is no overall number. Not for a video, not for a format, not for the
channel. Constitution rule 3 and section 26 both forbid it, and the reason is
that the company's actual objective - long-term profitable audience growth - is
not one number, so any single number here would be optimised in its place.

The suite asserts the absence by walking every field of every record in this
package for score-shaped names. That is a blunt instrument and it is the right
one: the failure mode is somebody adding a helpful `performance_index` in six
months, and a test that only checks today's fields would not catch it.

## Uncertainty is a section, not a footnote

`open_questions` and `not_concluded` are first-class output. A report that lists
five learnings and says nothing about what remains unknown reads as a state of
knowledge rather than a snapshot of an ongoing investigation. Sections 8 and 9
push the same way: an inconclusive experiment is a real outcome, and it belongs
on the page with the conclusive ones.

## Deterministic

Same store, same report, byte for byte. Everything is sorted by id, nothing
reads the clock - `as_of` is supplied by the caller - and every list has a
declared cap with the overflow reported as a count rather than truncated in
silence.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable

from .common import assert_day
from .experiments import ExperimentSpecification, ExperimentStatus
from .learning import AnalyticsHypothesis, HypothesisState
from .observations import MetricObservation
from .postmortem import DeliverablePostmortem
from .results import ExperimentResult
from .store import AnalyticsStore

# How many items of each kind reach the page. Beyond this the report says how
# many more there are rather than printing them; a list nobody reads to the end
# is a dump with a heading.
MAX_ITEMS = 8


@dataclass(frozen=True)
class MeasurementCoverage:
    """One metric: how many deliverables carry it, and how many do not."""

    metric: str
    observation_count: int
    deliverables_measured: int
    deliverables_missing: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observation_count": self.observation_count,
            "deliverables_measured": self.deliverables_measured,
            "deliverables_missing": list(self.deliverables_missing[:MAX_ITEMS]),
            "deliverables_missing_count": len(self.deliverables_missing),
        }


@dataclass(frozen=True)
class AnalyticsReport:
    """What was measured, what it suggests, and what it does not establish."""

    as_of: dt.date
    deliverable_count: int
    observation_count: int
    coverage: tuple[MeasurementCoverage, ...]
    variables_changed: tuple[str, ...]
    active_experiments: tuple[str, ...]
    completed_results: tuple[str, ...]
    learnings: tuple[str, ...]
    open_questions: tuple[str, ...]
    not_concluded: tuple[str, ...]
    next_to_test: tuple[str, ...]
    integrity_problems: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", assert_day(self.as_of, "as_of"))

    def to_dict(self) -> dict[str, Any]:
        """The serialised page. Lists capped, overflow reported as a count."""
        return {
            "as_of": self.as_of.isoformat(),
            "measured": {
                "deliverables": self.deliverable_count,
                "observations": self.observation_count,
                "metrics": [c.to_dict() for c in self.coverage],
            },
            "what_changed": _capped(self.variables_changed),
            "experiments_active": _capped(self.active_experiments),
            "experiments_completed": _capped(self.completed_results),
            "learned": _capped(self.learnings),
            "still_uncertain": _capped(self.open_questions),
            "not_concluded": _capped(self.not_concluded),
            "test_next": _capped(self.next_to_test),
            "integrity_problems": _capped(self.integrity_problems),
        }

    def render(self) -> str:
        """The same page as text, for a terminal. Deterministic."""
        lines = [f"Analytics report as of {self.as_of.isoformat()}", ""]
        lines.append(
            f"Measured: {self.deliverable_count} deliverable(s), "
            f"{self.observation_count} observation(s), {len(self.coverage)} metric(s)"
        )
        for entry in self.coverage[:MAX_ITEMS]:
            missing = (
                f", {len(entry.deliverables_missing)} without it"
                if entry.deliverables_missing
                else ""
            )
            lines.append(
                f"  {entry.metric}: {entry.observation_count} reading(s) across "
                f"{entry.deliverables_measured} deliverable(s){missing}"
            )
        for heading, items in (
            ("What changed", self.variables_changed),
            ("Experiments running", self.active_experiments),
            ("Experiments completed", self.completed_results),
            ("Learned", self.learnings),
            ("Still uncertain", self.open_questions),
            ("Not concluded", self.not_concluded),
            ("Test next", self.next_to_test),
            ("Integrity problems", self.integrity_problems),
        ):
            if not items:
                continue
            lines.extend(["", f"{heading}:"])
            for item in items[:MAX_ITEMS]:
                lines.append(f"  - {item}")
            if len(items) > MAX_ITEMS:
                lines.append(f"  ... and {len(items) - MAX_ITEMS} more")
        return "\n".join(lines)


def build_report(
    store: AnalyticsStore,
    as_of: Any,
    *,
    integrity_problems: Iterable[str] = (),
) -> AnalyticsReport:
    """Assemble the page from a store. Deterministic, and it reads no clock."""
    deliverables = store.list("deliverable")
    observations = store.list("observation")
    experiments = store.list("experiment")
    results = store.list("result")
    postmortems = store.list("postmortem")
    learnings = store.list("learning")
    hypotheses = store.list("hypothesis")

    return AnalyticsReport(
        as_of=assert_day(as_of, "as_of"),
        deliverable_count=len(deliverables),
        observation_count=len(observations),
        coverage=_coverage(deliverables, observations),
        variables_changed=_variables_changed(experiments),
        active_experiments=_active(experiments),
        completed_results=tuple(
            r.summary_line() for r in sorted(results, key=lambda r: r.result_id)
        ),
        learnings=tuple(
            l.qualified_statement for l in sorted(learnings, key=lambda l: l.learning_id)
        ),
        open_questions=_open_questions(postmortems, hypotheses),
        not_concluded=_not_concluded(results),
        next_to_test=_next_to_test(hypotheses),
        integrity_problems=tuple(integrity_problems),
    )


def _coverage(
    deliverables: tuple[Any, ...], observations: tuple[MetricObservation, ...]
) -> tuple[MeasurementCoverage, ...]:
    all_ids = {d.deliverable_id for d in deliverables}
    by_metric: dict[str, list[MetricObservation]] = {}
    for observation in observations:
        by_metric.setdefault(observation.metric.name, []).append(observation)

    out: list[MeasurementCoverage] = []
    for metric in sorted(by_metric):
        readings = by_metric[metric]
        measured = {o.deliverable_id for o in readings}
        out.append(
            MeasurementCoverage(
                metric=metric,
                observation_count=len(readings),
                deliverables_measured=len(measured),
                deliverables_missing=tuple(sorted(all_ids - measured)),
            )
        )
    return tuple(out)


def _variables_changed(experiments: tuple[ExperimentSpecification, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for specification in sorted(experiments, key=lambda e: e.experiment_id):
        for variable in specification.variables_changed:
            confounded = " (confounded)" if specification.confounded else ""
            out.append(
                f"{specification.experiment_id}: {variable.dimension}"
                f"{confounded} - {variable.description}"
            )
    return tuple(out)


def _active(experiments: tuple[ExperimentSpecification, ...]) -> tuple[str, ...]:
    running = (ExperimentStatus.RUNNING, ExperimentStatus.OBSERVING)
    return tuple(
        f"{e.experiment_id} ({e.status.value}, {e.observation_window.label}): {e.hypothesis}"
        for e in sorted(experiments, key=lambda e: e.experiment_id)
        if e.status in running
    )


def _not_concluded(results: tuple[ExperimentResult, ...]) -> tuple[str, ...]:
    """Experiments that did not conclude, and every unavailable causal claim.

    Both belong on the page. An inconclusive experiment is a real outcome, and a
    supported hypothesis that still cannot claim causation is the most common
    thing a reader gets wrong.
    """
    out: list[str] = []
    for result in sorted(results, key=lambda r: r.result_id):
        if not result.verdict.is_conclusive:
            out.append(
                f"{result.experiment_id}: {result.verdict.value} - "
                + (result.causal.blockers[0] if result.causal.blockers else result.interpretation)
            )
        elif not result.causal_claim_supported:
            out.append(
                f"{result.experiment_id}: {result.verdict.value}, but no causal claim - "
                + result.causal.blockers[0]
            )
    return tuple(out)


def _open_questions(
    postmortems: tuple[DeliverablePostmortem, ...],
    hypotheses: tuple[AnalyticsHypothesis, ...],
) -> tuple[str, ...]:
    out: list[str] = []
    for postmortem in sorted(postmortems, key=lambda p: p.postmortem_id):
        for question in postmortem.unresolved_questions:
            out.append(f"{postmortem.deliverable_id}: {question}")
    for hypothesis in sorted(hypotheses, key=lambda h: h.hypothesis_id):
        if hypothesis.state is HypothesisState.TESTING:
            out.append(f"{hypothesis.hypothesis_id} under test: {hypothesis.statement}")
    return tuple(out)


def _next_to_test(hypotheses: tuple[AnalyticsHypothesis, ...]) -> tuple[str, ...]:
    return tuple(
        f"{h.hypothesis_id}: {h.statement}"
        for h in sorted(hypotheses, key=lambda h: h.hypothesis_id)
        if h.state is HypothesisState.PROPOSED
    )


def _capped(items: tuple[str, ...]) -> dict[str, Any]:
    return {
        "items": list(items[:MAX_ITEMS]),
        "total": len(items),
        "omitted": max(0, len(items) - MAX_ITEMS),
    }
