"""Rigs that measure where a marble's energy goes, and how that depends on dt.

The production report's most important open question is section 12.1: bowl
revolutions rise monotonically with the physics rate - 2.32, 2.97, 4.58, 15.27
turns at 120, 240, 480, 960 Hz - and do not converge. The whole-machine number
that shows it is also the worst possible instrument for explaining it, because
a run of the whole machine confounds at least six things: the release spread of
an eight-marble queue, marble-on-marble collisions, the spout, the drain lip,
the curve underneath, and the bowl itself. Every one of those is rate sensitive
in its own right.

So this module measures *one marble, on one surface, with nothing else in the
world*, and it does it in two rigs.

## The floor rig

A marble launched in perfect rolling on a level surface, with every rolling,
spinning and damping term at exactly zero. In continuous time it should roll
forever. Whatever deceleration it has is entirely numerical, and the rig
reports it as an effective rolling-resistance coefficient `Crr = a / g` so that
it can be compared directly against the 0.001 to 0.002 a real glass marble
measures and against the coefficient of an explicit model.

The floors are chosen to take the answer apart:

* `plane` is `btStaticPlaneShape` - an analytic half-space with no triangles at
  all. Any loss here is the solver's, not the mesh's.
* `box` is a large mass-zero box - analytic, but a different collision
  algorithm from the plane, so a loss that appears on one and not the other is
  an algorithm artefact rather than a contact-solver one.
* `trimesh` is the same flat surface as a triangle mesh, and `trimesh_fine` is
  the same flat surface with 64 times as many triangles. Both are *exactly
  level*: their triangle edges are coplanar, so a sphere crossing one is not
  going over a bump. A difference between them is therefore pure
  contact-feature switching - the manifold being rebuilt as the marble moves
  from one triangle to the next - and not geometry.
* `faceted` is a deliberately corrugated mesh with a stated dihedral kink at
  every edge, which is the geometric part of the tessellation cost with the
  curvature removed.

Sweeping the physics rate over that set answers the question the whole-machine
table cannot: is the rate sensitivity in the mesh, or in the solver?

## The orbit rig

One marble, one bowl, no start module, no curve, no queue. The marble is placed
on the dish at a stated radius and given exactly the speed a circular orbit
needs there, `v = sqrt(g r tan(theta))`, plus the spin that makes it roll
rather than skid. Nothing pushes it after that.

That is the production bowl's own geometry, its own collider, its own
materials, and it isolates the bowl from everything upstream and downstream of
it. What comes out is a decay curve rather than a single number, and the decay
*rate* is the quantity a rate-independent physical model would hold constant
across 120, 240 and 480 Hz. `revolutions` is reported too, because it is what
the production report quotes and comparisons have to be able to reach it, but
it is a poor instrument: it is the integral of the decay over a threshold
crossing, so it amplifies small changes near the end of the run.

Four starting azimuths per configuration by default, spread over one mesh
segment. A single trajectory samples one phase of the marble against the
tessellation, exactly as one starting offset samples one phase of a tunnelling
test, and a bowl is chaotic enough that one run is an anecdote.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.hardening import apply_resistance
from marble3d.mesh import TriMesh
from marble3d.modules.bowl import BowlModule, BowlSpec
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.world import MarbleWorld, rolling_spin

__all__ = [
    "machine_with_sagitta",
    "FLOORS",
    "FloorResult",
    "measure_floor",
    "OrbitResult",
    "measure_orbit",
    "orbit_speed",
    "level_mesh",
    "faceted_mesh",
    "exponential_fit",
    "linear_fit",
]

# Sampling for every series this module produces. A quarter of 240 and a whole
# divisor of every rate in the matrix, so two rates' series line up sample for
# sample and can be differenced without interpolation.
SAMPLE_HZ = 60

# Two analytic surfaces, a sweep of level triangle meshes from 50 wu triangles
# down to 3.125 wu - one hundred times the marble and six times it - and one
# corrugated mesh at the finest resolution. `faceted64` differs from
# `trimesh64` only by a 0.02 wu dihedral kink at every edge, so the pair
# separates "the collider has edges" from "the collider has bumps".
BOWL_SAGITTA = 0.02        # what `BowlModule` defaults to, restated for callers


def machine_with_sagitta(sagitta: float = BOWL_SAGITTA, start: Any = None):
    """`start_bowl_curve`, with the bowl's collider resolution as a parameter.

    Assembled here rather than by widening `marble3d.machines.start_bowl_curve`,
    because section 18 of the hardening brief asks for the module and machine
    API that `marble-v1` is integrating against to be left exactly as it is. The
    socket algebra below is `machines.py`'s, verbatim; the only difference is the
    `sagitta_limit` handed to the bowl, and at the default this returns the same
    machine `start_bowl_curve()` does.

    Collider resolution turns out to be one of the two effective levers on the
    dissipation, so a study that could not vary it would have missed half the
    answer - and a renderer is free to tessellate the same analytic surface as
    finely as it likes, because the collider is not the thing that gets drawn.
    """
    from marble3d.machine import Machine
    from marble3d.machines import DRAIN_FALL
    from marble3d.modules.curve import CurveModule
    from marble3d.modules.start import StartModule

    machine = Machine("start_bowl_curve")
    bowl = machine.anchor(BowlModule("bowl", None, sagitta_limit=sagitta))
    start_module = machine.add(StartModule("start", start))
    curve = machine.add(CurveModule("curve"))
    machine.connect(start_module, "exit", bowl, "entry")
    machine.connect(bowl, "drain", curve, "entry", fall=DRAIN_FALL)
    return machine


FLOORS = (
    "plane",
    "box",
    "trimesh8",
    "trimesh16",
    "trimesh32",
    "trimesh64",
    "trimesh128",
    "faceted64",
)


# --- surfaces -------------------------------------------------------------


def level_mesh(size: float = 400.0, cells: int = 8) -> TriMesh:
    """A perfectly level triangle mesh. Every edge is coplanar with its neighbours.

    Deliberately the same construction as `marble3d.experiments.flat_plane`, so
    that the floor rig's `trimesh` row and the production report's
    tessellation-floor number are the same measurement, and `cells` is the only
    thing that changes between the coarse and fine rows.
    """
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
    return TriMesh(vertices, indices, f"level_{cells}")


def faceted_mesh(
    size: float = 400.0, cells: int = 64, sagitta: float = 0.02
) -> TriMesh:
    """A corrugated floor: the geometric part of tessellation, with no curvature.

    Alternate rows of vertices are lifted by `sagitta`, so a marble rolling
    across it climbs and descends a ridge every `size / cells` and meets a
    dihedral kink of `4 * sagitta / (size / cells)` radians at each edge. That
    is what a marble crossing a ring of a revolved collider meets, without the
    orbit, the drain or the curvature confounding it - so the difference
    between this and `trimesh_fine` at the same rate is the cost of the kink
    alone.

    Mean height is held at zero so that the resting height, and therefore the
    normal load, is the same as on the level floors.
    """
    step = size / cells
    vertices: list[tuple[float, float, float]] = []
    for row in range(cells + 1):
        lift = sagitta if row % 2 else -sagitta
        for column in range(cells + 1):
            vertices.append(
                (-0.5 * size + step * row, lift, -0.5 * size + step * column)
            )
    indices: list[int] = []
    for row in range(cells):
        for column in range(cells):
            a = row * (cells + 1) + column
            b, c, d = a + 1, a + cells + 1, a + cells + 2
            indices.extend((a, c, b, b, c, d))
    return TriMesh(vertices, indices, f"faceted_{cells}_{sagitta:g}")


FLOOR_SIZE = 400.0


def floor_edge(floor: str) -> float:
    """The triangle edge length a floor name implies, or 0 for an analytic one.

    The unit the edge-crossing hypothesis is stated in. A marble at `v` crosses
    `v / edge` of them a second, so if the loss is per crossing then `Crr`
    should be proportional to `1 / edge` and independent of everything else.
    """
    if floor in ("plane", "box"):
        return 0.0
    digits = "".join(character for character in floor if character.isdigit())
    return FLOOR_SIZE / int(digits or 8)


def _place_floor(world: MarbleWorld, floor: str) -> None:
    """Put the named surface in the world.

    `trimesh<N>` and `faceted<N>` take the grid resolution in the name, because
    the whole point of the floor rig is a sweep over it and a named constant per
    resolution would be five constants that mean the same thing.
    """
    if floor == "plane":
        world.add_static_plane(owner="floor")
    elif floor == "box":
        world.add_kinematic_box(
            (200.0, 20.0, 200.0), Transform((0.0, -20.0, 0.0)), owner="floor"
        )
    elif floor.startswith("trimesh"):
        world.add_static_mesh(
            level_mesh(FLOOR_SIZE, int(FLOOR_SIZE / floor_edge(floor))), owner="floor"
        )
    elif floor.startswith("faceted"):
        world.add_static_mesh(
            faceted_mesh(FLOOR_SIZE, int(FLOOR_SIZE / floor_edge(floor))), owner="floor"
        )
    else:
        raise ValueError(f"unknown floor {floor!r}; expected one of {FLOORS}")


# --- fits ----------------------------------------------------------------


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Ordinary least squares, returning (slope, intercept). Zeroes on <2 points."""
    count = len(xs)
    if count < 2:
        return (0.0, ys[0] if ys else 0.0)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 0.0:
        return (0.0, mean_y)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return (slope, mean_y - slope * mean_x)


def exponential_fit(times: Sequence[float], values: Sequence[float]) -> float:
    """The decay constant `k` in `E ~ exp(-k t)`, by least squares on `ln E`.

    Returns zero rather than raising when the series never becomes positive,
    because a configuration that dissipates nothing at all is a legitimate
    outcome of this study and should read as `k = 0` rather than as an error.
    """
    pairs = [(t, v) for t, v in zip(times, values) if v > 0.0]
    if len(pairs) < 3:
        return 0.0
    slope, _ = linear_fit([t for t, _ in pairs], [math.log(v) for _, v in pairs])
    return -slope


# --- the floor rig --------------------------------------------------------


@dataclass(frozen=True)
class FloorResult:
    """What a marble rolling on a level surface actually lost."""

    floor: str
    physics_hz: int
    speed: float
    seconds: float
    crr: float                     # a / g, the effective rolling resistance
    deceleration: float            # wu/s^2
    final_speed: float
    slip_fraction: float           # |v - w x r| / |v| at the end: is it still rolling?
    mean_contacts: float
    contact_fraction: float
    height_rms: float              # RMS deviation of the centre from r above the floor
    worst_penetration: float
    wall_seconds: float

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


def measure_floor(
    floor: str = "trimesh",
    config: CoreConfig | None = None,
    speed: float = 30.0,
    seconds: float = 2.0,
    settle: float = 0.25,
) -> FloorResult:
    """Roll a marble on `floor` and report every way it lost energy.

    The marble is launched already rolling - `omega = (n x v) / r` - so nothing
    about the launch presupposes a skid, and the first `settle` seconds are
    discarded because the transition from a launch to a steady manifold is a
    real transient. The measured `crr` is `a / g`, directly comparable with the
    coefficient of an explicit rolling-resistance model and with the 0.001 to
    0.002 a real glass marble on a hard track measures.
    """
    config = config or DEFAULT_CONFIG
    resistance = config.hardening.resistance
    dt = config.physics.dt
    started = time.perf_counter()

    world = MarbleWorld(config)
    try:
        _place_floor(world, floor)
        world.add_marble(
            0,
            (0.0, config.marble.radius, 0.0),
            (speed, 0.0, 0.0),
            rolling_spin((0.0, 1.0, 0.0), (speed, 0.0, 0.0), config.marble.radius),
        )

        def advance(ticks: int) -> tuple[int, int, float, float]:
            contacts = 0
            with_contact = 0
            worst = 0.0
            height_sq = 0.0
            for _ in range(ticks):
                if resistance.active:
                    apply_resistance(world, resistance, dt)
                world.step()
                points = world.contacts()
                contacts += len(points)
                if points:
                    with_contact += 1
                for point in points:
                    worst = min(worst, point.distance)
                height = world.marble_state(0)[0][1] - config.marble.radius
                height_sq += height * height
            return (contacts, with_contact, worst, height_sq)

        settle_ticks = int(round(settle / dt))
        run_ticks = int(round(seconds / dt))
        advance(settle_ticks)
        first = world.marble_state(0)
        contacts, with_contact, worst, height_sq = advance(run_ticks)
        second = world.marble_state(0)
    finally:
        world.close()

    start_speed = math.dist(first[2], (0.0, 0.0, 0.0))
    end_speed = math.dist(second[2], (0.0, 0.0, 0.0))
    deceleration = (start_speed - end_speed) / seconds
    velocity, spin = second[2], second[3]
    radius = config.marble.radius
    # The contact point of a sphere on a level floor is one radius below the
    # centre, so its velocity is `v + w x (-r y)` = `(vx + r wz, 0, vz - r wx)`.
    # Whatever is left of that is slip, and a rig that has quietly stopped
    # rolling is measuring sliding friction instead of what it claims to.
    slip = math.hypot(velocity[0] + radius * spin[2], velocity[2] - radius * spin[0])

    return FloorResult(
        floor=floor,
        physics_hz=config.physics.physics_hz,
        speed=speed,
        seconds=seconds,
        crr=deceleration / config.gravity,
        deceleration=deceleration,
        final_speed=end_speed,
        slip_fraction=slip / max(end_speed, 1e-9),
        mean_contacts=contacts / max(run_ticks, 1),
        contact_fraction=with_contact / max(run_ticks, 1),
        height_rms=math.sqrt(height_sq / max(run_ticks, 1)),
        worst_penetration=worst,
        wall_seconds=time.perf_counter() - started,
    )


# --- the orbit rig --------------------------------------------------------


def orbit_speed(spec: BowlSpec, radius: float, gravity: float) -> float:
    """The speed a circular orbit needs at `radius` on the dish.

    A marble held on a surface of slope `theta` by a normal force `N` has
    `N cos(theta) = mg` vertically and `N sin(theta) = m v^2 / r` inward, so
    `v^2 = g r tan(theta)` and `tan(theta)` is the dish's own slope. Friction is
    not in it: a steady circular orbit needs no tangential force, which is why
    the same expression is right for a marble that rolls and one that skids.
    """
    return math.sqrt(max(0.0, gravity * radius * spec.slope(radius)))


@dataclass(frozen=True)
class OrbitResult:
    """One marble, one bowl, from release to drain."""

    physics_hz: int
    launch_radius: float
    launch_speed: float
    azimuth: float
    turns: float
    seconds: float
    outcome: str                   # "drained", "escaped", "timeout"
    energy_decay: float            # k in E ~ exp(-k t), per second
    energy_loss_rate: float        # mean dE/dt over the orbit, wu^2/s^3
    equivalent_crr: float          # the loss as a rolling-resistance coefficient
    radial_rate: float             # mean dr/dt, wu/s
    peak_radius: float
    entry_radius: float
    mean_speed: float
    mean_contacts: float
    contact_fraction: float
    surface_rms: float             # RMS of |centre - surface| - r, the hop/dig
    worst_penetration: float
    steps: int
    wall_seconds: float
    series: list[tuple[float, float, float, float]] = field(default_factory=list)

    def to_json(self, with_series: bool = False) -> dict[str, Any]:
        payload = {
            key: value for key, value in self.__dict__.items() if key != "series"
        }
        if with_series:
            payload["series"] = [[round(v, 6) for v in row] for row in self.series]
        return payload


def _dish_normal(spec: BowlSpec, radius: float) -> tuple[float, float]:
    """The outward surface normal in the meridian plane, as (radial, vertical)."""
    slope = spec.slope(radius)
    length = math.hypot(1.0, slope)
    return (-slope / length, 1.0 / length)


def measure_orbit(
    config: CoreConfig | None = None,
    spec: BowlSpec | None = None,
    sagitta_limit: float = 0.02,
    launch_factor: float = 0.86,
    speed_factor: float = 1.0,
    azimuth: float = 0.0,
    duration: float = 60.0,
    dish_only: bool = True,
) -> OrbitResult:
    """Place one marble in a circular orbit in a bare bowl and watch it decay.

    `launch_factor` is the fraction of the rim radius the marble is placed at.
    0.86 puts it just inside the rim, on the steep part of the dish, well clear
    of the spout's footprint and far enough from the drain lip that the run
    measures an orbit rather than a drain. `dish_only` leaves the feed spout out
    of the world entirely, because the spout is a roof over the outer wall and a
    marble that climbs into it is measuring the spout.

    Nothing is applied to the marble after release except gravity, contact and -
    if one is configured - the explicit resistance model. There is no radial
    force, no attraction and no spiral anywhere in this function.
    """
    config = config or DEFAULT_CONFIG
    spec = spec or BowlSpec()
    resistance = config.hardening.resistance
    dt = config.physics.dt
    stride = max(1, config.physics.physics_hz // SAMPLE_HZ)
    radius_marble = config.marble.radius
    started = time.perf_counter()

    bowl = BowlModule("bowl", spec, sagitta_limit=sagitta_limit)
    meshes = bowl.local_colliders()
    contact_radius = launch_factor * spec.rim_radius
    speed = speed_factor * orbit_speed(spec, contact_radius, config.gravity)

    normal_r, normal_y = _dish_normal(spec, contact_radius)
    centre_radius = contact_radius + radius_marble * normal_r
    centre_height = spec.height(contact_radius) + radius_marble * normal_y
    cosine, sine = math.cos(azimuth), math.sin(azimuth)
    position = (centre_radius * cosine, centre_height, centre_radius * sine)
    # Tangential, in the direction of increasing azimuth.
    velocity = (-speed * sine, 0.0, speed * cosine)
    normal = (normal_r * cosine, normal_y, normal_r * sine)

    # The energy datum: where the marble's centre sits at rest on the lowest
    # part of the dish, which is the tangent point of the drain lip. Subtracting
    # it is what makes the decay curve approach zero rather than approaching
    # `g r`, and an exponential fit against the wrong asymptote reads as a
    # smaller decay constant than the run actually had.
    lip = bowl.lip_contact_radius
    floor = spec.height(lip) + radius_marble * _dish_normal(spec, lip)[1]
    escape_radius = spec.max_radius + MARBLE_DIAMETER
    limit_ticks = int(round(duration * config.physics.physics_hz))

    world = MarbleWorld(config)
    series: list[tuple[float, float, float, float]] = []
    try:
        for mesh in meshes if not dish_only else meshes[:1]:
            world.add_static_mesh(mesh, owner="bowl")
        world.add_marble(
            0, position, velocity, rolling_spin(normal, velocity, radius_marble)
        )

        accumulated = 0.0
        previous_angle = math.atan2(position[2], position[0])
        peak = centre_radius
        contacts = 0
        with_contact = 0
        worst = 0.0
        surface_sq = 0.0
        surface_samples = 0
        speed_sum = 0.0
        outcome = "timeout"
        ticks = 0

        while ticks < limit_ticks:
            if resistance.active:
                apply_resistance(world, resistance, dt)
            world.step()
            ticks += 1
            points = world.contacts()
            contacts += len(points)
            if points:
                with_contact += 1
            for point in points:
                worst = min(worst, point.distance)

            (x, y, z), _, linear, spin = world.marble_state(0)
            if not all(math.isfinite(value) for value in (x, y, z)):
                outcome = "diverged"
                break
            here = math.hypot(x, z)
            angle = math.atan2(z, x)
            accumulated += math.remainder(angle - previous_angle, 2.0 * math.pi)
            previous_angle = angle
            peak = max(peak, here)
            speed_sum += math.dist(linear, (0.0, 0.0, 0.0))
            # Only on the dish proper: over the drain lip and the shaft the
            # `height(r)` formula is not the surface the marble is touching, so
            # sampling there would report the fillet as a hop.
            if points and lip + radius_marble < here <= spec.max_radius:
                gap = (y - spec.height(here)) * _dish_normal(spec, here)[1] - radius_marble
                surface_sq += gap * gap
                surface_samples += 1

            if ticks % stride == 0:
                energy = (
                    0.5 * sum(value * value for value in linear)
                    + 0.2 * radius_marble * radius_marble
                    * sum(value * value for value in spin)
                    + config.gravity * y
                )
                series.append(
                    (ticks * dt, here, math.dist(linear, (0.0, 0.0, 0.0)), energy)
                )

            if y < spec.shaft_bottom:
                outcome = "drained"
                break
            if here > escape_radius:
                outcome = "escaped"
                break
    finally:
        world.close()

    seconds = ticks * dt
    # Fit over the orbiting part only: the last tenth of a second is the drain,
    # where the marble is falling rather than orbiting and its energy drops for
    # a reason that is not dissipation.
    orbiting = [row for row in series if row[0] <= max(0.0, seconds - 0.25)]
    times = [row[0] for row in orbiting]
    above_floor = [row[3] - config.gravity * floor for row in orbiting]
    decay = exponential_fit(times, above_floor)
    radial_rate, _ = linear_fit(times, [row[1] for row in orbiting])
    loss_rate = (
        (above_floor[0] - above_floor[-1]) / max(times[-1] - times[0], 1e-9)
        if len(orbiting) > 1
        else 0.0
    )
    mean_speed = speed_sum / max(ticks, 1)
    # An orbiting marble loses `dE/dt = -a v` to a resistance of deceleration
    # `a`, so `Crr = a / g = (dE/dt) / (g v)` makes this rig's answer directly
    # comparable with the floor rig's and with a materials table.
    equivalent = loss_rate / max(config.gravity * mean_speed, 1e-9)

    return OrbitResult(
        physics_hz=config.physics.physics_hz,
        launch_radius=contact_radius,
        launch_speed=speed,
        azimuth=azimuth,
        turns=abs(accumulated) / (2.0 * math.pi),
        seconds=seconds,
        outcome=outcome,
        energy_decay=decay,
        energy_loss_rate=loss_rate,
        equivalent_crr=equivalent,
        radial_rate=radial_rate,
        peak_radius=peak,
        entry_radius=centre_radius,
        mean_speed=mean_speed,
        mean_contacts=contacts / max(ticks, 1),
        contact_fraction=with_contact / max(ticks, 1),
        surface_rms=math.sqrt(surface_sq / max(surface_samples, 1)),
        worst_penetration=worst,
        steps=ticks,
        wall_seconds=time.perf_counter() - started,
        series=series,
    )


def orbit_sweep(
    config: CoreConfig | None = None,
    spec: BowlSpec | None = None,
    sagitta_limit: float = 0.02,
    phases: int = 4,
    **kwargs: Any,
) -> list[OrbitResult]:
    """`measure_orbit` at `phases` starting azimuths, spread over one mesh segment.

    A single trajectory samples one phase of the marble against the collider's
    meridians, the same way one starting offset samples one phase of a
    tunnelling test. The segment count is the bowl's own, so the sweep covers
    exactly one period of the tessellation and no more.
    """
    spec = spec or BowlSpec()
    bowl = BowlModule("bowl", spec, sagitta_limit=sagitta_limit)
    span = 2.0 * math.pi / bowl.segments
    return [
        measure_orbit(
            config=config,
            spec=spec,
            sagitta_limit=sagitta_limit,
            azimuth=span * index / phases,
            **kwargs,
        )
        for index in range(phases)
    ]


def summarise_orbits(results: Sequence[OrbitResult]) -> dict[str, Any]:
    """Median-of-phases for the numbers a comparison is made on."""

    def median(values: Sequence[float]) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return 0.5 * (ordered[middle - 1] + ordered[middle])

    return {
        "phases": len(results),
        "physics_hz": results[0].physics_hz if results else 0,
        "turns": median([r.turns for r in results]),
        "turns_min": min((r.turns for r in results), default=0.0),
        "turns_max": max((r.turns for r in results), default=0.0),
        "seconds": median([r.seconds for r in results]),
        "energy_decay": median([r.energy_decay for r in results]),
        "energy_loss_rate": median([r.energy_loss_rate for r in results]),
        "equivalent_crr": median([r.equivalent_crr for r in results]),
        "radial_rate": median([r.radial_rate for r in results]),
        "mean_contacts": median([r.mean_contacts for r in results]),
        "contact_fraction": median([r.contact_fraction for r in results]),
        "surface_rms": median([r.surface_rms for r in results]),
        "worst_penetration": min((r.worst_penetration for r in results), default=0.0),
        "peak_radius": max((r.peak_radius for r in results), default=0.0),
        "wall_seconds": sum(r.wall_seconds for r in results),
        "outcomes": sorted({r.outcome for r in results}),
    }
