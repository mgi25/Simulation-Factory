"""What the field looks like inside the chamber *before* anything opens.

## Why this exists, and why it is not an exit statistic

V1.7 measured the rotor start end to end and reported the trade it could not
escape: the chamber mixes well, but every rule that then *delivers* the field
to a central outlet - a floor gradient, a slow tail sweep - has to read where
each marble is, and the field's positions still carry whatever the mixing left
of the starting bay. So the better the delivery, the more of the bay it reads
back out.

That conclusion was drawn from exit ranks, which is an inference. Section 2 of
the V1.8 brief asks for the direct measurement instead: at the tick immediately
before the release would open, where is each marble, and how much does its
original bay still predict that?

The distinction matters because the two candidate diagnoses have the same exit
signature. If the chamber still orders the field, no release can fix it. If the
chamber has genuinely erased the bay, the release is the whole remaining
problem - and a release that does not read position at all is then worth
building. Only a pre-release measurement separates those.

## What is measured, and why each shape of relationship gets its own number

* **radius, x, z, speed** against the bay index, as plain Pearson r over every
  racer of every trial. `x` is the one that matters most: the eight bays are
  laid out along the module's own x, so `bay -> x` is the direct question "is
  the field still in its starting lateral order".
* **|bay - 3.5| against radius**, because a centre-versus-edge advantage is
  symmetric and a plain slot correlation cannot see it. That is the shape the
  taper and the basin both produced, and the shape V1.7's 15-degree floor
  recreated.
* **bearing**, as a *circular*-linear correlation. A plain Pearson r against an
  angle is meaningless - 359 degrees and 1 degree are adjacent - so this uses
  the standard circular-linear coefficient built from corr(x, cos t) and
  corr(x, sin t).
* **bearing relative to the rotor's own final angle**, folded into one blade
  pitch. This is the measurement that found V1.7's fixed-phase defect: with a
  fixed phase every racer parked at one of four bearings 90 degrees apart,
  being wherever the paddle that last touched it stopped. A seed-derived global
  phase spreads the *absolute* bearing uniformly by construction, so the
  absolute number is uninformative and this one is not.
* **cyclic order preservation**, as the fraction of bay triples whose cyclic
  order round the chamber matches their cyclic order across the pan. Rotation
  invariant by construction, which an angular rank correlation is not: the
  field can be rotated bodily by the rotor without being mixed at all, and a
  measure that calls that a change is measuring the phase and not the mixing.
  0.5 is no cyclic order retained; 1.0 is the necklace merely rotated.
* **lateral and radial order retention**, per trial, as Spearman's rho between
  the bay index and the rank of x (and of radius) within that trial. Per trial
  rather than pooled, because pooling over trials averages away the thing being
  asked - whether *this* field kept *its* order.

`in_chamber` is reported because a racer that never arrived is not evidence
about mixing either way, and V1.7's first clean-looking runs were a start that
delivered nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.machine import Machine

from sloped import layout
from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "ChamberSample",
    "sample_chamber",
    "summarise_chamber",
    "pearson",
    "circular_linear",
    "cyclic_orientation",
    "resultant",
    "bearing_noise_floor",
    "angular_span",
]


# --- the statistics, each with the reason it is this one ------------------


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx * syy < 1e-15:
        return None
    return sxy / (sxx * syy) ** 0.5


def circular_linear(xs: Sequence[float], angles: Sequence[float]) -> float | None:
    """The circular-linear correlation between a linear x and an angle.

    Mardia's coefficient: built from the correlations of x with cos and sin of
    the angle, corrected for the correlation between those two. It is in
    [0, 1] and has no sign, because "which way round" is not a property an
    angle has on its own.
    """
    if len(xs) < 4:
        return None
    cosines = [math.cos(a) for a in angles]
    sines = [math.sin(a) for a in angles]
    rxc = pearson(xs, cosines)
    rxs = pearson(xs, sines)
    rcs = pearson(cosines, sines)
    if rxc is None or rxs is None or rcs is None:
        return None
    denominator = 1.0 - rcs * rcs
    if abs(denominator) < 1e-12:
        return None
    value = (rxc * rxc + rxs * rxs - 2.0 * rxc * rxs * rcs) / denominator
    return math.sqrt(max(0.0, min(1.0, value)))


def cyclic_orientation(bays: Sequence[int], bearings_deg: Sequence[float]) -> tuple[int, int]:
    """How many bay triples kept their cyclic order round the chamber.

    Returns (agreeing triples, total triples). For each triple of bays taken in
    increasing index order, the triple agrees if, walking counter-clockwise
    from the first, the second is met before the third. A field that the rotor
    has only *rotated* agrees on every triple; a field whose cyclic order has
    gone agrees on about half.

    Rotation invariant, and that is the whole reason for using triples rather
    than an angular rank correlation. The rotor's job is not to move the
    necklace round - it is to break it.
    """
    count = len(bays)
    agree = 0
    total = 0
    for i in range(count):
        for j in range(i + 1, count):
            for k in range(j + 1, count):
                a, b, c = bearings_deg[i], bearings_deg[j], bearings_deg[k]
                d_ab = (b - a) % 360.0
                d_ac = (c - a) % 360.0
                total += 1
                if d_ab < d_ac:
                    agree += 1
    return agree, total


def resultant(bearings_deg: Sequence[float]) -> tuple[float, float] | None:
    """The circular mean bearing and mean resultant length of a set of angles.

    The resultant length is the interpretable form of "does this bay have a
    preferred place in the chamber": 0 is a bay whose racers end up anywhere,
    1 is a bay whose racers always end up at one bearing. For `n` samples of a
    genuinely uniform angle the expected length is about `0.886 / sqrt(n)`, so
    the noise floor is quotable rather than guessed - `bearing_noise_floor`
    below is that figure, and a bay under it has no preference to speak of.

    This exists because Mardia's circular-linear R cannot separate the two
    cases that matter. A field that all ends up in one arc *because the inlet
    is at one bearing* is not unfair - every bay shares the preference. A field
    whose eight bays each prefer a *different* arc is exactly the sectoring the
    previous six start topologies died of. The per-bay means separate them and
    a single pooled coefficient does not.
    """
    if not bearings_deg:
        return None
    cosines = sum(math.cos(math.radians(a)) for a in bearings_deg) / len(bearings_deg)
    sines = sum(math.sin(math.radians(a)) for a in bearings_deg) / len(bearings_deg)
    length = math.hypot(cosines, sines)
    mean = math.degrees(math.atan2(sines, cosines)) % 360.0
    return mean, length


def bearing_noise_floor(count: int) -> float:
    """What `resultant` returns for `count` samples of a truly uniform angle."""
    return 0.0 if count <= 0 else 0.8862269 / math.sqrt(count)


def angular_span(bearings_deg: Sequence[float]) -> float | None:
    """The smallest arc containing all of these bearings, in degrees.

    Applied to the eight per-bay circular means. A small span says every bay
    shares one preference, which is the inlet's own bearing and is fair. A span
    near 360 says the bays are spread round the chamber, each with its own
    sector, which is not.
    """
    if len(bearings_deg) < 2:
        return None
    ordered = sorted(angle % 360.0 for angle in bearings_deg)
    gaps = [
        (ordered[(index + 1) % len(ordered)] - ordered[index]) % 360.0
        for index in range(len(ordered))
    ]
    return 360.0 - max(gaps)


def _spearman(bays: Sequence[int], values: Sequence[float]) -> float | None:
    """Rho between the bay index and the rank of `values` within one trial."""
    if len(bays) < 4:
        return None
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    for rank, index in enumerate(order):
        ranks[index] = float(rank)
    return pearson([float(b) for b in bays], ranks)


# --- one seed -------------------------------------------------------------


@dataclass(frozen=True)
class ChamberSample:
    """The chamber's field at one tick of one seed, in layout units.

    Positions are in the start module's **own** frame - x across, z along the
    module's downhill, both relative to the chamber's centre - because that is
    the frame the geometry is authored in and the only one in which "bearing
    round the chamber" means anything.
    """

    seed: int
    tick: int
    time: float
    rotor_phase: float
    rotor_angle: float                 # blade 0's angle at this tick
    blades: int
    bays: tuple[int, ...]
    x: tuple[float, ...]
    y: tuple[float, ...]
    z: tuple[float, ...]
    radius: tuple[float, ...]
    bearing: tuple[float, ...]         # degrees, 0..360, about the chamber axis
    speed: tuple[float, ...]           # layout units per second
    in_chamber: tuple[bool, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "tick": self.tick,
            "time": round(self.time, 5),
            "rotor_phase": round(self.rotor_phase, 6),
            "rotor_angle": round(self.rotor_angle, 6),
            "bays": list(self.bays),
            "x": [round(v, 4) for v in self.x],
            "z": [round(v, 4) for v in self.z],
            "radius": [round(v, 4) for v in self.radius],
            "bearing": [round(v, 2) for v in self.bearing],
            "speed": [round(v, 4) for v in self.speed],
            "in_chamber": list(self.in_chamber),
        }


def _to_local(start, world_sim: Sequence[float]) -> tuple[float, float, float]:
    """A world simulation point back in the start module's layout frame.

    The module authors every vertex through `sloped.stations._place`, which
    applies the yaw frame about `self.origin` and then converts to simulation
    units. This is that, inverted - and the frame is orthonormal, so the
    inverse rotation is the transpose.
    """
    point = tuple(value * SIM_TO_LAYOUT for value in world_sim)
    delta = tuple(point[axis] - start.origin[axis] for axis in range(3))
    frame = start.frame
    return tuple(
        sum(frame[axis][component] * delta[component] for component in range(3))
        for axis in range(3)
    )


def sample_chamber(
    seed: int,
    machine: Machine,
    config: CoreConfig | None = None,
    marble_count: int = 8,
    at: float | None = None,
) -> ChamberSample:
    """Run one seed to the tick before the release opens, and read the field.

    Cheap on purpose: no checkpoints, no locating, no containment - about a
    quarter of the ticks a start-lab trial runs and none of its per-tick work.
    That is what makes 96 seeds of this a minute rather than an hour, and
    section 2 asks for at least 96.

    `at` defaults to the chamber's own `gate_time`, read off the module rather
    than typed, so a change to the release timeline cannot leave this sampling
    the old one.
    """
    from marble3d.simulation import MarbleSimulation
    from sloped.startlab import seed_phase_for

    config = config or DEFAULT_CONFIG
    start = machine.modules["start"]
    plan = getattr(machine, "plan", None)
    if plan is not None and getattr(plan, "seed_phase", False):
        start.rotor_phase = seed_phase_for(seed)
    when = float(start.gate_time if at is None else at)
    hz = config.physics.physics_hz
    # The last tick at which the release is still fully shut: `LinearGate`
    # holds its rest pose while `tick * dt - release_time <= 0`.
    target = int(math.floor(when * hz))

    sim = MarbleSimulation(machine, config, seed, marble_count)
    try:
        while sim.ticks < target:
            sim.step()
        rotor = next(
            (a for a in start.local_actuators() if a.name == "rotor0"), None
        )
        angle = 0.0 if rotor is None else rotor.angle_at(sim.ticks, sim.dt)
        bays: list[int] = []
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float] = []
        radii: list[float] = []
        bearings: list[float] = []
        speeds: list[float] = []
        inside: list[bool] = []
        for marble_id in sorted(sim.marbles):
            marble = sim.marbles[marble_id]
            local = _to_local(start, marble.pose[0])
            across = local[0]
            along = local[2] - start.CHAMBER_Z
            radius = math.hypot(across, along)
            bays.append(marble.start_index)
            xs.append(across)
            ys.append(local[1])
            zs.append(along)
            radii.append(radius)
            bearings.append(math.degrees(math.atan2(along, across)) % 360.0)
            speeds.append(math.hypot(*marble.pose[2]) * SIM_TO_LAYOUT)
            # In the chamber, rather than still on the apron or gone: inside
            # the wall and within a marble of the floor it should be resting
            # on. Both halves are needed - a racer that fell out of the machine
            # is also "inside the wall" in plan view.
            floor = start.floor_at(radius) if hasattr(start, "floor_at") else start.rim_floor
            inside.append(
                radius <= start.R_WALL + layout.MARBLE_RADIUS
                and abs(local[1] - (floor + layout.MARBLE_RADIUS)) < 3.0 * layout.MARBLE_RADIUS
            )
        return ChamberSample(
            seed=seed,
            tick=sim.ticks,
            time=sim.ticks * sim.dt,
            rotor_phase=float(getattr(start, "rotor_phase", 0.0)),
            rotor_angle=angle,
            blades=int(getattr(start, "PADDLES", 0)),
            bays=tuple(bays),
            x=tuple(xs),
            y=tuple(ys),
            z=tuple(zs),
            radius=tuple(radii),
            bearing=tuple(bearings),
            speed=tuple(speeds),
            in_chamber=tuple(inside),
        )
    finally:
        sim.close()


# --- the table ------------------------------------------------------------


def summarise_chamber(
    samples: Sequence[ChamberSample], slots: int = layout.BAYS
) -> dict[str, Any]:
    """The pre-release table section 3 of the brief reads its decision off.

    Only racers actually in the chamber are pooled. A racer that never arrived
    carries no information about whether the chamber erased its bay, and
    including it would put the apron's own ordering into a chamber statistic.
    """
    bays: list[float] = []
    centre: list[float] = []
    radii: list[float] = []
    xs: list[float] = []
    zs: list[float] = []
    speeds: list[float] = []
    absolute: list[float] = []
    relative: list[float] = []
    per_bay: dict[int, dict[str, list[float]]] = {
        slot: {"radius": [], "x": [], "z": [], "speed": [], "bearing": []}
        for slot in range(slots)
    }
    lateral: list[float] = []
    radial: list[float] = []
    agree = 0
    total = 0
    present = 0
    seen = 0
    for sample in samples:
        blade_pitch = 2.0 * math.pi / max(sample.blades, 1)
        keep = [i for i in range(len(sample.bays)) if sample.in_chamber[i]]
        seen += len(sample.bays)
        present += len(keep)
        for index in keep:
            bay = sample.bays[index]
            bays.append(float(bay))
            centre.append(abs(bay - (slots - 1) / 2.0))
            radii.append(sample.radius[index])
            xs.append(sample.x[index])
            zs.append(sample.z[index])
            speeds.append(sample.speed[index])
            absolute.append(math.radians(sample.bearing[index]))
            # Folded into one blade pitch: the question is which *sector* of
            # the rotor a racer parked in, and with four blades those repeat
            # every 90 degrees. Rescaled back to a full turn so the circular
            # statistic sees a whole circle.
            offset = (math.radians(sample.bearing[index]) - sample.rotor_angle) % blade_pitch
            relative.append(offset / blade_pitch * 2.0 * math.pi)
            row = per_bay[bay]
            row["radius"].append(sample.radius[index])
            row["x"].append(sample.x[index])
            row["z"].append(sample.z[index])
            row["speed"].append(sample.speed[index])
            row["bearing"].append(sample.bearing[index])
        # The order statistics are per trial and need the whole field: a
        # cyclic order over six of eight racers is not this field's order.
        if len(keep) == len(sample.bays):
            trial_bays = [sample.bays[i] for i in keep]
            got, count = cyclic_orientation(
                trial_bays, [sample.bearing[i] for i in keep]
            )
            agree += got
            total += count
            rho_x = _spearman(trial_bays, [sample.x[i] for i in keep])
            rho_r = _spearman(trial_bays, [sample.radius[i] for i in keep])
            if rho_x is not None:
                lateral.append(rho_x)
            if rho_r is not None:
                radial.append(rho_r)

    def mean(values: Sequence[float]) -> float | None:
        return sum(values) / len(values) if values else None

    def rounded(value: float | None, places: int = 4) -> float | None:
        return None if value is None else round(value, places)

    def span(key: str) -> float | None:
        values = [mean(per_bay[slot][key]) for slot in range(slots)]
        present_values = [v for v in values if v is not None]
        if len(present_values) < slots:
            return None
        return max(present_values) - min(present_values)

    orientation = (agree / total) if total else None
    # Per bay: is there a bearing this bay prefers, and do the eight bays
    # prefer the *same* one? See `resultant`.
    per_bay_bearing = {
        slot: resultant(per_bay[slot]["bearing"]) for slot in range(slots)
    }
    lengths = [v[1] for v in per_bay_bearing.values() if v is not None]
    means = [v[0] for v in per_bay_bearing.values() if v is not None]
    counts = [len(per_bay[slot]["bearing"]) for slot in range(slots)]
    floor = bearing_noise_floor(min(counts) if counts else 0)
    field = resultant([b for slot in range(slots) for b in per_bay[slot]["bearing"]])
    return {
        "trials": len(samples),
        "racers": seen,
        "in_chamber": present,
        "in_chamber_pct": round(100.0 * present / seen, 3) if seen else None,
        "bay_to_radius_r": rounded(pearson(bays, radii)),
        "bay_to_x_r": rounded(pearson(bays, xs)),
        "bay_to_z_r": rounded(pearson(bays, zs)),
        "bay_to_speed_r": rounded(pearson(bays, speeds)),
        "centre_to_radius_r": rounded(pearson(centre, radii)),
        "bay_to_bearing_R": rounded(circular_linear(bays, absolute)),
        # The magnitude of the (bay -> x, bay -> z) vector. Invariant to how
        # far the rotor carried the field round, which the two components
        # separately are not: a longer mix rotates the pattern and leaves this
        # alone, which is how a bulk transport is told from a residual order.
        "bay_to_plan_r": rounded(
            None if pearson(bays, xs) is None or pearson(bays, zs) is None
            else math.hypot(pearson(bays, xs), pearson(bays, zs))
        ),
        "bearing_resultant_mean": rounded(
            (sum(lengths) / len(lengths)) if lengths else None
        ),
        "bearing_resultant_max": rounded(max(lengths) if lengths else None),
        "bearing_noise_floor": rounded(floor),
        "bay_bearing_mean_span_deg": rounded(angular_span(means), 2),
        "field_bearing_mean_deg": rounded(None if field is None else field[0], 2),
        "field_bearing_resultant": rounded(None if field is None else field[1]),
        "bay_to_blade_sector_R": rounded(circular_linear(bays, relative)),
        "cyclic_order_agreement": rounded(orientation),
        "cyclic_order_retained": rounded(
            None if orientation is None else abs(2.0 * orientation - 1.0)
        ),
        "cyclic_triples": total,
        "lateral_order_rho": rounded(mean(lateral)),
        "radial_order_rho": rounded(mean(radial)),
        "mean_radius": rounded(mean(radii)),
        "mean_speed": rounded(mean(speeds)),
        "radius_span": rounded(span("radius")),
        "x_span": rounded(span("x")),
        "slots": [
            {
                "slot": slot,
                "racers": len(per_bay[slot]["radius"]),
                "mean_radius": rounded(mean(per_bay[slot]["radius"])),
                "mean_x": rounded(mean(per_bay[slot]["x"])),
                "mean_z": rounded(mean(per_bay[slot]["z"])),
                "mean_speed": rounded(mean(per_bay[slot]["speed"])),
                "bearing_mean_deg": rounded(
                    None if per_bay_bearing[slot] is None
                    else per_bay_bearing[slot][0], 2),
                "bearing_resultant": rounded(
                    None if per_bay_bearing[slot] is None
                    else per_bay_bearing[slot][1]),
            }
            for slot in range(slots)
        ],
    }
