"""HIT EVERY TILE TO ESCAPE: the ball, the activation ledger and the instruments.

One ball, one arena, 48 tiles. A tile is dark until the ball hits it and lit
for ever afterwards. Completion is `activated == total`. That is the whole
mechanic, and this module is the part that has to be boringly reliable for the
mechanic to be worth filming.

## Why this is event-driven and not stepped

A fixed-step solver has to answer two questions the prototype cannot afford to
get wrong: did the ball pass through a wall between two steps, and which tile
did it touch. Both get harder the faster the ball moves and the smaller the
tiles are, and both are exactly the knobs a satisfying version of this will want
to turn up.

So there is no step. `satisfying.tile_arena` guarantees the ball's centre lives
inside a convex polygon - sixteen half-planes - and inside that polygon the
ball flies a parabola. The time at which a parabola crosses a line is a
quadratic; the earliest positive root over the sixteen sides is the next
collision, exactly. Advance to it, reflect, repeat.

What that buys, and these are not claims but consequences of the method:

- **No tunnelling is possible.** Not "unlikely at this speed": the solver finds
  the first crossing of the first wall, so there is no interval in which the
  ball is on the wrong side. `max_wall_excursion` reports the largest distance
  the centre was ever found outside its allowed region, computed analytically
  over every flight rather than sampled, and it is floating-point noise.
- **No jitter.** There is no penetration to resolve and no contact to hold, so
  there is nothing for a solver to oscillate about.
- **No energy drift.** Reflection with `restitution = 1.0` preserves the normal
  speed exactly and gravity is conservative, so the specific energy
  `0.5*|v|^2 + g*y` is constant to the last bit. `energy_drift_relative`
  measures it rather than assuming it, which is also how a future restitution
  below 1 will show up as a number instead of a mood.
- **The tile is identified by the contact point,** not by a proximity guess.
  The contact point is on the wall line by construction.

The cost is that a non-convex arena, a moving wall or a second ball all need
more than this. Phase 1 has none of those. When Phase 2 adds a second ball,
this is the moment to re-open the choice - and not before.

## What the instruments are for

Phase 1 is not meant to produce a good-looking run. It is meant to say what the
natural physics does, including the parts that will need fixing:

- `longest_no_progress_seconds` and `longest_no_progress_collisions` - the dead
  periods. This is the pacing problem, measured.
- `longest_confined_run` - the longest stretch of consecutive collisions
  confined to two tiles or fewer. A two-point bounce loop, if there is one.
- `grazing_collisions` - hits whose normal speed is under
  `graze_fraction` of the speed. A near-tangential hit still activates a tile,
  but it reads as nothing on screen and it barely changes the trajectory.
- `hits_by_tile` - the distribution. Under gravity the floor is hit many times
  over before the ceiling is hit once, and that asymmetry is the reason the
  last tile takes as long as it does.
- `min_flight_seconds` - the smallest gap between two collisions. A collapsing
  gap is the signature of a ball settling against a wall.

None of this is anti-stagnation *assistance*. There is no trajectory help in
this module, deliberately: the brief asks what the natural system does first.

## Determinism

`start_state` derives the release point and heading from the seed through
`satisfying.seeds`, and nothing else in a run is random. Same seed, same
config, same arena gives the same collisions in the same order - and
`state_digest` is a SHA-256 over the raw IEEE-754 bytes of every collision, so
two runs that agree to six decimals at collision one and diverge by collision
two thousand compare as different rather than as equal.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from satisfying import seeds
from satisfying.tile_arena import Arena, Point, polygon_arena

__all__ = [
    "TileEscapeConfig",
    "DEFAULT_CONFIG",
    "Flight",
    "Collision",
    "TileEscapeRun",
    "start_state",
    "simulate",
]


@dataclass(frozen=True)
class TileEscapeConfig:
    """Everything about a run that is not the seed.

    The defaults are chosen so that the whole arena is energetically reachable.
    With `restitution = 1.0` the specific energy `0.5*speed^2 + gravity*y` is
    fixed for the run, so a ball released near the centre can only reach the
    ceiling if `0.5*speed^2 > gravity*(apothem - ball_radius)`. At the defaults
    that is 200 against 112, a comfortable margin; halve the speed and the top
    third of the arena becomes unreachable and the run can never complete.
    `reachability_margin` reports the ratio so a config change cannot quietly
    make completion impossible.
    """

    speed: float = 20.0
    gravity: float = 12.0
    restitution: float = 1.0
    ball_radius: float = 0.45
    duration: float = 240.0
    stop_on_complete: bool = True
    max_collisions: int = 200_000

    # Instrumentation thresholds. They change what is reported, never what the
    # ball does.
    graze_fraction: float = 0.05

    # The inward nudge applied after a reflection, in world units, so the ball
    # centre is strictly inside its allowed region and the just-hit wall cannot
    # be re-detected at dt = 0. Eight orders of magnitude below the ball radius
    # and ten below the tile length: far too small to read on screen, far too
    # large for a double to lose.
    skin: float = 1.0e-9
    time_epsilon: float = 1.0e-12

    def as_dict(self) -> dict[str, Any]:
        return {
            "speed": self.speed,
            "gravity": self.gravity,
            "restitution": self.restitution,
            "ball_radius": self.ball_radius,
            "duration": self.duration,
            "stop_on_complete": self.stop_on_complete,
            "max_collisions": self.max_collisions,
            "graze_fraction": self.graze_fraction,
            "skin": self.skin,
            "time_epsilon": self.time_epsilon,
        }


DEFAULT_CONFIG = TileEscapeConfig()


@dataclass(frozen=True)
class Flight:
    """A parabolic arc between two collisions.

    `t_start` is when it began, `position`/`velocity` the state then. The arc
    is exact: there is no sampled trajectory anywhere in this module, and
    `TileEscapeRun.position_at` reconstructs any instant from these three
    numbers.
    """

    t_start: float
    position: Point
    velocity: Point


@dataclass(frozen=True)
class Collision:
    """One ball-tile contact, whether or not it activated anything."""

    time: float
    tile_index: int
    tile_id: str
    side: int
    slot: int
    is_new: bool
    activated_after: int
    contact: Point
    incoming_speed: float
    normal_speed: float
    flight_seconds: float

    @property
    def graze_ratio(self) -> float:
        """Normal speed as a fraction of speed. 1 is head-on, 0 is tangential."""
        if self.incoming_speed <= 0.0:
            return 0.0
        return self.normal_speed / self.incoming_speed


@dataclass(frozen=True)
class TileEscapeRun:
    """The result of one run: the trajectory, the ledger and the instruments."""

    seed: int
    config: TileEscapeConfig
    arena: Arena
    flights: tuple[Flight, ...]
    collisions: tuple[Collision, ...]
    first_hit_time: dict[str, float]
    hits_by_tile: dict[str, int]
    end_time: float
    completed: bool
    completion_time: float | None
    stop_reason: str
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tiles(self) -> int:
        return self.arena.total_tiles

    @property
    def activated_tiles(self) -> int:
        return len(self.first_hit_time)

    @property
    def progress_ratio(self) -> float:
        return self.activated_tiles / self.total_tiles

    def _flight_at(self, t: float) -> Flight:
        lo, hi = 0, len(self.flights) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.flights[mid].t_start <= t:
                lo = mid
            else:
                hi = mid - 1
        return self.flights[lo]

    def position_at(self, t: float) -> Point:
        flight = self._flight_at(t)
        dt = max(0.0, t - flight.t_start)
        px, py = flight.position
        vx, vy = flight.velocity
        return (px + vx * dt, py + vy * dt - 0.5 * self.config.gravity * dt * dt)

    def velocity_at(self, t: float) -> Point:
        flight = self._flight_at(t)
        dt = max(0.0, t - flight.t_start)
        vx, vy = flight.velocity
        return (vx, vy - self.config.gravity * dt)

    def activated_count_at(self, t: float) -> int:
        return sum(1 for first in self.first_hit_time.values() if first <= t)

    def activated_at(self, t: float) -> frozenset[str]:
        return frozenset(
            tile_id for tile_id, first in self.first_hit_time.items() if first <= t
        )

    def unhit_tiles(self) -> tuple[str, ...]:
        return tuple(
            tile.tile_id
            for tile in self.arena.tiles
            if tile.tile_id not in self.first_hit_time
        )

    def time_of_nth_activation(self, n: int) -> float | None:
        """When the nth new tile lit up, 1-based. None if it never did."""
        times = sorted(self.first_hit_time.values())
        if n < 1 or n > len(times):
            return None
        return times[n - 1]

    def log_lines(self, duplicates: bool = False) -> Iterator[str]:
        """Development instrumentation, one line per event.

        Reads as `8.42s | tile_17 | NEW | 31/48`. Duplicates are off by default
        because there are an order of magnitude more of them than activations.
        """
        for hit in self.collisions:
            if not hit.is_new and not duplicates:
                continue
            kind = "NEW" if hit.is_new else "DUP"
            yield (
                f"{hit.time:7.2f}s | {hit.tile_id} | {kind:3s} | "
                f"{hit.activated_after}/{self.total_tiles}"
            )

    def state_digest(self) -> str:
        """SHA-256 over the raw bytes of every collision, before any rounding."""
        digest = hashlib.sha256()
        digest.update(struct.pack("<qq", self.seed, len(self.collisions)))
        for hit in self.collisions:
            digest.update(
                struct.pack(
                    "<dddddi",
                    hit.time,
                    hit.contact[0],
                    hit.contact[1],
                    hit.incoming_speed,
                    hit.normal_speed,
                    hit.tile_index,
                )
            )
        return digest.hexdigest()

    def summary(self) -> dict[str, Any]:
        """A JSON-serialisable report. Rounded for reading, unlike the digest."""
        return {
            "seed": self.seed,
            "config": self.config.as_dict(),
            "arena": {
                "sides": self.arena.sides,
                "tiles_per_side": self.arena.tiles_per_side,
                "total_tiles": self.arena.total_tiles,
                "circumradius": self.arena.circumradius,
                "apothem": round(self.arena.apothem, 6),
                "tile_length": round(self.arena.tile_length, 6),
            },
            "completed": self.completed,
            "completion_seconds": (
                None if self.completion_time is None else round(self.completion_time, 3)
            ),
            "end_seconds": round(self.end_time, 3),
            "stop_reason": self.stop_reason,
            "activated_tiles": self.activated_tiles,
            "total_tiles": self.total_tiles,
            "progress_ratio": round(self.progress_ratio, 4),
            "unhit_tiles": list(self.unhit_tiles()),
            "digest": self.state_digest(),
            **self.metrics,
        }


def start_state(
    seed: int,
    config: TileEscapeConfig = DEFAULT_CONFIG,
    arena: Arena | None = None,
) -> tuple[Point, Point]:
    """The release point and velocity for a seed. Pure, and the only randomness.

    Position is uniform over a disc about the centre - `sqrt(u)` on the radius,
    not `u`, so the release is uniform by area and not bunched at the middle -
    and the heading is uniform over the circle. Speed is exactly `config.speed`,
    because a prototype comparing seeds must not also be comparing energies.
    """
    arena = arena if arena is not None else polygon_arena()
    release_radius = seeds.RELEASE_RADIUS_FRACTION * arena.circumradius

    position_rng = seeds.make_position_rng(seed)
    radius = release_radius * math.sqrt(position_rng.random())
    angle = 2.0 * math.pi * position_rng.random()
    position = (radius * math.cos(angle), radius * math.sin(angle))

    heading = 2.0 * math.pi * seeds.make_heading_rng(seed).random()
    velocity = (config.speed * math.cos(heading), config.speed * math.sin(heading))
    return position, velocity


def reachability_margin(
    config: TileEscapeConfig = DEFAULT_CONFIG, arena: Arena | None = None
) -> float:
    """Kinetic energy at release over the potential energy needed at the ceiling.

    Above 1 the whole arena is reachable from the centre; at or below 1 the top
    of the arena cannot be touched at all and no run can ever complete. With
    `gravity = 0` it is infinite.
    """
    arena = arena if arena is not None else polygon_arena()
    if config.gravity <= 0.0:
        return math.inf
    top = arena.apothem - config.ball_radius
    return (0.5 * config.speed * config.speed) / (config.gravity * top)


def _longest_confined_run(indices: Sequence[int], distinct: int) -> tuple[int, tuple[int, ...]]:
    """Longest stretch of consecutive collisions touching at most `distinct` tiles."""
    best = 0
    best_set: tuple[int, ...] = ()
    counts: dict[int, int] = {}
    left = 0
    for right, index in enumerate(indices):
        counts[index] = counts.get(index, 0) + 1
        while len(counts) > distinct:
            leaving = indices[left]
            counts[leaving] -= 1
            if counts[leaving] == 0:
                del counts[leaving]
            left += 1
        if right - left + 1 > best:
            best = right - left + 1
            best_set = tuple(sorted(counts))
    return best, best_set


def simulate(
    seed: int,
    config: TileEscapeConfig = DEFAULT_CONFIG,
    arena: Arena | None = None,
) -> TileEscapeRun:
    """Run one ball until every tile is lit, the clock runs out, or physics faults."""
    arena = arena if arena is not None else polygon_arena()
    if config.ball_radius <= 0.0 or config.ball_radius >= arena.apothem:
        raise ValueError(
            f"ball radius {config.ball_radius} does not fit an arena of apothem "
            f"{arena.apothem}"
        )

    normals = arena.side_outward_normals
    sides = arena.sides
    limit = arena.apothem - config.ball_radius
    gravity = config.gravity
    skin = config.skin
    time_eps = config.time_epsilon
    bounce = 1.0 + config.restitution

    position, velocity = start_state(seed, config, arena)
    if not arena.contains(position, config.ball_radius):
        raise ValueError(
            f"seed {seed} releases the ball inside a wall; the release disc is "
            f"too wide for this ball radius"
        )

    flights: list[Flight] = [Flight(0.0, position, velocity)]
    collisions: list[Collision] = []
    first_hit_time: dict[str, float] = {}
    hits_by_tile: dict[str, int] = {tile.tile_id: 0 for tile in arena.tiles}

    t = 0.0
    completion_time: float | None = None
    stop_reason = "duration"
    max_excursion = 0.0
    speed_min = math.hypot(*velocity)
    speed_max = speed_min
    energy_first = 0.5 * speed_min * speed_min + gravity * position[1]
    energy_min = energy_first
    energy_max = energy_first

    while True:
        if len(collisions) >= config.max_collisions:
            stop_reason = "collision_cap"
            break

        px, py = position
        vx, vy = velocity

        # One quadratic per side: how far outside side k's wall line the centre
        # is, as a function of time. Gravity only enters through the normal's y
        # component, so `a2` is the same for the whole flight.
        quadratics: list[tuple[float, float, float]] = []
        best_dt = math.inf
        best_side = -1
        for k in range(sides):
            nx, ny = normals[k]
            a2 = -0.5 * gravity * ny
            b1 = vx * nx + vy * ny
            c0 = px * nx + py * ny - limit
            quadratics.append((a2, b1, c0))

            if abs(a2) < 1.0e-15:
                if b1 > 0.0:
                    root = -c0 / b1
                    if time_eps < root < best_dt:
                        best_dt, best_side = root, k
                continue
            disc = b1 * b1 - 4.0 * a2 * c0
            if disc < 0.0:
                continue
            sqrt_disc = math.sqrt(disc)
            for root in (
                (-b1 - sqrt_disc) / (2.0 * a2),
                (-b1 + sqrt_disc) / (2.0 * a2),
            ):
                if time_eps < root < best_dt:
                    best_dt, best_side = root, k

        if best_side < 0:
            # The ball is inside a convex region it can only leave through a
            # wall, so this cannot happen for finite state. If it ever does, it
            # is a numerical fault and must be reported rather than smoothed
            # over.
            stop_reason = "no_impact_found"
            break

        # Containment, analytically, over the flight that is about to happen:
        # the largest value each side's quadratic takes on [0, best_dt]. The
        # maximum is at an endpoint, or at the vertex of an upward parabola.
        for a2, b1, c0 in quadratics:
            worst = max(c0, c0 + b1 * best_dt + a2 * best_dt * best_dt)
            if a2 > 0.0:
                apex = -b1 / (2.0 * a2)
                if 0.0 < apex < best_dt:
                    worst = max(worst, c0 + b1 * apex + a2 * apex * apex)
            if worst > max_excursion:
                max_excursion = worst

        if t + best_dt > config.duration:
            stop_reason = "duration"
            break

        t += best_dt
        px += vx * best_dt
        py += vy * best_dt - 0.5 * gravity * best_dt * best_dt
        vy -= gravity * best_dt

        nx, ny = normals[best_side]
        contact = (px + config.ball_radius * nx, py + config.ball_radius * ny)
        tile = arena.tile_for_contact(best_side, contact)

        incoming_speed = math.hypot(vx, vy)
        normal_component = vx * nx + vy * ny

        is_new = tile.tile_id not in first_hit_time
        if is_new:
            first_hit_time[tile.tile_id] = t
        hits_by_tile[tile.tile_id] += 1
        collisions.append(
            Collision(
                time=t,
                tile_index=tile.index,
                tile_id=tile.tile_id,
                side=best_side,
                slot=tile.slot,
                is_new=is_new,
                activated_after=len(first_hit_time),
                contact=contact,
                incoming_speed=incoming_speed,
                normal_speed=abs(normal_component),
                flight_seconds=best_dt,
            )
        )

        vx -= bounce * normal_component * nx
        vy -= bounce * normal_component * ny
        # Put the centre strictly inside its region so the wall just hit cannot
        # be found again at dt = 0.
        outside = px * nx + py * ny - limit
        px -= (outside + skin) * nx
        py -= (outside + skin) * ny

        position = (px, py)
        velocity = (vx, vy)
        flights.append(Flight(t, position, velocity))

        speed_out = math.hypot(vx, vy)
        speed_min = min(speed_min, speed_out)
        speed_max = max(speed_max, speed_out)
        energy = 0.5 * speed_out * speed_out + gravity * py
        energy_min = min(energy_min, energy)
        energy_max = max(energy_max, energy)

        if len(first_hit_time) == arena.total_tiles and completion_time is None:
            completion_time = t
            if config.stop_on_complete:
                stop_reason = "complete"
                break

    end_time = config.duration if stop_reason == "duration" else t

    activation_times = sorted(first_hit_time.values())
    intervals = [
        round(b - a, 4) for a, b in zip([0.0] + activation_times, activation_times)
    ]
    # The stretch with no new tile includes the tail after the last activation,
    # which is the whole of an incomplete run's dead time and the part a pacing
    # fix has to attack first.
    tail = max(0.0, end_time - (activation_times[-1] if activation_times else 0.0))
    dead_windows = intervals + [round(tail, 4)]
    longest_dead = max(dead_windows) if dead_windows else 0.0
    longest_dead_at = 0.0
    if dead_windows:
        worst = dead_windows.index(longest_dead)
        longest_dead_at = 0.0 if worst == 0 else activation_times[worst - 1]

    gap_collisions = 0
    worst_gap_collisions = 0
    for hit in collisions:
        if hit.is_new:
            gap_collisions = 0
        else:
            gap_collisions += 1
            worst_gap_collisions = max(worst_gap_collisions, gap_collisions)

    confined, confined_tiles = _longest_confined_run([h.tile_index for h in collisions], 2)
    grazing = sum(1 for h in collisions if h.graze_ratio < config.graze_fraction)
    flight_times = [h.flight_seconds for h in collisions]
    hit_counts = [hits_by_tile[tile.tile_id] for tile in arena.tiles]

    metrics: dict[str, Any] = {
        "collisions": len(collisions),
        "new_activations": sum(1 for h in collisions if h.is_new),
        "duplicate_hits": sum(1 for h in collisions if not h.is_new),
        "collisions_per_second": (
            round(len(collisions) / end_time, 3) if end_time > 0 else 0.0
        ),
        "activation_intervals": intervals,
        "longest_no_progress_seconds": round(longest_dead, 3),
        "longest_no_progress_started_at": round(longest_dead_at, 3),
        "longest_no_progress_collisions": worst_gap_collisions,
        "median_activation_interval": (
            round(sorted(intervals)[len(intervals) // 2], 3) if intervals else 0.0
        ),
        "longest_confined_run": confined,
        "longest_confined_tiles": [
            arena.tiles[i].tile_id for i in confined_tiles
        ],
        "grazing_collisions": grazing,
        "grazing_fraction": (
            round(grazing / len(collisions), 4) if collisions else 0.0
        ),
        "min_flight_seconds": round(min(flight_times), 6) if flight_times else 0.0,
        "mean_flight_seconds": (
            round(sum(flight_times) / len(flight_times), 4) if flight_times else 0.0
        ),
        "max_wall_excursion": max_excursion,
        "speed_min": round(speed_min, 4),
        "speed_max": round(speed_max, 4),
        "energy_drift_relative": (
            round(abs(energy_max - energy_min) / abs(energy_first), 12)
            if energy_first
            else 0.0
        ),
        "reachability_margin": (
            None
            if math.isinf(reachability_margin(config, arena))
            else round(reachability_margin(config, arena), 3)
        ),
        "hits_by_tile": dict(hits_by_tile),
        "hits_min": min(hit_counts) if hit_counts else 0,
        "hits_max": max(hit_counts) if hit_counts else 0,
        "collision_cap_reached": stop_reason == "collision_cap",
    }

    return TileEscapeRun(
        seed=seed,
        config=config,
        arena=arena,
        flights=tuple(flights),
        collisions=tuple(collisions),
        first_hit_time=first_hit_time,
        hits_by_tile=hits_by_tile,
        end_time=end_time,
        completed=completion_time is not None,
        completion_time=completion_time,
        stop_reason=stop_reason,
        metrics=metrics,
    )
