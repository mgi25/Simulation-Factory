"""The camera schedule, authored against the race's own markers.

The brief's Part I asks for a restrained event-aware system and specifically not
an autonomous cinematographer. This is the line that draws: **which shot covers
which part of the course is authored, and when each shot starts is measured.**

A phase says what it is for - "four fast wheels, the biggest single reordering"
- and that determines the mode. The window comes from the race: the first racer
into the phase's first stage opens it, and the first racer into the next phase
closes it. So the same schedule fits a fast seed and a slow one without anything
being decided by a heuristic at run time, and two runs on one replay produce the
same track to the byte.

## Anticipation, interaction, consequence

Where a phase carries a mechanism, its window is cut into three rather than
one, which is the brief's Part G and Part H made into code:

    anticipation   from the phase opening to just before the leader's contact.
                   Camera past the mechanism, looking back up the course.
    interaction    the contact itself, plus CONSEQUENCE seconds after it.
                   Camera close and low.
    carry          whatever is left, as a tracking shot into the next phase.

If the leader never touches the mechanism - it can happen, a wheel is a
disruptor and not a wall - the window stays one tracking shot and the schedule
says so rather than inventing a contact.

## What is not here

No cut for variety. Every shot in the list has a reason in its `note`, and
`tools/race2_camera.py --map` prints them beside the events they cover so a
shot that is covering nothing is visible as a row with an empty right-hand side.
"""

from __future__ import annotations

from typing import Sequence

from race2.camera import CONSEQUENCE, Plan, Shot
from race2.course import Course
from race2.events import Timeline
from race2.race import RaceOutcome

__all__ = ["plan_for", "phase_windows", "station_hits", "MODE_FOR_ROLE"]

# Which mode a phase gets when it is not carrying a mechanism, by the verb in
# its first stage's role.
MODE_FOR_ROLE = {
    "release": "hook_close",
    "compress": "action",
    "recompress": "action",
    "last compression": "action",
    "queue": "pack_track",
    "carry": "pack_track",
    "disrupt": "action",
    "gate": "action",
    "separate": "pack_track",
    "route decision": "route_choice",
    "sprint": "final_sprint",
}

# Per mode: fov, elevation, bearing, look-ahead, target width, group size.
#
# The bearings are 30 to 52 degrees off directly behind the pack, which is the
# brief's low-to-moderate three-quarter and never the overhead map view. The
# target widths sit in the 25-45% band except the hook, which is meant to be
# larger, and the payoff, which frames one marble rather than a group.
#
# The elevations are *floors*: `race2.camera._solve_frame` raises a shot until
# the leading group is visible past the rest of the course, so what is authored
# here is the lowest a shot may sit and not where it will end up. On the
# switchyard they settle between 18 and 38 degrees, which is the brief's low to
# moderate three-quarter and not the map view it rules out.
PRESETS = {
    "hook_close": dict(fov=32.0, elevation=16.0, bearing=34.0, look_ahead=0.18,
                       target_width=0.58, group=8),
    "pack_track": dict(fov=36.0, elevation=22.0, bearing=58.0, look_ahead=0.32,
                       target_width=0.36, group=4),
    "obstacle_anticipation": dict(fov=34.0, elevation=20.0, bearing=40.0, look_ahead=0.0,
                                  target_width=0.50, group=3),
    # **66 degrees, not 48, and the reason is the wheels.** A blade set is
    # 0.8 layout units tall against a 0.57 marble, so a shot looking *along* a
    # corridor has every racer behind a wheel or behind the near rail. Looking
    # across the channel instead puts the racers against the far wall with
    # nothing in front of them, and the wheel reads as a thing beside them
    # rather than a thing in the way.
    "action": dict(fov=38.0, elevation=21.0, bearing=66.0, look_ahead=0.20,
                   target_width=0.42, group=4),
    "route_choice": dict(fov=36.0, elevation=26.0, bearing=34.0, look_ahead=0.42,
                         target_width=0.40, group=5),
    # Two, not three: the final sprint's subject is the contest for the line,
    # and framing a third racer that is four units back pushes the two that
    # matter apart. `race2.framing.report` records how many were in frame.
    "final_sprint": dict(fov=34.0, elevation=18.0, bearing=64.0, look_ahead=0.16,
                         target_width=0.38, group=3),
    "winner_payoff": dict(fov=32.0, elevation=18.0, bearing=40.0, look_ahead=0.0,
                          target_width=0.30, group=1),
}

# The shortest a shot may be. Under about 0.8 s a cut reads as a glitch rather
# than as a shot, and a schedule that emitted one would be cutting for variety.
MIN_SHOT = 0.80
# The longest the opening hook may run before the race has to start happening.
HOOK_MAX = 1.60
# How much of the end is given to the final sprint, when there is that much.
SPRINT_MIN = 1.70


def phase_windows(course: Course, outcome: RaceOutcome) -> list[tuple[str, float, float]]:
    """When each phase was the front of the race, from the stage times.

    Opened by the *first* racer into the phase's first stage, because the
    camera is with the leaders; closed by the first racer into the next phase,
    for the same reason. A phase nobody reached is dropped rather than given a
    zero-length window.
    """
    entry: dict[str, float] = {}
    for stage in course.stages:
        times = [
            racer.stage_times[run]
            for racer in outcome.racers
            for run in stage.runs
            if run in racer.stage_times
        ]
        if times:
            entry[stage.name] = min(times)

    opens: list[tuple[str, float]] = []
    for phase in course.phases:
        candidates = [entry[name] for name in phase.stages if name in entry]
        if candidates:
            opens.append((phase.name, min(candidates)))
    opens.sort(key=lambda pair: pair[1])

    finishes = [r.finish_time for r in outcome.racers if r.finish_time is not None]
    end = max(finishes) if finishes else outcome.seconds
    out: list[tuple[str, float, float]] = []
    for index, (name, start) in enumerate(opens):
        stop = opens[index + 1][1] if index + 1 < len(opens) else end
        out.append((name, start, stop))
    return out


def _hits_in(timeline: Timeline, start: float, stop: float, subject: str = "") -> list[float]:
    return [
        event.time
        for event in timeline.events
        if event.kind == "mechanism_hit" and start <= event.time < stop
        and (not subject or subject in event.detail)
    ]


def _station_in(course: Course, phase_name: str) -> str:
    """The station this phase is about, if it has one.

    Matched by the stage's runs rather than by name: a wheel knows which run it
    stands on, and a phase knows which stages it covers, so the join is through
    the geometry and not through a naming convention that would silently stop
    matching the day a module was renamed.
    """
    phase = next((p for p in course.phases if p.name == phase_name), None)
    if phase is None:
        return ""
    runs = {
        run
        for stage in course.stages
        if stage.name in phase.stages
        for run in stage.runs
    }
    for module_id in course.stations:
        module = course.machine.modules.get(module_id)
        on = getattr(module, "run", None)
        if on is not None and getattr(on, "id", "") in runs:
            return module_id
        left = getattr(module, "left", None)
        if left is not None and getattr(left, "id", "") in runs:
            return module_id
    return ""


def station_hits(course: Course, timeline: Timeline) -> list[tuple[str, float]]:
    """Each station, and when the leading group first reached it.

    In course order rather than in hit order, and de-duplicated: the drum is
    four wheels on one shaft line and the leaders meet it four times, which is
    one *shot* and four events. Taking the first hit per module is what turns
    the event stream into a shot list.

    **Only powered stations.** The stud field is a station for event purposes -
    the leaders crossing it really is a moment the order can change - but it is
    not a *threat*, and anchoring a shot to it cost the drum its anticipation
    beat: the studs are hit at 0.9 s and the drum at 2.2, so the studs' own
    impact shot ate the window the drum's reveal needed. A threat is something
    that moves, and "has an actuator" is that test asked of the geometry rather
    than of a name.
    """
    order = {
        module_id: index
        for index, module_id in enumerate(course.stations)
        if (module := course.machine.modules.get(module_id)) is not None
        and module.local_actuators()
    }
    first: dict[str, float] = {}
    for event in timeline.events:
        if event.kind != "mechanism_hit":
            continue
        module = event.detail.split(" into ")[-1].split(" ")[0]
        if module in order:
            first.setdefault(module, event.time)
    return sorted(first.items(), key=lambda pair: order.get(pair[0], 99))


def _phase_at(course: Course, windows, when: float) -> str:
    for name, start, stop in windows:
        if start <= when < stop:
            return name
    return windows[-1][0] if windows else ""


def _role_of(course: Course, phase_name: str) -> str:
    phase = next((p for p in course.phases if p.name == phase_name), None)
    if phase is None:
        return "carry"
    return next((s.role for s in course.stages if s.name == phase.stages[0]), "carry")


def plan_for(
    course: Course,
    outcome: RaceOutcome,
    timeline: Timeline,
    fps: int = 60,
    payoff: float = 1.8,
) -> Plan:
    """The whole schedule for one race, cut against its own mechanisms.

    **Station-driven rather than phase-driven, and the first build was the
    other way round.** Anchoring a shot to a phase gave seven cuts over
    nineteen seconds, five of them the same mode, and no anticipation shot at
    all - because a phase opens when the field enters its first *stage*, which
    on this course is a pan, and by the time the wheel in the corridor below is
    hit there is not enough of the window left to cut three shots out of.

    A station is the right anchor because a station is the thing a viewer is
    being asked a question about. So the schedule is:

        hook          the field at rest and the floor going
        for each station, in course order:
            anticipate    the mechanism revealed before the field reaches it
            impact        the contact, held CONSEQUENCE seconds past it
            carry         whatever is left before the next one, if it is
                          long enough to be a shot
        sprint        the last fall, with nothing on it
        payoff        the winner across the line

    Every window is measured from this seed's own times, so the same authored
    schedule fits a fast race and a slow one.
    """
    plan = Plan(fps=fps)
    windows = phase_windows(course, outcome)
    if not windows:
        return plan
    finishes = sorted(r.finish_time for r in outcome.racers if r.finish_time is not None)
    winner_at = finishes[0] if finishes else outcome.seconds
    hits = station_hits(course, timeline)

    # The hook. Long enough to read eight racers and the floor leaving, short
    # enough that the first mechanism is not waiting: it ends a second before
    # the first contact, or after HOOK_MAX, whichever is sooner.
    opening = timeline.start
    first_contact = hits[0][1] if hits else winner_at
    hook_end = min(opening + HOOK_MAX, max(opening + MIN_SHOT, first_contact - 1.05))
    plan.shots.append(
        _shot("hook", "hook_close", opening, hook_end,
              note="eight racers at rest, then the floor goes - the premise, "
                   "legible inside half a second")
    )

    for module_id, contact in hits:
        previous = plan.shots[-1].end
        if contact - previous < MIN_SHOT + 0.25:
            # No room for an anticipation beat before this one. Extend what is
            # already running rather than emit a quarter-second flash: a cut
            # that short reads as a glitch, and the brief forbids cutting for
            # variety even when the variety would be free.
            plan.shots[-1] = _replace(plan.shots[-1], end=max(previous, contact - 0.08))
            previous = plan.shots[-1].end
        else:
            plan.shots.append(
                _shot(f"{module_id}_anticipate", "obstacle_anticipation",
                      previous, contact - 0.08, subject=module_id,
                      note=f"the {module_id} in the foreground, the field arriving into it")
            )
            previous = plan.shots[-1].end
        plan.shots.append(
            _shot(f"{module_id}_impact", "action", previous,
                  min(winner_at, contact + CONSEQUENCE + 0.30), subject=module_id,
                  note="the contact, held long enough to read who came out in front")
        )

    # What is left between the last mechanism and the line.
    last = plan.shots[-1].end
    sprint_from = max(last, min(winner_at - SPRINT_MIN, winner_at))
    if sprint_from - last >= MIN_SHOT:
        phase = _phase_at(course, windows, 0.5 * (last + sprint_from))
        plan.shots.append(
            _shot("carry", MODE_FOR_ROLE.get(_role_of(course, phase), "pack_track"),
                  last, sprint_from,
                  note="the consequence of the last wheel, tracking into the sprint")
        )
        last = sprint_from
    if winner_at - last >= MIN_SHOT:
        plan.shots.append(
            _shot("sprint", "final_sprint", last, winner_at,
                  note="low and alongside, so the closing gap is the whole picture")
        )
    else:
        plan.shots[-1] = _replace(plan.shots[-1], end=winner_at)

    # The payoff runs to whichever is later: a beat past the winner, or a beat
    # past the *last* finisher. A film that cuts at the winner has eight racers
    # on screen and shows seven of them not arriving, which is the promise the
    # PICK A COLOR opening made being quietly dropped.
    tail = finishes[-1] + 0.40 if finishes else winner_at + payoff
    plan.shots.append(
        _shot("payoff", "winner_payoff", plan.shots[-1].end,
              max(plan.shots[-1].end + payoff, tail),
              note="the winner across the line, held until the whole field is home")
    )
    return plan


def _shot(name: str, mode: str, start: float, end: float, subject: str = "",
          note: str = "") -> Shot:
    preset = PRESETS[mode]
    return Shot(name=name, mode=mode, start=start, end=max(end, start + MIN_SHOT * 0.5),
                subject=subject, note=note, **preset)


def _replace(shot: Shot, **changes) -> Shot:
    from dataclasses import replace

    return replace(shot, **changes)
