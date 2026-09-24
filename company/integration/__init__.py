"""The production integration gate: may Company OS cross into production yet?

Read `company/integration/README.md` first. The modules are:

    model       Four statuses, a check, a section, a blocker, a report. No score.
    policy      Which checks block and which are only visible, written down once.
    sources     Which directories are production, which are Company OS, parsed once.
    graph       Cycle detection over a plain mapping, and the two graphs fed to it.
    boundary    Import, write, network and delete findings, read off the syntax tree.
    probes      Behavioural probes that drive a Company OS guard to its edge.
    contracts   Drift in permissions.yaml, the no-subagent chain, the gating claim.
    suites      Test results the caller supplies, because the gate will not run them.
    checks      One function per condition, one verdict each.
    report      Assembly, blockers and rendering.
    store       Append-only reports under a caller-supplied directory.

## What this subsystem does not do

It does not wire Company OS into production, and a `READY` verdict does not
authorize anybody to. It evaluates conditions and reports them. Integration
remains a CEO decision that happens somewhere else, and
`ProductionIntegrationReadinessReport.authorizes_production_integration` is
False in every report this package can construct.

It also holds none of the authority it checks for: no network client, no
process spawn, no delete call, and no write outside a directory its caller
names. The gate is subject to its own conditions, and
`tests/test_company_integration_gate.py` runs them over this package too.

## Dependency direction

    ai_platform  <-  knowledge.company_os  <-  company.*  <-  company.integration

This package reads the other subsystems and is read by none of them. Nothing
here imports production code, and no production module imports this. Standard
library only.
"""

from .checks import GateInputs, GateScan, evaluate
from .dependencies import (
    CapsuleTestAudit,
    CapsuleTestFinding,
    DependencyGraph,
    DependencyRelation,
    GovernedSubsystem,
    ImpactSlice,
    UnresolvedDependency,
    audit_capsule_tests,
    build_dependency_graph,
    governed_production_subsystems,
)
from .contracts import (
    REQUIRED_RESERVED_ACTIONS,
    REQUIRED_REVIEW_TRIGGERS,
    ChainLink,
    ContractDrift,
    integration_still_gated,
    no_subagent_chain,
    reserved_action_drift,
    review_trigger_drift,
)
from .errors import (
    GateEvaluationError,
    IntegrationGateError,
    PolicyError,
    ReportStoreError,
)
from .graph import (
    capsule_dependency_graph,
    find_cycles,
    render_cycle,
    subsystem_import_graph,
    type_checking_edges,
)
from .model import (
    EvidenceKind,
    EvidenceSource,
    GateCategory,
    GateCheck,
    GateSection,
    GateStatus,
    IntegrationBlocker,
    ProductionIntegrationReadinessReport,
    Readiness,
    readiness_of,
)
from .policy import (
    ADVISORY_CHECKS,
    DEFAULT_POLICY,
    NOT_APPLICABLE_ALLOWED,
    POLICY_VERSION,
    REQUIRED_CHECKS,
    GatePolicy,
)
from .report import (
    AUTHORIZATION_NOTE,
    CEO_DECISION_CHECKS,
    assemble,
    blockers_for,
    build_report,
    render_text,
)
from .store import ReadinessReportStore
from .suites import (
    REQUIRED_SUITES,
    RequiredSuites,
    SuiteEvidence,
    SuiteOrigin,
    SuiteRequirement,
    SuiteResult,
    resolve_required_suites,
    undeclared_company_os_suites,
)

__all__ = [
    "CapsuleTestAudit",
    "CapsuleTestFinding",
    "DependencyGraph",
    "DependencyRelation",
    "GovernedSubsystem",
    "ImpactSlice",
    "UnresolvedDependency",
    "audit_capsule_tests",
    "build_dependency_graph",
    "governed_production_subsystems",
    "ADVISORY_CHECKS",
    "AUTHORIZATION_NOTE",
    "CEO_DECISION_CHECKS",
    "DEFAULT_POLICY",
    "NOT_APPLICABLE_ALLOWED",
    "POLICY_VERSION",
    "REQUIRED_CHECKS",
    "REQUIRED_RESERVED_ACTIONS",
    "REQUIRED_REVIEW_TRIGGERS",
    "REQUIRED_SUITES",
    "ChainLink",
    "ContractDrift",
    "EvidenceKind",
    "EvidenceSource",
    "GateCategory",
    "GateCheck",
    "GateEvaluationError",
    "GateInputs",
    "GatePolicy",
    "GateScan",
    "GateSection",
    "GateStatus",
    "IntegrationBlocker",
    "IntegrationGateError",
    "PolicyError",
    "ProductionIntegrationReadinessReport",
    "ReadinessReportStore",
    "Readiness",
    "ReportStoreError",
    "RequiredSuites",
    "SuiteEvidence",
    "SuiteOrigin",
    "SuiteRequirement",
    "SuiteResult",
    "assemble",
    "blockers_for",
    "build_report",
    "capsule_dependency_graph",
    "evaluate",
    "find_cycles",
    "integration_still_gated",
    "no_subagent_chain",
    "readiness_of",
    "render_cycle",
    "render_text",
    "reserved_action_drift",
    "resolve_required_suites",
    "review_trigger_drift",
    "subsystem_import_graph",
    "undeclared_company_os_suites",
    "type_checking_edges",
]
