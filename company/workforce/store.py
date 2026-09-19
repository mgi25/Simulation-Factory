"""File-backed workforce state, under a directory the caller names.

## Definitions and state are separate trees

`company/workforce/*.py` and `capability_registry.json` are *definitions*: they
live in git, they are reviewed, and they change when someone decides the company
works differently. Everything this store writes is *state*: gaps that were
observed, proposals that were made, evaluations that were run. State goes under
a `state_dir` the caller supplies - a tmp path in tests, an operator-chosen
directory in use - and this module never defaults to a directory inside the
repository. `company/runtime/usage_store.py` made the same choice for the same
reason: a store with a default location writes somewhere by accident.

## Two write modes, deliberately

Records with an identity - a gap, a proposal, a role specification, one
employee's employment record - are written at `<kind>/<id>.json` and may be
rewritten as they change state. Observations have no identity and are appended
through `company.runtime.state_paths.append_json_bytes`, which creates with
`O_EXCL` so an existing record is never opened for write.

Both write canonical JSON from `ai_platform.serde.dumps`: sorted keys, stable
separators, trailing newline. Two equal records produce two identical files,
which is what makes a diff of the state directory mean something.

No database, no index file, no cache. Listing a kind is `sorted(glob)`, which is
deterministic and costs nothing at this scale; an index would be a second copy
of the directory, and the directory is the source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable, TypeVar

from ai_platform.serde import dumps, read_json
from company.runtime.state_paths import (
    StateStoreError,
    append_json_bytes,
    sorted_records,
    task_directory_name,
)

from .debt import OrganizationalDebt
from .employment import EmploymentRecord
from .errors import WorkforceError
from .evaluation import CandidateEvaluation
from .gaps import CapabilityGap
from .performance import PerformanceObservation
from .proposals import WorkforceProposal
from .roles import RoleSpecification
from .shadow import ShadowAssignment, ShadowComparison

T = TypeVar("T")


class WorkforceStoreError(StateStoreError):
    """A workforce state directory is missing, malformed, or unwritable."""


# kind -> (directory, id attribute, decoder)
_KINDS: dict[str, tuple[str, str, Callable[[dict[str, Any]], Any]]] = {
    "gap": ("gaps", "gap_id", CapabilityGap.from_dict),
    "proposal": ("proposals", "proposal_id", WorkforceProposal.from_dict),
    "role": ("role_specifications", "role_id", RoleSpecification.from_dict),
    "evaluation": ("evaluations", "evaluation_id", CandidateEvaluation.from_dict),
    "employment": ("employment", "employee_id", EmploymentRecord.from_dict),
    "shadow_assignment": ("shadow_assignments", "assignment_id", ShadowAssignment.from_dict),
    "shadow_comparison": ("shadow_comparisons", "comparison_id", ShadowComparison.from_dict),
    "debt": ("organizational_debt", "debt_id", OrganizationalDebt.from_dict),
}

_KIND_BY_TYPE: dict[type, str] = {
    CapabilityGap: "gap",
    WorkforceProposal: "proposal",
    RoleSpecification: "role",
    CandidateEvaluation: "evaluation",
    EmploymentRecord: "employment",
    ShadowAssignment: "shadow_assignment",
    ShadowComparison: "shadow_comparison",
    OrganizationalDebt: "debt",
}

_OBSERVATIONS = "performance"


class WorkforceStore:
    """Canonical JSON under an explicit root. No index, no cache, no database."""

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise WorkforceStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()

    # -- identified records -----------------------------------------------

    def put(self, record: Any) -> Path:
        """Write one identified record, replacing an earlier version of itself.

        Replacement is allowed here and refused for observations, because these
        records model something that legitimately changes - a gap gets resolved,
        a proposal gets approved - and their own classes carry the history that
        matters (`EmploymentRecord.history`, `CandidateEvaluation.outcomes`).
        """
        kind = self._kind_of(record)
        directory, id_field, _decode = _KINDS[kind]
        record_id = getattr(record, id_field)
        path = self.state_dir / directory / f"{record_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(record.to_dict()), encoding="utf-8")
        return path

    def get(self, kind: str, record_id: str) -> Any:
        directory, _id_field, decode = self._kind(kind)
        path = self.state_dir / directory / f"{record_id}.json"
        if not path.is_file():
            raise WorkforceStoreError(f"no {kind} record {record_id!r} under {self.state_dir}")
        return self._decode(path, decode, kind, record_id)

    def list(self, kind: str) -> tuple[Any, ...]:
        """Every record of one kind, in filename order. Deterministic by sorting."""
        directory, _id_field, decode = self._kind(kind)
        root = self.state_dir / directory
        if not root.is_dir():
            return ()
        return tuple(
            self._decode(path, decode, kind, path.stem)
            for path in sorted(root.glob("*.json"))
        )

    def ids(self, kind: str) -> tuple[str, ...]:
        directory, _id_field, _decode = self._kind(kind)
        root = self.state_dir / directory
        if not root.is_dir():
            return ()
        return tuple(path.stem for path in sorted(root.glob("*.json")))

    # -- append-only observations ------------------------------------------

    def append_observation(self, observation: PerformanceObservation) -> Path:
        """Append one performance observation. Never overwrites an existing one."""
        if not isinstance(observation, PerformanceObservation):
            raise WorkforceStoreError("append_observation takes a PerformanceObservation")
        directory = (
            self.state_dir
            / _OBSERVATIONS
            / task_directory_name(f"{observation.employee_id}/{observation.capability_id}")
        )
        return append_json_bytes(directory, dumps(observation.to_dict()).encode("utf-8"))

    def observations(
        self, employee_id: str | None = None, capability_id: str | None = None
    ) -> tuple[PerformanceObservation, ...]:
        """Observations in append order, optionally filtered.

        Filtering happens after decoding rather than by directory name, because
        the directory name is a hash-suffixed slug and reconstructing it for a
        partial filter would be a second implementation of the naming rule.
        """
        root = self.state_dir / _OBSERVATIONS
        if not root.is_dir():
            return ()
        found: list[PerformanceObservation] = []
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            for path in sorted_records(directory):
                found.append(
                    self._decode(
                        path, PerformanceObservation.from_dict, "observation", path.name
                    )
                )
        return tuple(
            item
            for item in found
            if (employee_id is None or item.employee_id == employee_id)
            and (capability_id is None or item.capability_id == capability_id)
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _kind_of(record: Any) -> str:
        kind = _KIND_BY_TYPE.get(type(record))
        if kind is None:
            raise WorkforceStoreError(
                f"{type(record).__name__} is not a storable workforce record. Performance "
                "observations go through append_observation"
            )
        return kind

    @staticmethod
    def _kind(kind: str) -> tuple[str, str, Callable[[dict[str, Any]], Any]]:
        try:
            return _KINDS[kind]
        except KeyError:
            raise WorkforceStoreError(
                f"unknown record kind {kind!r}; known kinds: " + ", ".join(sorted(_KINDS))
            ) from None

    @staticmethod
    def _decode(
        path: Path, decode: Callable[[dict[str, Any]], T], kind: str, record_id: str
    ) -> T:
        try:
            data = read_json(path)
        except ValueError as exc:
            raise WorkforceStoreError(f"{path}: not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise WorkforceStoreError(f"{path}: a {kind} record is a JSON object")
        try:
            return decode(data)
        except (KeyError, ValueError, WorkforceError) as exc:
            raise WorkforceStoreError(
                f"{path}: {kind} {record_id!r} does not decode: {exc}"
            ) from exc


def write_all(store: WorkforceStore, records: Iterable[Any]) -> tuple[Path, ...]:
    """Write a batch in the order given. No transaction: there is no database."""
    return tuple(store.put(record) for record in records)
