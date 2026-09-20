"""Knowledge decays at different rates, and the rate is a property of the claim.

Constitution rule 15 says a canonical fact is stored once and retrieved. That
only pays off if retrieval can tell a claim that is still true from one that
merely used to be. A store with no decay model turns into a store nobody
trusts, which is the same as no store at all - the next session re-derives
everything and the retrieval class (B) never fires.

## The four classes

    PERMANENT       An invariant. Newton's second law under a similarity
                    transform; the constitution's reserved decisions. Never
                    stale, no recheck date, and the class is a claim in itself -
                    marking something permanent that is not is the expensive
                    mistake here.
    SLOW_CHANGING   True until the surrounding system changes: an architecture
                    boundary, a physics constant this repository measured, a
                    module contract. One year.
    TIME_SENSITIVE  True about a moving world: a platform's behaviour, an
                    audience pattern, a provider's pricing or limits. Thirty
                    days.
    EXPERIMENTAL    True of one run, on one branch, under conditions that were
                    not held constant twice. Two weeks, and it should be either
                    promoted or dropped long before that.

The intervals are defaults, not measurements. A record may set `recheck_on`
explicitly and that value wins; the defaults exist so that a record which says
nothing still has a date, because a claim with no recheck date is a claim that
is never rechecked.

## Why `today` is always an argument

Every function here takes the date rather than reading the clock. Staleness is
then a pure function, the tests do not need a fake clock, and two sessions
auditing the same store on the same day get the same answer. `date.today()`
appears once, at the store boundary, where it belongs.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum


class Freshness(Enum):
    PERMANENT = "permanent"
    SLOW_CHANGING = "slow_changing"
    TIME_SENSITIVE = "time_sensitive"
    EXPERIMENTAL = "experimental"


DEFAULT_RECHECK_DAYS: dict[Freshness, int | None] = {
    Freshness.PERMANENT: None,
    Freshness.SLOW_CHANGING: 365,
    Freshness.TIME_SENSITIVE: 30,
    Freshness.EXPERIMENTAL: 14,
}

REVALIDATION_CLASSES: frozenset[Freshness] = frozenset(
    {Freshness.TIME_SENSITIVE, Freshness.EXPERIMENTAL}
)
"""Classes whose records may be flagged for revalidation before they expire."""


def default_recheck_on(freshness: Freshness, created: dt.date) -> dt.date | None:
    """The recheck date a record gets when it does not set one itself."""
    days = DEFAULT_RECHECK_DAYS[freshness]
    return None if days is None else created + dt.timedelta(days=days)


def is_stale(
    freshness: Freshness,
    created: dt.date,
    recheck_on: dt.date | None,
    today: dt.date,
) -> bool:
    """True when the claim is past its recheck date. Permanent is never stale."""
    if freshness is Freshness.PERMANENT:
        return False
    due = recheck_on if recheck_on is not None else default_recheck_on(freshness, created)
    if due is None:
        return False
    return today > due


def days_until_recheck(
    freshness: Freshness,
    created: dt.date,
    recheck_on: dt.date | None,
    today: dt.date,
) -> int | None:
    """Days remaining before a recheck is due; negative once overdue.

    `None` for permanent claims, which have no due date to count towards.
    """
    if freshness is Freshness.PERMANENT:
        return None
    due = recheck_on if recheck_on is not None else default_recheck_on(freshness, created)
    if due is None:
        return None
    return (due - today).days
