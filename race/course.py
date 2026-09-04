"""A race course as plain data: geometry, checkpoints, spawns, sections.

Data only, exactly like `engine.arena_layout`: no Pymunk shapes, no space,
no rendering state. `race.runtime` turns it into bodies, the renderer draws
it, and the tests measure it - all from this one description.

Geometry is reused rather than reinvented. A wall, a ramp, a shelf and a
peg are all `ObstacleSpec`s, so `corners()`, `bounds()` and the clearance
helpers the fight system already trusts apply here unchanged. What a course
adds on top is the part a duel has no concept of: a surface's material, a
piece's role in the race, and the ordered checkpoints that define what
"further along" means.

Spinners are the one thing that could not reuse `ObstacleSpec`: several arms
have to turn as one rigid body about a shared hub, and a spec describes a
single shape. So a spinner is its own record and `race.runtime` builds all
of its arms onto one kinematic body.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator

from engine.arena_layout import ObstacleSpec

__all__ = [
    "ROLE_WALL",
    "ROLE_RAMP",
    "ROLE_PEG",
    "ROLE_GATE",
    "ROLE_JUMP_PAD",
    "ROLES",
    "Material",
    "TRACK",
    "SLICK",
    "BOUNCY",
    "CoursePiece",
    "SpinnerSpec",
    "Checkpoint",
    "RacerSpawn",
    "CourseSection",
    "RaceCourse",
    "box_between",
]

# What a piece is for. All of them are solid; the role decides the material
# a builder reaches for, how the renderer draws it, and - for the two
# special cases - whether the simulation gives it a collision handler.
ROLE_WALL = "wall"          # course boundary, never removed
ROLE_RAMP = "ramp"          # a surface racers travel along
ROLE_PEG = "peg"            # a scatterer racers bounce off
ROLE_GATE = "gate"          # solid until the countdown ends, then removed
ROLE_JUMP_PAD = "jump_pad"  # solid, and kicks whatever touches it
ROLES: tuple[str, ...] = (ROLE_WALL, ROLE_RAMP, ROLE_PEG, ROLE_GATE, ROLE_JUMP_PAD)


@dataclass(frozen=True)
class Material:
    """How a surface behaves. Named presets, not free-form numbers.

    The duel gives every surface elasticity 1.0 and friction 0.0 because a
    fight has to conserve energy forever. A race must not: perfectly elastic
    walls would turn the course into a pinball machine and a frictionless
    ramp would never let a racer roll. So a race surface picks one of the
    three presets below, and a reader can tell what a piece does to a racer
    from its name alone.
    """

    name: str
    elasticity: float
    friction: float


# Ordinary course surface: absorbs most of an impact, grips enough to roll.
TRACK = Material("track", 0.24, 0.42)
# Funnel walls and accelerating ramps: racers should slide, not grip.
SLICK = Material("slick", 0.18, 0.05)
# Pegs and bumpers: the scattering comes from here.
BOUNCY = Material("bouncy", 0.62, 0.18)


@dataclass(frozen=True)
class CoursePiece:
    """One solid piece of course: geometry, plus what it is and what it does."""

    spec: ObstacleSpec
    role: str
    material: Material
    section: str = ""
    # Jump pads only. `impulse` is applied in world axes to a racer on
    # contact; `impulse_jitter` is the fraction it may vary by, drawn from
    # the seeded jitter stream so the variation is still reproducible.
    impulse: tuple[float, float] = (0.0, 0.0)
    impulse_jitter: float = 0.0

    @property
    def piece_id(self) -> int:
        return self.spec.obstacle_id

    @property
    def is_gate(self) -> bool:
        return self.role == ROLE_GATE

    @property
    def is_jump_pad(self) -> bool:
        return self.role == ROLE_JUMP_PAD

    @property
    def impulse_magnitude(self) -> float:
        return math.hypot(*self.impulse)

    def bounds(self) -> tuple[float, float, float, float]:
        return self.spec.bounds()


@dataclass(frozen=True)
class SpinnerSpec:
    """A hub with radial arms, turning at a constant rate.

    `arm_count` arms are spaced evenly around the hub; each one runs from
    the hub edge outwards for `arm_length`. The sign of `angular_speed` is
    the direction of rotation. `reach` is how far the arm tips get from the
    hub, which is what a course builder has to keep clear of the walls and
    of the next spinner.
    """

    spinner_id: int
    x: float
    y: float
    hub_radius: float
    arm_count: int
    arm_length: float
    arm_thickness: float
    angular_speed: float          # signed degrees per simulated second
    start_angle: float = 0.0      # degrees
    material: Material = TRACK
    section: str = ""

    def __post_init__(self) -> None:
        if self.arm_count < 1:
            raise ValueError("a spinner needs at least one arm")
        if self.arm_length <= 0.0 or self.arm_thickness <= 0.0:
            raise ValueError("spinner arms need a positive length and thickness")

    @property
    def center(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def reach(self) -> float:
        """Distance from the hub centre to an arm tip."""
        return self.hub_radius + self.arm_length

    @property
    def tip_speed(self) -> float:
        """How fast an arm tip travels, in pixels per second.

        The number that decides whether a spinner nudges a racer or fires it
        across the course, so it is worth being able to read directly.
        """
        return abs(math.radians(self.angular_speed)) * self.reach

    def arm_angles(self, seconds: float) -> tuple[float, ...]:
        """Each arm world angle in degrees at a moment of the rotation."""
        turned = self.start_angle + self.angular_speed * seconds
        step = 360.0 / self.arm_count
        return tuple(turned + index * step for index in range(self.arm_count))

    def arm_local_box(self) -> tuple[float, float, float]:
        """An arm as (length, thickness, centre distance from the hub)."""
        return (
            self.arm_length,
            self.arm_thickness,
            self.hub_radius + self.arm_length / 2.0,
        )

    def bounds(self) -> tuple[float, float, float, float]:
        """The circle the arms sweep, as a box. Conservative by construction."""
        return (
            self.x - self.reach,
            self.y - self.reach,
            self.x + self.reach,
            self.y + self.reach,
        )


@dataclass(frozen=True)
class Checkpoint:
    """One rung of the progress ladder.

    A checkpoint is a horizontal plane at `y`: a racer has reached it once
    its centre is at or below that line. Planes rather than trigger volumes
    because progress has to be a total order that no racer can skip, sneak
    past or register twice - and because ranking needs to interpolate
    between two rungs, which a volume cannot answer.

    `respawn` is a point known to be clear of geometry just past the plane.
    It is where a stuck or escaped racer is put back, so it is part of the
    course description rather than something recovery code guesses at.
    """

    index: int
    name: str
    y: float
    respawn: tuple[float, float]


@dataclass(frozen=True)
class RacerSpawn:
    """A slot on the starting grid. Racers are assigned to slots by seed."""

    slot: int
    x: float
    y: float


@dataclass(frozen=True)
class CourseSection:
    """A named stretch of course, for the camera, the HUD and debugging."""

    name: str
    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class RaceCourse:
    """Everything a race needs to exist, and nothing about how it is drawn."""

    course_id: str
    width: float
    top: float
    bottom: float
    pieces: tuple[CoursePiece, ...]
    spinners: tuple[SpinnerSpec, ...]
    checkpoints: tuple[Checkpoint, ...]
    spawns: tuple[RacerSpawn, ...]
    sections: tuple[CourseSection, ...]
    # How far outside the course a racer may get before it counts as lost.
    # Generous on purpose: this is the net under the geometry, not a rule.
    out_of_bounds_margin: float = 320.0
    metadata: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        indices = [checkpoint.index for checkpoint in self.checkpoints]
        if indices != list(range(len(indices))):
            raise ValueError("checkpoints must be indexed 0..n-1 in order")
        if len(indices) < 2:
            raise ValueError("a course needs at least a start and a finish")
        ys = [checkpoint.y for checkpoint in self.checkpoints]
        if any(later <= earlier for earlier, later in zip(ys, ys[1:])):
            raise ValueError("checkpoint planes must increase down the course")

    # --- the ladder ---

    @property
    def start(self) -> Checkpoint:
        return self.checkpoints[0]

    @property
    def finish(self) -> Checkpoint:
        return self.checkpoints[-1]

    @property
    def finish_y(self) -> float:
        return self.finish.y

    @property
    def last_index(self) -> int:
        return len(self.checkpoints) - 1

    def checkpoint(self, index: int) -> Checkpoint:
        return self.checkpoints[max(0, min(self.last_index, index))]

    def reached_index(self, y: float) -> int:
        """The highest checkpoint a racer at height `y` has passed."""
        reached = -1
        for checkpoint in self.checkpoints:
            if y >= checkpoint.y:
                reached = checkpoint.index
            else:
                break
        return reached

    def progress_at(self, y: float) -> float:
        """Course progress as a continuous number, in checkpoint units.

        0.0 is the start plane, `last_index` is the finish plane, and the
        fraction between two rungs is the racer share of the gap. This is
        the primary ranking key, and it is monotonic in `y` by construction,
        so it cannot rank a racer that is further down the course lower than
        one that is not.
        """
        index = self.reached_index(y)
        if index < 0:
            # Still above the start plane, in the pen. Report the shortfall
            # as a negative fraction of the run-up so grid order still ranks.
            first = self.checkpoints[0]
            run_up = max(1.0, first.y - self.top)
            return (y - first.y) / run_up
        if index >= self.last_index:
            return float(self.last_index)
        here = self.checkpoints[index]
        following = self.checkpoints[index + 1]
        span = following.y - here.y
        return index + max(0.0, min(1.0, (y - here.y) / span))

    # --- geometry ---

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def gates(self) -> tuple[CoursePiece, ...]:
        return tuple(piece for piece in self.pieces if piece.is_gate)

    @property
    def jump_pads(self) -> tuple[CoursePiece, ...]:
        return tuple(piece for piece in self.pieces if piece.is_jump_pad)

    def out_of_bounds(self, x: float, y: float) -> bool:
        margin = self.out_of_bounds_margin
        return not (
            -margin <= x <= self.width + margin
            and self.top - margin <= y <= self.bottom + margin
        )

    def section_at(self, y: float) -> CourseSection | None:
        for section in self.sections:
            if section.top <= y < section.bottom:
                return section
        if self.sections and y >= self.bottom:
            return self.sections[-1]
        return None

    def __iter__(self) -> Iterator[CoursePiece]:
        return iter(self.pieces)

    def __len__(self) -> int:
        return len(self.pieces)


def box_between(
    piece_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float,
) -> ObstacleSpec:
    """A box spanning two points: the primitive every ramp is built from.

    Course geometry is naturally described by where a surface begins and
    ends, while `ObstacleSpec.box` wants a centre, a size and an angle. This
    is the one conversion between the two, so no course builder ever does
    trigonometry by hand.
    """
    (x1, y1), (x2, y2) = start, end
    length = math.dist(start, end)
    if length <= 0.0:
        raise ValueError("a course box needs two distinct endpoints")
    return ObstacleSpec.box(
        obstacle_id=piece_id,
        x=(x1 + x2) / 2.0,
        y=(y1 + y2) / 2.0,
        width=length,
        height=thickness,
        rotation_degrees=math.degrees(math.atan2(y2 - y1, x2 - x1)),
    )
