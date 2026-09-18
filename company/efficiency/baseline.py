"""Extract a BEFORE baseline from recorded runs of actual Company engineering jobs.

This module reads the append-only efficiency store from one or more state
directories and produces a structured baseline summary.  Every number it
reports names the recorded run it was measured from; no saving is claimed
that was only simulated.

## What the baseline captures

For each recorded execution:
- task_id, model, provider, outcome
- input_tokens, output_tokens, cache_hits (provider-reported)
- tool_calls, context_chars, execution_packet_chars
- cost (provider-reported amount and currency)
- wall time (latency_ms when available)

The baseline summary aggregates these into averages, totals, and
distributions that the AFTER comparison can reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .store import EfficiencyStore
from .telemetry import (
    BenchmarkMode,
    EfficiencyRecord,
    EfficiencySummary,
    MeasurementSource,
    summarise_efficiency,
)


@dataclass(frozen=True)
class BaselineEntry:
    """One recorded execution, distilled to its baseline-relevant fields."""

    run_id: str
    task_id: str
    model: str | None
    provider: str | None
    outcome: str
    input_tokens: int | None
    output_tokens: int | None
    cache_hits: int | None
    tool_calls: int | None
    context_chars: int | None
    execution_packet_chars: int
    cost_amount: str | None
    cost_currency: str
    latency_ms: int | None
    state_dir: str

    @classmethod
    def from_record(
        cls, record: EfficiencyRecord, state_dir: str
    ) -> "BaselineEntry":
        cost_amount = (
            record.cost.amount
            if record.cost.source is not MeasurementSource.UNAVAILABLE
            else None
        )
        cost_currency = record.cost.currency if cost_amount else ""
        return cls(
            run_id=record.run_id,
            task_id=record.task_id,
            model=record.model,
            provider=record.provider,
            outcome=record.outcome,
            input_tokens=record.tokens.input_tokens,
            output_tokens=record.tokens.output_tokens,
            cache_hits=record.cache_hits,
            tool_calls=record.tool_calls,
            context_chars=record.context_chars,
            execution_packet_chars=record.execution_packet_chars,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            latency_ms=record.latency_ms,
            state_dir=state_dir,
        )


@dataclass(frozen=True)
class Baseline:
    """The BEFORE baseline from recorded runs."""

    entries: tuple[BaselineEntry, ...]
    summary: EfficiencySummary
    total_cost_usd: str | None
    all_used_strongest_model: bool
    state_dirs_read: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_count": len(self.entries),
            "entries": [
                {
                    "run_id": entry.run_id,
                    "task_id": entry.task_id,
                    "model": entry.model,
                    "provider": entry.provider,
                    "outcome": entry.outcome,
                    "input_tokens": entry.input_tokens,
                    "output_tokens": entry.output_tokens,
                    "cache_hits": entry.cache_hits,
                    "tool_calls": entry.tool_calls,
                    "cost_amount": entry.cost_amount,
                    "cost_currency": entry.cost_currency,
                }
                for entry in self.entries
            ],
            "total_cost_usd": self.total_cost_usd,
            "all_used_strongest_model": self.all_used_strongest_model,
            "state_dirs_read": list(self.state_dirs_read),
        }


def extract_baseline(*state_dirs: str | Path) -> Baseline:
    """Read efficiency records from state directories and build a baseline.

    Only real execution records (mode=REAL) are included.  Benchmark records
    are excluded because they contain no provider usage.
    """
    records: list[EfficiencyRecord] = []
    entries: list[BaselineEntry] = []
    dirs_read: list[str] = []

    for state_dir in state_dirs:
        path = Path(state_dir)
        if not path.exists():
            continue
        try:
            store = EfficiencyStore(path)
            all_records = store.all_records()
        except Exception:
            continue
        real = tuple(r for r in all_records if r.mode is BenchmarkMode.REAL)
        if not real:
            continue
        dirs_read.append(str(path))
        records.extend(real)
        entries.extend(
            BaselineEntry.from_record(r, str(path)) for r in real
        )

    summary = summarise_efficiency(tuple(records))

    # Total cost in USD from provider-reported entries
    usd_costs = [
        Decimal(e.cost_amount)
        for e in entries
        if e.cost_amount and e.cost_currency == "USD"
    ]
    total_cost = str(sum(usd_costs, Decimal("0"))) if usd_costs else None

    # Check if all jobs used the strongest model
    models = {e.model for e in entries if e.model}
    strongest_indicators = {"claude-opus-4-6[1m]", "claude-opus-4-6", "gpt-4o"}
    all_strongest = bool(models) and models.issubset(strongest_indicators)

    return Baseline(
        entries=tuple(entries),
        summary=summary,
        total_cost_usd=total_cost,
        all_used_strongest_model=all_strongest,
        state_dirs_read=tuple(dirs_read),
    )


__all__ = [
    "Baseline",
    "BaselineEntry",
    "extract_baseline",
]
