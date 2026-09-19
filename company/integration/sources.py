"""Which directories are production, which are Company OS, and how they are read.

## Why the roots are declared and then filtered

`DECLARED_PRODUCTION_ROOTS` names every production tree this repository has
been observed to contain, plus the ones the integration brief names. It is a
declaration, not a measurement, so `production_roots()` intersects it with the
checkout and `absent_production_roots()` reports the difference. A root the
brief names and the repository does not have (`race2/`, at the time of
writing) is reported as absent rather than invented as a pass or silently
dropped: the gate says what it looked at.

## Why the scan is an AST walk and not a grep

Three of the production-boundary conditions are about what code *does*: does it
import the control plane, can it reach the network, does it write into the
simulation tree. A regular expression over source text answers none of those
honestly - it matches the word `subprocess` in this docstring, and it misses
`from . import x` resolved against a package. `ast.parse` gives exact module
names, exact call targets and exact line numbers, which is what a finding needs
in order to be actionable and what a false positive costs the most.

Nothing here executes the modules it reads. Importing a production module to
inspect it would need pygame and pymunk, and a gate that needs the production
dependencies installed is a gate that cannot run.

## Why `__pycache__`, outputs and binaries are skipped

Section 5 of the brief: scope to source roots. `iter_python_files` walks
`*.py` only and prunes the directories that hold generated output, so a render
tree full of PNGs costs nothing.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
import sys


# Company OS lives in exactly these four roots. `company/README.md` states the
# dependency rule over them and the control-plane capsule repeats it.
COMPANY_OS_ROOTS: tuple[str, ...] = ("company", "ai_platform", "knowledge", "intelligence")

# The import roots a production module may not name. `knowledge.company_os` is
# spelled out because `knowledge` is also a plain namespace package.
COMPANY_OS_IMPORT_ROOTS: tuple[str, ...] = ("company", "ai_platform", "knowledge", "intelligence")

# Production trees. The first block is what the integration brief lists; the
# second is what this repository additionally contains. Both are filtered
# against the checkout before use.
DECLARED_PRODUCTION_ROOTS: tuple[str, ...] = (
    "engine",
    "entities",
    "godot",
    "marble3d",
    "modes",
    "powers",
    "production",
    "race",
    "race2",
    "sloped",
    # Observed in this repository and equally production.
    "audio",
    "evaluation",
    "rendering",
    "replay",
    "tools",
)

# Single-file entry points that are production by the same rule.
DECLARED_PRODUCTION_FILES: tuple[str, ...] = ("main.py", "race_main.py")

# Company OS test modules follow one naming convention. The architecture check
# does not trust the convention - it proves that every test importing Company
# OS matches it, which is the same statement without a hand-maintained list.
COMPANY_OS_TEST_PREFIX = "test_company"
TEST_ROOT = "tests"

_PRUNED_DIRECTORIES = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".venv",
        "venv",
        "node_modules",
        "exports",
        "out",
        "output",
        "renders",
        "build",
        "dist",
    }
)


@dataclass(frozen=True)
class SourceModule:
    """One parsed Python file, addressed by its repository-relative path.

    `imports` is computed once when the module is parsed rather than on each
    call. Six conditions ask this same file the same question, and walking the
    tree six times made the gate slow enough that people would stop running
    it.
    """

    path: str
    tree: ast.Module
    imports: tuple["ImportRef", ...] = ()


@dataclass(frozen=True)
class ParseFailure:
    """A file the gate could not read as Python, and why."""

    path: str
    reason: str


@dataclass(frozen=True)
class ImportRef:
    """One imported module name, and where it was written.

    `type_checking` marks an import inside `if TYPE_CHECKING:`. It never runs,
    so it is not a runtime dependency, but it is still a coupling worth naming
    separately rather than hiding.
    """

    path: str
    line: int
    module: str
    type_checking: bool = False

    @property
    def root(self) -> str:
        return self.module.split(".", 1)[0]

    def reference(self) -> str:
        return f"{self.path}:{self.line}"


def repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:  # outside the checkout; report what we were given
        return path.as_posix()


def production_roots(repo_root: Path | str) -> tuple[str, ...]:
    """Declared production roots that this checkout actually contains."""
    root = Path(repo_root)
    return tuple(name for name in sorted(DECLARED_PRODUCTION_ROOTS) if (root / name).is_dir())


def absent_production_roots(repo_root: Path | str) -> tuple[str, ...]:
    """Declared production roots this checkout does not have."""
    root = Path(repo_root)
    return tuple(
        name for name in sorted(DECLARED_PRODUCTION_ROOTS) if not (root / name).is_dir()
    )


def production_files(repo_root: Path | str) -> tuple[str, ...]:
    root = Path(repo_root)
    return tuple(name for name in sorted(DECLARED_PRODUCTION_FILES) if (root / name).is_file())


def company_os_roots(repo_root: Path | str) -> tuple[str, ...]:
    root = Path(repo_root)
    return tuple(name for name in COMPANY_OS_ROOTS if (root / name).is_dir())


def iter_python_files(repo_root: Path | str, roots: Sequence[str]) -> Iterator[Path]:
    """Every `*.py` under `roots`, in path order, with generated trees pruned."""
    base = Path(repo_root)
    for name in roots:
        start = base / name
        if start.is_file() and start.suffix == ".py":
            yield start
            continue
        if not start.is_dir():
            continue
        yield from _walk(start)


def _walk(directory: Path) -> Iterator[Path]:
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            if entry.name in _PRUNED_DIRECTORIES:
                continue
            yield from _walk(entry)
        elif entry.suffix == ".py":
            yield entry


def parse_tree(
    repo_root: Path | str, roots: Sequence[str]
) -> tuple[tuple[SourceModule, ...], tuple[ParseFailure, ...]]:
    """Parse every module under `roots`. Failures are returned, never raised.

    A file the gate cannot parse is a finding for `health.sources_parse`, not
    an exception that stops the whole report: one unreadable module must not
    hide the thirty conditions that could still be answered.
    """
    modules: list[SourceModule] = []
    failures: list[ParseFailure] = []
    for path in iter_python_files(repo_root, roots):
        relative = repo_relative(Path(repo_root), path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(ParseFailure(relative, f"cannot be read as UTF-8: {exc}"))
            continue
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            failures.append(ParseFailure(relative, f"line {exc.lineno}: {exc.msg}"))
            continue
        modules.append(SourceModule(relative, tree, _extract_imports(relative, tree)))
    return tuple(modules), tuple(failures)


def module_imports(module: SourceModule) -> tuple[ImportRef, ...]:
    """Every absolute module name this file imports, with TYPE_CHECKING marked.

    Relative imports are resolved against the file's own package, so
    `from .errors import X` inside `company/runtime/` becomes
    `company.runtime.errors` and participates in the cycle check like any other
    edge.
    """
    if module.imports:
        return module.imports
    return _extract_imports(module.path, module.tree)


def _extract_imports(path: str, tree: ast.Module) -> tuple[ImportRef, ...]:
    package = _package_of(path)
    guarded = _type_checking_spans(tree)
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            inside = _within(node.lineno, guarded)
            for alias in node.names:
                refs.append(ImportRef(path, node.lineno, alias.name, inside))
        elif isinstance(node, ast.ImportFrom):
            name = _resolve_from(node, package)
            if name:
                refs.append(ImportRef(path, node.lineno, name, _within(node.lineno, guarded)))
    return tuple(sorted(refs, key=lambda ref: (ref.line, ref.module)))


def _resolve_from(node: ast.ImportFrom, package: tuple[str, ...]) -> str:
    if not node.level:
        return node.module or ""
    if node.level > len(package):
        return ""
    base = package[: len(package) - node.level + 1]
    parts = list(base) + ([node.module] if node.module else [])
    return ".".join(part for part in parts if part)


def _package_of(path: str) -> tuple[str, ...]:
    parts = path.split("/")
    if parts and parts[-1].endswith(".py"):
        parts = parts[:-1] if parts[-1] == "__init__.py" else parts[:-1]
    return tuple(parts)


def _type_checking_spans(tree: ast.Module) -> tuple[tuple[int, int], ...]:
    """Line ranges covered by an `if TYPE_CHECKING:` body.

    Ranges rather than a set of every line: a guarded block is contiguous, and
    walking its whole subtree to enumerate lines made this quadratic on the
    larger modules.
    """
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not _is_type_checking(node.test) or not node.body:
            continue
        start = node.body[0].lineno
        end = max(getattr(item, "end_lineno", item.lineno) or item.lineno for item in node.body)
        spans.append((start, end))
    return tuple(spans)


def _within(line: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= line <= end for start, end in spans)


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def is_stdlib(module_root: str) -> bool:
    """Is this top-level name part of the standard library of the running Python?"""
    return module_root in sys.stdlib_module_names


def subsystem_of(path: str, roots: Sequence[str] = COMPANY_OS_ROOTS) -> str:
    """The Company OS subsystem a path belongs to: `company/runtime`, `ai_platform`.

    One level below a multi-package root, the root itself otherwise. This is
    the granularity the capsules use and therefore the granularity an import
    cycle between subsystems is worth reporting at.
    """
    parts = path.split("/")
    if not parts or parts[0] not in roots:
        return ""
    if parts[0] == "company" and len(parts) > 2:
        return f"company/{parts[1]}"
    if parts[0] == "knowledge" and len(parts) > 2:
        return f"knowledge/{parts[1]}"
    if parts[0] == "intelligence" and len(parts) > 2:
        return f"intelligence/{parts[1]}"
    return parts[0]


def module_subsystem(module_name: str) -> str:
    """The subsystem an imported dotted name resolves to, or an empty string."""
    parts = module_name.split(".")
    if not parts or parts[0] not in COMPANY_OS_ROOTS:
        return ""
    if parts[0] in ("company", "knowledge", "intelligence") and len(parts) > 1:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


__all__ = [
    "COMPANY_OS_IMPORT_ROOTS",
    "COMPANY_OS_ROOTS",
    "COMPANY_OS_TEST_PREFIX",
    "DECLARED_PRODUCTION_FILES",
    "DECLARED_PRODUCTION_ROOTS",
    "TEST_ROOT",
    "ImportRef",
    "ParseFailure",
    "SourceModule",
    "absent_production_roots",
    "company_os_roots",
    "is_stdlib",
    "iter_python_files",
    "module_imports",
    "module_subsystem",
    "parse_tree",
    "production_files",
    "production_roots",
    "repo_relative",
    "subsystem_of",
]
