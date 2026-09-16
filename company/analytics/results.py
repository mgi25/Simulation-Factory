"""What an experiment found, and - more carefully - what it is allowed to claim.

## The two questions, deliberately not merged

**Did the metric move the way we guessed?** That is `Verdict`, and it is
arithmetic: compare each primary metric's observed direction with its
expectation. A verdict is about our prediction.

**Did the change we made cause the movement?** That is `CausalAssessment`, and
it is almost never yes. A verdict is about our prediction; a causal claim is
about the world, and the world is not obliged to have held everything else still
while we changed a hook.

Merging them is the mistake this module exists to prevent, and it is an easy
mistake to make because `SUPPORTS_HYPOTHESIS` *reads* like a causal finding. It
is not one. An experiment can support its hypothesis and support no causal claim
at all, and that is the normal case for everything we publish.

## Why `causal_claim_supported` is computed and not stored

A boolean a caller sets is a boolean a caller sets to True. So it is a property
of `CausalAssessment`, derived from four conditions, and the reasons it is False
are the record's own content:

1. assignment was controlled - only `RANDOMIZED_SPLIT` (section 9);
2. exactly one variable changed - a confounded design attributes nothing;
3. the sample reached the minimum the specification set *beforehand*;
4. every primary metric actually compared - an unknown denominator or a window
   mismatch means the difference was never established in the first place.

All four, or `causal_claim_supported` is False and `blockers` says which failed.
There is no override parameter, no `force=`, and no way to construct a
`CausalAssessment` that claims causation from an observational comparison.

## Even when it is True the wording stays qualified

`statement` never produces "X caused Y". At best it produces "within this test,
the difference is attributable to the assigned variant", scoped to the audience,
the window and the period. Section 9 asks for that explicitly, and it is also
just true: a randomised split tells you about the split, on that channel, that
week.

## Insufficient evidence is a verdict, not a failure

`INSUFFICIENT_EVIDENCE` and `INCONCLUSIVE` are outcomes an experiment is allowed
to have, and they are forced rather than chosen: below the minimum sample no
other verdict can be returned, regardless of how clearly the numbers moved. This
is the guard against the single-video conclusion - one video beating another is
not a finding, and here it is not even a verdict.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_tag,
    evidence_tuple,
    record_to_dict,
    ref_tuple,
    text_tuple,
)
from .comparison import DeliverableComparison, MetricComparison
from .errors import AnalyticsError, EvidenceRequired, OverclaimRefused
from .experiments import (
    ComparisonBasis,
    Direction,
    Expectation,
    ExperimentSpecification,
    KillCondition,
)
from .references import ExecutionReference, FinanceReference, ResearchReference


class Verdict(Enum):
    """What the experiment says about its own hypothesis. Never about causation."""

    SUPPORTS_HYPOTHESIS = "supports_hypothesis"
    DOES_NOT_SUPPORT = "does_not_support"
    MIXED = "mixed"
    INCONCLUSIVE = "inconclusive"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

    @property
    def is_conclusive(self) -> bool:
        return self in (Verdict.SUPPORTS_HYPOTHESIS, Verdict.DOES_NOT_SUPPORT)


@dataclass(frozen=True)
class MetricOutcome:
    """One primary or guardrail metric: what it did against what we expected."""

    metric: str
    observed: Direction | None
    expected: Direction | None
    difference: float | None
    comparable: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", assert_tag(self.metric, "outcome metric"))
        object.__setattr__(self, "reasons", text_tuple(self.reasons, "outcome reasons"))

    @property
    def matched_expectation(self) -> bool | None:
        """True, False, or None when there is nothing to compare against."""
        if self.observed is None or self.expected is None or not self.comparable:
            return None
        return self.observed is self.expected

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observed": self.observed.value if self.observed else None,
            "expected": self.expected.value if self.expected else None,
            "difference": self.difference,
            "comparable": self.comparable,
            "matched_expectation": self.matched_expectation,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CausalAssessment:
    """Whether the design can attribute the difference to the change. Usually not.

    Constructed from the specification and the evidence, never from a caller's
    opinion. `causal_claim_supported` is a property; there is no field to set.
    """

    basis: ComparisonBasis
    sample_size: int
    minimum_sample: int
    changed_variable_count: int
    uncompared_primary_metrics: tuple[str, ...] = ()
    unresolved_confounders: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.basis, ComparisonBasis):
            raise AnalyticsError("causal assessment basis must be a ComparisonBasis")
        for name in ("sample_size", "minimum_sample", "changed_variable_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AnalyticsError(f"causal assessment {name} must be a non-negative integer")
        object.__setattr__(
            self,
            "uncompared_primary_metrics",
            tuple(sorted(self.uncompared_primary_metrics)),
        )
        object.__setattr__(
            self,
            "unresolved_confounders",
            text_tuple(self.unresolved_confounders, "unresolved_confounders"),
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        """Every reason a causal claim is unavailable, in a fixed order."""
        out: list[str] = []
        if not self.basis.controls_assignment:
            out.append(
                f"assignment was not controlled: a {self.basis.value} comparison "
                "observes two things that differ in the audience they reached, the "
                "week they reached it and what the platform was promoting, as well as "
                "in what we changed"
            )
        if self.changed_variable_count != 1:
            out.append(
                f"{self.changed_variable_count} variables changed; attribution to any "
                "one of them is unavailable"
                if self.changed_variable_count > 1
                else "no variable is recorded as changed, so there is nothing to attribute to"
            )
        if self.sample_size < self.minimum_sample:
            out.append(
                f"sample of {self.sample_size} is below the {self.minimum_sample} the "
                "specification required before the result was reviewed"
            )
        if self.uncompared_primary_metrics:
            out.append(
                "primary metric(s) never compared: "
                + ", ".join(self.uncompared_primary_metrics)
                + "; a difference that was not established cannot have a cause"
            )
        for confounder in self.unresolved_confounders:
            out.append(f"unresolved confounder: {confounder}")
        return tuple(out)

    @property
    def causal_claim_supported(self) -> bool:
        """False unless every blocker is cleared. There is no override."""
        return not self.blockers

    @property
    def association_statement(self) -> str:
        """What the evidence does support: an association, described as one."""
        return (
            "observed association only: the arms differ on the measured metrics over "
            "this window. Nothing here establishes what produced the difference"
        )

    @property
    def statement(self) -> str:
        """The strongest honest wording. Qualified even in the supported case."""
        if not self.causal_claim_supported:
            return self.association_statement
        return (
            "within this randomised split, the difference between arms is attributable "
            "to the assigned variant for this audience, this window and this period. "
            "It is not a general claim about the variable, and it does not transfer to "
            "another format, another channel or another season without retesting"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis.value,
            "sample_size": self.sample_size,
            "minimum_sample": self.minimum_sample,
            "changed_variable_count": self.changed_variable_count,
            "uncompared_primary_metrics": list(self.uncompared_primary_metrics),
            "unresolved_confounders": list(self.unresolved_confounders),
            "causal_claim_supported": self.causal_claim_supported,
            "blockers": list(self.blockers),
            "statement": self.statement,
        }


@dataclass(frozen=True)
class GuardrailOutcome:
    """A guardrail metric and whether a kill condition fired on it."""

    metric: str
    value: float | None
    breached: tuple[str, ...] = ()
    missing: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", assert_tag(self.metric, "guardrail metric"))
        object.__setattr__(self, "breached", text_tuple(self.breached, "breached"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "breached": list(self.breached),
            "missing": self.missing,
        }


@dataclass(frozen=True)
class ExperimentResult:
    """A qualified result: the verdict, the evidence, and what it cannot say."""

    result_id: str
    experiment_id: str
    verdict: Verdict
    causal: CausalAssessment
    primary_outcomes: tuple[MetricOutcome, ...]
    guardrail_outcomes: tuple[GuardrailOutcome, ...]
    observation_ids: tuple[str, ...]
    sample_size: int
    window_label: str
    interpretation: str
    reviewed_on: dt.date
    limitations: tuple[str, ...] = ()
    confounders: tuple[str, ...] = ()
    missing_measures: tuple[str, ...] = ()
    what_would_change_it: tuple[str, ...] = ()
    kill_conditions_triggered: tuple[str, ...] = ()
    finance_refs: tuple[FinanceReference, ...] = ()
    research_refs: tuple[ResearchReference, ...] = ()
    execution_refs: tuple[ExecutionReference, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", assert_record_id(self.result_id, "result_id"))
        object.__setattr__(
            self, "experiment_id", assert_record_id(self.experiment_id, "experiment_id")
        )
        if not isinstance(self.verdict, Verdict):
            raise AnalyticsError(f"verdict must be a Verdict, got {self.verdict!r}")
        if not isinstance(self.causal, CausalAssessment):
            raise AnalyticsError(
                "a result must carry a CausalAssessment; a verdict with no statement "
                "about attribution is a verdict that will be read as one"
            )
        object.__setattr__(
            self, "observation_ids", ref_tuple(self.observation_ids, "observation_ids",
                                               validator=assert_record_id)
        )
        if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int):
            raise AnalyticsError("sample_size must be an integer")
        object.__setattr__(
            self, "window_label", assert_tag(self.window_label, "window_label")
        )
        object.__setattr__(
            self, "interpretation", assert_prose(self.interpretation, "interpretation")
        )
        object.__setattr__(self, "reviewed_on", assert_day(self.reviewed_on, "reviewed_on"))
        for name in ("limitations", "confounders", "missing_measures",
                     "what_would_change_it", "kill_conditions_triggered"):
            object.__setattr__(self, name, text_tuple(getattr(self, name), name))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

        if not self.observation_ids:
            raise EvidenceRequired(
                f"{self.result_id}: a result must name the observations it was computed "
                "from. A verdict with no readings behind it is an impression"
            )
        if self.sample_size != len(set(self.observation_ids)):
            raise AnalyticsError(
                f"{self.result_id}: sample_size {self.sample_size} does not match the "
                f"{len(set(self.observation_ids))} distinct observations named. The "
                "sample is what was actually read, not what was hoped for"
            )
        if not self.what_would_change_it:
            raise AnalyticsError(
                f"{self.result_id}: a result must say what would change the conclusion. "
                "A finding with no falsifier is a belief, and the next session cannot "
                "tell whether new evidence bears on it"
            )
        if self.verdict.is_conclusive and self.sample_size < self.causal.minimum_sample:
            raise OverclaimRefused(
                f"{self.result_id}: verdict {self.verdict.value!r} from {self.sample_size} "
                f"observation(s) against a minimum of {self.causal.minimum_sample} set "
                "before review. Below the evidence condition the honest verdicts are "
                f"{Verdict.INSUFFICIENT_EVIDENCE.value!r} or "
                f"{Verdict.INCONCLUSIVE.value!r}"
            )
        if self.causal.causal_claim_supported and not self.causal.basis.controls_assignment:
            raise OverclaimRefused(  # pragma: no cover - CausalAssessment forbids it first
                f"{self.result_id}: causal claim without controlled assignment"
            )

    @property
    def causal_claim_supported(self) -> bool:
        """Convenience passthrough. False by default, and by design hard to flip."""
        return self.causal.causal_claim_supported

    @property
    def guardrails_breached(self) -> tuple[str, ...]:
        return tuple(
            statement for outcome in self.guardrail_outcomes for statement in outcome.breached
        )

    @property
    def all_caveats(self) -> tuple[str, ...]:
        """Everything a reader must carry away with the verdict."""
        return tuple(
            dict.fromkeys(
                (*self.causal.blockers, *self.confounders, *self.limitations,
                 *(f"not measured: {m}" for m in self.missing_measures))
            )
        )

    def summary_line(self) -> str:
        """One line for a report. Always names the attribution status."""
        claim = "causal claim supported" if self.causal_claim_supported else "association only"
        return (
            f"{self.experiment_id}: {self.verdict.value} over {self.sample_size} "
            f"observation(s) at {self.window_label} - {claim}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "experiment_id": self.experiment_id,
            "verdict": self.verdict.value,
            "causal": self.causal.to_dict(),
            "causal_claim_supported": self.causal_claim_supported,
            "primary_outcomes": [o.to_dict() for o in self.primary_outcomes],
            "guardrail_outcomes": [g.to_dict() for g in self.guardrail_outcomes],
            "observation_ids": list(self.observation_ids),
            "sample_size": self.sample_size,
            "window_label": self.window_label,
            "interpretation": self.interpretation,
            "reviewed_on": self.reviewed_on.isoformat(),
            "limitations": list(self.limitations),
            "confounders": list(self.confounders),
            "missing_measures": list(self.missing_measures),
            "what_would_change_it": list(self.what_would_change_it),
            "kill_conditions_triggered": list(self.kill_conditions_triggered),
            "finance_refs": [r.to_dict() for r in self.finance_refs],
            "research_refs": [r.to_dict() for r in self.research_refs],
            "execution_refs": [r.to_dict() for r in self.execution_refs],
            "evidence": [{"kind": e.kind, "ref": e.ref, "note": e.note} for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: Any) -> ExperimentResult:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a result object, got {data!r}")
        try:
            causal_data = data["causal"]
            causal = CausalAssessment(
                basis=ComparisonBasis(causal_data["basis"]),
                sample_size=causal_data["sample_size"],
                minimum_sample=causal_data["minimum_sample"],
                changed_variable_count=causal_data["changed_variable_count"],
                uncompared_primary_metrics=tuple(
                    causal_data.get("uncompared_primary_metrics") or ()
                ),
                unresolved_confounders=tuple(causal_data.get("unresolved_confounders") or ()),
            )
            return cls(
                result_id=data["result_id"],
                experiment_id=data["experiment_id"],
                verdict=Verdict(data["verdict"]),
                causal=causal,
                primary_outcomes=tuple(
                    MetricOutcome(
                        metric=o["metric"],
                        observed=Direction(o["observed"]) if o.get("observed") else None,
                        expected=Direction(o["expected"]) if o.get("expected") else None,
                        difference=o.get("difference"),
                        comparable=bool(o.get("comparable", False)),
                        reasons=tuple(o.get("reasons") or ()),
                    )
                    for o in data.get("primary_outcomes") or ()
                ),
                guardrail_outcomes=tuple(
                    GuardrailOutcome(
                        metric=g["metric"],
                        value=g.get("value"),
                        breached=tuple(g.get("breached") or ()),
                        missing=bool(g.get("missing", False)),
                    )
                    for g in data.get("guardrail_outcomes") or ()
                ),
                observation_ids=tuple(data["observation_ids"]),
                sample_size=data["sample_size"],
                window_label=data["window_label"],
                interpretation=data["interpretation"],
                reviewed_on=data["reviewed_on"],
                limitations=tuple(data.get("limitations") or ()),
                confounders=tuple(data.get("confounders") or ()),
                missing_measures=tuple(data.get("missing_measures") or ()),
                what_would_change_it=tuple(data.get("what_would_change_it") or ()),
                kill_conditions_triggered=tuple(data.get("kill_conditions_triggered") or ()),
                finance_refs=tuple(
                    FinanceReference.from_dict(r) for r in data.get("finance_refs") or ()
                ),
                research_refs=tuple(
                    ResearchReference.from_dict(r) for r in data.get("research_refs") or ()
                ),
                execution_refs=tuple(
                    ExecutionReference.from_dict(r) for r in data.get("execution_refs") or ()
                ),
                evidence=evidence_tuple(data.get("evidence")),
            )
        except KeyError as exc:
            raise AnalyticsError(f"result: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"result: {exc}") from None


def evaluate_experiment(
    result_id: str,
    specification: ExperimentSpecification,
    comparison: DeliverableComparison,
    observation_ids: Iterable[str],
    interpretation: str,
    reviewed_on: Any,
    *,
    guardrail_values: Mapping[str, float] | None = None,
    unresolved_confounders: Iterable[str] = (),
    what_would_change_it: Iterable[str] = (),
    finance_refs: Iterable[FinanceReference] = (),
    research_refs: Iterable[ResearchReference] = (),
    execution_refs: Iterable[ExecutionReference] = (),
    evidence: Iterable[Evidence] = (),
) -> ExperimentResult:
    """Derive a qualified result from a specification and a comparison.

    Deterministic: the same specification and comparison produce the same
    verdict, the same blockers and the same caveats. Every judgement it makes is
    a comparison of the observed direction with the expectation the
    specification recorded beforehand.
    """
    if not isinstance(specification, ExperimentSpecification):
        raise AnalyticsError("evaluate_experiment needs an ExperimentSpecification")
    if not isinstance(comparison, DeliverableComparison):
        raise AnalyticsError("evaluate_experiment needs a DeliverableComparison")
    if comparison.window != specification.observation_window:
        raise AnalyticsError(
            f"{specification.experiment_id}: the comparison was taken over "
            f"{comparison.window} but the specification set {specification.observation_window} "
            "before the experiment ran. Reading a different window after the fact is "
            "how a null result becomes a positive one"
        )

    ids = tuple(dict.fromkeys(observation_ids))
    outcomes = tuple(
        _outcome(metric, comparison, specification.expectation_for(metric))
        for metric in specification.primary_metrics
    )
    uncompared = tuple(o.metric for o in outcomes if not o.comparable)

    causal = CausalAssessment(
        basis=specification.basis,
        sample_size=len(ids),
        minimum_sample=specification.minimum_sample,
        changed_variable_count=len(specification.variables_changed),
        uncompared_primary_metrics=uncompared,
        unresolved_confounders=tuple(unresolved_confounders),
    )
    verdict = _verdict(outcomes, len(ids), specification.minimum_sample)
    guardrails = _guardrails(specification, guardrail_values or {})

    missing = tuple(
        sorted(
            set(uncompared)
            | {g.metric for g in guardrails if g.missing}
            | set(comparison.only_in_a)
            | set(comparison.only_in_b)
        )
    )
    limitations = list(comparison.caveats)
    for entry in comparison.comparisons:
        limitations.extend(entry.caveats)
        limitations.extend(entry.reasons)
    if comparison.unmatched_metrics:
        limitations.append(
            "measured on only one side: " + ", ".join(comparison.unmatched_metrics)
        )

    falsifiers = tuple(what_would_change_it) or (
        f"a repeat at the same {specification.observation_window.label} window reaching "
        f"at least {specification.minimum_sample} observations, or a randomised split "
        "isolating " + ", ".join(sorted(v.dimension for v in specification.variables_changed)),
    )

    return ExperimentResult(
        result_id=result_id,
        experiment_id=specification.experiment_id,
        verdict=verdict,
        causal=causal,
        primary_outcomes=outcomes,
        guardrail_outcomes=guardrails,
        observation_ids=ids,
        sample_size=len(ids),
        window_label=specification.observation_window.label,
        interpretation=interpretation,
        reviewed_on=reviewed_on,
        limitations=tuple(dict.fromkeys(limitations)),
        confounders=specification.confounding_reasons,
        missing_measures=missing,
        what_would_change_it=falsifiers,
        kill_conditions_triggered=tuple(
            statement for g in guardrails for statement in g.breached
        ),
        finance_refs=tuple(finance_refs),
        research_refs=tuple(research_refs),
        execution_refs=tuple(execution_refs),
        evidence=evidence_tuple(tuple(evidence)),
    )


def _outcome(
    metric: str, comparison: DeliverableComparison, expectation: Expectation | None
) -> MetricOutcome:
    entry: MetricComparison | None = comparison.get(metric)
    if entry is None:
        return MetricOutcome(
            metric=metric,
            observed=None,
            expected=expectation.direction if expectation else None,
            difference=None,
            comparable=False,
            reasons=(f"{metric} was not measured on both sides over {comparison.window}",),
        )
    return MetricOutcome(
        metric=metric,
        observed=entry.direction,
        expected=expectation.direction if expectation else None,
        difference=entry.difference,
        comparable=entry.comparable,
        reasons=entry.reasons,
    )


def _verdict(
    outcomes: tuple[MetricOutcome, ...], sample_size: int, minimum_sample: int
) -> Verdict:
    """Sample adequacy first, and it is not overridable.

    Checked before the numbers are looked at, because a clear-looking difference
    over two videos is exactly the evidence that tempts a conclusion.
    """
    if sample_size < minimum_sample:
        return Verdict.INSUFFICIENT_EVIDENCE
    matches = [o.matched_expectation for o in outcomes]
    if not matches or all(m is None for m in matches):
        return Verdict.INCONCLUSIVE
    decided = [m for m in matches if m is not None]
    if any(m is None for m in matches):
        return Verdict.MIXED if len(set(decided)) > 1 else Verdict.INCONCLUSIVE
    if all(decided):
        return Verdict.SUPPORTS_HYPOTHESIS
    if not any(decided):
        return Verdict.DOES_NOT_SUPPORT
    return Verdict.MIXED


def _guardrails(
    specification: ExperimentSpecification, values: Mapping[str, float]
) -> tuple[GuardrailOutcome, ...]:
    by_metric: dict[str, list[KillCondition]] = {}
    for condition in specification.kill_conditions:
        by_metric.setdefault(condition.metric, []).append(condition)

    out: list[GuardrailOutcome] = []
    for metric in sorted(set(specification.guardrail_metrics) | set(by_metric)):
        value = values.get(metric)
        if value is None:
            out.append(
                GuardrailOutcome(
                    metric=metric,
                    value=None,
                    breached=(),
                    missing=True,
                )
            )
            continue
        breached = tuple(
            condition.statement(value)
            for condition in sorted(by_metric.get(metric, ()), key=lambda c: c.condition_id)
            if condition.breached_by(value)
        )
        out.append(GuardrailOutcome(metric=metric, value=float(value), breached=breached))
    return tuple(out)
