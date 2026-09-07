"""Does the replay agree with the course it will be drawn on?

Section 33. `marble3d.contact` does this for the bowl machine and cannot do it
here - its `_CHECKS` table is keyed by module type and knows about dishes,
drains and chutes. This is the same idea against a channel: for every marble in
every sampled frame, find the run and sample it is on, express its centre in
that sample's own rolled frame, and measure how far it is from the section
polyline that frame's collider was swept from.

    clearance = distance from the marble's centre to the section - its radius

Zero is contact. Positive is a marble hovering over the surface it appears to
be running on; negative is a marble inside it. Both are visible in a render and
neither is visible in a run's own summary, which is the whole reason this
exists: a contract can agree with a replay about where the channel is and still
describe a channel that leaves the marbles a radius clear of it.

## Why the section and not the mesh

The collider is a tessellation of the section; the section is the thing the
render is also built from. Measuring against the section therefore measures the
agreement that matters - between the physics and the *drawing* - and it does
not inherit the facet error of either. A marble resting in a facetted cradle
sits up to one sagitta proud of the true arc, 0.02 simulation units at the
core's 4% budget, which is why the resting tolerance below is 0.06 and not
0.01: three sagittas, so a marble in the middle of a facet is not a finding.

## What it does not check

Terrain occlusion, and anything about the modules that are boxes rather than
channels - the start's fan, the merge apron, the finish deck. A marble on those
is reported as `off_channel` with the run it was last on, rather than being
silently measured against a section it is not on. Those regions are 8% of the
route and the stills are the check on them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.units import MARBLE_RADIUS

from sloped.race import ROUTE_RUNS
from sloped.scale import LAYOUT_TO_SIM

__all__ = [
    "PENETRATION_BUDGET",
    "FLOAT_BUDGET",
    "RESTING_SPEED",
    "ContactFinding",
    "ContactReport",
    "check_replay",
]

# A marble is allowed this far inside the section before it is a finding.
# 0.25 of a diameter, the same figure `marble3d.contact` uses, and the run's own
# worst contact penetration is normally a fifth of it.
PENETRATION_BUDGET = 0.25 * 2.0 * MARBLE_RADIUS

# And this far outside it, while resting. Three collider sagittas at the core's
# 4%-of-a-radius budget: a marble sitting in the middle of a facet is up to one
# sagitta proud of the true arc and that is the collider working as designed.
FLOAT_BUDGET = 0.06

# Below this speed a marble is resting and is expected to be in contact. Above
# it a gap is flight, which a marble in a channel with a 34-degree launch does
# legitimately do.
RESTING_SPEED = 3.0

# How far off any centreline a marble has to be before it is treated as being
# on a station - the start fan, the merge apron, the finish deck - rather than
# in a channel. Two diameters: further than any channel is wide.
OFF_CHANNEL = 2.0 * 2.0 * MARBLE_RADIUS


@dataclass
class ContactFinding:
    kind: str
    marble: int
    frame: int
    time: float
    run: str
    sample: int
    value: float
    position: tuple[float, float, float]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "marble": self.marble,
            "frame": self.frame,
            "time": round(self.time, 4),
            "run": self.run,
            "sample": self.sample,
            "value": round(self.value, 5),
            "at": [round(v, 4) for v in self.position],
        }


@dataclass
class ContactReport:
    frames: int = 0
    samples: int = 0
    channel_samples: int = 0
    off_channel_samples: int = 0
    findings: list[ContactFinding] = field(default_factory=list)
    worst_penetration: float = 0.0
    worst_float: float = 0.0

    def ok(self) -> bool:
        return not self.findings

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def to_json(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "samples": self.samples,
            "channel_samples": self.channel_samples,
            "off_channel_samples": self.off_channel_samples,
            "worst_penetration": round(self.worst_penetration, 5),
            "worst_float": round(self.worst_float, 5),
            "penetration_budget": round(PENETRATION_BUDGET, 5),
            "float_budget": FLOAT_BUDGET,
            "by_kind": self.by_kind(),
            "findings": [f.to_json() for f in self.findings[:60]],
            "ok": self.ok(),
        }


def _section_distance(section: Sequence[tuple[float, float]], across: float, up: float) -> float:
    """Distance from a point to a 2D polyline, in the section's own plane."""
    best = math.inf
    for (ax, ay), (bx, by) in zip(section, section[1:]):
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        if length < 1e-15:
            best = min(best, math.hypot(across - ax, up - ay))
            continue
        t = ((across - ax) * dx + (up - ay) * dy) / length
        t = min(1.0, max(0.0, t))
        best = min(best, math.hypot(across - (ax + dx * t), up - (ay + dy * t)))
    return best


def check_replay(
    replay: dict[str, Any],
    machine,
    stride: int = 1,
    radius: float | None = None,
) -> ContactReport:
    """Every marble in every `stride`th frame, against its own channel section."""
    runs = machine.runs
    radius = MARBLE_RADIUS if radius is None else radius
    routes: dict[int, str] = {}
    for event in replay["events"]:
        if event["kind"] == "route":
            routes[int(event["data"]["id"])] = str(event["data"]["route"])

    report = ContactReport()
    where: dict[int, tuple[str, int]] = {}
    window = 18
    frames = replay["frames"]

    for index, frame in enumerate(frames):
        if index % stride:
            continue
        report.frames += 1
        when = float(frame["t"])
        for sample in frame["marbles"]:
            marble_id = int(sample["id"])
            state = str(sample.get("s", "running"))
            if state in ("queued", "escaped", "finished"):
                continue
            report.samples += 1
            position = tuple(float(v) for v in sample["p"])
            speed = math.hypot(*(float(v) for v in sample["v"]))

            names = ROUTE_RUNS[routes.get(marble_id, "blue")]
            previous = where.get(marble_id)
            candidates = [previous[0]] if previous else list(names)
            if previous:
                at = names.index(previous[0])
                if at + 1 < len(names):
                    candidates.append(names[at + 1])
            best: tuple[float, str, int] | None = None
            for name in candidates:
                run = runs[name]
                if previous and previous[0] == name:
                    low = max(0, previous[1] - window)
                    high = min(len(run.sim_path), previous[1] + window + 1)
                else:
                    low, high = 0, min(len(run.sim_path), window + 1)
                for at in range(low, high):
                    point = run.sim_path[at]
                    distance = math.dist(position, point)
                    if best is None or distance < best[0]:
                        best = (distance, name, at)
            if best is None:
                continue
            centre_distance, name, at = best
            where[marble_id] = (name, at)

            if centre_distance > OFF_CHANNEL:
                report.off_channel_samples += 1
                continue
            report.channel_samples += 1

            run = runs[name]
            lateral, up_axis, _forward = run.frames[at]
            centre = run.sim_path[at]
            offset = [position[axis] - centre[axis] for axis in range(3)]
            across = sum(offset[axis] * lateral[axis] for axis in range(3))
            up = sum(offset[axis] * up_axis[axis] for axis in range(3))
            width = run.widths[at]
            # The section is authored in layout units; the offsets above are in
            # simulation units, so it converts here and the width factor is
            # applied to `across` only - exactly as `ring_points` applies it.
            section = [
                (a * width * LAYOUT_TO_SIM, b * LAYOUT_TO_SIM)
                for a, b in run.section_at(at)
            ]
            clearance = _section_distance(section, across, up) - radius

            if clearance < -PENETRATION_BUDGET:
                report.findings.append(
                    ContactFinding("penetration", marble_id, index, when, name, at,
                                   clearance, position)
                )
            elif speed < RESTING_SPEED and clearance > FLOAT_BUDGET:
                report.findings.append(
                    ContactFinding("floating", marble_id, index, when, name, at,
                                   clearance, position)
                )
            report.worst_penetration = min(report.worst_penetration, clearance)
            if speed < RESTING_SPEED:
                report.worst_float = max(report.worst_float, clearance)

    return report
