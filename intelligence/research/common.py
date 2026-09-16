"""The vocabulary every research record shares: ids, numbers, and doubt.

Three things recur in every type in this package, and each of them is a place
where research quietly turns into fiction unless something refuses it.

**An id is a filename.** Same rule, same pattern and nearly the same error as
`knowledge.company_os.records`, because these records live in a directory too.

**A number is a `Measurement`.** Constitution rule 7 says important claims
identify their evidence; the brief says do not fabricate numeric reference
measurements. A float field on a dataclass cannot tell a stopwatch reading from
a guess, so no research record has one. Every number that describes the outside
world arrives as a `Measurement`, which carries the unit, the method and a
mandatory `Evidence` pointer. A researcher who has not measured a thing cannot
type a number for it - the type will not hold one.

**Doubt is a field, not a tone.** `ResearchConfidence` is the brief's section 7
made structural: level, basis, evidence, sample size, source quality, freshness,
limitations, contradictory evidence, and what would change the conclusion. Two
of its rules are load-bearing:

- `would_change_if` is required. A finding nobody can name a refutation for is
  not a finding, and this is the field that stops "Shorts audiences prefer X"
  from ageing into scripture.
- `Freshness.PERMANENT` is refused. Research observes a moving world - a
  platform, an audience, a competitor's channel - and nothing observed about a
  moving world is an invariant. The legitimate route to a permanent claim is
  the knowledge store: record a `Hypothesis`, test it, `promote()` it. That
  route requires evidence of our own, which is the bar this refusal protects.

`Evidence` itself is imported, not redefined (rule 15). Its `ref` is already
held to the one-line reference budget in `ai_platform/references.py`.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, as_tuple
from intelligence.research.errors import ResearchError
from knowledge.company_os.freshness import Freshness, default_recheck_on
from knowledge.company_os.records import Evidence

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,47}$")

__all__ = [
    "Complexity",
    "ConfidenceLevel",
    "Evidence",
    "ID_PATTERN",
    "Measurement",
    "ResearchConfidence",
    "SLUG_PATTERN",
    "SourceQuality",
    "assert_nonempty",
    "assert_reference",
    "assert_research_id",
    "assert_slug",
    "assert_slugs",
    "assert_text",
    "assert_texts",
    "evidence_tuple",
    "opt_measurement",
]


def assert_research_id(value: str, kind: str) -> str:
    """Record ids are filenames, so they are held to a filename's alphabet."""
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise ResearchError(
            f"{kind} id {value!r} must be lowercase [a-z0-9._-], start alphanumeric, "
            "and be at most 80 characters - research record ids are also filenames"
        )
    return value


def assert_slug(value: str, field: str) -> str:
    """Tags are compared, grouped and counted, so they are lower_snake only."""
    if not isinstance(value, str) or not SLUG_PATTERN.match(value):
        raise ResearchError(
            f"{field}: {value!r} must be a lowercase snake_case tag of at most 48 "
            "characters, so two researchers spell the same concept the same way"
        )
    return value


def assert_slugs(values: Any, field: str) -> tuple[str, ...]:
    return tuple(assert_slug(v, field) for v in as_tuple(values))


def assert_nonempty(values: tuple[Any, ...], field: str, why: str) -> tuple[Any, ...]:
    if not values:
        raise ResearchError(f"{field}: at least one entry is required - {why}")
    return values


def assert_texts(values: Any, field: str) -> tuple[str, ...]:
    out = as_tuple(values)
    for item in out:
        assert_text(item, field)
    return out


def evidence_tuple(data: Any) -> tuple[Evidence, ...]:
    if not data:
        return ()
    return tuple(e if isinstance(e, Evidence) else Evidence.from_dict(e) for e in data)


class SourceQuality(Enum):
    """Where an observation came from, ordered by how much it can support.

    `FIRST_PARTY` is our own analytics or our own render - the only class that
    can carry private numbers, and only about us. `PLATFORM_PUBLIC` is what any
    logged-out viewer can read off a page. Everything below that is somebody
    else's summary of something they did not necessarily see either.
    """

    FIRST_PARTY = "first_party"
    PLATFORM_PUBLIC = "platform_public"
    THIRD_PARTY_REPORT = "third_party_report"
    ANECDOTAL = "anecdotal"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Four words, because a percentage on a judgement is false precision.

    A researcher who writes 0.73 has not measured 0.73. The numeric confidence
    on a `Fact` means something because a fact is evidenced; a research finding
    is a reading of a moving world, and four named levels are the most it can
    honestly support.
    """

    SPECULATIVE = "speculative"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class Complexity(Enum):
    """An estimate, always recorded beside the basis for it."""

    UNKNOWN = "unknown"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True)
class Measurement:
    """A number about the outside world, with what produced it.

    Four required parts and no shortcut past any of them. `unit`, because a
    bare 3.2 has been a second, a percentage and a ratio in three different
    reference notes. `method`, because "counted cuts in the first ten seconds"
    and "felt fast" produce the same float. `evidence`, because rule 7, and
    because the brief's one hard prohibition is fabricated reference numbers.
    """

    value: float
    unit: str
    method: str
    evidence: Evidence

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ResearchError(f"measurement value must be a number, got {self.value!r}")
        object.__setattr__(self, "value", float(self.value))
        assert_slug(self.unit, "measurement unit")
        assert_text(self.method, "measurement method (how this number was obtained)")
        if not isinstance(self.evidence, Evidence):
            raise ResearchError(
                "a measurement requires an Evidence pointer. A number with no evidence "
                "is an estimate - write it as prose, or go and measure it."
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Measurement:
        return cls(
            value=data["value"],
            unit=data["unit"],
            method=data["method"],
            evidence=Evidence.from_dict(data["evidence"]),
        )


def opt_measurement(data: Any) -> Measurement | None:
    if data is None:
        return None
    return data if isinstance(data, Measurement) else Measurement.from_dict(data)


@dataclass(frozen=True)
class ResearchConfidence:
    """How much weight a finding can carry, and what would take it away.

    Section 7 of the phase brief as one object. `limitations` and
    `contradictory_evidence` are optional because a finding may genuinely have
    none; `would_change_if` is not, because a finding nobody can refute is not
    a finding. See the module docstring for why `PERMANENT` is refused.
    """

    level: ConfidenceLevel
    basis: str
    freshness: Freshness
    observed_on: dt.date
    would_change_if: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()
    source_quality: SourceQuality = SourceQuality.UNKNOWN
    sample_size: int | None = None
    limitations: tuple[str, ...] = ()
    contradictory_evidence: tuple[Evidence, ...] = ()
    recheck_on: dt.date | None = None

    def __post_init__(self) -> None:
        assert_text(self.basis, "confidence basis (why this level, in one sentence)")
        object.__setattr__(
            self, "would_change_if", assert_texts(self.would_change_if, "would_change_if")
        )
        object.__setattr__(self, "limitations", assert_texts(self.limitations, "limitations"))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(
            self, "contradictory_evidence", evidence_tuple(self.contradictory_evidence)
        )
        assert_nonempty(
            self.would_change_if,
            "would_change_if",
            "name the observation that would overturn this, or it is a belief, not a finding",
        )
        if self.freshness is Freshness.PERMANENT:
            raise ResearchError(
                "research confidence may not be permanent. Research observes a moving "
                "world; an invariant is earned in the knowledge store by recording a "
                "Hypothesis, testing it, and promote()-ing it on evidence of our own."
            )
        if self.sample_size is not None:
            if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int):
                raise ResearchError(
                    f"sample_size must be a whole number, got {self.sample_size!r}"
                )
            if self.sample_size < 1:
                raise ResearchError(
                    f"sample_size {self.sample_size} is not a sample. Leave it unset when "
                    "the finding is not counted over anything."
                )
        if self.level in (ConfidenceLevel.MODERATE, ConfidenceLevel.STRONG) and not self.evidence:
            raise ResearchError(
                f"confidence {self.level.value!r} carries no evidence. Cite what raised it "
                "above weak, or record the finding as speculative or weak."
            )
        if self.recheck_on is None:
            object.__setattr__(
                self, "recheck_on", default_recheck_on(self.freshness, self.observed_on)
            )

    @property
    def is_contested(self) -> bool:
        """True when the author recorded evidence pointing the other way."""
        return bool(self.contradictory_evidence)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchConfidence:
        raw_recheck = data.get("recheck_on")
        return cls(
            level=ConfidenceLevel(data["level"]),
            basis=data["basis"],
            freshness=Freshness(data["freshness"]),
            observed_on=as_date(data["observed_on"], "observed_on"),
            would_change_if=as_tuple(data.get("would_change_if")),
            evidence=evidence_tuple(data.get("evidence")),
            source_quality=SourceQuality(data.get("source_quality", "unknown")),
            sample_size=data.get("sample_size"),
            limitations=as_tuple(data.get("limitations")),
            contradictory_evidence=evidence_tuple(data.get("contradictory_evidence")),
            recheck_on=None if raw_recheck is None else as_date(raw_recheck, "recheck_on"),
        )
