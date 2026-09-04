"""Course builders. One per course; V0.1 ships the prototype only."""

from __future__ import annotations

from race.courses.prototype import PROTOTYPE_COURSE_ID, build_prototype_course

# Name to builder, so a CLI flag or a future batch tool can pick a course
# without importing each module by hand.
COURSE_BUILDERS = {PROTOTYPE_COURSE_ID: build_prototype_course}
COURSE_NAMES: tuple[str, ...] = tuple(COURSE_BUILDERS)
DEFAULT_COURSE = PROTOTYPE_COURSE_ID

__all__ = [
    "COURSE_BUILDERS",
    "COURSE_NAMES",
    "DEFAULT_COURSE",
    "PROTOTYPE_COURSE_ID",
    "build_prototype_course",
    "build_course",
]


def build_course(name: str, seed: int):
    """Build a named course for a seed."""
    try:
        builder = COURSE_BUILDERS[name]
    except KeyError:
        raise ValueError(
            f"unknown course {name!r}; known courses: {', '.join(COURSE_NAMES)}"
        ) from None
    return builder(seed)
