"""The four ways an engineering job fails, kept apart because they differ.

`EngineeringError` is an ordinary malformed record. The other three name a
governance violation, and each one is a thing the implementer is structurally
unable to do rather than merely discouraged from doing:

- `AuthorityEscalation` — work reached outside the work order's authorized
  paths, or the work order itself changed after it was authorized.
- `ProtectedSurfaceViolation` — a file the work order protected was modified.
  This is the one that catches "change the policy until the gate passes".
- `SelfApproval` — the implementer tried to review or approve its own work.

They are separate types so a caller can tell an unreadable file from an attempt
to widen a ceiling, and so a test can assert the specific refusal rather than
"something raised".
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError


class EngineeringError(CompanyOSError):
    """A malformed engineering record, or an illegal lifecycle transition."""


class AuthorityEscalation(EngineeringError):
    """Work, or a plan, reached beyond the authority the work order granted."""


class ProtectedSurfaceViolation(AuthorityEscalation):
    """A file the work order declared protected was modified during execution."""


class SelfApproval(EngineeringError):
    """The implementer attempted to review, pass or approve its own work."""


__all__ = [
    "AuthorityEscalation",
    "EngineeringError",
    "ProtectedSurfaceViolation",
    "SelfApproval",
]
