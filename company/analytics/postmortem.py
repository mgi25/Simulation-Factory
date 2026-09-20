"""What we expected, what happened, and what survives the disappointment.

## The mechanism, stated as a constructor rule

"No failed video without learning" is a slogan until something enforces it.
Here it is two fields that cannot both be empty: a postmortem must carry either
a `durable_learning_id` or a `next_hypothesis_id`. A video that went badly and
taught us nothing is a record that will not construct, and the error says what
is missing.

That is deliberately a low bar. Not every disappointment yields a durable
learning - often the honest output is a sharper hypothesis for next time, and
`AnalyticsLearning` is rightly hard to satisfy. So either will do, and the
failure mode being prevented is the one that actually happens: shipping a weak
video, feeling bad about it, and recording nothing at all.

## Outcome is not a verdict and not a score

`DeliverableOutcome` has five members, and `BELOW_EXPECTATION` is an ordinary
one. It compares the result with what the specification or the research
reference said beforehand - nothing else. There is no numeric grade, and
`UNCLEAR` exists because a video published into an unmeasured week is genuinely
not classifiable, and forcing it into one of the other four would be an
invention.

## Expected versus actual, kept apart

`expected` is prose quoted from the research reference or the experiment
specification - what we believed *before*. `observation_ids` are the readings.
Section 7 again: the two never merge, and the postmortem is the place a reader
can see them side by side, which is the whole point of writing the expectation
down in advance.

## `not_supported_by_evidence` is a required section, not a courtesy

Section 10 lists it and it earns the space. A postmortem is written by someone
who has just watched the thing fail and has theories. Most of those theories are
not supported by anything in the observations, and the honest place for them is
a field that says so - not the `what_failed` list, where they would read as
findings for as long as the record survives.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_deliverable_id,
    assert_prose,
    assert_record_id,
    evidence_tuple,
    record_to_dict,
    ref_tuple,
    text_tuple,
)
from .errors import AnalyticsError, EvidenceRequired
from .references import ExecutionReference, FinanceReference, ResearchReference


class DeliverableOutcome(Enum):
    """How the result compared with what was expected beforehand. Not a grade."""

    ABOVE_EXPECTATION = "above_expectation"
    AS_EXPECTED = "as_expected"
    BELOW_EXPECTATION = "below_expectation"
    MIXED = "mixed"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class DeliverablePostmortem:
    """A retrospective on one deliverable, with its learning attached."""

    postmortem_id: str
    deliverable_id: str
    outcome: DeliverableOutcome
    expected: str
    observation_ids: tuple[str, ...]
    what_worked: tuple[str, ...]
    what_failed: tuple[str, ...]
    written_on: dt.date
    author: str
    surprises: tuple[str, ...] = ()
    technical_issues: tuple[str, ...] = ()
    viewer_behavior: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    not_supported_by_evidence: tuple[str, ...] = ()
    experiment_result_ids: tuple[str, ...] = ()
    durable_learning_id: str = ""
    next_hypothesis_id: str = ""
    finance_refs: tuple[FinanceReference, ...] = ()
    research_refs: tuple[ResearchReference, ...] = ()
    execution_refs: tuple[ExecutionReference, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "postmortem_id", assert_record_id(self.postmortem_id, "postmortem_id")
        )
        object.__setattr__(
            self,
            "deliverable_id",
            assert_deliverable_id(self.deliverable_id, "deliverable_id"),
        )
        if not isinstance(self.outcome, DeliverableOutcome):
            raise AnalyticsError(
                f"outcome must be a DeliverableOutcome, got {self.outcome!r}. Known: "
                + ", ".join(sorted(o.value for o in DeliverableOutcome))
            )
        object.__setattr__(self, "expected", assert_prose(self.expected, "expected"))
        object.__setattr__(
            self,
            "observation_ids",
            ref_tuple(self.observation_ids, "observation_ids", validator=assert_record_id),
        )
        for name in (
            "what_worked",
            "what_failed",
            "surprises",
            "technical_issues",
            "viewer_behavior",
            "unresolved_questions",
            "not_supported_by_evidence",
        ):
            object.__setattr__(self, name, text_tuple(getattr(self, name), name))
        object.__setattr__(self, "written_on", assert_day(self.written_on, "written_on"))
        object.__setattr__(self, "author", assert_prose(self.author, "author"))
        object.__setattr__(
            self,
            "experiment_result_ids",
            ref_tuple(
                self.experiment_result_ids, "experiment_result_ids", validator=assert_record_id
            ),
        )
        if self.durable_learning_id:
            object.__setattr__(
                self,
                "durable_learning_id",
                assert_record_id(self.durable_learning_id, "durable_learning_id"),
            )
        if self.next_hypothesis_id:
            object.__setattr__(
                self,
                "next_hypothesis_id",
                assert_record_id(self.next_hypothesis_id, "next_hypothesis_id"),
            )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

        if not self.observation_ids and not self.experiment_result_ids:
            raise EvidenceRequired(
                f"{self.postmortem_id}: a postmortem must name the observations or the "
                "experiment results it is about. A retrospective with no readings "
                "behind it is a recollection"
            )
        if not self.durable_learning_id and not self.next_hypothesis_id:
            raise AnalyticsError(
                f"{self.postmortem_id}: a postmortem must produce either a durable "
                "learning or a next hypothesis. A deliverable that disappointed and "
                "taught nothing is the one outcome this record exists to prevent - if "
                "the evidence does not support a learning yet, write the hypothesis it "
                "sharpened"
            )
        if self.outcome is DeliverableOutcome.BELOW_EXPECTATION and not (
            self.what_failed or self.unresolved_questions
        ):
            raise AnalyticsError(
                f"{self.postmortem_id}: outcome is below expectation but nothing is "
                "recorded as having failed or as still open. Say what went wrong, or "
                "say the question is unresolved - both are useful, silence is not"
            )

    @property
    def produced_learning(self) -> bool:
        return bool(self.durable_learning_id)

    @property
    def is_disappointment(self) -> bool:
        return self.outcome in (
            DeliverableOutcome.BELOW_EXPECTATION,
            DeliverableOutcome.MIXED,
        )

    def summary_line(self) -> str:
        produced = (
            f"learning {self.durable_learning_id}"
            if self.durable_learning_id
            else f"hypothesis {self.next_hypothesis_id}"
        )
        return f"{self.deliverable_id}: {self.outcome.value} -> {produced}"

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["outcome"] = self.outcome.value
        data["produced_learning"] = self.produced_learning
        return data

    @classmethod
    def from_dict(cls, data: Any) -> DeliverablePostmortem:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a postmortem object, got {data!r}")
        try:
            return cls(
                postmortem_id=data["postmortem_id"],
                deliverable_id=data["deliverable_id"],
                outcome=DeliverableOutcome(data["outcome"]),
                expected=data["expected"],
                observation_ids=tuple(data.get("observation_ids") or ()),
                what_worked=tuple(data.get("what_worked") or ()),
                what_failed=tuple(data.get("what_failed") or ()),
                written_on=data["written_on"],
                author=data["author"],
                surprises=tuple(data.get("surprises") or ()),
                technical_issues=tuple(data.get("technical_issues") or ()),
                viewer_behavior=tuple(data.get("viewer_behavior") or ()),
                unresolved_questions=tuple(data.get("unresolved_questions") or ()),
                not_supported_by_evidence=tuple(data.get("not_supported_by_evidence") or ()),
                experiment_result_ids=tuple(data.get("experiment_result_ids") or ()),
                durable_learning_id=data.get("durable_learning_id", ""),
                next_hypothesis_id=data.get("next_hypothesis_id", ""),
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
            raise AnalyticsError(f"postmortem: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"postmortem: {exc}") from None
