"""Compact, provider-independent view handed to a manual external session."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ai_platform.policy import SubagentPolicyViolation
from ai_platform.references import assert_reference
from ai_platform.serde import to_jsonable

from .authority import ExecutionAuthoritySnapshot
from .context_expansion import ContextExpansionLedger
from .errors import LifecycleError
from .execution_store import ExecutionRecordPointer
from .packets import SessionPacket
from .receipts import RECEIPT_VERSION


EXPANSION_INSTRUCTIONS: tuple[str, ...] = (
    "request additional references with context-request",
    "Company OS decides requests from the stored preparation-time authority",
    "use only initial or approved context references",
)
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


@dataclass(frozen=True)
class SessionTransportBundle:
    """References and public terms needed by an external executor."""

    packet: SessionPacket
    packet_attempt: int
    packet_ref: str
    authority_ref: str
    authority_fingerprint: str
    effective_context_fingerprint: str
    expansion_instructions: tuple[str, ...] = EXPANSION_INSTRUCTIONS
    receipt_version: int = RECEIPT_VERSION
    no_subagents: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.packet_attempt, bool)
            or not isinstance(self.packet_attempt, int)
            or self.packet_attempt < 1
        ):
            raise LifecycleError("session transport packet_attempt must be positive")
        assert_reference(self.packet_ref, "session_transport.packet_ref")
        assert_reference(self.authority_ref, "session_transport.authority_ref")
        for name in ("authority_fingerprint", "effective_context_fingerprint"):
            if not _FINGERPRINT.fullmatch(getattr(self, name)):
                raise LifecycleError(
                    f"session transport {name} must be a 16-character lowercase digest"
                )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation("session transport no_subagents must be true")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def create(
        cls,
        packet: SessionPacket,
        packet_pointer: ExecutionRecordPointer,
        authority: ExecutionAuthoritySnapshot,
        authority_pointer: ExecutionRecordPointer,
        ledger: ContextExpansionLedger,
    ) -> "SessionTransportBundle":
        ledger.assert_for_packet(packet, packet_attempt=packet_pointer.attempt)
        if (
            packet_pointer.fingerprint != packet.fingerprint()
            or authority.packet_fingerprint != packet.fingerprint()
            or authority.packet_attempt != packet_pointer.attempt
            or authority_pointer.fingerprint != authority.fingerprint()
            or authority_pointer.attempt != packet_pointer.attempt
        ):
            raise LifecycleError(
                "session transport records do not describe the same packet attempt"
            )
        return cls(
            packet=packet,
            packet_attempt=packet_pointer.attempt,
            packet_ref=packet_pointer.record_ref,
            authority_ref=authority_pointer.record_ref,
            authority_fingerprint=authority.fingerprint(),
            effective_context_fingerprint=ledger.effective_context_fingerprint,
        )


__all__ = ["EXPANSION_INSTRUCTIONS", "SessionTransportBundle"]
