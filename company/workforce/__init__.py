"""Workforce and HR: what the company can do, what it is missing, and who proves it.

Read `company/workforce/README.md` first. The modules, in the order the data
flows through them:

    capabilities  The capability model: definitions, explicit relations, and
                  providers derived from org_registry.yaml rather than copied.
    coverage      Active capacity versus organizational capability, kept apart.
    gaps          A proven inability, with frequency evidence supplied, never
                  inferred.
    proposals     The decision table from gap to recommendation, ranked.
    roles         A proposed role: a full contract that has not been hired.
    evaluation    The cases a candidate must pass before anything else happens.
    shadow        Read, recommend, be compared. Never write.
    employment    The lifecycle and the evidence each edge costs.
    performance   Per-capability observation. There is no global score.
    necessity     Is a role still worth having? Evidence in, human decides.
    debt          Lightweight organizational-cost records.
    integrity     Every cross-record invariant, reported in one pass.
    store         Canonical JSON under a caller-supplied state directory.

Dependency direction, unchanged and one-way:

    ai_platform  <-  knowledge.company_os  <-  company  <-  company.workforce

Nothing here imports production code (race, sloped, marble3d, rendering,
godot), and no production module imports this - `company/README.md`, dependency
rule. Standard library only.

## What this package cannot do, by construction

It cannot hire, fire, activate, or archive anyone. Nothing here writes
`company/org_registry.yaml` or `company/permissions.yaml`; the strongest output
is a record in the `PROPOSED` state that a human reads. It cannot grant
authority: every restricted state fails closed at the cap in `permissions.yaml`,
and a role specification emits an empty `may_write` regardless of what it asked
for. It cannot decide that a need recurs: frequency is evidence a caller
supplies, and this package only refuses to let someone claim it without having
counted.

What is deliberately absent: an agent creator, automatic hiring or firing, a
prompt generator, a scheduler, a model API, embeddings, and any global employee
score. Constitution rule 17 - prove need before building.
"""

from company.workforce.capabilities import (
    DEFAULT_REGISTRY_PATH,
    Capability,
    CapabilityGraph,
    CapabilityRegistry,
    CapabilityRelation,
    CapabilityStatus,
    Criticality,
    RelationKind,
    ResolvedCapability,
    graph_to_dict,
    load_capability_graph,
)
from company.workforce.common import IDENTIFIER, RECORD_ID
from company.workforce.coverage import (
    CapabilityCoverage,
    CoverageLevel,
    CoverageReport,
    CoverageStatus,
    assess_coverage,
    organization_single_points_of_failure,
    uncovered_critical_capabilities,
)
from company.workforce.debt import (
    DebtKind,
    DebtSeverity,
    DebtStatus,
    OrganizationalDebt,
    detect_debt,
    duplicated_roles,
)
from company.workforce.employment import (
    ALLOWED_TRANSITIONS,
    PRODUCTION_WRITE_ACTIONS,
    EmploymentRecord,
    EmploymentState,
    EmploymentTransition,
    advance,
    assert_authority,
    assert_may_not_write_production,
    assert_transition,
    can_transition,
    history_violations,
    required_evidence_kinds,
    state_authority_cap,
)
from company.workforce.errors import (
    AuthorityViolation,
    LifecycleViolation,
    WorkforceError,
    WorkforceIntegrityError,
)
from company.workforce.evaluation import (
    MANDATORY_CASE_KINDS,
    CandidateEvaluation,
    EvaluationCase,
    EvaluationCaseKind,
    EvaluationOutcome,
    EvaluationResult,
    default_case_set,
)
from company.workforce.gaps import (
    CapabilityGap,
    FrequencyEvidence,
    GapStatus,
    GapTrigger,
    NeedFrequency,
    TriggerKind,
    Urgency,
    gap_from_coverage,
)
from company.workforce.integrity import assert_integrity, check_integrity
from company.workforce.necessity import (
    DEFAULT_POLICY,
    PROTECTIVE_SIGNALS,
    Direction,
    NecessityFinding,
    NecessityPolicy,
    NecessitySignal,
    RoleNecessityReview,
    review_role,
    review_to_proposal,
)
from company.workforce.performance import (
    CapabilityPerformance,
    EmployeePerformance,
    PerformanceObservation,
    TaskOutcome,
    employee_performance,
    resource_summary,
    summarise_observations,
)
from company.workforce.proposals import (
    ProposalOption,
    Recommendation,
    WorkforceProposal,
    propose_for_gap,
    rank_options,
    record_decision,
    requires_ceo_approval,
    retraining_candidates,
)
from company.workforce.roles import (
    ApprovalState,
    ResourceBudget,
    RoleSpecification,
    approve_role_specification,
)
from company.workforce.shadow import (
    ComparisonDimension,
    ComparisonVerdict,
    ShadowAssignment,
    ShadowComparison,
    shadow_scope_violations,
)
from company.workforce.store import WorkforceStore, WorkforceStoreError, write_all

__all__ = [
    "ALLOWED_TRANSITIONS",
    "DEFAULT_POLICY",
    "DEFAULT_REGISTRY_PATH",
    "IDENTIFIER",
    "MANDATORY_CASE_KINDS",
    "PRODUCTION_WRITE_ACTIONS",
    "PROTECTIVE_SIGNALS",
    "RECORD_ID",
    "ApprovalState",
    "AuthorityViolation",
    "Capability",
    "CapabilityCoverage",
    "CapabilityGap",
    "CapabilityGraph",
    "CapabilityPerformance",
    "CapabilityRegistry",
    "CapabilityRelation",
    "CapabilityStatus",
    "CandidateEvaluation",
    "ComparisonDimension",
    "ComparisonVerdict",
    "CoverageLevel",
    "CoverageReport",
    "CoverageStatus",
    "Criticality",
    "DebtKind",
    "DebtSeverity",
    "DebtStatus",
    "Direction",
    "EmployeePerformance",
    "EmploymentRecord",
    "EmploymentState",
    "EmploymentTransition",
    "EvaluationCase",
    "EvaluationCaseKind",
    "EvaluationOutcome",
    "EvaluationResult",
    "FrequencyEvidence",
    "GapStatus",
    "GapTrigger",
    "LifecycleViolation",
    "NecessityFinding",
    "NecessityPolicy",
    "NecessitySignal",
    "NeedFrequency",
    "OrganizationalDebt",
    "PerformanceObservation",
    "ProposalOption",
    "Recommendation",
    "RelationKind",
    "ResolvedCapability",
    "ResourceBudget",
    "RoleNecessityReview",
    "RoleSpecification",
    "ShadowAssignment",
    "ShadowComparison",
    "TaskOutcome",
    "TriggerKind",
    "Urgency",
    "WorkforceError",
    "WorkforceIntegrityError",
    "WorkforceProposal",
    "WorkforceStore",
    "WorkforceStoreError",
    "advance",
    "approve_role_specification",
    "assert_authority",
    "assert_integrity",
    "assert_may_not_write_production",
    "assert_transition",
    "assess_coverage",
    "can_transition",
    "check_integrity",
    "default_case_set",
    "detect_debt",
    "duplicated_roles",
    "employee_performance",
    "gap_from_coverage",
    "graph_to_dict",
    "history_violations",
    "load_capability_graph",
    "organization_single_points_of_failure",
    "propose_for_gap",
    "rank_options",
    "record_decision",
    "required_evidence_kinds",
    "requires_ceo_approval",
    "resource_summary",
    "retraining_candidates",
    "review_role",
    "review_to_proposal",
    "shadow_scope_violations",
    "state_authority_cap",
    "summarise_observations",
    "uncovered_critical_capabilities",
    "write_all",
]
