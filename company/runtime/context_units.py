"""Cache-stable, typed context units: what a session is given, and on what authority.

`context_assembly` decides *which* references a task gets. This module decides
what one of those references looks like once it has been resolved into prompt
material, and it exists because a reference that has been read is a different
object from a reference that has only been named: it has content, the content
has a digest, and the digest is the only thing that makes reuse safe.

## The three questions a unit answers

**What is this?** `kind` - a capsule contract, a symbol span, a whole file, a
test anchor, a repository map, an authority record, a piece of evidence.

**Where did it come from?** `source` plus `span` plus `content_digest`. The
digest is over the canonical source bytes, not over the rendered body, so two
units that render differently (one compressed, one not) still agree about
whether the file underneath them has changed.

**On what authority?** `authority`, and this is the field that does the real
work - see below.

## Why authority is a field and not a comment

The brief for this package says: *learning must not create authority*. A
session that reads a file learns something; that learning is `OBSERVED`. A
session that infers a pattern across files learns something weaker; that is
`DERIVED`. Neither may become the thing that *binds* - the capsule contract,
the permission record, the work order - which is `CONTRACT`.

So `authority` is set where the unit is built, `binding` is a property derived
from it rather than a settable flag, and nothing in this module or
`context_cache` can raise a unit's authority. `compress` and `expand` carry it
through unchanged and assert that they did; `ContextBundle.contract_units()`
is how a consumer asks for the binding subset, so that "what constrains me" is
a filter over typed data instead of a judgement made at the reading end.

## Why cache stability is measured and not asserted

A prompt prefix is only reused by a provider cache while its bytes are
identical. Every plausible way to lose that is a value that is *true* but
*incidental*: today's date, an absolute checkout path, a session id, the order
a dict happened to iterate in. `ContextBundle.render()` therefore sorts, uses
repository-relative sources only, and carries no clock - and
`cache_stability()` returns the measured shared-prefix ratio between two
renderings so a test can fail on a regression rather than a reviewer having to
notice one.

## Why compression keeps a pointer rather than a summary

A summary cannot be checked. An elision can: `CompressedBody` keeps a head and
a tail verbatim, names the exact line range it removed, and carries the digest
of the whole. `expand()` puts the original back from the canonical source and
refuses any source whose digest does not match, so the compact form is either
reversible or loudly wrong - never quietly approximate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import fingerprint, to_jsonable

from .errors import LifecycleError


CONTEXT_UNIT_VERSION = 1

# How much of a body survives compression, in lines. Chosen so that a Python
# function's signature, docstring opening and return statement are all still
# visible - which is what a reader needs to decide whether to expand it.
DEFAULT_HEAD_LINES = 12
DEFAULT_TAIL_LINES = 4

# A rendered unit body longer than this is a candidate for compression. It is a
# budget, not a measurement: it is roughly the point at which one unit starts
# to crowd out the rest of a bundle.
DEFAULT_COMPRESSION_THRESHOLD_CHARS = 1200

_MAX_REASON_CHARS = 400
_ELISION = "... {count} line(s) elided: {source}#{start}-{end} sha256:{digest} ..."


class UnitKind(Enum):
    """What a context unit holds. The kinds a session is actually given."""

    CAPSULE = "capsule"
    FILE = "file"
    SYMBOL_SPAN = "symbol_span"
    TEST_ANCHOR = "test_anchor"
    REPO_MAP = "repo_map"
    AUTHORITY = "authority"
    EVIDENCE = "evidence"


class UnitAuthority(Enum):
    """How much a unit is allowed to decide.

    `CONTRACT` binds: a capsule, a permission record, a work order's authority
    envelope. `OBSERVED` is what the repository or a recorded run actually
    says. `DERIVED` is inferred - a ranking, a guess at relevance, a pattern
    across files - and binds nothing.
    """

    CONTRACT = "contract"
    OBSERVED = "observed"
    DERIVED = "derived"


class CompressionKind(Enum):
    """How a body was shortened, if it was."""

    NONE = "none"
    ELIDED = "elided"


# The order a bundle lays units out in, most stable first. It is declared here
# rather than falling out of `sorted()` because alphabetical order is an
# accident and prefix reuse is not: a provider cache reuses a *prefix*, so
# whatever sits at the top must be the material that changes least often, and
# a newly added unit should land as late as its nature allows.
#
# This was measured, not assumed. With the units sorted by `kind:source`, the
# string "evidence:" falls between "capsule:" and "file:", so appending one
# piece of evidence to a bundle moved everything after it and dropped the
# shared prefix from 100% to 19.4% - see
# docs/validation/company_os_p6a/measure_context_efficiency.py.
_AUTHORITY_ORDER: dict[UnitAuthority, int] = {
    # Contracts change on a review cycle; derived material changes per task.
    UnitAuthority.CONTRACT: 0,
    UnitAuthority.OBSERVED: 1,
    UnitAuthority.DERIVED: 2,
}
_KIND_ORDER: dict[UnitKind, int] = {
    UnitKind.CAPSULE: 0,
    UnitKind.AUTHORITY: 1,
    UnitKind.REPO_MAP: 2,
    UnitKind.FILE: 3,
    UnitKind.SYMBOL_SPAN: 4,
    UnitKind.TEST_ANCHOR: 5,
    UnitKind.EVIDENCE: 6,
}


def _lines(text: str) -> list[str]:
    """Split on newlines, and on nothing else.

    `str.splitlines()` also splits on form feed, vertical tab, the file/group/
    record separators, NEL and the Unicode line/paragraph separators. A source
    file containing any of those would then be numbered differently here than
    by an editor, `sed -n`, a pytest node id or a GitHub permalink - and the
    line range in the elision marker is the entire reason a compressed body is
    checkable rather than a summary. A pointer a reader cannot follow is worse
    than no pointer.

    Splitting on "\n" alone also leaves a "\r" at the end of each line of CRLF
    text, so the head and tail stay verbatim slices of the original.
    """
    return text.split("\n")


def content_digest(text: str) -> str:
    """The canonical digest of source text: full SHA-256 over its UTF-8 bytes.

    Full length rather than the 16-character `fingerprint`, because this value
    decides whether cached evidence may be reused, and a truncated hash is a
    smaller thing to have to be confident about than a whole one.
    """
    if not isinstance(text, str):
        raise LifecycleError("content_digest takes text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompressedBody:
    """A bounded body that can be put back, or that says why it cannot be.

    Never a summary. `head` and `tail` are verbatim slices of the original and
    `elided_span` is the exact 1-based inclusive line range between them, so
    `expand()` is arithmetic rather than interpretation.
    """

    source: str
    kind: CompressionKind
    head: str
    tail: str
    elided_span: tuple[int, int] | None
    full_digest: str
    full_lines: int
    full_chars: int

    def __post_init__(self) -> None:
        assert_reference(self.source, "compressed body source")
        if not isinstance(self.kind, CompressionKind):
            raise LifecycleError("compressed body kind must be a CompressionKind")
        if len(self.full_digest) != 64:
            raise LifecycleError(
                "a compressed body carries the full SHA-256 of its canonical source; "
                f"{self.full_digest!r} is not one"
            )
        if self.kind is CompressionKind.NONE and self.elided_span is not None:
            raise LifecycleError("an uncompressed body elides nothing")
        if self.kind is CompressionKind.ELIDED:
            if self.elided_span is None:
                raise LifecycleError(
                    "an elided body must name the line range it removed; a body that "
                    "cannot say what is missing cannot be reconstructed"
                )
            start, end = self.elided_span
            if start < 1 or end < start or end > self.full_lines:
                raise LifecycleError(
                    f"{self.source}: elided span {self.elided_span!r} is not inside "
                    f"1-{self.full_lines}"
                )

    @property
    def self_contained(self) -> bool:
        """True when the body is whole and needs no source to be read.

        The honest distinction, and it is falsifiable. An `ELIDED` body is
        *restorable*, not self-contained: `expand()` needs the canonical bytes
        and verifies them against `full_digest` rather than inventing the
        middle. For a repository file at a known commit those bytes can always
        be fetched again; for a synthesised repo map or a transient blob they
        may not be, and then the elided middle is gone for good. Compress
        those with a threshold that declines, or not at all.
        """
        return self.kind is CompressionKind.NONE

    @property
    def elided_lines(self) -> int:
        if self.elided_span is None:
            return 0
        start, end = self.elided_span
        return end - start + 1

    def render(self) -> str:
        """The compact text, with the elision marker carrying the pointer."""
        if self.kind is CompressionKind.NONE:
            return self.head
        start, end = self.elided_span  # type: ignore[misc]
        marker = _ELISION.format(
            count=self.elided_lines,
            source=self.source,
            start=start,
            end=end,
            digest=self.full_digest[:16],
        )
        parts = [self.head, marker]
        if self.tail:
            parts.append(self.tail)
        return "\n".join(parts)

    def chars(self) -> int:
        return len(self.render())

    def saved_chars(self) -> int:
        return max(0, self.full_chars - self.chars())

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def compress(
    text: str,
    *,
    source: str,
    head_lines: int = DEFAULT_HEAD_LINES,
    tail_lines: int = DEFAULT_TAIL_LINES,
    threshold_chars: int = DEFAULT_COMPRESSION_THRESHOLD_CHARS,
) -> CompressedBody:
    """Shorten `text` reversibly, or decline to shorten it.

    Declines - returns `CompressionKind.NONE` - when the text is under the
    threshold, or when keeping the head and tail would keep everything anyway.
    Declining is the safe direction: the caller gets the whole body and a
    digest, which is what it would have had without this module.
    """
    if not isinstance(text, str):
        raise LifecycleError("compress takes text")
    assert_reference(source, "compress source")
    for name, value in (("head_lines", head_lines), ("tail_lines", tail_lines)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise LifecycleError(f"compress {name} must be a non-negative integer")
    if head_lines + tail_lines == 0:
        raise LifecycleError(
            "compress would keep nothing verbatim; an elision with no anchor is a "
            "summary, and a summary cannot be checked"
        )

    lines = _lines(text)
    digest = content_digest(text)
    whole = CompressedBody(
        source=source,
        kind=CompressionKind.NONE,
        head=text,
        tail="",
        elided_span=None,
        full_digest=digest,
        full_lines=len(lines),
        full_chars=len(text),
    )
    if len(text) <= threshold_chars or len(lines) <= head_lines + tail_lines:
        return whole

    head = "\n".join(lines[:head_lines])
    tail = "\n".join(lines[len(lines) - tail_lines :]) if tail_lines else ""
    assert text.startswith(head), "the head must be a verbatim slice"
    elided = CompressedBody(
        source=source,
        kind=CompressionKind.ELIDED,
        head=head,
        tail=tail,
        elided_span=(head_lines + 1, len(lines) - tail_lines),
        full_digest=digest,
        full_lines=len(lines),
        full_chars=len(text),
    )
    # A compact form that is not smaller is a compact form with only costs.
    return elided if elided.chars() < whole.chars() else whole


def expand(body: CompressedBody, canonical_text: str) -> str:
    """Reconstruct the original text from the canonical source, or refuse.

    The digest check is the point. A body is only reversible against the exact
    bytes it was made from; handed a changed file, this raises instead of
    returning a plausible reconstruction, because a silently wrong expansion is
    worse than no expansion at all.
    """
    if not isinstance(body, CompressedBody):
        raise LifecycleError("expand takes a CompressedBody")
    observed = content_digest(canonical_text)
    if observed != body.full_digest:
        raise LifecycleError(
            f"{body.source}: the canonical source has changed since it was "
            f"compressed (digest {observed[:16]}, expected "
            f"{body.full_digest[:16]}). Re-read the source; a compressed body is "
            "reversible only against the bytes it was made from."
        )
    return canonical_text


@dataclass(frozen=True)
class ContextUnit:
    """One resolved, typed, digest-identified piece of a session's context."""

    kind: UnitKind
    source: str
    reason: str
    authority: UnitAuthority
    body: CompressedBody
    span: tuple[int, int] | None = None
    symbol: str = ""
    freshness: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, UnitKind):
            raise LifecycleError("context unit kind must be a UnitKind")
        if not isinstance(self.authority, UnitAuthority):
            raise LifecycleError("context unit authority must be a UnitAuthority")
        if not isinstance(self.body, CompressedBody):
            raise LifecycleError("context unit body must be a CompressedBody")
        assert_reference(self.source, "context unit source")
        assert_text(self.reason, f"{self.source} reason")
        if len(self.reason) > _MAX_REASON_CHARS:
            raise LifecycleError(
                f"{self.source}: a unit's reason is a phrase, not a body "
                f"({len(self.reason)} characters)"
            )
        if self.body.source != self.source:
            raise LifecycleError(
                f"context unit {self.source!r} carries a body from "
                f"{self.body.source!r}; a unit and its body name one source"
            )
        if self.span is not None:
            start, end = self.span
            if start < 1 or end < start:
                raise LifecycleError(f"{self.source}: invalid line span {self.span!r}")
        if self.symbol:
            assert_reference(self.symbol, f"{self.source} symbol")

    # -- identity ---------------------------------------------------------

    @property
    def content_digest(self) -> str:
        """The digest of the canonical source this unit was built from."""
        return self.body.full_digest

    @property
    def binding(self) -> bool:
        """Does this unit constrain what the session may do?

        A property, never a field. There is no call anywhere in this package
        that turns a `DERIVED` or `OBSERVED` unit into a binding one: what a
        session learns cannot become what authorises it.
        """
        return self.authority is UnitAuthority.CONTRACT

    def identity(self) -> dict[str, Any]:
        """Exactly the fields a cache may key on. No clock, no path, no order."""
        return {
            "version": CONTEXT_UNIT_VERSION,
            "kind": self.kind.value,
            "source": self.source,
            "span": list(self.span) if self.span else None,
            "symbol": self.symbol,
            "content_digest": self.content_digest,
            "authority": self.authority.value,
            "compression": self.body.kind.value,
            # The span too, not only the kind: two elisions of one file made
            # with different head/tail budgets are different material and must
            # not share an id.
            "elided_span": (
                list(self.body.elided_span) if self.body.elided_span else None
            ),
        }

    def unit_id(self) -> str:
        return fingerprint(self.identity())

    def key(self) -> str:
        """Where this unit lives in a cache, ignoring its content."""
        span = f"#{self.span[0]}-{self.span[1]}" if self.span else ""
        symbol = f"::{self.symbol}" if self.symbol else ""
        return f"{self.kind.value}:{self.source}{symbol}{span}"

    def cache_key(self) -> str:
        """Where this unit lives in a cache, including *which form of it*.

        `key()` is the unit's slot in a bundle - one unit per source and span.
        A cache key must say more. A whole file and an elision of that same
        file share a slot and a content digest, so keying the cache on `key()`
        let a `put` of the elided form answer a later lookup for the whole
        file: digest matched, nothing was stale, and the caller quietly
        received less material than it asked for. Representation is part of
        cache identity, which is what `identity()` said all along.
        """
        form = self.body.kind.value
        if self.body.elided_span is not None:
            start, end = self.body.elided_span
            form = f"{form}:{start}-{end}"
        return f"{self.key()}@{form}"

    def order_key(self) -> tuple[int, int, str]:
        """Where this unit sits in a bundle: most stable material first.

        Authority first because a contract outlives a task and a derived
        ranking does not; then the declared kind order; then the key, so the
        result is still total and still deterministic.
        """
        return (
            _AUTHORITY_ORDER[self.authority],
            _KIND_ORDER[self.kind],
            self.key(),
        )

    # -- rendering --------------------------------------------------------

    def render(self) -> str:
        """The unit's prompt material. Deterministic in its own fields alone."""
        head = f"[{self.kind.value}/{self.authority.value}] {self.key()}"
        lines = [
            f"{head} sha256:{self.content_digest[:16]}",
            f"  why: {self.reason}",
        ]
        if self.freshness:
            lines.append(f"  freshness: {self.freshness}")
        if self.body.kind is CompressionKind.ELIDED:
            lines.append(
                f"  compressed: {self.body.elided_lines} of {self.body.full_lines} "
                f"line(s) elided, reversible against {self.source}"
            )
        lines.append("  ---")
        lines.extend(f"  {line}" for line in self.body.render().splitlines())
        lines.append("  ---")
        return "\n".join(lines)

    def chars(self) -> int:
        return len(self.render())

    def to_dict(self) -> dict[str, Any]:
        return {**to_jsonable(self), "unit_id": self.unit_id()}


def unit_from_source(
    text: str,
    *,
    kind: UnitKind,
    source: str,
    reason: str,
    authority: UnitAuthority,
    span: tuple[int, int] | None = None,
    symbol: str = "",
    freshness: str = "",
    compress_over: int = DEFAULT_COMPRESSION_THRESHOLD_CHARS,
) -> ContextUnit:
    """Build a unit from canonical source text, compressing it if worthwhile."""
    return ContextUnit(
        kind=kind,
        source=source,
        reason=reason,
        authority=authority,
        body=compress(text, source=source, threshold_chars=compress_over),
        span=span,
        symbol=symbol,
        freshness=freshness,
    )


def recompress(unit: ContextUnit, *, threshold_chars: int) -> ContextUnit:
    """Re-shorten a unit's body. Authority is carried through, never raised."""
    if unit.body.kind is not CompressionKind.NONE:
        raise LifecycleError(
            f"{unit.source}: recompress takes an uncompressed unit; compressing an "
            "already-elided body would elide an elision marker"
        )
    rebuilt = ContextUnit(
        kind=unit.kind,
        source=unit.source,
        reason=unit.reason,
        authority=unit.authority,
        body=compress(unit.body.head, source=unit.source, threshold_chars=threshold_chars),
        span=unit.span,
        symbol=unit.symbol,
        freshness=unit.freshness,
    )
    if rebuilt.authority is not unit.authority:  # pragma: no cover - structural
        raise LifecycleError("compression may not change a unit's authority")
    return rebuilt


@dataclass(frozen=True)
class ContextBundle:
    """Every unit a session is given, in an order that does not depend on luck.

    Units are sorted by `order_key()` at construction, so two bundles holding
    the same units render identically however they were assembled. That is the
    whole cache-stability contract, and `cache_stability()` is how it is
    checked rather than assumed.

    The order is `_AUTHORITY_ORDER` then `_KIND_ORDER` then the key: contracts
    first, derived material last. Any total order loses the prefix when a unit
    is inserted before the end, so the one that is worth having is the one
    where the things that change most often are already at the bottom.
    """

    units: tuple[ContextUnit, ...] = ()

    def __post_init__(self) -> None:
        for unit in self.units:
            if not isinstance(unit, ContextUnit):
                raise LifecycleError("a context bundle holds ContextUnit values")
        keys = [unit.key() for unit in self.units]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise LifecycleError(
                "two units claim the same place in the bundle: " + ", ".join(duplicates)
            )
        object.__setattr__(
            self, "units", tuple(sorted(self.units, key=lambda unit: unit.order_key()))
        )

    def __len__(self) -> int:
        return len(self.units)

    def __iter__(self):
        return iter(self.units)

    def contract_units(self) -> tuple[ContextUnit, ...]:
        """The binding subset. What constrains the session, and nothing else."""
        return tuple(unit for unit in self.units if unit.binding)

    def derived_units(self) -> tuple[ContextUnit, ...]:
        return tuple(
            unit for unit in self.units if unit.authority is UnitAuthority.DERIVED
        )

    def render(self) -> str:
        """Cache-stable prompt material: sorted, relative, and clock-free."""
        if not self.units:
            return ""
        return "\n".join(unit.render() for unit in self.units) + "\n"

    def chars(self) -> int:
        return len(self.render())

    def canonical_chars(self) -> int:
        """What the same units would have cost with nothing compressed."""
        return sum(unit.body.full_chars for unit in self.units)

    def digest(self) -> str:
        """Identity of the rendered material, for comparing two assemblies."""
        return content_digest(self.render())

    def unit_ids(self) -> tuple[str, ...]:
        return tuple(unit.unit_id() for unit in self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest(),
            "chars": self.chars(),
            "canonical_chars": self.canonical_chars(),
            "units": [unit.to_dict() for unit in self.units],
        }


@dataclass(frozen=True)
class CacheStability:
    """How much of one rendering a provider cache could reuse for the next."""

    shared_prefix_chars: int
    left_chars: int
    right_chars: int
    identical: bool

    @property
    def ratio(self) -> float:
        """Shared prefix as a fraction of the longer rendering. 1.0 is reuse."""
        longest = max(self.left_chars, self.right_chars)
        return 1.0 if longest == 0 else self.shared_prefix_chars / longest

    def to_dict(self) -> dict[str, Any]:
        return {**to_jsonable(self), "ratio": round(self.ratio, 6)}


def cache_stability(left: str, right: str) -> CacheStability:
    """Measure the shared prefix of two renderings.

    A provider prompt cache reuses a *prefix*, so the honest measurement is
    prefix length, not edit distance and not a set comparison of the units. A
    volatile value near the top of a bundle costs far more than the same value
    near the bottom, and only this measurement shows that.
    """
    if not isinstance(left, str) or not isinstance(right, str):
        raise LifecycleError("cache_stability compares two renderings")
    shared = 0
    for a, b in zip(left, right):
        if a != b:
            break
        shared += 1
    return CacheStability(
        shared_prefix_chars=shared,
        left_chars=len(left),
        right_chars=len(right),
        identical=left == right,
    )


def bundle_of(units: Iterable[ContextUnit]) -> ContextBundle:
    return ContextBundle(tuple(units))


__all__ = [
    "CONTEXT_UNIT_VERSION",
    "DEFAULT_COMPRESSION_THRESHOLD_CHARS",
    "DEFAULT_HEAD_LINES",
    "DEFAULT_TAIL_LINES",
    "CacheStability",
    "CompressedBody",
    "CompressionKind",
    "ContextBundle",
    "ContextUnit",
    "UnitAuthority",
    "UnitKind",
    "bundle_of",
    "cache_stability",
    "compress",
    "content_digest",
    "expand",
    "recompress",
    "unit_from_source",
]
