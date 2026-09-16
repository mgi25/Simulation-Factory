"""Structured snapshot comparison; text is never assigned significance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import CompanyStateSnapshot, DashboardError


@dataclass(frozen=True)
class SnapshotChange:
    change_id: str
    category: str
    identity: str
    before_state: str | None
    after_state: str | None
    source_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"change_id": self.change_id, "category": self.category,
                "identity": self.identity, "before_state": self.before_state,
                "after_state": self.after_state, "source_refs": list(self.source_refs)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SnapshotChange":
        return cls(str(data["change_id"]), str(data["category"]), str(data["identity"]),
                   data.get("before_state"), data.get("after_state"),
                   tuple(data.get("source_refs", ())))


@dataclass(frozen=True)
class SnapshotDiff:
    previous_snapshot_id: str
    current_snapshot_id: str
    changes: tuple[SnapshotChange, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes", tuple(sorted(self.changes, key=lambda x: x.change_id)))

    def to_dict(self) -> dict[str, Any]:
        return {"previous_snapshot_id": self.previous_snapshot_id,
                "current_snapshot_id": self.current_snapshot_id,
                "changes": [item.to_dict() for item in self.changes]}


def diff_snapshots(previous: CompanyStateSnapshot, current: CompanyStateSnapshot) -> SnapshotDiff:
    if current.as_of < previous.as_of or current.generated_at < previous.generated_at:
        raise DashboardError("invalid snapshot chronology: current snapshot predates previous")
    changes: list[SnapshotChange] = []
    before = {item.key: item for item in previous.source_refs}
    after = {item.key: item for item in current.source_refs}
    for key in sorted(after.keys() - before.keys()):
        changes.append(_change("source_added", key, None, after[key].fingerprint, (key,)))
    for key in sorted(before.keys() - after.keys()):
        changes.append(_change("source_removed", key, before[key].fingerprint, None, (key,)))
    for key in sorted(before.keys() & after.keys()):
        if before[key].fingerprint != after[key].fingerprint:
            changes.append(_change("source_changed", key, before[key].fingerprint, after[key].fingerprint, (key,)))
        if before[key].freshness != after[key].freshness:
            changes.append(_change("freshness_changed", key, before[key].freshness.value,
                                   after[key].freshness.value, (key,)))
    _state_changes(changes, "decision", previous.decision_queue, current.decision_queue,
                   "decision_id", lambda x: x.current_state, lambda x: x.evidence_refs)
    _state_changes(changes, "attention", previous.attention_items, current.attention_items,
                   "attention_id", lambda x: x.level.value, lambda x: x.source_refs)
    return SnapshotDiff(previous.snapshot_id, current.snapshot_id, tuple(changes))


def _state_changes(out: list[SnapshotChange], category: str, old: tuple[Any, ...], new: tuple[Any, ...],
                   id_field: str, state: Any, refs: Any) -> None:
    before = {getattr(x, id_field): x for x in old}
    after = {getattr(x, id_field): x for x in new}
    for key in sorted(after.keys() - before.keys()):
        out.append(_change(f"{category}_added", key, None, state(after[key]), tuple(refs(after[key]))))
    for key in sorted(before.keys() - after.keys()):
        out.append(_change(f"{category}_removed", key, state(before[key]), None, tuple(refs(before[key]))))
    for key in sorted(before.keys() & after.keys()):
        if state(before[key]) != state(after[key]):
            out.append(_change(f"{category}_state_changed", key, state(before[key]), state(after[key]),
                               tuple(sorted(set(refs(before[key])) | set(refs(after[key]))))))


def _change(category: str, identity: str, before: str | None, after: str | None,
            refs: tuple[str, ...]) -> SnapshotChange:
    return SnapshotChange(f"{category}:{identity}", category, identity, before, after,
                          tuple(sorted(set(refs))))

