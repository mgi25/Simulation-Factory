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
    files_read_count: int
    cache_misses: int | None
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
            files_read_count=len(record.repository_files_read),
            cache_misses=record.cache_misses,
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
                    "latency_ms": entry.latency_ms,
                    "files_read_count": entry.files_read_count,
                    "cache_misses": entry.cache_misses,
                    "execution_packet_chars": entry.execution_packet_chars,
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
    strongest_indicators = {"claude-opus-4-6[1m]", "claude-opus-4-6"}
    all_strongest = bool(models) and models.issubset(strongest_indicators)

    return Baseline(
        entries=tuple(entries),
        summary=summary,
        total_cost_usd=total_cost,
        all_used_strongest_model=all_strongest,
        state_dirs_read=tuple(dirs_read),
    )


@dataclass(frozen=True)
class AfterComparison:
    """One AFTER run compared against the BEFORE baseline.

    Covers: context growth, input/output tokens, cache usage, tool calls,
    files read, wall time, cost proxy, model tier, and first-pass outcome.
    Reviewer findings, gate result and accepted-result quality are measured
    from the engineering lifecycle records, not from efficiency telemetry.
    """

    after_run_id: str
    after_task_id: str
    after_model: str | None
    baseline_entry_count: int
    baseline_all_strongest: bool
    baseline_total_cost_usd: str | None
    after_input_tokens: int | None
    after_output_tokens: int | None
    after_tool_calls: int | None
    after_cost_amount: str | None
    after_outcome: str
    baseline_avg_input_tokens: float | None
    baseline_avg_output_tokens: float | None
    baseline_avg_tool_calls: float | None
    input_token_change_pct: float | None
    output_token_change_pct: float | None
    tool_call_change_pct: float | None
    # Additional comparison dimensions
    after_cache_hits: int | None
    after_cache_misses: int | None
    baseline_avg_cache_hits: float | None
    cache_hit_change_pct: float | None
    after_latency_ms: int | None
    baseline_avg_latency_ms: float | None
    latency_change_pct: float | None
    after_files_read: int | None
    baseline_avg_files_read: float | None
    files_read_change_pct: float | None
    after_execution_packet_chars: int | None
    baseline_avg_execution_packet_chars: float | None
    context_growth_change_pct: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "after_run_id": self.after_run_id,
            "after_task_id": self.after_task_id,
            "after_model": self.after_model,
            "after_outcome": self.after_outcome,
            "baseline_entry_count": self.baseline_entry_count,
            "baseline_all_strongest": self.baseline_all_strongest,
            "baseline_total_cost_usd": self.baseline_total_cost_usd,
            "after_input_tokens": self.after_input_tokens,
            "after_output_tokens": self.after_output_tokens,
            "after_tool_calls": self.after_tool_calls,
            "after_cost_amount": self.after_cost_amount,
            "baseline_avg_input_tokens": self.baseline_avg_input_tokens,
            "baseline_avg_output_tokens": self.baseline_avg_output_tokens,
            "baseline_avg_tool_calls": self.baseline_avg_tool_calls,
            "input_token_change_pct": self.input_token_change_pct,
            "output_token_change_pct": self.output_token_change_pct,
            "tool_call_change_pct": self.tool_call_change_pct,
            "after_cache_hits": self.after_cache_hits,
            "after_cache_misses": self.after_cache_misses,
            "baseline_avg_cache_hits": self.baseline_avg_cache_hits,
            "cache_hit_change_pct": self.cache_hit_change_pct,
            "after_latency_ms": self.after_latency_ms,
            "baseline_avg_latency_ms": self.baseline_avg_latency_ms,
            "latency_change_pct": self.latency_change_pct,
            "after_files_read": self.after_files_read,
            "baseline_avg_files_read": self.baseline_avg_files_read,
            "files_read_change_pct": self.files_read_change_pct,
            "after_execution_packet_chars": self.after_execution_packet_chars,
            "baseline_avg_execution_packet_chars": self.baseline_avg_execution_packet_chars,
            "context_growth_change_pct": self.context_growth_change_pct,
        }


def _pct_change(baseline_avg: float | None, after: int | None) -> float | None:
    if baseline_avg is None or after is None or baseline_avg == 0:
        return None
    return ((after - baseline_avg) / baseline_avg) * 100.0


def compare_against_baseline(
    baseline: Baseline, record: EfficiencyRecord,
) -> AfterComparison:
    """Compare one AFTER execution record against the BEFORE baseline.

    Every number references the recorded run it was measured from (the
    baseline entries' run_ids and the after record's run_id).
    """
    b_input = [
        e.input_tokens for e in baseline.entries if e.input_tokens is not None
    ]
    b_output = [
        e.output_tokens for e in baseline.entries if e.output_tokens is not None
    ]
    b_tools = [
        e.tool_calls for e in baseline.entries if e.tool_calls is not None
    ]
    b_cache = [
        e.cache_hits for e in baseline.entries if e.cache_hits is not None
    ]
    b_latency = [
        e.latency_ms for e in baseline.entries if e.latency_ms is not None
    ]
    b_files = [e.files_read_count for e in baseline.entries]
    b_packet = [e.execution_packet_chars for e in baseline.entries]

    avg_in = (sum(b_input) / len(b_input)) if b_input else None
    avg_out = (sum(b_output) / len(b_output)) if b_output else None
    avg_tools = (sum(b_tools) / len(b_tools)) if b_tools else None
    avg_cache = (sum(b_cache) / len(b_cache)) if b_cache else None
    avg_latency = (sum(b_latency) / len(b_latency)) if b_latency else None
    avg_files = (sum(b_files) / len(b_files)) if b_files else None
    avg_packet = (sum(b_packet) / len(b_packet)) if b_packet else None

    cost_amount = (
        record.cost.amount
        if record.cost.source is not MeasurementSource.UNAVAILABLE
        else None
    )
    after_files = len(record.repository_files_read)

    return AfterComparison(
        after_run_id=record.run_id,
        after_task_id=record.task_id,
        after_model=record.model,
        baseline_entry_count=len(baseline.entries),
        baseline_all_strongest=baseline.all_used_strongest_model,
        baseline_total_cost_usd=baseline.total_cost_usd,
        after_input_tokens=record.tokens.input_tokens,
        after_output_tokens=record.tokens.output_tokens,
        after_tool_calls=record.tool_calls,
        after_cost_amount=cost_amount,
        after_outcome=record.outcome,
        baseline_avg_input_tokens=avg_in,
        baseline_avg_output_tokens=avg_out,
        baseline_avg_tool_calls=avg_tools,
        input_token_change_pct=_pct_change(avg_in, record.tokens.input_tokens),
        output_token_change_pct=_pct_change(avg_out, record.tokens.output_tokens),
        tool_call_change_pct=_pct_change(avg_tools, record.tool_calls),
        after_cache_hits=record.cache_hits,
        after_cache_misses=record.cache_misses,
        baseline_avg_cache_hits=avg_cache,
        cache_hit_change_pct=_pct_change(avg_cache, record.cache_hits),
        after_latency_ms=record.latency_ms,
        baseline_avg_latency_ms=avg_latency,
        latency_change_pct=_pct_change(avg_latency, record.latency_ms),
        after_files_read=after_files,
        baseline_avg_files_read=avg_files,
        files_read_change_pct=_pct_change(avg_files, after_files),
        after_execution_packet_chars=record.execution_packet_chars,
        baseline_avg_execution_packet_chars=avg_packet,
        context_growth_change_pct=_pct_change(avg_packet, record.execution_packet_chars),
    )


__all__ = [
    "AfterComparison",
    "Baseline",
    "BaselineEntry",
    "compare_against_baseline",
    "extract_baseline",
]
