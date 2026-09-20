"""Which query found this, who captured it, and how - kept past promotion.

Two small records, deliberately in their own module because they are the one
piece of vocabulary a `DiscoveryCandidate` and a `ResearchSource` both need.
`sources.py` imports this; `discovery.py` imports this; neither imports the
other, and that is the whole reason the file exists.

## Provenance is a list, not a field

The same video is found by several queries. "marble race" finds it, and so
does "satisfying machine", and the fact that *both* did is a signal about the
video that no single discovery run can see. So a candidate carries a tuple of
`DiscoveryProvenance` and re-discovery appends to it; the second query is never
dropped on the grounds that the first one got there first.

## Capture method is not evidence, and evidence is not capture method

`CaptureMethod` says *how* a number reached us. `Evidence` says what a reader
could go and check. Both are required on anything carrying a public metric,
because they fail differently: a screenshot with no capture method does not say
whether a human read the page or a script did, and a capture method with no
evidence is an unsourced claim with a provenance label on it.

`PLATFORM_API` exists as a value and no API adapter exists in this repository.
That is not an oversight - a researcher who exported rows from an API console
by hand should be able to say so, and the evidence pointer is what makes the
claim checkable. Nothing here performs a request.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import as_date, as_opt_date
from intelligence.research.common import (
    assert_reference,
    assert_research_id,
    assert_text,
)
from intelligence.research.errors import ResearchError


class CaptureMethod(Enum):
    """How externally captured metadata reached this system.

    Four values, none of them automatic. There is no `SCRAPED`, and adding one
    would need a scraper, which the package does not have and the phase brief
    does not want yet.
    """

    MANUAL_BROWSER = "manual_browser"
    JSON_IMPORT = "json_import"
    PLATFORM_API = "platform_api"
    PARTNER_EXPORT = "partner_export"


@dataclass(frozen=True)
class DiscoveryProvenance:
    """One query that found this candidate, on one day, at one position.

    `rank` is where it appeared in that query's results. It is optional because
    a researcher reading a page rarely knows it, and it is *not* a quality
    signal - it records what the platform showed, which is a fact about the
    platform on that day and nothing about the video.
    """

    query_id: str
    discovered_on: dt.date
    rank: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.query_id, "discovery query")
        if not isinstance(self.discovered_on, dt.date):
            raise ResearchError("discovery provenance must record the day it was found")
        if self.rank is not None:
            if isinstance(self.rank, bool) or not isinstance(self.rank, int):
                raise ResearchError(f"provenance rank must be a whole number, got {self.rank!r}")
            if self.rank < 1:
                raise ResearchError(
                    f"provenance rank {self.rank} is not a position; results are "
                    "counted from 1, and an unknown position is left unset"
                )

    @property
    def key(self) -> tuple[str, str]:
        """Two entries with the same key are the same discovery, not two."""
        return (self.query_id, self.discovered_on.isoformat())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryProvenance:
        return cls(
            query_id=data["query_id"],
            discovered_on=as_date(data["discovered_on"], "discovered_on"),
            rank=data.get("rank"),
            note=data.get("note", ""),
        )


def merge_provenance(
    existing: tuple[DiscoveryProvenance, ...],
    incoming: tuple[DiscoveryProvenance, ...],
) -> tuple[DiscoveryProvenance, ...]:
    """Union by (query, day), existing entries first and unmodified.

    Order is stable so two sessions merging the same two discoveries write the
    same file. An entry already present is not replaced: the first record of a
    discovery is the one that says when we actually first saw it.
    """
    out = list(existing)
    seen = {entry.key for entry in existing}
    for entry in incoming:
        if entry.key in seen:
            continue
        seen.add(entry.key)
        out.append(entry)
    return tuple(out)


@dataclass(frozen=True)
class DiscoveryOrigin:
    """Where a `ResearchSource` came from, so promotion throws nothing away.

    A source promoted out of the discovery queue would otherwise keep only its
    canonical URL, and the two facts most worth having six weeks later are the
    ones that would be lost: the string the researcher actually clicked, and
    which query made us look at all.
    """

    candidate_id: str
    platform: str
    original_url: str
    canonical_url: str
    capture_method: CaptureMethod
    provenance: tuple[DiscoveryProvenance, ...]
    external_id: str = ""
    screened_by: str = ""
    screened_on: dt.date | None = None

    def __post_init__(self) -> None:
        assert_research_id(self.candidate_id, "candidate")
        assert_text(self.platform, "origin platform")
        assert_reference(self.original_url, "origin original_url")
        assert_reference(self.canonical_url, "origin canonical_url")
        if not isinstance(self.capture_method, CaptureMethod):
            raise ResearchError("origin capture_method must be a CaptureMethod")
        object.__setattr__(self, "provenance", tuple(self.provenance))
        if not self.provenance:
            raise ResearchError(
                f"origin for candidate {self.candidate_id!r} names no discovery query. "
                "A source promoted from the queue keeps the queries that found it - "
                "that several found it is a signal no single query can see."
            )
        if self.screened_on is not None and not isinstance(self.screened_on, dt.date):
            raise ResearchError("origin screened_on must be a date")

    @property
    def query_ids(self) -> tuple[str, ...]:
        """Every query that found this, in discovery order, without duplicates."""
        out: list[str] = []
        for entry in self.provenance:
            if entry.query_id not in out:
                out.append(entry.query_id)
        return tuple(out)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryOrigin:
        return cls(
            candidate_id=data["candidate_id"],
            platform=data["platform"],
            original_url=data["original_url"],
            canonical_url=data["canonical_url"],
            capture_method=CaptureMethod(data["capture_method"]),
            provenance=tuple(
                DiscoveryProvenance.from_dict(p) for p in data.get("provenance", ())
            ),
            external_id=data.get("external_id", ""),
            screened_by=data.get("screened_by", ""),
            screened_on=as_opt_date(data.get("screened_on"), "screened_on"),
        )
