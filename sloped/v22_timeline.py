"""How much of the machine to keep: the V22 pacing model.

V21 is 18.45 s and it is too fast, but "too fast" is not an editing
instruction. This module turns it into one. It asks the replay a single
question - **is anything happening?** - and answers it with a number that can
be compared across the whole film, so a cut is defended by the footage rather
than by taste.

The number is `churn`: how far the eight marbles move, per marble, per second
of replay. Not speed, because a marble falling at 40 wu/s and a marble held
against a spinning blade at 3 wu/s look completely different on screen and
speed cannot tell you which is which; displacement can. Measured that way the
film sorts itself into two populations with nothing in between:

    the parked drum, replay 2.30-5.70          churn 0.43 - 1.64
    everything the film shows, 0.20-23.60      churn 2.33 - 9.28 and up

There is a factor of four between them and no 0.25 s slice anywhere in the
middle. That gap is the whole argument of this pass, and `CHURN_FLOOR` sits in
it.

## What the floor says about the film we shipped

Run every omission in V21 past it and two of the three come back wrong:

    replay          churn   verdict
    1.000-2.300      4.11   LIVE. Eight marble-on-marble hits, including the
                            hardest one in the drum (9.08 wu/s at 1.1875).
                            V21.1 cut it.
    2.300-5.700      1.17   DEAD. No contact, the field crawling under a rotor
                            that is doing nothing to it. Correctly cut.
    14.500-15.350    7.01   LIVE, and climbing - 5.03, 6.80, 8.29, 9.28 across
                            its four quarters. It is the field accelerating out
                            of the spinner trap, and it contains the leader's
                            own escape (marble 7 into `leg3` at 14.9958). V19
                            cut it and nothing since has re-examined it.

So the brief's suspicion is right in both places it looks, and the correction
is not "make the film longer" - it is **put the omission where the machine is
idle**, which is one place and not three.

## The second reason to restore the mixing, which nobody asked for

An omission is visible in proportion to how far things move across it. At
replay 1.000 the eight are still flying, so V21's join teleports them a mean of
**3.76 wu** - more than half the width of the field they are in. By 1.9 they
have found the arrangement they then hold all the way to 5.83, so the same join
made later moves them **1.00 wu**. Restoring the mixing does not cost a more
obvious cut. It buys a less obvious one.

## What this module will not do

It edits a master that already exists, so it can only ever *restore frames V21
dropped*. Replay the camera track never covered - 2.300-5.700 and
14.500-15.350 - is not in any file on disk, and `RESTORATIONS` records those as
work for the V22 camera master rather than pretending they can be cut in here.
No frame is generated, blended, held or reordered by anything below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from sloped.presentation import Clock, omit_frames

__all__ = [
    "CANDIDATES",
    "CHURN_FLOOR",
    "Candidate",
    "Restoration",
    "RESTORATIONS",
    "Slice",
    "activity",
    "beats",
    "candidate_clock",
    "churn",
    "cut_jump",
    "cut_on_motion",
    "field_at",
    "mixing",
    "retained_collisions",
    "shots",
    "sound_marks",
    "verify",
]


# The line between "the machine is doing something" and "the machine is idle",
# in world units of marble travel per marble per second of replay. Not a taste
# threshold: the drum's parked stretch tops out at 1.64 and the lowest slice
# anywhere the film keeps is 2.33, so anything from about 1.7 to 2.3 picks out
# the same frames. 2.00 is the middle of that.
CHURN_FLOOR = 2.00

# The slice the floor is measured over. Short enough to find a cut point to
# within a few frames, long enough that one marble's single bounce does not
# drag a quarter-second over the line on its own.
SLICE = 0.25

# The master every candidate here is cut from, and its frame count. The V22
# camera master will have its own; nothing below assumes this one except the
# `frames` figures in `CANDIDATES`, which `candidate_clock` recomputes anyway.
MASTER_FRAMES = 1150


# --- is anything happening? -------------------------------------------------


def field_at(replay: dict[str, Any], t: float) -> dict[int, tuple[float, float, float]]:
    """Every marble's position at a replay instant, by id.

    The replay is written at exactly 60 Hz from t=0, so the frame index is the
    instant times 60 - no search, and no interpolation either, because a
    fractional instant is not a thing this module ever needs.
    """
    frames = replay["frames"]
    index = int(round(t * 60.0))
    index = max(0, min(len(frames) - 1, index))
    return {
        int(sample["id"]): tuple(float(value) for value in sample["p"])
        for sample in frames[index]["marbles"]
    }


def churn(replay: dict[str, Any], t0: float, t1: float) -> float:
    """World units of travel per marble per second, over `[t0, t1]`.

    The path length the field actually walks, not the displacement between the
    ends: a marble rattling in a pocket returns to where it started and a
    difference of endpoints would score it zero, which is the one reading that
    would make the spinner trap look like dead air.
    """
    if t1 <= t0:
        return 0.0
    frames = replay["frames"]
    first = max(0, int(round(t0 * 60.0)))
    last = min(len(frames) - 1, int(round(t1 * 60.0)))
    total = 0.0
    count = 0
    previous: dict[int, tuple[float, float, float]] | None = None
    for index in range(first, last + 1):
        current = {
            int(sample["id"]): tuple(float(value) for value in sample["p"])
            for sample in frames[index]["marbles"]
        }
        if previous is not None:
            total += sum(
                math.dist(previous[key], current[key])
                for key in current
                if key in previous
            )
        count = max(count, len(current))
        previous = current
    if not count:
        return 0.0
    return total / count / (t1 - t0)


@dataclass(frozen=True)
class Slice:
    """One `SLICE`-long verdict on one stretch of replay."""

    replay_from: float
    replay_to: float
    churn: float
    collisions: int
    hardest: float

    @property
    def live(self) -> bool:
        return self.churn >= CHURN_FLOOR or self.collisions > 0


def activity(
    replay: dict[str, Any],
    t0: float,
    t1: float,
    step: float = SLICE,
) -> list[Slice]:
    """`t0` to `t1` chopped into slices, each scored and judged."""
    hits = [
        event
        for event in replay["events"]
        if event["kind"] == "collision" and t0 - 1e-9 <= float(event["t"]) <= t1 + 1e-9
    ]
    out: list[Slice] = []
    edge = t0
    while edge < t1 - 1e-9:
        stop = min(edge + step, t1)
        mine = [one for one in hits if edge - 1e-9 <= float(one["t"]) < stop - 1e-9]
        out.append(
            Slice(
                replay_from=edge,
                replay_to=stop,
                churn=churn(replay, edge, stop),
                collisions=len(mine),
                hardest=max((float(one["speed"]) for one in mine), default=0.0),
            )
        )
        edge = stop
    return out


# --- the candidates ---------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One pacing timeline: which of the master's frames the film keeps.

    `cuts` are inclusive master-frame ranges to drop, in the same units
    `presentation.omit_frames` takes, so a candidate is applied to a clock
    without this module knowing anything about ffmpeg. `restores` name replay
    the master does not contain and is therefore *not* in the proof clip - see
    `RESTORATIONS`.
    """

    key: str
    title: str
    cuts: tuple[tuple[int, int], ...]
    note: str
    restores: tuple[str, ...] = ()

    def dropped(self) -> int:
        return sum(last - first + 1 for first, last in self.cuts)


# Master frame f in the first window shows replay 0.200 + f/60, so the start's
# dial is one number: the last window-0 frame the film keeps.
#
#     f  48   replay 1.000   V21 stops here
#     f 102   replay 1.900   churn falls through the floor here
#     f 114   replay 2.100   the last marble-on-marble hit is at 2.0125
#     f 126   replay 2.300   the window ends; 2.100-2.300 buys nothing
#
# Every candidate also drops master frames 127-133, which are the head of the
# second start window - replay 5.700-5.817, the field parked before the floor
# opens. That trim is V21.1's and it is correct at every setting of the dial.
_TAIL = 133

CANDIDATES: dict[str, Candidate] = {
    "v21": Candidate(
        key="v21",
        title="V21 as delivered",
        cuts=((49, _TAIL),),
        note="the baseline: 0.683 s of live mixing, 7 of the drum's 15 hits, "
        "and a join the field crosses 3.76 wu wide",
    ),
    "a": Candidate(
        key="a",
        title="A - mixing only",
        cuts=((103, _TAIL),),
        note="stops on the frame churn falls through CHURN_FLOOR. 13 of 15 "
        "hits; the two it misses are the weakest in the drum",
    ),
    "b": Candidate(
        key="b",
        title="B - mixing and the last knock",
        cuts=((115, _TAIL),),
        note="stops 0.087 s after the drum's final contact, so the last hit "
        "has frames to read. Every physical event in the start is in the film",
    ),
    "c": Candidate(
        key="c",
        title="C - the whole drum window",
        cuts=((127, _TAIL),),
        note="every frame the camera track ever covered. The last 0.200 s "
        "contains no contact and scores 1.02-1.82: it is settle, not mixing",
    ),
}

# What a 2.5 s mixing candidate would need, and why there is no D.
#
# The brief asks for one. It cannot be built and it should not be: the drum's
# last marble-on-marble contact is at replay 2.0125, the camera track stops at
# 2.300, and every quarter-second from 2.300 to 5.700 scores under the floor.
# Mixing that runs 2.5 s from the gates would end at replay 2.817, which is
# 0.517 s of footage that (a) was never rendered and (b) shows eight marbles
# crawling. The dial's useful range ends at candidate C and its useful setting
# is short of it.
NO_CANDIDATE_D = (
    "2.5 s of mixing would run to replay 2.817. The last contact is at 2.0125 "
    "and 2.300-5.700 never rises above churn 1.64, so the extra 0.517 s is "
    "unrendered footage of a settled field."
)


@dataclass(frozen=True)
class Restoration:
    """Replay the V22 camera master should cover that no master covers now."""

    replay_from: float
    replay_to: float
    why: str
    lens: str
    proven: bool = False

    @property
    def seconds(self) -> float:
        return self.replay_to - self.replay_from

    @property
    def frames(self) -> int:
        return int(round(self.seconds * 60.0))


RESTORATIONS: tuple[Restoration, ...] = (
    Restoration(
        replay_from=14.500,
        replay_to=15.350,
        lens="obstacle, extended; or split, brought forward",
        why="the field accelerating out of the spinners - churn 5.03 rising to "
        "9.28 - and the leader's own escape into leg3 at 14.9958. It is the "
        "payoff of the 2.5 s the film has just spent watching the trap hold "
        "them, and it is the single highest-churn stretch the film omits",
    ),
    Restoration(
        replay_from=23.600,
        replay_to=24.467,
        lens="finish, extended",
        why="7th and 8th crossing at 24.3167 and 24.4167. The film currently "
        "ends 0.100 s after the 6th and two marbles are still running: churn "
        "over this stretch is 10.8-13.0, higher than anything in the finish "
        "window itself. It is also the only place a landing beat can come from",
    ),
)


def candidate_clock(base: Clock, candidate: Candidate) -> tuple[Clock, tuple[tuple[int, int], ...]]:
    """The clock this candidate's film runs on, and the frames to keep."""
    return omit_frames(base, candidate.cuts)


# --- reading a candidate ----------------------------------------------------


def mixing(replay: dict[str, Any], clock: Clock, gates: float | None = None) -> dict[str, float]:
    """What the start window shows, in replay seconds and in output seconds.

    `drum` is every frame of the start on screen; `live` is from the gates
    first moving, which is the part a viewer would call mixing. The two differ
    by the held line-up, and quoting only one of them is how this argument gets
    confusing.
    """
    first = clock.segments[0]
    opened = 0.316667 if gates is None else gates
    return {
        "replay_from": first[2],
        "replay_to": first[3],
        "drum": first[3] - first[2],
        "live": max(0.0, first[3] - opened),
        "gates_replay": opened,
        "output_from": clock.origin + first[0],
        "output_to": clock.origin + first[1],
    }


def retained_collisions(
    replay: dict[str, Any], clock: Clock, before: float = 3.0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The start drum's contacts, split into the ones on screen and the rest."""
    hits = [
        event
        for event in replay["events"]
        if event["kind"] == "collision" and float(event["t"]) < before
    ]
    kept = [one for one in hits if clock.at(float(one["t"])) is not None]
    gone = [one for one in hits if clock.at(float(one["t"])) is None]
    return kept, gone


def cut_on_motion(replay: dict[str, Any], clock: Clock, window: float = 0.1) -> float:
    """Churn over the last `window` of replay before the start omission.

    Half of the tie-break; `cut_jump` is the other half, and they pull against
    each other. An omission reads as a *skip* only if the field is still moving
    when it happens - cut a settling shot and the viewer's last impression is
    that the machine stopped, which is the one thing the whoosh then
    contradicts. But cut while the field is *flying* and the far side cannot be
    reconciled with the near one, and the skip reads as a jump cut instead.

    So the cut wants churn above `CHURN_FLOOR` **and** a small jump, and over
    the last tenth of a second the four settings separate completely:

        V21   10.40   jump 3.76   cut mid-tumble: a jump cut
        A      2.72   jump 1.05   moving, and the far side matches
        B      1.51   jump 1.00   the field has already settled
        C      1.40   jump 1.00   more so

    Exactly one of them is over the floor with the field where it stays.
    """
    edge = clock.segments[0][3]
    return churn(replay, max(0.0, edge - window), edge)


def cut_jump(replay: dict[str, Any], clock: Clock) -> list[tuple[float, float, float]]:
    """Per omission: `(output second, mean marble jump, worst jump)` in wu.

    How visible the cut is. A join the field crosses without moving is one a
    viewer cannot see; V21's start join moves them 3.76 wu across a field 6.4 wu
    wide, which is why it reads as a jump rather than as a skip.
    """
    out: list[tuple[float, float, float]] = []
    for before, after in zip(clock.segments, clock.segments[1:]):
        if after[2] - before[3] <= 1e-6:
            continue
        near = field_at(replay, before[3])
        far = field_at(replay, after[2])
        gaps = [math.dist(near[key], far[key]) for key in near if key in far]
        if not gaps:
            continue
        out.append((clock.origin + after[0], sum(gaps) / len(gaps), max(gaps)))
    return out


def shots(clock: Clock, names: Sequence[str]) -> list[tuple[str, float, float, float]]:
    """Per lens: `(name, output from, output to, seconds)`, the hold included.

    The hold is part of the first shot, because a viewer does not experience it
    as a separate one - it is the opening lens, standing still.
    """
    out: list[tuple[str, float, float, float]] = []
    for index, segment in enumerate(clock.segments):
        start, stop = clock.window(index)
        if index == 0:
            start = 0.0
        name = names[index] if index < len(names) else f"#{index}"
        out.append((name, start, stop, stop - start))
    return out


# --- the beats --------------------------------------------------------------
#
# Approach, interaction, exit for each thing the machine does, in replay
# seconds, read off the events and the churn rather than typed from memory.
# `approach` is where the field is committed to the event and a viewer can see
# what is about to happen; `interaction` is contact; `exit` is where the result
# is legible - who gained, who lost - and it is the one most often cut.

BEATS: tuple[tuple[str, float, float, float, str], ...] = (
    ("line-up",        0.200,  0.317,  0.317, "eight in eight bays, the only still picture in the film"),
    ("gates",          0.317,  0.620,  0.620, "the paddles swing and the field pours into the drum"),
    ("tumble",         0.620,  1.300,  1.900, "10 contacts, the hardest at 1.1875 - the mixing proper"),
    ("settle",         1.300,  2.013,  2.300, "5 more contacts, the field finding its arrangement"),
    ("parked",         2.300,  5.700,  5.700, "no contact, churn 1.17 - the only idle stretch in the replay"),
    ("trapdoor",       5.900,  6.117,  6.300, "the floor opens under a settled field"),
    ("the drop",       6.117,  6.871,  7.620, "12 contacts to 21.3 wu/s as the eight fall through"),
    ("run-out",        6.888,  7.700,  8.063, "mixer, shuffle, launch: hits of 23.3, 23.6, 26.0, 24.2"),
    ("first descent",  7.620,  8.620,  9.800, "leg1, the field strung out and accelerating past 50 wu/s"),
    ("hairpin",        9.800, 10.400, 10.800, "the bend, two hard contacts"),
    ("obstacle",      10.800, 12.300, 15.350, "approach at 45 wu/s, 29 contacts in 1.2 s, then the trap"),
    ("the trap",      12.300, 13.400, 14.400, "held against turning blades, churn 4.20 - slow, never still"),
    ("the escape",    14.400, 14.996, 18.054, "the leader out of the trap at 14.996, then one every 0.4 s"),
    ("the fork",      16.300, 17.850, 19.350, "eight route decisions, blue against orange"),
    ("branch race",   17.670, 19.070, 19.367, "the two routes run side by side"),
    ("the merge",     19.367, 20.067, 20.721, "the routes converge, contacts of 33.2 and 14.7"),
    ("final sprint",  20.067, 20.850, 20.850, "the run to the line"),
    ("the crossings", 20.850, 23.500, 24.417, "six in the film, eight in the replay"),
)


def beats(clock: Clock) -> list[dict[str, Any]]:
    """The beat table mapped onto one candidate's film.

    Each beat reports whether its approach, its interaction and its exit are on
    screen. A beat whose exit is missing is one the viewer sees happen and
    never sees the result of, which is the specific failure this pass is for.
    """
    out: list[dict[str, Any]] = []
    for name, approach, interaction, exit_at, detail in BEATS:
        row = {
            "name": name,
            "detail": detail,
            "replay": (approach, interaction, exit_at),
            "approach": clock.at(approach),
            "interaction": clock.at(interaction),
            "exit": clock.at(exit_at),
        }
        row["whole"] = all(
            row[part] is not None for part in ("approach", "interaction", "exit")
        )
        out.append(row)
    return out


# --- sound ------------------------------------------------------------------


def sound_marks(replay: dict[str, Any], clock: Clock, gates: float, panel: float) -> list[dict[str, Any]]:
    """Where the audio design's fixed cues land on a candidate's clock.

    Nothing here writes audio. `audio/marble.py` derives every cue from the
    clock it is given, so a new timeline moves the whole soundtrack with the
    picture for free - but three cues are *placed* rather than derived and an
    integrator needs to know they moved, and by how much.
    """
    marks: list[dict[str, Any]] = []
    marks.append({"cue": "tension run-up ends", "on": "the gates", "output": gates})
    marks.append({"cue": "trapdoor", "on": "start.panel first moves", "output": panel})
    for output, dropped in _omission_pairs(clock):
        marks.append(
            {
                "cue": "whoosh",
                "on": f"{dropped:.3f} s omitted",
                "output": output,
                "seconds": dropped,
            }
        )
    winner = _winner_crossing(replay)
    at = clock.at(winner)
    if at is not None:
        marks.append({"cue": "winner accent", "on": "the first crossing", "output": at})
    return sorted(marks, key=lambda one: one["output"])


def _omission_pairs(clock: Clock) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for before, after in zip(clock.segments, clock.segments[1:]):
        dropped = after[2] - before[3]
        if dropped > 1e-6:
            out.append((clock.origin + after[0], dropped))
    return out


def _winner_crossing(replay: dict[str, Any]) -> float:
    for event in replay["events"]:
        if event["kind"] == "finish_line" and int(event["order"]) == 1:
            return float(event["t"])
    raise ValueError("the replay records no winner")


# --- the rules --------------------------------------------------------------


def verify(
    clock: Clock,
    keep: Sequence[tuple[int, int]],
    base: Clock,
) -> list[str]:
    """Everything an omission can quietly get wrong, checked. Empty is a pass.

    `omit_frames` already refuses the two worst mistakes, so this is the belt
    to its braces - and it checks the *result* rather than the request, which
    is the only way a slope error or an off-by-one at a window edge shows up.
    """
    findings: list[str] = []
    fps = float(clock.fps)

    # 1. Slope one in every window: one frame of replay per frame of film.
    for index, (out_from, out_to, replay_from, replay_to) in enumerate(clock.segments):
        span = out_to - out_from
        replay_span = replay_to - replay_from
        if abs(span - replay_span) > 2e-6:
            findings.append(
                f"window {index} runs {span:.6f} s of film over "
                f"{replay_span:.6f} s of replay - that is a speed change"
            )

    # 2. The film steps forwards at every frame boundary, and never twice on
    #    the same instant.
    previous: float | None = None
    for frame in range(clock.master_frames):
        shown = clock.replay_at(clock.origin + frame / fps)
        if shown is None:
            findings.append(f"film frame {frame} is not on the map")
            break
        if previous is not None and shown <= previous + 1e-9:
            findings.append(
                f"film frame {frame} shows replay {shown:.6f} after {previous:.6f} "
                "- that is a repeat or a rewind"
            )
            break
        previous = shown

    # 3. Every kept master frame still shows the instant it always showed.
    kept = [frame for first, last in keep for frame in range(first, last + 1)]
    if len(kept) != clock.master_frames:
        findings.append(
            f"the clock carries {clock.master_frames} frames but the keep list "
            f"has {len(kept)}"
        )
    for index, master in enumerate(kept):
        was = base.replay_at(base.origin + master / fps)
        now = clock.replay_at(clock.origin + index / fps)
        if was is None or now is None or abs(was - now) > 1e-6:
            findings.append(
                f"master frame {master} showed {was} and now shows {now}"
            )
            break

    # 4. Frame 0 survives, because the hold clones it.
    if not keep or keep[0][0] != 0:
        findings.append("master frame 0 was dropped; the hold has nothing to clone")

    # 5. The omissions all step forwards.
    for before, after in zip(clock.segments, clock.segments[1:]):
        if after[2] < before[3] - 1e-9:
            findings.append(
                f"the film goes back from replay {before[3]:.6f} to {after[2]:.6f}"
            )

    return findings
