"""Visual contract and measurements for Category 3 Test #2, Phase 2A.

This module is deliberately a *playback consumer*.  It reads the frozen Phase
1 document and projects that document into a 9:16 frame.  It does not import
the simulator, seed generator, evaluator, or collision geometry.  The only
motion it evaluates is the closed-form flight already written into the
document; the only shell geometry it evaluates is ``theta0 + omega * t`` from
the canonical shell records.

The constants here mirror ``godot/scripts/shell_escape_scene.gd``.  Focused
tests parse the GDScript and keep the two consumers locked together.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Iterable, Sequence

from satisfying.shell_playback import panel_closed_at, position_at, region_at
from satisfying.tile_safe_area import DEFAULT_SAFE_AREA, Region, SafeAreaConfig

__all__ = [
    "EXPECTED_DOCUMENT_VERSION",
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_CONFIG_DIGEST",
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "ARENA_WIDTH_FRACTION",
    "ARENA_CENTRE_X_FRACTION",
    "ARENA_CENTRE_Y_FRACTION",
    "BALL_DRAW_SCALE",
    "TRAIL_SECONDS",
    "RELEASE_SECONDS",
    "END_HOLD_SECONDS",
    "RENDER_FPS",
    "REPRESENTATIVE_SEEDS",
    "validate_document",
    "pixels_per_unit",
    "project",
    "panel_segment",
    "panel_visual_state",
    "active_near_misses",
    "representative_moments",
    "safe_area_report",
    "motion_report",
    "candidate_report",
    "render_config",
    "render_config_digest",
]

EXPECTED_DOCUMENT_VERSION = "category3-test2-shell-escape-playback/1.0.0"
EXPECTED_SCHEMA_VERSION = "category3-test2-shell-escape/1.0.0"
EXPECTED_CONFIG_DIGEST = (
    "7da0cbc80d5958260b65417c1ac94fac2285471aaf8adc4f093b27e3445afb3e"
)

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# The Test #1 conservative Shorts rail begins at x=.84.  A .72-wide arena at
# x=.41 occupies x=.05-.77, leaving 75.6 px at 1080p for the release beat and
# action-rail margin.  The outer shell remains 778 px across and the innermost
# shell 169 px across, so frame one still reads as six barriers, not a dot.
ARENA_WIDTH_FRACTION = 0.720
ARENA_CENTRE_X_FRACTION = 0.410
ARENA_CENTRE_Y_FRACTION = 0.500

# Collision geometry remains canonical.  This is only the bright disc drawn
# at the canonical centre, made large enough to survive a phone screen.
BALL_DRAW_SCALE = 1.90
TRAIL_SECONDS = 0.080
TRAIL_SAMPLES = 10

# After the canonical escape event, continue its already-recorded last flight
# for 120 ms, then hold.  Nothing before escape is retimed or redirected.
RELEASE_SECONDS = 0.120
END_HOLD_SECONDS = 0.630
NEAR_MISS_FEEDBACK_SECONDS = 0.130
BREAK_FEEDBACK_SECONDS = 0.180
RENDER_FPS = 60

# Seven representatives from the existing 16-seed Phase 1 shortlist.  They
# cover all requested 20-26 s bands, both final routes, the highest near-miss
# candidate, and the 2/4 mixed progression route.  This is not a production
# selection; Phase 2B still has to evaluate the same cast.
REPRESENTATIVE_SEEDS = (17534, 3654, 6903, 9589, 11929, 7699, 18920)


class VisualDocumentError(ValueError):
    """A playback document is not the frozen contract this renderer reads."""


def validate_document(document: dict[str, Any]) -> None:
    """Refuse a plausible render of a different physics/schema revision."""
    if document.get("document_version") != EXPECTED_DOCUMENT_VERSION:
        raise VisualDocumentError("unexpected playback document version")
    if document.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise VisualDocumentError("unexpected event schema version")
    if document.get("config_digest") != EXPECTED_CONFIG_DIGEST:
        raise VisualDocumentError("unexpected frozen config digest")
    shells = document.get("shells", [])
    if len(shells) != 6 or int(document.get("arena", {}).get("shell_count", -1)) != 6:
        raise VisualDocumentError("the visual proof requires exactly six canonical shells")
    events = document.get("events", [])
    if not events or events[-1].get("kind") != "escape":
        raise VisualDocumentError("the candidate must end in a canonical escape event")
    times = [float(event["t"]) for event in events]
    if times != sorted(times):
        raise VisualDocumentError("canonical events are not time ordered")


def _outer_radius(document: dict[str, Any]) -> float:
    return float(document["shells"][-1]["radius"])


def pixels_per_unit(document: dict[str, Any], width: int = FRAME_WIDTH) -> float:
    validate_document(document)
    return width * ARENA_WIDTH_FRACTION / (2.0 * _outer_radius(document))


def project(
    document: dict[str, Any],
    point: Sequence[float],
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> tuple[float, float]:
    scale = pixels_per_unit(document, width)
    return (
        width * ARENA_CENTRE_X_FRACTION + float(point[0]) * scale,
        height * ARENA_CENTRE_Y_FRACTION - float(point[1]) * scale,
    )


def panel_segment(
    document: dict[str, Any], shell_id: int, panel_id: int, t: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Canonical panel endpoints, using only fields carried by ``shells``."""
    shell = document["shells"][shell_id]
    count = int(shell["panel_count"])
    if not 0 <= panel_id < count:
        raise IndexError((shell_id, panel_id))
    angle = float(shell["theta0"]) + float(shell["omega"]) * t
    step = float(shell["slot_width"])
    radius = float(shell["radius"])
    a0 = angle + panel_id * step
    a1 = angle + (panel_id + 1) * step
    return (
        (radius * math.cos(a0), radius * math.sin(a0)),
        (radius * math.cos(a1), radius * math.sin(a1)),
    )


def _damage_at(document: dict[str, Any], shell_id: int, panel_id: int, t: float) -> float:
    cumulative = 0.0
    threshold = float(document["config"]["break_threshold"])
    for event in document["events"]:
        if float(event["t"]) > t:
            break
        if (
            event["kind"] == "damage"
            and int(event["shell_id"]) == shell_id
            and int(event["panel_id"]) == panel_id
        ):
            cumulative = float(event["cumulative"])
            threshold = float(event["threshold"])
    return cumulative / threshold if threshold > 0.0 else 0.0


def panel_visual_state(
    document: dict[str, Any], shell_id: int, panel_id: int, t: float
) -> str:
    """Map canonical state to one of the four deliberately visible states."""
    shell = document["shells"][shell_id]
    if panel_id in [int(value) for value in shell["open_slots"]]:
        return "opening"
    if not panel_closed_at(document, shell_id, panel_id, t):
        return "broken"
    ratio = _damage_at(document, shell_id, panel_id, t)
    if ratio >= 0.72:
        return "heavily_damaged"
    if ratio >= 0.35:
        return "damaged"
    return "healthy"


def active_near_misses(document: dict[str, Any], t: float) -> list[dict[str, Any]]:
    """Only canonical near-miss events may trigger the post flash/spark."""
    return [
        event
        for event in document["events"]
        if event["kind"] == "near_miss"
        and 0.0 <= t - float(event["t"]) <= NEAR_MISS_FEEDBACK_SECONDS
    ]


def _first(
    events: Iterable[dict[str, Any]], predicate: Any, default: float
) -> float:
    for event in events:
        if predicate(event):
            return float(event["t"])
    return default


def representative_moments(document: dict[str, Any]) -> list[tuple[str, float]]:
    """Seven brief-mandated proof instants, derived from canonical events."""
    validate_document(document)
    events = document["events"]
    duration = float(document["summary"]["duration"])
    first_hit = _first(events, lambda e: e["kind"] == "collision", 0.25)
    near = _first(events, lambda e: e["kind"] == "near_miss", first_hit)
    panel_break = _first(events, lambda e: e["kind"] == "panel_break", duration * 0.4)
    middle = _first(
        events,
        lambda e: e["kind"] == "shell_exit" and int(e["to_region"]) >= 3,
        duration * 0.55,
    )
    outer = _first(
        events,
        lambda e: int(e.get("shell_id", -1)) == 5
        and e["kind"] in ("collision", "near_miss", "shell_exit"),
        duration * 0.82,
    )
    return [
        ("a_opening", 0.0),
        ("b_first_shell", min(duration, first_hit + 0.025)),
        ("c_near_miss", min(duration, near + 0.035)),
        ("d_panel_break", min(duration, panel_break + 0.045)),
        ("e_middle_progress", min(duration, middle + 0.080)),
        ("f_outer_sequence", min(duration, outer + 0.060)),
        ("g_final_escape", duration + RELEASE_SECONDS),
    ]


def _circle_region_fraction(
    x: float, y: float, radius: float, region: Region, width: int, height: int
) -> float:
    """Conservative overlap test (1 for any overlap, 0 for clear)."""
    left, top, right, bottom = region.rect(width, height)
    nearest_x = min(max(x, left), right)
    nearest_y = min(max(y, top), bottom)
    return 1.0 if math.hypot(x - nearest_x, y - nearest_y) < radius else 0.0


def _rect_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    horizontal = max(b[0] - a[2], a[0] - b[2], 0.0)
    vertical = max(b[1] - a[3], a[1] - b[3], 0.0)
    if horizontal > 0.0 or vertical > 0.0:
        return math.hypot(horizontal, vertical)
    return -min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])


def safe_area_report(
    document: dict[str, Any],
    config: SafeAreaConfig = DEFAULT_SAFE_AREA,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> dict[str, Any]:
    """Measure every brief-named critical target against Shorts controls."""
    validate_document(document)
    scale = pixels_per_unit(document, width)
    radius_px = _outer_radius(document) * scale
    cx = width * ARENA_CENTRE_X_FRACTION
    cy = height * ARENA_CENTRE_Y_FRACTION
    outer_box = (cx - radius_px, cy - radius_px, cx + radius_px, cy + radius_px)
    hook_box = (0.06 * width, 0.078 * height, 0.79 * width, 0.135 * height)
    regions = {region.name: region.rect(width, height) for region in config.regions}

    outer_clearance = min(_rect_gap(outer_box, rect) for rect in regions.values())
    hook_clearance = min(_rect_gap(hook_box, rect) for rect in regions.values())

    ball_draw_radius = float(document["arena"]["ball_radius"]) * BALL_DRAW_SCALE * scale
    duration = float(document["summary"]["duration"])
    end = duration + RELEASE_SECONDS
    frames = int(math.ceil(end * config.fps)) + 1
    ball_hidden = 0
    longest = 0
    run = 0
    min_ball_clearance = math.inf
    for frame in range(frames):
        t = min(frame / config.fps, end)
        x, y = project(document, position_at(document, t), width, height)
        overlaps = [
            _circle_region_fraction(x, y, ball_draw_radius, region, width, height)
            for region in config.regions
        ]
        hidden = any(value > 0.0 for value in overlaps)
        if hidden:
            ball_hidden += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        ball_box = (x - ball_draw_radius, y - ball_draw_radius,
                    x + ball_draw_radius, y + ball_draw_radius)
        min_ball_clearance = min(
            min_ball_clearance,
            min(_rect_gap(ball_box, rect) for rect in regions.values()),
        )

    # Every opening lies on or inside its shell's vertex circle.  Prove it at
    # every still instant anyway, so a future composition change cannot hide a
    # gap while leaving only the bounding circle nominally clear.
    opening_clear = True
    opening_min_clearance = math.inf
    for _, t in representative_moments(document):
        draw_t = min(t, duration + RELEASE_SECONDS)
        for shell in document["shells"]:
            sid = int(shell["shell_id"])
            for slot in shell["open_slots"]:
                p0, p1 = panel_segment(document, sid, int(slot), draw_t)
                midpoint = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
                x, y = project(document, midpoint, width, height)
                marker = max(3.0, 0.5 * float(shell["gap_chord"])
                             * scale) if "gap_chord" in shell else 4.0
                box = (x - marker, y - marker, x + marker, y + marker)
                clearance = min(_rect_gap(box, rect) for rect in regions.values())
                opening_min_clearance = min(opening_min_clearance, clearance)
                opening_clear = opening_clear and clearance >= 0.0

    final_t = duration + RELEASE_SECONDS
    final_x, final_y = project(document, position_at(document, final_t), width, height)
    final_box = (
        final_x - ball_draw_radius,
        final_y - ball_draw_radius,
        final_x + ball_draw_radius,
        final_y + ball_draw_radius,
    )
    final_clearance = min(_rect_gap(final_box, rect) for rect in regions.values())
    gate_pass = (
        outer_clearance >= 0.0
        and hook_clearance >= 0.0
        and ball_hidden == 0
        and opening_clear
        and final_clearance >= 0.0
    )
    return {
        "safe_area": config.name,
        "safe_area_fingerprint": config.fingerprint(),
        "frame": [width, height],
        "arena_box_px": [round(value, 3) for value in outer_box],
        "arena_occupancy_width_pct": round(100.0 * (2.0 * radius_px) / width, 3),
        "outer_shell_clearance_px": round(outer_clearance, 3),
        "hook_clearance_px": round(hook_clearance, 3),
        "openings_clear": opening_clear,
        "openings_min_clearance_px": round(opening_min_clearance, 3),
        "ball_frames": frames,
        "ball_hidden_frames": ball_hidden,
        "ball_longest_hidden_seconds": round(longest / config.fps, 4),
        "ball_min_clearance_px": round(min_ball_clearance, 3),
        "final_escape_clearance_px": round(final_clearance, 3),
        "gate_pass": gate_pass,
        "regions": {name: [round(value, 3) for value in rect]
                    for name, rect in regions.items()},
    }


def motion_report(
    document: dict[str, Any], width: int = FRAME_WIDTH, fps: int = RENDER_FPS
) -> dict[str, Any]:
    """Apparent size, travel and temporal continuity at an output rate."""
    validate_document(document)
    scale = pixels_per_unit(document, width)
    speed = float(document["config"]["speed"])
    collision_diameter = 2.0 * float(document["arena"]["ball_radius"]) * scale
    draw_diameter = collision_diameter * BALL_DRAW_SCALE
    travel = speed * scale / fps
    trail = speed * scale * TRAIL_SECONDS
    shell = document["shells"][0]
    inner_gap = min(float(opening["gap_chord"]) for opening in shell["openings"]) * scale
    outer_gap = min(float(opening["gap_chord"])
                    for opening in document["shells"][-1]["openings"]) * scale
    return {
        "fps": fps,
        "pixels_per_world_unit": round(scale, 4),
        "outer_shell_diameter_px": round(2.0 * _outer_radius(document) * scale, 3),
        "inner_shell_diameter_px": round(2.0 * float(shell["radius"]) * scale, 3),
        "collision_ball_diameter_px": round(collision_diameter, 3),
        "drawn_ball_diameter_px": round(draw_diameter, 3),
        "frame_travel_px": round(travel, 3),
        "frame_travel_ball_diameters": round(travel / draw_diameter, 4),
        "trail_length_px": round(trail, 3),
        "trail_covers_frame_step": trail + draw_diameter >= travel,
        "inner_opening_px": round(inner_gap, 3),
        "outer_opening_px": round(outer_gap, 3),
        "smallest_panel_stroke_px": 6.0,
        "largest_panel_stroke_px": 11.0,
    }


def _event_count(document: dict[str, Any], kind: str) -> int:
    return sum(event["kind"] == kind for event in document["events"])


def candidate_report(document: dict[str, Any]) -> dict[str, Any]:
    validate_document(document)
    escape = document["events"][-1]
    # Count the six first-time outward frontier crossings, not later exits from
    # regions the ball has already reached after falling inward.  This is the
    # Phase 1 shortlist's Open/Break progression definition.
    progression: list[dict[str, Any]] = []
    max_region = 0
    for event in document["events"]:
        if event["kind"] != "shell_exit":
            continue
        to_region = int(event["to_region"])
        if to_region > max_region:
            progression.append(event)
            max_region = to_region
    opening_progress = sum(event["method"] == "opening" for event in progression)
    break_progress = sum(event["method"] == "break" for event in progression)
    return {
        "seed": int(document["seed"]),
        "duration": round(float(document["summary"]["duration"]), 4),
        "digest": str(document["digest"]),
        "final_method": str(escape["method"]),
        "collisions": _event_count(document, "collision"),
        "near_misses": _event_count(document, "near_miss"),
        "breaks": _event_count(document, "panel_break"),
        "opening_progressions": opening_progress,
        "break_progressions": break_progress,
        "safe_area": safe_area_report(document),
        "motion_30fps": motion_report(document, fps=30),
        "motion_60fps": motion_report(document, fps=60),
        "moments": [{"name": name, "t": round(t, 6)}
                    for name, t in representative_moments(document)],
    }


def render_config() -> dict[str, Any]:
    return {
        "format": "category3-shell-visual-render/1.0.0",
        "frame": [FRAME_WIDTH, FRAME_HEIGHT],
        "fps": RENDER_FPS,
        "arena_width_fraction": ARENA_WIDTH_FRACTION,
        "arena_centre": [ARENA_CENTRE_X_FRACTION, ARENA_CENTRE_Y_FRACTION],
        "ball_draw_scale": BALL_DRAW_SCALE,
        "trail_seconds": TRAIL_SECONDS,
        "trail_samples": TRAIL_SAMPLES,
        "release_seconds": RELEASE_SECONDS,
        "end_hold_seconds": END_HOLD_SECONDS,
        "near_miss_feedback_seconds": NEAR_MISS_FEEDBACK_SECONDS,
        "break_feedback_seconds": BREAK_FEEDBACK_SECONDS,
        "safe_area_fingerprint": DEFAULT_SAFE_AREA.fingerprint(),
        "deterministic_clock": "frame_index/fps",
        "hook": "CAN THE BALL ESCAPE?",
        "audio": False,
    }


def render_config_digest() -> str:
    blob = json.dumps(render_config(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_document(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    validate_document(document)
    return document
