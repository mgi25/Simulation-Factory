"""Durable learnings and the hypotheses that have not earned that name yet.

## Two record types, and the gap between them is the point

An `AnalyticsHypothesis` is a guess with a lifecycle. An `AnalyticsLearning` is
something we are prepared to let the next video depend on. Section 12: a
hypothesis is not a durable fact, and it must not be silently promoted into one.

So promotion is a function with preconditions, not an attribute assignment.
`promote()` requires a result id and refuses a result that did not support the
hypothesis - and the created learning inherits the caveats of the evidence it
came from. A hypothesis whose experiment came back `INCONCLUSIVE` stays a
hypothesis, which is the correct and unsatisfying answer.

## Why a learning must say what would overturn it

`what_would_overturn` is required (section 11). A durable claim with no falsifier
cannot be checked by the next session, so it never gets checked, so it stays
authoritative long after it stopped being true. The field is the difference
between a learning and a house style.

`freshness` and `recheck_on` do the same job over time: what we learned about
hooks in a quarter when the platform was promoting one surface is a claim with a
shelf life, and the record says when somebody should look again.

## Why a scope is required and universality is refused

Section 24: no learning from one observation that claims universality.
`EvidenceStrength` is the enum, `scope` is the prose, and `__post_init__`
enforces the pairing - a learning whose evidence is `SINGLE_OBSERVATION` may not
claim `ALL_FORMATS` scope. It can still be recorded; it simply has to say it is
about the format it came from. That is almost always what was actually learned.

## No confidence percentage

`EvidenceStrength` is four words, for the reason
`intelligence/research/common.py` gives about its own confidence levels: someone
who writes 0.73 has not measured 0.73. The strength is derived from how many
observations and what kind of comparison, both of which are recorded.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_tag,
    evidence_tuple,
    record_to_dict,
    ref_tuple,
    tag_tuple,
    text_tuple,
)
from .errors import AnalyticsError, EvidenceRequired, OverclaimRefused
from .results import ExperimentResult, Verdict


class HypothesisState(Enum):
    """The lifecycle. `SUPPORTED` is reachable only through `promote`."""

    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    SUPERSEDED = "superseded"

    @property
    def is_settled(self) -> bool:
        return self in (
            HypothesisState.SUPPORTED,
            HypothesisState.NOT_SUPPORTED,
            HypothesisState.SUPERSEDED,
        )


# Which transitions are legal. A hypothesis cannot jump from proposed to
# supported without being tested, and a settled one cannot quietly reopen -
# superseding it is a new record that names the old one.
_TRANSITIONS: dict[HypothesisState, frozenset[HypothesisState]] = {
    HypothesisState.PROPOSED: frozenset(
        {HypothesisState.TESTING, HypothesisState.SUPERSEDED}
    ),
    HypothesisState.TESTING: frozenset(
        {
            HypothesisState.SUPPORTED,
            HypothesisState.NOT_SUPPORTED,
            HypothesisState.SUPERSEDED,
        }
    ),
    HypothesisState.SUPPORTED: frozenset({HypothesisState.SUPERSEDED}),
    HypothesisState.NOT_SUPPORTED: frozenset({HypothesisState.SUPERSEDED}),
    HypothesisState.SUPERSEDED: frozenset(),
}


class EvidenceStrength(Enum):
    """How much weight a claim can carry. Four words, no percentage."""

    SINGLE_OBSERVATION = "single_observation"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"

    @property
    def level(self) -> int:
        """Ordinal position, for the scope pairing below. Not a score."""
        return _STRENGTH_LEVEL[self]


_STRENGTH_LEVEL = {
    EvidenceStrength.SINGLE_OBSERVATION: 0,
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.STRONG: 3,
}


class LearningScope(Enum):
    """How far a learning claims to reach. Paired with evidence strength."""

    ONE_DELIVERABLE = "one_deliverable"
    ONE_FORMAT = "one_format"
    FORMAT_FAMILY = "format_family"
    ALL_FORMATS = "all_formats"

    @property
    def level(self) -> int:
        """How far the claim reaches, as an ordinal. Not a score."""
        return _SCOPE_LEVEL[self]


_SCOPE_LEVEL = {
    LearningScope.ONE_DELIVERABLE: 0,
    LearningScope.ONE_FORMAT: 1,
    LearningScope.FORMAT_FAMILY: 2,
    LearningScope.ALL_FORMATS: 3,
}

# The minimum evidence a scope may rest on. One observation supports a claim
# about that deliverable; generalising past its own format needs more than one.
_MINIMUM_STRENGTH: dict[LearningScope, EvidenceStrength] = {
    LearningScope.ONE_DELIVERABLE: EvidenceStrength.SINGLE_OBSERVATION,
    LearningScope.ONE_FORMAT: EvidenceStrength.WEAK,
    LearningScope.FORMAT_FAMILY: EvidenceStrength.MODERATE,
    LearningScope.ALL_FORMATS: EvidenceStrength.STRONG,
}


@dataclass(frozen=True)
class AnalyticsHypothesis:
    """A guess, with a state that only moves along declared transitions."""

    hypothesis_id: str
    statement: str
    rationale: str
    proposed_on: dt.date
    owner: str
    state: HypothesisState = HypothesisState.PROPOSED
    metrics: tuple[str, ...] = ()
    experiment_ids: tuple[str, ...] = ()
    result_ids: tuple[str, ...] = ()
    supersedes: str = ""
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "hypothesis_id", assert_record_id(self.hypothesis_id, "hypothesis_id")
        )
        object.__setattr__(self, "statement", assert_prose(self.statement, "statement"))
        object.__setattr__(self, "rationale", assert_prose(self.rationale, "rationale"))
        object.__setattr__(self, "proposed_on", assert_day(self.proposed_on, "proposed_on"))
        object.__setattr__(self, "owner", assert_prose(self.owner, "owner"))
        if not isinstance(self.state, HypothesisState):
            raise AnalyticsError(
                f"hypothesis state must be a HypothesisState, got {self.state!r}"
            )
        object.__setattr__(self, "metrics", tag_tuple(self.metrics, "metrics"))
        object.__setattr__(
            self,
            "experiment_ids",
            ref_tuple(self.experiment_ids, "experiment_ids", validator=assert_record_id),
        )
        object.__setattr__(
            self,
            "result_ids",
            ref_tuple(self.result_ids, "result_ids", validator=assert_record_id),
        )
        if self.supersedes:
            object.__setattr__(
                self, "supersedes", assert_record_id(self.supersedes, "supersedes")
            )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

        if self.state is HypothesisState.SUPPORTED and not self.result_ids:
            raise OverclaimRefused(
                f"{self.hypothesis_id}: a hypothesis cannot be 'supported' with no "
                "experiment result behind it. Promotion goes through promote(), which "
                "requires a result that actually supported it"
            )
        if self.state is HypothesisState.TESTING and not self.experiment_ids:
            raise AnalyticsError(
                f"{self.hypothesis_id}: a hypothesis in testing must name the "
                "experiment testing it"
            )

    def transition(
        self,
        state: HypothesisState,
        *,
        result_ids: tuple[str, ...] = (),
        experiment_ids: tuple[str, ...] = (),
    ) -> AnalyticsHypothesis:
        """Move to `state`, or raise naming the transitions that are legal."""
        if not isinstance(state, HypothesisState):
            raise AnalyticsError(f"state must be a HypothesisState, got {state!r}")
        allowed = _TRANSITIONS[self.state]
        if state not in allowed:
            legal = ", ".join(sorted(s.value for s in allowed)) or "none"
            raise AnalyticsError(
                f"{self.hypothesis_id}: {self.state.value} -> {state.value} is not a "
                f"legal transition. From {self.state.value} the legal moves are: {legal}"
            )
        from dataclasses import replace

        return replace(
            self,
            state=state,
            result_ids=tuple(dict.fromkeys(self.result_ids + result_ids)),
            experiment_ids=tuple(dict.fromkeys(self.experiment_ids + experiment_ids)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> AnalyticsHypothesis:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a hypothesis object, got {data!r}")
        try:
            return cls(
                hypothesis_id=data["hypothesis_id"],
                statement=data["statement"],
                rationale=data["rationale"],
                proposed_on=data["proposed_on"],
                owner=data["owner"],
                state=HypothesisState(data.get("state", "proposed")),
                metrics=tuple(data.get("metrics") or ()),
                experiment_ids=tuple(data.get("experiment_ids") or ()),
                result_ids=tuple(data.get("result_ids") or ()),
                supersedes=data.get("supersedes", ""),
                evidence=evidence_tuple(data.get("evidence")),
            )
        except KeyError as exc:
            raise AnalyticsError(f"hypothesis: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"hypothesis: {exc}") from None


@dataclass(frozen=True)
class AnalyticsLearning:
    """Something we are prepared to let the next video depend on."""

    learning_id: str
    statement: str
    scope: LearningScope
    strength: EvidenceStrength
    what_would_overturn: tuple[str, ...]
    created_on: dt.date
    evidence: tuple[Evidence, ...]
    applies_to: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    result_ids: tuple[str, ...] = ()
    postmortem_ids: tuple[str, ...] = ()
    source_hypothesis_id: str = ""
    recheck_on: dt.date | None = None
    causal_claim: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "learning_id", assert_record_id(self.learning_id, "learning_id")
        )
        object.__setattr__(self, "statement", assert_prose(self.statement, "statement"))
        if not isinstance(self.scope, LearningScope):
            raise AnalyticsError(f"learning scope must be a LearningScope, got {self.scope!r}")
        if not isinstance(self.strength, EvidenceStrength):
            raise AnalyticsError(
                f"evidence strength must be an EvidenceStrength, got {self.strength!r}"
            )
        object.__setattr__(
            self,
            "what_would_overturn",
            text_tuple(self.what_would_overturn, "what_would_overturn"),
        )
        object.__setattr__(self, "created_on", assert_day(self.created_on, "created_on"))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(self, "applies_to", tag_tuple(self.applies_to, "applies_to"))
        object.__setattr__(self, "limitations", text_tuple(self.limitations, "limitations"))
        for name in ("observation_ids", "result_ids", "postmortem_ids"):
            object.__setattr__(
                self, name, ref_tuple(getattr(self, name), name, validator=assert_record_id)
            )
        if self.source_hypothesis_id:
            object.__setattr__(
                self,
                "source_hypothesis_id",
                assert_record_id(self.source_hypothesis_id, "source_hypothesis_id"),
            )
        object.__setattr__(
            self, "recheck_on", None if self.recheck_on is None else assert_day(self.recheck_on, "recheck_on")
        )
        if not isinstance(self.causal_claim, bool):
            raise AnalyticsError("causal_claim must be a bool")

        assert_evidence(self.evidence, self.learning_id)
        if not (self.observation_ids or self.result_ids or self.postmortem_ids):
            raise EvidenceRequired(
                f"{self.learning_id}: a learning must name the observations, results or "
                "postmortems it came from. A statement citing only a document is a "
                "claim about a document"
            )
        if not self.what_would_overturn:
            raise AnalyticsError(
                f"{self.learning_id}: a learning must say what would overturn it. A "
                "durable claim with no falsifier is never rechecked, so it stays "
                "authoritative long after it stops being true"
            )
        required = _MINIMUM_STRENGTH[self.scope]
        if self.strength.level < required.level:
            raise OverclaimRefused(
                f"{self.learning_id}: {self.scope.value} scope on "
                f"{self.strength.value} evidence. A claim reaching that far needs at "
                f"least {required.value} evidence behind it; narrow the scope to what "
                "was actually observed, which is usually the more useful record anyway"
            )
        if self.causal_claim and not self.result_ids:
            raise OverclaimRefused(
                f"{self.learning_id}: a causal claim must name the experiment result "
                "that supports it. Causation is established by a design, not asserted "
                "by a learning"
            )

    @property
    def is_stale(self) -> bool:
        return False if self.recheck_on is None else self.recheck_on < dt.date.today()

    def stale_on(self, today: dt.date) -> bool:
        """Staleness against a supplied date, so callers stay deterministic."""
        return self.recheck_on is not None and self.recheck_on < assert_day(today, "today")

    @property
    def qualified_statement(self) -> str:
        """The statement with its scope and strength attached, as one sentence."""
        claim = "causal claim" if self.causal_claim else "association"
        return (
            f"{self.statement} [{self.scope.value}, {self.strength.value} evidence, "
            f"{claim}]"
        )

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["scope"] = self.scope.value
        data["strength"] = self.strength.value
        data["qualified_statement"] = self.qualified_statement
        return data

    @classmethod
    def from_dict(cls, data: Any) -> AnalyticsLearning:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a learning object, got {data!r}")
        try:
            return cls(
                learning_id=data["learning_id"],
                statement=data["statement"],
                scope=LearningScope(data["scope"]),
                strength=EvidenceStrength(data["strength"]),
                what_would_overturn=tuple(data.get("what_would_overturn") or ()),
                created_on=data["created_on"],
                evidence=evidence_tuple(data.get("evidence")),
                applies_to=tuple(data.get("applies_to") or ()),
                limitations=tuple(data.get("limitations") or ()),
                observation_ids=tuple(data.get("observation_ids") or ()),
                result_ids=tuple(data.get("result_ids") or ()),
                postmortem_ids=tuple(data.get("postmortem_ids") or ()),
                source_hypothesis_id=data.get("source_hypothesis_id", ""),
                recheck_on=data.get("recheck_on"),
                causal_claim=bool(data.get("causal_claim", False)),
            )
        except KeyError as exc:
            raise AnalyticsError(f"learning: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"learning: {exc}") from None


def promote(
    hypothesis: AnalyticsHypothesis,
    result: ExperimentResult,
    learning_id: str,
    scope: LearningScope,
    strength: EvidenceStrength,
    what_would_overturn: tuple[str, ...],
    created_on: Any,
    *,
    applies_to: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    evidence: tuple[Evidence, ...] = (),
) -> tuple[AnalyticsHypothesis, AnalyticsLearning]:
    """Turn a supported hypothesis into a learning, or refuse and say why.

    Returns the updated hypothesis alongside the new learning, because the two
    changes belong together: a hypothesis marked supported with no learning
    recorded is the silent promotion section 12 forbids.

    The created learning inherits the result's caveats as limitations and its
    causal assessment as `causal_claim`. A caller cannot claim causation here
    that the experiment's own design did not support.

    With no evidence supplied the learning cites the result record itself,
    which is the honest pointer: an `ExperimentResult` cannot be constructed
    without naming the observations behind it, so the chain from statement to
    reading stays walkable.
    """
    if not isinstance(hypothesis, AnalyticsHypothesis):
        raise AnalyticsError("promote needs an AnalyticsHypothesis")
    if not isinstance(result, ExperimentResult):
        raise AnalyticsError("promote needs an ExperimentResult")
    if result.verdict is not Verdict.SUPPORTS_HYPOTHESIS:
        raise OverclaimRefused(
            f"{hypothesis.hypothesis_id}: cannot be promoted on a result whose verdict "
            f"is {result.verdict.value!r}. Only a result that supported the hypothesis "
            "promotes it; an inconclusive experiment leaves a hypothesis exactly as "
            "hypothetical as it was"
        )
    if hypothesis.state is not HypothesisState.TESTING:
        raise AnalyticsError(
            f"{hypothesis.hypothesis_id}: only a hypothesis in testing can be promoted, "
            f"not one in {hypothesis.state.value}"
        )

    promoted = hypothesis.transition(
        HypothesisState.SUPPORTED, result_ids=(result.result_id,)
    )
    learning = AnalyticsLearning(
        learning_id=learning_id,
        statement=hypothesis.statement,
        scope=scope,
        strength=strength,
        what_would_overturn=what_would_overturn or result.what_would_change_it,
        created_on=created_on,
        evidence=evidence or result.evidence or _result_evidence(result),
        applies_to=applies_to,
        limitations=tuple(dict.fromkeys(tuple(limitations) + result.all_caveats)),
        observation_ids=result.observation_ids,
        result_ids=(result.result_id,),
        source_hypothesis_id=hypothesis.hypothesis_id,
        causal_claim=result.causal_claim_supported,
    )
    return promoted, learning


def _result_evidence(result: ExperimentResult) -> tuple[Evidence, ...]:
    """The result record as a pointer, for a promotion that supplied no other."""
    return (
        Evidence(
            kind="observation",
            ref=result.result_id,
            note=(
                f"{result.verdict.value} over {result.sample_size} observation(s) at "
                f"{result.window_label}"
            ),
        ),
    )


def assert_evidence(evidence: tuple[Evidence, ...], learning_id: str) -> None:
    if not evidence:
        raise EvidenceRequired(
            f"{learning_id}: a learning must carry at least one piece of evidence. "
            "Section 24: a claim with nothing checkable behind it is a house style "
            "that will outlive the conditions that produced it"
        )
