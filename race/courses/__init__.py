"""Course builders. One module per course, one entry in the registry.

Every course is reached through `build_course`, so nothing downstream - a
CLI flag, a batch tool, the replay exporter - ever imports a course module
by hand or knows how many there are.
"""

from __future__ import annotations

from race.courses.machine import MACHINE_COURSE_ID, build_machine_course
from race.courses.neon import NEON_COURSE_ID, build_neon_course
from race.courses.prototype import PROTOTYPE_COURSE_ID, build_prototype_course
from race.courses.split import SPLIT_COURSE_ID, build_split_course

# Name to builder, so a CLI flag or a batch tool can pick a course without
# importing each module by hand.
COURSE_BUILDERS = {
    PROTOTYPE_COURSE_ID: build_prototype_course,
    SPLIT_COURSE_ID: build_split_course,
    MACHINE_COURSE_ID: build_machine_course,
    NEON_COURSE_ID: build_neon_course,
}
COURSE_NAMES: tuple[str, ...] = tuple(COURSE_BUILDERS)
DEFAULT_COURSE = PROTOTYPE_COURSE_ID

__all__ = [
    "COURSE_BUILDERS",
    "COURSE_NAMES",
    "DEFAULT_COURSE",
    "MACHINE_COURSE_ID",
    "NEON_COURSE_ID",
    "PROTOTYPE_COURSE_ID",
    "SPLIT_COURSE_ID",
    "build_machine_course",
    "build_neon_course",
    "build_prototype_course",
    "build_split_course",
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
