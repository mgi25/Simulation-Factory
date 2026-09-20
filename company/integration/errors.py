"""One exception per failure class, so a caller can tell a bad gate from a bad company.

The distinction this package has to keep is between *the gate found a problem*
and *the gate itself is broken*. The first is data: a `GateCheck` with a `fail`
status, a reason and a remediation, which is the normal, expected output of a
company that is not finished yet. The second is an exception, because a gate
that cannot evaluate a condition must never quietly report that the condition
holds.

So nothing in here is raised to report a failed readiness condition. These are
raised when a report would be malformed, when a check id is not classified by
the policy, or when a stored report would be overwritten with different content.
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError, ValidationError


class IntegrationGateError(CompanyOSError, ValueError):
    """A readiness structure that would mislead a reader if it were built."""


class PolicyError(IntegrationGateError):
    """A check the gate policy does not classify as required or advisory.

    Refused rather than defaulted. A check that quietly lands in `advisory`
    because nobody classified it is a hidden weighting, and section 9 of the
    brief forbids exactly that.
    """


class ReportStoreError(IntegrationGateError):
    """A persisted report was about to be overwritten with different content."""


class GateEvaluationError(ValidationError):
    """The gate could not run a check that it is not allowed to skip."""


__all__ = [
    "GateEvaluationError",
    "IntegrationGateError",
    "PolicyError",
    "ReportStoreError",
]
