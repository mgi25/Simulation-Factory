"""Machine-readable measurements of the context an execution actually used.

Counts in this module are observations, never guesses.  Token and monetary
measurements carry their provenance explicitly, and unavailable values remain
``None``.  This lets a dashboard aggregate what is known without turning a
missing provider field into a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from ai_platform.references import assert_reference
from ai_platform.serde import fingerprint as _fingerprint, to_jsonable


SCHEMA_VERSION = 1


class EfficiencyError(ValueError):
    """An efficiency record is internally inconsistent."""


class MeasurementSource(str, Enum):
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class BenchmarkMode(str, Enum):
    BASELINE = "baseline"
    CAPSULE_OPTIMIZED = "capsule_optimized"
    FULL_RAW_CONTEXT = "full_raw_context"


class ReuseTier(str, Enum):
    COMPANY_OS_CAPABILITY = "existing_company_os_capability"
    PROJECT_UTILITY = "existing_project_utility"
    STANDARD_LIBRARY = "python_standard_library"
    INSTALLED_DEPENDENCY = "existing_installed_dependency"
    SMALL_IMPLEMENTATION = "small_new_implementation"
    LARGE_SUBSYSTEM = "large_new_subsystem"


_REUSE_ORDER = tuple(ReuseTier)


@dataclass(frozen=True)
class TokenMeasurement:
    source: MeasurementSource
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    method: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, MeasurementSource):
            raise EfficiencyError("token source must be a MeasurementSource")
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            _optional_count(getattr(self, name), f"tokens.{name}")
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.source is MeasurementSource.UNAVAILABLE:
            if any(value is not None for value in values):
                raise EfficiencyError("unavailable token measurements cannot carry counts")
            if not self.reason.strip():
                raise EfficiencyError("unavailable token measurements require a reason")
        elif all(value is None for value in values):
            raise EfficiencyError("reported or estimated token measurements need a count")
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise EfficiencyError("total_tokens must equal input_tokens + output_tokens")
        if self.source is MeasurementSource.ESTIMATED and not self.method.strip():
            raise EfficiencyError("estimated token measurements require a method")

    @classmethod
    def unavailable(cls, reason: str) -> "TokenMeasurement":
        return cls(MeasurementSource.UNAVAILABLE, reason=reason)

    @classmethod
    def provider_reported(
        cls, *, input_tokens: int | None, output_tokens: int | None,
        total_tokens: int | None = None, method: str = "provider usage"
    ) -> "TokenMeasurement":
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return cls(
            MeasurementSource.PROVIDER_REPORTED,
            input_tokens,
            output_tokens,
            total_tokens,
            method,
        )


def estimate_tokens(input_text: str, output_text: str = "") -> TokenMeasurement:
    """A dependency-free fallback: ceil(UTF-8 bytes / 4), labelled as estimated.

    This is deliberately not presented as provider usage.  A provider adapter
    should replace it with reported usage whenever that field exists.
    """

    def estimate(text: str) -> int:
        size = len(text.encode("utf-8"))
        return (size + 3) // 4

    input_count = estimate(input_text)
    output_count = estimate(output_text)
    return TokenMeasurement(
        MeasurementSource.ESTIMATED,
        input_count,
        output_count,
        input_count + output_count,
        "ceil(utf8_bytes/4)",
    )


@dataclass(frozen=True)
class CostMeasurement:
    source: MeasurementSource
    amount: str | None = None
    currency: str = ""
    rate_ref: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, MeasurementSource):
            raise EfficiencyError("cost source must be a MeasurementSource")
        if self.source is MeasurementSource.UNAVAILABLE:
            if self.amount is not None or self.currency or self.rate_ref:
                raise EfficiencyError("unavailable cost cannot carry an amount or rate")
            if not self.reason.strip():
                raise EfficiencyError("unavailable cost requires a reason")
            return
        if not isinstance(self.amount, str) or not self.amount.strip():
            raise EfficiencyError("reported or estimated cost requires a decimal amount")
        try:
            value = Decimal(self.amount)
        except InvalidOperation as exc:
            raise EfficiencyError("cost amount must be a decimal string") from exc
        if value < 0 or not self.currency.strip():
            raise EfficiencyError("cost must be non-negative and name a currency")
        if self.source is MeasurementSource.ESTIMATED and not self.rate_ref.strip():
            raise EfficiencyError("estimated cost requires an evidence-backed rate_ref")

    @classmethod
    def unavailable(cls, reason: str) -> "CostMeasurement":
        return cls(MeasurementSource.UNAVAILABLE, reason=reason)


@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    available: bool
    enabled: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if self.enabled and not self.available:
            raise EfficiencyError(f"{self.name}: unavailable integration cannot be enabled")
        if not self.enabled and not self.reason.strip():
            raise EfficiencyError(f"{self.name}: disabled integration requires a reason")


@dataclass(frozen=True)
class MinimalismCheck:
    selected_tier: ReuseTier
    considered_tiers: tuple[ReuseTier, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise EfficiencyError("minimalism check requires a reason")
        if self.selected_tier not in self.considered_tiers:
            raise EfficiencyError("selected reuse tier must be recorded as considered")
        selected_index = _REUSE_ORDER.index(self.selected_tier)
        required = set(_REUSE_ORDER[: selected_index + 1])
        if not required.issubset(self.considered_tiers):
            raise EfficiencyError("minimalism check must consider every cheaper reuse tier")

    @property
    def created_new_code(self) -> bool:
        return self.selected_tier in {
            ReuseTier.SMALL_IMPLEMENTATION,
            ReuseTier.LARGE_SUBSYSTEM,
        }


def check_reuse(selected_tier: ReuseTier, reason: str) -> MinimalismCheck:
    index = _REUSE_ORDER.index(selected_tier)
    return MinimalismCheck(selected_tier, _REUSE_ORDER[: index + 1], reason)


@dataclass(frozen=True)
class EfficiencyRecord:
    run_id: str
    task_id: str
    mode: BenchmarkMode
    capabilities_selected: tuple[str, ...]
    capsules_selected: tuple[str, ...]
    capsule_count: int
    capsule_chars: int
    context_chars: int
    context_bytes: int
    context_manifest_fingerprint: str
    execution_packet_chars: int
    execution_packet_bytes: int
    repository_references_selected: tuple[str, ...]
    repository_files_read: tuple[str, ...]
    tool_calls: int | None
    tool_output_chars: int | None
    tool_output_bytes: int | None
    tool_context_chars: int | None
    tool_context_bytes: int | None
    tokens: TokenMeasurement
    cache_hits: int | None
    cache_misses: int | None
    context_expansion_requests: int
    context_expansion_approvals: int
    context_expansion_denials: int
    latency_ms: int | None
    model: str | None
    cost: CostMeasurement
    packet_fingerprint: str = ""
    packet_attempt: int | None = None
    minimalism: MinimalismCheck | None = None
    integrations: tuple[IntegrationStatus, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        assert_reference(self.run_id, "efficiency.run_id")
        assert_reference(self.task_id, "efficiency.task_id")
        if not isinstance(self.mode, BenchmarkMode):
            raise EfficiencyError("efficiency mode must be a BenchmarkMode")
        if self.capsule_count != len(self.capsules_selected):
            raise EfficiencyError("capsule_count must match capsules_selected")
        for name in (
            "capsule_count", "capsule_chars", "context_chars", "context_bytes",
            "execution_packet_chars", "execution_packet_bytes",
            "context_expansion_requests", "context_expansion_approvals",
            "context_expansion_denials",
        ):
            _count(getattr(self, name), name)
        for name in (
            "tool_calls", "tool_output_chars", "tool_output_bytes",
            "tool_context_chars", "tool_context_bytes", "cache_hits",
            "cache_misses", "latency_ms", "packet_attempt",
        ):
            _optional_count(getattr(self, name), name)
        if self.context_expansion_approvals + self.context_expansion_denials > self.context_expansion_requests:
            raise EfficiencyError("expansion decisions cannot exceed requests")
        _fingerprint_value(self.context_manifest_fingerprint, "context manifest")
        if self.packet_fingerprint:
            _fingerprint_value(self.packet_fingerprint, "packet")
        if self.packet_attempt is not None and not self.packet_fingerprint:
            raise EfficiencyError("packet_attempt requires packet_fingerprint")
        if not isinstance(self.tokens, TokenMeasurement):
            raise EfficiencyError("tokens must be a TokenMeasurement")
        if not isinstance(self.cost, CostMeasurement):
            raise EfficiencyError("cost must be a CostMeasurement")
        names = [item.name for item in self.integrations]
        if len(names) != len(set(names)):
            raise EfficiencyError("integration status names must be unique")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EfficiencyRecord":
        tokens = data.get("tokens", {})
        cost = data.get("cost", {})
        minimalism = data.get("minimalism")
        return cls(
            run_id=str(data["run_id"]), task_id=str(data["task_id"]),
            mode=BenchmarkMode(data["mode"]),
            capabilities_selected=tuple(data.get("capabilities_selected", ())),
            capsules_selected=tuple(data.get("capsules_selected", ())),
            capsule_count=int(data["capsule_count"]),
            capsule_chars=int(data["capsule_chars"]),
            context_chars=int(data["context_chars"]),
            context_bytes=int(data["context_bytes"]),
            context_manifest_fingerprint=str(data["context_manifest_fingerprint"]),
            execution_packet_chars=int(data["execution_packet_chars"]),
            execution_packet_bytes=int(data["execution_packet_bytes"]),
            repository_references_selected=tuple(data.get("repository_references_selected", ())),
            repository_files_read=tuple(data.get("repository_files_read", ())),
            tool_calls=data.get("tool_calls"), tool_output_chars=data.get("tool_output_chars"),
            tool_output_bytes=data.get("tool_output_bytes"),
            tool_context_chars=data.get("tool_context_chars"),
            tool_context_bytes=data.get("tool_context_bytes"),
            tokens=TokenMeasurement(
                MeasurementSource(tokens["source"]), tokens.get("input_tokens"),
                tokens.get("output_tokens"), tokens.get("total_tokens"),
                tokens.get("method", ""), tokens.get("reason", ""),
            ),
            cache_hits=data.get("cache_hits"), cache_misses=data.get("cache_misses"),
            context_expansion_requests=int(data.get("context_expansion_requests", 0)),
            context_expansion_approvals=int(data.get("context_expansion_approvals", 0)),
            context_expansion_denials=int(data.get("context_expansion_denials", 0)),
            latency_ms=data.get("latency_ms"), model=data.get("model"),
            cost=CostMeasurement(
                MeasurementSource(cost["source"]), cost.get("amount"),
                cost.get("currency", ""), cost.get("rate_ref", ""), cost.get("reason", ""),
            ),
            packet_fingerprint=str(data.get("packet_fingerprint", "")),
            packet_attempt=data.get("packet_attempt"),
            minimalism=(
                MinimalismCheck(
                    ReuseTier(minimalism["selected_tier"]),
                    tuple(ReuseTier(item) for item in minimalism["considered_tiers"]),
                    minimalism["reason"],
                ) if minimalism else None
            ),
            integrations=tuple(
                IntegrationStatus(item["name"], item["available"], item["enabled"], item.get("reason", ""))
                for item in data.get("integrations", ())
            ),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class EfficiencyComparison:
    baseline_run_id: str
    optimized_run_id: str
    context_reduction_pct: float | None
    token_reduction_pct: float | None
    repository_read_reduction_pct: float | None


@dataclass(frozen=True)
class EfficiencySummary:
    """Stable aggregate shape for the future CEO dashboard."""

    total_runs: int
    average_input_tokens: float | None
    average_output_tokens: float | None
    token_source: MeasurementSource | None
    provider_reported_token_runs: int
    estimated_token_runs: int
    unavailable_token_runs: int
    average_context_bytes: float | None
    average_context_reduction_pct: float | None
    cost_amount: str | None
    cost_currency: str | None
    cost_source: MeasurementSource | None
    cache_hit_rate: float | None
    context_expansion_rate: float | None
    average_repository_files_read: float | None
    tool_output_reduction_pct: float | None


def compare_efficiency(baseline: EfficiencyRecord, optimized: EfficiencyRecord) -> EfficiencyComparison:
    return EfficiencyComparison(
        baseline.run_id,
        optimized.run_id,
        _reduction(baseline.context_chars, optimized.context_chars),
        _reduction(baseline.tokens.total_tokens, optimized.tokens.total_tokens),
        _reduction(len(baseline.repository_files_read), len(optimized.repository_files_read)),
    )


def summarise_efficiency(records: tuple[EfficiencyRecord, ...]) -> EfficiencySummary:
    comparisons: list[EfficiencyComparison] = []
    for task_id in sorted({record.task_id for record in records}):
        own = [record for record in records if record.task_id == task_id]
        baseline = [record for record in own if record.mode is BenchmarkMode.BASELINE]
        optimized = [record for record in own if record.mode is BenchmarkMode.CAPSULE_OPTIMIZED]
        if baseline and optimized:
            comparisons.append(compare_efficiency(baseline[-1], optimized[-1]))

    measured_tokens = [
        r.tokens for r in records
        if r.tokens.source is not MeasurementSource.UNAVAILABLE
    ]
    token_sources = {measurement.source for measurement in measured_tokens}
    one_token_source = (
        next(iter(token_sources))
        if len(token_sources) == 1 and len(measured_tokens) == len(records)
        else None
    )
    input_tokens = [
        measurement.input_tokens for measurement in measured_tokens
        if measurement.input_tokens is not None
    ]
    output_tokens = [
        measurement.output_tokens for measurement in measured_tokens
        if measurement.output_tokens is not None
    ]
    reductions = [
        item.context_reduction_pct for item in comparisons
        if item.context_reduction_pct is not None
    ]
    cache_hits = sum(r.cache_hits or 0 for r in records if r.cache_hits is not None)
    cache_misses = sum(r.cache_misses or 0 for r in records if r.cache_misses is not None)
    cache_total = cache_hits + cache_misses
    expansion_runs = sum(1 for r in records if r.context_expansion_requests)
    raw = sum(r.tool_output_bytes or 0 for r in records if r.tool_output_bytes is not None)
    context = sum(r.tool_context_bytes or 0 for r in records if r.tool_context_bytes is not None)
    priced = [r.cost for r in records if r.cost.amount is not None]
    currencies = {item.currency for item in priced}
    cost_sources = {item.source for item in priced}
    cost_amount = (
        str(sum((Decimal(item.amount or "0") for item in priced), Decimal("0")))
        if priced and len(priced) == len(records) and len(currencies) == 1
        and len(cost_sources) == 1
        else None
    )
    return EfficiencySummary(
        total_runs=len(records),
        average_input_tokens=_average(input_tokens) if one_token_source else None,
        average_output_tokens=_average(output_tokens) if one_token_source else None,
        token_source=one_token_source,
        provider_reported_token_runs=sum(
            1 for r in records if r.tokens.source is MeasurementSource.PROVIDER_REPORTED
        ),
        estimated_token_runs=sum(
            1 for r in records if r.tokens.source is MeasurementSource.ESTIMATED
        ),
        unavailable_token_runs=sum(
            1 for r in records if r.tokens.source is MeasurementSource.UNAVAILABLE
        ),
        average_context_bytes=_average([r.context_bytes for r in records]),
        average_context_reduction_pct=_average(reductions),
        cost_amount=cost_amount,
        cost_currency=next(iter(currencies)) if cost_amount is not None else None,
        cost_source=(next(iter(cost_sources)) if cost_amount is not None else None),
        cache_hit_rate=(cache_hits / cache_total) if cache_total else None,
        context_expansion_rate=(expansion_runs / len(records)) if records else None,
        average_repository_files_read=_average(
            [len(r.repository_files_read) for r in records]
        ),
        tool_output_reduction_pct=_reduction(raw, context),
    )


def _reduction(baseline: int | None, optimized: int | None) -> float | None:
    if baseline is None or optimized is None or baseline == 0:
        return None
    return ((baseline - optimized) / baseline) * 100.0


def _average(values: list[int | float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _count(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EfficiencyError(f"{field} must be a non-negative integer")


def _optional_count(value: Any, field: str) -> None:
    if value is not None:
        _count(value, field)


def _fingerprint_value(value: str, field: str) -> None:
    if len(value) != 16 or any(char not in "0123456789abcdef" for char in value):
        raise EfficiencyError(f"{field} fingerprint must be 16 lowercase hex characters")
