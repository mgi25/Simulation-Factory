"""File-backed organizational state, under a directory the caller names.

## Definitions and state are separate trees

`company/org_intelligence/*.py` is a definition: it lives in git, it is
reviewed, and it changes when somebody decides the company analyses itself
differently. Everything this store writes is state - the reviews that were run,
the signals that were observed, the recommendations nobody has decided yet.
State goes under a `state_dir` the caller supplies. There is no default
location, for the reason `company/runtime/usage_store.py` gives and
`company/workforce/store.py` repeats: a store with a default writes somewhere by
accident.

## No silent overwrite

This is the one place this store differs from the workforce store, and the
difference is deliberate. A workforce gap legitimately changes state in place. An
organizational record is an observation of a moment: a signal measured over one
window, a finding drawn from it, a recommendation somebody will decide on. Writing
a different record over one of those loses the thing the review was for.

So `put` compares bytes. Identical content is a no-op and returns the existing
path; different content under the same id raises. Replacing takes
`replace=True`, which is a caller saying so in the diff rather than a default
doing it quietly. Observations - the append-only half - go through
`company.runtime.state_paths.append_json_bytes`, which creates with `O_EXCL` so
the filesystem enforces the same rule.

## Determinism

Everything is written through `ai_platform.serde.dumps`: sorted keys, stable
separators, trailing newline. Two equal records produce two identical files,
which is what makes a diff of the state directory mean something. Listing a kind
is `sorted(glob)`. No index, no cache, no database - an index would be a second
copy of the directory, and the directory is the source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable, TypeVar

from ai_platform.serde import dumps, read_json
from company.runtime.state_paths import StateStoreError, append_json_bytes, sorted_records

from .change import (
    ChangeExperiment,
    OrganizationChangeProposal,
    OrganizationChangeReview,
)
from .errors import OrgIntelligenceError
from .findings import OrganizationalFinding
from .recommendations import OrganizationalRecommendation
from .review import OrganizationalReview
from .signals import OrganizationalSignal

T = TypeVar("T")


class OrgIntelligenceStoreError(StateStoreError):
    """An organizational state directory is missing, malformed, or unwritable."""


# kind -> (directory, id attribute, decoder)
_KINDS: dict[str, tuple[str, str, Callable[[dict[str, Any]], Any]]] = {
    "review": ("reviews", "review_id", OrganizationalReview.from_dict),
    "signal": ("signals", "signal_id", OrganizationalSignal.from_dict),
    "finding": ("findings", "finding_id", OrganizationalFinding.from_dict),
    "recommendation": (
        "recommendations",
        "recommendation_id",
        OrganizationalRecommendation.from_dict,
    ),
    "change_proposal": (
        "change_proposals",
        "proposal_id",
        OrganizationChangeProposal.from_dict,
    ),
    "experiment": ("experiments", "experiment_id", ChangeExperiment.from_dict),
    "change_review": ("change_reviews", "review_id", OrganizationChangeReview.from_dict),
}

_KIND_BY_TYPE: dict[type, str] = {
    OrganizationalReview: "review",
    OrganizationalSignal: "signal",
    OrganizationalFinding: "finding",
    OrganizationalRecommendation: "recommendation",
    OrganizationChangeProposal: "change_proposal",
    ChangeExperiment: "experiment",
    OrganizationChangeReview: "change_review",
}

_APPEND_ONLY = "observations"


class OrgIntelligenceStore:
    """Canonical JSON under an explicit root. No index, no cache, no database."""

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise OrgIntelligenceStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()

    # -- identified records -----------------------------------------------

    def put(self, record: Any, *, replace: bool = False) -> Path:
        """Write one record. Refuses to overwrite a different one silently.

        Three outcomes: the file does not exist and is written; the file exists
        with identical bytes and nothing happens; the file exists with different
        bytes and this raises unless `replace=True`. The third case is the one
        that matters - it is how a re-run with changed thresholds stops being
        indistinguishable from the original run.
        """
        kind = self._kind_of(record)
        directory, id_field, _decode = _KINDS[kind]
        record_id = getattr(record, id_field)
        path = self.state_dir / directory / f"{record_id}.json"
        payload = dumps(record.to_dict())
        if path.is_file():
            existing = path.read_text(encoding="utf-8")
            if existing == payload:
                return path
            if not replace:
                raise OrgIntelligenceStoreError(
                    f"{path} already holds a different {kind} {record_id!r}. An "
                    "organizational record is an observation of a moment; write a new id, "
                    "or pass replace=True so the overwrite is visible in the calling code"
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return path

    def get(self, kind: str, record_id: str) -> Any:
        directory, _id_field, decode = self._kind(kind)
        path = self.state_dir / directory / f"{record_id}.json"
        if not path.is_file():
            raise OrgIntelligenceStoreError(
                f"no {kind} record {record_id!r} under {self.state_dir}"
            )
        return self._decode(path, decode, kind, record_id)

    def list(self, kind: str) -> tuple[Any, ...]:
        """Every record of one kind, in filename order. Deterministic by sorting."""
        directory, _id_field, decode = self._kind(kind)
        root = self.state_dir / directory
        if not root.is_dir():
            return ()
        return tuple(
            self._decode(path, decode, kind, path.stem) for path in sorted(root.glob("*.json"))
        )

    def ids(self, kind: str) -> tuple[str, ...]:
        directory, _id_field, _decode = self._kind(kind)
        root = self.state_dir / directory
        if not root.is_dir():
            return ()
        return tuple(path.stem for path in sorted(root.glob("*.json")))

    # -- append-only observations ------------------------------------------

    def append_observation(self, payload: dict[str, Any]) -> Path:
        """Append one raw observation. Never opens an existing record for write.

        For the running notes a review accumulates that have no identity of
        their own. `append_json_bytes` creates with `O_EXCL`, so the
        no-overwrite guarantee here is the filesystem's rather than a
        check-then-write race.
        """
        if not isinstance(payload, dict):
            raise OrgIntelligenceStoreError("an observation is a JSON object")
        return append_json_bytes(
            self.state_dir / _APPEND_ONLY, dumps(payload).encode("utf-8")
        )

    def observations(self) -> tuple[dict[str, Any], ...]:
        root = self.state_dir / _APPEND_ONLY
        if not root.is_dir():
            return ()
        return tuple(self._raw(path) for path in sorted_records(root))

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _kind_of(record: Any) -> str:
        kind = _KIND_BY_TYPE.get(type(record))
        if kind is None:
            raise OrgIntelligenceStoreError(
                f"{type(record).__name__} is not a storable organizational record"
            )
        return kind

    @staticmethod
    def _kind(kind: str) -> tuple[str, str, Callable[[dict[str, Any]], Any]]:
        try:
            return _KINDS[kind]
        except KeyError:
            raise OrgIntelligenceStoreError(
                f"unknown record kind {kind!r}; known kinds: " + ", ".join(sorted(_KINDS))
            ) from None

    @staticmethod
    def _raw(path: Path) -> dict[str, Any]:
        data = read_json(path)
        if not isinstance(data, dict):
            raise OrgIntelligenceStoreError(f"{path}: an observation is a JSON object")
        return data

    @staticmethod
    def _decode(
        path: Path, decode: Callable[[dict[str, Any]], T], kind: str, record_id: str
    ) -> T:
        try:
            data = read_json(path)
        except ValueError as exc:
            raise OrgIntelligenceStoreError(f"{path}: not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise OrgIntelligenceStoreError(f"{path}: a {kind} record is a JSON object")
        try:
            return decode(data)
        except (KeyError, ValueError, OrgIntelligenceError) as exc:
            raise OrgIntelligenceStoreError(
                f"{path}: {kind} {record_id!r} does not decode: {exc}"
            ) from exc


def write_all(store: OrgIntelligenceStore, records: Iterable[Any]) -> tuple[Path, ...]:
    """Write a batch in the order given. No transaction: there is no database."""
    return tuple(store.put(record) for record in records)
