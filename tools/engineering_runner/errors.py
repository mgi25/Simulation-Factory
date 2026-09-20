"""What the runner refuses, as distinct types a caller can branch on.

Three of these are not failures in the ordinary sense. `AuthorityViolation`,
`IntegrityFailure` and `BackendUnavailable` all describe a run that stopped
because something did not add up, and a caller that cannot tell them apart
ends up treating "the model edited a file it was not allowed to" the same way
it treats "the CLI is not installed". They are separate so the run record can
say which one happened and the exit code can differ.
"""

from __future__ import annotations


class RunnerError(Exception):
    """The base of everything this package raises."""


class ConfigurationError(RunnerError):
    """The runner was pointed at something that is not there, or not a repository."""


class IntegrityFailure(RunnerError):
    """A Company OS artifact contradicts itself, so the runner will not act on it."""


class AuthorityViolation(RunnerError):
    """Work stepped outside the authority the work order granted it.

    Raised only by the verification in `authorization.py`. Every call site
    records it as BLOCKED rather than retrying: an attempt that exceeded its
    scope is not an attempt that needs another go, it is a question for the
    CEO.
    """


class BackendUnavailable(RunnerError):
    """No coding session could be launched, so nothing was attempted."""


class BackendFailure(RunnerError):
    """A coding session was launched and did not return a usable result."""


class ControlPlaneRefusal(RunnerError):
    """Company OS refused a stage. The runner never argues with that answer."""

    def __init__(self, command: str, exit_code: int, message: str) -> None:
        super().__init__(f"{command} exited {exit_code}: {message}")
        self.command = command
        self.exit_code = exit_code
        self.message = message


class ClaimUnavailable(RunnerError):
    """Another runner holds the lease on this work order, and holds it live."""


__all__ = [
    "AuthorityViolation",
    "BackendFailure",
    "BackendUnavailable",
    "ClaimUnavailable",
    "ConfigurationError",
    "ControlPlaneRefusal",
    "IntegrityFailure",
    "RunnerError",
]
