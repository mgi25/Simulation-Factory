"""A compact, deterministic execution/navigation artifact for one session.

## What this is, and what it is not

`ExecutionContextBundle` turns "here is a work order" into "here are the 2-5
files that matter, their exact symbols and line spans, who else depends on
them, and which tests already cover them" - computed once, outside the
session, from `repo_map.py`'s deterministic index. It is a navigation aid,
never a second governance system: nothing here grants a path, and a bundle
that named one nobody authorized would just be ignored by
`authorization.AuthorityEnvelope`, which reads the work order and nothing
this module produces.

It replaces two things `briefs.py` used to do separately and does not glue
them into a third: the free-text repo-map query V1 injected into every
briefing, and the *entire packet dumped as JSON* at the end of a developer
briefing (see `briefs.py`'s history). Both were pointers dressed up two
different ways; this is the one canonical rendering.

## The size budget, chosen before the matched job

`MAX_BUNDLE_CHARS = 6000`. Chosen for scale, not tuned to a job: a routine
packet's own referenced material ran 3,661-16,985 characters in the
consumer-mode baseline, and a bundle several times a packet's own size would
be the map's convenience turning into the packet's problem. `render()`
enforces this with a hard truncation, not a suggestion - `truncated` on the
returned bundle says so when it happens, so a reader (or a test) can tell an
honestly-bounded briefing from a silently-cut-off one.

## Reviewer vs. developer differ in what "primary" means, on purpose

This module does not decide which files are primary; it renders whatever list
it is given. `briefs.py` (developer) ranks by the objective's own text plus
the authorized paths, because a developer is choosing where to start.
`runner.py` (reviewer) passes the files the diff actually touched, because a
reviewer is judging a completed change, not discovering one - see section 5
of the milestone brief. Same renderer, same budget, different input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .repo_map import RepoMap, SymbolSpan
from .repo_map import neighborhood as repo_neighborhood
from .repo_map import query as repo_query

MAX_BUNDLE_CHARS = 6000
MAX_EXCERPT_LINES = 25
MAX_EXCERPT_CHARS = 600
# How many of the primary files get a source excerpt at all. Bounded
# separately from `limit` (how many files are listed) because a symbol
# excerpt is the expensive part of this artifact; the file list stays cheap
# whether or not excerpts are included.
MAX_FILES_WITH_EXCERPTS = 1
MAX_SYMBOLS_PER_EXCERPT = 2

TRUNCATION_MARKER = "\n... (execution context truncated at the size budget)\n"


@dataclass(frozen=True)
class SourceExcerpt:
    symbol: SymbolSpan
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol.to_dict(), "text": self.text}


@dataclass(frozen=True)
class RelevantFile:
    """One of the bundle's primary files: why it matters and what is in it."""

    path: str
    owner: str
    reason: str
    symbols: tuple[SymbolSpan, ...] = ()
    dependents: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    excerpts: tuple[SourceExcerpt, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "owner": self.owner,
            "reason": self.reason,
            "symbols": [s.to_dict() for s in self.symbols],
            "dependents": list(self.dependents),
            "tests": list(self.tests),
            "entry_points": list(self.entry_points),
            "excerpts": [e.to_dict() for e in self.excerpts],
        }


@dataclass(frozen=True)
class ContextPointer:
    """One packet-authorized context reference: never a body, always a pointer."""

    kind: str
    ref: str
    reason: str
    span: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "reason": self.reason, "span": self.span}


@dataclass(frozen=True)
class ExecutionContextBundle:
    """The one canonical repository-intelligence section a briefing renders."""

    files: tuple[RelevantFile, ...]
    context_refs: tuple[ContextPointer, ...] = ()
    budget_chars: int = MAX_BUNDLE_CHARS
    truncated: bool = False

    def render(self) -> str:
        if not self.files and not self.context_refs:
            return ""
        lines: list[str] = [
            "",
            "## Execution context (deterministic repository intelligence)",
            "",
            "Built once, outside this session, from the repository's own `ast` "
            "surface. Read the named files and symbols directly; do not re-derive "
            "this list with your own grep.",
            "",
        ]
        if self.files:
            lines.append("Primary relevant files:")
            for index, file in enumerate(self.files, start=1):
                lines.append(f"  {index}. {file.path} (owner: {file.owner}) - {file.reason}")
                if file.symbols:
                    spans = ", ".join(
                        f"{s.qualified_name}#{s.start_line}-{s.end_line} ({s.kind})"
                        for s in file.symbols
                    )
                    lines.append(f"     symbols: {spans}")
                if file.dependents:
                    lines.append(
                        "     other production modules that import it: "
                        + ", ".join(file.dependents)
                    )
                if file.tests:
                    lines.append("     tests already covering it: " + ", ".join(file.tests))
                if file.entry_points:
                    lines.append("     reached from entry point(s): " + ", ".join(file.entry_points))
                for excerpt in file.excerpts:
                    lines.append(
                        f"     excerpt of {excerpt.symbol.qualified_name} "
                        f"(lines {excerpt.symbol.start_line}-{excerpt.symbol.end_line}):"
                    )
                    lines.append("     ```")
                    lines.extend(f"     {line}" for line in excerpt.text.splitlines())
                    lines.append("     ```")
            lines.append("")
        if self.context_refs:
            lines.append("Context Company OS authorized for this task:")
            for ref in self.context_refs:
                span = f"#{ref.span[0]}-{ref.span[1]}" if ref.span else ""
                lines.append(f"  - [{ref.kind}] {ref.ref}{span} - {ref.reason}")
            lines.append("")
        text = "\n".join(lines)
        if len(text) > self.budget_chars:
            cut = max(self.budget_chars - len(TRUNCATION_MARKER), 0)
            return text[:cut] + TRUNCATION_MARKER
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": [f.to_dict() for f in self.files],
            "context_refs": [r.to_dict() for r in self.context_refs],
            "budget_chars": self.budget_chars,
            "truncated": self.truncated,
            "rendered_chars": len(self.render()),
        }


def _excerpt_candidates(symbols: Sequence[SymbolSpan]) -> list[SymbolSpan]:
    """Which symbols are worth an excerpt, biggest and most anchoring first.

    File order (what `hood.symbols` keeps, for readability in the plain
    listing) puts whichever symbol happens to be declared first ahead of the
    class the module is actually about - measured live: on this repository's
    own `repo_map.py`, file order picked a two-line tokenizer helper over
    `SymbolSpan`, `ModuleMap` and `RepoMap`. A class anchors a module more
    often than a function does, and a larger definition is more often the
    substance of a file than a one-line helper next to it - neither is a
    proxy for the objective's own words (this function never sees them), just
    a better default than declaration order.
    """
    return sorted(
        symbols,
        key=lambda s: (0 if s.kind == "class" else 1, -(s.end_line - s.start_line), s.start_line),
    )


def _read_excerpt(repo_root: Path, path: str, symbol: SymbolSpan) -> str | None:
    try:
        text = (repo_root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    end = min(symbol.end_line, symbol.start_line + MAX_EXCERPT_LINES - 1, len(lines))
    excerpt = "\n".join(lines[symbol.start_line - 1 : end])
    return excerpt[:MAX_EXCERPT_CHARS]


def _context_pointers(context_refs: Sequence[Mapping[str, Any]]) -> tuple[ContextPointer, ...]:
    pointers: list[ContextPointer] = []
    for raw in context_refs:
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind", "")).strip()
        ref = str(raw.get("ref", "")).strip()
        if not kind or not ref:
            continue
        span = raw.get("span")
        span_tuple = (
            (int(span[0]), int(span[1]))
            if isinstance(span, (list, tuple)) and len(span) == 2
            else None
        )
        pointers.append(
            ContextPointer(
                kind=kind, ref=ref, reason=str(raw.get("reason", "")).strip(), span=span_tuple
            )
        )
    return tuple(pointers)


def build_execution_context(
    repo_map: RepoMap | None,
    *,
    primary: Sequence[tuple[str, str]],
    context_refs: Sequence[Mapping[str, Any]] = (),
    repo_root: Path | None = None,
    limit: int = 5,
    include_excerpts: bool = True,
    budget_chars: int = MAX_BUNDLE_CHARS,
    symbol_limit: int = 12,
    dependent_limit: int = 6,
    test_limit: int = 5,
) -> ExecutionContextBundle:
    """Assemble the bundle from an already-ranked `(path, reason)` list.

    Ranking policy lives with the caller (`briefs.py` for a developer,
    `runner.py` for a reviewer - see the module docstring); this function only
    ever bounds, looks up and renders. `repo_map is None` or an unknown path
    still produces a bundle - possibly an empty one - never a raised error, so
    a missing map degrades the briefing rather than stopping the session.
    """
    files: list[RelevantFile] = []
    if repo_map is not None:
        seen: set[str] = set()
        for path, reason in primary:
            if path in seen or len(files) >= limit:
                continue
            seen.add(path)
            hood = repo_neighborhood(
                repo_map,
                path,
                symbol_limit=symbol_limit,
                dependent_limit=dependent_limit,
                test_limit=test_limit,
            )
            if not hood.found:
                continue
            excerpts: tuple[SourceExcerpt, ...] = ()
            if include_excerpts and repo_root is not None and len(files) < MAX_FILES_WITH_EXCERPTS:
                built: list[SourceExcerpt] = []
                for symbol in _excerpt_candidates(hood.symbols)[:MAX_SYMBOLS_PER_EXCERPT]:
                    text = _read_excerpt(repo_root, path, symbol)
                    if text:
                        built.append(SourceExcerpt(symbol=symbol, text=text))
                excerpts = tuple(built)
            module = repo_map.by_path(path)
            files.append(
                RelevantFile(
                    path=path,
                    owner=module.owner if module else "",
                    reason=reason,
                    symbols=hood.symbols,
                    dependents=hood.dependents,
                    tests=hood.tests,
                    entry_points=hood.entry_points,
                    excerpts=excerpts,
                )
            )
    bundle = ExecutionContextBundle(
        files=tuple(files),
        context_refs=_context_pointers(context_refs),
        budget_chars=budget_chars,
    )
    truncated = len(bundle.render()) >= budget_chars
    return ExecutionContextBundle(
        files=bundle.files,
        context_refs=bundle.context_refs,
        budget_chars=budget_chars,
        truncated=truncated,
    )


def rank_primary_files(
    repo_map: RepoMap | None,
    *,
    objective: str,
    focus_paths: Sequence[str],
    limit: int = 5,
    max_query_fill: int = 2,
    minimum_files: int = 2,
) -> tuple[tuple[str, str], ...]:
    """The developer-side ranking: authorized paths first, then the objective's
    own best matches, deduplicated and capped.

    Authorized paths come first because they are certain - the work order
    already named them - while a text query is a guess, however good. A
    reviewer does not use this function at all: it uses the diff's actual
    changed paths instead (`runner.py`), which need no ranking because they
    are not a guess either.

    The free-text query only fills up to `minimum_files` total, not up to
    `limit` - measured live on this repository's own real scale (593 Python
    files, not the tests' small synthetic fixture): a query for "extend
    repo_map.py with symbol spans and reverse production dependencies" ranked
    `tests/test_company_finance.py` and `tests/test_company_youtube_studio_
    ingestion.py` alongside the file actually being changed, because a test
    file's path routinely repeats its subject's own name - "repo_map" inside
    "test_engineering_runner_repo_map.py" - and `query`'s path-token weighting
    cannot tell that apart from the module itself; the false positives score
    exactly as high as the true one, so raising a score threshold would not
    fix it. Padding a 1-file work order out to `limit` (5) files this way
    turned the bundle into padding rather than intelligence. `max_query_fill`
    remains a hard ceiling on the guessed portion regardless of `minimum_files`
    or `limit`.
    """
    if repo_map is None:
        return ()
    ranked: list[tuple[str, str]] = []
    seen: set[str] = set()
    for path in focus_paths:
        if path in seen or len(ranked) >= limit:
            continue
        if repo_map.by_path(path) is None:
            continue
        seen.add(path)
        ranked.append((path, "a path this work order authorizes changing"))
    query_budget = min(
        max_query_fill, max(minimum_files - len(ranked), 0), max(limit - len(ranked), 0)
    )
    added_from_query = 0
    if query_budget:
        for hit in repo_query(repo_map, objective, limit=query_budget + len(seen)):
            if added_from_query >= query_budget:
                break
            if hit.path in seen:
                continue
            seen.add(hit.path)
            symbols = ", ".join(hit.matched_symbols[:3])
            reason = (
                f"matched the objective on: {symbols}" if symbols else "matched the objective's text"
            )
            ranked.append((hit.path, reason))
            added_from_query += 1
    return tuple(ranked)


__all__ = [
    "MAX_BUNDLE_CHARS",
    "MAX_EXCERPT_CHARS",
    "MAX_EXCERPT_LINES",
    "MAX_FILES_WITH_EXCERPTS",
    "MAX_SYMBOLS_PER_EXCERPT",
    "ContextPointer",
    "ExecutionContextBundle",
    "RelevantFile",
    "SourceExcerpt",
    "build_execution_context",
    "rank_primary_files",
]
