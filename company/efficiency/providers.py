"""Optional code-intelligence and tool-output compression boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from ai_platform.serde import fingerprint
from knowledge.company_os.capsules.index import normalise_path

from .telemetry import IntegrationStatus


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
