"""The three failures this subsystem distinguishes, and nothing finer.

`DelegationError` is a malformed record: a seat that is not declared, a budget
ladder whose child exceeds its parent, an objective whose parent is missing.

`AuthorityViolation` is the narrower one, and the reason it is separate: it is
raised when something tried to *take* authority rather than be granted it — a
seat approving its own request, a policy that grants a subordinate the right to
overrule its manager, a decision record that claims it authorizes the action.
Those are the failures a reader should be able to grep for by name.

`ShadowModeViolation` is raised by exactly one condition: a record or a policy
that claims this phase can execute authority. It is separate from
`AuthorityViolation` because the remedy is different — the first is a bug in a
grant, the second is an attempt to switch the phase on.
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError


class DelegationError(CompanyOSError):
    """A delegation record is missing, malformed, or contradicts the policy."""


class AuthorityViolation(DelegationError):
    """Something tried to take authority instead of receiving it."""


class ShadowModeViolation(AuthorityViolation):
    """Something claimed this phase may execute authority. It may not."""


__all__ = ["AuthorityViolation", "DelegationError", "ShadowModeViolation"]
