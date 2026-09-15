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
