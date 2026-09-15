"""What a camera track actually achieved, measured rather than asserted.

Three questions, and each one is a failure mode the brief names by hand:

**How big are the racers?** Part E: "a major failure mode is racers becoming
tiny". Measured as the horizontal span of the leading group as a fraction of
frame width, and as the diameter of a single racer in pixels at both the
delivery size and at phone size. The 25-45% band is a design reference; the
report prints what was achieved and flags what is outside it, and a shot that
is outside it because it is deliberately a wide establishing beat says so in
its own note.

**Is the next threat visible before it is hit?** Part G. For every
anticipation shot, whether the mechanism it names is inside the frustum for the
whole shot, and how long before the leader's contact it first appears. A shot
that reveals the obstacle after the collision has failed at the one job it was
authored for.

**Is it legible on a phone?** Part S. The same measurements at 270x480, plus
the count of racers in frame - because two racers is the least that can show a
position, and a shot with one racer in it is not a shot of a race.

## Why a frustum test and not a render

A render is the judgement; this is the screen. `docs/race2_drama_camera.md`
records the finding from V21's camera pass that a frustum count is not
visibility - a marble can be inside the frustum and behind a guard rail - so
nothing here is treated as proof. It is treated as a filter: everything it
flags is looked at, and what it passes is still looked at in motion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from sloped.scale import SIM_TO_LAYOUT

__all__ = ["ShotReport", "report", "PHONE", "DELIVERY"]

DELIVERY = (1080, 1920)
PHONE = (270, 480)

# A racer under about twenty pixels across in the delivery frame is a coloured
# dot a viewer reads as scenery. Race #1's camera check uses the same number.
MIN_RACER_PIXELS = 20.0
MIN_RACERS_IN_FRAME = 2
# The band the brief gives for the leading group's share of frame width.
GROUP_BAND = (0.25, 0.45)

LAYOUT_RADIUS = 0.285


@dataclass
class ShotReport:
    name: str
    mode: str
    subject: str
    start: float
    end: float
    group_width: float = 0.0          # fraction of frame width, at the midpoint
    group_width_min: float = 0.0
    group_width_max: float = 0.0
    racer_pixels: float = 0.0         # delivery frame
    phone_pixels: float = 0.0
    racers_in_frame: int = 0
    min_racers_in_frame: int = 0
    subject_visible: float = 0.0      # fraction of the shot the subject is in frame
    lead_seconds: float | None = None  # how long before contact it first appeared
    # When two racers were first in frame, as a fraction of the shot. On an
    # anticipation shot an empty opening is the *point* - the mechanism is
    # revealed, then the field arrives into it - so "no racers at the worst
    # moment" is not a fault there and this is the number that is.
    racers_enter: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "subject": self.subject,
            "from": round(self.start, 3),
            "to": round(self.end, 3),
            "group_width": round(self.group_width, 4),
            "group_width_range": [round(self.group_width_min, 4), round(self.group_width_max, 4)],
            "racer_pixels": round(self.racer_pixels, 1),
            "phone_pixels": round(self.phone_pixels, 1),
            "racers_in_frame": self.racers_in_frame,
            "min_racers_in_frame": self.min_racers_in_frame,
            "subject_visible": round(self.subject_visible, 3),
            "lead_seconds": None if self.lead_seconds is None else round(self.lead_seconds, 3),
            "racers_enter": None if self.racers_enter is None else round(self.racers_enter, 3),
            "notes": list(self.notes),
        }


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


def _project(point, position, forward, right, up, fov, size):
    """Screen coordinates in [-1, 1], or None if behind the lens."""
    offset = [point[axis] - position[axis] for axis in range(3)]
    depth = sum(offset[axis] * forward[axis] for axis in range(3))
    if depth <= 1e-4:
        return None, 0.0
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * (size[0] / size[1])
    x = sum(offset[axis] * right[axis] for axis in range(3)) / (depth * half_right)
    y = sum(offset[axis] * up[axis] for axis in range(3)) / (depth * half_up)
    return (x, y), depth


def report(
    track: dict[str, Any],
    replay: dict[str, Any],
    course,
    outcome,
    timeline=None,
) -> list[ShotReport]:
    """One row per cut, measured at every frame of it."""
    frames = replay["frames"]
    fps = float(replay.get("replay_fps", 60))
    stations: dict[str, tuple[float, float, float]] = {}
    for module_id in getattr(course, "stations", ()):
        module = course.machine.modules.get(module_id)
        if module is None:
            continue
        bounds = module.bounds()
        stations[module_id] = tuple(
            0.5 * (bounds.lower[axis] + bounds.upper[axis]) * SIM_TO_LAYOUT
            for axis in range(3)
        )
    hits: dict[str, float] = {}
    for event in getattr(timeline, "events", []) or []:
        if event.kind == "mechanism_hit":
            module = event.detail.split(" into ")[-1].split(" ")[0]
            hits.setdefault(module, event.time)

    out: list[ShotReport] = []
    for cut in track.get("cuts", []):
        rows = cut.get("frames", [])
        if not rows:
            continue
        entry = ShotReport(
            name=str(cut.get("name", "")),
            mode=str(cut.get("mode", "")),
            subject=str(cut.get("subject", "")),
            start=float(cut.get("from", rows[0][0])),
            end=float(cut.get("to", rows[-1][0])),
        )
        widths: list[float] = []
        counts: list[int] = []
        pixels: list[float] = []
        entered: float | None = None
        seen_subject = 0
        first_seen: float | None = None

        for row in rows:
            when = float(row[0])
            index = max(0, min(len(frames) - 1, int(round(when * fps))))
            position = (float(row[1]), float(row[2]), float(row[3]))
            aim = (float(row[4]), float(row[5]), float(row[6]))
            fov = float(row[7])
            forward, right, up = _basis(position, aim)

            points = []
            for sample in frames[index]["marbles"]:
                raw = sample["p"] if isinstance(sample, dict) else sample[1]
                points.append(tuple(float(v) * SIM_TO_LAYOUT for v in raw))
            screen: list[tuple[float, float]] = []
            depths: list[float] = []
            for point in points:
                projected, depth = _project(point, position, forward, right, up, fov, DELIVERY)
                if projected is None:
                    continue
                if -1.08 <= projected[0] <= 1.08 and -1.08 <= projected[1] <= 1.08:
                    screen.append(projected)
                    depths.append(depth)
            counts.append(len(screen))
            if entered is None and len(screen) >= MIN_RACERS_IN_FRAME:
                entered = (when - entry.start) / max(entry.end - entry.start, 1e-6)
            if screen:
                # Span of the leading group across the frame, as a fraction of
                # width. Screen x is already normalised to [-1, 1], so a span
                # of 2.0 is the whole frame.
                widths.append((max(x for x, _ in screen) - min(x for x, _ in screen)) / 2.0)
                mean_depth = sum(depths) / len(depths)
                half_up = math.tan(math.radians(fov) * 0.5)
                pixels.append(
                    2.0 * LAYOUT_RADIUS / (mean_depth * half_up) * 0.5 * DELIVERY[1]
                )
            if entry.subject and entry.subject in stations:
                projected, _depth = _project(stations[entry.subject], position,
                                             forward, right, up, fov, DELIVERY)
                if projected and -1.0 <= projected[0] <= 1.0 and -1.0 <= projected[1] <= 1.0:
                    seen_subject += 1
                    if first_seen is None:
                        first_seen = when

        entry.group_width = sum(widths) / len(widths) if widths else 0.0
        entry.group_width_min = min(widths) if widths else 0.0
        entry.group_width_max = max(widths) if widths else 0.0
        entry.racer_pixels = sum(pixels) / len(pixels) if pixels else 0.0
        entry.phone_pixels = entry.racer_pixels * PHONE[1] / DELIVERY[1]
        entry.racers_in_frame = round(sum(counts) / len(counts)) if counts else 0
        entry.min_racers_in_frame = min(counts) if counts else 0
        entry.subject_visible = seen_subject / len(rows) if rows else 0.0
        entry.racers_enter = entered
        contact = hits.get(entry.subject)
        if contact is not None and first_seen is not None:
            entry.lead_seconds = contact - first_seen

        if (
            entry.min_racers_in_frame < MIN_RACERS_IN_FRAME
            and entry.mode not in ("winner_payoff", "obstacle_anticipation")
        ):
            entry.notes.append(
                f"only {entry.min_racers_in_frame} racer(s) in frame at the worst moment"
            )
        if entry.mode == "obstacle_anticipation":
            if entry.racers_enter is None:
                entry.notes.append("the field never entered frame")
            elif entry.racers_enter > 0.70:
                entry.notes.append(
                    f"the field enters {entry.racers_enter * 100:.0f}% of the way through"
                )
        if entry.racer_pixels < MIN_RACER_PIXELS:
            entry.notes.append(f"racers {entry.racer_pixels:.0f} px in a 1080 frame")
        if entry.mode not in ("hook_close", "winner_payoff"):
            if entry.group_width < GROUP_BAND[0]:
                entry.notes.append(
                    f"leading group {entry.group_width * 100:.0f}% of width, under the 25% reference"
                )
            elif entry.group_width > GROUP_BAND[1]:
                entry.notes.append(
                    f"leading group {entry.group_width * 100:.0f}% of width, over the 45% reference"
                )
        if entry.mode == "obstacle_anticipation":
            if entry.subject_visible < 0.75:
                entry.notes.append(
                    f"{entry.subject or 'subject'} in frame only "
                    f"{entry.subject_visible * 100:.0f}% of the shot"
                )
            if entry.lead_seconds is not None and entry.lead_seconds < 0.4:
                entry.notes.append(
                    f"only {entry.lead_seconds:.2f} s of warning before the contact"
                )
        out.append(entry)
    return out


def summary(rows: Sequence[ShotReport]) -> str:
    lines = [
        f"{'shot':<24}{'mode':<22}{'width%':>8}{'px':>6}{'phone':>7}"
        f"{'in frame':>10}{'subj%':>7}{'lead s':>8}{'enter':>7}"
    ]
    lines.append("-" * 92)
    for row in rows:
        lines.append(
            f"{row.name:<24}{row.mode:<22}{row.group_width * 100:7.1f}%"
            f"{row.racer_pixels:6.0f}{row.phone_pixels:7.1f}"
            f"{row.racers_in_frame:6d}/{row.min_racers_in_frame:<3d}"
            f"{row.subject_visible * 100:6.0f}%"
            f"{'' if row.lead_seconds is None else f'{row.lead_seconds:8.2f}'}"
            f"{'' if row.racers_enter is None else f'{row.racers_enter * 100:6.0f}%'}"
        )
    faults = [(row.name, note) for row in rows for note in row.notes]
    if faults:
        lines.append("")
        for name, note in faults:
            lines.append(f"  {name}: {note}")
    else:
        lines.append("\n  no findings")
    return "\n".join(lines)
