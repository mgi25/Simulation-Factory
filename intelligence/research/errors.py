"""One exception, so a caller can tell a bad record from a bad program."""

from __future__ import annotations


class ResearchError(ValueError):
    """A research record that would corrupt the store if it were written."""
