"""Research batch reports, read as organizational signals.

## Why the report is duck-typed rather than imported

`intelligence/research/batch_report.py` already computes every number below, and
computing any of them again here would be the duplication constitution rule 15
forbids. What this module does *not* do is import that package: it reads a
documented set of attributes off whatever object the caller hands it. Three
reasons, in order of weight:

1. the boundary stays one-way. `company/org_intelligence` imports nothing from
   `intelligence/`, so the research subsystem can move, split or be replaced
   without this package noticing;
2. a caller with a summary rather than a whole report can still use it;
3. the attribute list below is the contract, and it is short enough to read.

`ResearchEvidence.from_batch_report` names every attribute it touches, so a
rename in the research layer fails loudly on the next run rather than silently
producing `None`.

## What this refuses to conclude

A weak batch is evidence about a batch. The brief is blunt about the inference
that must not happen - *do not infer that a content format is bad from one weak
research batch* - and the code keeps it out of reach twice: every signal's
subject is the batch id and its kind is `RESEARCH_BATCH`, never a format; and
`SINGLE_BATCH_LIMITATION` is attached to every signal, so a finding built from
one batch carries the sentence into its own limitations.

Sample size survives the same way. A duplicate rate over eleven observations is
a real number about a small search, and `minimum_candidates` puts the caveat on
the measurement rather than leaving it to whoever reads the report.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import positive_int, ratio
from .errors import OrgIntelligenceError
from .signals import (
    Direction,
    Measurement,
    OrganizationalSignal,
    SignalType,
    SubjectKind,
)
from .window import ReviewWindow

SINGLE_BATCH_LIMITATION = (
    "one research batch. Nothing here supports a conclusion about a content "
    "format, a creator or a query family - only about how this search ran"
)


@dataclass(frozen=True)
class ResearchPolicy:
    """Thresholds for reading a batch report. Every one of them an opinion."""

    duplicate_rate_threshold: float = 0.5
    creator_share_threshold: float = 0.5
    screening_coverage_threshold: float = 0.5
    promotion_yield_threshold: float = 0.1
    minimum_candidates: int = 10

    def __post_init__(self) -> None:
        for name in (
            "duplicate_rate_threshold",
            "creator_share_threshold",
            "screening_coverage_threshold",
            "promotion_yield_threshold",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise OrgIntelligenceError(f"{name} must be a rate in (0, 1]")
        positive_int(self.minimum_candidates, "minimum_candidates", minimum=2)


DEFAULT_RESEARCH_POLICY = ResearchPolicy()


@dataclass(frozen=True)
class ResearchEvidence:
    """One batch's numbers, copied from a report rather than recomputed."""

    batch_id: str
    observations: int
    unique_candidates: int
    duplicate_rate: float | None = None
    top_creator: str = ""
    top_creator_share: float | None = None
    unknown_creator_candidates: int = 0
    assessed_candidates: int = 0
    unscreened_candidates: int = 0
    promoted_sources: int = 0
    report_missing_measurements: tuple[str, ...] = ()

    @classmethod
    def from_batch_report(cls, report: Any) -> ResearchEvidence:
        """Read a `BatchReport` without importing one.

        Every attribute this touches is named here on purpose: `batch_id`,
        `progress.{observations,unique_candidates,unscreened,promoted_sources}`,
        `duplication.duplicate_rate`,
        `creators.{top_creator,top_creator_share,unknown_creator_candidates}`,
        `screening.assessed` and `missing_measurements`. A rename upstream raises
        `AttributeError` on the next run rather than quietly yielding `None`.
        """
        try:
            progress = report.progress
            duplication = report.duplication
            creators = report.creators
            screening = report.screening
            return cls(
                batch_id=str(report.batch_id),
                observations=int(progress.observations),
                unique_candidates=int(progress.unique_candidates),
                duplicate_rate=duplication.duplicate_rate,
                top_creator=str(creators.top_creator or ""),
                top_creator_share=creators.top_creator_share,
                unknown_creator_candidates=int(creators.unknown_creator_candidates),
                assessed_candidates=int(screening.assessed),
                unscreened_candidates=int(progress.unscreened),
                promoted_sources=int(progress.promoted_sources),
                report_missing_measurements=tuple(report.missing_measurements),
            )
        except AttributeError as exc:
            raise OrgIntelligenceError(
                "from_batch_report expects a research BatchReport shape; "
                f"missing attribute: {exc}"
            ) from exc

    @property
    def screening_coverage(self) -> float | None:
        return ratio(self.assessed_candidates, self.unique_candidates)

    @property
    def promotion_yield(self) -> float | None:
        return ratio(self.promoted_sources, self.unique_candidates)

    @property
    def missing_measurements(self) -> tuple[str, ...]:
        """The report's own absences, plus the ones a reader of it inherits."""
        out = list(self.report_missing_measurements)
        if self.duplicate_rate is None:
            out.append("duplicate rate: no observation log to compute it from")
        if self.top_creator_share is None:
            out.append("creator concentration: no candidate carried a creator")
        if self.unknown_creator_candidates:
            out.append(
                f"{self.unknown_creator_candidates} candidate(s) have no creator recorded, "
                "so concentration is computed over a smaller denominator"
            )
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base.update(
            screening_coverage=self.screening_coverage,
            promotion_yield=self.promotion_yield,
            missing_measurements=list(self.missing_measurements),
        )
        return base


def research_signals(
    evidence: ResearchEvidence,
    *,
    window: ReviewWindow,
    policy: ResearchPolicy = DEFAULT_RESEARCH_POLICY,
    evidence_refs: Iterable[Evidence] = (),
    prefix: str = "sig-rsr",
) -> tuple[OrganizationalSignal, ...]:
    """Duplication, concentration, screening yield and promotion yield.

    Every signal's subject is the batch. The sample caveat rides on the
    measurement (candidates below `minimum_candidates`), and the single-batch
    caveat rides on every signal whether the sample was small or not - because
    the thing it warns against is not a sample-size mistake, it is a
    unit-of-analysis mistake.
    """
    if not isinstance(evidence, ResearchEvidence):
        raise OrgIntelligenceError("research_signals takes a ResearchEvidence")
    pointers = tuple(evidence_refs) or (
        Evidence(
            kind="measurement",
            ref=f"intelligence/research/batch_report.py#{evidence.batch_id}",
            note=(
                f"{evidence.observations} observation(s), "
                f"{evidence.unique_candidates} unique candidate(s)"
            ),
        ),
    )
    stem = f"{prefix}-{evidence.batch_id.replace('_', '-')}"
    absences = evidence.missing_measurements
    out: list[OrganizationalSignal] = []

    for value, signal_type, threshold, direction, unit, detail in (
        (
            evidence.duplicate_rate,
            SignalType.RESEARCH_QUERY_DUPLICATION,
            policy.duplicate_rate_threshold,
            Direction.HIGHER_IS_WORSE,
            "rate",
            "of observations re-sighted a candidate the batch already had",
        ),
        (
            evidence.top_creator_share,
            SignalType.RESEARCH_CREATOR_CONCENTRATION,
            policy.creator_share_threshold,
            Direction.HIGHER_IS_WORSE,
            "rate",
            f"of candidates with a known creator come from {evidence.top_creator or 'one channel'}",
        ),
        (
            evidence.screening_coverage,
            SignalType.LOW_RESEARCH_YIELD,
            policy.screening_coverage_threshold,
            Direction.LOWER_IS_WORSE,
            "rate",
            "of unique candidates were screened at all",
        ),
        (
            evidence.promotion_yield,
            SignalType.LOW_RESEARCH_YIELD,
            policy.promotion_yield_threshold,
            Direction.LOWER_IS_WORSE,
            "rate",
            "of unique candidates were promoted to a source",
        ),
    ):
        measurement = Measurement(
            value=value,
            unit=unit if value is not None else "",
            threshold=threshold,
            direction=direction,
            sample_size=evidence.unique_candidates,
            minimum_sample=policy.minimum_candidates,
        )
        if measurement.breaches_threshold is not True:
            continue
        out.append(
            OrganizationalSignal(
                signal_id=(
                    f"{stem}-{signal_type.value.replace('_', '-')}"
                    f"-{_discriminator(signal_type, detail)}"
                ),
                type=signal_type,
                subject=evidence.batch_id,
                subject_kind=SubjectKind.RESEARCH_BATCH,
                window=window,
                detail=(
                    f"{evidence.batch_id}: {value:.3g} {detail}, against a "
                    f"{threshold:.3g} threshold"
                ),
                measurement=measurement,
                evidence=pointers,
                missing_measurements=absences,
                caveats=(SINGLE_BATCH_LIMITATION,),
                source_refs=("intelligence/research/batch_report.py",),
            )
        )
    return tuple(out)


def _discriminator(signal_type: SignalType, detail: str) -> str:
    """Keep the two `low_research_yield` signals from sharing an id."""
    if signal_type is not SignalType.LOW_RESEARCH_YIELD:
        return "1"
    return "promotion" if "promoted" in detail else "screening"
