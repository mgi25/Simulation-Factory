"""Shared, provider-neutral result and telemetry shapes for Benchmark C2.

Deliberately small: this benchmark measures navigation, not implementation,
so the shapes only need to carry a symbol, its location, an optional bounded
body, and enough telemetry to total resource cost per condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolMatch:
    """One bounded navigation result: a symbol, its kind, and its location."""

    name: str
    kind: str
    file: str
    start_line: int
    end_line: int | None = None
    body: str = ""
    body_truncated: bool = False

    def compact(self) -> str:
        """Encode as the compact string a CodeIntelligenceResult.references entry uses."""
        span = f"{self.start_line}-{self.end_line}" if self.end_line else str(self.start_line)
        return f"{self.file}:{span}:{self.kind}:{self.name}"


@dataclass(frozen=True)
class ProviderQueryResult:
    """Result of one bounded provider query, independent of the canonical Protocol."""

    provider: str
    query_kind: str
    value: str
    matches: tuple[SymbolMatch, ...]
    available: bool
    reason: str = ""
    truncated: bool = False

    @property
    def result_chars(self) -> int:
        return sum(len(m.compact()) + len(m.body) for m in self.matches)


@dataclass(frozen=True)
class ProviderCallRecord:
    """One provider invocation, for later aggregation into Checkpoint D telemetry."""

    provider: str
    query_kind: str
    value: str
    latency_ms: float
    result_chars: int
    match_count: int
    truncated: bool
    available: bool
    error: str = ""


@dataclass
class ProviderTelemetry:
    """Deterministic, local, no-model-call telemetry for provider queries.

    This is intentionally separate from the runner's real model-usage
    telemetry (turns/cache-read/cost/etc.), which Checkpoint D captures via
    the existing external engineering runner. This class only ever measures
    the candidate-provider side: query count, latency, result size, and
    truncation/error counts.
    """

    records: list[ProviderCallRecord] = field(default_factory=list)

    def record(self, record: ProviderCallRecord) -> None:
        self.records.append(record)

    @property
    def query_count(self) -> int:
        return len(self.records)

    @property
    def total_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self.records)

    @property
    def total_result_chars(self) -> int:
        return sum(r.result_chars for r in self.records)

    @property
    def truncation_count(self) -> int:
        return sum(1 for r in self.records if r.truncated)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.records if r.error)

    def summary(self) -> dict[str, object]:
        return {
            "query_count": self.query_count,
            "total_latency_ms": round(self.total_latency_ms, 3),
            "total_result_chars": self.total_result_chars,
            "truncation_count": self.truncation_count,
            "error_count": self.error_count,
        }
