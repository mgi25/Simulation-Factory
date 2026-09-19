"""Money: a Decimal and a currency code, and nothing that can round in secret.

## Why not float

`0.1 + 0.2` is `0.30000000000000004`, and a company that adds a thousand render
costs in binary floating point gets a total that is wrong by an amount nobody
can explain and everybody can argue about. `Decimal` is exact for the values
money actually takes, so the arithmetic below is exact too.

The guard is not "prefer Decimal", it is `float` being refused at construction.
A float that reaches `Money` has already lost precision, and accepting it would
launder the loss into a record that looks authoritative. `Money("0.1")` is
right, `Money(Decimal("0.1"))` is right, and `Money(0.1)` raises.

## Why the currency travels with the amount

Because the failure it prevents is silent. Adding 100 EUR to 100 USD and
getting 200 of something is not an error a reviewer catches by reading a total.
So the currency is part of the value, every binary operation checks it, and
`CurrencyMismatch` has its own type. Conversion is deliberately absent: it needs
an exchange-rate observation with a date and a source, which is a record this
package does not have and will not invent.

## Canonical form, and why equality and serialization agree

`Decimal("1.50")` and `Decimal("1.5")` are equal and serialize differently, and
a store that writes both has two files for one value. So every `Money`
normalizes its amount on the way in: trailing zeros dropped, exponent notation
expanded. `Money("100.00") == Money("1E+2")`, both write `"100"`, and a
fingerprint over a record is stable across the two ways of typing it.

Precision is otherwise untouched. A token price of `0.000003` per token is a
real rate and quantizing it to two decimals on arrival would make it zero, so
nothing here rounds until a caller asks for it by name - `quantize`, or the
explicit `quantum` argument to `split`.

## Splitting is exact, or it is not a split

`split` exists because section 7 needs a 20 EUR subscription across three
projects, and 6.67 x 3 is 20.01. Largest-remainder distribution gives parts
that sum to exactly the original: the same input always produces the same
parts, and the remainder lands on the largest fractional shares first, ties
broken by position so two runs never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_EVEN
import re
from typing import Any, Iterable, Sequence

from .errors import CurrencyMismatch, FinanceError

# ISO 4217 shape, not an ISO 4217 list. A closed list would be a table this
# package has to maintain and would reject a currency the company really used;
# the shape catches the failure that actually happens, which is a label like
# "euros" or a bare symbol arriving where a code belongs.
CURRENCY_CODE = re.compile(r"[A-Z]{3}")

# The default minor unit. Two decimals is what EUR and USD use and what a
# caller means by "cents" when they do not say. It is an argument everywhere it
# is used, never a constant baked into arithmetic, because a zero-decimal
# currency is not an error and this package must not turn it into one.
DEFAULT_QUANTUM = Decimal("0.01")


def assert_currency(value: Any, field: str = "currency") -> str:
    """Return `value` if it is a three-letter uppercase currency code, else raise."""
    if not isinstance(value, str) or not CURRENCY_CODE.fullmatch(value):
        raise FinanceError(
            f"{field}: {value!r} is not a currency code. Money carries a three-letter "
            "uppercase code such as EUR or USD, never a symbol or a name"
        )
    return value


def _canonical(value: Decimal) -> Decimal:
    """Normalize so that equal amounts have one spelling, without rounding.

    `normalize()` alone turns `Decimal("100")` into `Decimal("1E+2")`, which
    serializes as `1E+2` and reads as a bug. Re-quantizing the positive
    exponent away restores the plain form and changes no value.
    """
    normalized = value.normalize()
    if normalized == 0:
        return Decimal(0)
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        normalized = normalized.quantize(Decimal(1))
    return normalized


def as_decimal(value: Any, field: str = "amount") -> Decimal:
    """Coerce to Decimal from Decimal, int or str. A float is refused.

    `bool` is refused alongside the integers because `Money(True)` is never what
    a caller meant, and Python would otherwise make it one unit.
    """
    if isinstance(value, bool):
        raise FinanceError(f"{field}: a boolean is not an amount, got {value!r}")
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise FinanceError(f"{field}: an amount is required, got an empty string")
        try:
            candidate = Decimal(text)
        except InvalidOperation:
            raise FinanceError(f"{field}: {value!r} is not a decimal number") from None
    elif isinstance(value, float):
        raise FinanceError(
            f"{field}: {value!r} is a float. Money is Decimal-exact; pass the digits "
            "as a string so nothing is lost before it arrives"
        )
    else:
        raise FinanceError(
            f"{field}: expected a Decimal, int or decimal string, got "
            f"{type(value).__name__}"
        )
    if not candidate.is_finite():
        raise FinanceError(f"{field}: {value!r} is not a finite amount")
    return _canonical(candidate)


@dataclass(frozen=True, order=False)
class Money:
    """An exact amount in one named currency. Immutable, comparable, hashable."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", assert_currency(self.currency))
        object.__setattr__(self, "amount", as_decimal(self.amount))

    # -- construction ------------------------------------------------------

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal(0), currency)

    @classmethod
    def from_dict(cls, data: Any, field: str = "money") -> Money:
        """Decode an amount/currency object.

        The amount is read as a string on purpose: a JSON number would have gone
        through a float on the way in, which is the loss this type exists to
        prevent.
        """
        if not isinstance(data, dict):
            raise FinanceError(
                f"{field}: expected an amount/currency object, got {data!r}"
            )
        try:
            return cls(amount=data["amount"], currency=data["currency"])
        except KeyError as exc:
            raise FinanceError(f"{field}: missing {exc.args[0]!r}") from None

    def to_dict(self) -> dict[str, str]:
        """Canonical JSON form. The amount is text, so no float ever sees it."""
        return {"amount": self.text, "currency": self.currency}

    # -- reading -----------------------------------------------------------

    @property
    def text(self) -> str:
        """The amount in plain decimal notation, never exponent notation."""
        return format(self.amount, "f")

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def __str__(self) -> str:
        return f"{self.text} {self.currency}"

    def __repr__(self) -> str:
        return f"Money({self.text!r}, {self.currency!r})"

    # -- arithmetic --------------------------------------------------------

    def _same_currency(self, other: Money, operation: str) -> None:
        if not isinstance(other, Money):
            raise FinanceError(f"cannot {operation} Money and {type(other).__name__}")
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"cannot {operation} {self.currency} and {other.currency}. Convert with "
                "an explicit dated exchange-rate observation, or keep the two apart - "
                "this package will not pick a rate for you"
            )

    def __add__(self, other: Money) -> Money:
        self._same_currency(other, "add")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other, "subtract")
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    def __mul__(self, factor: Any) -> Money:
        """Scale by a quantity. Money times Money is not a quantity of anything."""
        if isinstance(factor, Money):
            raise FinanceError(
                "Money * Money has no meaning. Multiply an amount by a quantity - "
                "tokens, minutes, requests - not by another amount"
            )
        return Money(self.amount * as_decimal(factor, "factor"), self.currency)

    __rmul__ = __mul__

    def divided_by(self, divisor: Any) -> Money:
        """Exact division by a quantity, before any rounding.

        Named rather than `__truediv__` because `total / count` reads like it
        produces a shareable amount and it does not: the parts will not sum back
        to the total. `split` is the operation for that.
        """
        value = as_decimal(divisor, "divisor")
        if value == 0:
            raise FinanceError("cannot divide an amount by zero")
        return Money(self.amount / value, self.currency)

    def ratio_to(self, other: Money) -> Decimal:
        """This amount as a fraction of `other`. Same currency, non-zero denominator."""
        self._same_currency(other, "compare")
        if other.amount == 0:
            raise FinanceError("cannot express an amount as a fraction of zero")
        return self.amount / other.amount

    def quantize(self, quantum: Any = DEFAULT_QUANTUM) -> Money:
        """Round to an explicit quantum, banker's rounding. Never implicit."""
        return Money(
            self.amount.quantize(
                as_decimal(quantum, "quantum"), rounding=ROUND_HALF_EVEN
            ),
            self.currency,
        )

    # -- comparison --------------------------------------------------------

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other, "compare")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_currency(other, "compare")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._same_currency(other, "compare")
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._same_currency(other, "compare")
        return self.amount >= other.amount

    # -- allocation --------------------------------------------------------

    def split(
        self, weights: Sequence[Any], *, quantum: Any = DEFAULT_QUANTUM
    ) -> tuple[Money, ...]:
        """Divide into parts proportional to `weights` that sum to exactly this.

        Largest-remainder: every part is floored to `quantum`, then the leftover
        is handed out one quantum at a time to the parts with the largest
        discarded fraction, ties going to the earlier position. Deterministic,
        exact, and the reason a 20.00 EUR subscription across three projects
        does not become 20.01.
        """
        if not weights:
            raise FinanceError(
                "split needs at least one weight; an empty split is a no-op"
            )
        values = [
            as_decimal(weight, f"weight[{index}]")
            for index, weight in enumerate(weights)
        ]
        if any(value < 0 for value in values):
            raise FinanceError("split weights cannot be negative")
        total_weight = sum(values, Decimal(0))
        if total_weight == 0:
            raise FinanceError(
                "split weights sum to zero, so there is no basis for a share. Leave the "
                "cost unallocated rather than inventing one"
            )
        step = as_decimal(quantum, "quantum")
        if step <= 0:
            raise FinanceError("split quantum must be positive")
        units = (self.amount / step).to_integral_value(rounding=ROUND_HALF_EVEN)
        exact = [units * value / total_weight for value in values]
        floors = [part.to_integral_value(rounding=ROUND_FLOOR) for part in exact]
        remainder = int(units - sum(floors, Decimal(0)))
        order = sorted(
            range(len(values)),
            key=lambda index: (-(exact[index] - floors[index]), index),
        )
        # `remainder` is never negative: ROUND_FLOOR rounds toward minus
        # infinity, so the floors always sum to at most `units`, for a negative
        # total as much as a positive one.
        for position in range(remainder):
            floors[order[position % len(order)]] += 1
        return tuple(Money(floor * step, self.currency) for floor in floors)


def total(amounts: Iterable[Money], currency: str | None = None) -> Money:
    """Sum amounts that share one currency.

    `currency` is required for a possibly-empty iterable, because the zero of
    no currency is not a number this package is willing to make up.
    """
    running: Money | None = None
    for amount in amounts:
        if not isinstance(amount, Money):
            raise FinanceError(
                f"total() takes Money values, got {type(amount).__name__}"
            )
        running = amount if running is None else running + amount
    if running is None:
        if currency is None:
            raise FinanceError(
                "total() of nothing needs an explicit currency; there is no "
                "currency-free zero"
            )
        return Money.zero(currency)
    if currency is not None and running.currency != currency:
        raise CurrencyMismatch(
            f"total() was asked for {currency} and summed {running.currency}"
        )
    return running
