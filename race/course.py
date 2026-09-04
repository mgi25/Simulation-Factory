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
    "progress_along",
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
    """One node of the progress graph.

    A checkpoint is a horizontal plane at `y`, optionally narrowed to a
    corridor between `x_min` and `x_max`: a racer has reached it once its
    centre is at or below the line *and* inside the corridor. Planes rather
    than trigger volumes because progress has to be an order that no racer
    can skip, sneak past or register twice - and because ranking needs to
    interpolate between two nodes, which a volume cannot answer.

    `respawn` is a point known to be clear of geometry just past the plane.
    It is where a stuck or escaped racer is put back, so it is part of the
    course description rather than something recovery code guesses at.

    Two fields make branching possible, and both are inert on a course that
    does not branch:

    `branch` names the path this node belongs to. The empty string is the
    shared main line every racer travels; anything else is a node only
    racers on that branch can reach. A corridor is mandatory on a branch
    node, because the corridor is what physically separates one path from
    the other.

    `progress` is the course progress at this plane, and it - not `y`, and
    not `index` - is what ranking compares. On a linear course it is simply
    the node's position in the ladder, which is why the prototype behaves
    exactly as it always did. On a branching course, the nodes of both
    branches carry values inside the interval between the split and the
    rejoin, so two racers on different paths are compared by how far
    through their own route they are rather than by how far down the
    canvas they happen to be.
    """

    index: int
    name: str
    y: float
    respawn: tuple[float, float]
    branch: str = ""
    x_min: float | None = None
    x_max: float | None = None
    progress: float | None = None

    @property
    def value(self) -> float:
        """Course progress at this plane. Defaults to the ladder position."""
        return float(self.index) if self.progress is None else self.progress

    @property
    def corridor(self) -> bool:
        """Whether this plane is narrowed to part of the course width."""
        return self.x_min is not None or self.x_max is not None

    def covers(self, x: float) -> bool:
        """Whether `x` is inside this plane's corridor. Always true if open."""
        if self.x_min is not None and x < self.x_min:
            return False
        if self.x_max is not None and x > self.x_max:
            return False
        return True

    def reached_by(self, x: float, y: float) -> bool:
        """Whether a racer centred at `(x, y)` has passed this plane."""
        return y >= self.y and self.covers(x)


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

        names = [checkpoint.name for checkpoint in self.checkpoints]
        if len(set(names)) != len(names):
            raise ValueError("checkpoint names must be unique within a course")

        planes: dict[float, float] = {}
        for checkpoint in self.checkpoints:
            if checkpoint.branch and not checkpoint.corridor:
                raise ValueError(
                    f"branch checkpoint {checkpoint.name!r} needs a corridor:"
                    " a branch is only a branch if geometry separates it"
                )
            # Two nodes at the same course progress are alternatives - the
            # entries to the two sides of one split - and a racer choosing
            # between them must not be ranked by which one it takes. That
            # only holds if the two are the same plane.
            seen = planes.setdefault(checkpoint.value, checkpoint.y)
            if seen != checkpoint.y:
                raise ValueError(
                    f"checkpoints at progress {checkpoint.value} disagree about"
                    f" their plane: {seen} and {checkpoint.y}"
                )

        # Every route has to be a ladder in its own right: strictly further
        # along the course, and strictly further down it, at every rung.
        for branch in ("",) + self.branches:
            route = self.route(branch)
            label = branch or "main"
            values = [checkpoint.value for checkpoint in route]
            ys = [checkpoint.y for checkpoint in route]
            if any(later <= earlier for earlier, later in zip(values, values[1:])):
                raise ValueError(f"route {label} repeats or reverses course progress")
            if any(later <= earlier for earlier, later in zip(ys, ys[1:])):
                raise ValueError(
                    f"route {label} has planes that do not increase down the course"
                )

        finish = self.finish
        if finish.branch:
            raise ValueError("the finish must be on the main line, not on a branch")
        if sum(1 for cp in self.checkpoints if cp.value == finish.value) != 1:
            raise ValueError("a course needs exactly one finish plane")

        # Branches leaving the same point on the main line have to start at
        # the same course progress, or a racer would be ranked by which one
        # it entered rather than by how far along it has got.
        entries: dict[float, set[float]] = {}
        for branch in self.branches:
            first = next(cp for cp in self.route(branch) if cp.branch == branch)
            preceding = max(
                (cp.value for cp in self.main_line if cp.value < first.value),
                default=float("-inf"),
            )
            entries.setdefault(preceding, set()).add(first.value)
        for preceding, values in entries.items():
            if len(values) > 1:
                raise ValueError(
                    "branches leaving the same point must start at the same"
                    f" course progress; after {preceding} they start at"
                    f" {sorted(values)}"
                )

    # --- the progress graph ---

    @property
    def branches(self) -> tuple[str, ...]:
        """Every named path, in a fixed order. Empty on a linear course."""
        return tuple(sorted({cp.branch for cp in self.checkpoints if cp.branch}))

    @property
    def branching(self) -> bool:
        return bool(self.branches)

    @property
    def main_line(self) -> tuple[Checkpoint, ...]:
        """The nodes every racer passes, whichever branch it takes."""
        return tuple(cp for cp in self.checkpoints if not cp.branch)

    def route(self, branch: str = "") -> tuple[Checkpoint, ...]:
        """One complete path from start to finish, in progress order.

        The main line plus the nodes of `branch`. `branch=""` gives the
        shared spine on its own, which on a linear course is the whole
        ladder and is what `progress_at` reads.
        """
        nodes = [cp for cp in self.checkpoints if not cp.branch or cp.branch == branch]
        return tuple(sorted(nodes, key=lambda cp: (cp.value, cp.index)))

    @property
    def start(self) -> Checkpoint:
        return self.route()[0]

    @property
    def finish(self) -> Checkpoint:
        return max(self.checkpoints, key=lambda checkpoint: checkpoint.value)

    @property
    def finish_y(self) -> float:
        return self.finish.y

    @property
    def finish_index(self) -> int:
        return self.finish.index

    @property
    def max_progress(self) -> float:
        """Course progress at the finish plane. The top of the scale."""
        return self.finish.value

    @property
    def last_index(self) -> int:
        """Index of the finish plane. The linear reading of the ladder."""
        return self.finish.index

    def checkpoint(self, index: int) -> Checkpoint:
        return self.checkpoints[max(0, min(len(self.checkpoints) - 1, index))]

    def reached_index(self, y: float, x: float | None = None) -> int:
        """The furthest checkpoint a racer at `(x, y)` has passed.

        With no `x` only the main line is considered, which on a linear
        course is every checkpoint there is. Branch nodes cannot be answered
        without an x, because a corridor is what tells the two paths apart.
        """
        reached = -1
        best = float("-inf")
        for checkpoint in self.checkpoints:
            if checkpoint.branch and x is None:
                continue
            passed = y >= checkpoint.y if x is None else checkpoint.reached_by(x, y)
            if passed and checkpoint.value > best:
                best, reached = checkpoint.value, checkpoint.index
        return reached

    def progress_at(self, y: float) -> float:
        """Main-line course progress at height `y`, as a continuous number.

        0.0 is the start plane, `max_progress` is the finish plane, and the
        fraction between two nodes is the racer's share of the gap. On a
        linear course this is the whole ranking key. On a branching one it
        is the coarse reading that ignores which path was taken, and
        `race.progress` is what actually ranks a field there.
        """
        return progress_along(self.main_line, y, self.top)

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


def progress_along(
    route: tuple[Checkpoint, ...], y: float, top: float, reached: Checkpoint | None = None
) -> float:
    """Continuous course progress along one route at height `y`.

    `reached` is the furthest node the racer has actually passed, which on a
    branching course is not simply the last node above it: a racer can be
    below a plane it never entered the corridor of. Left out, the furthest
    node above `y` is used, which is the linear reading.

    Above the first node the shortfall is reported as a negative fraction of
    the run-up, so a field still on the grid ranks by how near the line it
    is rather than all tying on zero.
    """
    if not route:
        return 0.0
    if reached is None:
        passed = [node for node in route if y >= node.y]
        reached = passed[-1] if passed else None
    if reached is None:
        first = route[0]
        run_up = max(1.0, first.y - top)
        return (y - first.y) / run_up

    following = [node for node in route if node.value > reached.value]
    if not following:
        return reached.value
    upcoming = following[0]
    span = upcoming.y - reached.y
    if span <= 0.0:
        return reached.value
    share = max(0.0, min(1.0, (y - reached.y) / span))
    return reached.value + share * (upcoming.value - reached.value)


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
