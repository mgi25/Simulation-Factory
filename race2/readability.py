"""Can the viewer see the contest, and can they see where it is going?

`race2.flow` answers "is this a smooth edit" - cuts, reacquisition, screen
direction, racer size. Every one of its numbers is about the *lens*. A camera
can score well on all of them and still deliver the frame this branch was
opened on: a clot of marbles half behind a paddle, the channel crossing frame
as a white thread, and nothing above it but the far wall.

So this module measures the two things flow does not:

    who is on screen         per racer, every frame, occlusion included
    how much course is       how far ahead the centreline is visible, and
    on screen                whether the coming turn is inside the frame

and one rule the rigs then film to:

    the race-interest group  which marbles are the contest right now

Everything here is a pure function of the camera track, the replay and the
course. No image analysis: a pixel measure cannot tell a marble hidden behind
a support from a marble that is simply small, and it cannot see the centreline
at all under the racers. Projection and a ray test can do both, and they agree
between two runs to the last bit, which the renderer does not.

## The race-interest group

`race2.rig.active_pack` is the leader plus everyone within `PACK_GAP` of arc,
floored at three and **capped at four**. On the hero seed that cap binds on
73% of frames: five to eight racers are genuinely in contention and the camera
frames four of them. The floor binds on another 19%, which is the opposite
failure - the leader has broken clear and the rule hands back three racers
strung over a gap, so the solve widens for a contest that is not on screen.

The rule here is a **chain**, not a radius:

1. Rank by the race's own sticky order.
2. Walk down the field. Two neighbours are *linked* when the arc gap between
   them is at most `LINK_GAP` - about four marble diameters, which is close
   enough that a viewer reads them as racing each other rather than as two
   marbles that happen to be on the same course.
3. That splits the field into runs. The **lead run** contains the leader. The
   **contest run** is the largest run of two or more within `CONTEST_REACH` of
   the leader.
4. The group is the lead run followed by the contest run, trimmed so it never
   spans more than `INTEREST_SPAN` of arc and never holds more than
   `INTEREST_MAX` racers.

A break in the field is therefore something the rule *reads* rather than
something it averages over. When the leader escapes, the lead run is a single
marble and the contest run is the four fighting behind - and the group is both,
which is what the brief asks for and what neither a radius nor a fixed top-N
can express. When the field is one long bunch, the chain returns the front of
it and the cap does the rest.

## Weights

A group is not a set of equals. Each member carries a weight, and the anchor
the camera flies to is the weighted centroid:

- everyone in the group starts at 1.0
- the leader is worth `LEAD_WEIGHT` when it is alone in its run, so a lone
  leader still pulls the frame and stays narratively legible rather than being
  averaged into the bunch behind
- members are damped by how far behind the front of the group they are, so a
  racer at the tail of an eleven-unit group moves the anchor less than the
  three at the head of it

The weights are what stop the brief's two failure modes being one dial: the
group can be wide enough to *contain* the contest while the anchor stays where
the contest actually is.

## Track visibility

Per frame, the centreline is sampled from `BEHIND` units behind the pack to
`AHEAD` in front, and each sample is called visible when it projects inside the
frame **and** the course does not stand between it and the lens. Then:

    forward_arc   the contiguous visible run starting at the pack. This is the
                  number the brief's "predict the next one to two seconds" is
                  about, and it is contiguous on purpose: a strip of channel
                  visible past a hairpin with a blind gap in between is not a
                  path the viewer can follow.
    forward_s     the same, in seconds, at the pack's own speed
    seen_arc      every visible sample in the window, contiguous or not
    turn_next     how many degrees the course turns over the next
                  `TURN_WINDOW` units
    turn_seen     how many of those degrees happen inside the visible forward
                  arc. `turn_seen / turn_next` is whether the bend is on
                  screen, and it is the switchback measure.

## What is *not* measured here

Nothing in this module knows what a good number is. The thresholds below are
reporting bands, used to name the worst intervals so they can be looked at;
the brief's targets are perceptual and are settled by watching the film. This
exists so that "the course ahead is cropped" can be pointed at a second range
rather than argued about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from race2.flow import DELIVERY, MARBLE_RADIUS, _basis, _project

__all__ = [
    "interest_group",
    "interest_weights",
    "LINK_GAP",
    "CONTEST_REACH",
    "INTEREST_SPAN",
    "INTEREST_MAX",
    "INTEREST_MIN",
    "LEAD_WEIGHT",
    "measure_readability",
    "readability_summary",
]

# --- the race-interest group -------------------------------------------------

# The arc gap, in layout units, at which two racers stop reading as a contest.
# 2.4 is about four marble diameters. Chosen against the hero replay: at 2.0
# the chain breaks inside the drum's own compression, at 3.0 it links the whole
# field on every straight and the rule stops saying anything.
LINK_GAP = 2.4
# How far behind the leader the contest may be found. Past this the fight is a
# different part of the race and following it would abandon the leader.
CONTEST_REACH = 12.0
# The widest arc span a group may cover. A frame solved across more than this
# is a frame of dots - V28 recorded that failure at forty units.
INTEREST_SPAN = 11.0
INTEREST_MAX = 6
INTEREST_MIN = 3
# What a leader alone in its own run is worth against one member of the bunch.
LEAD_WEIGHT = 1.9
# How fast a member's weight falls off with arc distance from the front of the
# group. At the full `INTEREST_SPAN` a tail member is worth `TAIL_FLOOR`.
TAIL_FLOOR = 0.45


def _runs(ranked: Sequence[int], arcs: dict[int, float],
          link: float) -> list[list[int]]:
    """Split a ranked field into runs of racers linked by `link` of arc."""
    out: list[list[int]] = []
    for marble in ranked:
        if out and (arcs[out[-1][-1]] - arcs[marble]) <= link:
            out[-1].append(marble)
        else:
            out.append([marble])
    return out


def interest_group(
    order: Sequence[int],
    arcs: dict[int, float],
    link: float = LINK_GAP,
    reach: float = CONTEST_REACH,
    span: float = INTEREST_SPAN,
    least: int = INTEREST_MIN,
    most: int = INTEREST_MAX,
) -> list[int]:
    """The marbles that are the contest right now, in rank order.

    See the module docstring for the rule. `order` is the race's own sticky
    ranking and `arcs` is progress along the spine, exactly as `active_pack`
    takes them, so the two are swappable and a candidate camera differs from
    the control in which one it calls and nothing else.
    """
    ranked = [m for m in order if m in arcs]
    if not ranked:
        return []
    front = arcs[ranked[0]]
    runs = _runs(ranked, arcs, link)

    chosen = list(runs[0])
    # The contest: the largest run of two or more that starts within `reach` of
    # the leader. Ties go to the one nearer the front, which is what `max` over
    # an ordered list with a stable key does.
    best: list[int] | None = None
    for run in runs[1:]:
        if len(run) < 2 or (front - arcs[run[0]]) > reach:
            continue
        if best is None or len(run) > len(best):
            best = run
    if best is not None:
        chosen.extend(best)

    # Trim on span first, then on count: a group that has to lose someone
    # should lose the one furthest off the back, not the one the cap happens to
    # reach.
    kept = [m for m in chosen if (front - arcs[m]) <= span]
    if len(kept) < least:
        kept = chosen[:least] if len(chosen) >= least else list(ranked[:least])
    return kept[:most]


def interest_weights(
    group: Sequence[int],
    arcs: dict[int, float],
    span: float = INTEREST_SPAN,
    link: float = LINK_GAP,
) -> dict[int, float]:
    """How much each member of the group pulls on the anchor.

    A lone leader is worth `LEAD_WEIGHT`; everyone else starts at one and is
    damped toward `TAIL_FLOOR` by how far off the front of the group they sit.
    """
    if not group:
        return {}
    front = arcs[group[0]]
    alone = len(group) < 2 or (front - arcs[group[1]]) > link
    out: dict[int, float] = {}
    for index, marble in enumerate(group):
        behind = max(front - arcs[marble], 0.0) / max(span, 1e-6)
        weight = 1.0 - (1.0 - TAIL_FLOOR) * min(behind, 1.0)
        if index == 0 and alone:
            weight = LEAD_WEIGHT
        out[marble] = weight
    return out


# --- track visibility --------------------------------------------------------

# The centreline window sampled around the pack, in layout units of arc, and
# the step it is sampled at. One unit is under two marble diameters, which is
# finer than the eye resolves a gap in a path.
BEHIND = 8.0
AHEAD = 70.0
STEP = 1.0
# Over how much course ahead the "how much does it turn" question is asked.
# 24 units is about two seconds of racing on the switchyard's straights and it
# is long enough to contain a whole hairpin.
TURN_WINDOW = 24.0
# How far inside the frame edge a sample must fall to count as visible. The
# last few per cent of a portrait frame is where the eye does not look and
# where the vignette is, and a path that only exists in the corner is not one
# the viewer reads.
EDGE = 0.94
# A racer is on screen with the same margin, and its own radius is allowed for
# so a marble half off the edge is half on.
RACER_EDGE = 1.0
# The reporting bands. Not targets - see the module docstring.
SHORT_FORWARD = 0.85          # seconds of visible path under which a frame is short
# The speed "seconds of path ahead" is quoted at, when the pack is slower than
# this. **The first build of this instrument divided by the instantaneous arc
# rate and reported a mean look-ahead of 265 seconds**: the pack's own speed
# goes through zero at a hairpin and again once the field is home, and four
# units of visible channel over an arc rate of 0.008 is a large number that
# means nothing. Flooring the divisor makes the quotient conservative wherever
# it binds - a slower pack is credited with *less* path than it really has -
# which is the right direction for a measure whose job is to find failures.
CRAWL = 5.0
TURN_READ = 0.55              # share of the coming turn that must be on screen


@dataclass
class _Sample:
    t: float
    shot: str
    group: list[int] = field(default_factory=list)
    on: dict[int, bool] = field(default_factory=dict)
    seen: dict[int, bool] = field(default_factory=dict)
    centre: tuple[float, float] = (0.0, 0.0)
    width: float = 0.0
    forward_arc: float = 0.0
    forward_s: float = 0.0
    seen_arc: float = 0.0
    turn_next: float = 0.0
    turn_run: float = 0.0
    turn_seen: float = 0.0
    depression: float = 0.0
    station: str = ""
    station_span: float = 0.0


def _heading(spine, s: float) -> tuple[float, float]:
    forward = spine.frame_at(min(max(s, 0.0), spine.length))[0]
    return forward[0], forward[2]


def _turn_between(spine, a: float, b: float, step: float = 3.0) -> float:
    """Unsigned degrees of heading change walked from `a` to `b`.

    Walked rather than taken as one angle between the endpoints, because a
    hairpin and a straight can share endpoints' headings and they are not the
    same thing to look at.
    """
    if b <= a:
        return 0.0
    total = 0.0
    here = _heading(spine, a)
    s = a
    while s < b:
        s = min(s + step, b)
        there = _heading(spine, s)
        dot = max(-1.0, min(1.0, here[0] * there[0] + here[1] * there[1]))
        total += math.degrees(math.acos(dot))
        here = there
    return total


def _visible_run(spine, position, forward, right, up, fov, s0: float,
                 size) -> tuple[float, float, float, float]:
    """Walk the centreline forward from `s0` and report what is on screen.

    Returns `(forward_arc, seen_arc, turn_run, turn_seen)`. A sample counts
    when it lands inside `EDGE` of the frame and the course does not stand
    between it and the lens - `Spine.blocked` already forgives blockers close
    to the target, which is what keeps the channel the samples lie in from
    occluding itself.

    **Two turn measures, and the course is why there are two.** The switchyard
    is a hairpin every 32 layout units: its longest straight is 16 units, and
    half of every cycle is a 180-degree turn at 7 to 12 degrees per unit. On a
    course like that "one to two seconds of contiguous path ahead" - 12 to 24
    units at racing speed - is asking to see *round* a fold, which no lens
    standing behind the pack can do. So:

        turn_run    degrees of the coming turn inside the contiguous run.
                    What the viewer can follow with their eye, unbroken.
        turn_seen   degrees of it visible **anywhere in frame**, gap or no gap.
                    On a switchback this is the honest question: the next leg
                    runs back the other way 9.6 units to the side, and a viewer
                    who can see both legs at once understands the fold whether
                    or not the apex between them is occluded.

    `turn_seen` is the one reported as the switchback measure. `turn_run` is
    kept beside it because a candidate that scores well on the first and badly
    on the second is showing the course as a set of fragments.
    """
    contiguous = 0.0
    running = True
    total = 0.0
    turn_run = 0.0
    turn_seen = 0.0
    previous = _heading(spine, s0)
    steps = int((min(s0 + AHEAD, spine.length) - s0) / STEP)
    for index in range(steps + 1):
        s = s0 + index * STEP
        point = spine.point_at(s)
        projected, _depth = _project(point, position, forward, right, up, fov, size)
        ok = (
            projected is not None
            and abs(projected[0]) <= EDGE
            and abs(projected[1]) <= EDGE
            and not spine.blocked(position, point)
        )
        here = _heading(spine, s)
        dot = max(-1.0, min(1.0, previous[0] * here[0] + previous[1] * here[1]))
        swept = math.degrees(math.acos(dot))
        previous = here
        if ok:
            total += STEP
            turn_seen += swept
            if running:
                contiguous = index * STEP
                turn_run += swept
        elif running and index > 0:
            running = False
    if running:
        contiguous = steps * STEP
    return contiguous, total, turn_run, turn_seen


def measure_readability(
    track: dict[str, Any],
    pack,
    spine,
    outcome,
    stations: dict[str, Any] | None = None,
    stride: int = 2,
    size: tuple[int, int] = DELIVERY,
) -> dict[str, Any]:
    """Racer and track visibility over a whole camera track.

    `stride` samples every nth frame; the occlusion test is the cost and two
    frames at 60 fps are 33 ms apart, which is under the eye's own integration
    time. Every reported interval is still quoted in seconds of film.
    """
    fps = float(track.get("fps", 60))
    stations = stations or {}
    marbles = sorted(pack.places[0]) if pack.places else []

    samples: list[_Sample] = []
    for cut in track.get("cuts", []):
        rows = cut.get("frames", [])
        name = str(cut.get("name", ""))
        for offset in range(0, len(rows), max(stride, 1)):
            row = rows[offset]
            when = float(row[0])
            index = pack.frame_at(when)
            position = (float(row[1]), float(row[2]), float(row[3]))
            aim = (float(row[4]), float(row[5]), float(row[6]))
            fov = float(row[7])
            forward, right, up = _basis(position, aim)

            order = pack.order_at(when)
            arcs = pack.arcs[index]
            group = interest_group(order, arcs)
            places = pack.places[index]

            sample = _Sample(t=round(when, 4), shot=name, group=list(group))
            xs: list[float] = []
            ys: list[float] = []
            for marble in marbles:
                point = places.get(marble)
                if point is None:
                    sample.on[marble] = False
                    sample.seen[marble] = False
                    continue
                projected, depth = _project(point, position, forward, right, up,
                                            fov, size)
                if projected is None:
                    sample.on[marble] = False
                    sample.seen[marble] = False
                    continue
                # The marble's own half-width on screen, so one sitting on the
                # edge is scored as half visible rather than as gone.
                half_up = math.tan(math.radians(fov) * 0.5)
                pad = MARBLE_RADIUS / max(depth * half_up, 1e-6)
                on = (abs(projected[0]) <= RACER_EDGE + pad * size[1] / size[0]
                      and abs(projected[1]) <= RACER_EDGE + pad)
                sample.on[marble] = bool(on)
                sample.seen[marble] = bool(on and not spine.blocked(position, point))
                if marble in group and on:
                    xs.append(projected[0])
                    ys.append(projected[1])
            if xs:
                sample.centre = (sum(xs) / len(xs), sum(ys) / len(ys))
                sample.width = (max(xs) - min(xs)) / 2.0

            s_pack = pack.pack_arcs[index]
            contiguous, total, turn_run, turn_seen = _visible_run(
                spine, position, forward, right, up, fov, s_pack, size
            )
            sample.forward_arc = contiguous
            sample.seen_arc = total
            sample.turn_run = turn_run
            sample.turn_seen = turn_seen
            sample.turn_next = _turn_between(
                spine, s_pack, min(s_pack + TURN_WINDOW, spine.length)
            )
            speed = max(abs(pack.rates(index)[0]), CRAWL)
            sample.forward_s = contiguous / speed
            drop = position[1] - aim[1]
            flat = math.hypot(aim[0] - position[0], aim[2] - position[2])
            sample.depression = math.degrees(math.atan2(drop, max(flat, 1e-6)))

            # The nearest station in front of the pack, and how much of the
            # frame it covers. Part G: a mechanism that fills the frame while
            # the racers are hard to find is a framing fault, not a set one.
            best: tuple[float, str, float] | None = None
            for module_id, detail in stations.items():
                centre = detail["centre"] if isinstance(detail, dict) else detail
                radius = float(detail.get("radius", 2.0)) if isinstance(detail, dict) else 2.0
                projected, depth = _project(centre, position, forward, right, up,
                                            fov, size)
                if projected is None or abs(projected[0]) > 1.4 or abs(projected[1]) > 1.4:
                    continue
                half_up = math.tan(math.radians(fov) * 0.5)
                span = radius / max(depth * half_up, 1e-6) * size[1] / size[0]
                if best is None or span > best[0]:
                    best = (span, module_id, depth)
            if best is not None:
                sample.station_span = best[0]
                sample.station = best[1]
            samples.append(sample)

    return _report(samples, track, pack, outcome, fps, stride, marbles, size)


def _intervals(flags: Sequence[tuple[float, bool]], gap: float) -> list[tuple[float, float]]:
    """Contiguous `True` runs as `(from, to)`, merged across gaps under `gap`."""
    out: list[list[float]] = []
    for when, flag in flags:
        if not flag:
            continue
        if out and when - out[-1][1] <= gap:
            out[-1][1] = when
        else:
            out.append([when, when])
    return [(round(a, 3), round(b, 3)) for a, b in out]


def _longest(spans: Sequence[tuple[float, float]]) -> float:
    return round(max((b - a for a, b in spans), default=0.0), 3)


def _report(samples, track, pack, outcome, fps, stride, marbles, size) -> dict[str, Any]:
    if not samples:
        return {"frames": 0}
    step = stride / fps
    span = samples[-1].t - samples[0].t + step

    # Per marble, over the part of the film that marble is still racing.
    finished = {
        racer.marble_id: racer.finish_time
        for racer in outcome.racers if racer.finish_time is not None
    }
    per_marble: dict[str, Any] = {}
    for marble in marbles:
        done = finished.get(marble)
        live = [s for s in samples if done is None or s.t <= done + 0.15]
        if not live:
            continue
        seen = [s for s in live if s.seen.get(marble)]
        gaps = _intervals([(s.t, not s.seen.get(marble)) for s in live], step * 1.5)
        contest = [s for s in live if marble in s.group]
        contest_gaps = _intervals(
            [(s.t, marble in s.group and not s.seen.get(marble)) for s in live],
            step * 1.5,
        )
        per_marble[str(marble)] = {
            "racing_s": round(len(live) * step, 3),
            "visible_pct": round(100.0 * len(seen) / len(live), 2),
            "on_screen_pct": round(
                100.0 * len([s for s in live if s.on.get(marble)]) / len(live), 2),
            "longest_gap_s": _longest(gaps),
            "gaps_over_0s5": len([g for g in gaps if g[1] - g[0] >= 0.5]),
            "in_contest_s": round(len(contest) * step, 3),
            "contest_visible_pct": round(
                100.0 * len([s for s in contest if s.seen.get(marble)])
                / max(len(contest), 1), 2),
            "worst_contest_gap_s": _longest(contest_gaps),
        }

    group_seen = [
        sum(1 for m in s.group if s.seen.get(m)) / max(len(s.group), 1)
        for s in samples
    ]
    widths = [s.width for s in samples if s.width > 0.0]
    forward = [s.forward_arc for s in samples]
    forward_s = [s.forward_s for s in samples]

    short = _intervals([(s.t, s.forward_s < SHORT_FORWARD) for s in samples], step * 2.5)
    short = [w for w in short if w[1] - w[0] >= 0.25]
    turning = [s for s in samples if s.turn_next >= 18.0]
    blind = _intervals(
        [(s.t, s.turn_next >= 18.0 and s.turn_seen < TURN_READ * s.turn_next)
         for s in samples], step * 2.5,
    )
    blind = [w for w in blind if w[1] - w[0] >= 0.25]
    dominated = _intervals(
        [(s.t, s.station_span >= 0.55
          and (sum(1 for m in s.group if s.seen.get(m)) / max(len(s.group), 1)) < 0.6)
         for s in samples], step * 2.5,
    )
    dominated = [w for w in dominated if w[1] - w[0] >= 0.2]

    def worst_windows(values, count=3, width=0.6):
        """The `count` non-overlapping windows with the lowest mean value."""
        held = max(int(width / step), 1)
        scored = []
        for start in range(0, len(values) - held + 1):
            chunk = values[start:start + held]
            scored.append((sum(chunk) / len(chunk), samples[start].t,
                           samples[start + held - 1].t))
        scored.sort(key=lambda row: (row[0], row[1]))
        out: list[tuple[float, float, float]] = []
        for value, a, b in scored:
            if any(not (b < pa or a > pb) for _v, pa, pb in out):
                continue
            out.append((value, a, b))
            if len(out) >= count:
                break
        return [{"from": round(a, 3), "to": round(b, 3), "value": round(v, 3)}
                for v, a, b in out]

    group_sizes = [len(s.group) for s in samples]
    return {
        "camera": str(track.get("camera", "")),
        "frames": len(samples),
        "stride": stride,
        "seconds": round(span, 3),
        "size": list(size),
        "group": {
            "mean_size": round(sum(group_sizes) / len(group_sizes), 3),
            "size_range": [min(group_sizes), max(group_sizes)],
            "visible_pct": round(100.0 * sum(group_seen) / len(group_seen), 2),
            "all_visible_pct": round(
                100.0 * sum(1 for g in group_seen if g > 0.999) / len(group_seen), 2),
            "screen_width_mean": round(sum(widths) / max(len(widths), 1), 4),
            "screen_width_max": round(max(widths, default=0.0), 4),
            "screen_y_mean": round(
                sum(s.centre[1] for s in samples) / len(samples), 4),
            "screen_y_range": [round(min(s.centre[1] for s in samples), 3),
                               round(max(s.centre[1] for s in samples), 3)],
            "worst_visibility": worst_windows(group_seen),
        },
        "racers": per_marble,
        "racer_visible_pct_min": round(
            min((v["visible_pct"] for v in per_marble.values()), default=0.0), 2),
        "racer_longest_gap_s": round(
            max((v["longest_gap_s"] for v in per_marble.values()), default=0.0), 3),
        "track": {
            "forward_arc_mean": round(sum(forward) / len(forward), 3),
            "forward_arc_p10": round(sorted(forward)[len(forward) // 10], 3),
            "forward_arc_min": round(min(forward), 3),
            "forward_s_mean": round(sum(forward_s) / len(forward_s), 3),
            "forward_s_p10": round(sorted(forward_s)[len(forward_s) // 10], 3),
            "seen_arc_mean": round(
                sum(s.seen_arc for s in samples) / len(samples), 3),
            "depression_mean": round(
                sum(s.depression for s in samples) / len(samples), 2),
            "depression_range": [round(min(s.depression for s in samples), 2),
                                 round(max(s.depression for s in samples), 2)],
            "short_path_pct": round(
                100.0 * sum(1 for s in samples if s.forward_s < SHORT_FORWARD)
                / len(samples), 2),
            "short_path_intervals": short[:8],
            "worst_forward": worst_windows(forward_s),
        },
        "turns": {
            "turning_frames": len(turning),
            "turn_read_mean": round(
                sum(min(s.turn_seen / s.turn_next, 1.0) for s in turning)
                / max(len(turning), 1), 3),
            "turn_run_mean": round(
                sum(min(s.turn_run / s.turn_next, 1.0) for s in turning)
                / max(len(turning), 1), 3),
            "blind_turn_pct": round(
                100.0 * sum(1 for s in turning
                            if s.turn_seen < TURN_READ * s.turn_next)
                / max(len(turning), 1), 2),
            "blind_intervals": blind[:8],
        },
        "mechanism": {
            "span_mean": round(sum(s.station_span for s in samples) / len(samples), 4),
            "span_max": round(max(s.station_span for s in samples), 4),
            "dominant_pct": round(
                100.0 * sum(1 for s in samples if s.station_span >= 0.55)
                / len(samples), 2),
            "dominant_intervals": dominated[:8],
        },
        "per_shot": _per_shot(samples, step),
    }


def _per_shot(samples, step) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sample in samples:
        bucket = out.setdefault(sample.shot, {
            "frames": 0, "group_seen": 0.0, "forward_s": 0.0, "width": 0.0,
            "y": 0.0, "short": 0,
        })
        bucket["frames"] += 1
        bucket["group_seen"] += sum(
            1 for m in sample.group if sample.seen.get(m)) / max(len(sample.group), 1)
        bucket["forward_s"] += sample.forward_s
        bucket["width"] += sample.width
        bucket["y"] += sample.centre[1]
        bucket["short"] += 1 if sample.forward_s < SHORT_FORWARD else 0
    for name, bucket in out.items():
        count = max(bucket["frames"], 1)
        out[name] = {
            "seconds": round(bucket["frames"] * step, 3),
            "group_visible_pct": round(100.0 * bucket["group_seen"] / count, 2),
            "forward_s_mean": round(bucket["forward_s"] / count, 3),
            "screen_width_mean": round(bucket["width"] / count, 4),
            "screen_y_mean": round(bucket["y"] / count, 4),
            "short_path_pct": round(100.0 * bucket["short"] / count, 2),
        }
    return out


def readability_summary(report: dict[str, Any]) -> str:
    """The one-screen version, for a terminal."""
    if not report.get("frames"):
        return "  no frames"
    group = report["group"]
    track = report["track"]
    turns = report["turns"]
    lines = [
        f"  group   size {group['mean_size']:.2f} "
        f"{group['size_range']}  visible {group['visible_pct']:.1f}%  "
        f"all-visible {group['all_visible_pct']:.1f}%",
        f"  frame   width {group['screen_width_mean']:.3f}  "
        f"y {group['screen_y_mean']:+.3f} "
        f"[{group['screen_y_range'][0]:+.2f},{group['screen_y_range'][1]:+.2f}]",
        f"  track   ahead {track['forward_arc_mean']:.1f} u "
        f"({track['forward_s_mean']:.2f} s, p10 {track['forward_s_p10']:.2f} s)  "
        f"seen {track['seen_arc_mean']:.1f} u  "
        f"short {track['short_path_pct']:.1f}%  "
        f"depression {track['depression_mean']:.1f}deg",
        f"  turns   read {turns['turn_read_mean']:.2f} "
        f"(contiguous {turns['turn_run_mean']:.2f})  "
        f"blind {turns['blind_turn_pct']:.1f}% of {turns['turning_frames']} frames",
        f"  mech    span max {report['mechanism']['span_max']:.2f}  "
        f"dominant {report['mechanism']['dominant_pct']:.1f}%",
        f"  racers  worst visible {report['racer_visible_pct_min']:.1f}%  "
        f"longest gap {report['racer_longest_gap_s']:.2f} s",
    ]
    for window in track["worst_forward"][:3]:
        lines.append(f"    short path {window['from']:.2f}-{window['to']:.2f} s "
                     f"({window['value']:.2f} s of path)")
    return "\n".join(lines)
