"""Typed efficiency facade over the existing append-only execution store."""

from __future__ import annotations

import json
from pathlib import Path

from company.runtime.execution_store import (
    ExecutionRecordPointer,
    ExecutionStore,
    ExecutionStoreError,
)
from company.runtime.state_paths import sorted_records, task_directory_name

from .providers import ToolOutputArtifact
from .telemetry import EfficiencyRecord


class EfficiencyStore:
    """Persist efficiency data under ``execution/`` using runtime conventions."""

    def __init__(self, state_dir: str | Path) -> None:
        self.execution = ExecutionStore(state_dir)

    def append(self, record: EfficiencyRecord) -> ExecutionRecordPointer:
        if record.packet_attempt is not None:
            packet = self.execution.packet(record.task_id, record.packet_attempt)
            if packet is None or packet.fingerprint() != record.packet_fingerprint:
                raise ExecutionStoreError(
                    "efficiency record does not match its persisted packet attempt"
                )
        return self.execution.append_extension(
            "efficiency", record.task_id, record, record.fingerprint()
        )

    def append_idempotent(self, record: EfficiencyRecord) -> ExecutionRecordPointer:
        """Return an identical finalized run, but never overwrite or fork it."""
        for index, existing in enumerate(self.records(record.task_id), start=1):
            if existing.run_id != record.run_id:
                continue
            if existing.fingerprint() != record.fingerprint():
                raise ExecutionStoreError(
                    f"efficiency run {record.run_id!r} already exists with different telemetry"
                )
            path = (
                self.execution.root
                / "efficiency"
                / task_directory_name(record.task_id)
                / f"{index:06d}.json"
            )
            return ExecutionRecordPointer(
                path.relative_to(self.execution.state_dir).as_posix(),
                existing.fingerprint(),
                index,
            )
        return self.append(record)

    def records(self, task_id: str) -> tuple[EfficiencyRecord, ...]:
        try:
            return tuple(
                EfficiencyRecord.from_mapping(item)
                for item in self.execution.extension_records("efficiency", task_id)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutionStoreError(f"invalid efficiency record: {exc}") from exc

    def append_tool_output(
        self, artifact: ToolOutputArtifact
    ) -> ExecutionRecordPointer:
        return self.execution.append_extension(
            "tool_outputs", artifact.task_id, artifact, artifact.fingerprint()
        )

    def append_tool_output_idempotent(
        self, artifact: ToolOutputArtifact
    ) -> ExecutionRecordPointer:
        for index, existing in enumerate(self.tool_outputs(artifact.task_id), start=1):
            if existing.fingerprint() != artifact.fingerprint():
                continue
            path = (
                self.execution.root
                / "tool_outputs"
                / task_directory_name(artifact.task_id)
                / f"{index:06d}.json"
            )
            return ExecutionRecordPointer(
                path.relative_to(self.execution.state_dir).as_posix(),
                existing.fingerprint(),
                index,
            )
        return self.append_tool_output(artifact)

    def all_records(self) -> tuple[EfficiencyRecord, ...]:
        root = self.execution.root / "efficiency"
        if not root.exists():
            return ()
        records: list[EfficiencyRecord] = []
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            for path in sorted_records(directory):
                value = json.loads(path.read_text(encoding="utf-8"))
                records.append(EfficiencyRecord.from_mapping(value))
        return tuple(records)

    def tool_outputs(self, task_id: str) -> tuple[ToolOutputArtifact, ...]:
        try:
            return tuple(
                ToolOutputArtifact.from_mapping(item)
                for item in self.execution.extension_records("tool_outputs", task_id)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutionStoreError(f"invalid tool-output artifact: {exc}") from exc

    def history(self, task_id: str) -> dict[str, object]:
        history = self.execution.history(task_id)
        records = self.records(task_id)
        artifacts = self.tool_outputs(task_id)
        return {
            **history,
            "efficiency": [
                {
                    "run_id": record.run_id,
                    "mode": record.mode.value,
                    "fingerprint": record.fingerprint(),
                    "context_bytes": record.context_bytes,
                    "total_tokens": record.tokens.total_tokens,
                    "token_source": record.tokens.source.value,
                }
                for record in records
            ],
            "tool_outputs": [
                {
                    "fingerprint": artifact.fingerprint(),
                    "command": artifact.command,
                    "exit_status": artifact.exit_status,
                    "raw_bytes": artifact.raw_bytes,
                    "context_bytes": artifact.context_bytes,
                    "compressed": artifact.compressed,
                }
                for artifact in artifacts
            ],
        }


__all__ = ["EfficiencyStore"]
