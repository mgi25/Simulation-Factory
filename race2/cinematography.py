"""Three candidate cameras over one hero replay, and the markers they cut on.

The brief asks for three lightweight variants sharing infrastructure, not three
systems. What they share is everything: one `Spine`, one rail per reach, one
`PackTrack`, the same six rigs. **What differs is the edit** - how many shots,
which rig covers which stretch, and where the cuts land - which is what makes
the comparison a comparison about cinematography rather than about one
candidate having been given a better lens.

## Markers, not times

Every boundary below is a *marker*: the first or last contact of a named
station, the release, the winner's crossing. None of the three schedules
contains a number of seconds. That is V28's own pattern and it is kept for
V28's reason - the same authored schedule then fits a fast seed and a slow one,
and two runs on one replay produce the same track to the byte - and it is what
makes these cameras reusable on a race this session never saw.

## Where the cuts land, and why there

Each candidate cuts **on a mechanism contact**. Not near one: on the frame of
it. That is the brief's "cut on motion" made checkable, and it is the reason
`race2.flow` can report a cut-on reason per shot rather than a shrug. A cut
placed in a stretch of travelling is a cut the viewer has to recover from; a
cut placed on the frame a wheel hits the leader is one they read as a second
angle on the same collision.

## The final sprint is not cut at all

All three candidates run **one uninterrupted take from the last powered
mechanism to the end of the film**. On the hero seed that is 12.68 s to 19.15 s
- six and a half seconds containing the last wheel, m7 taking the lead at
13.12, m2 taking it back at 14.38, m7 taking it again at 15.57, the 0.067 s
crossing, and all eight racers home. It is the longest take in each film by
some way, and it is the one the brief makes a hard rule rather than a
preference: a comeback the viewer did not watch happen is a result, not a race.

## The three

**A, continuous chase.** Four shots. One rig family - a rear three-quarter
chase - for everything between the hook and the run-in. The most conservative
possible answer, and its job is to isolate one variable: how much of V28's
problem was the cutting, with nothing else changed.

**B, racing broadcast hybrid.** Five shots, four rigs. A rear three-quarter
through the drum, a side pursuit across the sweep's consequence, a long-trailed
bend orbit through the pair and the fourth hairpin, then the run-in. Variety
bought from rig changes at motivated cuts rather than from cutting more often.

**C, low pursuit.** Six shots, lower and closer throughout, with the lift
pulled under the rail and the reach at its floor. Larger racers and stronger
foreground, at the cost of seeing less of what is coming.
"""

from __future__ import annotations

from typing import Any, Sequence

from race2.rig import Plan, Shot

__all__ = ["markers", "plan_a", "plan_b", "plan_c", "CANDIDATES", "MIN_SHOT"]

# The shortest a shot may be. Under a second and a half a cut in a four-to-six
# shot film reads as a stumble rather than as an angle - deliberately far above
# V28's 0.80, because this budget is a fifth of the size and a short shot in it
# is a mistake rather than a beat.
MIN_SHOT = 1.50
# How long after the last finisher the film holds.
TAIL = 0.40


def markers(course, outcome, timeline) -> dict[str, Any]:
    """The race's own moments, as the only thing the schedules are authored on.

    Returns the release, the first and last contact of each powered station in
    course order, the winner's crossing and the end of the film.
    """
    powered = [
        module_id
        for module_id in course.stations
        if (module := course.machine.modules.get(module_id)) is not None
        and module.local_actuators()
    ]
    order = {module_id: index for index, module_id in enumerate(powered)}
    first: dict[str, float] = {}
    last: dict[str, float] = {}
    for event in timeline.events:
        if event.kind != "mechanism_hit":
            continue
        module = event.detail.split(" into ")[-1].split(" ")[0]
        if module in order:
            first.setdefault(module, event.time)
            last[module] = event.time

    finishes = sorted(
        racer.finish_time for racer in outcome.racers if racer.finish_time is not None
    )
    winner_at = finishes[0] if finishes else outcome.seconds
    end = (finishes[-1] + TAIL) if finishes else winner_at + 1.8
    return {
        "release": float(timeline.start),
        "stations": [module_id for module_id in powered if module_id in first],
        "first": first,
        "last": last,
        "winner": winner_at,
        "end": end,
    }


def _boundaries(marks: dict[str, Any], wanted: Sequence[tuple[str, str]]) -> list[float]:
    """Resolve `(station, "first"|"last")` pairs into times, dropping misses."""
    out: list[float] = []
    for station, which in wanted:
        table = marks[which]
        if station in table:
            out.append(float(table[station]))
    return out


def _assemble(
    name: str,
    marks: dict[str, Any],
    spec: Sequence[tuple[str, str, dict[str, float], str, tuple[str, str] | None]],
    note: str,
    fps: int = 60,
) -> Plan:
    """Build a plan from `(shot name, rig, tweaks, note, cut marker)` rows.

    The marker on a row is where that shot *ends*; the last row runs to the end
    of the film. A boundary that would leave a shot under `MIN_SHOT` is dropped
    and the two shots merge, so a seed whose mechanisms fire close together gets
    a shorter film rather than a stuttering one.
    """
    stops: list[float | None] = []
    for _n, _r, _t, _note, marker in spec:
        stops.append(None if marker is None else _one(marks, marker))

    shots: list[Shot] = []
    previous = marks["release"]
    for (shot_name, rig, tweaks, why, _marker), stop in zip(spec, stops):
        end = marks["end"] if stop is None else stop
        if end - previous < MIN_SHOT and shots:
            # Too short to be a shot: give the time to the one already running.
            shots[-1] = Shot(
                name=shots[-1].name, rig=shots[-1].rig, start=shots[-1].start,
                end=end, tweaks=shots[-1].tweaks, note=shots[-1].note,
                cut_on=shots[-1].cut_on,
            )
            previous = end
            continue
        shots.append(Shot(
            name=shot_name, rig=rig, start=previous, end=end,
            tweaks=dict(tweaks), note=why,
            cut_on="release" if not shots else shots[-1].name,
        ))
        previous = end
    if shots and shots[-1].end < marks["end"]:
        shots[-1] = Shot(
            name=shots[-1].name, rig=shots[-1].rig, start=shots[-1].start,
            end=marks["end"], tweaks=shots[-1].tweaks, note=shots[-1].note,
            cut_on=shots[-1].cut_on,
        )
    # Name the physical moment each cut lands on, for `race2.flow`.
    labelled: list[Shot] = []
    for index, shot in enumerate(shots):
        reason = "release" if index == 0 else _reason(spec[index - 1][4])
        labelled.append(Shot(
            name=shot.name, rig=shot.rig, start=shot.start, end=shot.end,
            tweaks=shot.tweaks, note=shot.note, cut_on=reason,
        ))
    return Plan(name=name, shots=labelled, fps=fps, note=note)


def _one(marks: dict[str, Any], marker: tuple[str, str]) -> float:
    station, which = marker
    table = marks[which]
    if station in table:
        return float(table[station])
    # A station this seed never reached: fall back to the winner's crossing so
    # the schedule degrades to fewer shots rather than to a broken one.
    return float(marks["winner"])


def _reason(marker: tuple[str, str] | None) -> str:
    if marker is None:
        return "end of film"
    station, which = marker
    return f"{station} {'first' if which == 'first' else 'last'} contact"


# --- A: continuous chase -----------------------------------------------------


def plan_a(marks: dict[str, Any], fps: int = 60) -> Plan:
    """Four shots, one rig family, maximum continuity."""
    return _assemble(
        "A",
        marks,
        [
            ("release", "hook_release", {},
             "eight racers large and the floor going, the lens already travelling",
             ("drum", "first")),
            ("upper", "chase_rear_3q", {},
             "one take from the drum to the pair: two mechanisms and two hairpins "
             "revealed by the camera turning rather than by cutting to them",
             ("pair", "first")),
            ("middle", "chase_rear_3q", {"trail": 9.5, "lead": 13.0},
             "the pair's consequence and the fourth hairpin, still travelling",
             ("last", "first")),
            ("run_in", "finish_chase", {},
             "the last wheel, the comeback and the line, uncut",
             None),
        ],
        note="the most conservative answer: change the editing and nothing else",
        fps=fps,
    )


# --- B: racing broadcast hybrid ---------------------------------------------


def plan_b(marks: dict[str, Any], fps: int = 60) -> Plan:
    """Five shots, four rigs, cuts only on contacts."""
    return _assemble(
        "B",
        marks,
        [
            ("release", "hook_release", {},
             "eight racers large and the floor going, the lens already travelling",
             ("drum", "first")),
            ("drum_run", "chase_rear_3q", {},
             "rear three-quarter from the drum through the second hairpin into "
             "the sweep, which enters frame as the camera comes round",
             ("sweep", "first")),
            ("sweep_out", "chase_side", {},
             "side pursuit across the sweep's consequence and down pan3 - the "
             "field crosses frame, which is where speed reads",
             ("pair", "first")),
            ("pair_bend", "bend_orbit", {},
             "a long trail through the pair and the fourth hairpin, so the turn "
             "happens in front of the lens instead of under it",
             ("last", "first")),
            ("run_in", "finish_chase", {},
             "the last wheel, the comeback and the line, uncut",
             None),
        ],
        note="variety bought from rig changes at motivated cuts, not from cutting more",
        fps=fps,
    )


# --- C: low pursuit ----------------------------------------------------------

# What "low" means, applied to every shot in C: a metre and a half under the
# rail's own height and the reach at its floor. The rail's clearance is solved
# at the nominal reach, so C's lift is the only thing that can put a lens into
# the course - `race2.flow` measures the flown clearance and says so.
LOW = {"lift": -1.6}


def plan_c(marks: dict[str, Any], fps: int = 60) -> Plan:
    """Six shots, lower and closer, more foreground and bigger racers."""
    return _assemble(
        "C",
        marks,
        [
            ("release", "hook_release", {"lift": -1.8, "reach": 7.0},
             "the grid, as close as the geometry allows",
             ("drum", "first")),
            ("drum_low", "chase_pack", dict(LOW, trail=5.5),
             "close behind into the drum, low enough that the wheels stand over "
             "the racers",
             ("drum", "last")),
            ("pan2_side", "chase_side", dict(LOW, reach=11.0),
             "the second hairpin from the side, with the channel edge in the "
             "near foreground",
             ("sweep", "first")),
            ("sweep_low", "compression_follow", dict(LOW),
             "tight and low on the sweep's consequence, held into the pair",
             ("pair", "first")),
            ("pair_low", "chase_pack", dict(LOW, trail=6.0),
             "the pair and the fourth hairpin, close behind",
             ("last", "first")),
            ("run_in", "finish_chase", {"lift": -1.6},
             "the last wheel, the comeback and the line, uncut and lower still",
             None),
        ],
        note="stronger racing energy: lower, closer, larger racers, six shots",
        fps=fps,
    )


CANDIDATES = {"A": plan_a, "B": plan_b, "C": plan_c}


# --- V31: the readability variants -------------------------------------------

"""Three framing variants over camera A's own schedule.

They are not new cameras. Each is camera A's four shots, on camera A's four
markers, with the same rig on each - `hook_release`, `chase_rear_3q` twice,
`finish_chase` - and a dict of parameter changes. `race2.rig` builds all four
from the same code path, so what separates them is a table of numbers that can
be read in one screen.

## What the measurements said before any of this was authored

On the hero replay, camera A delivers **3.9 layout units of visible course
ahead of the pack** - a third of a second at racing speed - and **15% of the
coming turn on screen** where the course is turning. Both were measured by
`race2.readability` against the delivered track, and the cause is not what the
brief assumed:

- The forward centreline is **never occluded**. Over the whole film the course
  never stands between the lens and the path ahead. A track-contrast change
  could not have helped, and none is made.
- It leaves **sideways**, at screen x of 1.07 to 1.12, within four to eight
  units. The delivery frame is portrait: at camera A's 34-degree lens it is
  **19.5 degrees wide** and 34 tall.
- And the switchyard is a **hairpin every 32 units**, turning 180 degrees over
  a 16-unit pan at 7 to 12 degrees per unit, with no straight longer than 16
  units anywhere on the course. Measured at 7.0 s: the coming hairpin projects
  at screen x **+1.7 to +3.0** - one and a half to three half-frames outside
  the picture - while the frame spends its width on the leg already run.

So the lever is the **horizontal field**, and the three variants differ mostly
in how much of it they buy and what they spend it on. Every other change that
was tried made the picture worse and the numbers say so:

    a longer trail          align 0.23 -> 0.45, but group visibility 79% -> 35%
    a shorter nominal reach depression to the 45-degree cap: the plan view
    a lower reach floor     forward path 6.1 -> 4.8 u and clearance 5.5 -> 3.2
    a vertical pack bias    falsified in **both** directions - see below
    a relaxed look-ahead    +0.10 u of course for +0.10 of reacquisition and
    hold                    six points of "all of the group on screen"

## The vertical bias, falsified both ways

The brief's Part F asks for the pack to sit below centre so that more upcoming
track is visible above it. That is the right principle and the wrong sign here,
and then the right sign does not pay either.

The switchyard descends at 0.65 units per unit of plan. From a lens above and
behind, **the course ahead is below the pack in frame, not above it** - the
track-visibility overlay in `docs/validation/race2/v31_readability` shows the
forward centreline running down and out of the bottom of the picture. Biasing
the group downward pushes the coming path off that edge: at the drum it took
the visible forward course from 7 units to 4.

Biasing it *upward* does what the geometry says it should - the visible course
ahead goes from 4.88 to 4.98 units and the total from 6.05 to 6.47 - and costs
more than it is worth, because the bottom of the frame is also where the
racers off the back of the group are. At a bias of +0.12 the longest any racer
spends off screen goes from **7.97 s to 13.35 s**: on a descending course the
coming path and the trailing racers are competing for the same edge of the
picture, and the racers win. Every variant here therefore ships at zero.
"""

# The depression band every readability variant holds. The rail's own answer is
# a ratio against the *nominal* reach, so any rig that changes its reach moves
# its depression without saying so; naming the band is what lets these shots
# widen the lens and keep the racing three-quarter view the brief locks.
V31_DEPRESSION = (31.0, 38.0)

# The opening, shared by all three variants so the comparison is about the
# chase and not about the hook.
#
# **It is a cut-continuity fix and the instrument named it.** Moving to the
# race-interest group costs reacquisition at exactly one join - `release` into
# `upper`, where the field is still one bunch and the interest group is at its
# widest six - and the measured cause is a lens-angle step of 11 degrees, which
# is the look-ahead blend changing across the cut. Matching the opening's
# look-ahead to the chase's and tightening its target to 0.73 of frame width
# takes the worst pack jump from **0.459 back to 0.284**, against camera A's
# 0.285, for seven pixels of racer in the opening take. The eight racers are
# still 86 pixels on the delivery frame and 21 on the phone.
V31_HOOK = {"look_ahead": 0.42, "lead": 10.0, "target_width": 0.73}


def _v31(name: str, marks: dict[str, Any], hook: dict, chase: dict, run_in: dict,
         note: str, fps: int = 60) -> Plan:
    """Camera A's schedule, with one parameter dict per rig family."""
    return _assemble(
        name,
        marks,
        [
            ("release", "hook_release", dict(hook),
             "eight racers large and the floor going, the lens already travelling",
             ("drum", "first")),
            ("upper", "chase_rear_3q", dict(chase),
             "one take from the drum to the pair: two mechanisms and two hairpins "
             "revealed by the camera turning rather than by cutting to them",
             ("pair", "first")),
            ("middle", "chase_rear_3q", dict(chase, trail=9.5, lead=13.0),
             "the pair's consequence and the fourth hairpin, still travelling",
             ("last", "first")),
            ("run_in", "finish_chase", dict(run_in),
             "the last wheel, the comeback and the line, uncut",
             None),
        ],
        note=note,
        fps=fps,
    )


def plan_ra(marks: dict[str, Any], fps: int = 60) -> Plan:
    """A - pack priority. The battle framed wider; the path left to itself.

    The race-interest group and the `contain` stage, four degrees of lens, and
    nothing aimed at the course at all: the look-ahead is camera A's own 0.30
    on camera A's own 0.70 hold. Its job is to separate the brief's Part A from
    its Part B, so that whatever B and C gain on the course is charged against
    this rather than against camera A.
    """
    chase = {
        "fov": 38.0, "depression_span": V31_DEPRESSION,
        "contain": 0.88, "target_width": 0.42,
    }
    return _v31(
        "RA", marks,
        hook=dict(V31_HOOK),
        chase=chase,
        run_in={},
        note="pack priority: the race-interest group, held in frame, and little else",
        fps=fps,
    )


def plan_rb(marks: dict[str, Any], fps: int = 60) -> Plan:
    """B - pack and path. The interest group, plus a lens that can see the bend.

    Everything A does, at 42 degrees - 24 wide against camera A's 19.5 - with
    the look-ahead blend raised to 0.42 and its **distance scaled by the
    course's own curvature**, so a hairpin reaches further ahead than a
    straight. The hold stays at camera A's 0.70: see the note on C for what
    relaxing it costs and buys.
    """
    chase = {
        "fov": 42.0, "depression_span": V31_DEPRESSION,
        "contain": 0.88, "target_width": 0.42,
        "look_ahead": 0.42, "lead": 12.0, "lead_curve": 0.9, "lead_max": 22.0,
    }
    return _v31(
        "RB", marks,
        hook=dict(V31_HOOK),
        chase=chase,
        run_in={},
        note="pack and path: the interest group plus the horizontal field to see the bend",
        fps=fps,
    )


def plan_rc(marks: dict[str, Any], fps: int = 60) -> Plan:
    """C - path-aware chase. As much future course as the racers will allow.

    B's shape with every path term pushed past where the measurements stop
    paying: 48 degrees, a look-ahead that may carry a racer to 0.86 of the
    half-frame, and the two bend terms - a little more reach and a little more
    height where the course turns, and nowhere else.

    It is the variant that finds the edge, and it does: the picture gains
    another third of a unit of visible course and loses nine pixels of racer,
    seven points of "every member of the group on screen", and a third of the
    lens clearance the rail proved. Reported rather than tuned away, because a
    candidate that shows where the trade turns over is worth more than a third
    good one.
    """
    chase = {
        "fov": 48.0, "depression_span": V31_DEPRESSION,
        "contain": 0.90, "target_width": 0.44,
        "look_ahead": 0.55, "look_hold": 0.86,
        "lead": 13.0, "lead_curve": 1.2, "lead_max": 24.0,
        "curve_reach": 0.05, "curve_lift": 0.09,
    }
    return _v31(
        "RC", marks,
        hook=dict(V31_HOOK),
        chase=chase,
        run_in={},
        note="path-aware chase: the most future course the racers will pay for",
        fps=fps,
    )


READABILITY = {"RA": plan_ra, "RB": plan_rb, "RC": plan_rc}
