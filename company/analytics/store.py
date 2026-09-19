"""File-backed analytics state, append-only, under a directory the caller names.

## Definitions and state are separate trees

`company/analytics/*.py` is definition: reviewed code that changes when somebody
decides we measure differently. Everything this store writes is state - the
readings that were taken, the experiments that were specified, what was
concluded. State goes under a `state_dir` the caller supplies, and this module
never defaults to a directory inside the repository, for the reason
`company/runtime/usage_store.py` and `company/finance/store.py` both give: a
store with a default location writes somewhere by accident.

## One write mode, because observation history has one rule

`put()` refuses a second write of the same id with different bytes.
Byte-identical is a no-op, so replaying an import is safe; anything else raises
`LedgerViolation` naming the fields that differ.

That is section 4 enforced at the filesystem. There is no update path for an
observation and no reason to want one: a video re-read at thirty days is a new
observation with a new id, and the 24-hour reading stays exactly as it was
recorded. A correction to a mis-transcribed figure is also a new record - one
that supersedes the old one in a postmortem or a result, so the history reads
forwards and the mistake stays visible.

## The observation ledger is the total order

Records live in per-kind directories keyed by id, which is what makes them
findable. The ledger under `ledger/` is the other view: one append-only sequence
of every observation as it arrived, created with `O_EXCL` through
`company.runtime.state_paths.append_json_bytes`, so the filesystem rather than a
check-then-write guarantees that nothing is replaced. Reading it back in order
answers "what did we know about this video, and when did we know it".

Only observations are mirrored. A specification or a learning is a document with
an identity; an observation is an event, and the sequence of events is the thing
a retrospective needs to replay.

No database, no index file, no cache. Listing a kind is `sorted(glob)`, which is
deterministic and costs nothing at this scale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from ai_platform.serde import dumps, fingerprint, read_json
from company.runtime.state_paths import (
    StateStoreError,
    append_json_bytes,
    sorted_records,
)

from .api_source import ApiArtifactSource
from .baseline import FormatBaseline
from .deliverable import AnalyzedDeliverable
from .errors import AnalyticsError, LedgerViolation
from .experiments import ExperimentSpecification
from .learning import AnalyticsHypothesis, AnalyticsLearning
from .metrics import DEFAULT_REGISTRY, MetricDefinition, MetricRegistry
from .observations import MetricObservation
from .postmortem import DeliverablePostmortem
from .results import ExperimentResult
from .studio_source import StudioExportSource

T = TypeVar("T")


class AnalyticsStoreError(StateStoreError):
    """An analytics state directory is missing, malformed, or unwritable."""


_LEDGER = "ledger"

# kind -> (directory, id attribute, decoder). One row per storable record type.
_KINDS: dict[str, tuple[str, str, Callable[..., Any]]] = {
    "deliverable": ("deliverables", "deliverable_id", AnalyzedDeliverable.from_dict),
    "observation": ("observations", "observation_id", MetricObservation.from_dict),
    "metric": ("metrics", "name", MetricDefinition.from_dict),
    "experiment": ("experiments", "experiment_id", ExperimentSpecification.from_dict),
    "result": ("results", "result_id", ExperimentResult.from_dict),
    "postmortem": ("postmortems", "postmortem_id", DeliverablePostmortem.from_dict),
    "learning": ("learnings", "learning_id", AnalyticsLearning.from_dict),
    "hypothesis": ("hypotheses", "hypothesis_id", AnalyticsHypothesis.from_dict),
    "baseline": ("baselines", "baseline_id", FormatBaseline.from_dict),
    # The export an import came off: which file, which bytes, what it was
    # declared to cover. A document about readings rather than a reading, so it
    # is stored beside them and stays out of the event ledger.
    "studio_source": ("studio_sources", "source_id", StudioExportSource.from_dict),
    # The API pull an import came off: which window, which digest of what was
    # reported, under which grant. The same kind of document as a studio source
    # and stored the same way - beside the readings, out of the event ledger.
    "api_source": ("api_sources", "source_id", ApiArtifactSource.from_dict),
}

_KIND_BY_TYPE: dict[type, str] = {
    AnalyzedDeliverable: "deliverable",
    MetricObservation: "observation",
    MetricDefinition: "metric",
    ExperimentSpecification: "experiment",
    ExperimentResult: "result",
    DeliverablePostmortem: "postmortem",
    AnalyticsLearning: "learning",
    AnalyticsHypothesis: "hypothesis",
    FormatBaseline: "baseline",
    StudioExportSource: "studio_source",
    ApiArtifactSource: "api_source",
}

# Kinds mirrored into the event ledger. Just the one: an observation is the
# event this subsystem records, and everything else is a document about events.
_EVENT_KINDS = frozenset({"observation"})


class AnalyticsStore:
    """Canonical JSON under an explicit root. Append-only, no index, no database."""

    def __init__(
        self, state_dir: str | Path, registry: MetricRegistry | None = None
    ) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise AnalyticsStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.registry = registry or DEFAULT_REGISTRY

    # -- writing -----------------------------------------------------------

    def put(self, record: Any) -> Path:
        """Write one record. A second write of the same id may not differ."""
        kind = self._kind_of(record)
        directory, id_field, _decode = _KINDS[kind]
        record_id = getattr(record, id_field)
        path = self.state_dir / directory / f"{record_id}.json"
        payload = dumps(record.to_dict())
        if path.is_file():
            existing = path.read_text(encoding="utf-8")
            if existing == payload:
                return path
            raise LedgerViolation(
                f"{kind} {record_id!r} is already recorded with different content: "
                + ", ".join(self._differing_fields(existing, payload))
                + ". Analytics history is append-only - a later reading is a new "
                "observation with its own id, and a correction is a new record that "
                "supersedes this one rather than an edit to what was believed"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        if kind in _EVENT_KINDS:
            self._append_ledger(kind, record_id, record)
        return path

    def put_all(self, records: Iterable[Any]) -> tuple[Path, ...]:
        """Write a batch in the order given. No transaction: there is no database."""
        return tuple(self.put(record) for record in records)

    @staticmethod
    def _differing_fields(existing: str, incoming: str) -> tuple[str, ...]:
        import json

        try:
            before = json.loads(existing)
            after = json.loads(incoming)
        except ValueError:  # pragma: no cover - a corrupt file is its own error
            return ("the stored file is not valid JSON",)
        if not isinstance(before, dict) or not isinstance(after, dict):
            return ("the stored record is not an object",)
        changed = sorted(
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        )
        return tuple(changed) or ("formatting",)

    def _append_ledger(self, kind: str, record_id: str, record: Any) -> Path:
        entry = {
            "kind": kind,
            "record_id": record_id,
            "fingerprint": fingerprint(record.to_dict()),
            "deliverable_id": getattr(record, "deliverable_id", ""),
            "metric": getattr(getattr(record, "metric", None), "name", ""),
            "observed_at": record.observed_at.isoformat(),
        }
        return append_json_bytes(self.state_dir / _LEDGER, dumps(entry).encode("utf-8"))

    # -- reading -----------------------------------------------------------

    def get(self, kind: str, record_id: str) -> Any:
        directory, _id_field, decode = self._kind(kind)
        path = self.state_dir / directory / f"{record_id}.json"
        if not path.is_file():
            raise AnalyticsStoreError(
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
            self._decode(path, decode, kind, path.stem)
            for path in sorted(root.glob("*.json"))
        )

    def ids(self, kind: str) -> tuple[str, ...]:
        directory, _id_field, _decode = self._kind(kind)
        root = self.state_dir / directory
        if not root.is_dir():
            return ()
        return tuple(path.stem for path in sorted(root.glob("*.json")))

    def observations_for(self, deliverable_id: str) -> tuple[MetricObservation, ...]:
        """Every reading of one deliverable, in the order taken."""
        return tuple(
            sorted(
                (
                    o
                    for o in self.list("observation")
                    if o.deliverable_id == deliverable_id
                ),
                key=lambda o: (o.observed_at, o.observation_id),
            )
        )

    def ledger(self) -> tuple[dict[str, Any], ...]:
        """Every observation in the order it was written."""
        root = self.state_dir / _LEDGER
        if not root.is_dir():
            return ()
        out: list[dict[str, Any]] = []
        for path in sorted_records(root):
            data = read_json(path)
            if not isinstance(data, dict):
                raise AnalyticsStoreError(f"{path}: a ledger entry is a JSON object")
            out.append(data)
        return tuple(out)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _kind_of(record: Any) -> str:
        kind = _KIND_BY_TYPE.get(type(record))
        if kind is None:
            raise AnalyticsStoreError(
                f"{type(record).__name__} is not a storable analytics record. Known "
                "kinds: " + ", ".join(sorted(_KINDS))
            )
        return kind

    @staticmethod
    def _kind(kind: str) -> tuple[str, str, Callable[..., Any]]:
        try:
            return _KINDS[kind]
        except KeyError:
            raise AnalyticsStoreError(
                f"unknown record kind {kind!r}; known kinds: " + ", ".join(sorted(_KINDS))
            ) from None

    def _decode(
        self, path: Path, decode: Callable[..., T], kind: str, record_id: str
    ) -> T:
        try:
            data = read_json(path)
        except ValueError as exc:
            raise AnalyticsStoreError(f"{path}: not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AnalyticsStoreError(f"{path}: a {kind} record is a JSON object")
        try:
            if kind == "observation":
                return decode(data, self.registry)
            if kind == "baseline":
                return decode(data, self._metric_definitions())
            return decode(data)
        except (KeyError, ValueError, AnalyticsError) as exc:
            raise AnalyticsStoreError(
                f"{path}: {kind} {record_id!r} does not decode: {exc}"
            ) from exc

    def _metric_definitions(self) -> dict[str, MetricDefinition]:
        """Every definition a stored baseline might refer to.

        The registry first, then any definition written to this store, so a
        baseline over a bespoke metric decodes without the caller having to
        rebuild the registry that produced it.
        """
        out = dict(
            (name, self.registry.get(name)) for name in self.registry.names()
        )
        directory = self.state_dir / _KINDS["metric"][0]
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                data = read_json(path)
                if isinstance(data, dict):
                    definition = MetricDefinition.from_dict(data)
                    out[definition.name] = definition
        return out
