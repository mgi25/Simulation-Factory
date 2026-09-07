"""Measurements of what the engine does, as opposed to what it was told.

Every function here builds a small world, runs it, and returns a number. They
exist because sections 7, 11, 23 and 27 of the brief all ask the same thing in
different words: do not report a configured value as if it were an observed
one. A friction coefficient that Bullet combines by multiplying is not the
coefficient that was set; a collision margin moves a resting surface by an
amount nobody wrote down; a physics rate is safe or unsafe against a speed the
machine produces rather than against a rule of thumb.

Both `tests/test_marble3d_*.py` and `tools/marble3d_validate.py` call these, so
the number in the regression test and the number in the report come from the
same code and cannot drift apart.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform, quat_from_axis_angle
from marble3d.materials import rolling_acceleration, rolling_threshold, sliding_acceleration
from marble3d.mesh import TriMesh
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.world import MarbleWorld

__all__ = [
    "flat_plane",
    "InclineResult",
    "measure_incline",
    "measure_resting_height",
    "measure_contact_separation",
    "measure_tunnelling",
    "measure_rolling_resistance",
    "measure_throughput",
]


def flat_plane(size: float = 400.0, cells: int = 8) -> TriMesh:
    """A big level trimesh, for the measurements that need a known surface."""
    vertices: list[tuple[float, float, float]] = []
    for row in range(cells + 1):
        for column in range(cells + 1):
            vertices.append(
                (
                    -0.5 * size + size * row / cells,
                    0.0,
                    -0.5 * size + size * column / cells,
                )
            )
    indices: list[int] = []
    for row in range(cells):
        for column in range(cells):
            a = row * (cells + 1) + column
            b, c, d = a + 1, a + cells + 1, a + cells + 2
            indices.extend((a, c, b, b, c, d))
    return TriMesh(vertices, indices, "flat_plane")


@dataclass(frozen=True)
class InclineResult:
    """What a marble did on a slope, and what the two models predict."""

    slope_degrees: float
    measured_acceleration: float
    rolling_prediction: float
    sliding_prediction: float
    inferred_friction: float
    threshold_friction: float
    rolls: bool

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


def measure_incline(
    slope_degrees: float,
    config: CoreConfig | None = None,
    surface_friction: float | None = None,
    seconds: float = 0.6,
    settle: float = 0.25,
) -> InclineResult:
    """Release a marble on a slope and measure what it actually does.

    A solid sphere that rolls without slipping accelerates at `(5/7) g sin`;
    one that skids accelerates at `g (sin - mu cos)`. Measuring the
    acceleration therefore both tells you which regime the engine chose and,
    in the skidding case, recovers the friction coefficient Bullet is really
    applying - which is the only way to find out what the product of two
    per-body coefficients came to.

    The marble is dropped from rest with no spin, so nothing about the launch
    presupposes rolling; and the first `settle` seconds are discarded, because
    the transition from slipping to rolling is a real transient that would
    otherwise be averaged into the answer.
    """
    config = config or DEFAULT_CONFIG
    if surface_friction is not None:
        config = config.with_overrides(marble__surface_friction=surface_friction)
    angle = math.radians(slope_degrees)

    world = MarbleWorld(config)
    try:
        tilt = Transform((0.0, 0.0, 0.0), quat_from_axis_angle((0.0, 0.0, 1.0), angle))
        world.add_static_mesh(flat_plane(), tilt, owner="incline")
        # Downhill is +X rotated by the tilt about Z... a positive rotation
        # about +Z lifts +X, so the marble runs toward -X.
        start = tilt.apply((0.0, MARBLE_RADIUS, 0.0))
        world.add_marble(0, start)
        dt = config.physics.dt
        for _ in range(int(settle / dt)):
            world.step()
        first = world.marble_state(0)[2]
        for _ in range(int(seconds / dt)):
            world.step()
        second = world.marble_state(0)[2]
    finally:
        world.close()

    measured = (math.dist(second, (0.0, 0.0, 0.0)) - math.dist(first, (0.0, 0.0, 0.0))) / seconds
    rolling = rolling_acceleration(config.gravity, angle)
    # Invert the sliding law for the coefficient that would produce what was
    # measured. Meaningless when the marble is rolling, which is why `rolls`
    # is reported alongside it rather than the caller having to guess.
    inferred = (math.sin(angle) - measured / config.gravity) / math.cos(angle)
    return InclineResult(
        slope_degrees=slope_degrees,
        measured_acceleration=measured,
        rolling_prediction=rolling,
        sliding_prediction=sliding_acceleration(
            config.gravity, angle, config.marble.surface_friction
        ),
        inferred_friction=inferred,
        threshold_friction=rolling_threshold(angle),
        rolls=abs(measured - rolling) < 0.03 * rolling,
    )


def measure_resting_height(
    config: CoreConfig | None = None, margin: float | None = None, seconds: float = 1.0
) -> float:
    """How far above a flat trimesh a marble comes to rest, minus its radius.

    Zero is correct and zero is what it measures, at every margin from 0 to
    0.2. That was not the expectation - the standard account is that a static
    trimesh collides one margin outside its triangles, so a marble should hover
    by the margin - and it is wrong on this build, because split-impulse
    penetration recovery resolves to contact whatever the margin was. What the
    margin actually changes is `measure_contact_gap`.
    """
    config = config or DEFAULT_CONFIG
    if margin is not None:
        config = config.with_overrides(collider__mesh_margin=margin)
    world = MarbleWorld(config)
    try:
        world.add_static_mesh(flat_plane(), owner="floor")
        world.add_marble(0, (0.0, MARBLE_RADIUS + 0.5 * MARBLE_DIAMETER, 0.0))
        for _ in range(int(seconds / config.physics.dt)):
            world.step()
        height = world.marble_state(0)[0][1]
    finally:
        world.close()
    return height - config.marble.radius


def measure_contact_gap(
    config: CoreConfig | None = None, margin: float | None = None, step: float = 0.001
) -> float:
    """The largest gap at which a marble and a trimesh still report a contact.

    This, and not the resting height, is what a trimesh's collision margin
    changes. A large margin makes Bullet generate a contact while the marble is
    still a margin away from the surface, so in a channel barely wider than a
    marble the marble is held off both walls before it reaches either - it is
    effectively fatter than it is. The resting height on an open surface is
    unaffected, because penetration recovery resolves to contact whatever the
    margin was.
    """
    config = config or DEFAULT_CONFIG
    if margin is not None:
        config = config.with_overrides(collider__mesh_margin=margin)
    world = MarbleWorld(config)
    try:
        world.add_static_mesh(flat_plane(size=40.0, cells=4), owner="floor")
        for index in range(1, 400):
            gap = index * step
            world.add_marble(0, (0.0, MARBLE_RADIUS + gap, 0.0))
            world.pybullet.performCollisionDetection(physicsClientId=world.client)
            contacts = world.contacts()
            world.remove_marble(0)
            if not contacts:
                return gap - step
    finally:
        world.close()
    return math.inf


def measure_contact_separation(config: CoreConfig | None = None) -> tuple[float, float]:
    """The centre separation at which two marbles start and stop touching.

    Returns (largest separation that reports a contact, smallest that does
    not). The boundary should be one marble diameter: `btSphereShape` carries
    its collision margin *as* its radius, so two spheres touch when their
    centres are a diameter apart and not a margin sooner. Everything the
    machine's clearances assume rests on that, so it is measured.
    """
    config = config or DEFAULT_CONFIG
    diameter = config.marble.diameter
    touching = 0.0
    clear = math.inf
    for step in range(-8, 9):
        separation = diameter + step * 0.002 * diameter
        world = MarbleWorld(config)
        try:
            world.add_marble(0, (0.0, 0.0, 0.0))
            world.add_marble(1, (separation, 0.0, 0.0))
            world.pybullet.performCollisionDetection(physicsClientId=world.client)
            contacts = world.contacts()
        finally:
            world.close()
        if contacts:
            touching = max(touching, separation)
        else:
            clear = min(clear, separation)
    return touching, clear


def measure_tunnelling(
    speed: float,
    config: CoreConfig | None = None,
    thickness: float = 0.3,
    phases: int = 20,
    ccd: bool = True,
) -> int:
    """How many of `phases` starting offsets pass straight through a wall.

    A phase sweep rather than a single shot, because whether a marble tunnels
    depends on where in its step the wall falls, and one starting position
    tests one phase of a periodic failure.
    """
    config = config or DEFAULT_CONFIG
    if not ccd:
        config = config.with_overrides(marble__ccd_swept_radius=0.0)
    half = 0.5 * thickness
    wall = TriMesh(
        [
            (-half, -20.0, -20.0), (-half, 20.0, -20.0), (-half, 20.0, 20.0), (-half, -20.0, 20.0),
            (half, -20.0, -20.0), (half, 20.0, -20.0), (half, 20.0, 20.0), (half, -20.0, 20.0),
        ],
        [0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6],
        "tunnel_wall",
    )
    dt = config.physics.dt
    travel = speed * dt
    through = 0
    for phase in range(phases):
        world = MarbleWorld(config.with_overrides(gravity=0.0))
        try:
            world.add_static_mesh(wall, owner="wall")
            start = -20.0 - travel * phase / phases
            world.add_marble(0, (start, 0.0, 0.0), (speed, 0.0, 0.0))
            for _ in range(int(round(40.0 / travel)) + 20):
                world.step()
                if world.marble_state(0)[0][0] > 5.0:
                    through += 1
                    break
        finally:
            world.close()
    return through


def measure_rolling_resistance(
    config: CoreConfig | None = None,
    rolling_friction: float | None = None,
    speed: float = 30.0,
    seconds: float = 2.0,
) -> float:
    """The effective rolling-resistance coefficient, `Crr = a / g`.

    Measured on a flat trimesh, so the answer includes the dissipation the
    tessellation imposes on its own - which at zero rolling friction is the
    whole of it, and is the number that decided `MarbleConfig.rolling_friction`.
    """
    config = config or DEFAULT_CONFIG
    if rolling_friction is not None:
        config = config.with_overrides(marble__rolling_friction=rolling_friction)
    world = MarbleWorld(config)
    try:
        world.add_static_mesh(flat_plane(), owner="floor")
        world.add_marble(
            0,
            (0.0, MARBLE_RADIUS, 0.0),
            (speed, 0.0, 0.0),
            (0.0, 0.0, -speed / MARBLE_RADIUS),
        )
        dt = config.physics.dt
        for _ in range(int(0.25 / dt)):
            world.step()
        first = world.marble_state(0)[2][0]
        for _ in range(int(seconds / dt)):
            world.step()
        second = world.marble_state(0)[2][0]
    finally:
        world.close()
    return ((first - second) / seconds) / config.gravity


def measure_throughput(
    machine_factory,
    marble_counts: Sequence[int] = (8, 16, 32, 64),
    seed: int = 7,
    config: CoreConfig | None = None,
) -> list[dict[str, Any]]:
    """Simulated seconds per wall-clock second, at each field size.

    The number a thousand-seed search is planned against, so it is measured on
    the real machine at the real rate rather than on a benchmark rig.
    """
    from marble3d.simulation import simulate

    config = config or DEFAULT_CONFIG
    rows: list[dict[str, Any]] = []
    for count in marble_counts:
        started = time.perf_counter()
        replay = simulate(seed=seed, machine=machine_factory(count), config=config,
                          marble_count=count)
        wall = time.perf_counter() - started
        rows.append(
            {
                "marbles": count,
                "wall_seconds": wall,
                "sim_seconds": replay.summary["sim_seconds"],
                "times_realtime": replay.summary["sim_seconds"] / wall if wall else 0.0,
                "finished": replay.summary["finished"],
                "escaped": replay.summary["escaped"],
                "unfinished": replay.summary["unfinished"],
            }
        )
    return rows
