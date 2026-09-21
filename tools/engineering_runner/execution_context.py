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

import hashlib
import re
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

# Test-pattern anchors: acceptance criteria -> existing sibling test symbols.
# See `rank_test_anchors`. Bounds fixed before the V3B matched run (milestone
# section 4): at most 2 anchors, at most 1 of them carries an excerpt, and
# that excerpt obeys the same MAX_EXCERPT_LINES/MAX_EXCERPT_CHARS as a file's
# own excerpt - this is not a second, looser budget.
MAX_TEST_ANCHORS = 2
MAX_TEST_ANCHOR_EXCERPTS = 1

# P3: compile several exact task-relevant spans up front so a routine session
# does not have to rediscover the same file repeatedly. The spans share the
# existing bundle budget; this is a tighter sub-budget, not additional context.
SEMANTIC_COMPILER_VERSION = 1
MAX_COMPILED_SPANS = 6
MAX_COMPILED_SPAN_CHARS = 3200
MAX_COMPILED_SINGLE_SPAN_CHARS = 900

TRUNCATION_MARKER = "\n... (execution context truncated at the size budget)\n"

# Two identifier shapes count as an "exact identifier phrase": snake_case
# (`developer_attempts`) and PascalCase (`EngineeringJob`) - both are how a
# work order names an existing symbol in prose, and a criterion's own class
# name is often the strongest disambiguator between two candidates that both
# mention a generic method name (`to_dict`, `from_mapping`).
_IDENTIFIER_PHRASE_RE = re.compile(
    r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+"
)
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")

# Tokens too generic to count as a meaningful match on their own - fixture and
# control-flow vocabulary that appears in nearly every test regardless of
# subject. Without this list, `_config`/`_fake_repo`/`_validation` style
# helpers would tie with the actually-relevant sibling test on token overlap
# alone, because every test in the file calls them.
_STOP_TOKENS = frozenset(
    {
        "test", "def", "self", "assert", "return", "tmp", "path", "config",
        "state", "job", "order", "on", "day", "repo", "true", "false", "none",
        "import", "from", "for", "in", "with", "as", "not", "is", "and", "or",
        "the", "a", "an", "this", "that", "it", "to", "of", "if", "else",
        "store", "execution", "usage",
    }
)


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
class TestPatternAnchor:
    """One existing test symbol the acceptance criteria's own words point to.

    A pointer, like `ContextPointer` - never a licence to skip reading the
    file. At most one anchor in a bundle carries `excerpt`
    (`MAX_TEST_ANCHOR_EXCERPTS`); the rest are name-and-span pointers only.
    """

    path: str
    qualified_name: str
    start_line: int
    end_line: int
    reason: str
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "qualified_name": self.qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "reason": self.reason,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True)
class CompiledSpan:
    """One locally-selected symbol span injected before the provider starts."""

    path: str
    qualified_name: str
    start_line: int
    end_line: int
    reason: str
    text: str
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "qualified_name": self.qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "reason": self.reason,
            "text": self.text,
            "digest": self.digest,
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
    test_anchors: tuple[TestPatternAnchor, ...] = ()
    compiled_spans: tuple[CompiledSpan, ...] = ()
    budget_chars: int = MAX_BUNDLE_CHARS
    truncated: bool = False

    def render(self) -> str:
        if not self.files and not self.context_refs and not self.test_anchors:
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
        if self.compiled_spans:
            lines.append("Precompiled task spans (read-once semantic context):")
            lines.append(
                "  Start here. These exact ranges were selected locally from the work "
                "order before the provider session. Do not broadly re-read or grep the "
                "same span. If a missing detail is genuinely needed, Read remains a "
                "fallback: use a targeted, preferably non-overlapping range."
            )
            for span in self.compiled_spans:
                lines.append(
                    f"  - {span.path}::{span.qualified_name} "
                    f"#{span.start_line}-{span.end_line} "
                    f"[{span.digest}] - {span.reason}"
                )
                lines.append("    ```")
                lines.extend(f"    {line}" for line in span.text.splitlines())
                lines.append("    ```")
            lines.append("")
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
        if self.test_anchors:
            lines.append(
                "Existing test(s) matching this work order's acceptance criteria "
                "(a pointer, not a substitute for reading the file - open it if you "
                "need the surrounding code):"
            )
            for anchor in self.test_anchors:
                lines.append(
                    f"  - {anchor.path}::{anchor.qualified_name} "
                    f"#{anchor.start_line}-{anchor.end_line} - {anchor.reason}"
                )
                if anchor.excerpt:
                    lines.append("    ```")
                    lines.extend(f"    {line}" for line in anchor.excerpt.splitlines())
                    lines.append("    ```")
            lines.append("")
        text = "\n".join(lines)
        if len(text) > self.budget_chars:
            cut = max(self.budget_chars - len(TRUNCATION_MARKER), 0)
            return text[:cut] + TRUNCATION_MARKER
        return text

    def fingerprint(self) -> str:
        """Stable short digest of the semantic context actually handed to the session."""
        parts = [f"v={SEMANTIC_COMPILER_VERSION}"]
        for span in self.compiled_spans:
            parts.append(
                "|".join(
                    (
                        span.path,
                        span.qualified_name,
                        str(span.start_line),
                        str(span.end_line),
                        span.digest,
                    )
                )
            )
        parts.extend(f"ref:{item.kind}:{item.ref}:{item.span}" for item in self.context_refs)
        parts.extend(
            f"test:{item.path}:{item.qualified_name}:{item.start_line}:{item.end_line}"
            for item in self.test_anchors
        )
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiler_version": SEMANTIC_COMPILER_VERSION,
            "fingerprint": self.fingerprint(),
            "files": [f.to_dict() for f in self.files],
            "context_refs": [r.to_dict() for r in self.context_refs],
            "test_anchors": [a.to_dict() for a in self.test_anchors],
            "compiled_spans": [s.to_dict() for s in self.compiled_spans],
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
    test_anchors: Sequence[TestPatternAnchor] = (),
    compiled_spans: Sequence[CompiledSpan] = (),
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
        test_anchors=tuple(test_anchors),
        compiled_spans=tuple(compiled_spans),
        budget_chars=budget_chars,
    )
    truncated = len(bundle.render()) >= budget_chars
    return ExecutionContextBundle(
        files=bundle.files,
        context_refs=bundle.context_refs,
        test_anchors=bundle.test_anchors,
        compiled_spans=bundle.compiled_spans,
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


def _identifier_phrases(text: str) -> frozenset[str]:
    return frozenset(m.lower() for m in _IDENTIFIER_PHRASE_RE.findall(text))


def _meaningful_tokens(text: str) -> frozenset[str]:
    return frozenset(
        t.lower()
        for t in _WORD_RE.findall(text)
        if len(t) > 2 and t.lower() not in _STOP_TOKENS
    )


def _test_symbols(repo_map: RepoMap, path: str) -> tuple[SymbolSpan, ...]:
    module = repo_map.by_path(path)
    if module is None or not path.startswith("tests/"):
        return ()
    return tuple(s for s in module.symbols if s.kind == "function" and s.qualified_name.startswith("test_"))


def _focused_excerpt(
    repo_root: Path,
    path: str,
    symbol: SymbolSpan,
    *,
    phrase_targets: frozenset[str],
    token_targets: frozenset[str],
) -> tuple[str, int] | None:
    """Return a bounded window centered on the first strongest matching line."""
    try:
        text = (repo_root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    start = max(symbol.start_line - 1, 0)
    end = min(symbol.end_line, len(lines))
    body = lines[start:end]
    if not body:
        return None

    match_index = 0
    for index, line in enumerate(body):
        lowered = line.lower()
        if any(phrase in lowered for phrase in phrase_targets):
            match_index = index
            break
    else:
        for index, line in enumerate(body):
            if _meaningful_tokens(line) & token_targets:
                match_index = index
                break

    window_start = max(match_index - 4, 0)
    window_end = min(match_index + 7, len(body))
    excerpt = "\n".join(body[window_start:window_end])
    absolute_start = symbol.start_line + window_start
    return excerpt[:MAX_COMPILED_SINGLE_SPAN_CHARS], absolute_start


def rank_task_spans(
    repo_map: RepoMap | None,
    *,
    objective: str,
    acceptance_criteria: Sequence[str],
    paths: Sequence[str],
    repo_root: Path | None,
    limit: int = MAX_COMPILED_SPANS,
    max_total_chars: int = MAX_COMPILED_SPAN_CHARS,
) -> tuple[CompiledSpan, ...]:
    """Compile the most relevant exact source/test spans before a model starts.

    Selection is deterministic and local. Only paths explicitly supplied by
    the caller are eligible; callers build that list from immutable work-order
    write scope plus declared/effective tests, so this function has no authority
    of its own.
    """
    if repo_map is None or repo_root is None or limit < 1 or max_total_chars < 1:
        return ()

    criteria_text = " ".join((objective, *acceptance_criteria))
    phrase_targets = _identifier_phrases(criteria_text)
    token_targets = _meaningful_tokens(criteria_text)

    # File names are routing signals, not evidence that every symbol inside a
    # named file is relevant. Remove those self-referential terms from scoring.
    self_references: set[str] = set()
    clean_paths = tuple(dict.fromkeys(path for path in paths if path))
    for path in clean_paths:
        stem = Path(path).stem.lower()
        self_references.add(stem)
        self_references |= _meaningful_tokens(stem)
    phrase_targets = phrase_targets - self_references
    token_targets = token_targets - self_references
    if not phrase_targets and not token_targets:
        return ()

    path_rank = {path: index for index, path in enumerate(clean_paths)}
    scored: list[tuple[int, int, str, SymbolSpan, tuple[str, ...], tuple[str, ...], str]] = []
    for path in clean_paths:
        module = repo_map.by_path(path)
        if module is None:
            continue
        for symbol in module.symbols:
            body = _read_excerpt_full(repo_root, path, symbol)
            if body is None:
                continue
            symbol_text = symbol.qualified_name
            body_phrases = _identifier_phrases(body) | _identifier_phrases(symbol_text)
            phrase_hits = tuple(sorted(body_phrases & phrase_targets))
            token_hits_set = tuple(
                sorted(
                    (_meaningful_tokens(body) | _meaningful_tokens(symbol_text))
                    & token_targets
                )
            )
            score = 7 * len(phrase_hits) + len(token_hits_set)
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    path_rank[path],
                    path,
                    symbol,
                    phrase_hits,
                    token_hits_set,
                    body,
                )
            )

    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3].start_line))
    selected: list[CompiledSpan] = []
    used_chars = 0
    for _score, _rank, path, symbol, phrase_hits, token_hits, body in scored:
        if len(selected) >= limit or used_chars >= max_total_chars:
            break
        focused = _focused_excerpt(
            repo_root,
            path,
            symbol,
            phrase_targets=phrase_targets,
            token_targets=token_targets,
        )
        if focused is None:
            continue
        excerpt, excerpt_start = focused
        remaining = max_total_chars - used_chars
        if remaining <= 0:
            break
        excerpt = excerpt[:remaining]
        if not excerpt:
            continue
        if phrase_hits:
            reason = "work order names: " + ", ".join(phrase_hits[:3])
        else:
            reason = "work order overlaps: " + ", ".join(token_hits[:4])
        selected.append(
            CompiledSpan(
                path=path,
                qualified_name=symbol.qualified_name,
                start_line=excerpt_start,
                end_line=min(
                    symbol.end_line,
                    excerpt_start + max(excerpt.count("\n"), 0),
                ),
                reason=reason,
                text=excerpt,
                digest=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            )
        )
        used_chars += len(excerpt)
    return tuple(selected)


def rank_test_anchors(
    repo_map: RepoMap | None,
    *,
    objective: str,
    acceptance_criteria: Sequence[str],
    test_paths: Sequence[str],
    repo_root: Path | None = None,
    limit: int = MAX_TEST_ANCHORS,
    with_excerpt: bool = True,
) -> tuple[TestPatternAnchor, ...]:
    """Acceptance-criteria text -> the existing sibling test(s) it implies.

    Deterministic, symbol/token matching only - no LLM, no embeddings (see
    the milestone's section 3/6). Scoring favors an *exact identifier
    phrase* the criteria already spell out (`developer_attempts`,
    `reviews_completed`) appearing in a test's own body over generic token
    overlap, which is what keeps a fixture like `_config` or `_fake_repo`
    from outranking the actually-relevant sibling test just because every
    test in the file happens to call it too (`_STOP_TOKENS` also guards
    this). A criterion with no identifier phrase and no meaningful-token
    overlap in any candidate produces no anchor at all - this is a pointer
    to a match already found, never a manufactured one.
    """
    if repo_map is None or repo_root is None:
        return ()
    criteria_text = " ".join((objective, *acceptance_criteria))
    phrase_targets = _identifier_phrases(criteria_text)
    token_targets = _meaningful_tokens(criteria_text)
    # A criterion naming the test file itself ("a new test case in
    # tests/test_x.py exercises...") must not let every candidate in that
    # file score a free match on its own filename - a self-referential path
    # mention is not a signal about *which* test inside it matters.
    self_references: set[str] = set()
    for path in test_paths:
        if not path:
            continue
        stem = Path(path).stem.lower()
        self_references.add(stem)
        self_references |= _meaningful_tokens(stem)
    phrase_targets = phrase_targets - self_references
    token_targets = token_targets - self_references
    if not phrase_targets and not token_targets:
        return ()

    scored: list[tuple[int, int, str, SymbolSpan, tuple[str, ...]]] = []
    seen_paths: set[str] = set()
    for path in test_paths:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        for symbol in _test_symbols(repo_map, path):
            body = _read_excerpt_full(repo_root, path, symbol)
            if body is None:
                continue
            body_phrases = _identifier_phrases(body)
            phrase_hits = tuple(sorted(body_phrases & phrase_targets))
            token_hits = len(_meaningful_tokens(body) & token_targets)
            score = 5 * len(phrase_hits) + token_hits
            if score <= 0:
                continue
            scored.append((score, -symbol.start_line, path, symbol, phrase_hits))

    # Deterministic order: best score first, ties broken by path then line -
    # never by discovery order, which would depend on `test_paths`' own order.
    scored.sort(key=lambda item: (-item[0], item[2], item[3].start_line))

    anchors: list[TestPatternAnchor] = []
    for index, (score, _neg_line, path, symbol, phrase_hits) in enumerate(scored[:limit]):
        if phrase_hits:
            reason = "acceptance criteria names: " + ", ".join(phrase_hits)
        else:
            reason = "acceptance criteria's wording overlaps this test's body"
        excerpt = None
        if with_excerpt and index < MAX_TEST_ANCHOR_EXCERPTS:
            excerpt = _read_excerpt(repo_root, path, symbol)
        anchors.append(
            TestPatternAnchor(
                path=path,
                qualified_name=symbol.qualified_name,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                reason=reason,
                excerpt=excerpt,
            )
        )
    return tuple(anchors)


def _read_excerpt_full(repo_root: Path, path: str, symbol: SymbolSpan) -> str | None:
    """The whole symbol body, for scoring - unlike `_read_excerpt`, not capped
    to `MAX_EXCERPT_LINES`/`MAX_EXCERPT_CHARS`, because a match late in a long
    test function must still be found."""
    try:
        text = (repo_root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    end = min(symbol.end_line, len(lines))
    return "\n".join(lines[symbol.start_line - 1 : end])


__all__ = [
    "MAX_BUNDLE_CHARS",
    "MAX_EXCERPT_CHARS",
    "MAX_EXCERPT_LINES",
    "MAX_FILES_WITH_EXCERPTS",
    "MAX_SYMBOLS_PER_EXCERPT",
    "MAX_TEST_ANCHORS",
    "MAX_TEST_ANCHOR_EXCERPTS",
    "MAX_COMPILED_SPANS",
    "MAX_COMPILED_SPAN_CHARS",
    "SEMANTIC_COMPILER_VERSION",
    "CompiledSpan",
    "ContextPointer",
    "ExecutionContextBundle",
    "RelevantFile",
    "SourceExcerpt",
    "TestPatternAnchor",
    "build_execution_context",
    "rank_primary_files",
    "rank_task_spans",
    "rank_test_anchors",
]
