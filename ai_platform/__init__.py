"""The AI platform: route a task, bound its context, record what it cost.

Read `ai_platform/README.md` first - it is the bootstrap contract, and this
package implements four of its pieces and deliberately none of the others.

    resource_classes  Six provider-agnostic task classes (A-F) and the
                      deterministic classifier that picks one.
    context_manifest  What a session is handed, as references and never bodies.
    usage             What the task cost, in a form that survives a provider
                      exposing no token counts.
    policy            The execution policy, and the two-key lock that keeps
                      nested agents unreachable in Bootstrap Mode.
    references        The one guard both manifests and knowledge records use to
                      refuse embedded content in a pointer field.
    serde             Canonical JSON in, canonical JSON out.

Dependency direction inside the control plane is one-way:
`knowledge.company_os` imports `ai_platform` (for `references` and `serde`) and
nothing here imports `knowledge`. Neither package imports production code, and
no production module may import either (`company/README.md`, dependency rule).

What is deliberately absent: a provider adapter, a scheduler, a prompt
template, a vector store, an orchestration loop. Constitution rule 17 - prove
need before building - and none of them has been needed yet.
"""

from ai_platform.context_manifest import ContextKind, ContextManifest, ContextRef
from ai_platform.policy import (
    BOOTSTRAP_MODE,
    BOOTSTRAP_POLICY,
    ExecutionPolicy,
    PolicyConfigError,
    SubagentPolicyViolation,
)
from ai_platform.references import MAX_REF_CHARS, ReferenceViolation, assert_reference
from ai_platform.resource_classes import (
    RESOURCE_CLASSES,
    Classification,
    ContextBudget,
    ReasoningClass,
    ResourceClass,
    Risk,
    TaskSignals,
    classify,
    escalate,
    resource_class,
)
from ai_platform.usage import (
    Outcome,
    ResourceSummary,
    ResourceUsageRecord,
    UsageLedger,
    UsageRecordError,
    UsageUnit,
)

__all__ = [
    "BOOTSTRAP_MODE",
    "BOOTSTRAP_POLICY",
    "MAX_REF_CHARS",
    "RESOURCE_CLASSES",
    "Classification",
    "ContextBudget",
    "ContextKind",
    "ContextManifest",
    "ContextRef",
    "ExecutionPolicy",
    "Outcome",
    "PolicyConfigError",
    "ReasoningClass",
    "ReferenceViolation",
    "ResourceClass",
    "ResourceSummary",
    "ResourceUsageRecord",
    "Risk",
    "SubagentPolicyViolation",
    "TaskSignals",
    "UsageLedger",
    "UsageRecordError",
    "UsageUnit",
    "assert_reference",
    "classify",
    "escalate",
    "resource_class",
]
