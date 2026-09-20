"""One exception per failure class, so a caller can tell bad data from a bug."""

from __future__ import annotations

from company.validation.errors import CompanyOSError, ValidationError


class WorkforceError(CompanyOSError, ValueError):
    """A workforce record that would mislead the organization if it were stored."""


class AuthorityViolation(WorkforceError):
    """A restricted employment state was handed authority it may not hold.

    Separate from `WorkforceError` because this is the failure the constitution
    cares about (rule 11, sandbox before production). A caller may reasonably
    catch a malformed record and repair it; catching this one and continuing is
    almost always wrong, and a distinct type makes that visible in the code.
    """


class LifecycleViolation(WorkforceError):
    """An employment transition that no evidence supports, or that cannot exist."""


class WorkforceIntegrityError(ValidationError):
    """One or more cross-record invariants are broken, reported together."""
