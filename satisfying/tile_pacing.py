"""What is happening while nothing is happening.

Phase 2 measured stagnation with one number per run - `longest_body_gap_seconds`
- and set the production ceiling at 4.0 s. Phase 3 rendered seven seeds whose
worst mid-run gaps were 0.88-2.27 s and concluded, correctly and narrowly, that
**a 2.3-second pause is shown to read and a 3.6-second one is not**. Phase 4
renders the gaps nobody had seen and answers the question the duration alone
cannot: is a four-second stretch with no new tile a *pause* or a *stall*?

It is a pause or a stall depending on **where in the run it falls**, and
almost not at all on what the ball is doing during it - which is the opposite
of what this module was built to find out, and is why it measures both. A
no-progress gap is a window of the event stream, and the event stream already
knows everything a viewer can see during it: how often the ball struck a wall,
how close those strikes came to the tiles that are still dark, how much of the
arena it crossed, how many different directions it flew in, and whether it was
retracing a path it had already flown. Those readings are what establish that
the activity is *not* the variable: over 2,244 gaps the contact rate never
drops below 3.89/s and no gap repeats a cycle at all.

## The window

A gap runs from one activation to the next - or from `t=0` to the first
activation, or from the last activation to the end of the run. Every contact in
a gap is by construction a **duplicate**: a contact on a dark tile would have
ended the gap. So a gap is exactly the stretch where the arena's progress
readout is frozen, which is the thing a viewer notices.

Gaps are classified once, by where they start, because the same four seconds
means three different things in three places:

* **body** - fewer than `total - 3` lit. Four or more dark tiles are on screen
  and there is nothing specific to wait for.
* **approach** - `total - 3` or `total - 2` lit. Two or three dark slots in a
  ring that already reads as finished.
* **final hunt** - `total - 1` lit. One dark tile left; the wait *is* the
  ending, and the brief allows it to be longer.

`PacingGate` gives each band its own ceiling, and the ordering is the finding
of the phase - see its docstring.

## The readings, and what each one is for

Taken together they are the brief's list; taken apart, each is a thing that can
be true while the others are false, which is the point.

* **`collisions_per_second`** - the raw event rate. The floor under "something
  is happening". A gap with three contacts in four seconds is a ball drifting
  across an empty arena; the same four seconds with thirty contacts is a
  machine-gun of bounces.
* **`near_misses`** - contacts that landed within one drawn ball width of a
  tile that is still dark. This is the one that separates tension from noise. A
  bounce beside the last dark tile is a *miss* the viewer feels; a bounce on
  the far side of the arena is not. The threshold is a drawn ball width, so
  "near" means what it looks like on screen rather than what is small in
  simulation units.
* **`near_miss_excess`** - and this is the correction that makes the count
  mean anything. With twenty-two tiles still dark, **87% of the wall is within
  a ball width of a dark tile**, so every contact is a "near miss" and the
  count is just the contact count. `near_miss_chance` is the exact share of the
  perimeter that lies inside the near band, computed by unioning each dark
  tile's interval with its margin, and `near_miss_excess` is the observed share
  minus it. A 3.21 s gap at 29 of 51 scores fifteen near misses out of fifteen
  contacts and an excess of **zero**: that gap has no tension in it, only
  targets. The same instrument gives seed 3530's 3.82 s final hunt an excess of
  **-0.06** - the ball spent nearly four seconds avoiding the one tile it
  needed, which is a different failure and a visible one.
* **`area_coverage`** - the share of the arena's interior the ball's path
  crossed, on a grid whose cell is `COVERAGE_CELL_WU`. Coverage: did the ball
  work the whole arena or one corner? The first draft of this module asked the
  same question as "the widest separation between two contacts, over the
  diameter" and that reading is **0.99 in every window of every seed** - any
  five contacts on a seventeen-gon include a near-opposite pair - so it was
  replaced rather than reported.
* **`distinct_sides`** - how many of the seventeen walls it touched. The same
  question asked discretely, and the one that catches a ball rattling between
  two adjacent walls at a high event rate.
* **`heading_changes`** - how many meaningfully different directions it flew
  in. A geometric orbit has few; a scattering path has many.
* **`repeat_ratio`** and **`longest_repeat_cycle`** - is it retracing? The
  ratio is the share of contacts that landed on a tile the gap had already
  touched; the cycle reuses Phase 2's periodic detector inside the window. The
  brief asks that a repetitive orbit be rejected *regardless of duration*, and
  these two are how that is stated.
* **`targets_remaining`** and **`target_sides`** - what the viewer has to
  anticipate. With a fixed orthographic camera showing the whole arena, every
  dark tile is on screen at every instant, so "are the remaining targets
  visible" is structurally always yes in Category 3; the question that has
  content is how many there are and whether they are spread around the ring or
  clustered on one wall.

## The gate

`PacingGate` is the production rule, and it is deliberately shaped like
`tile_evaluator.AcceptanceRule`: named thresholds, each passed or failed on its
own, and a verdict that reports every failure rather than the first. The
default thresholds are not preferences. They come from the Phase 4 renders
recorded in `docs/category3_tile_escape_phase4.md`, and the report states which
clip moved each one.

Nothing here scores. There is no weighted sum and no total, because the thing
Phase 4 learned is that duration and activity trade off in a way a single
number hides: 3.71 s with eleven near misses is a better clip than 2.5 s of
repetitive rattling, and a scalar that ranked them would also rank a 6 s stall
against a busy 3 s one and get it wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from satisfying.tile_arena import Arena
from satisfying.tile_escape import TileEscapeRun
from satisfying.tile_evaluator import PeriodicPattern, longest_periodic_run

__all__ = [
    "NEAR_MISS_BALL_WIDTHS",
    "HEADING_EPSILON_DEGREES",
    "REVIEW_FLOOR_SECONDS",
    "COVERAGE_CELL_WU",
    "GapWindow",
    "PacingGate",
    "PacingVerdict",
    "DEFAULT_GATE",
    "near_miss_distance",
    "near_miss_chance",
    "area_coverage",
    "gap_windows",
    "judge",
    "worst_body_gap",
    "final_hunt_gap",
]


# A near miss is measured in **drawn ball widths**, not in simulation units,
# because it is a statement about what the frame looks like. The scene draws
# the ball at `BALL_DRAW_SCALE = 1.45` times the collision radius, so at the
# locked configuration one drawn width is 2 * 1.45 * 0.45 = 1.305 wu against a
# tile 1.225 wu long: "the ball struck within its own width of a dark tile",
# which on a 1080-wide frame is 61 px - close enough that the eye reads the two
# as one event.
NEAR_MISS_BALL_WIDTHS = 1.0
BALL_DRAW_SCALE = 1.45

# Two headings count as different if they differ by more than this. Fifteen
# degrees is a little under the 21.2 degrees one side of a 17-gon subtends, so
# two flights that leave for different walls always count as different and two
# that retrace the same leg never do.
HEADING_EPSILON_DEGREES = 15.0

# Gaps shorter than this are not examined. At the locked operating point the
# median activation interval is about 0.6 s, and a stretch under a second and a
# half is not perceived as a stall at all - it is the ordinary rhythm of the
# run. Examining them would make every run fail a repetition test on a
# three-contact window.
REVIEW_FLOOR_SECONDS = 1.5

# The cell of the coverage grid, in simulation units. Two thirds of a drawn
# ball width: small enough that a path crossing the same cell twice really is
# the same corridor, large enough that seventeen chords do not fill the arena.
# Measured alternatives at the locked configuration - a 1.25 wu cell puts every
# window between 0.58 and 0.94 and separates nothing, a 0.63 wu cell compresses
# them all under 0.55 - so this is the size at which the reading discriminates.
COVERAGE_CELL_WU = 0.833


def _segment_distance(point: tuple[float, float],
                      start: Sequence[float],
                      end: Sequence[float]) -> float:
    """Euclidean distance from a point to a line segment."""
    px, py = point
    ax, ay = float(start[0]), float(start[1])
    bx, by = float(end[0]), float(end[1])
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 0.0:
        return math.hypot(px - ax, py - ay)
    along = ((px - ax) * dx + (py - ay) * dy) / span
    along = min(1.0, max(0.0, along))
    return math.hypot(px - (ax + along * dx), py - (ay + along * dy))


def near_miss_distance(arena: Arena,
                       contact: tuple[float, float],
                       dark: Sequence[int]) -> float:
    """How far a contact point landed from the nearest tile that is still dark.

    Zero would mean the contact was *on* a dark tile, which cannot happen
    inside a gap - that contact is an activation and ends the gap. So the
    smallest value this returns in practice is the distance across the drawn
    seam between two tiles.
    """
    if not dark:
        return math.inf
    best = math.inf
    for index in dark:
        tile = arena.tiles[index]
        best = min(best, _segment_distance(contact, tile.start, tile.end))
    return best


def near_miss_chance(arena: Arena, dark: Sequence[int], near_miss_wu: float) -> float:
    """The share of the wall that lies within `near_miss_wu` of a dark tile.

    The denominator a near-miss count has to be read against. Tiles are indexed
    around the perimeter (`side * tiles_per_side + slot`), so each tile owns the
    interval `[i*L, (i+1)*L)` of a cyclic perimeter of length `total * L`; a
    dark tile's near band is that interval grown by `near_miss_wu` at both ends,
    and the chance is the length of the union of those bands over the whole
    perimeter.

    At the locked configuration one dark tile puts 6.1% of the wall in the
    band and ten dark tiles put 61% of it there, which is why the raw count
    means nothing without this number beside it.
    """
    total = arena.total_tiles
    length = arena.tile_length
    perimeter = total * length
    if not dark or perimeter <= 0.0:
        return 0.0
    spans: list[tuple[float, float]] = []
    for index in dark:
        spans.append((index * length - near_miss_wu,
                      (index + 1) * length + near_miss_wu))
    # Unwrap onto [0, perimeter) by splitting anything that crosses the seam,
    # then merge. Splitting first is what makes the union exact at the wrap
    # rather than double-counting the tile at index 0.
    pieces: list[tuple[float, float]] = []
    for lo, hi in spans:
        # The width is taken **before** the wrap. Reading it afterwards - as
        # `hi = lo + (hi - lo)` with `lo` already reduced - measures the band
        # against the wrapped origin and produces intervals with a negative
        # length, which then subtract from the union: one dark tile came out at
        # a chance of -0.94.
        width = hi - lo
        if width >= perimeter:
            return 1.0
        lo %= perimeter
        hi = lo + width
        if hi <= perimeter:
            pieces.append((lo, hi))
        else:
            pieces.append((lo, perimeter))
            pieces.append((0.0, hi - perimeter))
    pieces.sort()
    covered = 0.0
    current_lo, current_hi = pieces[0]
    for lo, hi in pieces[1:]:
        if lo > current_hi:
            covered += current_hi - current_lo
            current_lo, current_hi = lo, hi
        else:
            current_hi = max(current_hi, hi)
    covered += current_hi - current_lo
    return min(1.0, covered / perimeter)


def _in_play_cells(arena: Arena, cell: float) -> tuple[int, frozenset[tuple[int, int]]]:
    """The grid cells whose centre is inside the arena. Cached per arena+cell."""
    key = (id(arena), cell)
    cached = _CELL_CACHE.get(key)
    if cached is not None:
        return cached
    radius = arena.circumradius
    side_count = max(1, int(math.ceil(2.0 * radius / cell)))
    cells = set()
    for i in range(side_count):
        for j in range(side_count):
            x = -radius + (i + 0.5) * cell
            y = -radius + (j + 0.5) * cell
            if arena.contains((x, y)):
                cells.add((i, j))
    result = (side_count, frozenset(cells))
    _CELL_CACHE[key] = result
    return result


_CELL_CACHE: dict[tuple[int, float], tuple[int, frozenset[tuple[int, int]]]] = {}


def area_coverage(arena: Arena,
                  path: Sequence[tuple[float, float]],
                  cell: float = COVERAGE_CELL_WU) -> float:
    """The share of the arena's interior a polyline crossed.

    `path` is the ordered list of flight endpoints - which at gravity 0 is the
    exact trajectory, because a flight is then a straight line. If Category 3
    ever runs at gravity != 0 this becomes a chord approximation of a parabola
    and has to be resampled; the assertion is worth making here rather than
    discovering later, so the sampler walks each leg at `cell/2` and would
    follow a curve if one were handed to it.
    """
    radius = arena.circumradius
    side_count, cells = _in_play_cells(arena, cell)
    if not cells:
        return 0.0
    visited: set[tuple[int, int]] = set()
    for k in range(len(path) - 1):
        ax, ay = path[k]
        bx, by = path[k + 1]
        distance = math.hypot(bx - ax, by - ay)
        steps = max(2, int(distance / (cell * 0.5)) + 1)
        for step in range(steps + 1):
            f = step / steps
            x = ax + (bx - ax) * f
            y = ay + (by - ay) * f
            index = (int((x + radius) / cell), int((y + radius) / cell))
            if index in cells:
                visited.add(index)
    return len(visited) / len(cells)


@dataclass(frozen=True)
class GapWindow:
    """One stretch with no new tile, and everything visible during it."""

    index: int
    start_seconds: float
    end_seconds: float
    seconds: float
    tiles_lit_at_start: int
    total_tiles: int
    kind: str  # "opening" | "body" | "approach" | "final_hunt" | "tail"

    collisions: int
    collisions_per_second: float
    distinct_tiles: int
    distinct_sides: int
    near_misses: int
    near_miss_rate: float
    near_miss_share: float
    near_miss_chance: float
    near_miss_excess: float
    nearest_dark_wu: float
    repeat_ratio: float
    longest_repeat_cycle: PeriodicPattern
    heading_changes: int
    travel_wu: float
    area_coverage: float
    targets_remaining: int
    target_sides: int

    @property
    def sides_per_second(self) -> float:
        """How fast the ball worked its way round the arena.

        The one activity reading that is not a restatement of the duration.
        The contact rate is nearly constant across the population (3.89 to
        12.96, p05 to p95 of 4.02 to 7.07) and both the side count and the area
        coverage rise with the length of a gap - but their *rate* does not:
        1.62 to 5.27 sides per second over the same 2,244 gaps, which is a ball
        rattling in one arc against a ball crossing the arena.
        """
        return self.distinct_sides / self.seconds if self.seconds > 0.0 else 0.0

    @property
    def is_body(self) -> bool:
        """The mid-run gaps, as `tile_evaluator.longest_body_gap_seconds`
        counts them: everything that begins before the last three tiles.

        `approach` is deliberately *not* included. Phase 2 lumped the two gaps
        at 48 and 49 of 51 in with the body and judged them by the body's
        ceiling; Phase 4's renders say they are the hardest band of the three,
        so the gate gives them their own.
        """
        return self.kind in ("opening", "body")

    def as_dict(self) -> dict[str, Any]:
        def r(value: float, places: int = 3) -> float:
            return round(value, places)

        return {
            "index": self.index,
            "start_seconds": r(self.start_seconds),
            "end_seconds": r(self.end_seconds),
            "seconds": r(self.seconds),
            "tiles_lit_at_start": self.tiles_lit_at_start,
            "total_tiles": self.total_tiles,
            "kind": self.kind,
            "is_body": self.is_body,
            "collisions": self.collisions,
            "collisions_per_second": r(self.collisions_per_second, 2),
            "distinct_tiles": self.distinct_tiles,
            "distinct_sides": self.distinct_sides,
            "sides_per_second": r(self.sides_per_second, 2),
            "near_misses": self.near_misses,
            "near_miss_rate": r(self.near_miss_rate, 2),
            "near_miss_share": r(self.near_miss_share),
            "near_miss_chance": r(self.near_miss_chance),
            "near_miss_excess": r(self.near_miss_excess),
            "nearest_dark_wu": (
                None if math.isinf(self.nearest_dark_wu) else r(self.nearest_dark_wu)
            ),
            "repeat_ratio": r(self.repeat_ratio),
            "longest_repeat_cycle": self.longest_repeat_cycle.as_dict(),
            "heading_changes": self.heading_changes,
            "travel_wu": r(self.travel_wu, 1),
            "area_coverage": r(self.area_coverage),
            "targets_remaining": self.targets_remaining,
            "target_sides": self.target_sides,
        }


def _classify(lit: int, total: int) -> str:
    if lit == 0:
        return "opening"
    if lit >= total:
        return "tail"
    if lit == total - 1:
        return "final_hunt"
    if lit >= total - 3:
        return "approach"
    return "body"


def gap_windows(run: TileEscapeRun,
                arena: Arena,
                near_miss_wu: float | None = None) -> tuple[GapWindow, ...]:
    """Every no-progress window of a run, with its perceptual activity.

    Pure: no simulation, no sampling, no pixels. The inputs are the ordered
    collision list and the arena geometry, which is what makes these numbers
    as deterministic as the run itself and reproducible from a playback
    document alone.
    """
    total = run.total_tiles
    if near_miss_wu is None:
        near_miss_wu = NEAR_MISS_BALL_WIDTHS * 2.0 * BALL_DRAW_SCALE * run.config.ball_radius
    collisions = run.collisions
    # The boundaries: t=0, each activation, and the end of the run.
    activation_times = [hit.time for hit in collisions if hit.is_new]
    edges = [0.0] + activation_times
    if run.end_time > edges[-1]:
        edges.append(run.end_time)

    # Which tiles are dark at each boundary. A gap's dark set is constant
    # across it, so it is computed once per window rather than per contact.
    lit_order = [hit.tile_index for hit in collisions if hit.is_new]

    windows: list[GapWindow] = []
    cursor = 0
    for index in range(len(edges) - 1):
        start, end = edges[index], edges[index + 1]
        lit_count = index
        dark = sorted(set(range(total)) - set(lit_order[:lit_count]))

        # Contacts strictly after the opening boundary and at or before the
        # closing one. The activation that closes the gap is excluded: it is
        # the event the gap was waiting for, not part of the wait.
        block = []
        while cursor < len(collisions) and collisions[cursor].time <= start:
            cursor += 1
        scan = cursor
        while scan < len(collisions) and collisions[scan].time < end:
            block.append(collisions[scan])
            scan += 1

        seconds = max(0.0, end - start)
        tiles = [hit.tile_index for hit in block]
        sides = [hit.side for hit in block]
        times = [hit.time for hit in block]
        distinct_tiles = len(set(tiles))
        distinct_sides = len(set(sides))

        misses = 0
        nearest = math.inf
        for hit in block:
            distance = near_miss_distance(arena, hit.contact, dark)
            nearest = min(nearest, distance)
            if distance <= near_miss_wu:
                misses += 1

        chance = near_miss_chance(arena, dark, near_miss_wu)
        share = misses / len(block) if block else 0.0

        # The path the ball flew during the window: the flight in progress at
        # the opening boundary, then every flight the window's own contacts
        # started, then the position at the closing boundary.
        path = _path_between(run, start, end)
        coverage = area_coverage(arena, path)

        # Heading changes, from the flights the gap's contacts started. A
        # flight's direction is its outgoing velocity, and the run stores that
        # in the flight appended after each collision; the gap's own contacts
        # index it one for one.
        headings: list[float] = []
        changes = 0
        for hit in block:
            flight = _flight_after(run, hit.time)
            if flight is None:
                continue
            angle = math.degrees(math.atan2(flight[1], flight[0]))
            if all(_angle_gap(angle, seen) > HEADING_EPSILON_DEGREES for seen in headings):
                headings.append(angle)
                changes += 1

        travel = sum(hit.flight_seconds for hit in block) * _speed(run)

        target_sides = len({arena.tiles[i].side for i in dark})
        windows.append(
            GapWindow(
                index=index,
                start_seconds=start,
                end_seconds=end,
                seconds=seconds,
                tiles_lit_at_start=lit_count,
                total_tiles=total,
                kind=_classify(lit_count, total),
                collisions=len(block),
                collisions_per_second=(len(block) / seconds if seconds > 0.0 else 0.0),
                distinct_tiles=distinct_tiles,
                distinct_sides=distinct_sides,
                near_misses=misses,
                near_miss_rate=(misses / seconds if seconds > 0.0 else 0.0),
                near_miss_share=share,
                near_miss_chance=chance,
                near_miss_excess=share - chance,
                nearest_dark_wu=nearest,
                repeat_ratio=(
                    (len(block) - distinct_tiles) / len(block) if block else 0.0
                ),
                longest_repeat_cycle=longest_periodic_run(tiles, times),
                heading_changes=changes,
                travel_wu=travel,
                area_coverage=coverage,
                targets_remaining=len(dark),
                target_sides=target_sides,
            )
        )
    return tuple(windows)


def _speed(run: TileEscapeRun) -> float:
    return run.config.speed


def _path_between(run: TileEscapeRun, start: float, end: float) -> list[tuple[float, float]]:
    """The ball's polyline over `[start, end]`, from the canonical flights.

    Includes the two boundary positions, so a window that opens or closes in
    the middle of a flight measures the part of that flight it actually
    contains rather than the whole leg.
    """
    points: list[tuple[float, float]] = [_position_at(run, start)]
    for flight in run.flights:
        if start < flight.t_start < end:
            points.append((flight.position[0], flight.position[1]))
    points.append(_position_at(run, end))
    return points


def _position_at(run: TileEscapeRun, t: float) -> tuple[float, float]:
    """The ball at `t`, in the same closed form the renderer uses."""
    flights = run.flights
    lo, hi = 0, len(flights) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if flights[mid].t_start <= t:
            lo = mid
        else:
            hi = mid - 1
    flight = flights[lo]
    dt = max(0.0, t - flight.t_start)
    gravity = run.config.gravity
    return (
        flight.position[0] + flight.velocity[0] * dt,
        flight.position[1] + flight.velocity[1] * dt - 0.5 * gravity * dt * dt,
    )


def _flight_after(run: TileEscapeRun, when: float) -> tuple[float, float] | None:
    """The velocity of the flight that begins at `when`, if there is one."""
    for flight in run.flights:
        if abs(flight.t_start - when) <= 1.0e-12:
            return (flight.velocity[0], flight.velocity[1])
    return None


def _angle_gap(a: float, b: float) -> float:
    delta = abs(a - b) % 360.0
    return min(delta, 360.0 - delta)


def worst_body_gap(windows: Sequence[GapWindow]) -> GapWindow | None:
    body = [w for w in windows if w.is_body]
    return max(body, key=lambda w: w.seconds) if body else None


def final_hunt_gap(windows: Sequence[GapWindow]) -> GapWindow | None:
    for window in windows:
        if window.kind == "final_hunt":
            return window
    return None


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PacingGate:
    """The Phase 4 production pacing rule: three duration bands, one guard.

    Every number below is quoted against a rendered clip in
    `docs/category3_tile_escape_phase4.md`. The shape is the finding: the
    ceiling is **not monotone in progress**. A long gap is least visible in the
    middle of the run, most visible in the approach, and acceptable again at
    the very end - because what the viewer is doing changes three times.

    The rule the three ceilings express: **the fewer targets remain, the longer
    a pause may be, because the viewer knows exactly what they are waiting
    for.** That is not the shape this phase expected to find and it is what the
    clips show.

    * **body** (fewer than `total - 3` lit), ceiling 4.0 s. Four or more dark
      tiles are scattered round a visibly unfinished ring, so there is nothing
      specific to anticipate - a pause here is only "some tile, somewhere,
      still". Rendered: 3.21 s at 29 of 51 and 3.71 s at 34 of 51 are
      indistinguishable from ordinary play; 5.15 s at 42 of 51, with nine
      scattered targets and the highest contact rate of anything rendered
      (7.4/s), is legible as a stall. The ceiling is Phase 2's, now confirmed
      by render rather than inherited from a percentile.
    * **approach** (`total - 3` or `total - 2` lit), ceiling 4.5 s. Two or
      three dark slots, usually adjacent, in a ring that already reads as
      finished: the eye has one place to watch and a miss beside it registers.
      Rendered: 2.82 s at 49 of 51 reads clean and 4.13 s at 48 of 51 reads as
      *tension* - the three dark tiles are one run and the ball keeps arriving
      next to them - while 6.31 s at 49 of 51 is dead, eleven frames of a
      motionless "49 / 51" against a ring that looks complete.
    * **final hunt** (`total - 1` lit), ceiling 5.0 s. One target, and the
      counter turns amber to name it. Rendered: 3.82 s reads as the ending
      doing its job; 6.20 s is a wait.

    **Phase 2 bounded none of this.** `longest_body_gap_seconds` counts only
    gaps beginning before `total - 3`, so the approach band had no per-gap
    ceiling at all, and the final hunt was bounded only by `max_final_tile` at
    9.0 s. Seed 38864 - Phase 3's tension candidate - therefore passed every
    Phase 2 condition while spending 6.31 s at 49 of 51 and 6.20 s at 50 of 51,
    twelve and a half seconds of a 39.6 second run in which two tiles light.
    That seed is the reason this gate exists.

    The activity guard is a **rate**, not a count, because every count scales
    with the gap's own length. It sits below the population's first percentile
    and therefore does very little work here: over 6,000 seeds it rejects 5 of
    the 684 that pass Phase 2, against 234 rejected on duration. That is an
    honest statement about this arena rather than a weak rule - over 2,244
    reviewed gaps the contact rate never fell below 3.89/s and the
    periodic-cycle detector returned **zero at every percentile**, so there are
    barely any dead or repetitive gaps here to reject. The guard is kept
    because those are properties of *this* configuration - gravity 0,
    seventeen sides, 85 wu/s - and a change to any of the three could produce
    one.

    Cost of the whole gate: Phase 2 accepts 11.4% of seeds, Phase 2 plus this
    gate accepts 7.5%, which is still about 3,750 filmable seeds per 50,000.
    """

    # Duration ceilings, one per band. A gap over its ceiling is rejected
    # however busy it is.
    max_body_gap_seconds: float = 4.0
    max_approach_gap_seconds: float = 4.5
    max_final_gap_seconds: float = 5.0

    # Above this a gap has to meet the activity guard.
    busy_above_seconds: float = 2.5

    # The guard. Rates, so a long gap is not read as a busy one.
    min_collisions_per_second: float = 3.5
    min_sides_per_second: float = 2.0

    # Repetition, rejected at any duration.
    max_repeat_ratio: float = 0.45
    max_repeat_cycle: int = 8

    # Gaps shorter than this are not examined at all.
    review_floor_seconds: float = REVIEW_FLOOR_SECONDS

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_body_gap_seconds": self.max_body_gap_seconds,
            "max_approach_gap_seconds": self.max_approach_gap_seconds,
            "max_final_gap_seconds": self.max_final_gap_seconds,
            "busy_above_seconds": self.busy_above_seconds,
            "min_collisions_per_second": self.min_collisions_per_second,
            "min_sides_per_second": self.min_sides_per_second,
            "max_repeat_ratio": self.max_repeat_ratio,
            "max_repeat_cycle": self.max_repeat_cycle,
            "review_floor_seconds": self.review_floor_seconds,
        }

    def ceiling(self, window: GapWindow) -> float:
        """The duration ceiling for the band this gap sits in."""
        if window.kind == "final_hunt":
            return self.max_final_gap_seconds
        if window.kind == "approach":
            return self.max_approach_gap_seconds
        # A `tail` window only exists on a run that never completed, and such a
        # run fails `tile_evaluator`'s `completes` condition long before this.
        return self.max_body_gap_seconds

    def is_busy(self, window: GapWindow) -> bool:
        """Both rates. A gap meeting neither is a ball drifting."""
        return (
            window.collisions_per_second >= self.min_collisions_per_second
            and window.sides_per_second >= self.min_sides_per_second
        )

    def is_repetitive(self, window: GapWindow) -> bool:
        return (
            window.repeat_ratio > self.max_repeat_ratio
            or window.longest_repeat_cycle.length > self.max_repeat_cycle
        )


DEFAULT_GATE = PacingGate()


@dataclass(frozen=True)
class PacingVerdict:
    """Accepted or not, every condition that decided it, and the evidence.

    `offending` names the gaps, not just the conditions. "This seed failed the
    ceiling" sends an operator back to a thirty-second run with no idea where
    to look; "its 6.31 s approach gap at 49 of 51 failed the ceiling" is an
    instruction. Same reasoning as reporting every failing condition rather
    than the first, one level further down.
    """

    accepted: bool
    failures: tuple[str, ...]
    passes: tuple[str, ...]
    offending: dict[str, tuple[str, ...]]
    reviewed: tuple[GapWindow, ...]
    worst_body: GapWindow | None
    final_hunt: GapWindow | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "failures": list(self.failures),
            "passes": list(self.passes),
            "offending": {k: list(v) for k, v in sorted(self.offending.items())},
            "reviewed": [w.as_dict() for w in self.reviewed],
            "worst_body": None if self.worst_body is None else self.worst_body.as_dict(),
            "final_hunt": (
                None if self.final_hunt is None else self.final_hunt.as_dict()
            ),
        }


def judge(run: TileEscapeRun,
          arena: Arena,
          gate: PacingGate = DEFAULT_GATE) -> PacingVerdict:
    """Apply the pacing gate to a run and report every condition.

    Deterministic by construction: it reads the same collision list twice in a
    row and has no state, no randomness and no clock of its own.
    """
    windows = gap_windows(run, arena)
    reviewed = tuple(w for w in windows if w.seconds >= gate.review_floor_seconds)

    over_ceiling: list[str] = []
    not_busy: list[str] = []
    repetitive: list[str] = []
    for window in reviewed:
        label = (
            f"{window.kind} {window.seconds:.2f}s at "
            f"{window.tiles_lit_at_start}/{window.total_tiles}"
        )
        if window.seconds > gate.ceiling(window):
            over_ceiling.append(label)
        elif window.seconds > gate.busy_above_seconds and not gate.is_busy(window):
            not_busy.append(label)
        if gate.is_repetitive(window):
            repetitive.append(label)

    checks = (
        ("no_gap_over_ceiling", not over_ceiling),
        ("long_gaps_are_busy", not not_busy),
        ("no_repetitive_stall", not repetitive),
    )
    failures = tuple(name for name, ok in checks if not ok)
    passes = tuple(name for name, ok in checks if ok)
    offending = {
        name: tuple(labels)
        for name, labels in (
            ("no_gap_over_ceiling", over_ceiling),
            ("long_gaps_are_busy", not_busy),
            ("no_repetitive_stall", repetitive),
        )
        if labels
    }
    return PacingVerdict(
        accepted=not failures,
        failures=failures,
        passes=passes,
        offending=offending,
        reviewed=reviewed,
        worst_body=worst_body_gap(windows),
        final_hunt=final_hunt_gap(windows),
    )
