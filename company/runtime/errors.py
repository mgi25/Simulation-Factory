"""Runtime-specific Company OS failures."""

from company.validation.errors import CompanyOSError


class LifecycleError(CompanyOSError):
    """A task cannot advance to its next explicit lifecycle state."""
