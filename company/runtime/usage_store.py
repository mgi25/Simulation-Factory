"""Append-only, provider-independent persistence for task resource usage."""

from __future__ import annotations

import json
from pathlib import Path

from ai_platform.serde import dumps
from ai_platform.usage import ResourceSummary, ResourceUsageRecord, UsageLedger

from .state_paths import (
    StateStoreError,
    append_json_bytes,
    sorted_records,
    task_directory_name,
)
from .tasks import UsageRecordPointer


class UsageStoreError(StateStoreError):
    """A usage history is missing, malformed, or fails its integrity check."""


class ResourceUsageStore:
    """A directory of immutable records, ordered per task by attempt number.

    The state directory is always supplied by the caller. Appending creates a
    new file with exclusive-create semantics; this API has no update or delete
    operation, so an earlier accepted, rejected, or abandoned attempt remains
    part of the history.
    """

    _STORE_DIRECTORY = "resource_usage"

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise UsageStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / self._STORE_DIRECTORY

    def append(self, record: ResourceUsageRecord) -> UsageRecordPointer:
        """Persist one record without ever opening an existing record for write."""
        record.check_policy()
        path = append_json_bytes(
            self.root / task_directory_name(record.task_id),
            dumps(record).encode("utf-8"),
        )
        return UsageRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=record.fingerprint(),
        )

    def records(self, task_id: str | None = None) -> tuple[ResourceUsageRecord, ...]:
        """Load all records in a scope, preserving deterministic file order."""
        if task_id is not None:
            directories = (self.root / task_directory_name(task_id),)
        elif self.root.exists():
            directories = tuple(
                path for path in sorted(self.root.iterdir()) if path.is_dir()
            )
        else:
            directories = ()

        records: list[ResourceUsageRecord] = []
        for directory in directories:
            for path in sorted_records(directory):
                record = self._read(path)
                if task_id is not None and record.task_id != task_id:
                    raise UsageStoreError(
                        f"{path}: task_id {record.task_id!r} does not match requested "
                        f"scope {task_id!r}"
                    )
                records.append(record)
        return tuple(records)

    def summarise(self, task_id: str | None = None) -> ResourceSummary:
        return UsageLedger(list(self.records(task_id))).summarise()

    def pointers(self, task_id: str) -> tuple[UsageRecordPointer, ...]:
        """Compact references to each immutable usage record for execution views."""
        directory = self.root / task_directory_name(task_id)
        pointers = []
        for path in sorted_records(directory):
            record = self._read(path)
            pointers.append(
                UsageRecordPointer(
                    record_ref=path.relative_to(self.state_dir).as_posix(),
                    fingerprint=record.fingerprint(),
                )
            )
        return tuple(pointers)

    def load(self, pointer: UsageRecordPointer) -> ResourceUsageRecord:
        """Resolve a compact handoff pointer and verify the detailed record."""
        path = (self.state_dir / Path(pointer.record_ref)).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise UsageStoreError(
                f"usage record pointer escapes the resource usage store: {pointer.record_ref}"
            ) from exc
        record = self._read(path)
        actual = record.fingerprint()
        if actual != pointer.fingerprint:
            raise UsageStoreError(
                f"{pointer.record_ref}: fingerprint mismatch; expected "
                f"{pointer.fingerprint}, got {actual}"
            )
        return record

    @staticmethod
    def _read(path: Path) -> ResourceUsageRecord:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UsageStoreError(
                f"cannot read resource usage record {path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise UsageStoreError(
                f"{path}: resource usage record must be a JSON object"
            )
        try:
            return ResourceUsageRecord.from_mapping(data)
        except (TypeError, ValueError) as exc:
            raise UsageStoreError(
                f"{path}: invalid resource usage record: {exc}"
            ) from exc
