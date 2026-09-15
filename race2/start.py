"""The Race #2 start: eight bays on one shelf, and the floor that leaves.

## Why a trapdoor and not a gate

Race #1 spent five sessions on its start, and
`docs/sloped_race_v18_floor.md` is where it landed: **a release that reads no
marble's position cannot, by construction, sort the field by position.** A gate
across eight bays already has that property - it frees all eight in the same
tick - and Race #1's 8.87x slot bias was never the gate's. It was the *fan*
below the gate, four layout units of trough that turned eight lanes into one
and therefore ordered the field by how far each marble had to travel sideways.

So the finding that transfers is not "use a trapdoor". It is:

    the release is not where a start goes wrong; the first constriction is.

Race #2 takes both halves. The release is a single panel hinged on the
across-course axis, so every bay sits at the same distance from the hinge and
loses support in the same tick - position-independent in the strongest sense
available, because there is no geometry between the hinge and any bay that
differs between bays. And **there is no constriction after it**: the field
falls 1.4 layout units onto a dished band as wide as the bay row, and that band
stays that wide for the whole of the first phase. Nothing narrows until the
pack has already been scrambled by a mechanism.

The trapdoor is also the better *picture*. A gate lifting is a small motion at
the edge of frame; a floor vanishing under eight racers at once is the whole
frame moving, and section "KEEP THE PROVEN HOOK PHILOSOPHY" wants the premise
legible inside half a second.

## What is measured and what is assumed

Nothing here argues that the start is fair. The claim is only that the release
mechanism cannot express a bay preference: `panel_release_times()` returns the
eight release times so a test can assert they are one number, and
`tools/race2_benchmark.py` measures the start-slot-to-finish-rank correlation
on the built course, which is the thing that actually decides.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import GUIDED, MarbleModule, Probe
from marble3d.units import MARBLE_RADIUS as SIM_MARBLE_RADIUS

from sloped import layout
from sloped.scale import to_sim
from sloped.solids import box_shell, merge_meshes, tube
from sloped.trapdoor import FloorPanel

from race2.kit import Frame, Vec3

__all__ = ["DropStart"]


class DropStart(MarbleModule):
    """Eight bays abreast on a level shelf over one hinged floor panel."""

    START_KIND = "drop"

    BAYS = 8
    # 0.82 against a 0.57 racer and a 0.14 divider leaves a 0.68 gap, so a
    # marble sits in its bay with 0.11 of slack and cannot be resting on a
    # divider. Race #1's 0.63 pitch is tighter than that and its dividers only
    # begin half way down the fan for exactly this reason; here the dividers
    # run the whole bay because the bay is where the field is photographed.
    BAY_PITCH = 0.82
    FIN_RADIUS = 0.07
    FIN_RISE = 0.20            # the divider's axis height above the deck

    DECK_THICK = 0.12
    PANEL_ALONG = 1.30         # how far the floor reaches downstream of its hinge
    PANEL_MARGIN = 0.45        # how far past the outermost bay the floor reaches

    WALL_THICK = 0.16
    WALL_RISE = 0.62
    BACK_RISE = 0.70

    # The release. 0.10 s of dwell so the first frames of a clip show eight
    # racers standing still - the premise - and then 0.16 s to swing clear,
    # which at a 1.4-unit fall is well under the time the first marble needs to
    # reach the band.
    RELEASE_TIME = 0.10
    RELEASE_DURATION = 0.16
    RELEASE_SWEEP = math.radians(96.0)

    def __init__(
        self,
        module_id: str,
        frame: Frame,
        fall: float,
        exit_width: float,
        bays: int = BAYS,
        release_time: float | None = None,
    ) -> None:
        """`frame` is the shelf: origin on the deck top at the bay row's centre.

        `fall` is how far below the deck top the receiving band's floor sits,
        in layout units, and is used only to size the exit socket and the
        module's own bounds - the band is a separate module and places itself.
        """
        super().__init__(module_id)
        if bays < 2:
            raise ValueError(f"{module_id}: a race needs at least two bays")
        self.frame = frame
        self.bays = int(bays)
        self.fall = float(fall)
        self.exit_width = float(exit_width)
        self.release_time = self.RELEASE_TIME if release_time is None else float(release_time)
        self.half_spread = 0.5 * (self.bays - 1) * self.BAY_PITCH
        self.panel_half_across = self.half_spread + self.PANEL_MARGIN
        self._mesh: TriMesh | None = None

    # --- where a racer waits ---------------------------------------------

    def bay_across(self, index: int) -> float:
        """The lane centre, in layout units, left-positive.

        Bay 0 is the **rightmost** lane looking downhill, so the numbering runs
        the way a starting grid is numbered from the camera's left. That is a
        presentation choice with a fairness consequence - every slot-bias plot
        in this package is indexed by it - so it is written down here and
        nowhere else.
        """
        return (self.half_spread - index * self.BAY_PITCH)

    def bay_along(self) -> float:
        """How far downstream of the hinge every bay sits.

        One number for all eight, and that is the whole mechanism: the hinge
        runs across the course, so bay distance from it does not depend on the
        bay.
        """
        return -0.5 * self.PANEL_ALONG

    def marble_starts(self) -> list[Transform]:
        """The eight resting poses, in simulation units."""
        rise = 0.5 * self.DECK_THICK + layout.MARBLE_RADIUS
        rotation = basis_from_forward_up(self.frame.forward, self.frame.up)
        return [
            Transform(
                position=self.frame.sim(self.bay_along(), rise, self.bay_across(index)),
                rotation=rotation,
            )
            for index in range(self.bays)
        ]

    def panel_release_times(self) -> list[float]:
        """Every panel's release time, for the test that asserts they are one.

        The claim the start rests on is that no bay is released before another.
        A test that read the docstring would be checking the prose; this reads
        the actuators the simulation is actually handed.
        """
        return [float(panel.release_time) for panel in self.local_actuators()]

    # --- geometry ----------------------------------------------------------

    def _deck_axes(self) -> tuple[Vec3, Vec3, Vec3]:
        """(along, up, across) as unit vectors, the order `box_shell` wants."""
        return (self.frame.forward, self.frame.up, self.frame.across)

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        along, up, across = self._deck_axes()
        parts: list[TriMesh] = []

        # **The back wall is four boxes, not one.** `marble3d.validation` bounds
        # a collider's longest triangle edge at four marble diameters, because a
        # long edge is how a phantom span - a triangle bridging a gap nothing
        # was meant to bridge - gets past every other check. A 6.6-unit wall as
        # one `box_shell` is an 11.7-unit edge in simulation units, and it is
        # not a phantom span, but a rule that is relaxed for the case that is
        # fine is a rule that does not catch the case that is not.
        span = 2.0 * (self.panel_half_across + self.WALL_THICK)
        segments = max(2, int(math.ceil(span / 1.4)))
        step = span / segments
        for index in range(segments):
            offset = -0.5 * span + (index + 0.5) * step
            back = self.frame.sim(
                -self.PANEL_ALONG - 0.5 * self.WALL_THICK,
                0.5 * self.BACK_RISE - 0.5 * self.DECK_THICK,
                offset,
            )
            parts.append(
                box_shell(
                    back,
                    (along, up, across),
                    (to_sim(0.5 * self.WALL_THICK), to_sim(0.5 * self.BACK_RISE),
                     to_sim(0.5 * step)),
                    name=f"start_back{index}",
                )
            )

        length = self.PANEL_ALONG + 2.0 * self.WALL_THICK
        along_segments = max(2, int(math.ceil(length / 1.4)))
        along_step = length / along_segments
        for side in (-1.0, 1.0):
            for index in range(along_segments):
                middle = -0.5 * self.PANEL_ALONG - 0.5 * length + (index + 0.5) * along_step
                centre = self.frame.sim(
                    middle + 0.5 * self.PANEL_ALONG,
                    0.5 * self.WALL_RISE - 0.5 * self.DECK_THICK,
                    side * (self.panel_half_across + 0.5 * self.WALL_THICK),
                )
                parts.append(
                    box_shell(
                        centre,
                        (along, up, across),
                        (to_sim(0.5 * along_step),
                         to_sim(0.5 * self.WALL_RISE),
                         to_sim(0.5 * self.WALL_THICK)),
                        name=f"start_wall{int(side)}_{index}",
                    )
                )

        # The dividers. Static, and clear of the panel by construction: their
        # lowest point is FIN_RISE - FIN_RADIUS = 0.13 above the deck top, and
        # the panel's top face is the deck top, so the floor swings out from
        # under them without touching one.
        for gap in range(self.bays - 1):
            offset = self.bay_across(gap) - 0.5 * self.BAY_PITCH
            start = self.frame.sim(-self.PANEL_ALONG + 0.06, self.FIN_RISE, offset)
            end = self.frame.sim(0.10, self.FIN_RISE, offset)
            parts.append(tube(start, end, to_sim(self.FIN_RADIUS), segments=8,
                              name=f"start_fin{gap}"))

        self._mesh = merge_meshes(parts, name=f"{self.id}_shell")
        return [self._mesh]

    def local_actuators(self) -> list[FloorPanel]:
        """The floor, as strips of one rigid panel about one hinge.

        Several boxes rather than one for the reason `FloorPanel` gives: a
        strip's corners stay inside the shelf's own footprint through the whole
        sweep, where one 5.7-unit slab's outer corner would swing through the
        side wall.
        """
        along, up, across = self._deck_axes()
        hinge = self.frame.sim(-self.PANEL_ALONG, -0.5 * self.DECK_THICK, 0.0)
        strips = 4
        step = self.PANEL_ALONG / strips
        panels: list[FloorPanel] = []
        for index in range(strips):
            panels.append(
                FloorPanel(
                    name=f"floor{index}",
                    # (half length along the hinge, half thickness,
                    # half width across the hinge) - `basis_from_forward_up`
                    # puts those on local X, Y, Z in that order.
                    half_extents=(
                        to_sim(self.panel_half_across),
                        to_sim(0.5 * self.DECK_THICK),
                        to_sim(0.5 * step),
                    ),
                    hinge=hinge,
                    axis=across,
                    across=along,
                    up=up,
                    offset=to_sim((index + 0.5) * step),
                    sweep=self.RELEASE_SWEEP,
                    release_time=self.release_time,
                    duration=self.RELEASE_DURATION,
                )
            )
        return panels

    def local_sockets(self) -> dict[str, Socket]:
        """One socket, at the lip, aimed downhill at the band's entry.

        It is not a join: nothing is connected to it, because every Race #2
        module is placed at world coordinates the way every Race #1 module is.
        It exists so `Machine` has a flow order and so a seam check has two
        frames to compare.
        """
        position = self.frame.sim(0.0, -0.5 * self.DECK_THICK - self.fall, 0.0)
        drop = math.atan2(self.fall, max(self.PANEL_ALONG, 1e-6))
        forward = (
            self.frame.forward[0] * math.cos(drop),
            -math.sin(drop),
            self.frame.forward[2] * math.cos(drop),
        )
        return {
            "exit": Socket(
                name="exit",
                frame=Transform(position=position,
                                rotation=basis_from_forward_up(forward, self.frame.up)),
                kind=GUIDED,
                width=to_sim(self.exit_width),
                height=to_sim(self.WALL_RISE),
            )
        }

    def local_bounds(self) -> Aabb:
        lower = [math.inf] * 3
        upper = [-math.inf] * 3
        corners = [
            self.frame.sim(along, up, across)
            for along in (-self.PANEL_ALONG - self.WALL_THICK, 0.3)
            for up in (-self.DECK_THICK - self.fall, self.BACK_RISE)
            for across in (-self.panel_half_across - self.WALL_THICK,
                           self.panel_half_across + self.WALL_THICK)
        ]
        for point in corners:
            for axis in range(3):
                lower[axis] = min(lower[axis], point[axis])
                upper[axis] = max(upper[axis], point[axis])
        grow = 2.0 * SIM_MARBLE_RADIUS
        return Aabb(
            tuple(value - grow for value in lower),
            tuple(value + grow for value in upper),
        )

    def local_probes(self) -> list[Probe]:
        """One ray per bay, fired at the deck the racer rests on.

        The deck is a kinematic body and not part of `local_colliders`, so a
        probe aimed at it would miss whatever the shelf looked like. These are
        aimed at the *dividers* instead - the thing that keeps eight racers in
        eight lanes - and at the side walls, which is the geometry a test can
        check without the actuator.
        """
        probes: list[Probe] = []
        reach = 3.0 * layout.MARBLE_RADIUS
        for gap in range(self.bays - 1):
            offset = self.bay_across(gap) - 0.5 * self.BAY_PITCH
            at = self.frame.sim(-0.5 * self.PANEL_ALONG, self.FIN_RISE, offset)
            outward = self.frame.sim(
                -0.5 * self.PANEL_ALONG,
                self.FIN_RISE + reach,
                offset,
            )
            probes.append(
                Probe(start=outward, end=at, expect_hit=True, tolerance=0.06,
                      label=f"{self.id}:fin{gap}")
            )
        return probes

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data.update(
            {
                "start_kind": self.START_KIND,
                "bays": self.bays,
                "bay_pitch": self.BAY_PITCH,
                "spread": round(2.0 * self.half_spread, 4),
                "fall": round(self.fall, 4),
                "release_time": self.release_time,
                "release_duration": self.RELEASE_DURATION,
                "release_times": self.panel_release_times(),
            }
        )
        return data
