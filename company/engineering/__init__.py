"""The company engineering execution loop: CEO request to CEO result.

Read `company/engineering/README.md` first — in particular the paragraph on
what is automatic and what is a human-started session, because this package
does not do the thing its name suggests and says so at the top of its own
README.

    intake        A CEO objective -> a bounded work order, or DECISION REQUIRED.
    work_order    The authority ceiling. Immutable, fingerprinted, derived from.
    protected     The governance files, digested before the work and re-read after.
    plan          A proposal about method, refused if it widens the ceiling.
    lifecycle     The job state machine, with a bounded correction loop.
    review        Deterministic QA plus one independent reviewer, worst wins.
    gate_evidence The integration gate's verdict, read and never computed here.
    result        The one page the CEO reads.
    decision      APPROVE / REQUEST_CHANGES / REJECT, recorded and not acted on.
    store         The append-only history under a caller-supplied directory.
    orchestrator  One function per stage, each one a recorded move.

## Dependency direction

    ai_platform  <-  knowledge.company_os  <-  company.runtime  <-  company.engineering

and `company.dashboard` reads this package. Nothing here imports
`company.integration` or `company.dashboard`: the gate's verdict arrives as
supplied evidence, which keeps the subsystem graph acyclic and means this
package holds no code that can produce a favourable gate result.
`gate_evidence.py` explains both halves of that.

## What this package cannot do, structurally

No `subprocess`, no network, no writes outside a directory its caller names. It
cannot run pytest, run git, or start a developer session, because
`production.no_publishing_capability` is a required integration-gate check and
forbids process spawning across all of Company OS. The developer and reviewer
are independent top-level sessions a human starts, exactly as constitution
rule 3 already requires.
"""

from .common import assert_named_person
from .decision import DECISION_VERSION, CEODecision, CEOVerdict
from .errors import (
    AuthorityEscalation,
    EngineeringError,
    ProtectedSurfaceViolation,
    SelfApproval,
)
from .gate_evidence import (
    GATE_VERDICT_VERSION,
    GateBlocker,
    GateReadiness,
    GateVerdict,
    readiness_from,
)
from .intake import (
    CREDENTIAL_TRIGGERS,
    RESERVED_TRIGGERS,
    CEORequest,
    DecisionRequired,
    IntakeAssessment,
    IntakeOutcome,
    ScopeDerivation,
    assess_request,
    reserved_actions,
    screen_credentials,
    screen_reserved,
)
from .lifecycle import (
    ALLOWED_TRANSITIONS,
    CEO_STATES,
    JOB_VERSION,
    MAIN_SEQUENCE,
    TERMINAL_STATES,
    EngineeringJob,
    JobState,
    JobTransition,
    StageTiming,
)
from .orchestrator import (
    DeveloperBriefing,
    DeveloperResult,
    OpenedJob,
    ReviewBriefing,
    ReviewResult,
    accepted,
    ingest_developer_result,
    open_job,
    prepare_developer_session,
    prepare_review_session,
    publish_result,
    record_decision,
    record_gate,
    record_review,
)
from .plan import PLAN_VERSION, ImplementationPlan, PlanStep, derive_plan
from .protected import (
    DEFAULT_PROTECTED_PATHS,
    ProtectedFile,
    ProtectedSurface,
)
from .result import (
    NOT_AN_APPROVAL,
    RESULT_VERSION,
    EngineeringResult,
    ResultTest,
    ScopeUsage,
    SuiteScope,
)
from .review import (
    REVIEW_VERSION,
    SEVERITY_ORDER,
    CriterionFinding,
    EngineeringReview,
    FindingSeverity,
    ReviewFinding,
    ReviewOutcome,
    ReviewerAttestation,
    adjudicate,
    deterministic_findings,
)
from .store import (
    EngineeringRecordPointer,
    EngineeringStore,
    EngineeringStoreError,
)
from .attempt_ledger import (
    AttemptLedger,
    AttemptLedgerEntry,
    build_attempt_ledger,
)
from .work_order import (
    ALLOWED_CEILINGS,
    DEFAULT_MAX_DEVELOPER_ATTEMPTS,
    FORBIDDEN_BRANCHES,
    SPECIALIST_DOMAIN,
    WORK_ORDER_VERSION,
    EngineeringWorkOrder,
)

__all__ = [
    "ALLOWED_CEILINGS",
    "AttemptLedger",
    "AttemptLedgerEntry",
    "ALLOWED_TRANSITIONS",
    "CEO_STATES",
    "CREDENTIAL_TRIGGERS",
    "DECISION_VERSION",
    "DEFAULT_MAX_DEVELOPER_ATTEMPTS",
    "DEFAULT_PROTECTED_PATHS",
    "FORBIDDEN_BRANCHES",
    "GATE_VERDICT_VERSION",
    "JOB_VERSION",
    "MAIN_SEQUENCE",
    "NOT_AN_APPROVAL",
    "PLAN_VERSION",
    "RESERVED_TRIGGERS",
    "RESULT_VERSION",
    "REVIEW_VERSION",
    "SEVERITY_ORDER",
    "SPECIALIST_DOMAIN",
    "TERMINAL_STATES",
    "WORK_ORDER_VERSION",
    "AuthorityEscalation",
    "CEODecision",
    "CEORequest",
    "CEOVerdict",
    "CriterionFinding",
    "DecisionRequired",
    "DeveloperBriefing",
    "DeveloperResult",
    "EngineeringError",
    "EngineeringJob",
    "EngineeringRecordPointer",
    "EngineeringResult",
    "EngineeringReview",
    "EngineeringStore",
    "EngineeringStoreError",
    "EngineeringWorkOrder",
    "FindingSeverity",
    "GateBlocker",
    "GateReadiness",
    "GateVerdict",
    "ImplementationPlan",
    "IntakeAssessment",
    "IntakeOutcome",
    "JobState",
    "JobTransition",
    "OpenedJob",
    "PlanStep",
    "ProtectedFile",
    "ProtectedSurface",
    "ProtectedSurfaceViolation",
    "ResultTest",
    "ReviewBriefing",
    "ReviewFinding",
    "ReviewOutcome",
    "ReviewResult",
    "ReviewerAttestation",
    "ScopeDerivation",
    "ScopeUsage",
    "SelfApproval",
    "StageTiming",
    "SuiteScope",
    "accepted",
    "adjudicate",
    "assess_request",
    "assert_named_person",
    "build_attempt_ledger",
    "derive_plan",
    "deterministic_findings",
    "ingest_developer_result",
    "open_job",
    "prepare_developer_session",
    "prepare_review_session",
    "publish_result",
    "readiness_from",
    "record_decision",
    "record_gate",
    "record_review",
    "reserved_actions",
    "screen_credentials",
    "screen_reserved",
]
