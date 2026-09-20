"""Per-attempt cost view for one engineering job.

The CEO objective: "every developer attempt that was made and what each one
cost, so I can tell whether an automated run is converging or thrashing without
reading the whole history."

The ledger is a read-only projection. It joins three stores that already exist:

- ``EngineeringStore``    — the job transitions (which attempts were issued)
- ``ExecutionStore``      — the receipts (what each attempt reported)
- ``ResourceUsageStore``  — the usage records (what each attempt cost)

It does not write to any of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import to_jsonable
from ai_platform.usage import Outcome, UsageUnit
from company.runtime.execution_store import ExecutionStore
from company.runtime.usage_store import ResourceUsageStore

from .errors import EngineeringError
from .lifecycle import JobState
from .store import EngineeringStore


@dataclass(frozen=True)
class AttemptLedgerEntry:
    """One developer attempt: what it reported and what it cost."""

    attempt: int
    outcome: str
    summary: str
    input_units: int | None
    output_units: int | None
    total_units: int | None
    usage_unit: str
    duration_s: float | None
    reasoning_class: str

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class AttemptLedger:
    """Every developer attempt on one job, with per-attempt and aggregate cost."""

    work_order_id: str
    objective: str
    state: str
    developer_attempts: int
    max_developer_attempts: int
    corrections_remaining: int
    entries: tuple[AttemptLedgerEntry, ...]
    total_input_units: int | None
    total_output_units: int | None
    total_units: int | None
    usage_unit: str
    total_duration_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def build_attempt_ledger(
    store: EngineeringStore,
    execution_store: ExecutionStore,
    usage_store: ResourceUsageStore,
    work_order_id: str,
) -> AttemptLedger:
    """Build the attempt ledger for one engineering job.

    Raises ``EngineeringError`` when the work order is not in the store.
    """
    order = store.work_order(work_order_id)
    if order is None:
        raise EngineeringError(
            f"no work order {work_order_id!r} is stored; "
            "the ledger can only describe a job that has been opened"
        )
    job = store.job(work_order_id)
    state = job.state.value if job else ""
    developer_attempts = job.developer_attempts if job else 0
    max_attempts = job.max_developer_attempts if job else order.max_developer_attempts
    corrections = job.corrections_remaining if job else max_attempts

    # Receipts keyed by packet_attempt for correlation with usage records.
    attempt_records = execution_store.attempts(work_order_id)
    receipt_by_attempt: dict[int, Any] = {}
    for record in attempt_records:
        receipt_by_attempt[record.attempt] = record.receipt

    # Usage records keyed by sequence position (1-based, matching attempt).
    usage_records = usage_store.records(work_order_id)

    entries: list[AttemptLedgerEntry] = []
    for index, usage in enumerate(usage_records):
        attempt_num = index + 1
        receipt = receipt_by_attempt.get(attempt_num)
        entries.append(
            AttemptLedgerEntry(
                attempt=attempt_num,
                outcome=usage.outcome.value,
                summary=receipt.summary if receipt else "",
                input_units=usage.input_units,
                output_units=usage.output_units,
                total_units=usage.total_units,
                usage_unit=usage.usage_unit.value,
                duration_s=usage.duration_s,
                reasoning_class=usage.reasoning_class.value,
            )
        )

    # Aggregates — only summable when every entry reports the same unit.
    units_seen = {e.usage_unit for e in entries if e.usage_unit != UsageUnit.UNKNOWN.value}
    if len(units_seen) == 1 and all(
        e.total_units is not None for e in entries
    ) and entries:
        agg_unit = units_seen.pop()
        agg_input: int | None = sum(
            e.input_units for e in entries if e.input_units is not None
        )
        agg_output: int | None = sum(
            e.output_units for e in entries if e.output_units is not None
        )
        agg_total: int | None = sum(e.total_units or 0 for e in entries)
    else:
        agg_unit = UsageUnit.UNKNOWN.value
        agg_input = None
        agg_output = None
        agg_total = None

    if entries and all(e.duration_s is not None for e in entries):
        agg_duration: float | None = sum(e.duration_s or 0.0 for e in entries)
    else:
        agg_duration = None

    return AttemptLedger(
        work_order_id=work_order_id,
        objective=order.objective,
        state=state,
        developer_attempts=developer_attempts,
        max_developer_attempts=max_attempts,
        corrections_remaining=corrections,
        entries=tuple(entries),
        total_input_units=agg_input,
        total_output_units=agg_output,
        total_units=agg_total,
        usage_unit=agg_unit,
        total_duration_s=agg_duration,
    )


__all__ = [
    "AttemptLedger",
    "AttemptLedgerEntry",
    "build_attempt_ledger",
]
