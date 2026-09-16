"""Organizational Intelligence - Company OS v1.

The deterministic answer to one question the rest of Company OS cannot ask:
**is the company itself organized well?**

Evidence the other subsystems already produced goes in; signals, findings,
recommendations and change proposals come out; a person decides. Nothing here
hires, merges, archives, reassigns, reorganizes or edits a company contract, and
that is enforced by construction rather than by policy - see `README.md`.

Standard library only. No database, no embeddings, no external service, no model
call. Nothing here imports production code.
"""

from __future__ import annotations

from .automation import (
    ABSOLUTE_MINIMUM_INSTANCES,
    RepeatedWork,
    automation_candidate,
    automation_signal,
)
from .change import (
    CANONICAL_CONTRACTS,
    CAUSALITY_CAVEAT,
    SINGLE_OBSERVATION_CAVEAT,
    ApprovalAuthority,
    ChangeExperiment,
    ChangeOutcome,
    MetricComparison,
    OrganizationChangeProposal,
    OrganizationChangeReview,
    SuccessMetric,
    significant,
)
from .common import AUTOMATIC_MARKERS, rendered_configuration
from .errors import (
    AdvisoryViolation,
    OrgIntelligenceError,
    OrgIntelligenceIntegrityError,
)
from .findings import (
    COUNTEREVIDENCE_LIMITATION,
    EvidenceStrength,
    FindingCategory,
    OrganizationalFinding,
    build_finding,
    evidence_strength,
)
from .integrity import assert_integrity, check_integrity
from .management import (
    DEFAULT_MANAGEMENT_POLICY,
    DEFAULT_REGISTRY_REF,
    ManagementGraph,
    ManagementPolicy,
    management_signals,
)
from .priority import (
    PRIORITY_DIMENSIONS,
    DimensionValue,
    PriorityWeights,
    RecommendationPriority,
    prioritise,
    rank,
)
from .recommendations import (
    CONSTITUTIONAL_POLICIES,
    ORDINARY_OPTIMIZATION_TYPES,
    POLICY_RESERVED_ACTIONS,
    WORKFORCE_EQUIVALENT,
    Decision,
    OrganizationalRecommendation,
    RecommendationState,
    RecommendationType,
    Reversibility,
    RiskLevel,
    ceo_reserved_actions,
    record_decision,
    unreserved_actions,
)
from .research_evidence import (
    SINGLE_BATCH_LIMITATION,
    DEFAULT_RESEARCH_POLICY,
    ResearchEvidence,
    ResearchPolicy,
    research_signals,
)
from .resources import (
    DEFAULT_RESOURCE_POLICY,
    ResourceEvidence,
    ResourcePolicy,
    attempt_pattern,
    resource_signals,
)
from .review import OrganizationalReview, ReviewScope
from .signals import (
    SMALL_SAMPLE_CAVEAT,
    Direction,
    Measurement,
    OrganizationalSignal,
    SignalType,
    SubjectKind,
    signals_of,
)
from .store import OrgIntelligenceStore, OrgIntelligenceStoreError, write_all
from .window import COMPARABLE_LENGTH_TOLERANCE, ReviewWindow
from .workforce_evidence import (
    DEBT_SIGNAL_TYPES,
    DEFAULT_WORKFORCE_POLICY,
    WorkforcePolicy,
    acceptance_ratio,
    gap_recurrence,
    signals_from_coverage,
    signals_from_debt,
    signals_from_gaps,
    signals_from_necessity,
    signals_from_performance,
)

__all__ = [
    "ABSOLUTE_MINIMUM_INSTANCES",
    "AUTOMATIC_MARKERS",
    "AdvisoryViolation",
    "ApprovalAuthority",
    "CANONICAL_CONTRACTS",
    "CAUSALITY_CAVEAT",
    "COMPARABLE_LENGTH_TOLERANCE",
    "CONSTITUTIONAL_POLICIES",
    "COUNTEREVIDENCE_LIMITATION",
    "ChangeExperiment",
    "ChangeOutcome",
    "DEBT_SIGNAL_TYPES",
    "DEFAULT_MANAGEMENT_POLICY",
    "DEFAULT_REGISTRY_REF",
    "DEFAULT_RESEARCH_POLICY",
    "DEFAULT_RESOURCE_POLICY",
    "DEFAULT_WORKFORCE_POLICY",
    "Decision",
    "DimensionValue",
    "Direction",
    "EvidenceStrength",
    "FindingCategory",
    "ManagementGraph",
    "ManagementPolicy",
    "Measurement",
    "MetricComparison",
    "ORDINARY_OPTIMIZATION_TYPES",
    "OrgIntelligenceError",
    "OrgIntelligenceIntegrityError",
    "OrgIntelligenceStore",
    "OrgIntelligenceStoreError",
    "OrganizationChangeProposal",
    "OrganizationChangeReview",
    "OrganizationalFinding",
    "OrganizationalRecommendation",
    "OrganizationalReview",
    "OrganizationalSignal",
    "PRIORITY_DIMENSIONS",
    "POLICY_RESERVED_ACTIONS",
    "PriorityWeights",
    "RecommendationPriority",
    "RecommendationState",
    "RecommendationType",
    "RepeatedWork",
    "ResearchEvidence",
    "ResearchPolicy",
    "ResourceEvidence",
    "ResourcePolicy",
    "ReviewScope",
    "ReviewWindow",
    "Reversibility",
    "RiskLevel",
    "SINGLE_BATCH_LIMITATION",
    "SINGLE_OBSERVATION_CAVEAT",
    "SMALL_SAMPLE_CAVEAT",
    "SignalType",
    "SubjectKind",
    "SuccessMetric",
    "WORKFORCE_EQUIVALENT",
    "WorkforcePolicy",
    "acceptance_ratio",
    "assert_integrity",
    "attempt_pattern",
    "automation_candidate",
    "automation_signal",
    "build_finding",
    "ceo_reserved_actions",
    "check_integrity",
    "evidence_strength",
    "gap_recurrence",
    "management_signals",
    "prioritise",
    "rank",
    "record_decision",
    "rendered_configuration",
    "research_signals",
    "resource_signals",
    "significant",
    "signals_from_coverage",
    "signals_from_debt",
    "signals_from_gaps",
    "signals_from_necessity",
    "signals_from_performance",
    "signals_of",
    "unreserved_actions",
    "write_all",
]
