"""File-backed financial state, append-only, under a directory the caller names.

## Definitions and state are separate trees

`company/finance/*.py` is definition: reviewed code that changes when somebody
decides the company accounts differently. Everything this store writes is state
- the costs that were incurred, the prices that were in force, the proposals
that were made. State goes under a `state_dir` the caller supplies, and this
module never defaults to a directory inside the repository, for the reason
`company/runtime/usage_store.py` gives: a store with a default location writes
somewhere by accident.

## One write mode, because financial history has one rule

`company/workforce/store.py` has two modes - identified records may be
rewritten, observations may not. This store has only the second. Section 16:
financial records are append-only, and a correction is a new record rather than
an edit.

So `put()` refuses a second write of the same id with different bytes, and
`LedgerViolation` names both the record and the field that differs. Writing
byte-identical content again is a no-op rather than an error, because an
idempotent replay of the same import should not fail.

What legitimately changes state does so through a *second* record: a
`CostAdjustment` against a cost, a `SpendDecision` against a proposal, a
superseding `CostRate` or `BudgetLine`. Every one of them names what it
supersedes, so the history reads forwards.

## The event ledger is the total order

Records live in per-kind directories keyed by id, which is what makes them
findable. The ledger under `ledger/` is the other view: one append-only sequence
of every money-bearing record as it arrived, created with `O_EXCL` through
`company.runtime.state_paths.append_json_bytes`, so the filesystem rather than a
check-then-write guarantees that nothing is replaced. Reading it back in order
answers "what did we know, and when did we know it".

No database, no index file, no cache. Listing a kind is `sorted(glob)`, which is
deterministic and costs nothing at this scale.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from ai_platform.serde import dumps, fingerprint, read_json
from company.runtime.state_paths import (
    StateStoreError,
    append_json_bytes,
    sorted_records,
)

from .budget import BudgetLine
from .costs import CostAdjustment, CostRecord
from .errors import FinanceError, LedgerViolation
from .investment import ReusableInvestment, ReuseEvent
from .labour import LabourRate
from .mapping import ResourceCostMapping
from .period import FinancialPeriod
from .proposals import SpendDecision, SpendProposal
from .rates import CostRate
from .recommendations import FinancialRecommendation
from .revenue import RevenueRecord

T = TypeVar("T")


class FinanceStoreError(StateStoreError):
    """A finance state directory is missing, malformed, or unwritable."""


# kind -> (directory, id attribute, decoder). One row per storable record type.
_KINDS: dict[str, tuple[str, str, Callable[[dict[str, Any]], Any]]] = {
    "period": ("periods", "period_id", FinancialPeriod.from_dict),
    "cost": ("costs", "cost_id", CostRecord.from_dict),
    "cost_adjustment": ("cost_adjustments", "adjustment_id", CostAdjustment.from_dict),
    "revenue": ("revenue", "revenue_id", RevenueRecord.from_dict),
    "rate": ("rates", "rate_id", CostRate.from_dict),
    "labour_rate": ("labour_rates", "rate_id", LabourRate.from_dict),
    "resource_cost_mapping": (
        "resource_cost_mappings",
        "mapping_id",
        ResourceCostMapping.from_dict,
    ),
    "budget": ("budgets", "budget_id", BudgetLine.from_dict),
    "reusable_investment": (
        "reusable_investments",
        "investment_id",
        ReusableInvestment.from_dict,
    ),
    "reuse_event": ("reuse_events", "event_id", ReuseEvent.from_dict),
    "spend_proposal": ("spend_proposals", "proposal_id", SpendProposal.from_dict),
    "spend_decision": ("spend_decisions", "decision_id", SpendDecision.from_dict),
    "financial_recommendation": (
        "financial_recommendations",
        "recommendation_id",
        FinancialRecommendation.from_dict,
    ),
}

_KIND_BY_TYPE: dict[type, str] = {
    FinancialPeriod: "period",
    CostRecord: "cost",
    CostAdjustment: "cost_adjustment",
    RevenueRecord: "revenue",
    CostRate: "rate",
    LabourRate: "labour_rate",
    ResourceCostMapping: "resource_cost_mapping",
    BudgetLine: "budget",
    ReusableInvestment: "reusable_investment",
    ReuseEvent: "reuse_event",
    SpendProposal: "spend_proposal",
    SpendDecision: "spend_decision",
    FinancialRecommendation: "financial_recommendation",
}

# Kinds that carry an amount. Every one of these is mirrored into the event
# ledger on write, so the sequence of money the company recorded is readable
# without walking thirteen directories.
_MONEY_KINDS = frozenset(
    {"cost", "cost_adjustment", "revenue", "rate", "labour_rate", "budget",
     "reusable_investment", "spend_proposal"}
)

_LEDGER = "ledger"


class FinanceStore:
    """Canonical JSON under an explicit root. Append-only, no index, no database."""

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise FinanceStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()

    # -- writing -----------------------------------------------------------

    def put(self, record: Any) -> Path:
        """Write one record. A second write of the same id may not differ.

        Byte-identical is a no-op, so replaying an import is safe. Anything else
        raises `LedgerViolation` and names the fields that changed - the whole
        no-silent-overwrite guarantee for records that have an identity.
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
            raise LedgerViolation(
                f"{kind} {record_id!r} is already recorded with different content: "
                + ", ".join(self._differing_fields(existing, payload))
                + ". Financial history is append-only - record a correction that "
                "supersedes it rather than editing what was believed"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        if kind in _MONEY_KINDS:
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
        """Mirror one money-bearing record into the append-only event sequence."""
        entry = {
            "kind": kind,
            "record_id": record_id,
            "fingerprint": fingerprint(record.to_dict()),
            "recorded_on": _recorded_on(record),
        }
        return append_json_bytes(
            self.state_dir / _LEDGER, dumps(entry).encode("utf-8")
        )

    # -- reading -----------------------------------------------------------

    def get(self, kind: str, record_id: str) -> Any:
        directory, _id_field, decode = self._kind(kind)
        path = self.state_dir / directory / f"{record_id}.json"
        if not path.is_file():
            raise FinanceStoreError(
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

    def ledger(self) -> tuple[dict[str, Any], ...]:
        """Every money-bearing record in the order it was written."""
        root = self.state_dir / _LEDGER
        if not root.is_dir():
            return ()
        out: list[dict[str, Any]] = []
        for path in sorted_records(root):
            data = read_json(path)
            if not isinstance(data, dict):
                raise FinanceStoreError(f"{path}: a ledger entry is a JSON object")
            out.append(data)
        return tuple(out)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _kind_of(record: Any) -> str:
        kind = _KIND_BY_TYPE.get(type(record))
        if kind is None:
            raise FinanceStoreError(
                f"{type(record).__name__} is not a storable finance record. Known kinds: "
                + ", ".join(sorted(_KINDS))
            )
        return kind

    @staticmethod
    def _kind(kind: str) -> tuple[str, str, Callable[[dict[str, Any]], Any]]:
        try:
            return _KINDS[kind]
        except KeyError:
            raise FinanceStoreError(
                f"unknown record kind {kind!r}; known kinds: " + ", ".join(sorted(_KINDS))
            ) from None

    @staticmethod
    def _decode(
        path: Path, decode: Callable[[dict[str, Any]], T], kind: str, record_id: str
    ) -> T:
        try:
            data = read_json(path)
        except ValueError as exc:
            raise FinanceStoreError(f"{path}: not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise FinanceStoreError(f"{path}: a {kind} record is a JSON object")
        try:
            return decode(data)
        except (KeyError, ValueError, FinanceError) as exc:
            raise FinanceStoreError(
                f"{path}: {kind} {record_id!r} does not decode: {exc}"
            ) from exc


def _recorded_on(record: Any) -> str:
    """The day a record says it was written, for the ledger entry.

    Falls back through the date fields the money-bearing records actually use.
    A record with none of them is a programming error, not a data one, so the
    message names the type rather than inventing today's date.
    """
    for name in ("recorded_on", "proposed_on", "created_on"):
        value = getattr(record, name, None)
        if isinstance(value, dt.date):
            return value.isoformat()
    raise FinanceStoreError(
        f"{type(record).__name__} carries no recorded_on date, so it cannot be "
        "placed in the event ledger"
    )
