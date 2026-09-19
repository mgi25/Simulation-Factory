"""The append-only execution history: what was sent out, and what came back.

```
<state_dir>/execution/packets/<task>/000001.json
<state_dir>/execution/authorities/<task>/000001.json
<state_dir>/execution/context_expansions/requests/<task>/000001.json
<state_dir>/execution/context_expansions/decisions/<task>/000001.json
<state_dir>/execution/receipts/<task>/000001.json
<state_dir>/execution/efficiency/<task>/000001.json
<state_dir>/execution/tool_outputs/<task>/000001.json
                                     000002.json
```

Three properties, and the directory layout is most of the implementation:

- **Append-only.** There is no update and no delete. A file is created with
  `O_EXCL` (see `state_paths.append_json_bytes`), so a second write never
  replaces a first.
- **Attempt-numbered.** Packet and authority records share a packet-attempt
  identity. Receipts retain their own append sequence and explicitly name the
  packet attempt they answer, so retries and repeated identical packets cannot
  cross their authority or context-expansion histories.
- **Caller-supplied.** The state directory is always passed in and is never
  inside the package, so runtime state is not committed to the repository by
  default. `.gitignore` carries `state/` for the conventional choice.

No database and no index file: a directory listing sorted by sequence answers
"every attempt at task X" exactly, and cannot disagree with the files.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from ai_platform.references import assert_reference
from ai_platform.serde import dumps
from ai_platform.usage import Outcome
from company.validation.errors import ValidationError

from .authority import ExecutionAuthoritySnapshot
from .context_expansion import (
    ContextExpansionDecision,
    ContextExpansionLedger,
    ContextExpansionRequest,
)
from .errors import LifecycleError
from .packets import SessionPacket
from .receipts import SessionReceipt
from .state_paths import (
    StateStoreError,
    append_json_bytes,
    create_json_bytes_at_sequence,
    sequence_of,
    sorted_records,
    task_directory_name,
)


class ExecutionStoreError(StateStoreError):
    """An execution history is missing, malformed, or fails its integrity check."""


@dataclass(frozen=True)
class ExecutionRecordPointer:
    """Where one packet or receipt lives, what it hashes to, and its attempt."""

    record_ref: str
    fingerprint: str
    attempt: int

    def __post_init__(self) -> None:
        assert_reference(self.record_ref, "execution.record_ref")
        if len(self.fingerprint) != 16 or not all(
            char in "0123456789abcdef" for char in self.fingerprint
        ):
            raise LifecycleError(
                "execution.fingerprint must be a 16-character lowercase hex digest"
            )
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise LifecycleError("execution.attempt must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_ref": self.record_ref,
            "fingerprint": self.fingerprint,
            "attempt": self.attempt,
        }


@dataclass(frozen=True)
class AttemptRecord:
    """One returned receipt, with the attempt number the history gave it."""

    attempt: int
    pointer: ExecutionRecordPointer
    receipt: SessionReceipt

    @property
    def outcome(self) -> Outcome:
        return self.receipt.outcome


@dataclass(frozen=True)
class PacketRecord:
    """One prepared packet at its immutable per-task attempt number."""

    attempt: int
    pointer: ExecutionRecordPointer
    packet: SessionPacket


@dataclass(frozen=True)
class AuthorityRecord:
    """The authority evidence paired with exactly one packet attempt."""

    attempt: int
    pointer: ExecutionRecordPointer
    snapshot: ExecutionAuthoritySnapshot


class ExecutionStore:
    """Packets out, receipts in - both immutable once written."""

    _ROOT = "execution"
    _PACKETS = "packets"
    _AUTHORITIES = "authorities"
    _CONTEXT_EXPANSIONS = "context_expansions"
    _EXPANSION_REQUESTS = "requests"
    _EXPANSION_DECISIONS = "decisions"
    _RECEIPTS = "receipts"
    _EFFICIENCY = "efficiency"
    _TOOL_OUTPUTS = "tool_outputs"
    _EXTENSIONS = frozenset({_EFFICIENCY, _TOOL_OUTPUTS})

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise ExecutionStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / self._ROOT

    # --- writing -----------------------------------------------------------

    def append_packet(self, packet: SessionPacket) -> ExecutionRecordPointer:
        return self._append(
            self._PACKETS, packet.task_id, dumps(packet), packet.fingerprint()
        )

    def append_receipt(self, receipt: SessionReceipt) -> ExecutionRecordPointer:
        """Persist a receipt - valid or not. A refused attempt is still history."""
        if receipt.packet_attempt < 1:
            raise ExecutionStoreError(
                "a persisted receipt must be associated with a packet attempt"
            )
        return self._append(
            self._RECEIPTS, receipt.task_id, dumps(receipt), receipt.fingerprint()
        )

    def append_authority(
        self, snapshot: ExecutionAuthoritySnapshot
    ) -> ExecutionRecordPointer:
        """Persist authority at the exact packet attempt it supports."""
        packet = self.packet(snapshot.task_id, snapshot.packet_attempt)
        if packet is None or packet.fingerprint() != snapshot.packet_fingerprint:
            raise ExecutionStoreError(
                "execution authority does not match the persisted packet at attempt "
                f"{snapshot.packet_attempt}"
            )
        path = create_json_bytes_at_sequence(
            self._directory(self._AUTHORITIES, snapshot.task_id),
            dumps(snapshot).encode("utf-8"),
            snapshot.packet_attempt,
        )
        return ExecutionRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=snapshot.fingerprint(),
            attempt=snapshot.packet_attempt,
        )

    def append_context_expansion_request(
        self, request: ContextExpansionRequest
    ) -> ExecutionRecordPointer:
        """Persist the request before deciding it; rejected requests stay history."""
        if (
            self.find_packet_record(
                request.task_id,
                request.packet_fingerprint,
                attempt=request.packet_attempt,
            )
            is None
        ):
            raise ExecutionStoreError(
                "context expansion request does not match a persisted packet attempt"
            )
        if self.find_context_expansion_request(request.task_id, request.request_id):
            raise ExecutionStoreError(
                f"context expansion request ID {request.request_id!r} already exists"
            )
        if (
            self.authority(
                request.task_id, request.packet_fingerprint, request.packet_attempt
            )
            is None
        ):
            raise ExecutionStoreError(
                "context expansion request has no matching authority snapshot"
            )
        decisions = tuple(
            item
            for item in self.context_expansion_decisions(request.task_id)
            if item.packet_fingerprint == request.packet_fingerprint
            and item.packet_attempt == request.packet_attempt
        )
        requests = tuple(
            item
            for item in self.context_expansion_requests(request.task_id)
            if item.packet_fingerprint == request.packet_fingerprint
            and item.packet_attempt == request.packet_attempt
        )
        if len(requests) != len(decisions):
            raise ExecutionStoreError(
                "the packet attempt already has an undecided context request"
            )
        if request.sequence != len(decisions) + 1:
            raise ExecutionStoreError(
                "context expansion request sequence is not next for its packet attempt"
            )
        return self._append_expansion(
            self._EXPANSION_REQUESTS,
            request.task_id,
            dumps(request),
            request.fingerprint(),
        )

    def append_context_expansion_decision(
        self, decision: ContextExpansionDecision
    ) -> ExecutionRecordPointer:
        authority = self.authority(
            decision.task_id,
            decision.packet_fingerprint,
            decision.packet_attempt,
        )
        if authority is None:
            raise ExecutionStoreError(
                "context expansion decision has no matching authority snapshot"
            )
        if decision.authority_fingerprint != authority.fingerprint():
            raise ExecutionStoreError(
                "context expansion decision authority fingerprint does not match the "
                "stored snapshot"
            )
        request = self.find_context_expansion_request(
            decision.task_id, decision.request_id
        )
        if (
            request is None
            or request.fingerprint() != decision.request_fingerprint
            or request.packet_fingerprint != decision.packet_fingerprint
            or request.packet_attempt != decision.packet_attempt
            or request.sequence != decision.sequence
        ):
            raise ExecutionStoreError(
                "context expansion decision does not match its persisted request"
            )
        if any(
            item.request_id == decision.request_id
            for item in self.context_expansion_decisions(decision.task_id)
        ):
            raise ExecutionStoreError(
                f"context expansion request {decision.request_id!r} already has a decision"
            )
        return self._append_expansion(
            self._EXPANSION_DECISIONS,
            decision.task_id,
            dumps(decision),
            decision.fingerprint(),
        )

    def append_extension(
        self, kind: str, task_id: str, payload: object, record_fingerprint: str
    ) -> ExecutionRecordPointer:
        """Append an approved typed extension beside core execution records.

        Runtime deliberately does not import the extension packages: callers
        validate and decode their own records, while this method supplies the
        same append-only path and exclusive-create semantics as packets.
        """
        if kind not in self._EXTENSIONS:
            raise ExecutionStoreError(f"unsupported execution extension {kind!r}")
        return self._append(kind, task_id, dumps(payload), record_fingerprint)

    # --- reading -----------------------------------------------------------

    def packets(self, task_id: str) -> tuple[SessionPacket, ...]:
        return tuple(record.packet for record in self.packet_records(task_id))

    def packet_records(self, task_id: str) -> tuple[PacketRecord, ...]:
        records = []
        for path in sorted_records(self._directory(self._PACKETS, task_id)):
            packet = self._read_packet(path)
            attempt = sequence_of(path)
            records.append(
                PacketRecord(
                    attempt=attempt,
                    pointer=ExecutionRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=packet.fingerprint(),
                        attempt=attempt,
                    ),
                    packet=packet,
                )
            )
        return tuple(records)

    def packet(self, task_id: str, attempt: int) -> SessionPacket | None:
        return next(
            (
                record.packet
                for record in self.packet_records(task_id)
                if record.attempt == attempt
            ),
            None,
        )

    def authorities(self, task_id: str) -> tuple[ExecutionAuthoritySnapshot, ...]:
        return tuple(record.snapshot for record in self.authority_records(task_id))

    def authority_records(self, task_id: str) -> tuple[AuthorityRecord, ...]:
        records = []
        for path in sorted_records(self._directory(self._AUTHORITIES, task_id)):
            snapshot = self._read_authority(path)
            attempt = sequence_of(path)
            if snapshot.packet_attempt != attempt:
                raise ExecutionStoreError(
                    f"{path}: authority packet_attempt does not match record sequence"
                )
            packet = self.packet(task_id, attempt)
            if (
                packet is None
                or packet.fingerprint() != snapshot.packet_fingerprint
                or packet.employee != snapshot.employee
            ):
                raise ExecutionStoreError(
                    f"{path}: authority does not match its packet attempt"
                )
            records.append(
                AuthorityRecord(
                    attempt=attempt,
                    pointer=ExecutionRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=snapshot.fingerprint(),
                        attempt=attempt,
                    ),
                    snapshot=snapshot,
                )
            )
        return tuple(records)

    def authority(
        self, task_id: str, packet_fingerprint: str, packet_attempt: int
    ) -> ExecutionAuthoritySnapshot | None:
        return next(
            (
                record.snapshot
                for record in self.authority_records(task_id)
                if record.attempt == packet_attempt
                and record.snapshot.packet_fingerprint == packet_fingerprint
            ),
            None,
        )

    def receipts(self, task_id: str) -> tuple[SessionReceipt, ...]:
        return tuple(record.receipt for record in self.attempts(task_id))

    def attempts(self, task_id: str) -> tuple[AttemptRecord, ...]:
        """Every attempt at one task, in the order it was recorded."""
        records: list[AttemptRecord] = []
        for path in sorted_records(self._directory(self._RECEIPTS, task_id)):
            receipt = self._read_receipt(path)
            attempt = sequence_of(path)
            records.append(
                AttemptRecord(
                    attempt=attempt,
                    pointer=ExecutionRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=receipt.fingerprint(),
                        attempt=attempt,
                    ),
                    receipt=receipt,
                )
            )
        return tuple(records)

    def context_expansion_requests(
        self, task_id: str
    ) -> tuple[ContextExpansionRequest, ...]:
        return tuple(
            self._read_expansion_request(path)
            for path in sorted_records(
                self._expansion_directory(self._EXPANSION_REQUESTS, task_id)
            )
        )

    def context_expansion_decisions(
        self, task_id: str
    ) -> tuple[ContextExpansionDecision, ...]:
        return tuple(
            self._read_expansion_decision(path)
            for path in sorted_records(
                self._expansion_directory(self._EXPANSION_DECISIONS, task_id)
            )
        )

    def extension_records(self, kind: str, task_id: str) -> tuple[dict[str, object], ...]:
        """Return canonical mappings; the owning extension validates its schema."""
        if kind not in self._EXTENSIONS:
            raise ExecutionStoreError(f"unsupported execution extension {kind!r}")
        return tuple(
            self._load(path)
            for path in sorted_records(self._directory(kind, task_id))
        )

    def context_expansion_ledger(
        self, packet: SessionPacket, *, packet_attempt: int = 1
    ) -> ContextExpansionLedger:
        """The decisions for this exact packet; other attempts remain isolated."""
        packet_fingerprint = packet.fingerprint()
        decisions = tuple(
            decision
            for decision in self.context_expansion_decisions(packet.task_id)
            if decision.packet_fingerprint == packet_fingerprint
            and decision.packet_attempt == packet_attempt
        )
        authority = self.authority(packet.task_id, packet_fingerprint, packet_attempt)
        for decision in decisions:
            if (
                authority is None
                or decision.authority_fingerprint != authority.fingerprint()
            ):
                raise ExecutionStoreError(
                    "context expansion decision is not bound to the stored authority "
                    f"for packet attempt {packet_attempt}"
                )
        return ContextExpansionLedger.for_packet(
            packet, decisions, packet_attempt=packet_attempt
        )

    def find_packet(self, task_id: str, fingerprint: str) -> SessionPacket | None:
        """The packet a receipt claims to answer, or None if this history lacks it."""
        for packet in self.packets(task_id):
            if packet.fingerprint() == fingerprint:
                return packet
        return None

    def find_packet_record(
        self, task_id: str, fingerprint: str, *, attempt: int | None = None
    ) -> PacketRecord | None:
        matches = tuple(
            record
            for record in self.packet_records(task_id)
            if record.pointer.fingerprint == fingerprint
            and (attempt is None or record.attempt == attempt)
        )
        return matches[-1] if matches else None

    def find_context_expansion_request(
        self, task_id: str, request_id: str
    ) -> ContextExpansionRequest | None:
        matches = tuple(
            request
            for request in self.context_expansion_requests(task_id)
            if request.request_id == request_id
        )
        if len(matches) > 1:
            raise ExecutionStoreError(
                f"context expansion request ID {request_id!r} is not unique"
            )
        return matches[0] if matches else None

    def context_expansion_request_pointer(
        self, task_id: str, request_id: str
    ) -> ExecutionRecordPointer | None:
        matches = []
        for path in sorted_records(
            self._expansion_directory(self._EXPANSION_REQUESTS, task_id)
        ):
            request = self._read_expansion_request(path)
            if request.request_id == request_id:
                sequence = sequence_of(path)
                matches.append(
                    ExecutionRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=request.fingerprint(),
                        attempt=sequence,
                    )
                )
        if len(matches) > 1:
            raise ExecutionStoreError(
                f"context expansion request ID {request_id!r} is not unique"
            )
        return matches[0] if matches else None

    def history(self, task_id: str) -> dict[str, object]:
        """A compact, JSON-ready answer to 'what happened to this task?'."""
        attempts = self.attempts(task_id)
        packet_records = self.packet_records(task_id)
        authority_records = self.authority_records(task_id)
        requests = self.context_expansion_requests(task_id)
        decisions = self.context_expansion_decisions(task_id)
        return {
            "task_id": task_id,
            "packets": [
                {
                    "attempt": record.attempt,
                    "fingerprint": packet.fingerprint(),
                    "employee": packet.employee,
                    "expected_branch": packet.expected_branch,
                    "executor": packet.executor.value,
                    "size_chars": packet.size_chars(),
                }
                for record in packet_records
                for packet in (record.packet,)
            ],
            "authorities": [
                {
                    "attempt": record.attempt,
                    "packet_fingerprint": record.snapshot.packet_fingerprint,
                    "fingerprint": record.pointer.fingerprint,
                    "record_ref": record.pointer.record_ref,
                    "source": record.snapshot.source.value,
                    "no_subagents": record.snapshot.no_subagents,
                }
                for record in authority_records
            ],
            "attempts": [
                {
                    "attempt": record.attempt,
                    "outcome": record.outcome.value,
                    "packet_fingerprint": record.receipt.packet_fingerprint,
                    "packet_attempt": record.receipt.packet_attempt,
                    "authority_fingerprint": record.receipt.authority_fingerprint,
                    "commit_sha": record.receipt.commit_sha,
                    "remote_verified": record.receipt.remote_verified,
                    "subagents_used": record.receipt.subagents_used,
                    "record_ref": record.pointer.record_ref,
                }
                for record in attempts
            ],
            "context_expansions": {
                "requests": [
                    {
                        "request_id": request.request_id,
                        "packet_fingerprint": request.packet_fingerprint,
                        "packet_attempt": request.packet_attempt,
                        "sequence": request.sequence,
                        "requested_refs": [ref.key for ref in request.requested_refs],
                        "required_to_continue": request.required_to_continue,
                    }
                    for request in requests
                ],
                "decisions": [
                    {
                        "request_id": decision.request_id,
                        "packet_fingerprint": decision.packet_fingerprint,
                        "packet_attempt": decision.packet_attempt,
                        "authority_fingerprint": decision.authority_fingerprint,
                        "sequence": decision.sequence,
                        "required_to_continue": decision.required_to_continue,
                        "outcome": decision.outcome.value,
                        "approved_refs": [ref.key for ref in decision.approved_refs],
                        "rejected_refs": [
                            item.requested_ref.key for item in decision.rejected_refs
                        ],
                        "resulting_context_fingerprint": (
                            decision.resulting_context_fingerprint
                        ),
                    }
                    for decision in decisions
                ],
            },
            "effective_contexts": [
                {
                    "attempt": record.attempt,
                    "packet_fingerprint": record.packet.fingerprint(),
                    "fingerprint": self.context_expansion_ledger(
                        record.packet, packet_attempt=record.attempt
                    ).effective_context_fingerprint,
                }
                for record in packet_records
            ],
        }

    # --- internals ---------------------------------------------------------

    def _directory(self, kind: str, task_id: str) -> Path:
        return self.root / kind / task_directory_name(task_id)

    def _expansion_directory(self, kind: str, task_id: str) -> Path:
        return (
            self.root / self._CONTEXT_EXPANSIONS / kind / task_directory_name(task_id)
        )

    def _append(
        self, kind: str, task_id: str, payload: str, fingerprint: str
    ) -> ExecutionRecordPointer:
        path = append_json_bytes(
            self._directory(kind, task_id), payload.encode("utf-8")
        )
        return ExecutionRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=fingerprint,
            attempt=sequence_of(path),
        )

    def _append_expansion(
        self, kind: str, task_id: str, payload: str, fingerprint: str
    ) -> ExecutionRecordPointer:
        path = append_json_bytes(
            self._expansion_directory(kind, task_id), payload.encode("utf-8")
        )
        return ExecutionRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=fingerprint,
            attempt=sequence_of(path),
        )

    def _read_packet(self, path: Path) -> SessionPacket:
        try:
            return SessionPacket.from_mapping(self._load(path))
        except LifecycleError as exc:
            raise ExecutionStoreError(f"{path}: invalid session packet: {exc}") from exc

    def _read_receipt(self, path: Path) -> SessionReceipt:
        try:
            return SessionReceipt.from_mapping(self._load(path))
        except ValidationError as exc:
            raise ExecutionStoreError(
                f"{path}: invalid session receipt: {exc}"
            ) from exc

    def _read_authority(self, path: Path) -> ExecutionAuthoritySnapshot:
        try:
            return ExecutionAuthoritySnapshot.from_mapping(self._load(path))
        except (LifecycleError, ValueError) as exc:
            raise ExecutionStoreError(
                f"{path}: invalid execution authority snapshot: {exc}"
            ) from exc

    def _read_expansion_request(self, path: Path) -> ContextExpansionRequest:
        try:
            return ContextExpansionRequest.from_mapping(self._load(path))
        except (LifecycleError, ValueError) as exc:
            raise ExecutionStoreError(
                f"{path}: invalid context expansion request: {exc}"
            ) from exc

    def _read_expansion_decision(self, path: Path) -> ContextExpansionDecision:
        try:
            return ContextExpansionDecision.from_mapping(self._load(path))
        except (LifecycleError, ValueError) as exc:
            raise ExecutionStoreError(
                f"{path}: invalid context expansion decision: {exc}"
            ) from exc

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExecutionStoreError(
                f"cannot read execution record {path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ExecutionStoreError(f"{path}: execution record must be a JSON object")
        return data


__all__ = [
    "AuthorityRecord",
    "AttemptRecord",
    "ExecutionRecordPointer",
    "ExecutionStore",
    "ExecutionStoreError",
    "PacketRecord",
]
