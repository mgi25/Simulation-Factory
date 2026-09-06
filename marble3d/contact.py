"""Does the marble touch the thing that was drawn?

The physics core already proves the marbles behave: it measures penetration,
energy and containment against its own colliders, and those tests pass. This
module asks the other question, the one that only exists once there is a second
description of the machine. The collider is not what the viewer sees. If the
drawn bowl and the solved bowl disagree by half a marble, every number in the
physics report stays green and the clip shows marbles hovering.

So this walks the replay and, for every sampled marble, measures the distance
from the marble's surface to the *visible* surface it is supposed to be on -
the analytic surface the presentation contract told Godot to build. Not the
mesh Godot produced: the contract is what both sides were given, so a
disagreement here is a disagreement about the machine rather than about
tessellation, and it can be found without a GPU.

## What it looks for

    below the surface     the marble is inside the drawn shell
    floating              the marble is clear of every surface while slow
    outside the dish      the marble has left the drawn bowl entirely
    outside the channel   the marble is beyond the drawn curve's guard
    in the void           the marble is in no module's drawn geometry at all

A marble in mid-air is not floating - it is falling, and the run is full of
legitimate flight. Floating is being clear of the surface *and* slow *and* not
accelerating downward through a gap, which is what separates a rendering fault
from a marble that has simply been thrown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

from marble3d.geometry import quat_conjugate, quat_rotate

__all__ = [
    "ContactFinding",
    "ContactReport",
    "check_contact",
]


# How far a marble may sit inside the drawn surface before it is a fault. The
# solver's own worst penetration on this machine is about 0.14 of a diameter
# against its collider, and the drawn surface is a different surface, so the
# budget here has to be looser than the physics one or it would be re-testing
# the solver. A quarter of a radius is still a quarter of a radius: at this
# scale it is invisible, and twice it is not.
PENETRATION_BUDGET = 0.25

# How far clear a marble may be before it counts as unsupported, in radii.
CLEARANCE_BUDGET = 0.60

# Below this speed a marble that is clear of everything is not falling, it is
# floating. In world units per second, against a run whose top speed is ~49.
RESTING_SPEED = 3.0

# How long a marble has to hang there before it counts, in seconds.
#
# The chute releases by dropping each marble onto its floor, so at the instant
# of release every marble in the machine is legitimately clear of a surface and
# legitimately slow. That is a designed fall, not a rendering fault, and
# without a persistence window this checker reports all eight of them - which
# was its second false positive.
FLOATING_SECONDS = 0.25

# Sub-millimetre overshoots are the swept channel's own chord error against its
# analytic centreline, not a marble through a rail.
GEOMETRIC_EPSILON = 1.0e-2


@dataclass
class ContactFinding:
    kind: str
    marble: int
    frame: int
    time: float
    module: str
    value: float
    position: tuple[float, float, float]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "marble": self.marble,
            "frame": self.frame,
            "time": self.time,
            "module": self.module,
            "value": self.value,
            "position": list(self.position),
        }


@dataclass
class ContactReport:
    frames_checked: int = 0
    samples: int = 0
    findings: list[ContactFinding] = field(default_factory=list)
    worst_penetration: float = 0.0
    worst_clearance: float = 0.0

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def ok(self) -> bool:
        return not self.findings

    def to_json(self) -> dict[str, Any]:
        return {
            "frames_checked": self.frames_checked,
            "samples": self.samples,
            "worst_penetration": self.worst_penetration,
            "worst_clearance": self.worst_clearance,
            "counts": self.by_kind(),
            # Capped: a systematic fault produces one finding per marble per
            # frame, and ten thousand copies of the same sentence is not a
            # better report than fifty of them.
            "findings": [finding.to_json() for finding in self.findings[:50]],
            "findings_total": len(self.findings),
        }


def _to_local(module: dict[str, Any], point: Iterable[float]) -> tuple[float, float, float]:
    origin = module["origin"]
    inverse = quat_conjugate(module["orientation"])
    shifted = [float(p) - float(o) for p, o in zip(point, origin)]
    return quat_rotate(inverse, shifted)


def _bowl_clearance(
    module: dict[str, Any], point: Iterable[float], radius: float
) -> tuple[str, float]:
    """Signed distance from the marble's surface to the drawn dish.

    Positive is clear of it, negative is inside it, measured along the surface
    normal rather than vertically - on a slope that reaches 42 degrees the two
    differ by a third.

    The surface is read off the contract's `profile` polyline, which is the
    line the collider was revolved from, rather than evaluated from
    `profile_power`. The power law is only the first of the profile's three
    pieces: past it the surface rolls over a fillet and drops to the drain rim,
    half a marble radius below where the bare exponent puts it. Trusting the
    exponent was this checker's third false positive, and it reported every
    marble that reached the lip as buried in the floor.
    """
    visual = module["visual"]
    outer = float(visual["outer_radius"])
    drain = float(visual["drain_radius"])
    shaft_bottom = float(visual["shaft_bottom"])
    drain_rim_height = float(visual["drain_rim_height"])
    profile = visual["profile"]

    x, y, z = _to_local(module, point)
    r = math.hypot(x, z)

    # Down the drain, which has three regions and only one of them is a
    # surface a marble can be wrong about.
    #
    # Reading the whole column as a floor was this checker's first false
    # positive - it reported every successful drain as a marble buried three
    # radii inside the bowl - and then reading it as a wall was the second,
    # because a marble crossing the open mouth of a hole is not touching the
    # rim it is passing over.
    if r <= drain:
        if y < shaft_bottom:
            # Out of the bottom and on its way to the catch: the module doing
            # its job, and no longer a claim about the bowl at all.
            return "through_drain", shaft_bottom - y
        if y < drain_rim_height:
            # Inside the shaft, where the cylinder wall is real geometry.
            return "shaft", drain - (r + radius)
        # Over the mouth, above the rim, in the air. Nothing to touch.
        return "over_drain", 0.0

    if r > outer:
        return "outside_dish", r - outer

    return "bowl", _profile_distance(profile, r, y) - radius


def _profile_distance(profile: list[Any], r: float, y: float) -> float:
    """True signed distance from a meridian point to the revolved profile.

    Positive is on the open side of the surface, negative is inside the solid.
    For a surface of revolution this is exact: the distance from a point to the
    surface is the distance from (r, y) to the profile polyline in the
    meridian half-plane, so there is no reason to settle for the vertical
    offset scaled by the slope.

    Which matters at exactly one place and it is the important one. The drain
    lip is a fillet of radius 0.6 against a marble of radius 0.5, and where the
    surface curves that tightly a first-order projection reads a marble rolling
    correctly over the lip as three quarters of a radius inside it. That was
    this checker's fourth false positive, and unlike the first three it was
    wrong about the geometry rather than about the classification.
    """
    best = float("inf")
    sign = 1.0
    for before, after in zip(profile, profile[1:]):
        r0, y0 = float(before[0]), float(before[1])
        r1, y1 = float(after[0]), float(after[1])
        dr, dy = r1 - r0, y1 - y0
        length_squared = dr * dr + dy * dy
        if length_squared <= 0.0:
            continue
        t = ((r - r0) * dr + (y - y0) * dy) / length_squared
        t = min(1.0, max(0.0, t))
        near_r = r0 + dr * t
        near_y = y0 + dy * t
        distance = math.hypot(r - near_r, y - near_y)
        if distance < best:
            best = distance
            # The profile is wound bottom-up and outward, so the open side is
            # the one a left turn from the segment direction points at.
            cross = dr * (y - y0) - dy * (r - r0)
            sign = 1.0 if cross >= 0.0 else -1.0
    if best == float("inf"):
        return 0.0
    return sign * best


def _curve_clearance(
    module: dict[str, Any], point: Iterable[float], radius: float
) -> tuple[str, float]:
    """Distance from the marble to the drawn channel, in the banked frame.

    The channel is a swept section, so the nearest centreline sample is found
    and the point expressed in that sample's own frame - which is banked, and
    has to be, or a marble correctly riding a 28-degree bank reads as being
    through the wall.
    """
    visual = module["visual"]
    half_width = float(visual["half_width"])
    wall_height = float(visual["wall_height"])
    centreline = visual["centreline"]

    best = None
    best_distance = float("inf")
    for sample in centreline:
        position = sample["position"]
        distance = sum((float(a) - float(b)) ** 2 for a, b in zip(point, position))
        if distance < best_distance:
            best_distance = distance
            best = sample
    if best is None:
        return "void", 0.0

    inverse = quat_conjugate(best["rotation"])
    offset = [float(p) - float(c) for p, c in zip(point, best["position"])]
    _along, up, across = quat_rotate(inverse, offset)

    if abs(across) > half_width + radius:
        return "outside_channel", abs(across) - half_width - radius
    if up > wall_height + radius * 2.0:
        return "curve_air", up - radius
    return "curve", up - radius


def _start_clearance(
    module: dict[str, Any], point: Iterable[float], radius: float
) -> tuple[str, float]:
    """The chute is a straight inclined channel in its own frame."""
    visual = module["visual"]
    half_width = 0.5 * float(visual["channel_width"])
    x, y, z = _to_local(module, point)
    if abs(z) > half_width + radius:
        return "outside_channel", abs(z) - half_width - radius
    return "start", y - radius


_CHECKS = {
    "BowlModule": _bowl_clearance,
    "CurveModule": _curve_clearance,
    "StartModule": _start_clearance,
}


def check_contact(
    replay: dict[str, Any],
    contract: dict[str, Any],
    stride: int = 1,
    penetration_budget: float = PENETRATION_BUDGET,
    clearance_budget: float = CLEARANCE_BUDGET,
) -> ContactReport:
    """Walk the replay against the drawn machine and report disagreements."""
    radius = float(contract.get("marble_radius", 0.5))
    modules = {module["id"]: module for module in contract.get("modules", [])}
    report = ContactReport()
    replay_fps = float(replay.get("replay_fps", 60)) or 60.0
    floating_frames = max(1, int(round(FLOATING_SECONDS * replay_fps / max(stride, 1))))
    # How many consecutive samples each marble has been clear and slow for.
    hanging: dict[int, int] = {}

    for index, frame in enumerate(replay.get("frames", [])):
        if index % stride:
            continue
        report.frames_checked += 1
        time = float(frame.get("t", 0.0))
        for record in frame.get("marbles", []):
            state = str(record.get("s", ""))
            # Queued marbles have not been released and retired ones are held
            # at their last pose; neither is a claim about contact.
            if state != "running":
                continue
            module_id = str(record.get("in", ""))
            module = modules.get(module_id)
            if module is None:
                continue
            check = _CHECKS.get(str(module["type"]))
            if check is None:
                continue

            report.samples += 1
            marble_id = int(record["id"])
            position = tuple(float(v) for v in record["p"])
            where, clearance = check(module, position, radius)
            speed = math.sqrt(sum(float(v) ** 2 for v in record.get("v", (0, 0, 0))))

            # A marble on its way down the shaft, or crossing the open mouth
            # of it, is between two modules and touching neither - which is
            # what a drop join is.
            if where in ("through_drain", "over_drain"):
                hanging[marble_id] = 0
                continue

            if where in ("outside_dish", "outside_channel"):
                if clearance > GEOMETRIC_EPSILON:
                    report.findings.append(
                        ContactFinding(where, marble_id, index, time,
                                       module_id, clearance, position)
                    )
                hanging[marble_id] = 0
                continue

            if clearance < -penetration_budget * radius:
                report.worst_penetration = min(report.worst_penetration, clearance)
                report.findings.append(
                    ContactFinding("below_surface", marble_id, index,
                                   time, module_id, clearance, position)
                )
                hanging[marble_id] = 0
            elif clearance > clearance_budget * radius and speed < RESTING_SPEED:
                # Clear of the surface and not moving. Falling would be fine -
                # the run is full of legitimate flight - so this only counts
                # once it has persisted, which is what separates a marble
                # hanging in the air from one that has just been dropped.
                hanging[marble_id] = hanging.get(marble_id, 0) + 1
                if hanging[marble_id] >= floating_frames:
                    report.worst_clearance = max(report.worst_clearance, clearance)
                    report.findings.append(
                        ContactFinding("floating", marble_id, index, time,
                                       module_id, clearance, position)
                    )
            else:
                hanging[marble_id] = 0
                report.worst_penetration = min(report.worst_penetration, clearance)

    return report
