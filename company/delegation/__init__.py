"""Executive delegation and management by exception, in shadow.

The one-paragraph version: the CEO should set objectives, constraints, budgets
and risk tolerance, and then receive outcomes and exceptions. Everything
between those two points is what this package models — which seat owns an
action, whether that seat could decide it, where it escalates when it could
not, and which of the results the CEO actually has to see.

**It decides nothing.** Every record here refuses to claim authority to act,
the policy refuses to leave shadow mode, and `company.delegation.shadow` probes
the canonical CEO stop semantics on every run to prove they are still the only
thing that closes an engineering job. Turning delegation on is
`change_delegation_policy`, which this package reserves to the CEO
unconditionally and holds no capability to perform.

## Where to start reading

| Question | Module |
|---|---|
| What can be decided at all? | `actions.py` |
| Who is there to decide it? | `org.py` |
| What may each seat decide? | `policy.py`, `company/delegation_policy.yaml` |
| What does the money allow? | `budget.py` |
| What is the answer? | `authority.py` |
| Does the CEO have to see it? | `exceptions.py` |
| What gets written down? | `record.py`, `store.py` |
| What does the CEO read? | `brief.py` |
| Why are we doing this at all? | `objectives.py` |
| Does it match what really happened? | `scenarios.py` |
| Is the gate still up? | `shadow.py` |
"""

from __future__ import annotations

from .actions import (
    RESERVED_AS,
    RESERVED_HERE,
    ActionType,
    ReservationDrift,
    parse_action,
    reservation_drift,
    reserved_action_types,
)
from .authority import (
    AuthorityDecision,
    AuthorityRequest,
    ChainStep,
    Decision,
    Insufficiency,
    evaluate,
    evaluate_all,
)
from .brief import ExecutiveBrief, brief_from_records, build_brief, portfolio_spend
from .deployment import (
    DEPLOYMENT_POLICY,
    DeploymentClass,
    DeploymentDecision,
    DeploymentKind,
    DeploymentPolicy,
    classification_of,
    policy_table,
)
from .metrics import (
    DecisionOutcome,
    ManagementMetrics,
    ManagementReport,
    measure,
    spend_of,
)
from .budget import (
    BudgetFinding,
    BudgetLadder,
    BudgetLevel,
    BudgetScope,
    money_from_text,
)
from .errors import AuthorityViolation, DelegationError, ShadowModeViolation
from .exceptions import (
    ExceptionClass,
    ExceptionContext,
    ExceptionReport,
    ManagementException,
    classify,
)
from .candidates import (
    CandidateRegister,
    CandidateSource,
    CandidateStatus,
    WorkCandidate,
    load_seed_register,
    propose_candidate,
    register_from,
)
from .planning import (
    ELIGIBILITY_CHECKS,
    CandidateEligibility,
    EligibilityCheck,
    PlanningResult,
    WorkOrderProposal,
    assess_candidate,
    eligible_candidates,
    propose_work_order,
    select_work,
)
from .planning_record import PlanningDecisionRecord, PlanningOutcome
from .objectives import (
    ExecutivePlan,
    Objective,
    ObjectiveLevel,
    ObjectiveTree,
    PlanningEnvelope,
    assert_within_intent,
    decompose,
    envelope_violations,
)
from .org import (
    CEO_SEAT,
    Hierarchy,
    Seat,
    SeatAvailability,
    SeatKind,
    SeatStanding,
)
from .policy import (
    POLICY_VERSION,
    DelegatedAuthority,
    DelegationMode,
    DelegationPolicy,
    load_delegation_policy,
    parse_risk,
    risk_rank,
)
from .record import ExecutiveDecisionRecord, record_decision
from .scenarios import (
    CONTROL_SCENARIOS,
    SCENARIOS,
    ReplayResult,
    Scenario,
    replay,
    summarise,
)
from .shadow import ShadowCheck, ShadowReport, assert_shadow_mode, verify_shadow_mode
from .store import DelegationStore, DelegationStoreError


__all__ = [
    "CEO_SEAT",
    "CONTROL_SCENARIOS",
    "DEPLOYMENT_POLICY",
    "DecisionOutcome",
    "DeploymentClass",
    "DeploymentDecision",
    "DeploymentKind",
    "DeploymentPolicy",
    "ManagementMetrics",
    "ManagementReport",
    "classification_of",
    "measure",
    "policy_table",
    "spend_of",
    "POLICY_VERSION",
    "RESERVED_AS",
    "RESERVED_HERE",
    "SCENARIOS",
    "ActionType",
    "AuthorityDecision",
    "AuthorityRequest",
    "AuthorityViolation",
    "BudgetFinding",
    "BudgetLadder",
    "BudgetLevel",
    "BudgetScope",
    "ChainStep",
    "Decision",
    "DelegatedAuthority",
    "DelegationError",
    "DelegationMode",
    "DelegationPolicy",
    "DelegationStore",
    "DelegationStoreError",
    "ExceptionClass",
    "ExceptionContext",
    "ExceptionReport",
    "ExecutiveBrief",
    "ExecutiveDecisionRecord",
    "ExecutivePlan",
    "Hierarchy",
    "Insufficiency",
    "ManagementException",
    "Objective",
    "ObjectiveLevel",
    "ObjectiveTree",
    "PlanningEnvelope",
    "ReplayResult",
    "ReservationDrift",
    "Scenario",
    "Seat",
    "SeatAvailability",
    "SeatKind",
    "SeatStanding",
    "ShadowCheck",
    "ShadowModeViolation",
    "ShadowReport",
    "assert_shadow_mode",
    "assert_within_intent",
    "brief_from_records",
    "build_brief",
    "classify",
    "decompose",
    "envelope_violations",
    "evaluate",
    "evaluate_all",
    "load_delegation_policy",
    "money_from_text",
    "parse_action",
    "parse_risk",
    "portfolio_spend",
    "record_decision",
    "replay",
    "reservation_drift",
    "reserved_action_types",
    "risk_rank",
    "summarise",
    "verify_shadow_mode",
    "CandidateEligibility",
    "CandidateRegister",
    "CandidateSource",
    "CandidateStatus",
    "ELIGIBILITY_CHECKS",
    "EligibilityCheck",
    "PlanningDecisionRecord",
    "PlanningOutcome",
    "PlanningResult",
    "WorkCandidate",
    "WorkOrderProposal",
    "assess_candidate",
    "eligible_candidates",
    "load_seed_register",
    "propose_candidate",
    "propose_work_order",
    "register_from",
    "select_work",
]
