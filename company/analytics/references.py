"""Pointers into the other subsystems, carrying ids and never carrying their work.

## Why these are records rather than imports

`company/finance` already knows what a video cost and what it earned.
`intelligence/research` already knows what we expected before we published.
`company/runtime` already knows what the session that built it consumed.
Analytics needs to *cite* all three and must recompute none of them
(constitution rule 15, brief sections 20-23).

The cheapest way to guarantee that is to have nothing to recompute with. These
records hold record ids and a note. No amounts, no rates, no counts. A
`FinanceReference` cannot be summed because there is nothing on it to sum; a
reader who wants the margin goes to `company/finance` and asks it, which is the
subsystem that knows about currency, allocation rules and what is still missing.

This also keeps the import graph one-way. `company/analytics` imports no other
Company OS subsystem except `company/runtime/state_paths` for file creation and
`company/validation/errors` for the exception base - the same two
`company/finance` takes. So the capsule edge added in this phase,
organizational intelligence to analytics, cannot close a cycle.

## The one record that points outward at somebody else

`CompetitorPublicReference` is how a competitor's numbers reach an analysis.
Section 19: their public metrics may be referenced from research, their private
metrics do not exist. So the record names the research dossier, lists which
*public* metric names it covers, and refuses a private one by asking the metric
registry - the same definition `observations.py` asks. A competitor's retention
has nowhere to be stored, on either path.

It is also deliberately not an observation. It has no value field, so a
competitor reading can never end up in one of our series, in one of our
baselines, or on one side of a comparison against our own deliverable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .common import (
    assert_prose,
    assert_record_id,
    assert_tag,
    ref_tuple,
    record_to_dict,
    tag_tuple,
)
from .errors import AnalyticsError, ProvenanceViolation
from .metrics import DEFAULT_REGISTRY, MetricRegistry


class FinanceRecordKind(Enum):
    """The finance records analytics may cite, by the names finance gives them."""

    COST_RECORD = "cost_record"
    REVENUE_RECORD = "revenue_record"
    DELIVERABLE_ECONOMICS = "deliverable_economics"
    PROFITABILITY_SUMMARY = "profitability_summary"


@dataclass(frozen=True)
class FinanceReference:
    """A pointer at finance records. Carries no money and does no arithmetic."""

    kind: FinanceRecordKind
    record_ids: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FinanceRecordKind):
            raise AnalyticsError(
                f"finance reference kind must be a FinanceRecordKind, got {self.kind!r}. "
                "Known: " + ", ".join(sorted(k.value for k in FinanceRecordKind))
            )
        object.__setattr__(
            self,
            "record_ids",
            ref_tuple(self.record_ids, "finance record_ids", validator=assert_record_id),
        )
        if not self.record_ids:
            raise AnalyticsError(
                "a finance reference must name at least one record; a reference to "
                "finance in general is not evidence of anything"
            )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "finance note"))

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> FinanceReference:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a finance reference object, got {data!r}")
        try:
            return cls(
                kind=FinanceRecordKind(data["kind"]),
                record_ids=tuple(data["record_ids"]),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"finance reference: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"finance reference: {exc}") from None


class ResearchRecordKind(Enum):
    """The research records analytics may cite."""

    VIDEO_INTELLIGENCE_DOSSIER = "video_intelligence_dossier"
    OPPORTUNITY_DOSSIER = "opportunity_dossier"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    RESEARCH_EVIDENCE = "research_evidence"
    BATCH_REPORT = "batch_report"


@dataclass(frozen=True)
class ResearchReference:
    """A pointer at research records, with what we expected before publishing.

    `expectation` is the one piece of prose that earns its place: section 21
    asks a postmortem to compare the pre-video expectation with the post-release
    result, and the expectation as it was written *at the time* is the thing
    that gets rewritten by memory if it is not copied down. It is a quotation of
    a dated record, not a recomputation of one.
    """

    kind: ResearchRecordKind
    record_ids: tuple[str, ...]
    expectation: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResearchRecordKind):
            raise AnalyticsError(
                f"research reference kind must be a ResearchRecordKind, got "
                f"{self.kind!r}. Known: "
                + ", ".join(sorted(k.value for k in ResearchRecordKind))
            )
        object.__setattr__(
            self,
            "record_ids",
            ref_tuple(self.record_ids, "research record_ids", validator=assert_record_id),
        )
        if not self.record_ids:
            raise AnalyticsError(
                "a research reference must name at least one record; a reference to "
                "research in general is not evidence of anything"
            )
        if self.expectation:
            object.__setattr__(
                self, "expectation", assert_prose(self.expectation, "expectation")
            )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "research note"))

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> ResearchReference:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a research reference object, got {data!r}")
        try:
            return cls(
                kind=ResearchRecordKind(data["kind"]),
                record_ids=tuple(data["record_ids"]),
                expectation=data.get("expectation", ""),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"research reference: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"research reference: {exc}") from None


class ExecutionRecordKind(Enum):
    """The runtime records analytics may cite when studying what work cost us."""

    RESOURCE_USAGE_RECORD = "resource_usage_record"
    SESSION_RECEIPT = "session_receipt"


@dataclass(frozen=True)
class ExecutionReference:
    """A pointer at what building the deliverable consumed.

    No token counts, no retry counts, no minutes. `ai_platform/usage.py` counts
    those and `company/org_intelligence/resources.py` already reads them; a
    second count here would be a second answer to one question.
    """

    kind: ExecutionRecordKind
    record_ids: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecutionRecordKind):
            raise AnalyticsError(
                f"execution reference kind must be an ExecutionRecordKind, got "
                f"{self.kind!r}. Known: "
                + ", ".join(sorted(k.value for k in ExecutionRecordKind))
            )
        object.__setattr__(
            self,
            "record_ids",
            ref_tuple(self.record_ids, "execution record_ids", validator=assert_record_id),
        )
        if not self.record_ids:
            raise AnalyticsError(
                "an execution reference must name at least one record"
            )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "execution note"))

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> ExecutionReference:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an execution reference object, got {data!r}")
        try:
            return cls(
                kind=ExecutionRecordKind(data["kind"]),
                record_ids=tuple(data["record_ids"]),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"execution reference: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"execution reference: {exc}") from None


@dataclass(frozen=True)
class CompetitorPublicReference:
    """Somebody else's video, cited from research, public metric names only.

    Holds no values. A competitor's public view count that we want to reason
    about lives in the research snapshot that recorded it; what this record does
    is let an analysis say which dossier it consulted, without opening a path
    for that number to enter one of our series.
    """

    dossier_ids: tuple[str, ...]
    public_metrics: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dossier_ids",
            ref_tuple(self.dossier_ids, "dossier_ids", validator=assert_record_id),
        )
        if not self.dossier_ids:
            raise AnalyticsError(
                "a competitor reference must name the research dossier it came from; "
                "an uncited external claim is a rumour"
            )
        object.__setattr__(
            self, "public_metrics", tag_tuple(self.public_metrics, "public_metrics")
        )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "competitor note"))
        self.assert_public_only()

    def assert_public_only(self, registry: MetricRegistry | None = None) -> None:
        """Refuse a private metric name on an external reference.

        Runs at construction against the default registry; exposed as a method
        so a caller that registered private metrics of its own can re-check
        against the registry it actually uses.
        """
        known = registry or DEFAULT_REGISTRY
        for name in self.public_metrics:
            if name in known and known.get(name).private:
                raise ProvenanceViolation(
                    f"{name!r} is a private channel analytic and cannot be attributed "
                    "to somebody else's video. No public page shows it, so a value "
                    "would be an inference wearing the clothes of an observation. "
                    "Their public counts are in the research snapshot; their private "
                    "analytics are not observable by anyone outside their channel."
                )

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: Any) -> CompetitorPublicReference:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a competitor reference object, got {data!r}")
        try:
            return cls(
                dossier_ids=tuple(data["dossier_ids"]),
                public_metrics=tuple(data.get("public_metrics") or ()),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(
                f"competitor reference: missing {exc.args[0]!r}"
            ) from None
