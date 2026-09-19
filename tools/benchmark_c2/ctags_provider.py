"""Isolated Universal Ctags GDScript navigation provider for Benchmark C2.

Ctags is never vendored and never added as a production dependency. This
module only shells out to a ctags binary that already exists on the machine
(system PATH, an explicit ``CTAGS_BIN`` override, or the winget per-user
install location) and writes its generated tag index to a temp file outside
the repository. Benchmark C's own finding governs the indexing invocation
used here: recursive ``-R`` mode produced zero useful GDScript tags in this
environment, so this provider always builds an explicit file list instead.

Ctags has no cross-reference/caller tracking for GDScript (confirmed via
``ctags --list-kinds-full=GDScript``: no kind has a reference role), so
``CALLERS``/``DEPENDENCIES``/``PATH`` queries are honestly reported
unavailable rather than emulated.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
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


@dataclass(frozen=True)
class CtagsIndexStats:
    files_indexed: int
    build_time_ms: float
    index_bytes: int
    tag_count: int
    tags_path: str


def locate_ctags_binary() -> str | None:
    """Find a ctags executable without vendoring one into the repo."""
    override = os.environ.get("CTAGS_BIN")
    if override and Path(override).is_file():
        return override
    found = shutil.which("ctags")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates = glob.glob(
            str(Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
                / "UniversalCtags.Ctags_*" / "ctags.exe")
        )
        if candidates:
            return candidates[0]
    return None


class CtagsProvider:
    """CodeIntelligenceProvider backed by an isolated Universal Ctags index."""

    name = "ctags"

    def __init__(
        self,
        repo_root: str | Path,
        *,
        ctags_bin: str | None = None,
        telemetry: ProviderTelemetry | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ctags_bin = ctags_bin or locate_ctags_binary()
        self.telemetry = telemetry or ProviderTelemetry()
        self._tags_by_name: dict[str, list[SymbolMatch]] = {}
        self._tags_by_file: dict[str, list[SymbolMatch]] = {}
        self.index_stats: CtagsIndexStats | None = None

    @property
    def available(self) -> bool:
        return self.ctags_bin is not None

    def build_index(self, *, glob_pattern: str = "godot/**/*.gd") -> CtagsIndexStats:
        """Index GDScript files via an explicit file list (never ``-R``)."""
        if not self.available:
            raise RuntimeError("ctags binary not found; check CTAGS_BIN or PATH")
        files = sorted(
            str(p.relative_to(self.repo_root))
            for p in self.repo_root.glob(glob_pattern)
            if p.is_file()
        )
        with tempfile.TemporaryDirectory(prefix="benchmark_c2_ctags_") as tmpdir:
            filelist_path = Path(tmpdir) / "filelist.txt"
            tags_path = Path(tempfile.gettempdir()) / "benchmark_c2_gd_tags.tags"
            filelist_path.write_text("\n".join(files), encoding="utf-8")
            start = time.perf_counter()
            subprocess.run(
                [
                    self.ctags_bin, "-f", str(tags_path),
                    "-L", str(filelist_path),
                    "--languages=GDScript", "--fields=+n",
                ],
                cwd=self.repo_root, check=True, capture_output=True,
            )
            build_time_ms = (time.perf_counter() - start) * 1000
        self._parse_tags_file(tags_path)
        stats = CtagsIndexStats(
            files_indexed=len(files),
            build_time_ms=round(build_time_ms, 3),
            index_bytes=tags_path.stat().st_size,
            tag_count=sum(len(v) for v in self._tags_by_name.values()),
            tags_path=str(tags_path),
        )
        self.index_stats = stats
        return stats

    def _parse_tags_file(self, tags_path: Path) -> None:
        self._tags_by_name.clear()
        self._tags_by_file.clear()
        text = tags_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("!"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            name, file_, _pattern = parts[0], parts[1], parts[2]
            kind = ""
            line_no = 0
            for extra in parts[3:]:
                extra = extra.rstrip(';"')
                if extra in ("m", "v", "c", "C", "e", "g", "s", "z", "l"):
                    kind = extra
                elif extra.startswith("line:"):
                    try:
                        line_no = int(extra.split(":", 1)[1])
                    except ValueError:
                        line_no = 0
            match = SymbolMatch(name=name, kind=kind, file=file_, start_line=line_no)
            self._tags_by_name.setdefault(name, []).append(match)
            self._tags_by_file.setdefault(file_, []).append(match)

    def find_definition(self, symbol_name: str) -> ProviderQueryResult:
        start = time.perf_counter()
        matches = tuple(self._tags_by_name.get(symbol_name, ()))
        truncated = len(matches) > MAX_MATCHES
        bounded = matches[:MAX_MATCHES]
        result = self._to_result("find_definition", symbol_name, bounded, truncated)
        self._record(start, result)
        return result

    def symbols_in_file(self, file_path: str) -> ProviderQueryResult:
        start = time.perf_counter()
        matches = tuple(self._tags_by_file.get(file_path, ()))
        truncated = len(matches) > MAX_MATCHES
        bounded = matches[:MAX_MATCHES]
        result = self._to_result("symbols_in_file", file_path, bounded, truncated)
        self._record(start, result)
        return result

    def _to_result(self, query_kind, value, matches, truncated):
        chars = sum(len(m.compact()) for m in matches)
        if chars > MAX_RESULT_CHARS:
            kept: list[SymbolMatch] = []
            running = 0
            for m in matches:
                running += len(m.compact())
                if running > MAX_RESULT_CHARS:
                    truncated = True
                    break
                kept.append(m)
            matches = tuple(kept)
        return ProviderQueryResult(
            provider=self.name, query_kind=query_kind, value=value,
            matches=matches, available=self.available, truncated=truncated,
            reason="" if matches or not self.available else "no matching symbol in index",
        )

    def _record(self, start: float, result) -> None:
        latency_ms = (time.perf_counter() - start) * 1000
        self.telemetry.record(ProviderCallRecord(
            provider=self.name, query_kind=result.query_kind, value=result.value,
            latency_ms=round(latency_ms, 4), result_chars=result.result_chars,
            match_count=len(result.matches), truncated=result.truncated,
            available=result.available,
        ))

    def query(self, request: CodeIntelligenceQuery) -> CodeIntelligenceResult:
        """Adapt to the canonical CodeIntelligenceProvider Protocol (read-only, additive)."""
        if request.kind is CodeQueryKind.SYMBOLS:
            result = self.find_definition(request.value)
            return CodeIntelligenceResult(
                request, tuple(m.compact() for m in result.matches),
                result.available and bool(result.matches), self.name,
                result.reason or "ctags definition lookup",
            )
        return CodeIntelligenceResult(
            request, (), False, self.name,
            "ctags has no reference/caller graph for GDScript; "
            f"{request.kind.value} is not supported by this provider",
        )
