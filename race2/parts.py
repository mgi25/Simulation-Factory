"""The two pieces of Race #2 geometry that are not a run and not the start.

Everything else a Race #2 course is made of already exists:
`sloped.track.TrackRun` is the channel, `sloped.stations.Mixer` is the pin
field and `sloped.stations.Spinners` is the blade wheel. Both stations read
`sloped.layout.NODES` only when their `at` argument is omitted, so passing a
sample index is the whole of what it takes to stand one somewhere else, and
neither is modified here.

What does not exist is a divider - Race #1's fork is a guard window in the side
of a channel with a lobe peeling away sideways, which is a shape that took five
sessions to make work and does not generalise to a symmetric split - and a
finish deck that is not welded to `layout.NODES["finish"]`.

## Why the divider is a blade and not a wedge

A split in this package is symmetric: one wide run ends, two narrower runs begin
side by side on the same centreline, and the field's lateral position at the
lip decides which one each marble takes. The two branches' own guard rails
close the gap between them everywhere except the first couple of units, where
the rails have not yet separated. So the only geometry a split needs is a blade
standing on the dividing line over that stretch, tapering up out of the floor
at its nose so a marble arriving dead centre is deflected rather than stopped.

That is one ribbon. A solid wedge would be three surfaces, a cap, and an
argument about what is under it.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from marble3d.geometry import Socket, Transform, basis_from_forward_up
from marble3d.mesh import Aabb, TriMesh
from marble3d.modules.base import GUIDED, MarbleModule, Probe
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS

# `marble3d.config`'s own bound on a collider's longest triangle edge.
# Read from the constant rather than repeated, so the two cannot drift.
COLLIDER_MAX_EDGE = 4.0 * MARBLE_DIAMETER

from race2.kit import flat_forward
from sloped import layout
from sloped.scale import to_sim, to_sim_point
from sloped.solids import merge_meshes, plate, tube, wall_strip
from sloped.stations import Spinner, Spinners
from sloped.track import TrackRun

__all__ = ["Divider", "RunOut", "Wheel"]


class Divider(MarbleModule):
    """The blade between the two branches of a split.

    Placed from the branches themselves: the dividing line is the midline
    between their two centrelines, sampled over `reach` layout units from the
    split, and the blade's top follows the branches' own containment so it is
    never shorter than the rails it is continuing.
    """

    NOSE_RADIUS = 0.11
    THICK = 0.18
    # What fraction of the blade is the rising nose. A blade that reached full
    # containment in a fifth of its length was a 1.6-unit wall going up in 1.1
    # units of travel, arriving at a field doing 15 layout units a second.
    NOSE_FRACTION = 0.22

    def __init__(
        self,
        module_id: str,
        left: TrackRun,
        right: TrackRun,
        reach: float = 4.2,
        rise: float | None = None,
    ) -> None:
        super().__init__(module_id)
        self.left = left
        self.right = right
        self.reach = float(reach)
        # As tall as the branches' own containment unless told otherwise. A
        # blade shorter than the rails either side of it is a blade a marble
        # rides over into the other branch, which is a route choice made by
        # nothing.
        self.rise = (
            (layout.CONTAINMENT_TOP - layout.FLOOR_Y) * left.scale if rise is None else float(rise)
        )
        self._mesh: TriMesh | None = None
        self._stations = self._midline()

    def _midline(self) -> list[tuple[float, float, float]]:
        """The dividing line, in layout units, from the nose downstream."""
        out: list[tuple[float, float, float]] = []
        step = self.left.arc[-1] / (len(self.left.path) - 1)
        count = max(3, int(round(self.reach / step)) + 1)
        for index in range(min(count, len(self.left.path), len(self.right.path))):
            a = self.left.path[index]
            b = self.right.path[index]
            out.append(((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5))
        return out

    def separation(self) -> list[float]:
        """How far apart the two branch centrelines are, sample by sample.

        Reported rather than assumed: a blade is only doing its job where the
        branches are far enough apart to have a gap between their rails, and
        `tools/race2_concepts.py` prints this so a split whose branches have
        not separated by the end of the blade is visible as a number.
        """
        out: list[float] = []
        for index in range(len(self._stations)):
            a = self.left.path[index]
            b = self.right.path[index]
            out.append(math.dist((a[0], a[1], a[2]), (b[0], b[1], b[2])))
        return out

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        parts: list[TriMesh] = []
        line = self._stations
        span = len(line) - 1
        for index in range(span):
            a, b = line[index], line[index + 1]
            forward = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            length = math.hypot(forward[0], forward[2]) or 1e-6
            side = (-forward[2] / length, 0.0, forward[0] / length)
            # The nose rises out of the floor over the first fifth of the
            # blade, so a marble arriving on the centreline meets a ramp and is
            # deflected, not a wall it stops dead against.
            def height_at(step: int) -> float:
                t = min(1.0, step / max(1.0, self.NOSE_FRACTION * span))
                return self.rise * (t * t * (3.0 - 2.0 * t))

            low, high = height_at(index), height_at(index + 1)
            floor = layout.FLOOR_Y * self.left.scale
            for sign in (-1.0, 1.0):
                corners = [
                    (a[0] + side[0] * sign * 0.5 * self.THICK, a[1] + floor,
                     a[2] + side[2] * sign * 0.5 * self.THICK),
                    (b[0] + side[0] * sign * 0.5 * self.THICK, b[1] + floor,
                     b[2] + side[2] * sign * 0.5 * self.THICK),
                    (b[0] + side[0] * sign * 0.5 * self.THICK, b[1] + floor + high,
                     b[2] + side[2] * sign * 0.5 * self.THICK),
                    (a[0] + side[0] * sign * 0.5 * self.THICK, a[1] + floor + low,
                     a[2] + side[2] * sign * 0.5 * self.THICK),
                ]
                parts.append(
                    plate([to_sim_point(point) for point in corners],
                          name=f"{self.id}_face{index}{int(sign)}", steps=2)
                )
            # The cap, so the blade is a solid and not two parallel sheets a
            # marble can be inside.
            cap = [
                (a[0] - side[0] * 0.5 * self.THICK, a[1] + floor + low,
                 a[2] - side[2] * 0.5 * self.THICK),
                (b[0] - side[0] * 0.5 * self.THICK, b[1] + floor + high,
                 b[2] - side[2] * 0.5 * self.THICK),
                (b[0] + side[0] * 0.5 * self.THICK, b[1] + floor + high,
                 b[2] + side[2] * 0.5 * self.THICK),
                (a[0] + side[0] * 0.5 * self.THICK, a[1] + floor + low,
                 a[2] + side[2] * 0.5 * self.THICK),
            ]
            parts.append(plate([to_sim_point(p) for p in cap], name=f"{self.id}_cap{index}"))

        nose = line[0]
        floor = layout.FLOOR_Y * self.left.scale
        parts.append(
            tube(
                to_sim_point((nose[0], nose[1] + floor, nose[2])),
                to_sim_point((nose[0], nose[1] + floor + 0.25 * self.rise, nose[2])),
                to_sim(self.NOSE_RADIUS),
                segments=8,
                name=f"{self.id}_nose",
            )
        )
        self._mesh = merge_meshes(parts, name=f"{self.id}_blade")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        return {}

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(v - MARBLE_DIAMETER for v in bounds.lower),
            tuple(v + MARBLE_DIAMETER for v in bounds.upper),
        )

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        gaps = self.separation()
        data.update(
            {
                "reach": round(self.reach, 3),
                "rise": round(self.rise, 3),
                "separation_first": round(gaps[0], 3),
                "separation_last": round(gaps[-1], 3),
            }
        )
        return data


class RunOut(MarbleModule):
    """The deck the field runs out onto after the line.

    The finish *line* is the sprint's exit socket and the timing happens there.
    This is what happens next, and it exists for the reason Race #1's finish
    deck exists: a marble retired at the line leaves the finish shot with
    nothing in it, and a course whose last marble is removed at the line has
    never proved that it can bring a field to a stop.

    Authored from the sprint's own exit rather than from a recorded node, so a
    course can be re-routed without a second coordinate to update.
    """

    WIDTH = 11.0
    # **Sized to the shot, and contained against a bounce that does not
    # converge.**
    #
    # `DEPTH` was 8.2 and `RIM` was 0.80, and with the deck laid across the
    # track neither number was ever tested: the field left sideways before it
    # could reach the back of the deck. Turned the right way round, both are
    # wrong, and for two different reasons.
    #
    # *Depth comes from the camera envelope, not from a score.* The finish shot
    # pulls back through the payoff, and what it can still hold collapses
    # quickly: measured against the locked track over the settled window, a
    # racer resting at `along` 3.0 is in frame across the deck's whole width,
    # at 3.4 only within +/-4.3 of the centreline, and at 4.0 and beyond there
    # is no lateral position that stays in frame to the last frame. A racer
    # comes to rest about a radius short of the back wall, so `DEPTH` 3.2 puts
    # the field at 2.9 - inside the band where *every* part of the deck it can
    # reach is on screen. That is why this number is robust: it does not depend
    # on which way the pack happens to scatter. At 8.2 the winner was on screen
    # for 95 of the 200 frames after it crossed, because it settled behind the
    # picture.
    #
    # *Rim is sized to the worst rebound, because the rebound is chaotic.* A
    # racer arrives at about 29 layout units a second and is stopped by a wall.
    # How high it comes off that wall does not settle down as the deck is
    # tuned - over `DEPTH` 3.0 to 3.6 the worst rise in the field runs 0.74,
    # 1.11, 0.78, 0.86, 1.82, 1.21 with no trend, and it moved again when the
    # wall's own triangulation changed (see `_wall_steps`). At `RIM` 0.80 that
    # was a coin toss on whether the winner cleared the wall and was retired
    # through the gate behind it - 4.8 and 5.6 lost it, 4.6 and 5.0 did not.
    # So the rim is not tuned either: it is set above the worst centre height
    # seen anywhere in that range, 2.10, with margin over the depth that
    # ships: 2.00 leaves 0.94 - more than a marble diameter and a half - above
    # the highest any racer gets at `DEPTH` 3.2. It is not raised further
    # because `wall_strip` never subdivides vertically, so the rim's own height
    # is a single triangle edge and `check_mesh` bounds that at four marble
    # diameters: 2.28 would be the wall that cannot be built at all.
    DEPTH = 3.2
    RIM = 2.00
    # Downhill, away from the line, and it has to be: the deck's front edge is
    # the channel mouth and has no wall. An upslope was tried - it gathers the
    # field beautifully and then rolls three to six racers back out of the
    # machine through that mouth. See the document's section 4.
    FALL_DEG = 1.4
    # How far past the back wall's inner face the machine's finish gate sits,
    # in layout units. One marble diameter is 0.57, so a racer resting against
    # the wall is clear of the gate by a margin rather than by a rounding.
    CATCH = 0.60
    # How much of `check_mesh`'s longest-edge budget a wall quad may spend.
    # Not the whole of it: the bound is on the built mesh and `_wall_steps` is
    # arithmetic on the nominal cell, and a wall that follows a sloping base is
    # a little longer than its plan.
    EDGE_TARGET = 0.95

    def __init__(self, module_id: str, sprint: TrackRun, width: float | None = None) -> None:
        super().__init__(module_id)
        self.sprint = sprint
        self.width = self.WIDTH if width is None else float(width)
        exit_index = len(sprint.path) - 1
        point = sprint.path[exit_index]
        # **The tangent, never a heading.** This line used to read
        # `heading_deg` - `atan2(x, z)` - through `Frame.yaw`'s inverse -
        # `atan2(-z, x)` - and the two are ninety degrees apart at every
        # heading, so the deck was laid across the direction of travel from the
        # commit that wrote it (8daff3a, with SWITCHYARD) to V33.
        # `race2.kit`'s convention note has the arithmetic;
        # `flat_forward` of the run's own tangent cannot express the mistake.
        self.forward = flat_forward(sprint.tangents[exit_index])
        self.across = (-self.forward[2], 0.0, self.forward[0])
        # The deck top sits a cradle's depth below the exit centreline, so the
        # channel's running surface and the deck are the same height at the
        # seam and a marble rolls out rather than off a step.
        self.origin = (
            point[0],
            point[1] + layout.FLOOR_Y * sprint.scale,
            point[2],
        )
        self._mesh: TriMesh | None = None

    def _wall_steps(self, span: float) -> int:
        """Enough subdivisions that no wall quad's diagonal is a phantom span.

        **A taller rim needs a finer wall.** `check_mesh` bounds the longest
        triangle edge at four marble diameters, and a `wall_strip` cell is
        `span/steps` wide by the rim's *full* height - the height is never
        subdivided, so raising `RIM` tightens the bound on `steps`. That is
        how V33.1 first broke this check: `RIM` 1.60 made the back wall's cell
        3.216 by 2.807 simulation units and its diagonal 4.269, over the 4.000
        limit, on a mesh that had been well formed at 0.80 for the same six
        steps.

        Derived rather than typed, so the next dimension change does not have
        to remember, and it raises rather than silently fails if the rim alone
        is over budget - a `wall_strip` never subdivides vertically, so a tall
        enough rim is one edge that no number of steps can shorten. That is a
        real ceiling: at `RIM` 2.28 the wall's own height reaches the limit.
        """
        limit = COLLIDER_MAX_EDGE * self.EDGE_TARGET
        height = to_sim(self.RIM)
        if height >= limit:
            raise ValueError(
                f"RIM {self.RIM} is {height:.3f} simulation units, at or over "
                f"the {limit:.3f} this wall may spend on one edge. A "
                "`wall_strip` never subdivides vertically, so no number of "
                "steps can bring it back - the rim itself is the edge.")
        room = math.sqrt(limit * limit - height * height)
        return max(6, math.ceil(to_sim(span) / room))

    def _at(self, along: float, across: float) -> tuple[float, float, float]:
        drop = -math.tan(math.radians(self.FALL_DEG)) * max(along, 0.0)
        return (
            self.origin[0] + self.forward[0] * along + self.across[0] * across,
            self.origin[1] + drop,
            self.origin[2] + self.forward[2] * along + self.across[2] * across,
        )

    def local_colliders(self) -> list[TriMesh]:
        if self._mesh is not None:
            return [self._mesh]
        half = 0.5 * self.width
        parts: list[TriMesh] = [
            plate(
                [
                    to_sim_point(self._at(0.0, -half)),
                    to_sim_point(self._at(self.DEPTH, -half)),
                    to_sim_point(self._at(self.DEPTH, half)),
                    to_sim_point(self._at(0.0, half)),
                ],
                name=f"{self.id}_deck",
                steps=8,
            )
        ]
        stations = [(self.DEPTH, -half), (self.DEPTH, half)]
        parts.append(
            wall_strip(
                to_sim_point(self.origin),
                self.forward,
                self.across,
                (0.0, 1.0, 0.0),
                [(to_sim(a), to_sim(c)) for a, c in stations],
                base=lambda a, c: to_sim(-math.tan(math.radians(self.FALL_DEG)) * max(a, 0.0)),
                top=lambda a, c: to_sim(self.RIM - math.tan(math.radians(self.FALL_DEG)) * max(a, 0.0)),
                name=f"{self.id}_back",
                steps=self._wall_steps(self.width),
            )
        )
        for sign in (-1.0, 1.0):
            parts.append(
                wall_strip(
                    to_sim_point(self.origin),
                    self.forward,
                    self.across,
                    (0.0, 1.0, 0.0),
                    [(0.0, to_sim(sign * half)), (to_sim(self.DEPTH), to_sim(sign * half))],
                    base=lambda a, c: to_sim(-math.tan(math.radians(self.FALL_DEG)) * max(a, 0.0)),
                    top=lambda a, c: to_sim(self.RIM - math.tan(math.radians(self.FALL_DEG)) * max(a, 0.0)),
                    name=f"{self.id}_side{int(sign)}",
                    steps=self._wall_steps(self.DEPTH),
                )
            )
        self._mesh = merge_meshes(parts, name=f"{self.id}_deck")
        return [self._mesh]

    def local_sockets(self) -> dict[str, Socket]:
        # **Past the back wall, not in front of it.** `MarbleSimulation` takes
        # the last module's `exit` as the machine's finish gate and retires -
        # freezes, and removes from the world - anything that reaches it. This
        # socket used to stand at `DEPTH - 0.2`, while a marble resting against
        # the back wall centres at `DEPTH - MARBLE_RADIUS`, which is 0.285:
        # the gate was 0.085 layout units in *front* of the resting place, so
        # the wall could never stop anybody. Everything that reached the back
        # of the deck was captured just before it touched, and stood frozen
        # there for the rest of the film. The wall is the thing that stops the
        # field; the gate is for a marble that has left over it.
        position = to_sim_point(self._at(self.DEPTH + self.CATCH, 0.0))
        return {
            "entry": Socket(
                name="entry",
                frame=Transform(position=to_sim_point(self._at(0.0, 0.0)),
                                rotation=basis_from_forward_up(self.forward, (0.0, 1.0, 0.0))),
                kind=GUIDED,
                width=to_sim(self.width),
                height=to_sim(self.RIM),
            ),
            "exit": Socket(
                name="exit",
                frame=Transform(position=position,
                                rotation=basis_from_forward_up(self.forward, (0.0, 1.0, 0.0))),
                kind=GUIDED,
                width=to_sim(self.width),
                height=to_sim(self.RIM),
            ),
        }

    def local_bounds(self) -> Aabb:
        bounds = self.local_colliders()[0].aabb()
        return Aabb(
            tuple(v - MARBLE_DIAMETER for v in bounds.lower),
            tuple(v + MARBLE_DIAMETER for v in bounds.upper),
        )

    def local_probes(self) -> list[Probe]:
        """Rays at the deck, so a missing floor is a finding and not a mystery."""
        probes: list[Probe] = []
        reach = 4.0 * MARBLE_RADIUS
        for along in (1.0, 0.5 * self.DEPTH, self.DEPTH - 1.0):
            for across in (-0.3 * self.width, 0.0, 0.3 * self.width):
                point = to_sim_point(self._at(along, across))
                above = (point[0], point[1] + reach, point[2])
                probes.append(
                    Probe(start=above, end=point, expect_hit=True, tolerance=0.05,
                          label=f"{self.id}:deck")
                )
        return probes

    def holds(self, position: Sequence[float]) -> bool:
        """Is this point on the deck? Used to excuse a finisher's containment."""
        offset = [position[axis] - to_sim_point(self.origin)[axis] for axis in range(3)]
        along = sum(offset[axis] * self.forward[axis] for axis in range(3))
        across = sum(offset[axis] * self.across[axis] for axis in range(3))
        return (
            -MARBLE_DIAMETER <= along <= to_sim(self.DEPTH) + MARBLE_DIAMETER
            and abs(across) <= to_sim(0.5 * self.width) + MARBLE_DIAMETER
        )

class Wheel(Spinners):
    """A blade wheel sized to the channel it is standing in.

    `sloped.stations.Spinners` is reused for its pose law, its shaft, its
    alternating sense and its "the blade must not pass through the floor"
    arithmetic. What it cannot supply is the *reach*: its tip radius is
    `0.90 * run.scale` layout units, which was measured against Race #1's
    0.94 half width at scale 1.0 and becomes 1.80 in a Race #2 channel whose
    half width is 1.17. Installed unchanged it sweeps 0.63 units through each
    wall, and a blade that overhangs a wall traps a marble against it: the
    first three-concept run left seven of eight racers stuck at two wheels.

    So the reach is a **fraction of the local half width**, and the local half
    width includes the run's per-sample width factor, because that is what
    Race #2 varies and `run.scale` is constant.

    ## Reach is the whole design decision

    `reach = 0.96` is a *gate*: the blade sweeps the clear channel and the field
    passes between blades, metered into bursts. That is Race #1's obstacle.

    `reach = 0.55` is a *disruptor*: there is 0.6 of a layout unit either side
    of the blade, which is more than a marble diameter, so nothing is ever
    stopped - a marble is deflected, delayed or let through depending on where
    the blade is when it arrives. That changes order without risking a jam, and
    a jam with eight marbles arriving together is the failure mode a folded
    course has and a strung-out one does not.
    """

    def __init__(
        self,
        module_id: str,
        run: TrackRun,
        at: int,
        reach: float = 0.55,
        blades: int = 4,
        rate: float = 4.2,
        offsets: Sequence[float] = (0.0,),
        blade_height: float | None = None,
    ) -> None:
        self.reach = float(reach)
        self.blades = int(blades)
        self.width_factor = float(run.widths[min(max(at, 0), len(run.widths) - 1)])
        # `TIP` is read as `TIP * run.scale` by the parent, so this is the
        # layout reach divided back out by the scale.
        self.TIP = self.reach * layout.CHANNEL_HALF * self.width_factor
        if blade_height is not None:
            self.BLADE_HEIGHT = float(blade_height)
        super().__init__(module_id, run, at=at, offsets=offsets, rate=rate)

    def half_width(self) -> float:
        """The clear half channel at the wheel, in layout units."""
        return layout.CHANNEL_HALF * self.run.scale * self.width_factor

    def side_gap(self) -> float:
        """How much clear channel is left beside the blade, in layout units.

        Reported because it is the number that decides whether the wheel is a
        gate or a disruptor, and a wheel whose gap has quietly fallen under a
        marble diameter is a wheel that will jam on the seed nobody ran.
        """
        return self.half_width() - self.TIP * self.run.scale

    def _hub_of(self, index: int):
        """The hub, with the cradle read at the *local* tip, not Race #1's.

        The parent asks `floor_y_at(TIP, CHANNEL_HALF)`, which is the cradle
        height at a lateral offset of `TIP` in a channel of half width 0.94.
        Here the tip's position in section coordinates is
        `reach * CHANNEL_HALF * width`, and the cradle rise there is scaled by
        the run's profile scale - the same expression `TrackRun.surface_point`
        uses, so the blade clears the floor the collider actually has.
        """
        _lateral, up, _forward = self.run.frames[index]
        centre = self.run.sim_path[index]
        across_profile = self.reach * layout.CHANNEL_HALF * self.width_factor
        tip_floor = to_sim(layout.floor_y_at(across_profile) * self.run.scale)
        base = tip_floor + to_sim(self.FLOOR_CLEARANCE * self.run.scale)
        half_height = to_sim(0.5 * self.BLADE_HEIGHT * self.run.scale)
        hub = tuple(centre[axis] + up[axis] * (base + half_height) for axis in range(3))
        return hub, half_height

    def local_actuators(self):
        """The parent's wheel, with this module's blade count.

        `layout.SPINNER_BLADES` is a global four. A gate wants fewer blades so
        its opening lasts long enough to be a gap rather than a flicker, and a
        disruptor wants more so that arrival phase matters more often.
        """
        actuators = []
        radius_layout = self.TIP * self.run.scale
        for wheel, (index, phase, rate) in enumerate(self._stations()):
            lateral, up, forward = self.run.frames[index]
            hub, half_height = self._hub_of(index)
            for blade in range(self.blades):
                actuators.append(
                    Spinner(
                        name=f"wheel{wheel}_blade{blade}",
                        half_extents=(
                            to_sim(0.5 * radius_layout),
                            half_height,
                            to_sim(0.5 * self.THICK * self.run.scale),
                        ),
                        hub=hub,
                        lateral=lateral,
                        up=up,
                        forward=forward,
                        radius=to_sim(0.5 * radius_layout),
                        blade=blade,
                        blades=self.blades,
                        phase=phase,
                        rate=rate,
                    )
                )
        return actuators

    def describe(self):
        data = super().describe()
        data.update(
            {
                "kind": "Wheel",
                "blades": self.blades,
                "reach": round(self.reach, 4),
                "half_width": round(self.half_width(), 4),
                "side_gap": round(self.side_gap(), 4),
                "gate": self.side_gap() < 2.0 * layout.MARBLE_RADIUS,
            }
        )
        return data
