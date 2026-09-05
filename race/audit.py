"""Static checks on a course, before a single race is run.

Every failure this module looks for cost a batch of races to find the first
time, and each one is invisible in the course description: a respawn point
three pixels inside a peg, a rotor arm that sweeps through a wall, two
shelves whose ends leave a gap exactly one racer wide. The race reports them
as "stuck" or "retired", thousands of ticks after the mistake, and the
geometry that caused it is not obviously wrong when you read it.

So the geometry is measured instead of trusted. Nothing here runs physics -
it is arithmetic on the same `corners()` the solver builds its polygons
from, which is what makes an audit finding a fact about the course rather
than a guess about it.

Five things are checked, and each corresponds to a way a course has actually
broken during this phase:

* **Respawn clearance.** A recovery puts a racer at a checkpoint's respawn
  point. If that point is inside geometry, the racer is stuck again on the
  next tick, and after four tries it is retired. The V0.4 course lost ten
  racers in one seed to a respawn point directly above the peg that had
  stuck them in the first place.

* **Pinch traps.** A gap wider than nothing and narrower than a racer is a
  hole a racer can be driven into and cannot leave. A gap between one and
  two racer diameters is a hopper waiting to arch. Both are found by
  sampling the clear width across the whole course.

* **Rotor sweep against geometry.** A kinematic arm and a static wall do not
  collide - they pass through each other. It is not a crash and nothing
  reports it; it just looks like a bug, forever.

* **Rotor sweep against rotor sweep.** Two rotors whose arms can reach each
  other pass through each other for the same reason.

* **Rotor sweep against walls.** The gap between an arm's tip circle and a
  wall has to be nothing at all, or wider than a racer. Anything between is
  a slot a racer is batted into by every passing arm.

* **Balance points.** A racer in free fall has no sideways velocity, so a
  peg apex directly under a starting slot is a place it can come to rest
  exactly on top of. That is not a theoretical concern: it is what stuck
  the first version of the machine course's opening.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.arena_layout import ObstacleSpec
from race.config import RACER_RADIUS
from race.course import ROLE_GATE, RaceCourse

__all__ = [
    "Finding",
    "audit_course",
    "format_findings",
    "clear_spans",
    "point_clearance",
]

RACER_DIAMETER = RACER_RADIUS * 2.0

# A respawn has to leave this much air around the racer put there.
RESPAWN_MARGIN = 8.0
# A gap narrower than a racer is a trap; one under two diameters plus this
# margin is an arching risk, which the prototype's funnel throat measured
# empirically at 126px against a 60px racer.
ARCH_MARGIN = 6.0
# How finely the course is sampled when looking for pinches.
SCAN_STEP = 20.0
# How near a starting slot's fall line a peg apex may be. Below this a racer
# dropped from the grid can land on top of it and stay there.
BALANCE_MARGIN = 45.0
# Spawn jitter widens the fall line; a racer can start this far either side
# of its slot.
FALL_SPREAD = 24.0
# Narrower than this, the gap between an arm's tip circle and a wall is not
# a slot a racer can be driven into - it is a seal, which is how a tray gate
# shuts a hole without pinching anything against its lip.
TIP_SLOT_MIN = 12.0


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a course, or one thing worth knowing about it."""

    severity: str      # "error" or "warning"
    kind: str
    detail: str
    x: float | None = None
    y: float | None = None

    def __str__(self) -> str:
        where = "" if self.x is None else f"  at ({self.x:.0f}, {self.y:.0f})"
        return f"[{self.severity.upper():7}] {self.kind}: {self.detail}{where}"


# --- geometry helpers -------------------------------------------------------


def _segment_distance(point: tuple[float, float], a: tuple[float, float],
                      b: tuple[float, float]) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= 0.0:
        return math.dist(point, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.dist(point, (ax + t * dx, ay + t * dy))


def _inside_polygon(point: tuple[float, float],
                    corners: tuple[tuple[float, float], ...]) -> bool:
    """Whether a point is inside a convex polygon given in corner order."""
    sign = 0
    for index, corner in enumerate(corners):
        nxt = corners[(index + 1) % len(corners)]
        cross = (nxt[0] - corner[0]) * (point[1] - corner[1]) - (
            nxt[1] - corner[1]
        ) * (point[0] - corner[0])
        if cross == 0.0:
            continue
        step = 1 if cross > 0 else -1
        if sign == 0:
            sign = step
        elif step != sign:
            return False
    return True


def point_clearance(point: tuple[float, float], spec: ObstacleSpec) -> float:
    """Distance from a point to a shape. Negative when the point is inside."""
    if spec.is_circle:
        return math.dist(point, spec.center) - spec.radius
    corners = spec.corners()
    edge = min(
        _segment_distance(point, corners[index], corners[(index + 1) % 4])
        for index in range(4)
    )
    return -edge if _inside_polygon(point, corners) else edge


def _blocking(course: RaceCourse, walls_only: bool = False) -> list[ObstacleSpec]:
    """Every piece a racer cannot pass through once the race is under way.

    The starting gate is excluded: it is removed the moment the countdown
    ends, so treating it as a wall would report the whole start line as one
    enormous pinch. `walls_only` additionally drops the pegs - see
    `clear_spans` for why that is the right reading for arching and the
    wrong one for traps.
    """
    return [
        piece.spec
        for piece in course.pieces
        if piece.role != ROLE_GATE
        and not (walls_only and piece.spec.is_circle)
    ]


def clear_spans(
    course: RaceCourse, y: float, walls_only: bool = False
) -> list[tuple[float, float]]:
    """The open intervals across the course at one height.

    Conservative in exactly one direction: a rotated box is projected onto
    the x axis by its axis-aligned extent, so a steep ramp is reported as
    blocking more than it really does. That is the right way round for a
    trap check - it can call a passage narrower than it is, never wider.

    `walls_only` drops the pegs, which is the right reading for an arching
    check and the wrong one for a trap check. A peg is not a hopper lip: a
    racer goes round one and between two, and counting them would report
    every row of plinko as a throat about to jam. A racer *can* still be
    driven into a gap between a peg and a wall it cannot fit through, so the
    trap sweep keeps them.
    """
    blocked: list[tuple[float, float]] = []
    for spec in _blocking(course, walls_only):
        left, top, right, bottom = spec.bounds()
        if top <= y <= bottom:
            blocked.append((left, right))
    blocked.sort()

    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for left, right in blocked:
        if left > cursor:
            spans.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < course.width:
        spans.append((cursor, course.width))
    return spans


# --- the checks -------------------------------------------------------------


def _check_respawns(course: RaceCourse) -> list[Finding]:
    findings = []
    for checkpoint in course.checkpoints:
        point = checkpoint.respawn
        for spec in _blocking(course):
            clearance = point_clearance(point, spec)
            if clearance < RACER_RADIUS + RESPAWN_MARGIN:
                findings.append(
                    Finding(
                        "error",
                        "respawn blocked",
                        f"{checkpoint.name!r} respawn is {clearance:.0f}px from"
                        f" piece {spec.obstacle_id}"
                        f" (needs {RACER_RADIUS + RESPAWN_MARGIN:.0f})",
                        point[0],
                        point[1],
                    )
                )
        for spinner in course.spinners:
            gap = math.dist(point, spinner.center) - spinner.reach
            if gap < RACER_RADIUS:
                findings.append(
                    Finding(
                        "warning",
                        "respawn in sweep",
                        f"{checkpoint.name!r} respawn is inside spinner"
                        f" {spinner.spinner_id}'s sweep by {-gap:.0f}px",
                        point[0],
                        point[1],
                    )
                )
        if not (course.top <= point[1] <= course.bottom):
            findings.append(
                Finding(
                    "error",
                    "respawn off course",
                    f"{checkpoint.name!r} respawn is outside the course",
                    point[0],
                    point[1],
                )
            )
        if point[1] < checkpoint.y:
            findings.append(
                Finding(
                    "warning",
                    "respawn behind plane",
                    f"{checkpoint.name!r} respawn is above its own plane, so a"
                    " rescued racer has to cross it again",
                    point[0],
                    point[1],
                )
            )
    return findings


def _check_pinches(course: RaceCourse) -> list[Finding]:
    """Find every gap a racer cannot fit through, or can only just.

    Reported once per contiguous stretch rather than once per sample, so a
    300px-tall slot is one finding and not fifteen.
    """
    findings: list[Finding] = []
    open_traps: dict[int, tuple[float, float, float]] = {}
    steps = int((course.bottom - course.top) / SCAN_STEP)

    def close(bucket: dict, severity: str, kind: str, note: str) -> None:
        for _, (top, bottom, worst) in sorted(bucket.items()):
            findings.append(
                Finding(
                    severity,
                    kind,
                    f"{note}: {worst:.0f}px clear over y {top:.0f}-{bottom:.0f}",
                    None,
                    (top + bottom) / 2.0,
                )
            )
        bucket.clear()

    previous: dict[int, tuple[float, float, float]] = {}
    for step in range(steps + 1):
        y = course.top + step * SCAN_STEP
        current: dict[int, tuple[float, float, float]] = {}
        for index, (left, right) in enumerate(clear_spans(course, y)):
            width = right - left
            # A span touching a course edge is the course's own boundary
            # opening, not a passage between two pieces.
            if width <= 0.0 or width >= RACER_DIAMETER:
                continue
            if left <= 1.0 or right >= course.width - 1.0:
                continue
            key = int(round((left + right) / 2.0 / 40.0))
            was = previous.get(key)
            current[key] = (
                was[0] if was else y,
                y,
                min(was[2], width) if was else width,
            )
        finished = {key: value for key, value in previous.items() if key not in current}
        close(finished, "error", "pinch trap", "a racer cannot pass and can be driven in")
        previous = current
    close(previous, "error", "pinch trap", "a racer cannot pass and can be driven in")

    # Arching risk is a separate, softer sweep: gaps a racer fits through but
    # two can bridge.
    previous = {}
    threshold = RACER_DIAMETER * 2.0 + ARCH_MARGIN
    for step in range(steps + 1):
        y = course.top + step * SCAN_STEP
        current = {}
        for left, right in clear_spans(course, y, walls_only=True):
            width = right - left
            if not (RACER_DIAMETER <= width < threshold):
                continue
            if left <= 1.0 or right >= course.width - 1.0:
                continue
            key = int(round((left + right) / 2.0 / 40.0))
            was = previous.get(key)
            current[key] = (
                was[0] if was else y,
                y,
                min(was[2], width) if was else width,
            )
        finished = {key: value for key, value in previous.items() if key not in current}
        close(finished, "warning", "arch risk", "two racers can bridge this")
        previous = current
    close(previous, "warning", "arch risk", "two racers can bridge this")

    del open_traps
    return findings


def _check_spinners(course: RaceCourse) -> list[Finding]:
    findings = []
    for spinner in course.spinners:
        for spec in _blocking(course):
            clearance = point_clearance(spinner.center, spec)
            # A peg near a sweep is not a slot: it is round, it is small, and
            # a racer rolls off it rather than being held against it. The
            # trap this check exists for is a rotor running close to a long
            # flat surface, which is a box.
            if spec.is_circle and clearance >= spinner.reach:
                continue
            if clearance < spinner.reach:
                findings.append(
                    Finding(
                        "error",
                        "arm through geometry",
                        f"spinner {spinner.spinner_id} reaches {spinner.reach:.0f}px"
                        f" but piece {spec.obstacle_id} is {clearance:.0f}px away",
                        spinner.x,
                        spinner.y,
                    )
                )
                continue
            # A slot beside a rotor is worse than no gap at all: a racer
            # driven into it is batted against the wall by every arm. A gap
            # of a few pixels is not that - nothing can get into it - and a
            # tray gate is built out of exactly such a gap, so the check
            # starts where a racer could begin to enter.
            slot = clearance - spinner.reach
            if TIP_SLOT_MIN < slot < RACER_DIAMETER:
                findings.append(
                    Finding(
                        "warning",
                        "rotor slot",
                        f"spinner {spinner.spinner_id} leaves a {slot:.0f}px slot"
                        f" against piece {spec.obstacle_id}",
                        spinner.x,
                        spinner.y,
                    )
                )
    for index, first in enumerate(course.spinners):
        for second in course.spinners[index + 1 :]:
            gap = math.dist(first.center, second.center) - first.reach - second.reach
            if gap < 0.0:
                findings.append(
                    Finding(
                        "error",
                        "arms intersect",
                        f"spinners {first.spinner_id} and {second.spinner_id}"
                        f" overlap by {-gap:.0f}px",
                        first.x,
                        first.y,
                    )
                )
    return findings


def _check_balance_points(course: RaceCourse) -> list[Finding]:
    """Peg apexes a racer can be dropped onto from the starting grid.

    A racer in free fall has no sideways velocity: land it within a few
    pixels of the top of a round peg and it can sit there until the recovery
    net notices. Only the first thing under each slot matters - once a racer
    has touched anything at all it is moving sideways and cannot balance.
    """
    findings = []
    for spawn in course.spawns:
        first = _first_below(course, spawn.x, spawn.y)
        if first is None or not first.is_circle:
            continue
        offset = abs(first.x - spawn.x)
        if offset - FALL_SPREAD >= BALANCE_MARGIN:
            continue
        findings.append(
            Finding(
                "warning",
                "balance point",
                f"slot {spawn.slot} at x={spawn.x:.0f} falls onto peg"
                f" {first.obstacle_id} at x={first.x:.0f}"
                f" ({offset:.0f}px off the apex)",
                first.x,
                first.y,
            )
        )
    return findings


def _first_below(course: RaceCourse, x: float, y: float) -> ObstacleSpec | None:
    """The first piece a racer dropped at `x` from height `y` can touch.

    Only the first one can be a balance point. Once a racer has touched
    anything at all it is moving sideways, and a ball with sideways velocity
    does not come to rest on top of a circle.
    """
    reach = RACER_RADIUS + FALL_SPREAD
    candidates = [
        spec
        for spec in _blocking(course)
        if spec.bounds()[1] > y
        and spec.bounds()[0] - reach <= x <= spec.bounds()[2] + reach
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda spec: spec.bounds()[1])


def audit_course(course: RaceCourse) -> list[Finding]:
    """Every finding for a course, errors first."""
    findings = (
        _check_respawns(course)
        + _check_pinches(course)
        + _check_spinners(course)
        + _check_balance_points(course)
    )
    order = {"error": 0, "warning": 1}
    return sorted(findings, key=lambda finding: (order[finding.severity], finding.kind))


def format_findings(course: RaceCourse, findings: list[Finding]) -> str:
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = len(findings) - errors
    lines = [
        f"=== COURSE AUDIT: {course.course_id} ===",
        f"{len(course.pieces)} pieces, {len(course.spinners)} spinners,"
        f" {len(course.checkpoints)} checkpoints, {len(course.spawns)} spawn slots",
        f"errors {errors}   warnings {warnings}",
    ]
    lines.extend(str(finding) for finding in findings)
    return "\n".join(lines)
