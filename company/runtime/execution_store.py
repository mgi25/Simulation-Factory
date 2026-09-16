"""The append-only execution history: what was sent out, and what came back.

```
<state_dir>/execution/packets/<task>/000001.json
<state_dir>/execution/receipts/<task>/000001.json
                                     000002.json
```

Three properties, and the directory layout is most of the implementation:

- **Append-only.** There is no update and no delete. A file is created with
  `O_EXCL` (see `state_paths.append_json_bytes`), so a second write never
  replaces a first.
- **Attempt-numbered.** The receipt sequence *is* the attempt number. A task
  whose first attempt was rejected and whose second was accepted keeps both,
  in order, which is exactly what the resources-per-accepted-deliverable metric
  needs: the rejected attempt is the cost of reaching the accepted one.
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

from .errors import LifecycleError
from .packets import SessionPacket
from .receipts import SessionReceipt
from .state_paths import (
    StateStoreError,
    append_json_bytes,
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
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
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


class ExecutionStore:
    """Packets out, receipts in - both immutable once written."""

    _ROOT = "execution"
    _PACKETS = "packets"
    _RECEIPTS = "receipts"

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise ExecutionStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / self._ROOT

    # --- writing -----------------------------------------------------------

    def append_packet(self, packet: SessionPacket) -> ExecutionRecordPointer:
        return self._append(self._PACKETS, packet.task_id, dumps(packet), packet.fingerprint())

    def append_receipt(self, receipt: SessionReceipt) -> ExecutionRecordPointer:
        """Persist a receipt - valid or not. A refused attempt is still history."""
        return self._append(
            self._RECEIPTS, receipt.task_id, dumps(receipt), receipt.fingerprint()
        )

    # --- reading -----------------------------------------------------------

    def packets(self, task_id: str) -> tuple[SessionPacket, ...]:
        return tuple(
            self._read_packet(path)
            for path in sorted_records(self._directory(self._PACKETS, task_id))
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

    def find_packet(self, task_id: str, fingerprint: str) -> SessionPacket | None:
        """The packet a receipt claims to answer, or None if this history lacks it."""
        for packet in self.packets(task_id):
            if packet.fingerprint() == fingerprint:
                return packet
        return None

    def history(self, task_id: str) -> dict[str, object]:
        """A compact, JSON-ready answer to 'what happened to this task?'."""
        attempts = self.attempts(task_id)
        return {
            "task_id": task_id,
            "packets": [
                {
                    "fingerprint": packet.fingerprint(),
                    "employee": packet.employee,
                    "expected_branch": packet.expected_branch,
                    "executor": packet.executor.value,
                    "size_chars": packet.size_chars(),
                }
                for packet in self.packets(task_id)
            ],
            "attempts": [
                {
                    "attempt": record.attempt,
                    "outcome": record.outcome.value,
                    "packet_fingerprint": record.receipt.packet_fingerprint,
                    "commit_sha": record.receipt.commit_sha,
                    "remote_verified": record.receipt.remote_verified,
                    "subagents_used": record.receipt.subagents_used,
                    "record_ref": record.pointer.record_ref,
                }
                for record in attempts
            ],
        }

    # --- internals ---------------------------------------------------------

    def _directory(self, kind: str, task_id: str) -> Path:
        return self.root / kind / task_directory_name(task_id)

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

    def _read_packet(self, path: Path) -> SessionPacket:
        try:
            return SessionPacket.from_mapping(self._load(path))
        except LifecycleError as exc:
            raise ExecutionStoreError(f"{path}: invalid session packet: {exc}") from exc

    def _read_receipt(self, path: Path) -> SessionReceipt:
        try:
            return SessionReceipt.from_mapping(self._load(path))
        except ValidationError as exc:
            raise ExecutionStoreError(f"{path}: invalid session receipt: {exc}") from exc

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExecutionStoreError(f"cannot read execution record {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ExecutionStoreError(f"{path}: execution record must be a JSON object")
        return data


__all__ = [
    "AttemptRecord",
    "ExecutionRecordPointer",
    "ExecutionStore",
    "ExecutionStoreError",
]
