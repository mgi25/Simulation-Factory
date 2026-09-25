"""The current repository, as the experience store is allowed to see it.

Two jobs, and they are the same job at two moments. At **capture** it records
the scoped contract and structural state an episode depended on
(`capture_provenance`). At **query** it decides whether that state still holds
(`evaluate_validity`) and revalidates every suggestion against the
repository as it is now - the current capsule contracts, the files on disk,
and P6B's import graph whenever a caller supplies one - before anything is
offered.

## Validity is scoped, never a whole-repository commit

| status | means | may drive a suggestion |
|---|---|---|
| `current` | every anchored capsule contract and path governance is unchanged, and every file the attempt only read has the same structure | yes, after per-item revalidation |
| `stale` | a relevant contract, governance or structure moved | no - historical reference only |
| `invalid` | something the episode rests on is gone: a capsule, a path, a canonical record, or the capsule store itself | no - excluded |

A commit SHA would be simpler and useless: every render, every race course,
every unrelated control-plane change would make every episode stale. The
anchors are chosen so an unrelated change moves none of them.

## Why three anchors, and why not file content everywhere

**Capsule contracts** (`contract_digest`): the governed surface - what a
subsystem owns, may read, must not modify, and which tests witness it. A
precedent recorded under one contract is not evidence about work under
another, so any change is `stale`. Prose fields (title, purpose, review
dates, source digests) are excluded: re-wording a capsule is not a contract
change.

**Path governance**: which in-force capsules govern each path the episode
touched. Ownership moving is a contract change even when neither capsule's own
digest did.

**Structure of files the attempt read but did not change**
(`structural_digest`: top-level names plus import statements). Body and
comment edits do not move it; a renamed function, a removed class or a new
import does.

A file the attempt **changed** is deliberately *not* anchored by content or
structure. Its content legitimately differs before and after the change is
integrated, and capture does not know which side of that it is on - anchoring
it would mark every accepted precedent stale the moment its own change
merged. It is anchored by existence and governance instead. Tests are
anchored the same way; whether a test still matters to a task is decided per
suggestion, from the current import graph, not from a digest of a file that
every change to the subsystem edits.

## Why the import graph is supplied, never imported

P6B's canonical graph (`build_dependency_graph(GateScan.of(root))`) lives in
`company.integration`, and the gate is read by no other Company OS subsystem
(`tests/test_company_integration_gate.py::test_no_other_company_os_subsystem_
imports_the_gate`): a subsystem that could reach gate code could reach code
that produces a readiness verdict. So this package never imports it. A caller
that holds a graph passes a `graph_builder` - a test, or the replay harness,
which runs outside Company OS - and three states follow, each honest:

| `graph_state` | means | a suggestion that needs the graph |
|---|---|---|
| `built` | the caller supplied a graph and it was built | checked here |
| `not_supplied` | nobody supplied one | offered with `checked` omitting `import_graph`, so the consumer must check |
| `failed: ...` | a graph was supplied and could not be built | refused - an attempted check that errored is not a pass |

The consumer in the real flow is the external runner, and it always performs
the import-graph check itself with its own P6B map (`tools/engineering_runner/
repo_map.py`, pinned to the same resolution rules), built from the task's own
worktree - the most current tree there is. So every suggestion that reaches a
session has been checked against a current import graph exactly once, by the
component that holds one.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from company.runtime.git_evidence import read_ref
from knowledge.company_os.capsules import CapsuleIndex, normalise_path
from knowledge.company_os.records import RecordStatus

from .model import CapsuleAnchor, ExperienceEpisode, PathAnchor, ScopeProvenance


# The capsule fields that constitute its contract. Everything that governs
# what a task may touch or must prove; nothing that only describes it.
CONTRACT_FIELDS: tuple[str, ...] = (
    "owns_paths",
    "may_read",
    "may_write",
    "must_not_modify",
    "dependencies",
    "invariants",
    "tests",
    "capabilities",
    "status",
)

# Mirrors `company.integration.suites._IN_FORCE` and
# `company.integration.dependencies.IN_FORCE_STATUSES`: a capsule flagged for
# revalidation still governs; only superseded and retired stop.
IN_FORCE: frozenset[RecordStatus] = frozenset(
    {RecordStatus.ACTIVE, RecordStatus.NEEDS_REVALIDATION}
)

SEED_PATH = "knowledge/company_os/capsules/seeds"
TEST_PREFIX = "tests/"


class Validity(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True)
class ValidityReport:
    status: Validity
    reasons: tuple[str, ...] = ()

    @property
    def reusable(self) -> bool:
        return self.status is Validity.CURRENT

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "reasons": list(self.reasons)}


def covers(rule: str, path: str) -> bool:
    """Whether a path rule grants `path`, wildcards included.

    The same reading as `company.runtime.context_expansion_policy._covers` and
    `company.engineering.work_order._read_covers`, restated because both are
    private; `tests/test_company_experience_store.py` pins all three to one
    table of hard cases so the restatement cannot drift.
    """
    rule = str(rule).replace("\\", "/")
    path = str(path).replace("\\", "/")
    if not rule or not path:
        return False
    if any(token in rule for token in "*?["):
        return PurePosixPath(path).match(rule)
    return path == rule or path.startswith(rule + "/")


def contract_digest(capsule: Any) -> str:
    """The identity of a capsule's contract: the governing fields, nothing else."""
    return _fingerprint({name: to_jsonable(getattr(capsule, name)) for name in CONTRACT_FIELDS})


def structural_digest_of(path: Path) -> str:
    """Top-level names and imports for Python; bytes for anything else.

    Empty when the file does not exist. A Python file that does not parse is
    digested by its bytes, which makes any edit to it a structural change -
    the conservative reading of a file nobody can read structurally.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if path.suffix != ".py":
        return hashlib.sha256(data).hexdigest()[:16]
    try:
        tree = ast.parse(data.decode("utf-8", errors="replace"))
    except SyntaxError:
        return hashlib.sha256(data).hexdigest()[:16]
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(f"def:{node.name}")
        elif isinstance(node, ast.Assign):
            names.extend(f"let:{t.id}" for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(f"let:{node.target.id}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(f"import:{alias.name}" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            names.extend(f"from:{base}:{alias.name}" for alias in node.names)
    return _fingerprint(sorted(set(names)))


def file_digest(path: Path) -> str:
    """SHA-256 of a file's bytes, first 16 hex; empty when unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


@dataclass
class RepositoryView:
    """The repository at one moment: capsule contracts, files, and the import graph.

    `graph_builder` exists so a caller that cannot afford - or is not allowed -
    to parse the checkout can supply the graph another way (a replay harness
    holding historical trees, a test with a synthetic graph). Left None, the
    canonical P6B builder is used.
    """

    repo_root: Path
    capsules: CapsuleIndex | None = None
    capsule_error: str = ""
    graph_builder: Callable[[Path], Any] | None = None
    _graph: Any = field(default=None, repr=False)
    _graph_error: str = field(default="", repr=False)
    _graph_built: bool = field(default=False, repr=False)

    @classmethod
    def load(
        cls,
        repo_root: str | Path,
        *,
        capsule_root: str | Path | None = None,
        graph_builder: Callable[[Path], Any] | None = None,
    ) -> "RepositoryView":
        root = Path(repo_root).resolve()
        seeds = Path(capsule_root) if capsule_root is not None else root / SEED_PATH
        try:
            index: CapsuleIndex | None = CapsuleIndex.load(seeds)
            error = "" if len(index) else f"no capsules under {seeds}"
            if not len(index):
                index = None
        except Exception as exc:  # noqa: BLE001 - an unreadable store is a finding
            index, error = None, f"capsule store unreadable: {type(exc).__name__}: {exc}"
        return cls(repo_root=root, capsules=index, capsule_error=error, graph_builder=graph_builder)

    # --- capsules -------------------------------------------------------------

    def capsule(self, capsule_id: str) -> Any | None:
        if self.capsules is None or capsule_id not in self.capsules:
            return None
        return self.capsules.get(capsule_id)

    def governing(self, path: str) -> tuple[str, ...]:
        """In-force capsules that own `path`, or - for a test - declare it."""
        if self.capsules is None:
            return ()
        clean = normalise_path(path)
        found: set[str] = set()
        for capsule in self.capsules.all():
            if capsule.status not in IN_FORCE:
                continue
            if any(covers(rule, clean) for rule in capsule.owns_paths):
                found.add(capsule.id)
            elif clean.startswith(TEST_PREFIX) and any(
                normalise_path(test) == clean for test in capsule.tests
            ):
                found.add(capsule.id)
        return tuple(sorted(found))

    def governing_all(self, paths: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({cid for path in paths for cid in self.governing(path)}))

    # --- files ----------------------------------------------------------------

    def exists(self, path: str) -> bool:
        clean = normalise_path(path)
        if not clean or clean.startswith("/") or ".." in clean.split("/"):
            return False
        return (self.repo_root / clean).exists()

    def is_file(self, path: str) -> bool:
        clean = normalise_path(path)
        if not clean or clean.startswith("/") or ".." in clean.split("/"):
            return False
        return (self.repo_root / clean).is_file()

    def structural_digest(self, path: str) -> str:
        return structural_digest_of(self.repo_root / normalise_path(path))

    def commit(self) -> str:
        try:
            value = read_ref(self.repo_root, "HEAD")
        except Exception:  # noqa: BLE001 - informational only
            return ""
        return value if len(value) == 40 else ""

    # --- the P6B import graph ---------------------------------------------------

    @property
    def graph(self) -> Any | None:
        """The supplied P6B dependency graph, built once, or None."""
        if not self._graph_built:
            self._graph_built = True
            if self.graph_builder is not None:
                try:
                    self._graph = self.graph_builder(self.repo_root)
                except Exception as exc:  # noqa: BLE001 - fails closed, see module doc
                    self._graph = None
                    self._graph_error = f"{type(exc).__name__}: {exc}"
        return self._graph

    @property
    def graph_error(self) -> str:
        return self._graph_error

    @property
    def graph_state(self) -> str:
        """`built`, `not_supplied`, or `failed: <why>` - see the module docstring."""
        if self.graph is not None:
            return "built"
        if self.graph_builder is None:
            return "not_supplied"
        return f"failed: {self._graph_error}"

    def modules_under(self, rule: str) -> tuple[str, ...]:
        graph = self.graph
        if graph is None:
            return ()
        return tuple(m for m in graph.modules if covers(rule, m))


# --- capture ---------------------------------------------------------------------


def capture_provenance(
    view: RepositoryView,
    *,
    captured_on: Any,
    decision_capsules: Iterable[str],
    changed: Iterable[str],
    read: Iterable[str],
    tests: Iterable[str],
) -> ScopeProvenance:
    """Anchor an episode's scope in the repository as it stands at capture."""
    changed_set = sorted({normalise_path(p) for p in changed if normalise_path(p)})
    read_set = sorted({normalise_path(p) for p in read if normalise_path(p)} - set(changed_set))
    test_set = sorted({normalise_path(p) for p in tests if normalise_path(p)} - set(changed_set) - set(read_set))
    paths: list[PathAnchor] = []
    for role, members in (("changed", changed_set), ("read", read_set), ("test", test_set)):
        for path in members:
            paths.append(
                PathAnchor(
                    path=path,
                    role=role,
                    governed_by=view.governing(path),
                    digest=view.structural_digest(path) if role == "read" else "",
                )
            )
    capsule_ids = set(decision_capsules) | {cid for anchor in paths for cid in anchor.governed_by}
    anchors = []
    for capsule_id in sorted(capsule_ids):
        capsule = view.capsule(capsule_id)
        if capsule is not None:
            anchors.append(CapsuleAnchor(capsule_id=capsule_id, contract_digest=contract_digest(capsule)))
    return ScopeProvenance(
        captured_on=captured_on,
        repository_commit=view.commit(),
        capsules=tuple(anchors),
        paths=tuple(paths),
    )


# --- query -----------------------------------------------------------------------


def evaluate_validity(
    episode: ExperienceEpisode,
    view: RepositoryView,
    *,
    pointer_problems: Iterable[str] = (),
) -> ValidityReport:
    """Whether an episode may still be reused, and every reason it may not.

    `pointer_problems` are the caller's findings about the canonical records
    behind the episode's pointers (see `capture.verify_pointers`). A pointer
    that no longer resolves makes the episode unresolved: an index entry whose
    evidence is gone is an assertion nobody can check.
    """
    invalid: list[str] = [f"canonical evidence: {item}" for item in pointer_problems]
    stale: list[str] = []
    if view.capsules is None:
        invalid.append(view.capsule_error or "capsule store unavailable")
        return ValidityReport(Validity.INVALID, tuple(invalid))
    provenance = episode.provenance
    if not provenance.capsules and not provenance.paths:
        invalid.append("no scoped provenance was recorded at capture")
    for anchor in provenance.capsules:
        capsule = view.capsule(anchor.capsule_id)
        if capsule is None:
            invalid.append(f"capsule {anchor.capsule_id} no longer exists")
        elif capsule.status not in IN_FORCE:
            invalid.append(f"capsule {anchor.capsule_id} is {capsule.status.value}")
        elif contract_digest(capsule) != anchor.contract_digest:
            stale.append(f"capsule {anchor.capsule_id} contract changed since capture")
    for anchor in provenance.paths:
        if not view.exists(anchor.path):
            invalid.append(f"{anchor.path} no longer exists")
            continue
        now = view.governing(anchor.path)
        if set(now) != set(anchor.governed_by):
            stale.append(
                f"{anchor.path} is governed by {', '.join(now) or 'nothing'} "
                f"(was {', '.join(anchor.governed_by) or 'nothing'})"
            )
        if anchor.role == "read" and anchor.digest and view.structural_digest(anchor.path) != anchor.digest:
            stale.append(f"{anchor.path} changed structure since it was read")
    if invalid:
        return ValidityReport(Validity.INVALID, tuple(invalid + stale))
    if stale:
        return ValidityReport(Validity.STALE, tuple(stale))
    return ValidityReport(Validity.CURRENT, ())


__all__ = [
    "CONTRACT_FIELDS",
    "IN_FORCE",
    "RepositoryView",
    "Validity",
    "ValidityReport",
    "capture_provenance",
    "contract_digest",
    "covers",
    "evaluate_validity",
    "file_digest",
    "structural_digest_of",
]
