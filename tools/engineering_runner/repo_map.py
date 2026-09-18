"""A deterministic, cacheable map of the repository's own Python surface.

## Why this exists

Company OS measured a routine job that read 1,835,390 cache units to add two
fields to a dataclass, after the packet the company handed it had already been
narrowed to 3,661 characters. The remaining cost is what the session did
*after* the packet arrived: discovering, turn by turn, which files answer its
question. `tools/engineering_runner/backends.py` runs the coding CLI with
`--output-format json`, so none of that discovery is ever visible to Company
OS - see `company.efficiency.budget`'s `repo_file_reads` / `repo_searches`
dimensions, declared UNAVAILABLE for exactly this reason.

What *can* be done outside the session is answer the question a grep loop is
usually asking - "which files matter here" - before the session has to ask it
turn by turn. This module builds that answer once, deterministically, from
the standard library `ast` module, and caches it. It is handed to a briefing
as a short, queried slice, never as a whole map: see `briefs.py`.

## Why not an external tool

`ast-grep` was evaluated and rejected for this milestone. This repository is
593 Python files against 76 GDScript files - the Python side is what a
routine Company OS job actually touches - and a full-repository `ast` parse
of every `.py` file here completes in about two seconds and needs nothing
`requirements.txt` does not already have. `ast-grep` was not even reachable
without a fresh install in this environment. Structural, multi-language
search earns its cost when a codebase needs it; this one, for this job,
does not. See `docs/company_os_v1_repository_exploration_efficiency.md`.

## What this deliberately is not

It is not a second capsule registry and it does not claim to be one. The
`owner` field is a directory prefix, not `company.runtime`'s capsule id -
this package may not import the capsule layer at all (the architecture gate
that proves it: `architecture.production_does_not_import_company_os`), so a
cheap, filesystem-only proxy is what is available here, and it is named as a
proxy rather than dressed up as the real thing.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

# The directories a routine Company OS job's own code lives under. Anything
# else in this repository - the marble-race simulation, its rendered output,
# its Godot project files - is out of scope for the engineering runner this
# map serves, and including it would make the cache bigger for no queries
# this package ever issues.
DEFAULT_ROOTS: tuple[str, ...] = (
    "company",
    "tools",
    "tests",
)

_EXCLUDED_PARTS = frozenset({".git", "__pycache__", ".venv", "venv", "node_modules"})

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


@dataclass(frozen=True)
class ModuleMap:
    """One Python file's deterministic surface: no source, only its shape."""

    path: str
    owner: str
    classes: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    doc: str = ""
    lines: int = 0
    is_entry_point: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "owner": self.owner,
            "classes": list(self.classes),
            "functions": list(self.functions),
            "imports": list(self.imports),
            "doc": self.doc,
            "lines": self.lines,
            "is_entry_point": self.is_entry_point,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ModuleMap":
        return cls(
            path=str(data.get("path", "")),
            owner=str(data.get("owner", "")),
            classes=tuple(str(x) for x in data.get("classes", ())),
            functions=tuple(str(x) for x in data.get("functions", ())),
            imports=tuple(str(x) for x in data.get("imports", ())),
            doc=str(data.get("doc", "")),
            lines=int(data.get("lines", 0)),
            is_entry_point=bool(data.get("is_entry_point", False)),
        )

    def searchable_text(self) -> str:
        return " ".join(
            (self.path, self.owner, self.doc, " ".join(self.classes), " ".join(self.functions))
        )


@dataclass(frozen=True)
class RepoMap:
    """The whole map: one entry per module, plus the test reverse-index.

    Cacheable and compact on purpose - `to_json()` on this repository's own
    `company` + `tools` + `tests` trees is well under 400 KB, and nothing in
    this package ever hands the whole thing to a model session. See `query`.
    """

    modules: tuple[ModuleMap, ...]
    tests_by_module: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    roots: tuple[str, ...] = DEFAULT_ROOTS

    def to_dict(self) -> dict[str, object]:
        return {
            "roots": list(self.roots),
            "modules": [m.to_dict() for m in self.modules],
            "tests_by_module": {k: list(v) for k, v in sorted(self.tests_by_module.items())},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "RepoMap":
        modules = tuple(ModuleMap.from_dict(m) for m in data.get("modules", ()))
        tests_by_module = {
            str(k): tuple(str(x) for x in v)
            for k, v in dict(data.get("tests_by_module", {})).items()
        }
        return cls(
            modules=modules,
            tests_by_module=tests_by_module,
            roots=tuple(str(r) for r in data.get("roots", DEFAULT_ROOTS)),
        )

    @classmethod
    def from_json(cls, text: str) -> "RepoMap":
        return cls.from_dict(json.loads(text))

    def size_chars(self) -> int:
        return len(self.to_json())

    def by_path(self, path: str) -> ModuleMap | None:
        for module in self.modules:
            if module.path == path:
                return module
        return None


def _dotted_module_name(rel_path: str) -> str:
    dotted = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    dotted = dotted.replace("/", ".")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    return dotted


def _imported_modules(tree: ast.AST) -> set[str]:
    """Every dotted module name this file imports, at whatever depth it named."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module)
    return found


def _module_map(repo_root: Path, path: Path, owner_root: str) -> ModuleMap:
    rel = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    owner = "/".join(path.relative_to(repo_root).parts[:-1]) or owner_root
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return ModuleMap(path=rel, owner=owner, lines=text.count("\n") + 1)
    classes = tuple(sorted(n.name for n in tree.body if isinstance(n, ast.ClassDef)))
    functions = tuple(
        sorted(n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    )
    imports = tuple(sorted(_imported_modules(tree)))
    docstring = ast.get_docstring(tree) or ""
    doc_line = docstring.strip().splitlines()[0] if docstring.strip() else ""
    entry_point = path.name == "__main__.py" or "main" in functions
    return ModuleMap(
        path=rel,
        owner=owner,
        classes=classes,
        functions=functions,
        imports=imports,
        doc=doc_line,
        lines=text.count("\n") + 1,
        is_entry_point=entry_point,
    )


def _reverse_test_index(
    modules: tuple[ModuleMap, ...],
) -> dict[str, tuple[str, ...]]:
    """Module path -> the test files that import it, resolved from real imports.

    Deliberately not a filename heuristic (`test_foo.py` "belongs to" `foo.py`)
    - that guesses, and guesses wrong for a shared module tested from several
    files or a test file that covers more than its name says. This instead
    asks each test file what it actually imports and matches by dotted module
    name, exact or via a package prefix.
    """
    production = [m for m in modules if not m.path.startswith("tests/")]
    dotted_to_path = {_dotted_module_name(m.path): m.path for m in production}
    index: dict[str, set[str]] = {path: set() for path in dotted_to_path.values()}
    for test in modules:
        if not test.path.startswith("tests/"):
            continue
        for imported in test.imports:
            for dotted, path in dotted_to_path.items():
                if imported == dotted or imported.startswith(dotted + "."):
                    index[path].add(test.path)
    return {path: tuple(sorted(tests)) for path, tests in index.items() if tests}


def build_repo_map(repo_root: Path, *, roots: Iterable[str] = DEFAULT_ROOTS) -> RepoMap:
    """Walk `roots` under `repo_root` and parse every `.py` file with `ast`.

    Deterministic: the same tree produces the same map, byte for byte, because
    nothing here depends on file-system iteration order (`rglob` results are
    sorted) or on wall-clock time.
    """
    roots = tuple(roots)
    modules: list[ModuleMap] = []
    for root_name in roots:
        base = repo_root / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if _EXCLUDED_PARTS & set(path.parts):
                continue
            modules.append(_module_map(repo_root, path, root_name))
    modules.sort(key=lambda m: m.path)
    tests_index = _reverse_test_index(tuple(modules))
    return RepoMap(modules=tuple(modules), tests_by_module=tests_index, roots=roots)


@dataclass(frozen=True)
class QueryHit:
    path: str
    owner: str
    score: int
    matched_symbols: tuple[str, ...]
    tests: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "owner": self.owner,
            "score": self.score,
            "matched_symbols": list(self.matched_symbols),
            "tests": list(self.tests),
        }


def query(repo_map: RepoMap, text: str, *, limit: int = 5) -> tuple[QueryHit, ...]:
    """Rank modules against free text, deterministically and without a model.

    Scoring is a fixed, explainable rule, not a learned ranking: a token
    matching the path counts most, a token matching a symbol name counts
    less, and a token matching only the docstring's first line counts least.
    Ties break on path, so the result is the same every time for the same
    map and the same query. This is the "2-5 likely files" half of the
    milestone's brief; `briefs.py` calls it and injects only the hits, never
    the map.
    """
    tokens = set(_tokenize(text))
    if not tokens:
        return ()
    hits: list[QueryHit] = []
    for module in repo_map.modules:
        path_tokens = set(_tokenize(module.path))
        symbol_tokens = set(_tokenize(" ".join(module.classes) + " " + " ".join(module.functions)))
        doc_tokens = set(_tokenize(module.doc))
        matched_symbols = tuple(
            sorted(
                name
                for name in (*module.classes, *module.functions)
                if set(_tokenize(name)) & tokens
            )
        )
        score = (
            3 * len(tokens & path_tokens)
            + 2 * len(tokens & symbol_tokens)
            + 1 * len(tokens & doc_tokens)
        )
        if score <= 0:
            continue
        hits.append(
            QueryHit(
                path=module.path,
                owner=module.owner,
                score=score,
                matched_symbols=matched_symbols,
                tests=repo_map.tests_by_module.get(module.path, ()),
            )
        )
    hits.sort(key=lambda h: (-h.score, h.path))
    return tuple(hits[:limit])


def build_and_cache(repo_root: Path, cache_path: Path, *, roots: Iterable[str] = DEFAULT_ROOTS) -> RepoMap:
    repo_map = build_repo_map(repo_root, roots=roots)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(repo_map.to_json(), encoding="utf-8")
    return repo_map


def load_or_build(repo_root: Path, cache_path: Path, *, roots: Iterable[str] = DEFAULT_ROOTS) -> RepoMap:
    """Read the cache if it parses; rebuild and rewrite it if it does not.

    A stale-but-present cache is still cheaper to query than a fresh build on
    every session, and a missing or corrupt one costs one rebuild rather than
    a refusal.
    """
    if cache_path.is_file():
        try:
            return RepoMap.from_json(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return build_and_cache(repo_root, cache_path, roots=roots)


__all__ = [
    "DEFAULT_ROOTS",
    "ModuleMap",
    "QueryHit",
    "RepoMap",
    "build_and_cache",
    "build_repo_map",
    "load_or_build",
    "query",
]
