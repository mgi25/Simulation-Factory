"""One exception per failure class, so a caller can tell bad data from a breach.

`AdvisoryViolation` is the one worth reading. Everything in this package is
advisory by construction: it observes, it reasons deterministically, and it
stops at a record a person reads. A record that would step over that line - a
recommendation that approved itself, an optimisation that proposes amending the
constitution, a change proposal that names itself as the implementer - is not a
malformed record, it is the failure this subsystem exists to make impossible.
A distinct type makes catching it and continuing visible in the code.
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError, ValidationError


class OrgIntelligenceError(CompanyOSError, ValueError):
    """An organizational record that would mislead the company if it were stored."""


class AdvisoryViolation(OrgIntelligenceError):
    """A record tried to act, approve itself, or bypass a constitutional rule."""


class OrgIntelligenceIntegrityError(ValidationError):
    """One or more cross-record invariants are broken, reported together."""
