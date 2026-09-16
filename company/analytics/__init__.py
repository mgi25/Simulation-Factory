"""Company OS analytics: what happened after we published, and what it proves.

The durable analytical contracts. It records observations, defines comparisons,
and interprets evidence cautiously - and it keeps those three things apart,
because collapsing them is how a content company convinces itself it has learned
something.

## The loop

    published deliverable
      -> dated observations        immutable, sourced, never overwritten
      -> experiment comparison     what changed, what was held, at what age
      -> qualified result          a verdict about our prediction, not the world
      -> postmortem                including when it went badly
      -> durable learning          or the sharper hypothesis it produced instead

## Five rules the whole package is built on

1. **An observation is an event, not a field.** A video at one hour and at
   thirty days are two records. There is no update path, and the store refuses a
   second write of one id with different bytes.
2. **A metric means one thing.** A value is recorded against a
   `MetricDefinition` carrying its unit and, for a rate, its denominator - never
   against a bare name.
3. **Association is not causation, and the default is association.**
   `causal_claim_supported` is computed from the design, not set by a caller. A
   randomised split with one changed variable and adequate sample can reach True;
   nothing else can, and even then the wording stays qualified.
4. **Unknown stays unknown.** A metric nobody measured is missing, a rate with
   no denominator is not comparable, and a partial reading says what it excludes.
   None of them become zero.
5. **No score.** Not for a video, a format, an experiment or the channel. The
   objective is long-term profitable audience growth, which is not one number,
   and a single number here would be optimised in its place.

## What it deliberately does not have

No YouTube connector, no OAuth, no scraper, no scheduler, no prediction model,
no embeddings, no LLM analysis. Constitution rule 17 - prove need before
building. This phase defines the contracts the data will have to satisfy; a
session that later fetches the data has something to put it in.

No title inference either, in this phase or a later one. Feature tags are
recorded by whoever made the thing (`genome.py`), because a feature read off a
title is a guess about how a video was made carrying the authority of a record.

## Boundaries

Finance owns money, research owns the outside world, the runtime owns what work
consumed. Analytics cites all three by reference (`references.py`) and
recomputes none of them. It imports no other Company OS subsystem beyond
`company.runtime.state_paths` and `company.validation.errors`, so the capsule
edge from organizational intelligence to analytics cannot close a cycle.

Nothing here imports production, and no production module imports this.
Standard library only.
"""

from .baseline import (
    FormatBaseline,
    MetricSummary,
    OutlierMethod,
    OutlierRule,
    build_baseline,
    summarise_metric,
)
from .common import DataScope, DataSource, Provenance
from .comparison import DeliverableComparison, MetricComparison, compare_deliverables
from .deliverable import AnalyzedDeliverable, DeliverableKind
from .errors import (
    AnalyticsError,
    AnalyticsIntegrityError,
    EvidenceRequired,
    LedgerViolation,
    OverclaimRefused,
    ProvenanceViolation,
)
from .experiments import (
    ComparisonBasis,
    Direction,
    Expectation,
    ExperimentSpecification,
    ExperimentStatus,
    KillCondition,
    Variable,
)
from .formats import (
    ASSOCIATION_NOTE,
    GroupBy,
    GroupedPerformance,
    PerformanceGroup,
    group_performance,
    group_value,
)
from .genome import ALL_DIMENSIONS, ContentFeatures, FeatureDimension
from .integrity import CONSTRUCTION_ENFORCED, assert_integrity, check_integrity
from .learning import (
    AnalyticsHypothesis,
    AnalyticsLearning,
    EvidenceStrength,
    HypothesisState,
    LearningScope,
    promote,
)
from .metrics import (
    DEFAULT_REGISTRY,
    STANDARD_METRICS,
    MetricDefinition,
    MetricKind,
    MetricRegistry,
)
from .observations import MetricObservation, ObservationSeries, observe
from .postmortem import DeliverableOutcome, DeliverablePostmortem
from .references import (
    CompetitorPublicReference,
    ExecutionRecordKind,
    ExecutionReference,
    FinanceRecordKind,
    FinanceReference,
    ResearchRecordKind,
    ResearchReference,
)
from .report import AnalyticsReport, MeasurementCoverage, build_report
from .results import (
    CausalAssessment,
    ExperimentResult,
    GuardrailOutcome,
    MetricOutcome,
    Verdict,
    evaluate_experiment,
)
from .store import AnalyticsStore, AnalyticsStoreError
from .windows import (
    FIRST_7D,
    FIRST_24H,
    FIRST_30D,
    FIRST_HOUR,
    LIFETIME,
    STANDARD_AGE_WINDOWS,
    AgeWindow,
    DateRange,
    standard_age_window,
)

__all__ = [
    "ALL_DIMENSIONS",
    "ASSOCIATION_NOTE",
    "CONSTRUCTION_ENFORCED",
    "DEFAULT_REGISTRY",
    "FIRST_7D",
    "FIRST_24H",
    "FIRST_30D",
    "FIRST_HOUR",
    "LIFETIME",
    "STANDARD_AGE_WINDOWS",
    "STANDARD_METRICS",
    "AgeWindow",
    "AnalyticsError",
    "AnalyticsHypothesis",
    "AnalyticsIntegrityError",
    "AnalyticsLearning",
    "AnalyticsReport",
    "AnalyticsStore",
    "AnalyticsStoreError",
    "AnalyzedDeliverable",
    "CausalAssessment",
    "CompetitorPublicReference",
    "ComparisonBasis",
    "ContentFeatures",
    "DataScope",
    "DataSource",
    "DateRange",
    "DeliverableComparison",
    "DeliverableKind",
    "DeliverableOutcome",
    "DeliverablePostmortem",
    "Direction",
    "EvidenceRequired",
    "EvidenceStrength",
    "ExecutionRecordKind",
    "ExecutionReference",
    "Expectation",
    "ExperimentResult",
    "ExperimentSpecification",
    "ExperimentStatus",
    "FeatureDimension",
    "FinanceRecordKind",
    "FinanceReference",
    "FormatBaseline",
    "GroupBy",
    "GroupedPerformance",
    "GuardrailOutcome",
    "HypothesisState",
    "KillCondition",
    "LearningScope",
    "LedgerViolation",
    "MeasurementCoverage",
    "MetricComparison",
    "MetricDefinition",
    "MetricKind",
    "MetricObservation",
    "MetricOutcome",
    "MetricRegistry",
    "MetricSummary",
    "ObservationSeries",
    "OutlierMethod",
    "OutlierRule",
    "OverclaimRefused",
    "PerformanceGroup",
    "Provenance",
    "ProvenanceViolation",
    "ResearchRecordKind",
    "ResearchReference",
    "Variable",
    "Verdict",
    "assert_integrity",
    "build_baseline",
    "build_report",
    "check_integrity",
    "compare_deliverables",
    "evaluate_experiment",
    "group_performance",
    "group_value",
    "observe",
    "promote",
    "standard_age_window",
    "summarise_metric",
]
