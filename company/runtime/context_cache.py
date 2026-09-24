"""Read-once repository evidence: reuse what was already read, never what changed.

A task reads the same things repeatedly - the repository map, a symbol span, a
test anchor, a capsule's metadata, an authority record - and each re-read costs
the same as the first. This module holds what a task has already resolved so it
can be handed back instead of read again.

## Why identity, not recency

The tempting cache is keyed by path and invalidated by a timestamp. That cache
is wrong on exactly the runs that matter: a file rewritten within the same
second, a worktree switched under a session, a `git checkout` that restores an
mtime. So the key is `(kind, source, symbol, span)` and the *validator* is the
content digest of the source. A caller must supply the digest it observed now;
if it differs from the stored one, the entry is evicted and the answer is a
miss.

**A cache miss is preferable to stale evidence.** Everything here is arranged
so that the failure mode is "read it again" rather than "answer from something
that has changed underneath". There is deliberately no `force`, no grace period
and no "probably still fine" path.

## Why the stats are part of the design

`CacheStats` separates `misses` from `stale_rejections`. They cost the same at
run time and mean opposite things: misses are a cache that has not warmed up,
stale rejections are a cache that would have been *wrong*. A single hit-rate
number hides the second, and the second is the one that tells you the digest
check is earning its place.

## What this module refuses to do

It does not read files. A cache that could fetch its own misses would decide
what a session is allowed to read, and read authority lives in
`company/runtime/authority.py`. `read_once` takes a loader from the caller and
calls it only on a miss, so the authority check stays where the caller put it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable

from .context_units import ContextUnit
from .errors import LifecycleError


class CacheOutcome(Enum):
    """What a lookup did. `STALE` never returns a unit."""

    HIT = "hit"
    MISS = "miss"
    STALE = "stale"


@dataclass(frozen=True)
class CacheLookup:
    """One lookup, its outcome, and the unit if there was one to give."""

    key: str
    outcome: CacheOutcome
    unit: ContextUnit | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.outcome is CacheOutcome.HIT and self.unit is None:
            raise LifecycleError("a cache hit must carry the unit it hit")
        if self.outcome is not CacheOutcome.HIT and self.unit is not None:
            raise LifecycleError(
                f"{self.key}: a {self.outcome.value} lookup must not carry a unit; "
                "returning content on a non-hit is how stale evidence travels"
            )

    @property
    def reusable(self) -> bool:
        return self.outcome is CacheOutcome.HIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "outcome": self.outcome.value,
            "unit_id": self.unit.unit_id() if self.unit is not None else "",
            "detail": self.detail,
        }


@dataclass
class CacheStats:
    """What the cache did over one task. Counts only; no clock, no identity."""

    hits: int = 0
    misses: int = 0
    stale_rejections: int = 0
    stores: int = 0
    loads: int = 0
    chars_reused: int = 0
    canonical_chars_reused: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses + self.stale_rejections

    @property
    def reuse_ratio(self) -> float:
        """Hits over lookups. Zero lookups is 0.0, not a division by zero."""
        return 0.0 if self.lookups == 0 else self.hits / self.lookups

    @property
    def reads_avoided(self) -> int:
        """Loader calls a warm cache saved. Equal to hits, named for the reader."""
        return self.hits

    def to_dict(self) -> dict[str, Any]:
        return {
            **to_jsonable(self),
            "lookups": self.lookups,
            "reads_avoided": self.reads_avoided,
            "reuse_ratio": round(self.reuse_ratio, 6),
        }


@dataclass
class ContextCache:
    """Units already resolved during one task, reusable only while unchanged.

    Scope is one task. It is not persisted, not shared between work orders and
    not keyed by anything a second task could collide with, because the point
    is to stop one session reading the same span nine times - not to build a
    cross-session store whose invalidation nobody owns.
    """

    entries: dict[str, ContextUnit] = field(default_factory=dict)
    stats: CacheStats = field(default_factory=CacheStats)

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, key: object) -> bool:
        return key in self.entries

    def lookup(self, key: str, observed_digest: str) -> CacheLookup:
        """Ask for a unit, proving what the source says *now*.

        `observed_digest` is not optional and has no default. A caller that
        could omit it would be asking the cache to guess, and the guess would
        be "still fine", which is the one answer this module must not give.
        """
        if not isinstance(key, str) or not key:
            raise LifecycleError("a cache key is a non-empty string")
        if not isinstance(observed_digest, str) or len(observed_digest) != 64:
            raise LifecycleError(
                f"{key}: a lookup must carry the full SHA-256 of the source as it "
                "is now; without it the cache cannot tell reuse from staleness"
            )
        stored = self.entries.get(key)
        if stored is None:
            self.stats.misses += 1
            return CacheLookup(key=key, outcome=CacheOutcome.MISS, detail="not cached")
        if stored.content_digest != observed_digest:
            del self.entries[key]
            self.stats.stale_rejections += 1
            return CacheLookup(
                key=key,
                outcome=CacheOutcome.STALE,
                detail=(
                    f"source changed since it was cached "
                    f"(cached {stored.content_digest[:16]}, now "
                    f"{observed_digest[:16]}); evicted"
                ),
            )
        self.stats.hits += 1
        self.stats.chars_reused += stored.chars()
        self.stats.canonical_chars_reused += stored.body.full_chars
        return CacheLookup(key=key, outcome=CacheOutcome.HIT, unit=stored, detail="reused")

    def put(self, unit: ContextUnit) -> ContextUnit:
        """Store a unit under its own key. Refuses an authority change.

        Replacing a `contract` unit with an `observed` one at the same key -
        or the reverse - would let the cache decide what binds the session.
        It does not. Re-storing under a different authority is a programming
        error, and is raised as one.
        """
        if not isinstance(unit, ContextUnit):
            raise LifecycleError("a context cache stores ContextUnit values")
        key = unit.key()
        stored = self.entries.get(key)
        if stored is not None and stored.authority is not unit.authority:
            raise LifecycleError(
                f"{key}: cached as {stored.authority.value} and re-stored as "
                f"{unit.authority.value}. Reuse may not change what a unit is "
                "allowed to decide."
            )
        self.entries[key] = unit
        self.stats.stores += 1
        return unit

    def read_once(
        self,
        key: str,
        observed_digest: str,
        loader: Callable[[], ContextUnit],
    ) -> tuple[ContextUnit, CacheLookup]:
        """Return the cached unit, or call `loader` exactly once and cache it.

        The loader is the caller's read, with the caller's authority check
        already applied. This function never opens a file.
        """
        found = self.lookup(key, observed_digest)
        if found.reusable and found.unit is not None:
            return found.unit, found
        unit = loader()
        self.stats.loads += 1
        if unit.key() != key:
            raise LifecycleError(
                f"read_once was asked for {key!r} and the loader returned "
                f"{unit.key()!r}; a cache that stores one thing under another "
                "thing's name is worse than no cache"
            )
        if unit.content_digest != observed_digest:
            raise LifecycleError(
                f"{key}: the loader read content with digest "
                f"{unit.content_digest[:16]} while the caller observed "
                f"{observed_digest[:16]}. The source changed mid-read; nothing is "
                "cached."
            )
        self.put(unit)
        return unit, found

    def invalidate(self, key: str) -> bool:
        return self.entries.pop(key, None) is not None

    def clear(self) -> None:
        self.entries.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": sorted(self.entries),
            "stats": self.stats.to_dict(),
        }


__all__ = [
    "CacheLookup",
    "CacheOutcome",
    "CacheStats",
    "ContextCache",
]
