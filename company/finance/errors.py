"""One exception per failure class, so a caller can tell bad data from a bug.

The split matters more here than elsewhere in Company OS. A malformed cost
record is a data problem somebody repairs; a mixed-currency addition is an
arithmetic lie that would produce a plausible wrong number; an append-only
violation is history being rewritten. Catching the first and continuing is
reasonable. Catching either of the other two and continuing is almost always
wrong, and a distinct type makes that visible at the call site.
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError, ValidationError


class FinanceError(CompanyOSError, ValueError):
    """A financial record that would mislead the company if it were stored."""


class CurrencyMismatch(FinanceError):
    """Two amounts in different currencies were combined or compared.

    Separate because there is no safe recovery. Every other finance failure has
    a repair - supply the evidence, fix the date, name the allocation rule. This
    one has only two honest answers: work in one currency, or record an explicit
    exchange-rate observation and convert deliberately. Neither is something the
    arithmetic may choose on a caller's behalf, so `Money` never picks one.
    """


class EvidenceRequired(FinanceError):
    """A monetary record pointed at nothing a second person could check.

    Section 3 of the brief: no monetary cost without evidence/source. A number
    with no receipt behind it is a number somebody remembered, and a company
    that budgets on remembered numbers is guessing with extra steps.
    """


class LedgerViolation(FinanceError):
    """Recorded financial history was about to be overwritten.

    Corrections are new records, not edits (section 16). This fires when the
    same record id is written twice with different bytes, which is the only way
    the file-backed store can lose a number that was already believed.
    """


class SpendAuthorityViolation(FinanceError):
    """A spend proposal claimed authority it does not have.

    Finance records the proposal and the evidence. It never approves, never
    pays, and never decides that something is small enough not to ask. A
    proposal that marks itself approved, or that is CEO-reserved and does not
    say so, is refused at construction rather than flagged later.
    """


class FinanceIntegrityError(ValidationError):
    """One or more cross-record financial invariants are broken, reported together."""
