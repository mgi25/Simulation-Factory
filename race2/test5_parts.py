"""Physics-first mechanisms for Race #2 Test #5.

This module is deliberately separate from the frozen SWITCHYARD production
parts. Test #5 is a direct media experiment, not a Company OS job, and its
mechanisms must be proved in isolation before they are composed into a course.

P0 starts with Pendulum Cross because it fits the engine's existing actuator
contract exactly: its pose is a pure function of tick/time, while its effect on
race order comes from the racers' arrival phase.

A true Memory Rocker is intentionally NOT implemented here. The current
Actuator contract is kinematic and cannot react to marble contact; scripting a
rocker's tilt by time would violate the experiment's physical-cause rule.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import Actuator, MarbleModule
from marble3d.units import MARBLE_DIAMETER
from race2.track import RaceRun
from sloped.scale import to_sim
from sloped.solids import merge_meshes, tube

__all__ = ["PendulumArm", "PendulumCross"]


class PendulumArm(Actuator):
    """One rigid pendulum arm sweeping across a channel.

    Angle zero hangs straight down from the pivot. Positive angle moves the arm
    toward the run's lateral axis. The sinusoidal motion depends only on tick
    and dt, so it remains deterministic and replay-safe.
    """

    def __init__(
        self,
        name: str,
        pivot: Sequence[float],
        lateral: Sequence[float],
        up: Sequence[float],
        forward: Sequence[float],
        length: float,
        thickness: float,
        depth: float,
        amplitude: float,
        rate: float,
        phase: float = 0.0,
    ) -> None:
        super().__init__(
            name,
            half_extents=(0.5 * float(length), 0.5 * float(thickness), 0.5 * float(depth)),
        )
        self.pivot = tuple(float(v) for v in pivot)
        self.lateral = tuple(float(v) for v in lateral)
        self.up = tuple(float(v) for v in up)
        self.forward = tuple(float(v) for v in forward)
        self.length = float(length)
        self.amplitude = float(amplitude)
        self.rate = float(rate)
        self.phase = float(phase)

        if self.length <= 0.0:
            raise ValueError("pendulum length must be positive")
        if not 0.0 < self.amplitude < math.pi / 2.0:
            raise ValueError("pendulum amplitude must be between 0 and 90 degrees")
        if self.rate <= 0.0:
            raise ValueError("pendulum rate must be positive")

    def angle_at(self, tick: int, dt: float) -> float:
        return self.amplitude * math.sin(self.phase + self.rate * tick * dt)

    def pose_at(self, tick: int, dt: float) -> Transform:
        angle = self.angle_at(tick, dt)
        arm = tuple(
            -self.up[axis] * math.cos(angle) + self.lateral[axis] * math.sin(angle)
            for axis in range(3)
        )
        centre = tuple(
            self.pivot[axis] + arm[axis] * (0.5 * self.length)
            for axis in range(3)
        )
        return Transform(
            position=centre,
            rotation=basis_from_forward_up(arm, self.forward),
        )

    def to_json(self) -> dict[str, Any]:
        data = super().to_json()
        data.update(
            {
                "pivot": list(self.pivot),
                "length": self.length,
                "amplitude": self.amplitude,
                "rate": self.rate,
                "phase": self.phase,
            }
        )
        return data


class PendulumCross(MarbleModule):
    """A single large readable pendulum over one Race2 run."""

    ARM_LENGTH = 2.30
    ARM_THICKNESS = 0.18
    ARM_DEPTH = 0.34
    PIVOT_RISE = 1.72
    AMPLITUDE_DEG = 46.0
    RATE = 3.65

    def __init__(
        self,
        module_id: str,
        run: RaceRun,
        at: int,
        *,
        amplitude_deg: float | None = None,
        rate: float | None = None,
        phase: float = 0.0,
    ) -> None:
        super().__init__(module_id)
        self.run = run
        self.index = min(max(int(at), 1), len(run.path) - 2)
        self.amplitude = math.radians(
            self.AMPLITUDE_DEG if amplitude_deg is None else float(amplitude_deg)
        )
        self.rate = self.RATE if rate is None else float(rate)
        self.phase = float(phase)
        self._mesh: TriMesh | None = None

    def _frame(self):
        return self.run.frames[self.index]

    def _pivot(self) -> tuple[float, float, float]:
        _lateral, up, _forward = self._frame()
        centre = self.run.sim_path[self.index]
        rise = to_sim(self.PIVOT_RISE * self.run.scale)
        return tuple(centre[axis] + up[axis] * rise for axis in range(3))

    def local_actuators(self) -> list[Actuator]:
        lateral, up, forward = self._frame()
        scale = self.run.scale
        return [
            PendulumArm(
                name="arm",
                pivot=self._pivot(),
                lateral=lateral,
                up=up,
                forward=forward,
                length=to_sim(self.ARM_LENGTH * scale),
                thickness=to_sim(self.ARM_THICKNESS * scale),
                depth=to_sim(self.ARM_DEPTH * scale),
                amplitude=self.amplitude,
                rate=self.rate,
                phase=self.phase,
            )
        ]

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        _lateral, _up, forward = self._frame()
        pivot = self._pivot()
        half = to_sim(0.42 * self.run.scale)
        a = tuple(pivot[axis] - forward[axis] * half for axis in range(3))
        b = tuple(pivot[axis] + forward[axis] * half for axis in range(3))
        self._mesh = merge_meshes(
            [
                tube(
                    a,
                    b,
                    to_sim(0.10 * self.run.scale),
                    segments=10,
                    name=f"{self.id}_pivot",
                    caps=True,
                )
            ],
            name=f"{self.id}_fixed",
        )
        return [self._mesh]

    def local_sockets(self) -> dict:
        return {}

    def local_bounds(self) -> Aabb:
        pivot = self._pivot()
        reach = to_sim(self.ARM_LENGTH * self.run.scale) + MARBLE_DIAMETER
        return Aabb(
            tuple(value - reach for value in pivot),
            tuple(value + reach for value in pivot),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "PendulumCross",
            "on": self.run.id,
            "sample": self.index,
            "amplitude_deg": round(math.degrees(self.amplitude), 3),
            "rate": round(self.rate, 6),
            "phase": round(self.phase, 6),
            "reactive": False,
            "selection": "arrival_phase_only",
        }
