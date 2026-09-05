"""The bowl benchmark: one configuration, one set of initial conditions.

`bowl_benchmark.json` is the only place any number in the experiment is
written down, and this module is the only thing that reads it. Both prototypes
take a `Benchmark` and neither of them holds a constant of its own, so a bowl
that is deeper in one experiment than the other is not a mistake this study can
make.

The initial conditions are generated *here*, in Python, once, and handed to
whichever engine is about to run - including the ones that are not Python. That
is the point: "same initial positions and entry velocities" cannot be achieved
by two engines each deriving them from the same seed, because that only works
until one of them consumes a random number the other does not. A generated
`RunSpec` is data, and data can be compared byte for byte.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import asdict, dataclass, replace
from typing import Any

from physics_lab.common.bowl import BowlSurface

__all__ = [
    "Benchmark",
    "MarbleStart",
    "RunSpec",
    "CONFIG_PATH",
    "load_benchmark",
    "make_run_spec",
]

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bowl_benchmark.json")

# Its own stream, the way `race.seeds` gives every seeded concern one. A sweep
# that changes the damping must not move a marble's entry angle, or the sweep
# would be measuring two things at once.
ENTRY_STREAM_SALT = 0x9E3779B1


@dataclass(frozen=True)
class MarbleStart:
    """One marble's complete initial state, in world coordinates.

    Position and velocity are three-dimensional and lie exactly on the centre
    surface and its tangent plane respectively; `spin` is the angular velocity
    of a sphere already rolling without slipping at that velocity. A 3D engine
    that is given the position and velocity but not the spin spends its first
    tenth of a second skidding, which the 2.5D model never does - so the two
    would be answering different questions from the first frame.
    """

    marble_id: int
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    spin: tuple[float, float, float]


@dataclass(frozen=True)
class Benchmark:
    """Every number the benchmark is made of, and nothing else."""

    gravity: float
    rim_radius: float
    rim_depth: float
    profile_power: float
    surface_max_radius: float
    drain_radius: float
    drain_exit_y: float
    marble_count: int
    marble_radius: float
    marble_mass: float
    restitution: float
    friction: float
    surface_friction: float
    linear_damping: float
    rolling_resistance: float
    rolling_inertia_factor: float
    surface_restitution: float
    physics_hz: int
    sample_hz: int
    duration_limit: float
    entry_radius_min: float
    entry_radius_max: float
    entry_speed_factor_min: float
    entry_speed_factor_max: float
    entry_radial_inward_fraction: float
    entry_angle_jitter_deg: float
    seeds: tuple[int, ...]

    # --- derived -------------------------------------------------------

    @property
    def dt(self) -> float:
        return 1.0 / self.physics_hz

    @property
    def ticks_per_sample(self) -> int:
        if self.physics_hz % self.sample_hz:
            raise ValueError(
                f"physics_hz {self.physics_hz} is not a whole multiple of "
                f"sample_hz {self.sample_hz}; the two engines would sample "
                "different instants"
            )
        return self.physics_hz // self.sample_hz

    @property
    def drain_diameter_ratio(self) -> float:
        """Drain diameter in marble diameters - the number section 28 asks for."""
        return self.drain_radius / self.marble_radius

    def surface(self) -> BowlSurface:
        return BowlSurface(
            rim_radius=self.rim_radius,
            rim_depth=self.rim_depth,
            profile_power=self.profile_power,
            drain_radius=self.drain_radius,
            marble_radius=self.marble_radius,
            surface_max_radius=self.surface_max_radius,
        )

    def with_overrides(self, **changes: Any) -> "Benchmark":
        """A copy with named fields replaced - how a parameter sweep works.

        Sweeping by editing the JSON would leave the repository describing
        whichever run happened last; sweeping by override leaves the committed
        configuration describing the benchmark and the sweep describing itself.
        """
        unknown = set(changes) - set(asdict(self))
        if unknown:
            raise ValueError(f"unknown benchmark field(s): {sorted(unknown)}")
        return replace(self, **changes)


def load_benchmark(path: str = CONFIG_PATH) -> Benchmark:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if int(raw.get("version", 0)) != 1:
        raise ValueError(f"{path}: benchmark schema version {raw.get('version')!r}, expected 1")

    world, bowl = raw["world"], raw["bowl"]
    marble, contact = raw["marble"], raw["contact"]
    sim, entry = raw["sim"], raw["entry"]
    return Benchmark(
        gravity=float(world["gravity"]),
        rim_radius=float(bowl["rim_radius"]),
        rim_depth=float(bowl["rim_depth"]),
        profile_power=float(bowl["profile_power"]),
        surface_max_radius=float(bowl["surface_max_radius"]),
        drain_radius=float(bowl["drain_radius"]),
        drain_exit_y=float(bowl["drain_exit_y"]),
        marble_count=int(marble["count"]),
        marble_radius=float(marble["radius"]),
        marble_mass=float(marble["mass"]),
        restitution=float(marble["restitution"]),
        friction=float(marble["friction"]),
        surface_friction=float(marble["surface_friction"]),
        linear_damping=float(contact["linear_damping"]),
        rolling_resistance=float(contact["rolling_resistance"]),
        rolling_inertia_factor=float(contact["rolling_inertia_factor"]),
        surface_restitution=float(contact["surface_restitution"]),
        physics_hz=int(sim["physics_hz"]),
        sample_hz=int(sim["sample_hz"]),
        duration_limit=float(sim["duration_limit"]),
        entry_radius_min=float(entry["radius_min"]),
        entry_radius_max=float(entry["radius_max"]),
        entry_speed_factor_min=float(entry["speed_factor_min"]),
        entry_speed_factor_max=float(entry["speed_factor_max"]),
        entry_radial_inward_fraction=float(entry["radial_inward_fraction"]),
        entry_angle_jitter_deg=float(entry["angle_jitter_deg"]),
        seeds=tuple(int(value) for value in raw["seeds"]),
    )


@dataclass(frozen=True)
class RunSpec:
    """A benchmark plus a seed, resolved down to eight explicit marble states.

    Both prototypes are given one of these. Nothing downstream of it draws a
    random number, so the only difference between a 2.5D run and a rigid-body
    run of the same spec is the physics.
    """

    benchmark: Benchmark
    seed: int
    starts: tuple[MarbleStart, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "benchmark": asdict(self.benchmark),
            "starts": [
                {
                    "id": start.marble_id,
                    "position": list(start.position),
                    "velocity": list(start.velocity),
                    "spin": list(start.spin),
                }
                for start in self.starts
            ],
        }


def make_run_spec(benchmark: Benchmark, seed: int) -> RunSpec:
    """Place `marble_count` marbles on the wall of the bowl, moving.

    Every marble is put on the surface with a mostly tangential velocity, so
    the benchmark tests wall-following and orbit decay rather than eight
    simultaneous drops onto the drain. Three things vary with the seed, and
    each one is there for a reason:

    * **angle**, so the field is not a rotationally symmetric ring - which,
      on a surface of revolution, would stay a ring and never collide.
    * **radius**, so the marbles start at different heights and therefore
      with different mechanical energy. This is most of what makes them
      interleave.
    * **speed, as a fraction of the local circular-orbit speed**, so some
      marbles start sub-orbital and fall inward while others start above it
      and climb. Quoting it as a fraction rather than in metres per second is
      what keeps "0.8" meaning the same thing at every radius.

    All eight run prograde. Counter-rotating marbles would produce far more
    collisions, and they would be head-on collisions of a kind a real machine
    fed from one chute never sees - which would flatter whichever engine
    handles violent impacts better and tell us nothing about a bowl.
    """
    surface = benchmark.surface()
    rng = random.Random((int(seed) ^ ENTRY_STREAM_SALT) & 0xFFFFFFFF)
    count = benchmark.marble_count

    starts: list[MarbleStart] = []
    for index in range(count):
        base = 2.0 * math.pi * index / count
        jitter = math.radians(benchmark.entry_angle_jitter_deg)
        angle = base + rng.uniform(-jitter, jitter)
        radius = rng.uniform(benchmark.entry_radius_min, benchmark.entry_radius_max)
        factor = rng.uniform(
            benchmark.entry_speed_factor_min, benchmark.entry_speed_factor_max
        )
        speed = factor * surface.circular_orbit_speed(
            radius, benchmark.gravity, benchmark.rolling_inertia_factor
        )

        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x, z = radius * cos_a, radius * sin_a
        # Prograde tangent, plus a modest inward radial component. The two are
        # the sine and cosine of one entry angle rather than being added, so
        # `speed` stays the marble's actual speed.
        entry = math.asin(max(-0.9, min(0.9, benchmark.entry_radial_inward_fraction)))
        tangential, inward = speed * math.cos(entry), speed * math.sin(entry)
        vx = tangential * -sin_a + inward * -cos_a
        vz = tangential * cos_a + inward * -sin_a

        position = surface.world_position(x, z)
        velocity = surface.world_velocity(x, z, vx, vz)
        normal = surface.normal(x, z)
        # Already rolling: omega = (n x v) / r puts the contact point at rest.
        spin = (
            (normal[1] * velocity[2] - normal[2] * velocity[1]) / benchmark.marble_radius,
            (normal[2] * velocity[0] - normal[0] * velocity[2]) / benchmark.marble_radius,
            (normal[0] * velocity[1] - normal[1] * velocity[0]) / benchmark.marble_radius,
        )
        starts.append(MarbleStart(index, position, velocity, spin))

    return RunSpec(benchmark=benchmark, seed=int(seed), starts=tuple(starts))
