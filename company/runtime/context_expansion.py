"""Audited, reference-only context expansion for a prepared session.

The packet is the prediction: it records the context Company OS expected to be
enough.  This module never changes that packet.  It records explicit requests,
deterministic decisions, and an append-only ledger whose approved references
form the effective context beside the original packet.

No record contains or resolves reference bodies.  Policy evaluation lives in
``context_expansion_policy`` so these identities remain pure data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.policy import SubagentPolicyViolation
from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .errors import LifecycleError
from .packets import ExecutorHint, SessionPacket


_FINGERPRINT = re.compile(r"[0-9a-f]{16}")
_VAGUE_REASONS = frozenset(
    {
        "context",
        "more context",
        "need context",
        "need more context",
        "needs context",
        "needs more context",
    }
)
_MAX_REASON_CHARS = 500


class ExpansionOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ALREADY_PRESENT = "already_present"


@dataclass(frozen=True)
class ContextExpansionRequest:
    """One executor's bounded request for additional pointers, never contents."""

    task_id: str
    packet_fingerprint: str
    request_id: str
    requested_refs: tuple[ContextRef, ...]
    reason: str
    requesting_executor: ExecutorHint
    sequence: int
    required_to_continue: bool
    no_subagents: bool = True

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "context_expansion.task_id")
        assert_reference(self.request_id, "context_expansion.request_id")
        _assert_fingerprint(
            self.packet_fingerprint, "context_expansion.packet_fingerprint"
        )
        if not isinstance(self.requested_refs, tuple) or not self.requested_refs:
            raise LifecycleError(
                "context_expansion.requested_refs must be a non-empty tuple of ContextRef values"
            )
        if any(not isinstance(ref, ContextRef) for ref in self.requested_refs):
            raise LifecycleError(
                "context_expansion.requested_refs must contain ContextRef values"
            )
        keys = tuple(ref.key for ref in self.requested_refs)
        if len(keys) != len(set(keys)):
            raise LifecycleError(
                "context_expansion.requested_refs must not repeat a reference"
            )
        _assert_specific_reason(self.reason, "context_expansion.reason")
        for index, ref in enumerate(self.requested_refs):
            _assert_specific_reason(
                ref.reason, f"context_expansion.requested_refs[{index}].reason"
            )
        if not isinstance(self.requesting_executor, ExecutorHint):
            raise LifecycleError(
                "context_expansion.requesting_executor must be an ExecutorHint value"
            )
        _assert_positive_integer(self.sequence, "context_expansion.sequence")
        if not isinstance(self.required_to_continue, bool):
            raise LifecycleError(
                "context_expansion.required_to_continue must be a boolean"
            )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "context_expansion.no_subagents must be true; requesting context does "
                "not grant nested-agent authority"
            )
        object.__setattr__(
            self,
            "requested_refs",
            tuple(sorted(self.requested_refs, key=lambda ref: ref.key)),
        )

    @property
    def requested_kinds(self) -> tuple[ContextKind, ...]:
        return tuple(ref.kind for ref in self.requested_refs)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ContextExpansionRequest":
        _assert_mapping_fields(data, cls, "context expansion request")
        return cls(
            task_id=_required_string(data, "task_id"),
            packet_fingerprint=_required_string(data, "packet_fingerprint"),
            request_id=_required_string(data, "request_id"),
            requested_refs=_context_refs(data.get("requested_refs"), "requested_refs"),
            reason=_required_string(data, "reason"),
            requesting_executor=_enum(
                ExecutorHint, data.get("requesting_executor"), "requesting_executor"
            ),
            sequence=_integer(data.get("sequence"), "sequence"),
            required_to_continue=_boolean(
                data.get("required_to_continue"), "required_to_continue"
            ),
            no_subagents=_boolean(data.get("no_subagents", True), "no_subagents"),
        )


@dataclass(frozen=True)
class ContextRefRejection:
    requested_ref: ContextRef
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.requested_ref, ContextRef):
            raise LifecycleError("context expansion rejection must name a ContextRef")
        assert_text(self.reason, "context expansion rejection reason")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ContextRefRejection":
        if not isinstance(data, Mapping):
            raise LifecycleError("context expansion rejection must be a mapping")
        unknown = sorted(set(data) - {"requested_ref", "reason"})
        if unknown:
            raise LifecycleError(
                "context expansion rejection has unknown field(s): "
                + ", ".join(unknown)
            )
        refs = _context_refs((data.get("requested_ref"),), "requested_ref")
        return cls(refs[0], _required_string(data, "reason"))


@dataclass(frozen=True)
class ContextExpansionDecision:
    """The deterministic disposition of one expansion request."""

    task_id: str
    packet_fingerprint: str
    request_id: str
    request_fingerprint: str
    sequence: int
    required_to_continue: bool
    outcome: ExpansionOutcome
    approved_refs: tuple[ContextRef, ...]
    rejected_refs: tuple[ContextRefRejection, ...]
    already_present_refs: tuple[str, ...]
    previous_context_fingerprint: str
    resulting_context_fingerprint: str
    no_subagents: bool = True

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "context_expansion_decision.task_id")
        assert_reference(self.request_id, "context_expansion_decision.request_id")
        for name in (
            "packet_fingerprint",
            "request_fingerprint",
            "previous_context_fingerprint",
            "resulting_context_fingerprint",
        ):
            _assert_fingerprint(
                getattr(self, name), f"context_expansion_decision.{name}"
            )
        _assert_positive_integer(self.sequence, "context_expansion_decision.sequence")
        if not isinstance(self.required_to_continue, bool):
            raise LifecycleError(
                "context_expansion_decision.required_to_continue must be a boolean"
            )
        if not isinstance(self.outcome, ExpansionOutcome):
            raise LifecycleError(
                "context_expansion_decision.outcome must be an ExpansionOutcome value"
            )
        if not isinstance(self.approved_refs, tuple) or any(
            not isinstance(ref, ContextRef) for ref in self.approved_refs
        ):
            raise LifecycleError(
                "context_expansion_decision.approved_refs must contain ContextRef values"
            )
        if not isinstance(self.rejected_refs, tuple) or any(
            not isinstance(item, ContextRefRejection) for item in self.rejected_refs
        ):
            raise LifecycleError(
                "context_expansion_decision.rejected_refs must contain rejections"
            )
        if not isinstance(self.already_present_refs, tuple) or any(
            not isinstance(key, str) or not key for key in self.already_present_refs
        ):
            raise LifecycleError(
                "context_expansion_decision.already_present_refs must be reference keys"
            )
        approved_keys = tuple(ref.key for ref in self.approved_refs)
        rejected_keys = tuple(item.requested_ref.key for item in self.rejected_refs)
        categories = approved_keys + rejected_keys + self.already_present_refs
        if len(categories) != len(set(categories)):
            raise LifecycleError(
                "a context expansion reference must have exactly one decision"
            )
        expected = _decision_outcome(
            self.approved_refs, self.rejected_refs, self.already_present_refs
        )
        if self.outcome is not expected:
            raise LifecycleError(
                f"context expansion outcome {self.outcome.value} does not match its refs; "
                f"expected {expected.value}"
            )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "context_expansion_decision.no_subagents must be true"
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ContextExpansionDecision":
        _assert_mapping_fields(data, cls, "context expansion decision")
        rejected = data.get("rejected_refs", ())
        if isinstance(rejected, (str, bytes)) or not isinstance(
            rejected, (list, tuple)
        ):
            raise LifecycleError(
                "context expansion decision rejected_refs must be a list"
            )
        already = _string_tuple(
            data.get("already_present_refs"), "already_present_refs"
        )
        return cls(
            task_id=_required_string(data, "task_id"),
            packet_fingerprint=_required_string(data, "packet_fingerprint"),
            request_id=_required_string(data, "request_id"),
            request_fingerprint=_required_string(data, "request_fingerprint"),
            sequence=_integer(data.get("sequence"), "sequence"),
            required_to_continue=_boolean(
                data.get("required_to_continue"), "required_to_continue"
            ),
            outcome=_enum(ExpansionOutcome, data.get("outcome"), "outcome"),
            approved_refs=_context_refs(data.get("approved_refs", ()), "approved_refs"),
            rejected_refs=tuple(
                ContextRefRejection.from_mapping(item) for item in rejected
            ),
            already_present_refs=already,
            previous_context_fingerprint=_required_string(
                data, "previous_context_fingerprint"
            ),
            resulting_context_fingerprint=_required_string(
                data, "resulting_context_fingerprint"
            ),
            no_subagents=_boolean(data.get("no_subagents", True), "no_subagents"),
        )


@dataclass(frozen=True)
class ContextExpansionLedger:
    """Approved expansion history beside one immutable original packet."""

    task_id: str
    packet_fingerprint: str
    initial_context_fingerprint: str
    decisions: tuple[ContextExpansionDecision, ...] = ()
    no_subagents: bool = True

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "context_expansion_ledger.task_id")
        _assert_fingerprint(
            self.packet_fingerprint, "context_expansion_ledger.packet_fingerprint"
        )
        _assert_fingerprint(
            self.initial_context_fingerprint,
            "context_expansion_ledger.initial_context_fingerprint",
        )
        if not isinstance(self.decisions, tuple) or any(
            not isinstance(item, ContextExpansionDecision) for item in self.decisions
        ):
            raise LifecycleError(
                "context_expansion_ledger.decisions must contain ContextExpansionDecision values"
            )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "context_expansion_ledger.no_subagents must be true"
            )

        expected_previous = self.initial_context_fingerprint
        approved: list[ContextRef] = []
        seen: set[str] = set()
        for expected_sequence, decision in enumerate(self.decisions, start=1):
            if (
                decision.task_id != self.task_id
                or decision.packet_fingerprint != self.packet_fingerprint
            ):
                raise LifecycleError(
                    "context expansion decision belongs to another task or packet"
                )
            if decision.sequence != expected_sequence:
                raise LifecycleError(
                    "context expansion decision sequence must be contiguous from 1"
                )
            if decision.previous_context_fingerprint != expected_previous:
                raise LifecycleError(
                    "context expansion decision breaks the fingerprint chain"
                )
            for ref in decision.approved_refs:
                if ref.key in seen:
                    raise LifecycleError(
                        f"context expansion ledger approves {ref.key} more than once"
                    )
                seen.add(ref.key)
                approved.append(ref)
            expected_result = effective_context_fingerprint(
                self.initial_context_fingerprint, tuple(approved)
            )
            if decision.resulting_context_fingerprint != expected_result:
                raise LifecycleError(
                    "context expansion decision has an invalid resulting fingerprint"
                )
            expected_previous = expected_result

    @classmethod
    def for_packet(
        cls,
        packet: SessionPacket,
        decisions: tuple[ContextExpansionDecision, ...] = (),
    ) -> "ContextExpansionLedger":
        return cls(
            task_id=packet.task_id,
            packet_fingerprint=packet.fingerprint(),
            initial_context_fingerprint=packet.context_fingerprint,
            decisions=decisions,
        )

    @property
    def approved_refs(self) -> tuple[ContextRef, ...]:
        return tuple(
            ref for decision in self.decisions for ref in decision.approved_refs
        )

    @property
    def rejected_ref_keys(self) -> tuple[str, ...]:
        keys = (
            item.requested_ref.key
            for decision in self.decisions
            for item in decision.rejected_refs
        )
        return tuple(dict.fromkeys(keys))

    @property
    def expansion_count(self) -> int:
        return sum(bool(decision.approved_refs) for decision in self.decisions)

    @property
    def required_expansion_count(self) -> int:
        return sum(
            bool(decision.approved_refs) and decision.required_to_continue
            for decision in self.decisions
        )

    @property
    def expansion_chars(self) -> int:
        return sum(
            len(ref.key) + len(ref.reason) + len(ref.digest)
            for ref in self.approved_refs
        )

    @property
    def effective_context_fingerprint(self) -> str:
        if not self.decisions:
            return self.initial_context_fingerprint
        return self.decisions[-1].resulting_context_fingerprint

    def effective_refs(self, packet: SessionPacket) -> tuple[ContextRef, ...]:
        self.assert_for_packet(packet)
        return packet.context_refs + self.approved_refs

    def effective_keys(self, packet: SessionPacket) -> tuple[str, ...]:
        return tuple(ref.key for ref in self.effective_refs(packet))

    def with_decision(
        self, decision: ContextExpansionDecision
    ) -> "ContextExpansionLedger":
        return ContextExpansionLedger(
            task_id=self.task_id,
            packet_fingerprint=self.packet_fingerprint,
            initial_context_fingerprint=self.initial_context_fingerprint,
            decisions=self.decisions + (decision,),
        )

    def assert_for_packet(self, packet: SessionPacket) -> None:
        if (
            self.task_id != packet.task_id
            or self.packet_fingerprint != packet.fingerprint()
        ):
            raise LifecycleError(
                "context expansion ledger belongs to another task or packet"
            )
        if self.initial_context_fingerprint != packet.context_fingerprint:
            raise LifecycleError(
                "context expansion ledger does not begin at the packet's context fingerprint"
            )

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "task_id": self.task_id,
                "packet_fingerprint": self.packet_fingerprint,
                "initial_context_fingerprint": self.initial_context_fingerprint,
                "decision_fingerprints": tuple(
                    item.fingerprint() for item in self.decisions
                ),
            }
        )


def effective_context_fingerprint(
    initial_context_fingerprint: str, approved_refs: tuple[ContextRef, ...]
) -> str:
    _assert_fingerprint(initial_context_fingerprint, "initial_context_fingerprint")
    if not approved_refs:
        return initial_context_fingerprint
    return _fingerprint(
        {
            "initial_context_fingerprint": initial_context_fingerprint,
            "approved_expansion_refs": approved_refs,
        }
    )


def _decision_outcome(
    approved: tuple[ContextRef, ...],
    rejected: tuple[ContextRefRejection, ...],
    already: tuple[str, ...],
) -> ExpansionOutcome:
    if approved:
        return ExpansionOutcome.APPROVED
    if already and not rejected:
        return ExpansionOutcome.ALREADY_PRESENT
    return ExpansionOutcome.REJECTED


def _assert_specific_reason(value: str, field: str) -> None:
    assert_text(value, field)
    if "\n" in value or "\r" in value or len(value) > _MAX_REASON_CHARS:
        raise LifecycleError(
            f"{field} must be one compact line of at most {_MAX_REASON_CHARS} characters"
        )
    normalised = " ".join(value.casefold().strip().rstrip(".").split())
    if normalised in _VAGUE_REASONS:
        raise LifecycleError(
            f"{field} must state the missing fact, not merely 'need more context'"
        )


def _assert_fingerprint(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _FINGERPRINT.fullmatch(value):
        raise LifecycleError(f"{field} must be a 16-character lowercase hex digest")


def _assert_positive_integer(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LifecycleError(f"{field} must be a positive integer")


def _assert_mapping_fields(data: Mapping[str, Any], cls: type[Any], label: str) -> None:
    if not isinstance(data, Mapping):
        raise LifecycleError(f"{label} must be a mapping")
    unknown = sorted(set(data) - set(cls.__dataclass_fields__))
    if unknown:
        raise LifecycleError(f"{label} has unknown field(s): " + ", ".join(unknown))


def _context_refs(value: Any, field: str) -> tuple[ContextRef, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise LifecycleError(f"context expansion {field} must be a list")
    return tuple(
        _context_ref(item, f"{field}[{index}]") for index, item in enumerate(value)
    )


def _context_ref(value: Any, field: str) -> ContextRef:
    if not isinstance(value, Mapping):
        raise LifecycleError(f"context expansion {field} must be a mapping")
    unknown = sorted(set(value) - {"kind", "ref", "reason", "span", "digest"})
    if unknown:
        raise LifecycleError(
            f"context expansion {field} has unknown field(s): " + ", ".join(unknown)
        )
    span = value.get("span")
    if span is not None:
        if (
            not isinstance(span, (list, tuple))
            or len(span) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in span)
        ):
            raise LifecycleError(f"context expansion {field}.span must be [start, end]")
        span = (span[0], span[1])
    digest = value.get("digest", "")
    if not isinstance(digest, str):
        raise LifecycleError(f"context expansion {field}.digest must be a string")
    return ContextRef(
        kind=_enum(ContextKind, value.get("kind"), f"{field}.kind"),
        ref=_required_string(value, "ref"),
        reason=_required_string(value, "reason"),
        span=span,
        digest=digest,
    )


def _required_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"context expansion {field} must be a non-empty string")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise LifecycleError(f"context expansion {field} must be a list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise LifecycleError(
            f"context expansion {field} must be a list of non-empty strings"
        )
    return tuple(value)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LifecycleError(f"context expansion {field} must be an integer")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LifecycleError(f"context expansion {field} must be a boolean")
    return value


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise LifecycleError(f"context expansion {field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise LifecycleError(
            f"context expansion {field} must be one of: {allowed}"
        ) from exc


__all__ = [
    "ContextExpansionDecision",
    "ContextExpansionLedger",
    "ContextExpansionRequest",
    "ContextRefRejection",
    "ExpansionOutcome",
    "effective_context_fingerprint",
]
