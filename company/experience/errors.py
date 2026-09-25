"""The three ways the experience store says no."""

from __future__ import annotations

from company.validation.errors import CompanyOSError


class ExperienceError(CompanyOSError):
    """An experience record is malformed, or a request of the store is refused."""


class ExperienceConflict(ExperienceError):
    """A different episode was offered under an identity the store already holds.

    Raised, never resolved. The identity is derived from canonical pointers, so
    two different bodies under one identity means a canonical record changed
    underneath an index that was built from it - which is exactly the thing an
    index must never absorb silently.
    """


class CaptureRefused(ExperienceError):
    """A completed attempt could not be turned into an episode, and why.

    `code` is one of a fixed vocabulary (see `capture.REFUSAL_CODES`) so a
    caller - and the replay measurement - can count refusals by cause rather
    than by parsing prose.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


__all__ = ["CaptureRefused", "ExperienceConflict", "ExperienceError"]
