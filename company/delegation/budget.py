"""The four-level budget ladder, and what it refuses to assume.

```
company  -->  department  -->  program  -->  work_order
```

Each level names a ceiling in `company.finance.money.Money`, which is reused
rather than reinvented: it is exact decimal arithmetic that refuses to add two
currencies, and a budget model built on floats would eventually approve a spend
by rounding.

## Three invariants, and why each one is here

**A child may not exceed its parent.** Obvious, and not sufficient on its own.

**Siblings may not sum past their parent.** This is the one that actually
prevents unrestricted spend. Four departments each capped at the company
ceiling are four ways to spend the whole company budget, and every one of them
passes a per-line check. The ladder refuses to be constructed that way.

**An unknown ceiling is not an unlimited one.** A scope the ladder does not
carry produces `known=False`, and `company/delegation/authority.py` turns that
into ESCALATE. This mirrors `company.finance.economics`, where a margin with
nothing recorded is UNKNOWN rather than zero, and the integration gate probes
that property by name (`finance.unknown_is_not_zero`). The failure mode of a
missing number is no authority, never unchecked authority.

## Why consumption is passed in rather than read

`consumed` is a mapping the caller supplies. This module opens no store and
reads no usage ledger, so a budget answer is a pure function of (ladder,
consumption, request) and two runs over the same three produce the same answer.
The real consumption numbers live in `company/finance` and
`company/efficiency`, and a caller that wants them fetches them there — which
also means this module cannot be the thing that gets a spend wrong because it
read a stale total.

## The consumer-subscription objective

The master plan asks that the company function on roughly one ordinary consumer
AI subscription wherever practical, and `company/efficiency/profile.py` already
carries the `consumer` resource profile that work orders run under. The ladder
does not restate a number for that: the company ceiling is a policy value the
CEO sets, and `docs/company_os_executive_delegation.md` records that the seed
policy sets it at the consumer-subscription scale rather than at what the
company could afford.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from company.finance.errors import FinanceError
from company.finance.money import Money, total

from .common import assert_prose, assert_record_id
from .errors import DelegationError


class BudgetLevel(str, Enum):
    """The four rungs, coarsest first."""

    COMPANY = "company"
    DEPARTMENT = "department"
    PROGRAM = "program"
    WORK_ORDER = "work_order"


LEVEL_ORDER: tuple[BudgetLevel, ...] = (
    BudgetLevel.COMPANY,
    BudgetLevel.DEPARTMENT,
    BudgetLevel.PROGRAM,
    BudgetLevel.WORK_ORDER,
)


def parse_level(value: Any, field: str = "level") -> BudgetLevel:
    if isinstance(value, BudgetLevel):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be a budget level name, got {value!r}")
    try:
        return BudgetLevel(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LEVEL_ORDER)
        raise DelegationError(f"{field} must be one of: {allowed}") from exc


def _money(value: Any, field: str) -> Money:
    if isinstance(value, Money):
        amount = value
    elif isinstance(value, Mapping):
        try:
            amount = Money.from_dict(dict(value), field)
        except FinanceError as exc:
            raise DelegationError(f"{field}: {exc}") from exc
    else:
        raise DelegationError(
            f"{field} must be a Money value or an amount/currency object, got {value!r}"
        )
    if amount.is_negative:
        raise DelegationError(f"{field}: a ceiling is not negative ({amount})")
    return amount


@dataclass(frozen=True)
class BudgetScope:
    """One rung: what it covers, what it may spend, and what it hangs from."""

    scope_id: str
    level: BudgetLevel
    ceiling: Money
    parent_id: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "scope_id", assert_record_id(self.scope_id, "budget.scope_id")
        )
        object.__setattr__(self, "level", parse_level(self.level, "budget.level"))
        object.__setattr__(self, "ceiling", _money(self.ceiling, "budget.ceiling"))
        if self.level is BudgetLevel.COMPANY:
            if self.parent_id:
                raise DelegationError(
                    "the company budget is the root and hangs from nothing"
                )
        else:
            object.__setattr__(
                self, "parent_id", assert_record_id(self.parent_id, "budget.parent_id")
            )
            if self.parent_id == self.scope_id:
                raise DelegationError(f"budget {self.scope_id} is its own parent")
        object.__setattr__(
            self,
            "label",
            assert_prose(self.label, "budget.label") if self.label else self.scope_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "level": self.level.value,
            "ceiling": self.ceiling.to_dict(),
            "parent_id": self.parent_id,
            "label": self.label,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BudgetScope":
        if not isinstance(data, Mapping):
            raise DelegationError("a budget scope must be a mapping")
        return cls(
            scope_id=str(data.get("scope_id", "")),
            level=parse_level(data.get("level"), "budget.level"),
            ceiling=_money(data.get("ceiling"), "budget.ceiling"),
            parent_id=str(data.get("parent_id", "") or ""),
            label=str(data.get("label", "") or ""),
        )


@dataclass(frozen=True)
class BudgetFinding:
    """What the ladder says about one requested amount."""

    known: bool
    scope_id: str
    level: str
    within: bool
    requested: Money | None
    ceiling: Money | None
    consumed: Money | None
    remaining: Money | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "known": self.known,
            "scope_id": self.scope_id,
            "level": self.level,
            "within": self.within,
            "requested": self.requested.to_dict() if self.requested else None,
            "ceiling": self.ceiling.to_dict() if self.ceiling else None,
            "consumed": self.consumed.to_dict() if self.consumed else None,
            "remaining": self.remaining.to_dict() if self.remaining else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BudgetLadder:
    """Company down to work order, with the sibling sum enforced at every rung."""

    scopes: tuple[BudgetScope, ...]
    currency: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.scopes, tuple) or not self.scopes:
            raise DelegationError("a budget ladder needs at least a company scope")
        by_id: dict[str, BudgetScope] = {}
        for scope in self.scopes:
            if not isinstance(scope, BudgetScope):
                raise DelegationError("every entry in scopes must be a BudgetScope")
            if scope.scope_id in by_id:
                raise DelegationError(f"budget scope {scope.scope_id} is declared twice")
            by_id[scope.scope_id] = scope
        roots = [s for s in self.scopes if s.level is BudgetLevel.COMPANY]
        if len(roots) != 1:
            raise DelegationError(
                f"a ladder has exactly one company scope, found {len(roots)}. Two "
                "company budgets are two companies."
            )
        currency = roots[0].ceiling.currency
        object.__setattr__(self, "currency", currency)
        for scope in self.scopes:
            if scope.ceiling.currency != currency:
                raise DelegationError(
                    f"budget {scope.scope_id} is in {scope.ceiling.currency} and the "
                    f"company budget is in {currency}; this package will not pick an "
                    "exchange rate"
                )
            if scope.level is BudgetLevel.COMPANY:
                continue
            parent = by_id.get(scope.parent_id)
            if parent is None:
                raise DelegationError(
                    f"budget {scope.scope_id} hangs from {scope.parent_id!r}, which "
                    "the ladder does not carry"
                )
            expected = LEVEL_ORDER[LEVEL_ORDER.index(scope.level) - 1]
            if parent.level is not expected:
                raise DelegationError(
                    f"budget {scope.scope_id} is a {scope.level.value} whose parent "
                    f"{parent.scope_id} is a {parent.level.value}; a "
                    f"{scope.level.value} hangs from a {expected.value}"
                )
            if scope.ceiling > parent.ceiling:
                raise DelegationError(
                    f"budget {scope.scope_id} ({scope.ceiling}) exceeds its parent "
                    f"{parent.scope_id} ({parent.ceiling})"
                )
        object.__setattr__(self, "_by_id", by_id)
        for parent_id, parent in by_id.items():
            children = [s for s in self.scopes if s.parent_id == parent_id]
            if not children:
                continue
            summed = total([child.ceiling for child in children], currency)
            if summed > parent.ceiling:
                names = ", ".join(sorted(child.scope_id for child in children))
                raise DelegationError(
                    f"the children of {parent_id} sum to {summed}, above its "
                    f"{parent.ceiling} ceiling ({names}). Sibling ceilings that each "
                    "fit but together do not are four ways to spend one budget."
                )

    @property
    def _index(self) -> dict[str, BudgetScope]:
        return getattr(self, "_by_id")

    def scope_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._index))

    def scope(self, scope_id: str) -> BudgetScope | None:
        return self._index.get(scope_id)

    def lineage(self, scope_id: str) -> tuple[BudgetScope, ...]:
        """This scope and every scope above it, narrowest first."""
        out: list[BudgetScope] = []
        seen: set[str] = set()
        current = self._index.get(scope_id)
        while current is not None:
            if current.scope_id in seen:
                raise DelegationError(f"budget lineage loops at {current.scope_id}")
            seen.add(current.scope_id)
            out.append(current)
            current = self._index.get(current.parent_id) if current.parent_id else None
        return tuple(out)

    def check(
        self,
        scope_id: str,
        requested: Money | None,
        consumed: Mapping[str, Money] | None = None,
    ) -> BudgetFinding:
        """Whether `requested` fits at `scope_id` and at every scope above it.

        The tightest binding rung is the one reported, so a work order that fits
        its own line but would push its department over the edge is refused with
        the department named.
        """
        spent = dict(consumed or {})
        scope = self._index.get(scope_id)
        if scope is None:
            return BudgetFinding(
                known=False,
                scope_id=scope_id,
                level="",
                within=False,
                requested=requested,
                ceiling=None,
                consumed=None,
                remaining=None,
                reason=(
                    f"no budget ceiling is recorded for {scope_id!r}. An unknown "
                    "ceiling is not an unlimited one, so this escalates rather than "
                    "being approved against a number nobody set."
                ),
            )
        if requested is None:
            return BudgetFinding(
                known=False,
                scope_id=scope_id,
                level=scope.level.value,
                within=False,
                requested=None,
                ceiling=scope.ceiling,
                consumed=None,
                remaining=None,
                reason=(
                    "the request names no amount. A spend of unknown size cannot be "
                    "compared with a ceiling."
                ),
            )
        amount = _money(requested, "requested")
        if amount.currency != self.currency:
            return BudgetFinding(
                known=False,
                scope_id=scope_id,
                level=scope.level.value,
                within=False,
                requested=amount,
                ceiling=scope.ceiling,
                consumed=None,
                remaining=None,
                reason=(
                    f"the request is in {amount.currency} and the ladder is in "
                    f"{self.currency}; converting needs a dated rate this package "
                    "will not choose"
                ),
            )
        worst: BudgetFinding | None = None
        for rung in self.lineage(scope_id):
            used = spent.get(rung.scope_id, Money.zero(self.currency))
            used = _money(used, f"consumed[{rung.scope_id}]")
            if used.currency != self.currency:
                return BudgetFinding(
                    known=False,
                    scope_id=rung.scope_id,
                    level=rung.level.value,
                    within=False,
                    requested=amount,
                    ceiling=rung.ceiling,
                    consumed=None,
                    remaining=None,
                    reason=(
                        f"consumption for {rung.scope_id} is in {used.currency}, not "
                        f"{self.currency}"
                    ),
                )
            remaining = rung.ceiling - used
            within = (used + amount) <= rung.ceiling
            finding = BudgetFinding(
                known=True,
                scope_id=rung.scope_id,
                level=rung.level.value,
                within=within,
                requested=amount,
                ceiling=rung.ceiling,
                consumed=used,
                remaining=remaining,
                reason=(
                    f"{amount} against {rung.ceiling} at {rung.scope_id} with {used} "
                    f"already consumed, leaving {remaining}"
                    if within
                    else (
                        f"{amount} would take {rung.scope_id} to "
                        f"{used + amount}, above its {rung.ceiling} ceiling"
                    )
                ),
            )
            if not within:
                return finding
            if worst is None or (
                finding.remaining is not None
                and worst.remaining is not None
                and finding.remaining < worst.remaining
            ):
                worst = finding
        assert worst is not None  # lineage always yields at least the named scope
        return worst

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "scopes": [scope.to_dict() for scope in self.scopes],
        }

    @classmethod
    def from_mappings(cls, values: Any) -> "BudgetLadder":
        if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
            raise DelegationError("budget scopes must be a list")
        return cls(tuple(BudgetScope.from_mapping(item) for item in values))


def money_from_text(amount: Any, currency: str, field: str) -> Money:
    """Build Money from a policy file, where an amount is always text.

    A YAML number would have gone through a float on the way in, which is the
    loss `company.finance.money` exists to prevent, so the policy file writes
    `"25.00"` and this refuses anything that is not a decimal string.
    """
    if not isinstance(amount, str) or not amount.strip():
        raise DelegationError(
            f"{field} must be a decimal amount written as text, such as '25.00'. A "
            "YAML number reaches this code as a float and a budget is not a float."
        )
    try:
        value = Decimal(amount.strip())
    except Exception as exc:  # noqa: BLE001 - Decimal raises InvalidOperation
        raise DelegationError(f"{field}: {amount!r} is not a decimal amount") from exc
    try:
        return Money(value, currency)
    except FinanceError as exc:
        raise DelegationError(f"{field}: {exc}") from exc


__all__ = [
    "LEVEL_ORDER",
    "BudgetFinding",
    "BudgetLadder",
    "BudgetLevel",
    "BudgetScope",
    "money_from_text",
    "parse_level",
]
