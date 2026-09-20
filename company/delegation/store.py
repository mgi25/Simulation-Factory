"""The append-only delegation history, under a directory the caller names.

```
<state_dir>/delegation/decisions/<objective-or-loose>/000001.json
<state_dir>/delegation/objectives/<objective>/000001.json
<state_dir>/delegation/plans/<objective>/000001.json
```

No database and no index, and no second copy of the exclusive-create loop:
writing goes through `company.runtime.state_paths.append_json_bytes`, which
creates each record with `O_EXCL` so a second write never replaces a first.
That is the same mechanism `ExecutionStore` and `EngineeringStore` use, reused
here rather than reimplemented for the reason `state_paths` gives — a second
copy of the loop is a second place for an overwrite bug.

## Why decisions are grouped by objective

The question this store is asked is "what did the company decide while pursuing
this objective", and grouping by objective answers it by listing a directory. A
decision with no objective lands under `unattributed/`, which is deliberately
ugly: a delegated decision that traces back to no CEO objective is a governance
gap, and it should look like one in a directory listing.

## What this store refuses to do

It has no update, no delete and no compaction. `integrity` reads the history
and reports contradictions — a record claiming merge authority, a record
claiming it left shadow mode, a seat approving its own request — rather than
repairing them, because a store that could repair its own history is not an
audit trail.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, TypeVar

from ai_platform.references import assert_reference
from ai_platform.serde import dumps
from company.finance.errors import FinanceError
from company.finance.money import Money
from company.runtime.state_paths import (
    StateStoreError,
    append_json_bytes,
    sequence_of,
    sorted_records,
    task_directory_name,
)

from .errors import DelegationError
from .objectives import ExecutivePlan, Objective, objectives_from
from .record import ExecutiveDecisionRecord


T = TypeVar("T")

UNATTRIBUTED = "unattributed"
"""Where a decision with no objective lands. Visible, on purpose."""


class DelegationStoreError(StateStoreError):
    """A delegation history is missing, malformed, or contradicts itself."""


@dataclass(frozen=True)
class DelegationRecordPointer:
    """Where one record lives, what it hashes to, and its sequence."""

    record_ref: str
    fingerprint: str
    sequence: int

    def __post_init__(self) -> None:
        assert_reference(self.record_ref, "delegation.record_ref")
        if len(self.fingerprint) != 16 or any(
            char not in "0123456789abcdef" for char in self.fingerprint
        ):
            raise DelegationError(
                "delegation.fingerprint must be a 16-character lowercase hex digest"
            )
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise DelegationError("delegation.sequence must be an integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_ref": self.record_ref,
            "fingerprint": self.fingerprint,
            "sequence": self.sequence,
        }


class DelegationStore:
    """Decisions, objectives and plans, appended and never rewritten."""

    _ROOT = "delegation"
    _DECISIONS = "decisions"
    _OBJECTIVES = "objectives"
    _PLANS = "plans"

    KINDS: tuple[str, ...] = (_DECISIONS, _OBJECTIVES, _PLANS)

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise DelegationStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / self._ROOT

    # --- writing -----------------------------------------------------------

    def append_decision(
        self, record: ExecutiveDecisionRecord
    ) -> DelegationRecordPointer:
        if not isinstance(record, ExecutiveDecisionRecord):
            raise DelegationStoreError("append_decision takes an ExecutiveDecisionRecord")
        return self._append(
            self._DECISIONS,
            record.objective_id or UNATTRIBUTED,
            record,
            record.fingerprint(),
        )

    def append_objective(self, objective: Objective) -> DelegationRecordPointer:
        if not isinstance(objective, Objective):
            raise DelegationStoreError("append_objective takes an Objective")
        root = objective.parent_id or objective.objective_id
        return self._append(
            self._OBJECTIVES, root, objective, objective.fingerprint()
        )

    def append_plan(self, plan: ExecutivePlan) -> DelegationRecordPointer:
        if not isinstance(plan, ExecutivePlan):
            raise DelegationStoreError("append_plan takes an ExecutivePlan")
        return self._append(self._PLANS, plan.objective_id, plan, plan.fingerprint())

    # --- reading -----------------------------------------------------------

    def decisions(self, objective_id: str = "") -> tuple[ExecutiveDecisionRecord, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._DECISIONS,
                objective_id or UNATTRIBUTED,
                ExecutiveDecisionRecord.from_mapping,
            )
        )

    def objective_ids(self) -> tuple[str, ...]:
        """Every group the decisions directory holds, by directory listing."""
        directory = self.root / self._DECISIONS
        if not directory.is_dir():
            return ()
        found: set[str] = set()
        for group in sorted(directory.iterdir()):
            if not group.is_dir():
                continue
            for path in sorted_records(group):
                data = self._load(path)
                identity = data.get("objective_id")
                found.add(str(identity) if identity else UNATTRIBUTED)
        return tuple(sorted(found))

    def all_decisions(self) -> tuple[ExecutiveDecisionRecord, ...]:
        """Every decision in the store, ordered by objective then sequence."""
        out: list[ExecutiveDecisionRecord] = []
        directory = self.root / self._DECISIONS
        if not directory.is_dir():
            return ()
        for group in sorted(directory.iterdir()):
            if not group.is_dir():
                continue
            for path in sorted_records(group):
                out.append(
                    ExecutiveDecisionRecord.from_mapping(self._load(path))
                )
        return tuple(out)

    def objectives(self, root_id: str) -> tuple[Objective, ...]:
        decoded = tuple(
            data
            for _pointer, data in self._records(self._OBJECTIVES, root_id, dict)
        )
        if not decoded:
            return ()
        return objectives_from(list(decoded)).objectives

    def plans(self, objective_id: str) -> tuple[ExecutivePlan, ...]:
        out: list[ExecutivePlan] = []
        for path in sorted_records(self._directory(self._PLANS, objective_id)):
            data = self._load(path)
            spend = data.get("estimated_spend")
            try:
                estimated = (
                    Money.from_dict(dict(spend), "plan.estimated_spend")
                    if isinstance(spend, Mapping)
                    else None
                )
            except FinanceError as exc:
                raise DelegationStoreError(
                    f"{path}: invalid plan record: {exc}"
                ) from exc
            out.append(
                ExecutivePlan(
                    plan_id=str(data.get("plan_id", "")),
                    objective_id=str(data.get("objective_id", "")),
                    planned_by=str(data.get("planned_by", "")),
                    planned_on=str(data.get("planned_on", "")),
                    envelope_fingerprint=str(data.get("envelope_fingerprint", "")),
                    departments=tuple(data.get("departments", ())),
                    actions=tuple(data.get("actions", ())),
                    estimated_spend=estimated,
                    max_risk=str(data.get("max_risk", "low")),
                    completion_by=data.get("completion_by") or None,
                    steps=tuple(data.get("steps", ())),
                )
            )
        return tuple(out)

    # --- integrity ---------------------------------------------------------

    def integrity(self) -> tuple[str, ...]:
        """Every contradiction in the stored history. Reported, never repaired."""
        problems: list[str] = []
        seen: dict[str, str] = {}
        for record in self.all_decisions():
            if record.authorizes_action:
                problems.append(
                    f"{record.decision_id}: a stored record claims it authorizes the "
                    "action it describes"
                )
            if not record.shadow:
                problems.append(
                    f"{record.decision_id}: a stored record claims it was taken "
                    "outside shadow mode, which this version never produced"
                )
            if record.requesting_role == record.approving_role:
                problems.append(
                    f"{record.decision_id}: {record.requesting_role} appears as both "
                    "requester and approver"
                )
            if record.decision.value == "approved" and record.approving_role == "ceo":
                problems.append(
                    f"{record.decision_id}: a CEO approval was written by the "
                    "delegation model, which never writes one"
                )
            previous = seen.get(record.decision_id)
            if previous is not None and previous != record.fingerprint():
                problems.append(
                    f"{record.decision_id} appears twice with different contents "
                    f"({previous} and {record.fingerprint()})"
                )
            seen[record.decision_id] = record.fingerprint()
        return tuple(dict.fromkeys(problems))

    # --- internals ---------------------------------------------------------

    def _directory(self, kind: str, identity: str) -> Path:
        if kind not in self.KINDS:
            raise DelegationStoreError(f"unsupported delegation record kind {kind!r}")
        return self.root / kind / task_directory_name(identity)

    def _append(
        self, kind: str, identity: str, record: Any, fingerprint: str
    ) -> DelegationRecordPointer:
        path = append_json_bytes(
            self._directory(kind, identity), dumps(record.to_dict()).encode("utf-8")
        )
        return DelegationRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=fingerprint,
            sequence=sequence_of(path),
        )

    def _records(
        self, kind: str, identity: str, decoder: Callable[[Mapping[str, Any]], T]
    ) -> tuple[tuple[DelegationRecordPointer, T], ...]:
        out: list[tuple[DelegationRecordPointer, T]] = []
        for path in sorted_records(self._directory(kind, identity)):
            data = self._load(path)
            try:
                record = decoder(data)
            except DelegationError as exc:
                raise DelegationStoreError(
                    f"{path}: invalid {kind} record: {exc}"
                ) from exc
            digest = getattr(record, "fingerprint", None)
            out.append(
                (
                    DelegationRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=digest() if callable(digest) else "0" * 16,
                        sequence=sequence_of(path),
                    ),
                    record,
                )
            )
        return tuple(out)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DelegationStoreError(
                f"cannot read delegation record {path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise DelegationStoreError(
                f"{path}: a delegation record must be a JSON object"
            )
        return data


__all__ = [
    "UNATTRIBUTED",
    "DelegationRecordPointer",
    "DelegationStore",
    "DelegationStoreError",
]
