"""What a bowl run is judged on, computed from the time series alone.

Everything here reads a `LabRun` and nothing else. That is deliberate: the same
code has to score a Python 2.5D run, a PyBullet run, a Godot run and - for the
comparison in section 2 of the experiment plan - the production 2D neon replay,
and a metric that reached into an engine for a quantity the others could not
supply would not be a comparison.

The headline number is **revolutions**: accumulated angular travel about the
bowl axis before a marble leaves, over two pi. It is the one measurement that
separates a bowl from a funnel. A marble that enters and heads for the drain
accumulates a fraction of a turn no matter how convincingly it is drawn; a
marble that genuinely orbits accumulates several.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from physics_lab.common.labreplay import STATE_DRAINED, STATE_ESCAPED, LabRun

__all__ = ["MarbleMetrics", "RunMetrics", "measure", "summarise"]

# A marble whose centre is within two of its own diameters of the hole is "at
# the drain" for the throughput and clogging measurements. Expressed against
# the marble rather than as a multiple of the drain radius because that is what
# arching is about: two marbles jammed across a hole are touching its rim, and
# how far away the rim is in units of itself has nothing to do with it. An
# earlier version used three drain radii and measured the entire spiral-in
# phase as a clog, because in this bowl every marble ends up inside 0.18 m.
DRAIN_ZONE_MARBLE_DIAMETERS = 1.0

# Tighter still, for the clogging measurement: a marble whose centre is within
# one radius of the hole is touching its rim. Two of those at once and nothing
# leaving is an arch, which is the failure section 28 asks about; two marbles
# merely *near* the drain and not leaving is a bowl still doing its job.
ARCH_ZONE_MARBLE_RADII = 1.0

# Frame-to-frame energy rises larger than this, on a frame with no collision in
# it, are counted as unexplained. Sized against the numerical noise of a 60 fps
# sample of a 240 Hz simulation rather than picked: the 2.5D integrator's own
# drift over a whole run is smaller than one part in a million of the starting
# energy, so anything at the millijoule scale is a real event.
ENERGY_RISE_TOLERANCE = 1e-4


@dataclass
class MarbleMetrics:
    marble_id: int
    entry_speed: float
    revolutions: float
    peak_radius: float
    final_radius: float
    radial_slope: float          # metres per second, fitted over its whole life
    mean_speed: float
    peak_speed: float
    collisions: int
    time_to_drain: float | None
    drain_order: int | None
    drained: bool
    escaped: bool
    time_in_drain_zone: float
    max_penetration: float       # how far below the bowl its centre ever got
    max_hover: float             # and how far above it, while in contact
    rolling_ratio: float         # mean |omega| r / |v|: 1 is rolling, 0 is sliding


@dataclass
class RunMetrics:
    approach: str
    seed: int
    marbles: list[MarbleMetrics] = field(default_factory=list)
    total_collisions: int = 0
    drained: int = 0
    escaped: int = 0
    stuck: int = 0
    all_drained_time: float | None = None
    mean_drain_time: float | None = None
    min_drain_time: float | None = None
    max_drain_time: float | None = None
    median_revolutions: float = 0.0
    fraction_over_one_revolution: float = 0.0
    fraction_decaying: float = 0.0
    energy_first: float = 0.0
    energy_last: float = 0.0
    unexplained_energy_rises: int = 0
    largest_energy_rise: float = 0.0
    max_overlap: float = 0.0
    max_penetration: float = 0.0
    max_hover: float = 0.0
    longest_drain_stall: float = 0.0
    wall_clock: float = 0.0
    failure: str | None = None

    @property
    def sim_seconds(self) -> float:
        return self.all_drained_time or 0.0


def _wrap(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def _slope(times: Sequence[float], values: Sequence[float]) -> float:
    """Least-squares slope. Zero for fewer than two samples."""
    count = len(times)
    if count < 2:
        return 0.0
    mean_t = sum(times) / count
    mean_v = sum(values) / count
    numerator = sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values))
    denominator = sum((t - mean_t) ** 2 for t in times)
    return 0.0 if denominator <= 0.0 else numerator / denominator


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def measure(run: LabRun, surface_height=None) -> RunMetrics:
    """Score one run.

    `surface_height` is a callable from bowl radius to the height of the centre
    surface there. When it is supplied the adherence metrics are computed -
    how far a marble's centre ever got below the surface it is supposed to be
    on, and how far above. For the 2.5D prototype both are exactly zero by
    construction, and that is worth showing rather than assuming; for a
    rigid-body engine they are the penetration and the jitter.
    """
    benchmark = run.benchmark
    radius = float(benchmark["marble_radius"])
    mass = float(benchmark["marble_mass"])
    gravity = float(benchmark["gravity"])
    inertia = float(benchmark["rolling_inertia_factor"])
    drain_zone = float(benchmark["drain_radius"]) + DRAIN_ZONE_MARBLE_DIAMETERS * 2.0 * radius
    lip = float(benchmark["drain_radius"])
    frame_dt = 1.0 / run.sample_hz if run.sample_hz else 0.0

    ids = [marble.marble_id for marble in run.frames[0].marbles] if run.frames else []
    travel = {marble_id: 0.0 for marble_id in ids}
    last_angle: dict[int, float] = {}
    peak_radius = {marble_id: 0.0 for marble_id in ids}
    final_radius = {marble_id: 0.0 for marble_id in ids}
    speeds: dict[int, list[float]] = {marble_id: [] for marble_id in ids}
    radius_series: dict[int, tuple[list[float], list[float]]] = {
        marble_id: ([], []) for marble_id in ids
    }
    entry_speed = {marble_id: 0.0 for marble_id in ids}
    zone_time = {marble_id: 0.0 for marble_id in ids}
    penetration = {marble_id: 0.0 for marble_id in ids}
    hover = {marble_id: 0.0 for marble_id in ids}
    rolling: dict[int, list[float]] = {marble_id: [] for marble_id in ids}

    max_overlap = 0.0
    energies: list[tuple[float, float]] = []

    for frame in run.frames:
        active = []
        total_energy = 0.0
        for marble in frame.marbles:
            if marble.state in (STATE_DRAINED, STATE_ESCAPED):
                continue
            marble_id = marble.marble_id
            x, y, z = marble.position
            speed = math.sqrt(sum(value * value for value in marble.velocity))
            bowl_radius = math.hypot(x, z)

            if marble_id not in last_angle:
                entry_speed[marble_id] = speed
            else:
                travel[marble_id] += _wrap(math.atan2(z, x) - last_angle[marble_id])
            last_angle[marble_id] = math.atan2(z, x)

            peak_radius[marble_id] = max(peak_radius[marble_id], bowl_radius)
            final_radius[marble_id] = bowl_radius
            speeds[marble_id].append(speed)
            radius_series[marble_id][0].append(frame.time)
            radius_series[marble_id][1].append(bowl_radius)
            if bowl_radius <= drain_zone:
                zone_time[marble_id] += frame_dt

            spin = math.sqrt(sum(value * value for value in marble.spin))
            if surface_height is not None and bowl_radius >= lip:
                offset = y - surface_height(bowl_radius)
                penetration[marble_id] = min(penetration[marble_id], offset)
                hover[marble_id] = max(hover[marble_id], offset)
                # Only measured in contact: a marble in flight keeps whatever
                # spin it had and the ratio means nothing there.
                if speed > 1e-3 and abs(offset) < radius:
                    rolling[marble_id].append(spin * radius / speed)

            # Energy is read out of each engine's own state rather than
            # reconstructed from a rolling assumption, so that an engine whose
            # marbles skid is charged for the energy that skidding costs
            # instead of being credited with spin it does not have.
            total_energy += (
                mass * gravity * y
                + 0.5 * mass * speed * speed
                + 0.5 * inertia * mass * radius * radius * spin * spin
            )
            active.append((x, y, z))

        for index, first in enumerate(active):
            for second in active[index + 1:]:
                gap = math.dist(first, second)
                max_overlap = max(max_overlap, 2.0 * radius - gap)
        energies.append((frame.time, total_energy))

    collision_times = {
        round(event.time, 6) for event in run.events if event.kind == "collision"
    }
    unexplained = 0
    largest_rise = 0.0
    for (time_a, energy_a), (time_b, energy_b) in zip(energies, energies[1:]):
        rise = energy_b - energy_a
        if rise <= ENERGY_RISE_TOLERANCE:
            continue
        # A collision anywhere in the sampled window explains a step, because
        # the sample rate is coarser than the physics rate and a restitution
        # event redistributes energy between marbles inside one frame.
        window = any(time_a - 1e-9 <= t <= time_b + 1e-9 for t in collision_times)
        if not window:
            unexplained += 1
            largest_rise = max(largest_rise, rise)

    drain_order: dict[int, int] = {}
    drain_time: dict[int, float] = {}
    escaped: set[int] = set()
    collisions = {marble_id: 0 for marble_id in ids}
    for event in run.events:
        if event.kind == "collision":
            collisions[int(event.data["a"])] += 1
            collisions[int(event.data["b"])] += 1
        elif event.kind == "drained":
            drain_order[int(event.data["id"])] = int(event.data["order"])
            drain_time[int(event.data["id"])] = event.time
        elif event.kind == "escaped":
            escaped.add(int(event.data["id"]))

    marbles: list[MarbleMetrics] = []
    for marble_id in ids:
        times, radii = radius_series[marble_id]
        marbles.append(
            MarbleMetrics(
                marble_id=marble_id,
                entry_speed=entry_speed[marble_id],
                revolutions=abs(travel[marble_id]) / (2.0 * math.pi),
                peak_radius=peak_radius[marble_id],
                final_radius=final_radius[marble_id],
                radial_slope=_slope(times, radii),
                mean_speed=sum(speeds[marble_id]) / len(speeds[marble_id])
                if speeds[marble_id]
                else 0.0,
                peak_speed=max(speeds[marble_id]) if speeds[marble_id] else 0.0,
                collisions=collisions[marble_id],
                time_to_drain=drain_time.get(marble_id),
                drain_order=drain_order.get(marble_id),
                drained=marble_id in drain_time,
                escaped=marble_id in escaped,
                time_in_drain_zone=zone_time[marble_id],
                max_penetration=max(0.0, -penetration[marble_id]),
                max_hover=max(0.0, hover[marble_id]),
                rolling_ratio=sum(rolling[marble_id]) / len(rolling[marble_id])
                if rolling[marble_id]
                else 0.0,
            )
        )

    drained_times = sorted(drain_time.values())
    revolutions = [marble.revolutions for marble in marbles]
    decaying = [marble for marble in marbles if marble.radial_slope < 0.0]

    metrics = RunMetrics(
        approach=run.approach,
        seed=run.seed,
        marbles=marbles,
        total_collisions=sum(1 for event in run.events if event.kind == "collision"),
        drained=len(drained_times),
        escaped=len(escaped),
        stuck=len(ids) - len(drained_times) - len(escaped),
        all_drained_time=drained_times[-1] if len(drained_times) == len(ids) else None,
        mean_drain_time=sum(drained_times) / len(drained_times) if drained_times else None,
        min_drain_time=drained_times[0] if drained_times else None,
        max_drain_time=drained_times[-1] if drained_times else None,
        median_revolutions=_median(revolutions),
        fraction_over_one_revolution=sum(1 for value in revolutions if value >= 1.0)
        / len(revolutions)
        if revolutions
        else 0.0,
        fraction_decaying=len(decaying) / len(marbles) if marbles else 0.0,
        energy_first=energies[0][1] if energies else 0.0,
        energy_last=energies[-1][1] if energies else 0.0,
        unexplained_energy_rises=unexplained,
        largest_energy_rise=largest_rise,
        max_overlap=max_overlap,
        max_penetration=max((marble.max_penetration for marble in marbles), default=0.0),
        max_hover=max((marble.max_hover for marble in marbles), default=0.0),
        longest_drain_stall=_longest_stall(
            run,
            drained_times,
            float(benchmark["drain_radius"]) + ARCH_ZONE_MARBLE_RADII * radius,
        ),
        wall_clock=float(run.stats.get("wall_clock", 0.0)),
        failure=run.stats.get("failure"),
    )
    return metrics


def _longest_stall(run: LabRun, drained_times: Sequence[float], arch_zone: float) -> float:
    """The longest stretch with marbles queued at the drain and none leaving.

    The clogging measurement. Two marbles arching across the hole is a real
    failure of a marble machine and it is invisible in a drain-time average:
    the average only says that everything eventually left.
    """
    queued_from: float | None = None
    longest = 0.0
    exits = sorted(drained_times)
    for frame in run.frames:
        waiting = sum(
            1
            for marble in frame.marbles
            if marble.state not in (STATE_DRAINED, STATE_ESCAPED)
            and math.hypot(marble.position[0], marble.position[2]) <= arch_zone
        )
        if waiting >= 2:
            if queued_from is None:
                queued_from = frame.time
            elif not any(queued_from < exit_time <= frame.time for exit_time in exits):
                longest = max(longest, frame.time - queued_from)
            else:
                queued_from = frame.time
        else:
            queued_from = None
    return longest


def summarise(runs: Iterable[RunMetrics]) -> dict[str, float]:
    """Roll a batch of runs up into the numbers the comparison table needs."""
    batch = list(runs)
    if not batch:
        return {}
    marbles = [marble for run in batch for marble in run.marbles]
    drain_times = [
        marble.time_to_drain for marble in marbles if marble.time_to_drain is not None
    ]
    revolutions = [marble.revolutions for marble in marbles]
    completed = [run.all_drained_time for run in batch if run.all_drained_time is not None]
    return {
        "runs": len(batch),
        "marbles": len(marbles),
        "drained_fraction": sum(1 for marble in marbles if marble.drained) / len(marbles),
        "escaped": sum(run.escaped for run in batch),
        "stuck": sum(run.stuck for run in batch),
        "failures": sum(1 for run in batch if run.failure),
        "median_revolutions": _median(revolutions),
        "mean_revolutions": sum(revolutions) / len(revolutions),
        "min_revolutions": min(revolutions),
        "max_revolutions": max(revolutions),
        "fraction_over_one_revolution": sum(1 for value in revolutions if value >= 1.0)
        / len(revolutions),
        "fraction_decaying": sum(run.fraction_decaying for run in batch) / len(batch),
        "mean_drain_time": sum(drain_times) / len(drain_times) if drain_times else 0.0,
        "min_drain_time": min(drain_times) if drain_times else 0.0,
        "max_drain_time": max(drain_times) if drain_times else 0.0,
        "mean_all_drained_time": sum(completed) / len(completed) if completed else 0.0,
        "runs_fully_drained": len(completed),
        "collisions_per_run": sum(run.total_collisions for run in batch) / len(batch),
        "max_overlap": max(run.max_overlap for run in batch),
        "max_penetration": max(run.max_penetration for run in batch),
        "max_hover": max(run.max_hover for run in batch),
        "mean_rolling_ratio": sum(marble.rolling_ratio for marble in marbles) / len(marbles),
        "min_rolling_ratio": min(marble.rolling_ratio for marble in marbles),
        "unexplained_energy_rises": sum(run.unexplained_energy_rises for run in batch),
        "largest_energy_rise": max(run.largest_energy_rise for run in batch),
        "longest_drain_stall": max(run.longest_drain_stall for run in batch),
        "mean_wall_clock": sum(run.wall_clock for run in batch) / len(batch),
        "total_wall_clock": sum(run.wall_clock for run in batch),
    }
