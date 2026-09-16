"""What came in, from whom, and the three things that can never become revenue.

## Only our own money, only from an authenticated source

Section 4 is unusually specific, and it is specific because the failure is
tempting. A public view count multiplied by a plausible RPM produces a number
that looks like revenue, sits in a spreadsheet indistinguishable from a real
one, and is wrong by an unknown factor. So this module refuses it three ways:

1. `EvidenceOrigin` has no member for a public estimate. The evidence backing a
   revenue line is an analytics export, a payment statement, a contract, an
   invoice or a bank record - things with an account behind them.
2. `PUBLIC_EVIDENCE_KINDS` names the kinds that *look* like evidence and are
   not, and any of them on a `RevenueRecord` is a construction error whose
   message says why.
3. `SubjectKind` (in `common.py`) has no COMPETITOR member, so there is no way
   to spell a revenue line for somebody else's channel in the first place. The
   remaining route - our own subject id that happens to name a competitor's
   video - is caught by `integrity.assigned_to_external_reference`, which takes
   the external reference ids from whoever knows them.

## Gross or net is recorded, never assumed

A sponsorship figure before agency fees and the same figure after them differ by
a third, and a summary that adds one of each is wrong in a way no total reveals.
`Basis.UNKNOWN` exists because a real statement sometimes does not say, and an
honest unknown is better than a guess that propagates. `economics.py` reports
the mix rather than silently normalising it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterable

from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_kinds,
    evidence_tuple,
    record_to_dict,
)
from .errors import FinanceError
from .money import Money


class RevenueCategory(Enum):
    """Where the money came from. Section 4's list, one value each."""

    YOUTUBE_AD_REVENUE = "youtube_ad_revenue"
    SPONSORSHIP = "sponsorship"
    AFFILIATE = "affiliate"
    LICENSING = "licensing"
    PLATFORM_BONUS = "platform_bonus"
    OTHER = "other"


class Basis(Enum):
    """Whether an amount is before or after the platform's and agent's cut."""

    GROSS = "gross"
    NET = "net"
    UNKNOWN = "unknown"


class EvidenceOrigin(Enum):
    """How we came to know this number.

    Both members describe our own company's data. There is deliberately no
    member for an estimate, a public figure or a third-party guess: the absence
    is the guarantee, because an enum with no way to spell it cannot store it.
    """

    OWN_AUTHENTICATED = "own_authenticated"  # pulled from an account we log into
    OWN_SUPPLIED = "own_supplied"  # handed over by us, from a statement we hold


# Evidence kinds that look authoritative and are not. Any one of these on a
# revenue record is the exact failure section 4 names.
PUBLIC_EVIDENCE_KINDS = frozenset(
    {
        "public_estimate",
        "public_view_count",
        "public_metric",
        "competitor_observation",
        "competitor_estimate",
        "third_party_estimate",
        "social_media_public",
        "scraped",
        "estimate",
    }
)

# Evidence kinds that do have an account or a counterparty behind them. At least
# one is required: a revenue record backed only by `note` and `document` is a
# figure somebody typed.
ACCOUNTED_EVIDENCE_KINDS = frozenset(
    {
        "analytics_export",
        "payment_statement",
        "bank_record",
        "invoice",
        "contract",
        "platform_report",
        "remittance",
    }
)


@dataclass(frozen=True)
class RevenueRecord:
    """One revenue line of ours, from a source with an account behind it."""

    kind: ClassVar[str] = "revenue"

    revenue_id: str
    received_on: dt.date
    amount: Money
    category: RevenueCategory
    subject: SubjectRef
    source: str
    evidence: tuple[Evidence, ...]
    recorded_by: str
    recorded_on: dt.date
    basis: Basis = Basis.UNKNOWN
    origin: EvidenceOrigin = EvidenceOrigin.OWN_AUTHENTICATED
    supersedes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.revenue_id, "revenue_id")
        object.__setattr__(self, "received_on", assert_day(self.received_on, "received_on"))
        object.__setattr__(self, "recorded_on", assert_day(self.recorded_on, "recorded_on"))
        for name, enum_type in (
            ("category", RevenueCategory),
            ("basis", Basis),
            ("origin", EvidenceOrigin),
        ):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                raise FinanceError(
                    f"revenue {self.revenue_id!r}: {name} must be a {enum_type.__name__}, "
                    f"got {value!r}"
                )
        if not isinstance(self.amount, Money):
            raise FinanceError(
                f"revenue {self.revenue_id!r}: amount must be Money, got "
                f"{type(self.amount).__name__}"
            )
        if self.amount.is_negative:
            raise FinanceError(
                f"revenue {self.revenue_id!r}: revenue is not negative ({self.amount}). A "
                "clawback or a reversal is its own record referencing this one"
            )
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"revenue {self.revenue_id!r}: subject must be a SubjectRef naming what "
                "earned this"
            )
        assert_ref(self.source, f"revenue {self.revenue_id!r} source")
        assert_prose(self.recorded_by, f"revenue {self.revenue_id!r} recorded_by")
        if self.supersedes:
            assert_record_id(self.supersedes, f"revenue {self.revenue_id!r} supersedes")
        for name in ("notes",):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(f"revenue {self.revenue_id!r}: {name} must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"revenue {self.revenue_id!r} evidence",
            "revenue is never inferred; it is read off a statement somebody can open "
            "(brief section 4)",
        )
        self._check_evidence_is_ours()

    def _check_evidence_is_ours(self) -> None:
        kinds = evidence_kinds(self.evidence)
        public = sorted(kinds & PUBLIC_EVIDENCE_KINDS)
        if public:
            raise FinanceError(
                f"revenue {self.revenue_id!r}: evidence of kind {', '.join(public)} is a "
                "public or third-party figure. YouTube revenue is never inferred from "
                "views, and competitor data never becomes our revenue (brief section 4)"
            )
        if not kinds & ACCOUNTED_EVIDENCE_KINDS:
            raise FinanceError(
                f"revenue {self.revenue_id!r}: at least one piece of evidence must be an "
                "accounted kind - "
                + ", ".join(sorted(ACCOUNTED_EVIDENCE_KINDS))
                + f" - and this record has only {', '.join(sorted(kinds))}"
            )

    # -- reading -----------------------------------------------------------

    @property
    def currency(self) -> str:
        return self.amount.currency

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RevenueRecord:
        return cls(
            revenue_id=data["revenue_id"],
            received_on=assert_day(data["received_on"], "received_on"),
            amount=Money.from_dict(data["amount"], "revenue amount"),
            category=RevenueCategory(data["category"]),
            subject=SubjectRef.from_dict(data["subject"]),
            source=data["source"],
            evidence=evidence_tuple(data.get("evidence")),
            recorded_by=data["recorded_by"],
            recorded_on=assert_day(data["recorded_on"], "recorded_on"),
            basis=Basis(data.get("basis", "unknown")),
            origin=EvidenceOrigin(data.get("origin", "own_authenticated")),
            supersedes=data.get("supersedes", ""),
            notes=data.get("notes", ""),
        )


def basis_mix(records: Iterable[RevenueRecord]) -> tuple[str, ...]:
    """Which gross/net bases appear in a set, sorted.

    A summary over a mix of gross and net is not wrong, it is ambiguous, and
    this is what lets it say so instead of averaging the ambiguity away.
    """
    return tuple(sorted({record.basis.value for record in records}))
