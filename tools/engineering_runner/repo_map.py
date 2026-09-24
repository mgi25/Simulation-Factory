"""A deterministic, cacheable map of the repository's own Python surface.

## Why this exists

Company OS measured a routine job that read 1,835,390 cache units to add two
fields to a dataclass, after the packet the company handed it had already been
narrowed to 3,661 characters. The remaining cost is what the session did
*after* the packet arrived: discovering, turn by turn, which files answer its
question. Repository Exploration Efficiency V1 shipped this map to answer
"which files matter here" before a session has to ask it turn by turn, and
also declared `company.efficiency.budget`'s `repo_file_reads` / `repo_searches`
dimensions UNAVAILABLE, because `backends.py` ran the coding CLI with
`--output-format json` - one final envelope, never a per-tool-call log. V2
changes that launch mode (see `exploration_telemetry.py`), so those two
dimensions are POST_SESSION_OBSERVABLE now; this module's job is unchanged.

What *can* be done outside the session is answer the question a grep loop is
usually asking - "which files matter here" - before the session has to ask it
turn by turn. This module builds that answer once, deterministically, from
the standard library `ast` module, and caches it. It is handed to a briefing
as a short, queried slice, never as a whole map: see `briefs.py` and
`execution_context.py`.

## V1 named two gaps; this closes them

1. A query answered "which module", never "which lines". A session still had
   to open the file and re-derive where the relevant class or function starts
   and ends. `ModuleMap.symbols` now carries a qualified name, a line span and
   a kind (`class` / `function` / `method`) for every top-level and
   class-level definition, from the same `ast` walk that already ran.
2. The map's own docstring claimed to help a session find "modules that
   already depend on authorized files", and nothing computed that - only the
   test reverse-index existed. `RepoMap.production_dependents` is the missing
   half: for a production module, which *other production modules* import it,
   resolved the same way the test index is (real imports, not filename
   guesses). `neighborhood()` bundles both indexes plus the module's own
   symbols and entry-point status into one bounded answer for one path.

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
import hashlib
import json
import os
import re
from collections import deque
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

# P4: cache parser/index products only when their source identity proves they
# belong to the exact repository content being mapped. Increment this if the
# serialized map semantics change in a way old entries cannot represent.
REPO_MAP_CACHE_VERSION = 4


@dataclass(frozen=True)
class RepoMapCacheEvidence:
    """Measured reuse from one deterministic repository-map build."""

    version: int
    tree_fingerprint: str
    roots: tuple[str, ...]
    module_count: int
    module_hits: int
    module_misses: int
    snapshot_hit: bool
    invalid_entries: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "tree_fingerprint": self.tree_fingerprint,
            "roots": list(self.roots),
            "module_count": self.module_count,
            "module_hits": self.module_hits,
            "module_misses": self.module_misses,
            "snapshot_hit": self.snapshot_hit,
            "invalid_entries": self.invalid_entries,
        }


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


@dataclass(frozen=True)
class SymbolSpan:
    """Where one class, function or method actually lives, in lines.

    `qualified_name` is `Class.method` for a method and the bare name
    otherwise, so a method and a same-named top-level function never collide
    in a rendered list. Lines are 1-indexed and inclusive, matching what a
    reader does with an editor rather than what `ast` calls them internally.
    """

    qualified_name: str
    kind: str  # "class" | "function" | "method"
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SymbolSpan":
        return cls(
            qualified_name=str(data.get("qualified_name", "")),
            kind=str(data.get("kind", "")),
            start_line=int(data.get("start_line", 0)),
            end_line=int(data.get("end_line", 0)),
        )


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
    symbols: tuple[SymbolSpan, ...] = ()
    # `from X import a` written as `X.a`, for the index builder to test against
    # the real module set. Not shown to a session: see `_imported_modules`.
    from_names: tuple[str, ...] = ()
    # Lines holding a dynamic import. Never an edge, always reported.
    dynamic_import_lines: tuple[int, ...] = ()

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
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "from_names": list(self.from_names),
            "dynamic_import_lines": list(self.dynamic_import_lines),
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
            symbols=tuple(SymbolSpan.from_dict(s) for s in data.get("symbols", ())),
            from_names=tuple(str(x) for x in data.get("from_names", ())),
            dynamic_import_lines=tuple(int(x) for x in data.get("dynamic_import_lines", ())),
        )

    def searchable_text(self) -> str:
        return " ".join(
            (self.path, self.owner, self.doc, " ".join(self.classes), " ".join(self.functions))
        )

    def symbol(self, qualified_name: str) -> "SymbolSpan | None":
        for symbol in self.symbols:
            if symbol.qualified_name == qualified_name:
                return symbol
        return None


@dataclass(frozen=True)
class RepoMap:
    """The whole map: one entry per module, plus the test reverse-index.

    Cacheable and compact on purpose - `to_json()` on this repository's own
    `company` + `tools` + `tests` trees is well under 400 KB, and nothing in
    this package ever hands the whole thing to a model session. See `query`.
    """

    modules: tuple[ModuleMap, ...]
    # The canonical direct edge map. `tests_by_module` and
    # `production_dependents` are views of it; the closures are computed from
    # it on demand rather than stored, because a serialized transitive closure
    # over 500 modules is larger than the map it came from and goes stale in
    # exactly the same way.
    imports_by_module: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    tests_by_module: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # Module path -> production modules that import it, resolved from real
    # imports the same way `tests_by_module` is. Named `production_dependents`
    # rather than `callers`: an import is a module-level dependency, not
    # necessarily a call, and the distinction matters to a session deciding
    # whether a change is safe to make silently.
    production_dependents: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    roots: tuple[str, ...] = DEFAULT_ROOTS

    def to_dict(self) -> dict[str, object]:
        return {
            "roots": list(self.roots),
            "modules": [m.to_dict() for m in self.modules],
            "imports_by_module": {
                k: list(v) for k, v in sorted(self.imports_by_module.items())
            },
            "tests_by_module": {k: list(v) for k, v in sorted(self.tests_by_module.items())},
            "production_dependents": {
                k: list(v) for k, v in sorted(self.production_dependents.items())
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "RepoMap":
        modules = tuple(ModuleMap.from_dict(m) for m in data.get("modules", ()))
        imports_by_module = {
            str(k): tuple(str(x) for x in v)
            for k, v in dict(data.get("imports_by_module", {})).items()
        }
        tests_by_module = {
            str(k): tuple(str(x) for x in v)
            for k, v in dict(data.get("tests_by_module", {})).items()
        }
        production_dependents = {
            str(k): tuple(str(x) for x in v)
            for k, v in dict(data.get("production_dependents", {})).items()
        }
        return cls(
            modules=modules,
            imports_by_module=imports_by_module,
            tests_by_module=tests_by_module,
            production_dependents=production_dependents,
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

    # -- the graph ---------------------------------------------------------

    def direct_dependencies(self, path: str) -> tuple[str, ...]:
        return self.imports_by_module.get(path, ())

    def transitive_dependencies(self, path: str) -> tuple[str, ...]:
        """Everything `path` reaches through imports, excluding itself."""
        return _closure(path, self.imports_by_module)

    def direct_dependents(self, path: str) -> tuple[str, ...]:
        """Everything that imports `path`, tests included."""
        return _reverse(self.imports_by_module).get(path, ())

    def transitive_dependents(self, path: str) -> tuple[str, ...]:
        return _closure(path, _reverse(self.imports_by_module))

    def tests_reaching(self, path: str, *, transitive: bool = True) -> tuple[str, ...]:
        """Test files whose imports statically reach `path`.

        Not "tests that cover `path`". Reaching a module means the suite loads
        it, which is necessary for testing it and nowhere near sufficient. The
        distinction is the whole reason this is safe to hand a session as
        localization and not as a coverage claim.
        """
        source = (
            self.transitive_dependents(path)
            if transitive
            else self.direct_dependents(path)
        )
        return tuple(sorted(item for item in source if _is_test_path(item)))

    def unresolved_imports(self) -> tuple[str, ...]:
        """Every dynamic import in the mapped tree, as `path:line`.

        Reported rather than resolved. A map that silently drops what it could
        not resolve looks exactly like a map with nothing to resolve.
        """
        return tuple(
            f"{module.path}:{line}"
            for module in self.modules
            for line in module.dynamic_import_lines
        )


def _dotted_module_name(rel_path: str) -> str:
    dotted = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    dotted = dotted.replace("/", ".")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    return dotted


def _package_parts(rel_path: str) -> tuple[str, ...]:
    """The package a file lives in, as dotted parts.

    `company/runtime/routing.py` and `company/runtime/__init__.py` both live in
    `company.runtime`: a package's `__init__` is inside the package, not beside
    it, so a `from . import x` in either resolves the same way.
    """
    parts = rel_path.split("/")
    return tuple(parts[:-1])


def _resolve_relative(level: int, module: str, package: tuple[str, ...]) -> str:
    """`from ..errors import X` in `a/b/c.py` -> `a.errors`, or "" if it escapes.

    A level deeper than the package nesting cannot be resolved against this
    repository at all; returning "" puts it in `unresolved` rather than
    inventing a name.
    """
    if level > len(package):
        return ""
    base = package[: len(package) - level + 1]
    parts = list(base) + ([module] if module else [])
    return ".".join(part for part in parts if part)


def _imported_modules(tree: ast.AST, package: tuple[str, ...]) -> tuple[set[str], set[str]]:
    """What this file imports: resolved module names, and `from X import a` candidates.

    Two sets, because they are two different degrees of certainty and the
    second must not be shown to a reader as if it were the first.

    `modules` holds dotted names that an import statement really named -
    `import a.b`, `from a.b import X`, and relative forms resolved against
    `package`. V1-V3 dropped every relative import (`node.level == 0` was the
    only branch that recorded anything), which is 965 imports in this
    repository and almost every internal edge in `company/`. That is the bug
    this signature exists to fix, and why the cache version moved to 4.

    `candidates` holds `X.a` for each `from X import a`. Whether that names a
    submodule or a class cannot be decided from one file - it depends on
    whether `X/a.py` exists - so the question is recorded here and answered by
    the index builder, which holds the whole module set. Keeping them out of
    `modules` is what stops `neighborhood()` telling a session that
    `company.integration.GateStatus` is a module it imports.
    """
    modules: set[str] = set()
    candidates: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = _resolve_relative(node.level, name, package)
            if not name:
                continue
            modules.add(name)
            for alias in node.names:
                if alias.name != "*":
                    candidates.add(f"{name}.{alias.name}")
    return modules, candidates


_DYNAMIC_IMPORT_CALLS = ("import_module", "__import__")


def _dynamic_import_lines(tree: ast.AST) -> tuple[int, ...]:
    """Lines holding a dynamic import, recorded as unresolvable rather than guessed.

    A literal argument would be resolvable most of the time. It is not
    resolved, because the one time the guess is wrong the map asserts an edge
    nobody wrote, and a map that is usually right is not something a gate or a
    briefing can rest on.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in _DYNAMIC_IMPORT_CALLS:
            lines.append(node.lineno)
    return tuple(sorted(set(lines)))


_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _symbol_spans(tree: ast.AST) -> tuple[SymbolSpan, ...]:
    """Every top-level class/function and every method, with its line span.

    Only one level of nesting is walked into (a class's direct methods) - a
    function nested inside another function is an implementation detail of
    its parent, not a symbol a session would ask for by name, and walking
    arbitrarily deep would make this unbounded per-file.
    """
    spans: list[SymbolSpan] = []
    body = getattr(tree, "body", ())
    for node in body:
        if isinstance(node, ast.ClassDef):
            spans.append(
                SymbolSpan(
                    qualified_name=node.name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                )
            )
            for member in node.body:
                if isinstance(member, _DEF_TYPES):
                    spans.append(
                        SymbolSpan(
                            qualified_name=f"{node.name}.{member.name}",
                            kind="method",
                            start_line=member.lineno,
                            end_line=getattr(member, "end_lineno", member.lineno),
                        )
                    )
        elif isinstance(node, _DEF_TYPES):
            spans.append(
                SymbolSpan(
                    qualified_name=node.name,
                    kind="function",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                )
            )
    spans.sort(key=lambda s: (s.start_line, s.qualified_name))
    return tuple(spans)


def _module_map_from_text(
    repo_root: Path, path: Path, owner_root: str, text: str
) -> ModuleMap:
    rel = path.relative_to(repo_root).as_posix()
    owner = "/".join(path.relative_to(repo_root).parts[:-1]) or owner_root
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return ModuleMap(path=rel, owner=owner, lines=text.count("\n") + 1)
    classes = tuple(sorted(n.name for n in tree.body if isinstance(n, ast.ClassDef)))
    functions = tuple(
        sorted(n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    )
    imported, candidates = _imported_modules(tree, _package_parts(rel))
    imports = tuple(sorted(imported))
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
        symbols=_symbol_spans(tree),
        from_names=tuple(sorted(candidates)),
        dynamic_import_lines=_dynamic_import_lines(tree),
    )


def _module_map(repo_root: Path, path: Path, owner_root: str) -> ModuleMap:
    return _module_map_from_text(
        repo_root,
        path,
        owner_root,
        path.read_text(encoding="utf-8", errors="replace"),
    )


def _assemble_repo_map(
    modules: Iterable[ModuleMap], roots: tuple[str, ...]
) -> RepoMap:
    modules_t = tuple(sorted(modules, key=lambda module: module.path))
    edges = _direct_edges(modules_t)
    return RepoMap(
        modules=modules_t,
        imports_by_module=edges,
        tests_by_module=_reverse_test_index(edges),
        production_dependents=_reverse_production_index(edges),
        roots=roots,
    )


def _module_cache_key(relative_path: str, raw: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(f"repo-map-v{REPO_MAP_CACHE_VERSION}\0".encode("utf-8"))
    digest.update(relative_path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(raw)
    return digest.hexdigest()


def _module_identity_key(relative_path: str, identity: str) -> str:
    """Versioned cache key from a trusted content identity such as a Git blob id."""
    digest = hashlib.sha256()
    digest.update(f"repo-map-v{REPO_MAP_CACHE_VERSION}\0identity\0".encode("utf-8"))
    digest.update(relative_path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(identity.encode("utf-8"))
    return digest.hexdigest()


def _tree_cache_key(
    roots: tuple[str, ...], entries: Iterable[tuple[str, str]]
) -> str:
    digest = hashlib.sha256()
    digest.update(f"repo-map-tree-v{REPO_MAP_CACHE_VERSION}\0".encode("utf-8"))
    for root in roots:
        digest.update(root.encode("utf-8"))
        digest.update(b"\0")
    for relative_path, module_key in entries:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(module_key.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_object(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache_object(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically publish one disposable runner-owned cache object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


# A walk that has expanded this many nodes without terminating has met
# something pathological. The map is ~520 modules; the bound exists so a
# bounded answer that says so beats an unbounded one that hangs a session.
MAX_CLOSURE_EXPANSIONS = 100_000


def _closure(start: str, adjacency: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Everything reachable from `start`, excluding `start`, cycle-safe.

    Breadth-first over a visited set, so the import cycles this repository
    really contains - a package `__init__` and the modules it re-exports -
    terminate instead of recursing.
    """
    seen: set[str] = set()
    queue: deque[str] = deque(adjacency.get(start, ()))
    expansions = 0
    while queue and expansions < MAX_CLOSURE_EXPANSIONS:
        current = queue.popleft()
        expansions += 1
        if current in seen or current == start:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, ()))
    return tuple(sorted(seen))


def _direct_edges(modules: tuple[ModuleMap, ...]) -> dict[str, tuple[str, ...]]:
    """importer path -> the repository paths its own import statements reach.

    One graph, from which the test index and the production index are both
    *views*. V1-V3 computed two reverse indexes independently over the same
    resolution rule; they could not disagree in principle, but nothing said so,
    and a third question would have meant a third walk. The edge map is the
    single answer, and `tests_by_module` and `production_dependents` are two
    filters over its reverse.

    Three things make an edge, all of them things Python does at import time:

    * the dotted name an import statement resolved to, exactly;
    * every package above it, because importing `a.b.c` runs `a/__init__.py`
      and `a/b/__init__.py`;
    * `X.a` from `from X import a`, when a module of that name exists. This is
      the case a package-facade import falls into - a test naming the package
      and the module it wants in one statement - and without it such an import
      credits only the package. It is the dominant pattern in the control
      plane's own tests, and missing it is what made most of them look as
      though they depended on nothing.

    The control-plane package names are deliberately not spelled out above.
    A capsule-layer guard greps every module under this root for them, and a
    docstring quoting the roots this package must not import reads to that
    guard exactly like a module that imports them. `tools/youtube_fetch`
    states the same rule for the same reason.

    Not a filename heuristic. `test_foo.py` has no relationship to `foo.py`
    here unless an import statement creates one.
    """
    dotted_to_path = {_dotted_module_name(m.path): m.path for m in modules}
    edges: dict[str, set[str]] = {}
    for module in modules:
        found: set[str] = set()
        for imported in module.imports:
            if imported in dotted_to_path:
                found.add(dotted_to_path[imported])
            parts = imported.split(".")
            for i in range(1, len(parts)):
                ancestor = ".".join(parts[:i])
                if ancestor in dotted_to_path:
                    found.add(dotted_to_path[ancestor])
        for candidate in module.from_names:
            if candidate in dotted_to_path:
                found.add(dotted_to_path[candidate])
        found.discard(module.path)
        if found:
            edges[module.path] = tuple(sorted(found))
    return dict(sorted(edges.items()))


def _reverse(edges: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    reverse: dict[str, set[str]] = {}
    for importer, imported in edges.items():
        for target in imported:
            reverse.setdefault(target, set()).add(importer)
    return {k: tuple(sorted(v)) for k, v in sorted(reverse.items())}


def _is_test_path(path: str) -> bool:
    return path.startswith("tests/")


def _reverse_test_index(
    edges: Mapping[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Module path -> the test files that import it. A view of `_direct_edges`."""
    reverse = _reverse(edges)
    out = {
        path: tuple(t for t in importers if _is_test_path(t))
        for path, importers in reverse.items()
        if not _is_test_path(path)
    }
    return {path: tests for path, tests in out.items() if tests}


def _reverse_production_index(
    edges: Mapping[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Module path -> other production modules that import it. A view of the same.

    Named `production_dependents` rather than `callers`: an import is a
    module-level dependency, not necessarily a call, and the distinction
    matters to a session deciding whether a change is safe to make silently.
    """
    reverse = _reverse(edges)
    out = {
        path: tuple(d for d in importers if not _is_test_path(d))
        for path, importers in reverse.items()
        if not _is_test_path(path)
    }
    return {path: dependents for path, dependents in out.items() if dependents}


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
    return _assemble_repo_map(modules, roots)


def build_repo_map_cached(
    repo_root: Path,
    cache_root: Path,
    *,
    roots: Iterable[str] = DEFAULT_ROOTS,
    content_identities: Mapping[str, str] | None = None,
) -> tuple[RepoMap, RepoMapCacheEvidence]:
    """Build the map from exact content identities, reusing safe snapshots.

    P4C accepts an optional trusted path -> content identity mapping. The
    runner supplies Git blob ids only for a clean worktree. In that mode the
    cache can determine unchanged modules without reopening their source files.
    With no identity mapping, the P4B filesystem-content path remains intact.

    The cache keeps two deterministic records under runner-owned state:

    * an exact-tree snapshot keyed by the complete scoped tree fingerprint;
    * a tiny `latest.json` manifest that points at the previous snapshot and
      records each path's exact content key.

    An unchanged tree loads its exact snapshot. A changed tree loads at most
    one previous snapshot and reuses only ModuleMaps whose path *and* exact
    content key still match. Changed/new modules are parsed again and reverse
    indexes are rebuilt deterministically.

    The cache is advisory. Missing/corrupt records are misses, never authority,
    and nothing stale is accepted merely because a cache file exists.
    """
    repo_root = Path(repo_root)
    cache_root = Path(cache_root)
    roots_t = tuple(roots)

    entries: list[tuple[Path, str, str, bytes | None, str]] = []

    if content_identities is not None:
        for relative, identity in sorted(
            (str(path).replace("\\", "/"), str(value))
            for path, value in content_identities.items()
        ):
            if not relative.endswith(".py"):
                continue
            owner_root = next(
                (
                    root
                    for root in roots_t
                    if relative == root or relative.startswith(root + "/")
                ),
                "",
            )
            if not owner_root:
                continue
            source = repo_root / relative
            entries.append(
                (
                    source,
                    owner_root,
                    relative,
                    None,
                    _module_identity_key(relative, identity),
                )
            )
    else:
        for root_name in roots_t:
            base = repo_root / root_name
            if not base.is_dir():
                continue
            for source in sorted(base.rglob("*.py")):
                if _EXCLUDED_PARTS & set(source.parts):
                    continue
                relative = source.relative_to(repo_root).as_posix()
                raw = source.read_bytes()
                entries.append(
                    (
                        source,
                        root_name,
                        relative,
                        raw,
                        _module_cache_key(relative, raw),
                    )
                )

    current_keys = {
        relative: module_key
        for _source, _root, relative, _raw, module_key in entries
    }
    expected_paths = tuple(sorted(current_keys))
    tree_fingerprint = _tree_cache_key(
        roots_t,
        ((relative, current_keys[relative]) for relative in expected_paths),
    )
    snapshot_path = cache_root / "snapshots" / f"{tree_fingerprint}.json"
    latest_path = cache_root / "latest.json"
    invalid_entries = 0

    if snapshot_path.is_file():
        snapshot = _cache_object(snapshot_path)
        if (
            snapshot is not None
            and snapshot.get("version") == REPO_MAP_CACHE_VERSION
            and snapshot.get("tree_fingerprint") == tree_fingerprint
            and tuple(str(item) for item in snapshot.get("roots", ())) == roots_t
            and isinstance(snapshot.get("repo_map"), Mapping)
        ):
            try:
                repo_map = RepoMap.from_dict(snapshot["repo_map"])
            except (TypeError, ValueError):
                repo_map = None
            if (
                repo_map is not None
                and tuple(module.path for module in repo_map.modules) == expected_paths
            ):
                _write_cache_object(
                    latest_path,
                    {
                        "version": REPO_MAP_CACHE_VERSION,
                        "tree_fingerprint": tree_fingerprint,
                        "roots": list(roots_t),
                        "module_keys": current_keys,
                    },
                )
                return repo_map, RepoMapCacheEvidence(
                    version=REPO_MAP_CACHE_VERSION,
                    tree_fingerprint=tree_fingerprint[:16],
                    roots=roots_t,
                    module_count=len(entries),
                    module_hits=len(entries),
                    module_misses=0,
                    snapshot_hit=True,
                    invalid_entries=0,
                )
        invalid_entries += 1

    previous_keys: dict[str, str] = {}
    previous_modules: dict[str, ModuleMap] = {}

    if latest_path.is_file():
        latest = _cache_object(latest_path)
        latest_fingerprint = ""
        if (
            latest is not None
            and latest.get("version") == REPO_MAP_CACHE_VERSION
            and tuple(str(item) for item in latest.get("roots", ())) == roots_t
            and isinstance(latest.get("module_keys"), Mapping)
        ):
            latest_fingerprint = str(latest.get("tree_fingerprint", ""))
            previous_keys = {
                str(path): str(key)
                for path, key in dict(latest["module_keys"]).items()
            }

        previous_snapshot_path = (
            cache_root / "snapshots" / f"{latest_fingerprint}.json"
            if latest_fingerprint
            else None
        )
        previous_snapshot = (
            _cache_object(previous_snapshot_path)
            if previous_snapshot_path is not None
            and previous_snapshot_path.is_file()
            else None
        )
        if (
            previous_snapshot is not None
            and previous_snapshot.get("version") == REPO_MAP_CACHE_VERSION
            and previous_snapshot.get("tree_fingerprint") == latest_fingerprint
            and tuple(str(item) for item in previous_snapshot.get("roots", ())) == roots_t
            and isinstance(previous_snapshot.get("repo_map"), Mapping)
        ):
            try:
                previous_map = RepoMap.from_dict(previous_snapshot["repo_map"])
            except (TypeError, ValueError):
                previous_map = None
            if previous_map is not None:
                previous_modules = {
                    module.path: module for module in previous_map.modules
                }
            else:
                previous_keys = {}
                invalid_entries += 1
        else:
            previous_keys = {}
            invalid_entries += 1

    modules: list[ModuleMap] = []
    module_hits = 0
    module_misses = 0
    for source, owner_root, relative, raw, module_key in entries:
        module = None
        if previous_keys.get(relative) == module_key:
            candidate = previous_modules.get(relative)
            if candidate is not None and candidate.path == relative:
                module = candidate

        if module is None:
            if raw is None:
                raw = source.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            module = _module_map_from_text(repo_root, source, owner_root, text)
            module_misses += 1
        else:
            module_hits += 1
        modules.append(module)

    repo_map = _assemble_repo_map(modules, roots_t)
    _write_cache_object(
        snapshot_path,
        {
            "version": REPO_MAP_CACHE_VERSION,
            "tree_fingerprint": tree_fingerprint,
            "roots": list(roots_t),
            "repo_map": repo_map.to_dict(),
        },
    )
    _write_cache_object(
        latest_path,
        {
            "version": REPO_MAP_CACHE_VERSION,
            "tree_fingerprint": tree_fingerprint,
            "roots": list(roots_t),
            "module_keys": current_keys,
        },
    )
    return repo_map, RepoMapCacheEvidence(
        version=REPO_MAP_CACHE_VERSION,
        tree_fingerprint=tree_fingerprint[:16],
        roots=roots_t,
        module_count=len(entries),
        module_hits=module_hits,
        module_misses=module_misses,
        snapshot_hit=False,
        invalid_entries=invalid_entries,
    )


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


@dataclass(frozen=True)
class Neighborhood:
    """One authorized file's bounded surroundings: symbols, callers, tests.

    Every list here is a direct lookup against an index `build_repo_map`
    already built - no traversal, no recursion, no walk of a caller's own
    callers. That is what "cheap" and "bounded" mean for this milestone: the
    cost is paid once, at map-build time, and a query against it is a dict
    lookup plus a slice.
    """

    path: str
    found: bool
    symbols: tuple[SymbolSpan, ...] = ()
    imports: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    # Tests that reach this file only through another module. Kept apart from
    # `tests` because the two are different strengths of evidence and a
    # session choosing what to run should be able to tell them apart.
    transitive_tests: tuple[str, ...] = ()
    considered: int = 0
    truncated: tuple[str, ...] = ()

    def returned(self) -> int:
        return (
            len(self.symbols)
            + len(self.imports)
            + len(self.dependents)
            + len(self.tests)
            + len(self.transitive_tests)
            + len(self.entry_points)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "found": self.found,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": list(self.imports),
            "dependents": list(self.dependents),
            "tests": list(self.tests),
            "entry_points": list(self.entry_points),
            "transitive_tests": list(self.transitive_tests),
            "considered": self.considered,
            "truncated": list(self.truncated),
        }


def neighborhood(
    repo_map: RepoMap,
    path: str,
    *,
    symbol_limit: int = 20,
    dependent_limit: int = 8,
    test_limit: int = 5,
    import_limit: int = 15,
) -> Neighborhood:
    """One authorized production file's symbols, dependents, tests - bounded.

    `entry_points` is the subset of `dependents` that are themselves flagged
    `is_entry_point` - the modules a session would need to know about to
    understand how this file is actually reached, not every entry point in
    the repository.
    """
    module = repo_map.by_path(path)
    if module is None:
        return Neighborhood(path=path, found=False, considered=len(repo_map.modules))
    dependents = repo_map.production_dependents.get(path, ())
    entry_points = tuple(
        p for p in dependents if (m := repo_map.by_path(p)) is not None and m.is_entry_point
    )
    direct_tests = repo_map.tests_by_module.get(path, ())
    indirect = tuple(
        t for t in repo_map.tests_reaching(path, transitive=True) if t not in set(direct_tests)
    )
    sized = (
        ("symbols", module.symbols, symbol_limit),
        ("imports", module.imports, import_limit),
        ("dependents", dependents, dependent_limit),
        ("tests", direct_tests, test_limit),
        ("transitive_tests", indirect, test_limit),
    )
    return Neighborhood(
        path=path,
        found=True,
        symbols=module.symbols[:symbol_limit],
        imports=module.imports[:import_limit],
        dependents=dependents[:dependent_limit],
        tests=direct_tests[:test_limit],
        entry_points=entry_points[:dependent_limit],
        transitive_tests=indirect[:test_limit],
        considered=len(repo_map.modules),
        # A truncated answer that does not say it is truncated is a wrong
        # answer: a session told "these are the tests" will not run the others.
        truncated=tuple(
            sorted(name for name, values, limit in sized if len(values) > limit)
        ),
    )


@dataclass(frozen=True)
class ChangeImpact:
    """What one attempt's changed paths reach, bounded and deterministic.

    Repository intelligence, and nothing more. This may recommend what to read
    and what to run; it may not decide what is allowed. Nothing here widens an
    authorized path set, relaxes a read ceiling, or excuses a required suite -
    `authorization.py` owns all three and does not consult this type. A
    reviewer handed an impact slice still reviews under the same envelope.

    Every list is capped and `truncated` names the ones that hit the cap,
    because a session told "these are the tests" will not run the others.
    """

    changed: tuple[str, ...] = ()
    unmapped: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    direct_tests: tuple[str, ...] = ()
    transitive_tests: tuple[str, ...] = ()
    considered: int = 0
    truncated: tuple[str, ...] = ()

    def returned(self) -> int:
        return (
            len(self.dependents) + len(self.direct_tests) + len(self.transitive_tests)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "changed": list(self.changed),
            "unmapped": list(self.unmapped),
            "dependents": list(self.dependents),
            "direct_tests": list(self.direct_tests),
            "transitive_tests": list(self.transitive_tests),
            "considered": self.considered,
            "truncated": list(self.truncated),
        }


def change_impact(
    repo_map: RepoMap,
    changed_paths: Iterable[str],
    *,
    dependent_limit: int = 12,
    test_limit: int = 12,
) -> ChangeImpact:
    """Blast radius for a set of changed paths: dependents, tests, both degrees.

    The runner already knows its real change set - `workspace.changed_paths()`
    runs `git diff --name-status` and the result reaches the receipt as
    `files_changed`. Until P6B nothing joined that to the map, so a reviewer
    was told which files changed and left to work out what else touches them.

    `unmapped` is not padding. A changed path outside the mapped roots - a
    YAML file, a document, a simulation module - has no import answer, and
    saying so is different from returning an empty list that reads as "nothing
    depends on this".
    """
    changed = tuple(sorted({str(path).replace("\\", "/") for path in changed_paths if str(path).strip()}))
    known = [path for path in changed if repo_map.by_path(path) is not None]
    unmapped = tuple(path for path in changed if path not in set(known))

    dependents: set[str] = set()
    direct: set[str] = set()
    indirect: set[str] = set()
    for path in known:
        dependents.update(repo_map.production_dependents.get(path, ()))
        direct.update(repo_map.tests_by_module.get(path, ()))
        indirect.update(repo_map.tests_reaching(path, transitive=True))
    dependents.difference_update(changed)
    indirect.difference_update(direct)

    ordered = (
        ("dependents", tuple(sorted(dependents)), dependent_limit),
        ("direct_tests", tuple(sorted(direct)), test_limit),
        ("transitive_tests", tuple(sorted(indirect)), test_limit),
    )
    return ChangeImpact(
        changed=changed,
        unmapped=unmapped,
        dependents=ordered[0][1][:dependent_limit],
        direct_tests=ordered[1][1][:test_limit],
        transitive_tests=ordered[2][1][:test_limit],
        considered=len(repo_map.modules),
        truncated=tuple(
            sorted(name for name, values, limit in ordered if len(values) > limit)
        ),
    )


# The serialized shape of a dependency manifest. Increment when the meaning of
# a field changes in a way an older reader would get wrong.
DEPENDENCY_MANIFEST_SCHEMA = "engineering-runner/dependency-manifest"
DEPENDENCY_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class DependencyManifest:
    """The graph as a file, with enough identity to refuse it when it is stale.

    A manifest exists because the map is *cached*: the expensive part is the
    parse, and a session that reuses yesterday's parse against today's tree
    gets answers about code that is no longer there. Every field below exists
    to make that detectable rather than silent.

    * `schema` and `version` - an older reader must refuse a newer shape
      rather than read fields it thinks it understands.
    * `tree_fingerprint` - the identity of the exact content that was parsed.
      `matches()` compares it, and a mismatch is a refusal, never a warning.
    * `roots` - the same tree parsed over different roots is a different
      manifest, and a narrower one would answer "no dependents" truthfully and
      uselessly.
    * `digest` - the identity of the graph itself, so two manifests can be
      compared without diffing them.
    * `unresolved` - the dynamic imports that are in the tree and not in the
      graph. A manifest that dropped them would look complete.
    """

    schema: str
    version: int
    tree_fingerprint: str
    roots: tuple[str, ...]
    edges: Mapping[str, tuple[str, ...]]
    unresolved: tuple[str, ...]
    module_count: int

    @classmethod
    def of(cls, repo_map: RepoMap, *, tree_fingerprint: str) -> "DependencyManifest":
        return cls(
            schema=DEPENDENCY_MANIFEST_SCHEMA,
            version=DEPENDENCY_MANIFEST_VERSION,
            tree_fingerprint=tree_fingerprint,
            roots=tuple(repo_map.roots),
            edges={k: tuple(v) for k, v in sorted(repo_map.imports_by_module.items())},
            unresolved=repo_map.unresolved_imports(),
            module_count=len(repo_map.modules),
        )

    def digest(self) -> str:
        """Content identity of the graph, independent of how it was produced."""
        payload = json.dumps(
            {
                "schema": self.schema,
                "version": self.version,
                "roots": list(self.roots),
                "edges": {k: list(v) for k, v in sorted(self.edges.items())},
                "unresolved": list(self.unresolved),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "tree_fingerprint": self.tree_fingerprint,
            "roots": list(self.roots),
            "edges": {k: list(v) for k, v in sorted(self.edges.items())},
            "unresolved": list(self.unresolved),
            "module_count": self.module_count,
            "digest": self.digest(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "DependencyManifest":
        return cls(
            schema=str(data.get("schema", "")),
            version=int(data.get("version", 0)),
            tree_fingerprint=str(data.get("tree_fingerprint", "")),
            roots=tuple(str(r) for r in data.get("roots", ())),
            edges={
                str(k): tuple(str(x) for x in v)
                for k, v in dict(data.get("edges", {})).items()
            },
            unresolved=tuple(str(x) for x in data.get("unresolved", ())),
            module_count=int(data.get("module_count", 0)),
        )

    def matches(self, *, tree_fingerprint: str, roots: Iterable[str]) -> bool:
        """True only for the exact tree and roots this manifest was built from.

        Fail-closed on every axis at once: a wrong schema, a newer version, a
        different tree or a different root set all return False, because there
        is no partial way to be the right manifest.
        """
        return (
            self.schema == DEPENDENCY_MANIFEST_SCHEMA
            and self.version == DEPENDENCY_MANIFEST_VERSION
            and bool(self.tree_fingerprint)
            and self.tree_fingerprint == tree_fingerprint
            and self.roots == tuple(roots)
        )


def load_dependency_manifest(
    path: Path, *, tree_fingerprint: str, roots: Iterable[str]
) -> DependencyManifest | None:
    """Read a manifest and return it only if it describes this exact tree.

    `None` for missing, unreadable, malformed *and* stale. The caller rebuilds;
    it never gets a manifest it has to decide whether to trust.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    manifest = DependencyManifest.from_dict(data)
    if not manifest.matches(tree_fingerprint=tree_fingerprint, roots=roots):
        return None
    return manifest


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
    "DEPENDENCY_MANIFEST_SCHEMA",
    "DEPENDENCY_MANIFEST_VERSION",
    "MAX_CLOSURE_EXPANSIONS",
    "REPO_MAP_CACHE_VERSION",
    "ChangeImpact",
    "DependencyManifest",
    "ModuleMap",
    "Neighborhood",
    "QueryHit",
    "RepoMap",
    "RepoMapCacheEvidence",
    "SymbolSpan",
    "build_and_cache",
    "build_repo_map",
    "change_impact",
    "build_repo_map_cached",
    "load_dependency_manifest",
    "load_or_build",
    "neighborhood",
    "query",
]
