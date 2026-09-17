"""Optional code-intelligence and tool-output compression boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from ai_platform.serde import fingerprint
from knowledge.company_os.capsules.index import normalise_path

from .telemetry import (
    CostMeasurement,
    IntegrationStatus,
    MeasurementSource,
    TokenMeasurement,
)


@dataclass(frozen=True)
class ProviderUsage:
    """Provider-neutral usage copied from an external provider response.

    The runtime's current executor is an external-session transport, not a
    provider client.  Consequently this adapter accepts the usage mapping that
    the executor observed and never treats absence as zero.
    """

    provider: str | None
    model: str | None
    tokens: TokenMeasurement
    latency_ms: int | None
    cost: CostMeasurement


def normalise_provider_usage(
    payload: Mapping[str, Any] | None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> ProviderUsage:
    """Normalize common provider usage shapes without inventing usage.

    Supported token names are OpenAI-style ``prompt_tokens`` /
    ``completion_tokens`` and provider-neutral/Anthropic-style
    ``input_tokens`` / ``output_tokens``.  Either may be nested under
    ``usage``.  A conflicting reported total is ignored in favour of the two
    provider-reported components; it is never allowed to corrupt finalization.
    """

    data: Mapping[str, Any] = payload or {}
    nested = data.get("usage")
    usage = nested if isinstance(nested, Mapping) else data
    input_tokens = _optional_provider_count(
        usage.get("input_tokens", usage.get("prompt_tokens"))
    )
    output_tokens = _optional_provider_count(
        usage.get("output_tokens", usage.get("completion_tokens"))
    )
    total_tokens = _optional_provider_count(usage.get("total_tokens"))
    if (
        total_tokens is not None
        and input_tokens is not None
        and output_tokens is not None
        and total_tokens != input_tokens + output_tokens
    ):
        total_tokens = None
    if any(value is not None for value in (input_tokens, output_tokens, total_tokens)):
        tokens = TokenMeasurement.provider_reported(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            method="normalized external provider usage",
        )
    else:
        tokens = TokenMeasurement.unavailable("provider omitted token usage")

    latency_ms = _optional_provider_count(data.get("latency_ms"))
    cost = _reported_cost(data)
    resolved_provider = provider or _optional_text(data.get("provider"))
    resolved_model = model or _optional_text(data.get("model"))
    return ProviderUsage(resolved_provider, resolved_model, tokens, latency_ms, cost)


def _reported_cost(data: Mapping[str, Any]) -> CostMeasurement:
    raw = data.get("cost")
    currency = _optional_text(data.get("currency")) or ""
    if isinstance(raw, Mapping):
        amount = raw.get("amount")
        currency = _optional_text(raw.get("currency")) or currency
    else:
        amount = raw
    if amount is None or not currency:
        return CostMeasurement.unavailable("provider omitted monetary cost")
    try:
        return CostMeasurement(
            MeasurementSource.PROVIDER_REPORTED,
            amount=str(amount),
            currency=currency,
        )
    except ValueError:
        return CostMeasurement.unavailable("provider returned invalid monetary cost")


def _optional_provider_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


class CodeQueryKind(str, Enum):
    SYMBOLS = "find_symbols"
    CALLERS = "find_callers"
    DEPENDENCIES = "find_dependencies"
    PATH = "find_path"
    LIKELY_FILES = "find_likely_files"


@dataclass(frozen=True)
class CodeIntelligenceQuery:
    kind: CodeQueryKind
    value: str
    destination: str = ""
    candidate_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeIntelligenceResult:
    query: CodeIntelligenceQuery
    references: tuple[str, ...]
    available: bool
    provider: str
    reason: str = ""


class CodeIntelligenceProvider(Protocol):
    name: str

    def query(self, request: CodeIntelligenceQuery) -> CodeIntelligenceResult: ...


class ReferenceRepositoryProvider:
    """The existing deterministic mechanism: validate caller-supplied paths.

    It does not pretend to be a symbol graph.  Those query kinds remain
    explicitly unavailable until a real provider (for example Graphify) is
    installed and injected.
    """

    name = "repository_references"

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    def query(self, request: CodeIntelligenceQuery) -> CodeIntelligenceResult:
        if request.kind is not CodeQueryKind.LIKELY_FILES:
            return CodeIntelligenceResult(
                request, (), False, self.name,
                "the reference provider has no symbol graph; inject a code-intelligence provider",
            )
        references: list[str] = []
        for value in sorted(set(request.candidate_paths)):
            cleaned = normalise_path(value)
            if not cleaned:
                continue
            path = (self.repo_root / cleaned).resolve()
            try:
                path.relative_to(self.repo_root)
            except ValueError:
                continue
            if path.is_file():
                references.append(path.relative_to(self.repo_root).as_posix())
        return CodeIntelligenceResult(
            request,
            tuple(references),
            True,
            self.name,
            "validated explicit repository references; no repository scan performed",
        )


GRAPHIFY_STATUS = IntegrationStatus(
    "graphify", False, False, "not installed; repository reference provider remains active"
)
RTK_STATUS = IntegrationStatus(
    "rtk", False, False, "not installed; raw tool output remains the model-context output"
)


class ToolOutputCompressor(Protocol):
    name: str

    def compress(self, raw_output: str) -> str: ...


@dataclass(frozen=True)
class ToolOutputArtifact:
    task_id: str
    command: str
    exit_status: int
    raw_output: str
    context_output: str
    important_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    summary: str = ""
    artifact_references: tuple[str, ...] = ()
    compressor: str = ""

    @property
    def compressed(self) -> bool:
        return bool(self.compressor)

    @property
    def raw_chars(self) -> int:
        return len(self.raw_output)

    @property
    def raw_bytes(self) -> int:
        return len(self.raw_output.encode("utf-8"))

    @property
    def context_chars(self) -> int:
        return len(self.context_output)

    @property
    def context_bytes(self) -> int:
        return len(self.context_output.encode("utf-8"))

    def fingerprint(self) -> str:
        return fingerprint(self)

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "ToolOutputArtifact":
        return cls(
            task_id=str(data["task_id"]), command=str(data["command"]),
            exit_status=int(data["exit_status"]), raw_output=str(data["raw_output"]),
            context_output=str(data["context_output"]),
            important_failures=tuple(data.get("important_failures", ())),
            warnings=tuple(data.get("warnings", ())), summary=str(data.get("summary", "")),
            artifact_references=tuple(data.get("artifact_references", ())),
            compressor=str(data.get("compressor", "")),
        )


def capture_tool_output(
    *, task_id: str, command: str, exit_status: int, raw_output: str,
    important_failures: tuple[str, ...] = (), warnings: tuple[str, ...] = (),
    summary: str = "", artifact_references: tuple[str, ...] = (),
    compressor: ToolOutputCompressor | None = None,
) -> ToolOutputArtifact:
    context_output = compressor.compress(raw_output) if compressor else raw_output
    return ToolOutputArtifact(
        task_id, command, exit_status, raw_output, context_output,
        important_failures, warnings, summary, artifact_references,
        compressor.name if compressor else "",
    )
