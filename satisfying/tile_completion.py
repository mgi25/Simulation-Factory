"""The ending: what happens after the fifty-first tile, and why it is honest.

Phase 3 ended a run by holding the finished arena on screen for two seconds.
That is a placeholder, not an ending - the hook promises *escape* and the video
never showed one. Phase 4 builds the real completion sequence, and the whole
design problem is that the escape must be both **obviously earned** and
**obviously not cheated**.

## The one idea

A convex billiard at gravity 0 has no free parameters after the release: from
the moment the ball leaves the fifty-first tile its path is a straight line and
the next wall it will reach is already determined. So the arena does not choose
where to open. **The ball's own next wall is the gate.**

That single rule is what makes the ending honest:

* the escape flight is *exactly* `run.flights[-1]`, the state the canonical
  solver left the ball in. Not a copy of it, not a recomputation - the same
  floats, asserted by a test.
* nothing steers, curves, retargets or nudges. The only thing that changes is
  that one section of wall is no longer there.
* the change happens **after** the objective is met and the viewer watches it
  happen. The brief calls this an explicit new game state, and `UNLOCKED` is
  written down in the document rather than implied by a renderer.

The alternative - pick a dramatic side, then bend the ball toward it - would be
hidden trajectory assistance, which Phase 2 rejected for the body of the run
and which there is no reason to smuggle into the last second.

## The five beats, as states

The document carries a timeline of segments, each with a **render** interval, a
**simulation** start and a rate. Simulation time is not render time during the
ending, and that is deliberate: the ball crosses the whole arena in a quarter
of a second at 85 wu/s, so an ending played at 1.0x would be over before the
arena had finished acknowledging it.

| state       | rate | what the viewer sees                                   |
|-------------|------|--------------------------------------------------------|
| `locked`    | 1.0  | the canonical run, untouched, start to completion       |
| `final_hit` | 0.0  | the fifty-first tile detonates; the ball is held        |
| `confirming`| 0.0  | a wave runs both ways around the ring from that tile    |
| `unlocking` | 0.0  | the gate section flares, then retracts outward          |
| `escaping`  | <1   | the ball is released and flies out through the opening  |
| `settled`   | 0.0  | the open arena, held briefly, and the end               |

`rate = 0.0` is a hold: the simulation clock does not advance, so the ball is
frozen exactly where the canonical run left it and **no simulated time passes
that the physics did not produce**. `rate < 1` on the escape is slow motion
over a trajectory the physics did produce. Neither can invent a position.

The `locked` segment is the identity map, which is the property that matters
most here and the one a test pins: attaching a completion block cannot move a
single frame of the run that earned it.

## Why not simply delete the whole boundary

Because the reference channel already does that, and because it throws away the
only thing this arena has that a circle does not: seventeen discrete sides. A
section that *retracts* says "this part opened"; a boundary that vanishes says
"the rules stopped applying". The gate is `2 * gate_neighbour_sides + 1`
consecutive sides centred on the side the ball is going to reach, so the
opening is an arc the eye can see the shape of, and the remaining fourteen
sides stay lit to say what was accomplished.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

from satisfying.tile_arena import Arena
from satisfying.tile_escape import TileEscapeRun

__all__ = [
    "COMPLETION_FORMAT",
    "ARENA_WIDTH_FRACTION",
    "ARENA_CENTRE_OFFSET_FRACTION",
    "DELIVERY_ASPECT",
    "CompletionError",
    "ClimaxTiming",
    "Segment",
    "EscapeRoute",
    "TIMINGS",
    "DEFAULT_TIMING",
    "escape_route",
    "gate_sides",
    "ripple_phases",
    "timeline",
    "sim_time_at",
    "state_at",
    "completion_block",
    "attach_completion",
    "total_render_seconds",
]


# Bumped when the meaning of a field changes. The renderer refuses a block it
# does not understand rather than drawing a plausible wrong ending.
COMPLETION_FORMAT = 1

# Mirrors `ARENA_WIDTH_FRACTION` in `godot/scripts/tile_escape_scene.gd`. The
# escape needs to know where the frame edge is in simulation units, because
# "the ball has left" is a statement about the frame and not about the arena.
# A test asserts the two constants agree.
ARENA_WIDTH_FRACTION = 0.765
# And the offset, for the same reason: Phase 6 moved the arena left of centre
# to clear the player's action rail, so the frame's world bounds moved with it.
# "The ball has left the frame" is asymmetric now - the left edge is nearer in
# world units than the right one - and an escape computed against a centred
# frame would cut the ball off on one side and leave it hanging on the other.
ARENA_CENTRE_OFFSET_FRACTION = -0.060
# 9:16, the locked delivery frame. 1080x1920 and the 270x480 phone check have
# the same aspect, so one number covers both and the ending is the same length
# at either size.
DELIVERY_ASPECT = 1920.0 / 1080.0


class CompletionError(RuntimeError):
    """A run or a configuration that cannot carry a completion sequence."""


@dataclass(frozen=True)
class ClimaxTiming:
    """Every clock in the ending, in render seconds after the final activation.

    Offsets rather than durations, because the thing that has to be readable is
    the *order* - hit, confirm, unlock, release - and an ordering is easier to
    check on offsets than on a chain of sums. `__post_init__` refuses any set
    that puts the release before the gate has finished opening, which is the
    one mistake that would make the ending incoherent.
    """

    name: str = "standard"
    # Beat 1. The hit-stop: the ball is held at the instant of contact.
    impact_hold_seconds: float = 0.14
    # Beat 2. The wave leaves the final tile at the impact and takes this long
    # to reach the far side of the ring.
    confirm_seconds: float = 0.52
    # Beat 3. When the gate section flares and starts to retract, and how long
    # the retraction takes.
    gate_open_at_seconds: float = 0.62
    gate_open_seconds: float = 0.30
    # Beat 4. When the ball is released, and how fast the escape plays.
    release_at_seconds: float = 0.92
    escape_rate: float = 0.45
    # How far past the frame edge the ball has to be before it counts as gone.
    #
    # Eight world units, not one: the ball drags a 0.09 s trail and at 85 wu/s
    # that streak is 7.65 wu long. With a one-unit margin the ball left the
    # frame while most of its trail was still inside it, the simulation clock
    # then stopped for the closing hold, and the last three quarters of a
    # second of the video had a blue smear frozen against the top edge. The
    # ball is not gone until its trail is.
    exit_margin_wu: float = 8.0
    # Beat 5.
    end_hold_seconds: float = 0.50
    # The gate is this many sides either side of the one the ball will reach.
    gate_neighbour_sides: int = 1

    # Offsets are compared with a tolerance, not exactly. A preset whose gate
    # opens at 0.80 and takes 0.38 has a release of exactly 1.18 by intent and
    # of 1.1800000000000002 in binary, and a strict `<` refused it at import
    # time. The constraint is "not before", and two hundred attoseconds is not
    # a beat out of order.
    ORDER_EPSILON = 1.0e-9

    def __post_init__(self) -> None:
        if self.impact_hold_seconds <= 0.0:
            raise CompletionError("the hit-stop must be positive")
        if self.gate_open_at_seconds < self.impact_hold_seconds - self.ORDER_EPSILON:
            raise CompletionError(
                "the gate cannot start opening during the hit-stop"
            )
        if self.release_at_seconds < self.gate_open_by_seconds - self.ORDER_EPSILON:
            raise CompletionError(
                f"{self.name}: the ball is released at "
                f"{self.release_at_seconds:.2f}s but the gate is not open until "
                f"{self.gate_open_at_seconds + self.gate_open_seconds:.2f}s"
            )
        if not 0.0 < self.escape_rate <= 1.0:
            raise CompletionError("the escape rate must be in (0, 1]")
        if self.gate_neighbour_sides < 0:
            raise CompletionError("gate_neighbour_sides cannot be negative")
        if self.end_hold_seconds < 0.0:
            raise CompletionError("the end hold cannot be negative")

    @property
    def gate_open_by_seconds(self) -> float:
        return self.gate_open_at_seconds + self.gate_open_seconds

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "impact_hold_seconds": self.impact_hold_seconds,
            "confirm_seconds": self.confirm_seconds,
            "gate_open_at_seconds": self.gate_open_at_seconds,
            "gate_open_seconds": self.gate_open_seconds,
            "release_at_seconds": self.release_at_seconds,
            "escape_rate": self.escape_rate,
            "exit_margin_wu": self.exit_margin_wu,
            "end_hold_seconds": self.end_hold_seconds,
            "gate_neighbour_sides": self.gate_neighbour_sides,
        }


# The four variants Phase 4 rendered and compared on seed 3530, and what each
# one looked like. They are kept rather than pruned because the comparison is
# the evidence for `standard`, and a preset nobody can re-render is an opinion.
#
#   compact      1.72 s  too fast, and the failure is specific: at +0.34 s the
#                        wave is still crossing the ring while the gate is
#                        already flaring, so the arena's answer and the unlock
#                        arrive as one event rather than as two beats.
#   standard     2.41 s  the recommendation. Wave, flare, retraction, release,
#                        each with daylight around it.
#   stretched    2.57 s  legible - if anything cleaner than `standard` - but
#                        the last third of it is a static arena.
#   narrow_gate  2.41 s  `standard` timing with a one-side opening. Three
#                        missing tiles out of fifty-one read as a chip out of
#                        the ring rather than as a section that opened. This is
#                        the comparison that settled `gate_neighbour_sides`.
TIMINGS: dict[str, ClimaxTiming] = {
    "compact": ClimaxTiming(
        name="compact",
        impact_hold_seconds=0.10,
        confirm_seconds=0.38,
        gate_open_at_seconds=0.42,
        gate_open_seconds=0.22,
        release_at_seconds=0.66,
        escape_rate=0.68,
        end_hold_seconds=0.40,
    ),
    "standard": ClimaxTiming(),
    # `stretched` lengthens the *front* beats - the hit-stop, the wave and the
    # gate - and keeps `standard`'s escape rate exactly. That is the axis worth
    # varying, and the constraint is arithmetic: the escape is over a second of
    # screen time at 0.45x, so an ending stretched by slowing it as well runs
    # past the brief's 2.5 s ceiling without making the confirmation any more
    # readable. The first draft did exactly that and came out at 3.41 s; the
    # second overcorrected into an escape *faster* than `standard`'s, which
    # made "stretched" 4 ms shorter than the preset it was meant to be longer
    # than.
    #
    # Phase 6 shortened the tail hold from 0.40 to 0.33. Not a creative change:
    # moving the arena off centre and narrowing it made the delivery frame
    # *wider in world units*, from 11.63 to 13.07 half-widths, so the ball has
    # further to travel before it has left - and every preset's escape got
    # 0.067 s longer for free. `standard` absorbed that (2.412 -> 2.479 s) but
    # `stretched` was deliberately parked 0.029 s under the 2.6 s ceiling and
    # tipped over it to 2.639. The tail hold is the right dial to take it out
    # of, because the axis this preset exists to vary is the *front* beats and
    # the hold is not one of them.
    "stretched": ClimaxTiming(
        name="stretched",
        impact_hold_seconds=0.20,
        confirm_seconds=0.70,
        gate_open_at_seconds=0.80,
        gate_open_seconds=0.38,
        release_at_seconds=1.18,
        escape_rate=0.45,
        end_hold_seconds=0.33,
    ),
    "narrow_gate": ClimaxTiming(name="narrow_gate", gate_neighbour_sides=0),
}
DEFAULT_TIMING = TIMINGS["standard"]


# --------------------------------------------------------------------------
# The escape, from the canonical state the run ended in
# --------------------------------------------------------------------------


def _first_positive_root(a: float, b: float, c: float, eps: float) -> float:
    """Smallest `t > eps` with `a t^2 + b t + c = 0`, or infinity."""
    if abs(a) < 1.0e-15:
        if abs(b) < 1.0e-15:
            return math.inf
        root = -c / b
        return root if root > eps else math.inf
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return math.inf
    sqrt_disc = math.sqrt(disc)
    best = math.inf
    for root in ((-b - sqrt_disc) / (2.0 * a), (-b + sqrt_disc) / (2.0 * a)):
        if eps < root < best:
            best = root
    return best


@dataclass(frozen=True)
class EscapeRoute:
    """Where the ball was already going, and how long it takes to get out."""

    gate_side: int
    gate_side_list: tuple[int, ...]
    gate_tiles: tuple[int, ...]
    start_seconds: float
    start_position: tuple[float, float]
    start_velocity: tuple[float, float]
    reach_seconds: float
    crossing: tuple[float, float]
    exit_seconds: float
    exit_position: tuple[float, float]
    frame_half_width_wu: float
    frame_half_height_wu: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_side": self.gate_side,
            "gate_sides": list(self.gate_side_list),
            "gate_tiles": list(self.gate_tiles),
            "start_seconds": self.start_seconds,
            "start_position": list(self.start_position),
            "start_velocity": list(self.start_velocity),
            "reach_seconds": self.reach_seconds,
            "crossing": list(self.crossing),
            "exit_seconds": self.exit_seconds,
            "exit_position": list(self.exit_position),
            "frame_half_width_wu": self.frame_half_width_wu,
            "frame_half_height_wu": self.frame_half_height_wu,
        }


def gate_sides(arena: Arena, side: int, neighbours: int) -> tuple[int, ...]:
    """The consecutive sides that form the opening, centred on `side`."""
    span = min(arena.sides, 2 * neighbours + 1)
    first = side - (span // 2)
    return tuple((first + k) % arena.sides for k in range(span))


def escape_route(run: TileEscapeRun,
                 arena: Arena,
                 timing: ClimaxTiming = DEFAULT_TIMING) -> EscapeRoute:
    """The wall the ball was already heading for, and its flight out.

    Reads `run.flights[-1]` and nothing else about the trajectory. That flight
    is the post-bounce state the solver appended after the fifty-first
    activation: position nudged inside by the skin, velocity reflected. So the
    route below is the continuation the solver itself would have produced if
    the run had not stopped on completion.
    """
    if not run.completed or run.completion_time is None:
        raise CompletionError(f"seed {run.seed} never completed; it has no ending")
    last = run.flights[-1]
    if abs(last.t_start - run.completion_time) > 1.0e-12:
        raise CompletionError(
            f"seed {run.seed}: the last flight starts at {last.t_start} but the "
            f"run completed at {run.completion_time}; this run did not stop on "
            "completion and its ending would not be the canonical continuation"
        )

    px, py = last.position
    vx, vy = last.velocity
    gravity = run.config.gravity
    limit = arena.apothem - run.config.ball_radius
    eps = run.config.time_epsilon

    best_dt, best_side = math.inf, -1
    for k in range(arena.sides):
        nx, ny = arena.side_outward_normals[k]
        root = _first_positive_root(
            -0.5 * gravity * ny,
            vx * nx + vy * ny,
            px * nx + py * ny - limit,
            eps,
        )
        if root < best_dt:
            best_dt, best_side = root, k
    if best_side < 0:
        raise CompletionError(
            f"seed {run.seed}: the ball leaves the completion contact on a path "
            "that reaches no wall; the escape cannot be built"
        )

    def at(dt: float) -> tuple[float, float]:
        return (px + vx * dt, py + vy * dt - 0.5 * gravity * dt * dt)

    half_width = arena.circumradius / ARENA_WIDTH_FRACTION
    half_height = half_width * DELIVERY_ASPECT
    # The frame's centre in world units. The camera sits `-offset * camera_size`
    # from the origin and `camera_size` is `2 * half_width`, so a leftward
    # offset puts the frame centre to the *right* of the arena's centre.
    centre_x = -ARENA_CENTRE_OFFSET_FRACTION * 2.0 * half_width
    margin_y = half_height + timing.exit_margin_wu
    exit_dt = math.inf
    for bound, axis_p, axis_v, curved in (
        (centre_x + half_width + timing.exit_margin_wu, px, vx, False),
        (centre_x - half_width - timing.exit_margin_wu, px, vx, False),
        (margin_y, py, vy, True),
        (-margin_y, py, vy, True),
    ):
        root = _first_positive_root(
            -0.5 * gravity if curved else 0.0, axis_v, axis_p - bound, eps
        )
        exit_dt = min(exit_dt, root)
    if not math.isfinite(exit_dt):
        raise CompletionError(
            f"seed {run.seed}: the escape never leaves the frame; at gravity "
            f"{gravity} a straight line always does, so this is a fault"
        )

    sides_in_gate = gate_sides(arena, best_side, timing.gate_neighbour_sides)
    tiles = tuple(
        tile.index for tile in arena.tiles if tile.side in sides_in_gate
    )
    return EscapeRoute(
        gate_side=best_side,
        gate_side_list=sides_in_gate,
        gate_tiles=tiles,
        start_seconds=run.completion_time,
        start_position=(px, py),
        start_velocity=(vx, vy),
        reach_seconds=best_dt,
        crossing=at(best_dt),
        exit_seconds=exit_dt,
        exit_position=at(exit_dt),
        frame_half_width_wu=half_width,
        frame_half_height_wu=half_height,
    )


# --------------------------------------------------------------------------
# The timeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """One state, its render interval, and how simulation time runs inside it."""

    state: str
    render_start: float
    render_end: float
    sim_start: float
    sim_rate: float

    def sim_at(self, render_t: float) -> float:
        return self.sim_start + (render_t - self.render_start) * self.sim_rate

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "render_start": self.render_start,
            "render_end": self.render_end,
            "sim_start": self.sim_start,
            "sim_rate": self.sim_rate,
        }


# The order the states must appear in. A test walks the built timeline against
# this tuple, because "gate opens before the ball is released" is the one
# property of the ending that cannot be checked by looking at a still.
STATE_SEQUENCE: tuple[str, ...] = (
    "locked",
    "final_hit",
    "confirming",
    "unlocking",
    "escaping",
    "settled",
)


def timeline(route: EscapeRoute, timing: ClimaxTiming = DEFAULT_TIMING) -> tuple[Segment, ...]:
    """The six segments, contiguous and in order."""
    t = route.start_seconds
    escape_render = route.exit_seconds / timing.escape_rate
    marks = (
        ("locked", 0.0, t, 0.0, 1.0),
        ("final_hit", t, t + timing.impact_hold_seconds, t, 0.0),
        ("confirming", t + timing.impact_hold_seconds,
         t + timing.gate_open_at_seconds, t, 0.0),
        ("unlocking", t + timing.gate_open_at_seconds,
         t + timing.release_at_seconds, t, 0.0),
        ("escaping", t + timing.release_at_seconds,
         t + timing.release_at_seconds + escape_render, t, timing.escape_rate),
        ("settled", t + timing.release_at_seconds + escape_render,
         t + timing.release_at_seconds + escape_render + timing.end_hold_seconds,
         t + route.exit_seconds, 0.0),
    )
    return tuple(
        Segment(state=name, render_start=a, render_end=b, sim_start=c, sim_rate=d)
        for name, a, b, c, d in marks
    )


def total_render_seconds(route: EscapeRoute,
                         timing: ClimaxTiming = DEFAULT_TIMING) -> float:
    return timeline(route, timing)[-1].render_end


def _segment_at(segments: Sequence[Segment], render_t: float) -> Segment:
    for segment in segments:
        if render_t < segment.render_end:
            return segment
    return segments[-1]


def sim_time_at(segments: Sequence[Segment], render_t: float) -> float:
    """Simulation time at a render instant. Identity below the completion."""
    if render_t <= segments[0].render_end:
        return max(0.0, render_t)
    return _segment_at(segments, render_t).sim_at(render_t)


def state_at(segments: Sequence[Segment], render_t: float) -> str:
    if render_t <= segments[0].render_end:
        return segments[0].state
    return _segment_at(segments, render_t).state


# --------------------------------------------------------------------------
# The confirmation wave
# --------------------------------------------------------------------------


def ripple_phases(arena: Arena, final_tile: int) -> tuple[float, ...]:
    """When each tile is reached by the confirmation wave, in [0, 1].

    Tiles are numbered around the perimeter, so the wave is a cyclic distance:
    it leaves the final tile in both directions at once and the two fronts meet
    on the opposite side of the ring. That shape is the point - a wave with one
    front would read as a sweep with a direction, and this one reads as the
    arena answering the tile that was just hit.
    """
    total = arena.total_tiles
    half = total / 2.0
    phases = []
    for index in range(total):
        forward = (index - final_tile) % total
        distance = min(forward, total - forward)
        phases.append(distance / half if half > 0.0 else 0.0)
    return tuple(phases)


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def completion_block(run: TileEscapeRun,
                     arena: Arena,
                     timing: ClimaxTiming = DEFAULT_TIMING) -> dict[str, Any]:
    """Everything the renderer needs for the ending, and nothing it may invent."""
    route = escape_route(run, arena, timing)
    segments = timeline(route, timing)
    final = [hit for hit in run.collisions if hit.is_new][-1]
    return {
        "format": COMPLETION_FORMAT,
        "timing": timing.as_dict(),
        "final_tile": final.tile_index,
        "final_side": final.side,
        "final_seconds": final.time,
        "final_contact": [final.contact[0], final.contact[1]],
        "escape": {
            "t": route.start_seconds,
            "p": list(route.start_position),
            "v": list(route.start_velocity),
        },
        "route": route.as_dict(),
        "ripple_phase": list(ripple_phases(arena, final.tile_index)),
        "states": list(STATE_SEQUENCE),
        "timeline": [segment.as_dict() for segment in segments],
        "total_render_seconds": segments[-1].render_end,
        "climax_seconds": segments[-1].render_end - route.start_seconds,
    }


def attach_completion(document: dict[str, Any],
                      run: TileEscapeRun,
                      arena: Arena,
                      timing: ClimaxTiming = DEFAULT_TIMING) -> dict[str, Any]:
    """Return the playback document with a `completion` block added.

    A new dictionary, never a mutation, and the canonical fields are copied
    across untouched. Nothing under `flights`, `collisions`, `activations` or
    `digest` is read or written here, which is the mechanical reason a
    completion block cannot change the run it describes.
    """
    if int(document.get("seed", -1)) != run.seed:
        raise CompletionError(
            f"document is for seed {document.get('seed')}, run is seed {run.seed}"
        )
    merged = dict(document)
    merged["completion"] = completion_block(run, arena, timing)
    return merged


def named_timing(name: str, **overrides: Any) -> ClimaxTiming:
    """A preset by name, optionally with fields replaced."""
    if name not in TIMINGS:
        raise CompletionError(
            f"unknown climax timing {name!r}; known: {sorted(TIMINGS)}"
        )
    base = TIMINGS[name]
    return replace(base, **overrides) if overrides else base
