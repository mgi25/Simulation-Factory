"""What an external session is actually handed, as one compact JSON object.

The engineering brief lists what developer execution must receive: the
objective, the authorized scope, the relevant repository context, the
architecture constraints and the acceptance criteria. All five already exist as
records — this module arranges them into one payload and adds nothing.

It reuses `company.runtime.transport.SessionTransportBundle` for the execution
half (packet reference, immutable authority reference, effective context
fingerprint, expansion instructions, receipt version) and adds the two things a
work order knows and a packet does not:

- **`escalate_instead_of` —** the list from section 6 of the brief, spelled out
  in the briefing rather than left in a document, because a session that never
  reads the document is the one that widens its own scope. Each line names a
  situation in which the session must stop and return a receipt reporting the
  escalation instead of proceeding.
- **`protected_paths` —** the governance surface, named so the session knows it
  is measured. The digests are deliberately *not* included: a session that
  knows the digests learns nothing useful, and a briefing is a set of pointers.
- **`efficiency` —** the execution strategy Company OS selected for this job,
  including model tier, context budget, checkpoint rule, output reduction
  directives and resource ceilings. The operator applies these with the
  runner's existing flags; Company OS determines and records them.

## Still references, never bodies

Nothing here reads a file the payload points at. `context_refs` are the work
order's `ContextRef` keys, which is what makes the briefing a few thousand
characters while the material behind it runs to hundreds of thousands.
`size_chars` reports the former so the ratio can be watched rather than
assumed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_platform.serde import to_jsonable
from company.efficiency.strategy import select_strategy
from company.runtime.transport import SessionTransportBundle

from .work_order import EngineeringWorkOrder

if TYPE_CHECKING:  # avoids an import cycle with the orchestrator's dataclasses
    from .orchestrator import DeveloperBriefing, ReviewBriefing


# The situations in which a session stops and escalates instead of continuing.
# Section 6 of the engineering brief, as instructions a session can follow.
ESCALATE_INSTEAD_OF: tuple[str, ...] = (
    "changing architecture outside the authorized paths",
    "adding a dependency the work order did not authorize",
    "reading or using any credential, token or secret",
    "widening the objective beyond what the work order states",
    "editing any protected governance path",
    "deciding a business question the work order leaves open",
    "any destructive operation on repository or company data",
    "merging, deploying, publishing or tagging anything",
)

# What a reviewer does instead. A reviewer that finds a defect reports it.
REVIEW_INSTRUCTIONS: tuple[str, ...] = (
    "read the work order, the diff, the reported tests and the changed paths",
    "answer every acceptance criterion with a reference to what satisfies it",
    "report one finding per defect, with a severity and a reference",
    "change nothing: this packet grants no writable path",
    "return pass, changes_required or blocked, and never an approval",
)


def _work_order_terms(order: EngineeringWorkOrder) -> dict[str, Any]:
    """The work order as terms, with its scope and its refusals in one place."""
    return {
        "work_order_id": order.work_order_id,
        "work_order_fingerprint": order.fingerprint(),
        "objective": order.objective,
        "requested_by": order.requested_by,
        "authorized_on": order.authorized_on.isoformat(),
        "authorized_branch": order.authorized_branch,
        "base_commit": order.base_commit,
        "authorized_paths": list(order.authorized_paths),
        "forbidden_paths": list(order.forbidden_paths),
        "protected_paths": list(order.protected.paths),
        "acceptance_criteria": list(order.acceptance_criteria),
        "constraints": list(order.constraints),
        "required_tests": list(order.required_tests),
        "context_refs": [ref.key for ref in order.context_refs],
        "max_developer_attempts": order.max_developer_attempts,
        "escalate_instead_of": list(ESCALATE_INSTEAD_OF),
    }


def _efficiency_directives(
    order: EngineeringWorkOrder,
    reasoning_class_value: str,
    max_context_refs: int,
    *,
    is_review: bool = False,
) -> dict[str, Any]:
    """Compute execution strategy from work order properties and emit as directives.

    The strategy is deterministic: the same work order always produces the same
    directives.  The operator applies model tier and resource ceilings using
    the runner's existing flags; Company OS determines and records them.
    """
    from ai_platform.resource_classes import ReasoningClass

    strategy = select_strategy(
        ReasoningClass(reasoning_class_value),
        order.risk,
        evidence_required=order.evidence_required,
        max_context_refs=max_context_refs,
        is_review=is_review,
    )
    directives = strategy.to_dict()
    directives["operator_applied"] = True
    directives["note"] = (
        "Company OS selected this execution strategy. The operator applies "
        "model_tier and resource_ceiling using the runner's --model and "
        "--max-turns flags. These are not advisory; the session should stop "
        "and escalate before exceeding the resource ceiling."
    )
    return directives


def developer_briefing_payload(briefing: "DeveloperBriefing") -> dict[str, Any]:
    """Everything an external developer session needs, and nothing else."""
    packet = briefing.packet
    bundle = SessionTransportBundle.create(
        packet,
        briefing.prepared.pointer,
        briefing.prepared.authority,
        briefing.prepared.authority_pointer,
        briefing.ledger,
    )
    return {
        "role": "developer",
        "employee": briefing.employee,
        "state": briefing.job.state.value,
        "work_order": _work_order_terms(briefing.work_order),
        "packet": packet.to_dict(),
        "packet_fingerprint": packet.fingerprint(),
        "transport": bundle.to_dict(),
        "size_chars": packet.size_chars(),
        "persisted": {
            "packet": briefing.prepared.pointer.to_dict(),
            "authority": briefing.prepared.authority_pointer.to_dict(),
            "job": briefing.job_pointer.to_dict(),
        },
        "efficiency": _efficiency_directives(
            briefing.work_order,
            packet.reasoning_class.value,
            len(packet.context_refs),
            is_review=False,
        ),
    }


def review_briefing_payload(briefing: "ReviewBriefing") -> dict[str, Any]:
    """Everything an external reviewer session needs, read-only by construction."""
    packet = briefing.packet
    bundle = SessionTransportBundle.create(
        packet,
        briefing.prepared.pointer,
        briefing.prepared.authority,
        briefing.prepared.authority_pointer,
        briefing.ledger,
    )
    return {
        "role": "reviewer",
        "reviewer": briefing.reviewer,
        "implementer": briefing.implementer,
        "state": briefing.job.state.value,
        "read_only": packet.path_scope.read_only,
        "work_order": _work_order_terms(briefing.work_order),
        "review_instructions": list(REVIEW_INSTRUCTIONS),
        "packet": packet.to_dict(),
        "packet_fingerprint": packet.fingerprint(),
        "transport": bundle.to_dict(),
        "size_chars": packet.size_chars(),
        "persisted": {
            "packet": briefing.prepared.pointer.to_dict(),
            "authority": briefing.prepared.authority_pointer.to_dict(),
            "job": briefing.job_pointer.to_dict(),
        },
        "efficiency": _efficiency_directives(
            briefing.work_order,
            packet.reasoning_class.value,
            len(packet.context_refs),
            is_review=True,
        ),
    }


def payload_json(payload: dict[str, Any]) -> Any:
    return to_jsonable(payload)


__all__ = [
    "ESCALATE_INSTEAD_OF",
    "REVIEW_INSTRUCTIONS",
    "developer_briefing_payload",
    "payload_json",
    "review_briefing_payload",
]
