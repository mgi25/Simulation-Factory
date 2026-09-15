"""Does the film flow, and can the eye keep hold of one colour across a cut?

`race2.framing` measures a shot. This measures **the joins**, because the joins
are where V28's film loses the viewer: every one of its eleven cuts is a correct
shot of a real event, and the complaint is not about any of them individually.

Four families, and none of them is claimed to be quality:

## Reacquisition

At each cut, where the active pack was on screen in the last frame of the
outgoing shot, and where it is in the first frame of the incoming one. The
distance between those two points, in **normalised screen space** where 1.0 is
half the frame width, is how far the eye has to travel to find the race again.
A cut that leaves the pack in the same corner is one the viewer does not have
to recover from.

Measured beside it: the **scale jump**, the ratio of the pack's apparent size
either side, and the **size discontinuity**, the change in how many racers are
in the active pack. A cut that halves the racers' size is a cut the viewer
re-reads even if the pack has not moved on screen.

## Screen direction

The pack's screen-space velocity, sampled either side of a cut. If its
horizontal component reverses sign, the racers were going right and are now
going left, and the viewer has been told the race turned round when it did not.
This is the racing form of the 180-degree rule, and on a course that folds back
on itself five times it is the failure mode to watch.

Note what is *not* counted: a reversal **inside** a shot. The switchyard turns
through 180 degrees five times and the racers really do change direction; when
that happens continuously in front of a moving lens the viewer watches the
course turn and understands it. Only a reversal across a hard cut is a
reversal, and that distinction is the whole of this branch's answer to the
switchback problem.

## Camera kinematics

Speed, acceleration, angular speed and angular acceleration of the lens, in
layout units and degrees per second. Diagnostics and not blockers, as the brief
says: a fast camera on a fast course is not a fault, and what these catch is
the *discontinuity* - a camera that moves 40 units a second for one frame is a
solver artefact, not a crane.

## Visibility

Whether the racers are actually on screen and not behind the course, per frame:
frustum membership **and** a sightline test against the spine's blockers.
`race2.framing`'s own docstring records that a frustum count is not visibility,
and that finding cost V28 a rendered shot with nothing moving in it, so the
count here is both.

## The identical-frame detector

`identical_frames` hashes rendered PNGs and reports consecutive pairs that are
byte-identical. V28 found that an identical pair is a cheap and complete
detector for "nothing in this shot is moving", and that it caught a defect
eleven still frames and a framing report had all passed. It is kept, unchanged
in spirit, and run over every candidate clip.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "measure",
    "identical_frames",
    "summary",
    "DELIVERY",
    "PHONE",
    "MARBLE_RADIUS",
]

DELIVERY = (1080, 1920)
PHONE = (270, 480)
MARBLE_RADIUS = 0.285

# How far apart, in normalised screen units where 1.0 is half the frame width,
# the pack may land across a cut before the eye has to hunt for it. A third of
# a half-width is about the width of the pack itself at the sizes these shots
# use, so under it the racers overlap their own outgoing position.
REACQUIRE_GOOD = 0.33
# And the scale ratio band over which a cut reads as the same race.
SCALE_BAND = (0.60, 1.67)


def _basis(position, aim):
    forward = [aim[axis] - position[axis] for axis in range(3)]
    span = math.sqrt(sum(v * v for v in forward)) or 1.0
    forward = [v / span for v in forward]
    up = [0.0, 1.0, 0.0]
    right = [
        forward[1] * up[2] - forward[2] * up[1],
        forward[2] * up[0] - forward[0] * up[2],
        forward[0] * up[1] - forward[1] * up[0],
    ]
    span = math.sqrt(sum(v * v for v in right)) or 1.0
    right = [v / span for v in right]
    true_up = [
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    ]
    return forward, right, true_up


def _project(point, position, forward, right, up, fov, size=DELIVERY):
    """Screen coordinates in [-1, 1] and depth, or `(None, 0)` if behind."""
    offset = [point[axis] - position[axis] for axis in range(3)]
    depth = sum(offset[axis] * forward[axis] for axis in range(3))
    if depth <= 1e-4:
        return None, 0.0
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * (size[0] / size[1])
    x = sum(offset[axis] * right[axis] for axis in range(3)) / (depth * half_right)
    y = sum(offset[axis] * up[axis] for axis in range(3)) / (depth * half_up)
    return (x, y), depth


def _pixels(depth: float, fov: float, size=DELIVERY) -> float:
    half_up = math.tan(math.radians(fov) * 0.5)
    return 2.0 * MARBLE_RADIUS / max(depth * half_up, 1e-6) * 0.5 * size[1]


@dataclass
class ShotFlow:
    name: str
    rig: str
    start: float
    end: float
    cut_on: str = ""
    racer_pixels: float = 0.0
    racer_pixels_min: float = 0.0
    phone_pixels: float = 0.0
    group_width: float = 0.0
    pack_visible: float = 0.0        # fraction of frames with the whole pack seen
    pack_on_screen: float = 0.0      # mean fraction of the pack on screen
    min_on_screen: int = 0
    lens_clearance: float = 0.0
    max_speed: float = 0.0
    max_accel: float = 0.0
    max_turn: float = 0.0
    max_turn_accel: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "rig": self.rig,
            "from": round(self.start, 3), "to": round(self.end, 3),
            "duration": round(self.end - self.start, 3),
            "cut_on": self.cut_on,
            "racer_pixels": round(self.racer_pixels, 1),
            "racer_pixels_min": round(self.racer_pixels_min, 1),
            "phone_pixels": round(self.phone_pixels, 1),
            "group_width": round(self.group_width, 4),
            "pack_visible": round(self.pack_visible, 3),
            "pack_on_screen": round(self.pack_on_screen, 3),
            "min_on_screen": self.min_on_screen,
            "lens_clearance": round(self.lens_clearance, 3),
            "max_speed": round(self.max_speed, 2),
            "max_accel": round(self.max_accel, 1),
            "max_turn": round(self.max_turn, 1),
            "max_turn_accel": round(self.max_turn_accel, 1),
            "notes": list(self.notes),
        }


@dataclass
class CutFlow:
    at: float
    outgoing: str
    incoming: str
    cut_on: str = ""
    reacquire: float = 0.0        # normalised screen distance the pack jumps
    scale_ratio: float = 1.0
    pack_before: int = 0
    pack_after: int = 0
    direction_flip: bool = False
    screen_drift: tuple[float, float] = (0.0, 0.0)
    angle_change: float = 0.0     # degrees between the two lens forwards

    def to_json(self) -> dict[str, Any]:
        return {
            "at": round(self.at, 3),
            "from": self.outgoing, "to": self.incoming,
            "cut_on": self.cut_on,
            "reacquire": round(self.reacquire, 4),
            "scale_ratio": round(self.scale_ratio, 3),
            "pack_before": self.pack_before, "pack_after": self.pack_after,
            "direction_flip": self.direction_flip,
            "screen_drift": [round(v, 3) for v in self.screen_drift],
            "angle_change": round(self.angle_change, 1),
        }


def _rows_of(track: dict[str, Any]) -> list[tuple[str, list[float]]]:
    out: list[tuple[str, list[float]]] = []
    for cut in track.get("cuts", []):
        for row in cut.get("frames", []):
            out.append((str(cut.get("name", "")), row))
    return out


def _screen_of(row, points, size=DELIVERY):
    """Mean screen position, span and apparent size of a set of world points."""
    position = (float(row[1]), float(row[2]), float(row[3]))
    aim = (float(row[4]), float(row[5]), float(row[6]))
    fov = float(row[7])
    forward, right, up = _basis(position, aim)
    seen: list[tuple[float, float]] = []
    depths: list[float] = []
    for point in points:
        projected, depth = _project(point, position, forward, right, up, fov, size)
        if projected is None:
            continue
        seen.append(projected)
        depths.append(depth)
    if not seen:
        return None
    centre = (
        sum(x for x, _ in seen) / len(seen),
        sum(y for _, y in seen) / len(seen),
    )
    width = (max(x for x, _ in seen) - min(x for x, _ in seen)) / 2.0
    depth = sum(depths) / len(depths)
    return centre, width, _pixels(depth, fov, size), forward


def measure(
    track: dict[str, Any],
    pack,
    spine,
    outcome,
    marks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything the brief asks to be measured about one candidate camera."""
    fps = float(track.get("fps", 60))
    dt = 1.0 / fps
    cuts = track.get("cuts", [])
    shots: list[ShotFlow] = []
    joins: list[CutFlow] = []

    for cut in cuts:
        rows = cut.get("frames", [])
        if not rows:
            continue
        entry = ShotFlow(
            name=str(cut.get("name", "")), rig=str(cut.get("mode", "")),
            start=float(cut.get("from", rows[0][0])),
            end=float(cut.get("to", rows[-1][0])),
            cut_on=str(cut.get("cut_on", "")),
        )
        widths: list[float] = []
        pixels: list[float] = []
        on_screen: list[float] = []
        whole = 0
        least = 99
        clearance = 1e9
        speeds: list[float] = []
        turns: list[float] = []
        previous_position = None
        previous_forward = None

        for row in rows:
            when = float(row[0])
            index = pack.frame_at(when)
            members = pack.packs[index]
            points = [pack.places[index][m] for m in members if m in pack.places[index]]
            position = (float(row[1]), float(row[2]), float(row[3]))
            aim = (float(row[4]), float(row[5]), float(row[6]))
            fov = float(row[7])
            forward, right, up = _basis(position, aim)
            clearance = min(clearance, spine.clearance(position))

            count = 0
            depths: list[float] = []
            frame_points: list[tuple[float, float]] = []
            for point in points:
                projected, depth = _project(point, position, forward, right, up, fov)
                if projected is None:
                    continue
                inside = -1.0 <= projected[0] <= 1.0 and -1.0 <= projected[1] <= 1.0
                # Frustum membership is not visibility - hence the sightline.
                if inside and not spine.blocked(position, point):
                    count += 1
                    depths.append(depth)
                    frame_points.append(projected)
            on_screen.append(count / max(len(points), 1))
            least = min(least, count)
            if points and count == len(points):
                whole += 1
            if frame_points:
                widths.append(
                    (max(x for x, _ in frame_points) - min(x for x, _ in frame_points)) / 2.0
                )
            if depths:
                pixels.append(_pixels(sum(depths) / len(depths), fov))

            if previous_position is not None:
                speeds.append(math.dist(previous_position, position) / dt)
                dot = max(-1.0, min(1.0, sum(
                    previous_forward[axis] * forward[axis] for axis in range(3)
                )))
                turns.append(math.degrees(math.acos(dot)) / dt)
            previous_position = position
            previous_forward = forward

        entry.racer_pixels = sum(pixels) / len(pixels) if pixels else 0.0
        entry.racer_pixels_min = min(pixels) if pixels else 0.0
        entry.phone_pixels = entry.racer_pixels * PHONE[1] / DELIVERY[1]
        entry.group_width = sum(widths) / len(widths) if widths else 0.0
        entry.pack_visible = whole / len(rows)
        entry.pack_on_screen = sum(on_screen) / len(on_screen)
        entry.min_on_screen = 0 if least == 99 else least
        entry.lens_clearance = 0.0 if clearance > 1e8 else clearance
        entry.max_speed = max(speeds) if speeds else 0.0
        entry.max_turn = max(turns) if turns else 0.0
        entry.max_accel = max(
            (abs(b - a) / dt for a, b in zip(speeds, speeds[1:])), default=0.0
        )
        entry.max_turn_accel = max(
            (abs(b - a) / dt for a, b in zip(turns, turns[1:])), default=0.0
        )
        if entry.racer_pixels < 20.0:
            entry.notes.append(f"racers {entry.racer_pixels:.0f} px in a 1080 frame")
        if entry.min_on_screen < 2:
            entry.notes.append(
                f"only {entry.min_on_screen} of the pack visible at the worst moment"
            )
        if entry.lens_clearance < 1.6:
            entry.notes.append(
                f"lens within {entry.lens_clearance:.2f} units of the course"
            )
        shots.append(entry)

    # --- the joins -------------------------------------------------------
    for before, after in zip(cuts, cuts[1:]):
        rows_a, rows_b = before.get("frames", []), after.get("frames", [])
        if not rows_a or not rows_b:
            continue
        last, first = rows_a[-1], rows_b[0]
        index_a = pack.frame_at(float(last[0]))
        index_b = pack.frame_at(float(first[0]))
        members_a = pack.packs[index_a]
        members_b = pack.packs[index_b]
        points_a = [pack.places[index_a][m] for m in members_a]
        points_b = [pack.places[index_b][m] for m in members_b]
        left = _screen_of(last, points_a)
        right = _screen_of(first, points_b)
        join = CutFlow(
            at=float(first[0]),
            outgoing=str(before.get("name", "")),
            incoming=str(after.get("name", "")),
            cut_on=str(after.get("cut_on", "")),
            pack_before=len(members_a), pack_after=len(members_b),
        )
        if left and right:
            join.reacquire = math.dist(left[0], right[0])
            join.scale_ratio = right[2] / max(left[2], 1e-6)
            dot = max(-1.0, min(1.0, sum(
                left[3][axis] * right[3][axis] for axis in range(3)
            )))
            join.angle_change = math.degrees(math.acos(dot))
            # Screen direction: the pack's horizontal screen velocity a few
            # frames either side of the join, which is what the eye reads.
            before_x = _drift(rows_a, pack, -1)
            after_x = _drift(rows_b, pack, +1)
            join.direction_flip = (
                before_x is not None and after_x is not None
                and abs(before_x) > DIRECTION_DEADBAND
                and abs(after_x) > DIRECTION_DEADBAND
                and before_x * after_x < 0.0
            )
            join.screen_drift = (before_x or 0.0, after_x or 0.0)
        joins.append(join)

    durations = [shot.end - shot.start for shot in shots]
    total = sum(durations) or 1.0
    longest = sorted(durations, reverse=True)
    sprint = shots[-1] if shots else None

    report: dict[str, Any] = {
        "camera": track.get("camera", ""),
        "duration": round(total, 3),
        "shots": len(shots),
        "hard_cuts": max(len(shots) - 1, 0),
        "mean_shot": round(total / max(len(shots), 1), 3),
        "shortest_shot": round(min(durations), 3) if durations else 0.0,
        "longest_shot": round(max(durations), 3) if durations else 0.0,
        "two_longest_share": round(sum(longest[:2]) / total, 4),
        "continuous_share": round(
            sum(d for d in durations if d >= 3.0) / total, 4
        ),
        "direction_flips": sum(1 for j in joins if j.direction_flip),
        "worst_reacquire": round(max((j.reacquire for j in joins), default=0.0), 4),
        "mean_reacquire": round(
            sum(j.reacquire for j in joins) / max(len(joins), 1), 4
        ),
        "worst_scale_jump": round(
            max((max(j.scale_ratio, 1.0 / max(j.scale_ratio, 1e-6)) for j in joins),
                default=1.0), 3
        ),
        "worst_angle_change": round(
            max((j.angle_change for j in joins), default=0.0), 1
        ),
        "racer_pixels": [
            round(min(s.racer_pixels for s in shots), 1) if shots else 0.0,
            round(max(s.racer_pixels for s in shots), 1) if shots else 0.0,
        ],
        "phone_pixels": [
            round(min(s.phone_pixels for s in shots), 1) if shots else 0.0,
            round(max(s.phone_pixels for s in shots), 1) if shots else 0.0,
        ],
        "min_lens_clearance": round(
            min((s.lens_clearance for s in shots), default=0.0), 3
        ),
        "max_speed": round(max((s.max_speed for s in shots), default=0.0), 2),
        "max_accel": round(max((s.max_accel for s in shots), default=0.0), 1),
        "max_turn": round(max((s.max_turn for s in shots), default=0.0), 1),
        "max_turn_accel": round(max((s.max_turn_accel for s in shots), default=0.0), 1),
        "shot_rows": [shot.to_json() for shot in shots],
        "cut_rows": [join.to_json() for join in joins],
    }
    report["flow_score"] = _flow_score(report)
    if sprint is not None:
        report["final_sprint"] = _sprint_report(track, pack, spine, outcome, marks, sprint)
    return report


def _drift(rows, pack, direction: int, span: int = 8) -> float | None:
    """Which way the racers are travelling **across the frame**, per second.

    Not the pack centroid's drift, which is what this measured first and which
    is the wrong thing on a camera that works: a chase rig holds the pack in the
    middle of frame, so its centroid barely moves, and the sign of "barely" is
    noise. Measured that way the three candidates reported two to four screen
    direction reversals each, all of them at cuts where nothing reversed - and
    the reason the count had been zero before was that the pack was drifting out
    of frame, which gave the measurement something large and consistent to read.

    What the 180-degree rule is actually about is the direction the *racers* are
    going on screen, so that is what this projects: the pack's world velocity,
    into the lens's own right vector. A rear chase legitimately has almost no
    lateral component - the racers recede - so the deadband below is what stops
    a receding shot being scored as having a direction at all.
    """
    if len(rows) < 2:
        return None
    chosen = rows[-span:] if direction < 0 else rows[:span]
    total = 0.0
    counted = 0
    for row in chosen:
        index = pack.frame_at(float(row[0]))
        _arc, velocity = pack.rates(index)
        position = (float(row[1]), float(row[2]), float(row[3]))
        aim = (float(row[4]), float(row[5]), float(row[6]))
        forward, right, _up = _basis(position, aim)
        depth = max(math.dist(position, pack.anchors[index]), 1e-6)
        half = math.tan(math.radians(float(row[7])) * 0.5) * (DELIVERY[0] / DELIVERY[1])
        # Screen-x units per second: the lateral component of the racers' own
        # velocity, divided by how wide the frame is at their distance.
        lateral = sum(velocity[axis] * right[axis] for axis in range(3))
        total += lateral / (depth * half)
        counted += 1
    return None if not counted else total / counted


# How much lateral screen motion per second counts as the racers having a
# direction at all. Under it the shot is a rear chase in which they recede, and
# a rear chase has no screen direction to reverse.
DIRECTION_DEADBAND = 0.25


def _sprint_report(track, pack, spine, outcome, marks, sprint: ShotFlow) -> dict[str, Any]:
    """The final take, measured as its own thing, because it is the hard rule."""
    winner = outcome.winner()
    winner_id = winner.marble_id if winner is not None else None
    crossing = winner.finish_time if winner is not None and winner.finish_time else None
    rows = next(
        (c["frames"] for c in track["cuts"] if c.get("name") == sprint.name), []
    )
    top3_seen = 0
    winner_seen = 0
    winner_px: list[float] = []
    before_line = 0
    counted = 0
    for row in rows:
        when = float(row[0])
        index = pack.frame_at(when)
        position = (float(row[1]), float(row[2]), float(row[3]))
        aim = (float(row[4]), float(row[5]), float(row[6]))
        fov = float(row[7])
        forward, right, up = _basis(position, aim)
        order = pack.order_at(when)
        places = pack.places[index]
        top3 = [m for m in order[:3] if m in places]
        visible = 0
        for marble in top3:
            projected, _d = _project(places[marble], position, forward, right, up, fov)
            if projected and -1.0 <= projected[0] <= 1.0 and -1.0 <= projected[1] <= 1.0 \
                    and not spine.blocked(position, places[marble]):
                visible += 1
        top3_seen += visible / max(len(top3), 1)
        counted += 1
        if winner_id is not None and winner_id in places:
            projected, depth = _project(places[winner_id], position, forward, right, up, fov)
            if projected and -1.0 <= projected[0] <= 1.0 and -1.0 <= projected[1] <= 1.0 \
                    and not spine.blocked(position, places[winner_id]):
                winner_seen += 1
                winner_px.append(_pixels(depth, fov))
                if crossing is not None and when < crossing:
                    before_line += 1
    fps = float(track.get("fps", 60))
    return {
        "shot": sprint.name,
        "duration": round(sprint.end - sprint.start, 3),
        "hard_cuts": 0,
        "top3_visible": round(top3_seen / max(counted, 1), 4),
        "winner_visible": round(winner_seen / max(counted, 1), 4),
        "winner_pixels": round(sum(winner_px) / len(winner_px), 1) if winner_px else 0.0,
        "winner_pixels_min": round(min(winner_px), 1) if winner_px else 0.0,
        "visible_before_crossing": round(before_line / fps, 3),
        "crossing_at": None if crossing is None else round(crossing, 3),
    }


# The FLOW score's five terms and what each is worth out of a hundred. Weighted
# in the brief's own order of priority: continuity first, then the cut budget,
# then whether the eye can find the racers again, then screen direction, then
# scale.
FLOW_WEIGHTS = {
    "continuity": 40.0,    # share of the film inside its two longest takes
    "budget": 15.0,        # hard cuts against the 4-6 the brief asks for
    "reacquire": 20.0,     # how far the pack jumps at the worst cut
    "direction": 15.0,     # 180-degree reversals across cuts
    "scale": 10.0,         # how much the racers change size at the worst cut
}
# Where each term reaches zero.
CONTINUITY_FULL = 0.75     # two longest takes covering three quarters of the film
REACQUIRE_ZERO = 0.66      # the pack landing two thirds of a half-frame away
SCALE_ZERO = 0.67          # the racers changing size by two thirds


def anticipation(track, spine, stations: dict, hits: dict) -> dict[str, Any]:
    """When each mechanism first reaches the frame, relative to its contact.

    Negative is warning; positive means the mechanism arrived with the racers or
    after them. **This is the measure V28 wins on** - it leads every contact by
    about a second, where a trailing chase reveals the mechanism as the pack
    reaches it - and it is reported here rather than left to the prose so the
    trade is a number.

    Also returns the uncut film held after each contact, which is the measure the
    chase wins on by three to eight times. A cut landing exactly *on* a contact
    is not counted as ending the consequence: it is the motivated cut, and the
    take it opens is where the consequence is seen.
    """
    rows = [row for cut in track.get("cuts", []) for row in cut.get("frames", [])]
    ends = sorted(float(cut["to"]) for cut in track.get("cuts", []))
    duration = float(track.get("duration", ends[-1] if ends else 0.0))
    lead: dict[str, float | None] = {}
    held: dict[str, float] = {}
    for module, when in hits.items():
        point = stations.get(module)
        first = None
        if point is not None:
            for row in rows:
                if float(row[0]) > when + 1.5:
                    break
                position = (float(row[1]), float(row[2]), float(row[3]))
                aim = (float(row[4]), float(row[5]), float(row[6]))
                forward, right, up = _basis(position, aim)
                projected, _depth = _project(point, position, forward, right, up,
                                             float(row[7]))
                if (projected and -1.0 <= projected[0] <= 1.0
                        and -1.0 <= projected[1] <= 1.0
                        and not spine.blocked(position, point)):
                    first = float(row[0])
                    break
        lead[module] = None if first is None else round(first - when, 3)
        later = [e for e in ends if e > when + 0.05]
        held[module] = round((later[0] if later else duration) - when, 3)
    return {"lead_seconds": lead, "consequence_seconds": held}


def _flow_score(report: dict[str, Any]) -> float:
    """A blunt composite, on 0 to 100, and explicitly not a quality judgement.

    It exists to rank obviously disruptive edits against obviously smooth ones
    and to make a regression visible. Every term is one of the brief's own and
    every term is reported separately above, so a number that disagrees with the
    picture can be taken apart rather than argued with.

    **It is a weighted sum rather than a hundred minus penalties**, which is how
    it started and which stopped telling the three candidates apart the moment
    they all got good: with penalties only, A, B and C all pinned at 100 while
    differing by a third in continuity and by two hard cuts.
    """
    cuts = report["hard_cuts"]
    terms = {
        "continuity": min(report["two_longest_share"] / CONTINUITY_FULL, 1.0),
        "budget": 1.0 if cuts <= 4 else max(0.0, 1.0 - 0.25 * (cuts - 4)),
        "reacquire": max(0.0, 1.0 - report["worst_reacquire"] / REACQUIRE_ZERO),
        "direction": max(0.0, 1.0 - report["direction_flips"] / 2.0),
        "scale": max(
            0.0, 1.0 - (max(report["worst_scale_jump"], 1.0) - 1.0) / SCALE_ZERO
        ),
    }
    report["flow_terms"] = {k: round(v, 3) for k, v in terms.items()}
    return round(sum(FLOW_WEIGHTS[k] * v for k, v in terms.items()), 1)


def identical_frames(folder: str, pattern: str = "frame_") -> list[tuple[str, str]]:
    """Consecutive rendered frames that are byte-identical.

    V28's detector, kept: an identical pair is a cheap and complete test for
    "nothing in this shot is moving", and it found a defect that eleven still
    frames and a framing report had all passed.
    """
    if not os.path.isdir(folder):
        return []
    names = sorted(
        name for name in os.listdir(folder)
        if name.startswith(pattern) and name.endswith(".png")
    )
    pairs: list[tuple[str, str]] = []
    previous_hash = None
    previous_name = ""
    for name in names:
        with open(os.path.join(folder, name), "rb") as handle:
            digest = hashlib.sha1(handle.read()).hexdigest()
        if previous_hash is not None and digest == previous_hash:
            pairs.append((previous_name, name))
        previous_hash = digest
        previous_name = name
    return pairs


def summary(report: dict[str, Any]) -> str:
    lines = [
        f"{'shot':<14}{'rig':<20}{'secs':>6}{'px':>6}{'phone':>7}"
        f"{'width%':>8}{'pack':>7}{'clear':>7}{'m/s':>7}{'deg/s':>7}  cut on"
    ]
    lines.append("-" * 104)
    for shot in report["shot_rows"]:
        lines.append(
            f"{shot['name']:<14}{shot['rig']:<20}{shot['duration']:6.2f}"
            f"{shot['racer_pixels']:6.0f}{shot['phone_pixels']:7.1f}"
            f"{shot['group_width'] * 100:7.1f}%"
            f"{shot['pack_on_screen'] * 100:6.0f}%"
            f"{shot['lens_clearance']:7.2f}"
            f"{shot['max_speed']:7.1f}{shot['max_turn']:7.1f}  {shot['cut_on']}"
        )
    lines.append("")
    lines.append(
        f"{'cut at':>8}  {'from -> to':<28}{'reacq':>7}{'scale':>7}"
        f"{'angle':>7}{'pack':>8}  flip"
    )
    lines.append("-" * 80)
    for join in report["cut_rows"]:
        lines.append(
            f"{join['at']:8.2f}  {join['from'] + ' -> ' + join['to']:<28}"
            f"{join['reacquire']:7.3f}{join['scale_ratio']:7.2f}"
            f"{join['angle_change']:7.1f}"
            f"{join['pack_before']:4d}/{join['pack_after']:<3d}"
            f"  {'YES' if join['direction_flip'] else '-'}"
        )
    lines.append("")
    lines.append(
        f"  {report['shots']} shots, {report['hard_cuts']} hard cuts, "
        f"mean {report['mean_shot']:.2f} s "
        f"({report['shortest_shot']:.2f} to {report['longest_shot']:.2f})"
    )
    lines.append(
        f"  two longest shots cover {report['two_longest_share'] * 100:.0f}% of the film; "
        f"shots of 3 s or more cover {report['continuous_share'] * 100:.0f}%"
    )
    lines.append(
        f"  worst reacquisition {report['worst_reacquire']:.3f}, "
        f"worst scale jump {report['worst_scale_jump']:.2f}, "
        f"direction flips {report['direction_flips']}"
    )
    lines.append(
        f"  racers {report['racer_pixels'][0]:.0f}-{report['racer_pixels'][1]:.0f} px "
        f"at 1080, {report['phone_pixels'][0]:.1f}-{report['phone_pixels'][1]:.1f} px at 270"
    )
    lines.append(
        f"  lens speed to {report['max_speed']:.1f} u/s, "
        f"turn to {report['max_turn']:.0f} deg/s, "
        f"min clearance {report['min_lens_clearance']:.2f} u"
    )
    sprint = report.get("final_sprint")
    if sprint:
        lines.append(
            f"  final sprint '{sprint['shot']}': {sprint['duration']:.2f} s, "
            f"{sprint['hard_cuts']} cuts, top3 {sprint['top3_visible'] * 100:.0f}%, "
            f"winner {sprint['winner_visible'] * 100:.0f}% at "
            f"{sprint['winner_pixels']:.0f} px, "
            f"{sprint['visible_before_crossing']:.2f} s visible before the line"
        )
    lines.append(f"  flow score {report['flow_score']:.1f}")
    faults = [(s["name"], note) for s in report["shot_rows"] for note in s["notes"]]
    if faults:
        lines.append("")
        for name, note in faults:
            lines.append(f"  {name}: {note}")
    return "\n".join(lines)
