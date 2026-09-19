"""Isolated tree-sitter-gdscript navigation provider for Benchmark C2.

``tree-sitter`` / ``tree-sitter-gdscript`` are never added to the production
or Company OS dependency manifests. They are only ever imported when this
module is run inside the dedicated benchmark venv created for Benchmark C2
(outside the repository tree). The import is therefore lazy and guarded: importing
this module elsewhere in the repo does not require the packages to be
installed, and a missing installation is reported as ``available=False``
rather than raising.

Unlike Ctags, tree-sitter gives a native end-of-node position, so this
provider can return a real body/line-span — the capability Benchmark C's
prior research flagged as tree-sitter's unique differentiator. It still has
no cross-file caller/reference graph: relationship queries beyond
same-file structure are honestly reported unavailable, not emulated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from company.efficiency.providers import (
    CodeIntelligenceQuery,
    CodeIntelligenceResult,
    CodeQueryKind,
)

from .types import ProviderCallRecord, ProviderQueryResult, ProviderTelemetry, SymbolMatch

MAX_MATCHES = 20
MAX_RESULT_CHARS = 4000
MAX_BODY_CHARS = 4000

_DEFINITION_NODE_KINDS = {
    "function_definition": "method",
    "class_definition": "class",
    "variable_statement": "variable",
    "const_statement": "const",
    "signal_statement": "signal",
    "enum_definition": "enum",
}

try:  # pragma: no cover - exercised only inside the isolated benchmark venv
    import tree_sitter as _ts
    import tree_sitter_gdscript as _tsg

    _IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover
    _ts = None
    _tsg = None
    _IMPORT_ERROR = str(exc)


@dataclass(frozen=True)
class TreeSitterIndexStats:
    files_parsed: int
    parse_failures: int
    parse_time_ms: float
    symbol_count: int
    source_bytes_parsed: int


class TreeSitterProvider:
    """CodeIntelligenceProvider backed by isolated tree-sitter-gdscript parses."""

    name = "tree_sitter_gdscript"

    def __init__(
        self,
        repo_root: str | Path,
        *,
        telemetry: ProviderTelemetry | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.telemetry = telemetry or ProviderTelemetry()
        self._parser = None
        self._symbols_by_name: dict[str, list[SymbolMatch]] = {}
        self._symbols_by_file: dict[str, list[SymbolMatch]] = {}
        self._source_by_file: dict[str, bytes] = {}
        self.index_stats: TreeSitterIndexStats | None = None
        if _ts is not None and _tsg is not None:
            language = _ts.Language(_tsg.language())
            self._parser = _ts.Parser(language)

    @property
    def available(self) -> bool:
        return self._parser is not None

    @property
    def unavailable_reason(self) -> str:
        return _IMPORT_ERROR or ""

    def build_index(self, *, glob_pattern: str = "godot/**/*.gd") -> TreeSitterIndexStats:
        if not self.available:
            raise RuntimeError(f"tree-sitter-gdscript not installed: {self.unavailable_reason}")
        self._symbols_by_name.clear()
        self._symbols_by_file.clear()
        self._source_by_file.clear()
        files = sorted(p for p in self.repo_root.glob(glob_pattern) if p.is_file())
        start = time.perf_counter()
        failures = 0
        total_bytes = 0
        for path in files:
            rel = str(path.relative_to(self.repo_root))
            try:
                source = path.read_bytes()
            except OSError:
                failures += 1
                continue
            try:
                self._index_file(rel, source)
            except Exception:
                failures += 1
                continue
            total_bytes += len(source)
        parse_time_ms = (time.perf_counter() - start) * 1000
        stats = TreeSitterIndexStats(
            files_parsed=len(files) - failures,
            parse_failures=failures,
            parse_time_ms=round(parse_time_ms, 3),
            symbol_count=sum(len(v) for v in self._symbols_by_name.values()),
            source_bytes_parsed=total_bytes,
        )
        self.index_stats = stats
        return stats

    def _index_file(self, rel_path: str, source: bytes) -> None:
        tree = self._parser.parse(source)
        self._source_by_file[rel_path] = source
        matches: list[SymbolMatch] = []
        self._walk(tree.root_node, rel_path, source, matches, depth=0)
        self._symbols_by_file[rel_path] = matches
        for match in matches:
            self._symbols_by_name.setdefault(match.name, []).append(match)

    def _walk(self, node, rel_path: str, source: bytes, matches: list, depth: int) -> None:
        if depth > 2:
            return
        kind = _DEFINITION_NODE_KINDS.get(node.type)
        if kind is not None:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                matches.append(SymbolMatch(
                    name=name_node.text.decode("utf-8", "replace"),
                    kind=kind, file=rel_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                ))
        for child in node.children:
            self._walk(child, rel_path, source, matches, depth + 1)

    def find_definition(self, symbol_name: str, *, with_body: bool = False) -> ProviderQueryResult:
        start = time.perf_counter()
        matches = list(self._symbols_by_name.get(symbol_name, ()))
        truncated = len(matches) > MAX_MATCHES
        matches = matches[:MAX_MATCHES]
        if with_body:
            matches = [self._attach_body(m) for m in matches]
        result = self._to_result("find_definition", symbol_name, tuple(matches), truncated)
        self._record(start, result)
        return result

    def symbols_in_file(self, file_path: str) -> ProviderQueryResult:
        start = time.perf_counter()
        matches = tuple(self._symbols_by_file.get(file_path, ()))
        truncated = len(matches) > MAX_MATCHES
        matches = matches[:MAX_MATCHES]
        result = self._to_result("symbols_in_file", file_path, matches, truncated)
        self._record(start, result)
        return result

    def _attach_body(self, match: SymbolMatch) -> SymbolMatch:
        source = self._source_by_file.get(match.file)
        if source is None or match.end_line is None:
            return match
        lines = source.decode("utf-8", "replace").splitlines()
        body_lines = lines[match.start_line - 1: match.end_line]
        body = "\n".join(body_lines)
        truncated = len(body) > MAX_BODY_CHARS
        if truncated:
            body = body[:MAX_BODY_CHARS]
        return SymbolMatch(
            name=match.name, kind=match.kind, file=match.file,
            start_line=match.start_line, end_line=match.end_line,
            body=body, body_truncated=truncated,
        )

    def _to_result(self, query_kind, value, matches, truncated) -> ProviderQueryResult:
        chars = sum(len(m.compact()) + len(m.body) for m in matches)
        if chars > MAX_RESULT_CHARS:
            kept: list[SymbolMatch] = []
            running = 0
            for m in matches:
                running += len(m.compact()) + len(m.body)
                if running > MAX_RESULT_CHARS:
                    truncated = True
                    break
                kept.append(m)
            matches = tuple(kept)
        available = self.available
        return ProviderQueryResult(
            provider=self.name, query_kind=query_kind, value=value,
            matches=tuple(matches), available=available, truncated=truncated,
            reason="" if (matches or not available) else "no matching symbol in index",
        )

    def _record(self, start: float, result: ProviderQueryResult) -> None:
        latency_ms = (time.perf_counter() - start) * 1000
        self.telemetry.record(ProviderCallRecord(
            provider=self.name, query_kind=result.query_kind, value=result.value,
            latency_ms=round(latency_ms, 4), result_chars=result.result_chars,
            match_count=len(result.matches), truncated=result.truncated,
            available=result.available,
        ))

    def query(self, request: CodeIntelligenceQuery) -> CodeIntelligenceResult:
        """Adapt to the canonical CodeIntelligenceProvider Protocol (read-only, additive)."""
        if not self.available:
            return CodeIntelligenceResult(
                request, (), False, self.name,
                f"tree-sitter-gdscript not installed: {self.unavailable_reason}",
            )
        if request.kind is CodeQueryKind.SYMBOLS:
            result = self.find_definition(request.value, with_body=True)
            return CodeIntelligenceResult(
                request, tuple(m.compact() for m in result.matches),
                bool(result.matches), self.name,
                result.reason or "tree-sitter definition + span lookup",
            )
        return CodeIntelligenceResult(
            request, (), False, self.name,
            "tree-sitter-gdscript has no cross-file reference/caller graph; "
            f"{request.kind.value} is not supported by this provider",
        )
