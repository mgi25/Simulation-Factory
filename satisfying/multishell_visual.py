"""Category 3, Test #2 redesign - the PREMIUM visual contract, Phase 2A.

This module is a **playback consumer and nothing else**. It reads the canonical
V2 document written by `satisfying.multishell_playback` and turns it into the
numbers a renderer needs: where the camera is, how big a thing is in pixels,
what colour a ball's family is, which of the five damage states a panel is in.
It never imports `satisfying.multishell`, never integrates, never resolves a
contact, and never touches a seed. The one rule the Phase 1 document states -

    a consumer of this document may read a trajectory and may not compute one

- is the reason this file exists at the same time as `multishell_scene.gd`:
every constant the scene draws with is declared here, a test parses the
GDScript and compares the two, and a measurement printed in the report is
therefore a measurement of the render that was actually made.

## Why the previous visual language was thrown away

The single-ball Phase 2A drew the arena with `draw_line` on a `Node2D`: five
concentric polylines six to eleven pixels wide, a 1.9x ball on a 0.72-wide
frame, damage as a recolour of the whole panel and a break as a panel that
stopped being drawn. Every complaint in the rejection is a direct consequence
of that choice, and none of them is fixable by picking better colours. So the
geometry is rebuilt as real material: chamfered slabs with depth, pillars at
the vertices, cracks that start where the ball actually hit, and a break that
fractures and retracts instead of vanishing.

## The one composition problem, stated as arithmetic

The arena is 49.1 world units across and the ball is 0.8 units across. The ball
is **1.6% of the arena's width**, and no choice of frame, palette or material
changes that ratio. At the largest framing the Shorts safe area permits - the
disc has to clear the action rail at x=0.840 and the title block at y=0.840, so
it caps at 0.834 of the frame width - a full-arena camera puts the ball at
**15 px across on a 1080 px frame**. Frame one of a fixed full-arena camera is
a speck in the middle of five rings, which is exactly what was rejected.

The answer is not a bigger ball. Drawing the ball past 1.375x its true radius
makes it overlap a panel it is only touching, and the rejected version's 1.9x
already did. The answer is that **the camera frames the frontier, not the
arena**: at t=0 it frames shell 0, and each time the canonical high-water
frontier advances a region it opens out one shell. At the opening the ball is
83 px across and shell 0's openings are 367 px wide; by the climax the camera
has settled on the whole arena and stays there for the last seven to nine
seconds without moving at all.

That schedule is a pure function of the document - `frame_marks` reads the
`shell_exit` stream and nothing else - it is monotone by construction, and it
is the escalation: the world the viewer is looking at gets bigger because the
balls got further, and it gets bigger exactly when they do.

## Depth, and why the camera is perspective

A wall 0.30 units thick is 5.3 px at the final framing. Nothing drawn inside
the canonical silhouette can be made to look massive at 5.3 px, so the mass
comes from **behind** it: each panel is extruded backwards, away from the
camera, and a perspective camera sees the receding flank. A point at `z = -d`
and radius `r` projects to radius `r*D/(D+d)`, which is *inside* the panel's
front face, so a flank never covers a ball - every ball is at `z = 0`, in front
of every flank. The flank is `r*d/(D+d)` wide, which at the final framing is
18.9 px for the outermost shell and 1.3 px for the innermost - fourteen times
the flank, and 3.6 times the whole wall once the 5.3 px face is counted in.
The outer wall looks like the hardest barrier because it is drawn with that
much more material, and the depth ramp is the only place the difference comes
from.

Everything the physics cares about is at `z = 0`, and a perspective camera
looking down `-Z` projects that plane by an exact uniform scale. The earlier
camera achieved the safe-area offset by translating its eye sideways. Because
the five slabs have different extrusion depths, that introduced depth-dependent
parallax and made their rear rims appear to have different centres. Phase 3B
keeps the eye on the invariant world origin and uses an asymmetric frustum to
place that origin at the same safe-area point. Scale can change, but the
principal point cannot drift with depth.

## The candidate set

Sixteen successful seeds were taken from the new 20,000-seed run. A measured
screen rejected three severe visual piles, leaving thirteen engineering
survivors. `CANDIDATE_RULE` and the committed shortlist record the six rendered
review candidates and why they span the desired routes and cooperative damage.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Sequence

from satisfying.multishell_playback import panel_state_at, position_at
from satisfying.tile_safe_area import DEFAULT_SAFE_AREA, Region, SafeAreaConfig

__all__ = [
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_CONFIG_DIGEST",
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "VIEW_DIAMETER_FRACTION",
    "ARENA_CENTRE_X_FRACTION",
    "ARENA_CENTRE_Y_FRACTION",
    "VIEW_RADIUS_PAD",
    "CAMERA_HFOV_DEGREES",
    "CAMERA_NEAR",
    "CAMERA_FRUSTUM_SIZE",
    "CAMERA_FRUSTUM_OFFSET",
    "FRAME_LEAD_SECONDS",
    "FRAME_EASE_SECONDS",
    "BALL_DRAW_SCALE",
    "HALO_SCALE",
    "BALL_RIM_SCALE",
    "TRAIL_SECONDS",
    "TRAIL_SAMPLES",
    "PANEL_DEPTH",
    "POST_DEPTH_FACTOR",
    "PANEL_CHAMFER",
    "DAMAGE_STATES",
    "CANDIDATE_RULE",
    "CANDIDATE_SEEDS",
    "validate_document",
    "frame_marks",
    "view_radius_at",
    "pixels_per_unit",
    "camera_distance",
    "flank_width",
    "project",
    "project_3d",
    "projected_shell_centres",
    "centre_alignment_report",
    "alignment_moments",
    "lineage_palette",
    "shell_geometry_report",
    "composition_report",
    "safe_area_report",
    "readability_report",
    "damage_report",
    "event_moments",
    "measure_document",
    "candidate_seeds",
    "candidate_manifest",
    "render_config",
    "render_config_digest",
]

# --------------------------------------------------------------------------
# What this consumer will read, and refuses to read
# --------------------------------------------------------------------------

EXPECTED_SCHEMA_VERSION = "category3-test2-multiplying-shell/2.0.0"
# The frozen Phase 1 operating configuration. A document from any other config
# renders a plausible video of a different simulation, which is worse than an
# error, so this is checked rather than trusted.
EXPECTED_CONFIG_DIGEST = (
    "1803a066cc67ed08088294e64dd42b7264e2bcc210f055ab225d9983e2725d38"
)
EXPECTED_SHELL_COUNT = 5

DAMAGE_STATES: tuple[str, ...] = (
    "healthy", "damaged", "critical", "fractured", "broken",
)

# --------------------------------------------------------------------------
# Frame and composition
# --------------------------------------------------------------------------

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# The framed disc's diameter as a fraction of the frame width. Derived, not
# chosen: the conservative Shorts action rail starts at x=0.840 and the title
# block at y=0.840, so the largest disc that clears both is centred at x=0.420
# with a radius of 0.420 of the frame width. 0.834 with a 0.85-unit pad leaves
# the outermost shell's material 18.4 px clear of the rail on the right and of
# the frame edge on the left. `safe_area_report` measures it rather than
# asserting it.
VIEW_DIAMETER_FRACTION = 0.834
ARENA_CENTRE_X_FRACTION = 0.420
# 0.440 rather than 0.500: the disc has to clear the top bar at y=0.060 and the
# title block at y=0.840, and sitting slightly above the frame's middle leaves
# the larger of the two bands at the bottom, where the escapee's run-out and
# the player's own title block both live.
ARENA_CENTRE_Y_FRACTION = 0.440
# World units of clear space beyond the framed shell's outer material edge.
VIEW_RADIUS_PAD = 0.85

# Horizontal field of view. `Camera3D.keep_aspect = KEEP_WIDTH` makes `fov` the
# horizontal angle, so this and VIEW_DIAMETER_FRACTION together fix the camera
# distance at every framing - see `camera_distance`. 47 degrees puts the
# outermost shell 19.2 degrees off axis at the final framing, which is what
# makes its 3.2-unit flank 18.9 px wide.
CAMERA_HFOV_DEGREES = 47.0
CAMERA_NEAR = 0.20
# An asymmetric perspective frustum keeps the camera itself on the canonical
# world centre.  The offset moves the principal point to the Shorts-safe
# composition point without introducing the depth-dependent parallax caused by
# translating the camera laterally.
CAMERA_FRUSTUM_SIZE = (
    2.0
    * CAMERA_NEAR
    * math.tan(math.radians(CAMERA_HFOV_DEGREES) * 0.5)
    * FRAME_HEIGHT
    / FRAME_WIDTH
)
CAMERA_FRUSTUM_OFFSET = (
    (0.5 - ARENA_CENTRE_X_FRACTION)
    * CAMERA_FRUSTUM_SIZE
    * FRAME_WIDTH
    / FRAME_HEIGHT,
    (ARENA_CENTRE_Y_FRACTION - 0.5) * CAMERA_FRUSTUM_SIZE,
)

# The framing opens this long before the canonical crossing that triggers it,
# so the frame is already moving as the ball goes through rather than reacting
# after it.
FRAME_LEAD_SECONDS = 0.12
FRAME_EASE_SECONDS = 0.55

# --------------------------------------------------------------------------
# Balls
# --------------------------------------------------------------------------

# A ball touching a panel has its centre 0.55 units from the chord axis
# (0.40 radius + 0.15 half-thickness), so 1.375 is the largest scale that never
# draws the ball inside a panel it is only touching. 1.50 overlaps by 0.05
# units - 3.2 px at the opening framing, 0.9 px at the final one - which is
# below the bloom's own falloff and reads as contact rather than penetration.
BALL_DRAW_SCALE = 1.50
# The additive halo billboard, as a multiple of the drawn core radius. This is
# where the apparent size comes from at the final framing, and it is light
# rather than material: a halo over a panel reads as spill, not as a ball
# inside the wall.
HALO_SCALE = 2.60
# A near-black disc behind each core, slightly larger than it, drawn at a small
# negative z so a core always wins the depth test against another ball's rim.
# Seven balls inside two drawn diameters happens - seed 7183 at 15.6 s - and
# seven overlapping bright discs with no rims are one blob, while seven with
# rims are still seven.
BALL_RIM_SCALE = 1.24
# The presentation layers sit just *in front* of the play plane so they read
# over a panel instead of being occluded by one. The core sphere - the
# canonical position - is at z = 0 exactly.
BALL_RIM_Z = 0.02
TRAIL_Z = 0.06
HALO_Z = 0.12
EFFECT_Z = 0.16
# A time window, not a frame count, so the trail is identical at any rate. At
# 10 units/s the ball moves about half its own drawn diameter per frame at
# 30 fps, so - unlike Test #1 - it never strobes and the trail is not needed
# for continuity at all. It is here for two other jobs: it says which ball is
# which inside a knot, and it is what turns a pile of seven balls into seven
# diverging streaks. 0.16 s is 1.6 world units at the constant speed of 10, so
# the trail is 34 px at the final framing against a 21 px ball, and the vector
# is the larger signal. `readability_report` is what raised it from 0.11.
TRAIL_SECONDS = 0.16
TRAIL_SAMPLES = 20
TRAIL_HEAD_WIDTH = 0.92
TRAIL_TAIL_WIDTH = 0.34

# --------------------------------------------------------------------------
# Walls
# --------------------------------------------------------------------------

# Backward extrusion per shell, inner to outer. The whole "the outer wall is
# the hardest" read lives in this ramp: nothing else about a panel may grow,
# because the front face is the canonical collision silhouette.
PANEL_DEPTH: tuple[float, ...] = (0.90, 1.30, 1.80, 2.40, 3.20)
# Pillars at the shell vertices are the panels' own round caps, so their radius
# is the canonical half-thickness and only their depth is a drawing choice.
POST_DEPTH_FACTOR = 1.55
PANEL_CHAMFER = 0.085
# Each panel is drawn as three sub-slabs so that `fractured` can separate them
# and a break can retract them into the two posts. They are flush and share one
# material until the panel fractures.
PANEL_SEGMENTS = 3
# Albedo value and specular response, inner to outer: the outer shells are
# darker and more metallic, which reads as denser material under one key light.
SHELL_ALBEDO_VALUE: tuple[float, ...] = (1.00, 0.97, 0.94, 0.91, 0.88)
SHELL_METALLIC: tuple[float, ...] = (0.05, 0.15, 0.25, 0.35, 0.45)
SHELL_ROUGHNESS: tuple[float, ...] = (0.55, 0.49, 0.43, 0.37, 0.31)

# --------------------------------------------------------------------------
# Events, as presentation
# --------------------------------------------------------------------------

SPAWN_FLASH_SECONDS = 0.30
SPAWN_FLASH_RADIUS = 3.10
SPAWN_LINK_SECONDS = 0.18
NEAR_MISS_SECONDS = 0.16
BREAK_FLASH_SECONDS = 0.16
BREAK_RETRACT_SECONDS = 0.55
BREAK_DEBRIS_SECONDS = 0.45
BREAK_DEBRIS_COUNT = 8
BREAK_DEBRIS_SIZE = 0.55
BREAK_DEBRIS_SPEED = 7.0
BREAK_DEBRIS_SPEED_SPREAD = 7.5
BREAK_RING_SECONDS = 0.60
BREAK_RING_RADIUS = 5.50
ESCAPE_FLARE_SECONDS = 0.60
ESCAPE_RING_SECONDS = 0.75
# The release beat. The document ends at the escape, so only the escapee has a
# canonical flight to continue; every other ball is held at its last canonical
# position rather than extrapolated, because a ball still inside the arena has
# walls in front of it and continuing its flight would draw it through one.
# `--release=0` renders the hard cut instead, and Phase 2A compares the two
# rather than assuming.
RELEASE_SECONDS = 0.55
END_HOLD_SECONDS = 0.40

# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

BACKGROUND_RGB = (0.020, 0.026, 0.042)
FLOOR_RGB = (0.075, 0.100, 0.165)
# The arena throws light into the 71% of the frame it cannot fill, sized from
# the framing rather than from the arena so it is a halo around shell 0 at the
# opening instead of a wash over the hook.
BACKDROP_Z = -6.0
GLOW_POOL_Z = -4.0
GLOW_POOL_RADII = 2.60
GLOW_POOL_ALPHA = 0.42

# The founder, and then one base hue per founder-child. Cool jewel tones only:
# the warm end of the spectrum belongs to damage and breaks, so a viewer never
# has to ask whether an orange thing is a ball or a wound. A founder can have
# at most five children, so five families is the whole space.
FOUNDER_RGB = (0.960, 0.980, 1.000)
FAMILY_RGB: tuple[tuple[float, float, float], ...] = (
    (0.250, 0.860, 1.000),   # cyan
    (0.440, 0.620, 1.000),   # azure
    (0.660, 0.500, 1.000),   # violet
    (0.940, 0.440, 0.920),   # magenta
    (0.300, 0.980, 0.840),   # aqua
)
# Each generation below the family root pales toward white and gains emission.
GENERATION_WHITEN = 0.13
GENERATION_WHITEN_MAX = 0.45
GENERATION_ENERGY_STEP = 0.12

PANEL_RGB = (0.400, 0.455, 0.560)
# The lit face and the lit back rim. A panel's collision surface is 0.30 units
# thick - 5.3 px at the final framing - so it is emitted rather than merely lit,
# and the back rim at z = -depth turns each panel into a well seen down its own
# axis: two bright lines with the flank between them, and the distance between
# them *is* the depth. That is where "the outer wall is the hardest" comes from.
FACE_RGB = (0.560, 0.720, 0.880)
FACE_ENERGY = 0.62
BACK_RGB = (0.300, 0.480, 0.680)
BACK_ENERGY = 0.30
# A pillar exists only where a panel ends, because a pillar is the panel
# capsule's own round cap. One that flanks an opening is the one a ball clips
# when it aims at the hole and misses, so it carries a cool cap and more depth.
POST_RGB = (0.330, 0.380, 0.470)
POST_HOT_RGB = (1.000, 0.680, 0.300)
POST_EDGE_RGB = (0.420, 0.860, 1.000)
POST_EDGE_ENERGY = 1.60
POST_BASE_ENERGY = 0.26
POST_EDGE_DEPTH = 1.35
CRACK_RGB = (1.000, 0.620, 0.220)
CRITICAL_RGB = (1.000, 0.440, 0.160)
FRACTURE_RGB = (1.000, 0.300, 0.140)
BREAK_FLASH_RGB = (1.000, 0.930, 0.800)

# Emission energy by damage state, in the same order as DAMAGE_STATES. The
# progression a viewer reads is this ramp times the crack count below it, not a
# recolour of the panel body, which keeps its own material throughout.
DAMAGE_EMISSION_ENERGY: tuple[float, ...] = (0.00, 0.90, 2.20, 4.00, 0.00)
# How many of a panel's crack marks are shown in each state. The marks are
# placed at the panel's own canonical impact offsets, in the order the impacts
# happened, so damage appears where the ball actually hit it.
DAMAGE_CRACK_COUNT: tuple[int, ...] = (0, 2, 4, 6, 0)
# How wide a damage mark is along the panel's own chord. The mark spans the
# panel's full wall depth - its 0.30-unit face and its whole flank behind it -
# so at the final framing it is a 5.5 px wide bar 24 px tall on an 85 px panel,
# and four of them read as a damaged panel at phone size. It is exactly as
# thick as the panel radially, so a mark never puts a pixel outside the
# canonical silhouette.
DAMAGE_MARK_CHORD = 0.30
# `fractured` opens two gaps between the three sub-slabs. The gaps are cut out
# of the sub-slabs rather than made by pushing them apart, so the panel's two
# ends stay exactly where they were and a fractured panel never occupies a
# pixel a healthy one did not. 0.20 units is 3.5 px at the final framing and
# 13 px while its own shell is framed; 0.05, the first value tried, was 0.9 px
# and invisible.
FRACTURE_GAP = 0.20
# A roll about each sub-slab's own long axis. It changes nothing in silhouette
# and everything in shading, which is what makes a fractured panel look
# buckled rather than repainted.
FRACTURE_TILT_DEGREES = 9.0
FRACTURE_RECESS = 0.10

# --------------------------------------------------------------------------
# The candidate rule
# --------------------------------------------------------------------------

SHORTLIST_PATH = os.path.join(
    "docs", "validation", "category3_multiplying_shell_adjust_v3b",
    "phase3b_shortlist.json"
)

CANDIDATE_RULE: dict[str, Any] = {
    "source": SHORTLIST_PATH,
    "duration_seconds": [20.0, 26.0],
    "first_spawn_seconds_preferred_max": 2.5,
    "first_spawn_seconds_max": 3.0,
    "first_spawn_seconds_reject_above": 3.0,
    "population_total": [8, 15],
    "flags": "none",
    "note": (
        "Six review renders selected from the thirteen engineering-screened "
        "survivors of the new 20,000-seed Phase 3B run. The set spans opening "
        "and break routes, descendant escapes, cooperative outer-wall breaks, "
        "and high-but-readable populations."
    ),
}

# The result of applying CANDIDATE_RULE, frozen so a test catches a drift in
# either the rule or the shortlist.
CANDIDATE_SEEDS: tuple[int, ...] = (15793, 8292, 17251, 16733, 12197, 14705)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_document(document: dict[str, Any]) -> str:
    """Empty string if this consumer may draw the document, else the reason."""
    if str(document.get("schema", "")) != EXPECTED_SCHEMA_VERSION:
        return (
            f"schema is {document.get('schema')!r}, this renderer reads "
            f"{EXPECTED_SCHEMA_VERSION!r}"
        )
    if str(document.get("config_digest", "")) != EXPECTED_CONFIG_DIGEST:
        return "config digest is not the locked Phase 3B operating configuration"
    shells = document.get("shells", [])
    if len(shells) != EXPECTED_SHELL_COUNT:
        return (
            f"the visual proof is built for {EXPECTED_SHELL_COUNT} shells, "
            f"got {len(shells)}"
        )
    if not document.get("summary", {}).get("escaped", False):
        return "a proof candidate must reach a canonical escape"
    events = document.get("events", [])
    if not events:
        return "the document carries no events"
    previous = -math.inf
    for event in events:
        at = float(event["t"])
        if at < previous:
            return "canonical event order is not monotone in time"
        previous = at
    if not any(event["kind"] == "escape" for event in events):
        return "no canonical escape event"
    return ""


def _require_valid(document: dict[str, Any]) -> None:
    reason = validate_document(document)
    if reason:
        raise ValueError(reason)


# --------------------------------------------------------------------------
# The camera schedule
# --------------------------------------------------------------------------


def shell_view_radii(document: dict[str, Any]) -> tuple[float, ...]:
    """The framed radius at each stage: a shell's material edge plus the pad."""
    return tuple(
        float(shell["radius"]) + 0.5 * float(shell["thickness"]) + VIEW_RADIUS_PAD
        for shell in document["shells"]
    )


def frame_marks(document: dict[str, Any]) -> tuple[tuple[float, int], ...]:
    """`(t, stage)` for each advance of the canonical high-water frontier.

    Read from the `shell_exit` stream and from nothing else. `to_region` is the
    region a ball moved into, so the first exit to region `k` is the first
    moment any ball is bounded by shell `k` and the first moment shell `k` has
    to be in frame. Stage 5 - escaped - has no shell to frame, so the schedule
    stops at 4.
    """
    limit = len(document["shells"]) - 1
    marks: list[tuple[float, int]] = []
    high_water = 0
    for event in document["events"]:
        if event["kind"] != "shell_exit":
            continue
        to_region = int(event["to_region"])
        while high_water < min(to_region, limit):
            high_water += 1
            marks.append((float(event["t"]), high_water))
    return tuple(marks)


def _smoothstep(u: float) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return u * u * (3.0 - 2.0 * u)


def view_radius_at(document: dict[str, Any], t: float) -> float:
    """The framed world radius at `t`. Monotone non-decreasing by construction.

    Each frontier advance contributes an independent eased step, so two
    advances 0.36 s apart - which happens in four of the seven candidates -
    simply overlap instead of fighting over one target, and the result is still
    monotone and still exactly reproducible from the document.
    """
    radii = shell_view_radii(document)
    radius = radii[0]
    for at, stage in frame_marks(document):
        span = radii[stage] - radii[stage - 1]
        radius += span * _smoothstep(
            (t - (at - FRAME_LEAD_SECONDS)) / FRAME_EASE_SECONDS
        )
    return radius


def pixels_per_unit(view_radius: float, width: int = FRAME_WIDTH) -> float:
    """Exact, not fitted: `2*view_radius` occupies VIEW_DIAMETER_FRACTION of the frame."""
    return float(width) * VIEW_DIAMETER_FRACTION / (2.0 * view_radius)


def camera_distance(view_radius: float) -> float:
    """Where the eye sits for that framing, from the horizontal field of view."""
    half_width_units = view_radius / VIEW_DIAMETER_FRACTION
    return half_width_units / math.tan(math.radians(CAMERA_HFOV_DEGREES) * 0.5)


def project(
    point: Sequence[float],
    view_radius: float,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> tuple[float, float]:
    """A canonical `z = 0` position to a pixel, origin at the frame's top left.

    The z=0 plane is projected by a uniform scale even under the perspective
    camera, because the camera looks straight down -Z, so this is the
    renderer's projection and not an approximation of it.
    """
    scale = pixels_per_unit(view_radius, width)
    return (
        width * ARENA_CENTRE_X_FRACTION + float(point[0]) * scale,
        height * ARENA_CENTRE_Y_FRACTION - float(point[1]) * scale,
    )


def project_3d(
    point: Sequence[float],
    z: float,
    view_radius: float,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> tuple[float, float]:
    """Project a point through the centred asymmetric perspective frustum."""
    distance = camera_distance(view_radius)
    scale = pixels_per_unit(view_radius, width) * distance / (distance - float(z))
    return (
        width * ARENA_CENTRE_X_FRACTION + float(point[0]) * scale,
        height * ARENA_CENTRE_Y_FRACTION - float(point[1]) * scale,
    )


def projected_shell_centres(view_radius: float) -> tuple[tuple[float, float], ...]:
    """Projected centres of the five thick slabs, sampled at slab mid-depth."""
    return tuple(project_3d((0.0, 0.0), -0.5 * depth, view_radius) for depth in PANEL_DEPTH)


def centre_alignment_report(
    document: dict[str, Any], fps: float = 60.0
) -> dict[str, Any]:
    """Measure shell-centre agreement on every rendered frame.

    The shell centres are sampled at their visual mid-depth, not merely at the
    shared front plane.  That is the measurement that exposes the old lateral
    camera's parallax and proves the off-axis frustum removed it.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    frame_count = int(math.ceil(duration * fps)) + 1
    maximum = 0.0
    worst_t = 0.0
    worst_centres: tuple[tuple[float, float], ...] = ()
    for frame in range(frame_count):
        t = min(duration, frame / fps)
        centres = projected_shell_centres(view_radius_at(document, t))
        for a in centres:
            for b in centres:
                error = math.hypot(a[0] - b[0], a[1] - b[1])
                if error > maximum:
                    maximum = error
                    worst_t = t
                    worst_centres = centres
    return {
        "fps": fps,
        "frames": frame_count,
        "maximum_disagreement_px": maximum,
        "worst_t": worst_t,
        "worst_centres": [list(point) for point in worst_centres],
        "target_px": 1.0,
        "preferred_px": 0.5,
        "passes": maximum <= 1.0,
    }


def alignment_moments(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Diagnostic still times around every centred frontier reframe."""
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    rows: list[dict[str, Any]] = [
        {"name": "frame_0", "t": 0.0, "why": "opening frame"}
    ]
    for index, (at, stage) in enumerate(frame_marks(document), start=1):
        rows.append(
            {
                "name": f"transition_{index}_mid",
                "t": max(0.0, at - FRAME_LEAD_SECONDS + 0.5 * FRAME_EASE_SECONDS),
                "why": f"mid-transition to frontier stage {stage}",
            }
        )
        rows.append(
            {
                "name": f"frontier_{index}_settled",
                "t": min(duration, at - FRAME_LEAD_SECONDS + FRAME_EASE_SECONDS),
                "why": f"after frontier stage {stage} settled",
            }
        )
    rows.append(
        {
            "name": "final_outer_section",
            "t": max(0.0, duration - 0.5),
            "why": "final outer-shell section",
        }
    )
    return rows


def flank_width(radius: float, depth: float, view_radius: float) -> float:
    """How wide a panel's receding side reads, in world units at the z=0 scale.

    A point at `z = -depth` and radius `r` projects to `r*D/(D+depth)`, so the
    flank runs from there out to the front face and is `r*depth/(D+depth)`
    wide. It lies *inside* the front face, which is why it can never cover a
    ball: every ball is at z=0, in front of every flank.
    """
    distance = camera_distance(view_radius)
    return radius * depth / (distance + depth)


# --------------------------------------------------------------------------
# Lineage colour
# --------------------------------------------------------------------------


def lineage_palette(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """One colour per ball, from `lineage` and `generation` and nothing else.

    The founder is the only white ball. Every other ball belongs to the family
    of the founder-child it descends from - `lineage[1]`, which is on every
    ball record - and keeps that family's base hue for the rest of the run. A
    generation below the family root pales the hue toward white by a fixed step
    and lifts its emission, so a fifth-generation descendant is recognisably
    the same family as its great-great-grandparent and recognisably younger.

    Families are numbered by the order their roots appear in `balls`, which is
    birth order, so the mapping is a function of the document and two renders
    of the same seed tint the same ball the same colour.
    """
    balls = document["balls"]
    roots: list[int] = []
    for ball in balls:
        lineage = ball["lineage"]
        if len(lineage) >= 2 and lineage[1] not in roots:
            roots.append(int(lineage[1]))

    palette: dict[int, dict[str, Any]] = {}
    for ball in balls:
        ball_id = int(ball["ball_id"])
        lineage = ball["lineage"]
        generation = int(ball["generation"])
        if len(lineage) < 2:
            palette[ball_id] = {
                "family": -1,
                "family_root": None,
                "depth": 0,
                "rgb": FOUNDER_RGB,
                "energy": 1.0,
                "generation": generation,
            }
            continue
        root = int(lineage[1])
        family = roots.index(root) % len(FAMILY_RGB)
        depth = max(0, generation - 1)
        whiten = min(GENERATION_WHITEN_MAX, GENERATION_WHITEN * depth)
        base = FAMILY_RGB[family]
        rgb = tuple(base[i] + (1.0 - base[i]) * whiten for i in range(3))
        palette[ball_id] = {
            "family": family,
            "family_root": root,
            "depth": depth,
            "rgb": rgb,
            "energy": 1.0 + GENERATION_ENERGY_STEP * depth,
            "generation": generation,
        }
    return palette


# --------------------------------------------------------------------------
# Reading the document back
# --------------------------------------------------------------------------


def live_balls_at(document: dict[str, Any], t: float) -> list[int]:
    """Ball ids that have been born by `t`, in birth order."""
    out = []
    for ball in document["balls"]:
        if float(ball["birth_time"]) <= t:
            out.append(int(ball["ball_id"]))
    return out


def positions_at(document: dict[str, Any], t: float) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for ball_id in live_balls_at(document, t):
        point = position_at(document, ball_id, t)
        if point is not None:
            out[ball_id] = point
    return out


def panel_impact_offsets(document: dict[str, Any]) -> dict[tuple[int, int], list[float]]:
    """Where each panel was actually hit, along its own chord, in time order.

    This is what makes a crack appear at an impact rather than at a decorative
    position: `panel_local_offset` is on every canonical collision event and is
    the contact's position along the panel measured from its centre.
    """
    out: dict[tuple[int, int], list[float]] = {}
    for event in document["events"]:
        if event["kind"] != "collision":
            continue
        key = (int(event["shell_id"]), int(event["panel_id"]))
        out.setdefault(key, []).append(float(event["panel_local_offset"]))
    return out


def damage_counts_at(document: dict[str, Any], t: float) -> dict[str, int]:
    """How many panels are in each canonical state at `t`, across all shells."""
    counts = {state: 0 for state in DAMAGE_STATES}
    total = 0
    for shell in document["shells"]:
        open_slots = set(int(s) for s in shell["open_slots"])
        for panel_id in range(int(shell["panel_count"])):
            if panel_id in open_slots:
                continue
            total += 1
            counts[panel_state_at(document, int(shell["shell_id"]), panel_id, t)] += 1
    counts["panels"] = total
    return counts


# --------------------------------------------------------------------------
# Geometry, measured
# --------------------------------------------------------------------------


def shell_geometry_report(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Per shell: how big its features are, at its own framing and at the last.

    Two columns matter and they answer different questions. `at_own_stage` is
    what the viewer sees while that shell is the frontier and the camera is
    framed on it; `at_final_stage` is what it looks like once the camera has
    opened out to the whole arena, which is where the five layers have to look
    different from each other.
    """
    radii = shell_view_radii(document)
    final_radius = radii[-1]
    out: list[dict[str, Any]] = []
    for shell in document["shells"]:
        index = int(shell["shell_id"])
        radius = float(shell["radius"])
        thickness = float(shell["thickness"])
        depth = PANEL_DEPTH[index]
        own = radii[index]
        entry: dict[str, Any] = {
            "shell_id": index,
            "radius": radius,
            "panel_count": int(shell["panel_count"]),
            "panels": int(shell["panel_count"]) - len(shell["open_slots"]),
            "openings": len(shell["openings"]),
            "open_fraction": len(shell["open_slots"]) / float(shell["panel_count"]),
            "chord_length": float(shell["chord_length"]),
            "gap_chord": min(float(o["gap_chord"]) for o in shell["openings"]),
            "depth": depth,
        }
        for label, view in (("at_own_stage", own), ("at_final_stage", final_radius)):
            scale = pixels_per_unit(view)
            flank = flank_width(radius, depth, view)
            entry[label] = {
                "view_radius": view,
                "pixels_per_unit": scale,
                "face_px": thickness * scale,
                "flank_px": flank * scale,
                "wall_px": (thickness + flank) * scale,
                "chord_px": float(shell["chord_length"]) * scale,
                "gap_px": entry["gap_chord"] * scale,
                "ring_radius_px": radius * scale,
            }
        out.append(entry)
    return out


def composition_report(document: dict[str, Any], samples: int = 240) -> dict[str, Any]:
    """Framing over the whole run: what fills the frame, and when it moves.

    `structure_occupancy` is the honest empty-space number. It is the fraction
    of the frame that lies inside the outermost shell with any material in
    shot, so it counts the shells that sit in the vertical bands at the tighter
    framings and does not count the bands that are genuinely dark at the last
    one.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    radii = shell_view_radii(document)
    marks = frame_marks(document)
    ball_radius = float(document["config"]["ball_radius"])

    moving = 0
    rows: list[dict[str, Any]] = []
    previous = None
    for index in range(samples + 1):
        t = duration * index / samples
        view = view_radius_at(document, t)
        scale = pixels_per_unit(view)
        if previous is not None and abs(view - previous) > 1e-9:
            moving += 1
        previous = view
        # Half-extents of the frame in world units.
        half_w = 0.5 * FRAME_WIDTH / scale
        half_h = 0.5 * FRAME_HEIGHT / scale
        centre_x = (ARENA_CENTRE_X_FRACTION - 0.5) * FRAME_WIDTH / scale
        centre_y = (0.5 - ARENA_CENTRE_Y_FRACTION) * FRAME_HEIGHT / scale
        # The outermost shell with material anywhere inside the frame.
        visible = 0.0
        for shell in document["shells"]:
            ring = float(shell["radius"]) + 0.5 * float(shell["thickness"])
            nearest_x = max(0.0, abs(centre_x) - half_w)
            nearest_y = max(0.0, abs(centre_y) - half_h)
            if math.hypot(nearest_x, nearest_y) <= ring:
                visible = max(visible, ring)
        rows.append(
            {
                "t": t,
                "view_radius": view,
                "pixels_per_unit": scale,
                "ball_px": 2.0 * ball_radius * BALL_DRAW_SCALE * scale,
                "halo_px": 2.0 * ball_radius * BALL_DRAW_SCALE * HALO_SCALE * scale,
                "structure_occupancy": _disc_frame_fraction(visible * scale),
            }
        )

    moving_fraction = moving / float(samples)
    static_tail = duration - (marks[-1][0] - FRAME_LEAD_SECONDS + FRAME_EASE_SECONDS) \
        if marks else duration
    return {
        "duration": duration,
        "frame_marks": [{"t": at, "stage": stage} for at, stage in marks],
        "stage_view_radii": list(radii),
        "camera_moving_fraction": moving_fraction,
        "camera_moving_seconds": moving_fraction * duration,
        "static_tail_seconds": static_tail,
        "ball_px_first_frame": rows[0]["ball_px"],
        "ball_px_last_frame": rows[-1]["ball_px"],
        "halo_px_last_frame": rows[-1]["halo_px"],
        "structure_occupancy_min": min(r["structure_occupancy"] for r in rows),
        "structure_occupancy_mean": sum(r["structure_occupancy"] for r in rows) / len(rows),
        "structure_occupancy_first": rows[0]["structure_occupancy"],
        "structure_occupancy_last": rows[-1]["structure_occupancy"],
        "samples": rows,
    }


def _disc_frame_fraction(radius_px: float) -> float:
    """What fraction of the 1080x1920 frame a disc of that pixel radius covers.

    Monte-Carlo-free: the disc is centred at the composition point and the
    frame is a rectangle, so the overlap is computed by integrating the disc's
    chord against the frame's vertical extent.
    """
    if radius_px <= 0.0:
        return 0.0
    cx = ARENA_CENTRE_X_FRACTION * FRAME_WIDTH
    cy = ARENA_CENTRE_Y_FRACTION * FRAME_HEIGHT
    steps = 480
    lo = max(0.0, cy - radius_px)
    hi = min(float(FRAME_HEIGHT), cy + radius_px)
    if hi <= lo:
        return 0.0
    area = 0.0
    step = (hi - lo) / steps
    for index in range(steps):
        y = lo + (index + 0.5) * step
        half = math.sqrt(max(0.0, radius_px * radius_px - (y - cy) ** 2))
        left = max(0.0, cx - half)
        right = min(float(FRAME_WIDTH), cx + half)
        area += max(0.0, right - left) * step
    return area / float(FRAME_WIDTH * FRAME_HEIGHT)


# --------------------------------------------------------------------------
# Safe area
# --------------------------------------------------------------------------


def safe_area_report(
    document: dict[str, Any],
    config: SafeAreaConfig = DEFAULT_SAFE_AREA,
    fps: float = 30.0,
) -> dict[str, Any]:
    """Does anything the viewer needs sit under the player's own controls?

    Two readings. The **arena** is geometry and is checked at the final
    framing, where it is largest: the outermost shell's material circle against
    each region, reported as the clearance in pixels, negative if it intrudes.
    The **balls** are checked over time, because a ball is where the viewer is
    looking and a ball under the action rail is a ball that is not there.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    final_view = shell_view_radii(document)[-1]
    scale = pixels_per_unit(final_view)
    outer = float(document["shells"][-1]["radius"]) + 0.5 * float(
        document["shells"][-1]["thickness"]
    )
    cx = ARENA_CENTRE_X_FRACTION * FRAME_WIDTH
    cy = ARENA_CENTRE_Y_FRACTION * FRAME_HEIGHT
    radius_px = outer * scale

    regions: list[dict[str, Any]] = []
    for region in config.regions:
        left, top, right, bottom = region.rect(FRAME_WIDTH, FRAME_HEIGHT)
        # Signed clearance from the disc to the rectangle: positive is clear.
        dx = max(left - cx, 0.0, cx - right)
        dy = max(top - cy, 0.0, cy - bottom)
        if dx == 0.0 and dy == 0.0:
            clearance = -radius_px
        else:
            clearance = math.hypot(dx, dy) - radius_px
        regions.append(
            {
                "region": region.name,
                "clearance_px": clearance,
                "clear": clearance > 0.0,
            }
        )

    ball_radius_px = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE * scale
    frames = max(1, int(round(duration * fps)))
    hidden_total = 0
    hidden_run = 0
    worst_run = 0
    hidden_by_region: dict[str, int] = {r.name: 0 for r in config.regions}
    for index in range(frames + 1):
        t = duration * index / frames
        view = view_radius_at(document, t)
        any_hidden = False
        for point in positions_at(document, t).values():
            px, py = project(point, view)
            for region in config.regions:
                covered = _disc_rect_fraction(px, py, ball_radius_px, region)
                if covered >= config.ball_hidden_fraction:
                    hidden_by_region[region.name] += 1
                    any_hidden = True
        if any_hidden:
            hidden_total += 1
            hidden_run += 1
            worst_run = max(worst_run, hidden_run)
        else:
            hidden_run = 0

    return {
        "safe_area": config.name,
        "fingerprint": config.fingerprint(),
        "final_view_radius": final_view,
        "pixels_per_unit": scale,
        "arena_radius_px": radius_px,
        "arena_regions": regions,
        "arena_clear": all(entry["clear"] for entry in regions),
        "min_clearance_px": min(entry["clearance_px"] for entry in regions),
        "ball_hidden_frames": hidden_total,
        "ball_hidden_seconds": hidden_total / fps,
        "ball_hidden_longest_seconds": worst_run / fps,
        "ball_hidden_budget_seconds": config.ball_hidden_budget_seconds,
        "ball_hidden_by_region": hidden_by_region,
        "ball_pass": (worst_run / fps) <= config.ball_hidden_budget_seconds,
    }


def _disc_rect_fraction(px: float, py: float, radius: float, region: Region) -> float:
    """Roughly how much of a disc falls inside a rectangle. Sampled on a grid.

    Exactness is not the question here - the gate is "half the ball or more" -
    and a 9x9 grid over the disc's bounding box answers that to about 1%.
    """
    left, top, right, bottom = region.rect(FRAME_WIDTH, FRAME_HEIGHT)
    if px + radius < left or px - radius > right:
        return 0.0
    if py + radius < top or py - radius > bottom:
        return 0.0
    inside = 0
    total = 0
    steps = 9
    for iy in range(steps):
        for ix in range(steps):
            x = px + radius * (2.0 * (ix + 0.5) / steps - 1.0)
            y = py + radius * (2.0 * (iy + 0.5) / steps - 1.0)
            if (x - px) ** 2 + (y - py) ** 2 > radius * radius:
                continue
            total += 1
            if left <= x <= right and top <= y <= bottom:
                inside += 1
    return inside / float(total) if total else 0.0


# --------------------------------------------------------------------------
# Readability
# --------------------------------------------------------------------------


def readability_report(document: dict[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Can the viewer follow the balls, and does the population read?

    Four questions, all of them answered from the document and the projection
    rather than from a render, because a number that comes from reading pixels
    back can only be taken after the render and this one has to be able to
    reject a composition before it is made.

    * **Crowding.** With ball-ball collisions off, two balls may occupy the
      same pixel, and at fifteen balls that is the failure mode the brief names
      - a glow cloud. The closest pair is the obvious measure and it is the
      wrong one: two balls crossing for three frames is not a glow cloud, and
      over twenty seconds and fifteen balls a near-coincidence is certain. So
      the report clusters the balls on each frame at a one-diameter threshold
      and asks how many **distinguishable blobs** there are against how many
      balls there are, what the largest cluster gets to, and how long a cluster
      of three or more survives. A three-ball merge that lasts a fifth of a
      second is a glint; one that lasts two seconds is the failure.
    * **Continuity.** How far a ball moves between two frames against its own
      drawn diameter. Above 1.0 the ball strobes and needs the trail to bridge
      it; Test #1 found 2.2 at 30 fps and had to add one.
    * **Escalation.** The population at each third of the run, which is the one
      thing the redesign exists to show.
    * **Lineage load.** How many distinct families are on screen at once.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    ball_radius = float(document["config"]["ball_radius"])
    palette = lineage_palette(document)
    frames = max(2, int(round(duration * fps)))

    closest = math.inf
    closest_t = 0.0
    max_step_ratio = 0.0
    max_step_t = 0.0
    peak_population = 0
    peak_t = 0.0
    max_families = 0
    largest_cluster = 1
    largest_cluster_t = 0.0
    merge_run = 0
    worst_merge_run = 0
    worst_merge_t = 0.0
    blob_deficit_frames = 0
    blob_sum = 0.0
    ball_sum = 0.0
    previous: dict[int, tuple[float, float]] = {}

    for index in range(frames + 1):
        t = duration * index / frames
        view = view_radius_at(document, t)
        scale = pixels_per_unit(view)
        drawn_diameter = 2.0 * ball_radius * BALL_DRAW_SCALE * scale
        points = positions_at(document, t)
        screen = {b: project(p, view) for b, p in points.items()}

        if len(screen) > peak_population:
            peak_population = len(screen)
            peak_t = t
        families = {palette[b]["family"] for b in screen}
        max_families = max(max_families, len(families))

        ids = sorted(screen)
        # Union-find over "centres closer than one drawn diameter". A component
        # is what the eye has to separate; its size is what makes that hard.
        parent = {ball_id: ball_id for ball_id in ids}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                ax, ay = screen[ids[i]]
                bx, by = screen[ids[j]]
                ratio = math.hypot(ax - bx, ay - by) / drawn_diameter
                if ratio < closest:
                    closest = ratio
                    closest_t = t
                if ratio < 1.0:
                    ra, rb = find(ids[i]), find(ids[j])
                    if ra != rb:
                        parent[ra] = rb

        sizes: dict[int, int] = {}
        for ball_id in ids:
            root = find(ball_id)
            sizes[root] = sizes.get(root, 0) + 1
        biggest = max(sizes.values()) if sizes else 1
        blobs = len(sizes)
        blob_sum += blobs
        ball_sum += len(ids)
        if blobs < len(ids):
            blob_deficit_frames += 1
        if biggest > largest_cluster:
            largest_cluster = biggest
            largest_cluster_t = t
        if biggest >= 3:
            merge_run += 1
            if merge_run > worst_merge_run:
                worst_merge_run = merge_run
                worst_merge_t = t
        else:
            merge_run = 0

        for ball_id, point in screen.items():
            if ball_id in previous:
                step = math.hypot(point[0] - previous[ball_id][0],
                                  point[1] - previous[ball_id][1])
                ratio = step / drawn_diameter
                if ratio > max_step_ratio:
                    max_step_ratio = ratio
                    max_step_t = t
        previous = screen

    thirds = []
    for third in range(3):
        at = duration * (third + 1) / 3.0
        thirds.append(len(positions_at(document, at)))

    return {
        "fps": fps,
        "peak_population": peak_population,
        "peak_population_t": peak_t,
        "population_by_third": thirds,
        "population_first_frame": len(positions_at(document, 0.0)),
        "families_max_on_screen": max_families,
        "families_total": len(document["balls"][0]["children"]),
        "closest_pair_diameters": closest if closest < math.inf else None,
        "closest_pair_t": closest_t,
        "largest_cluster": largest_cluster,
        "largest_cluster_t": largest_cluster_t,
        "longest_triple_merge_seconds": worst_merge_run / fps,
        "longest_triple_merge_t": worst_merge_t,
        "blob_deficit_frames": blob_deficit_frames,
        "blob_deficit_fraction": blob_deficit_frames / float(frames + 1),
        "mean_blobs_per_ball": (blob_sum / ball_sum) if ball_sum else 1.0,
        "max_step_diameters": max_step_ratio,
        "max_step_t": max_step_t,
        "strobes": max_step_ratio > 1.0,
    }


def damage_report(document: dict[str, Any], samples: int = 120) -> dict[str, Any]:
    """The wall's own story: how much of it is marked, and how big the marks are.

    The brief asks whether the five states are legible, which is two separate
    facts - that a state is *reached* often enough to be seen at all, and that
    a panel in that state is big enough on screen to read. The second is the
    one a composition can fail, so the panel's drawn face is reported in pixels
    at the framing in force when that panel actually changed state.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    shells = {int(s["shell_id"]): s for s in document["shells"]}

    reached = {state: 0 for state in DAMAGE_STATES[1:]}
    sizes: dict[str, list[float]] = {state: [] for state in DAMAGE_STATES[1:]}
    for entry in document["panel_states"]:
        shell = shells[int(entry["shell_id"])]
        chord = float(shell["chord_length"])
        thickness = float(shell["thickness"])
        for transition in entry["transitions"]:
            state = transition["state"]
            reached[state] = reached.get(state, 0) + 1
            view = view_radius_at(document, float(transition["t"]))
            scale = pixels_per_unit(view)
            sizes[state].append(chord * scale)
        if entry["break_time"] is not None:
            reached["broken"] += 1
            view = view_radius_at(document, float(entry["break_time"]))
            scale = pixels_per_unit(view)
            sizes["broken"].append(chord * scale)
            sizes.setdefault("broken_face_px", []).append(thickness * scale)

    timeline = []
    for index in range(samples + 1):
        t = duration * index / samples
        counts = damage_counts_at(document, t)
        timeline.append({"t": t, **counts})

    end = damage_counts_at(document, duration)
    return {
        "states_reached": reached,
        "panel_chord_px_when_reached": {
            state: {
                "min": min(values),
                "median": sorted(values)[len(values) // 2],
                "max": max(values),
            }
            for state, values in sizes.items()
            if values and state in DAMAGE_STATES
        },
        "final_counts": end,
        "damaged_or_worse_at_end": end["panels"] - end["healthy"],
        "broken_at_end": end["broken"],
        "shared_breaks": sum(
            1
            for event in document["events"]
            if event["kind"] == "panel_break" and int(event["contributors"]) > 1
        ),
        "timeline": timeline,
    }


# --------------------------------------------------------------------------
# The stills the brief asks for
# --------------------------------------------------------------------------

STILL_ORDER: tuple[str, ...] = (
    "a_opening",
    "b_first_split",
    "c_four_balls",
    "d_near_miss",
    "e_damaged_panel",
    "f_critical_panel",
    "g_panel_break",
    "h_late_population",
    "i_final_escape",
)


def event_moments(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The nine named instants, each one an actual canonical event time.

    Chosen rather than sampled: a still of "a panel breaking" taken at a round
    number of seconds is a still of whatever happened to be on screen. Each of
    these is a canonical event plus a stated offset, and the offset is there
    only so the still lands inside the effect rather than on its first frame.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    events = document["events"]
    balls = {int(b["ball_id"]): b for b in document["balls"]}

    def first(kind: str, predicate=None) -> dict[str, Any] | None:
        for event in events:
            if event["kind"] == kind and (predicate is None or predicate(event)):
                return event
        return None

    def last(kind: str, predicate=None) -> dict[str, Any] | None:
        found = None
        for event in events:
            if event["kind"] == kind and (predicate is None or predicate(event)):
                found = event
        return found

    moments: list[dict[str, Any]] = []

    moments.append({"name": "a_opening", "t": min(0.30, duration), "why": "frame one"})

    spawn = first("ball_spawn")
    if spawn is not None:
        moments.append(
            {
                "name": "b_first_split",
                "t": float(spawn["t"]) + 0.5 * SPAWN_LINK_SECONDS,
                "why": f"ball {spawn['ball_id']} born at {float(spawn['t']):.2f}s",
            }
        )

    fourth = None
    for ball in document["balls"]:
        if int(ball["ball_id"]) == 3:
            fourth = float(ball["birth_time"])
    if fourth is not None:
        moments.append(
            {"name": "c_four_balls", "t": min(duration, fourth + 0.45),
             "why": "0.45 s after the fourth ball exists"}
        )

    # The closest near miss in the run, which is the one worth a still.
    near = None
    for event in events:
        if event["kind"] != "near_miss":
            continue
        if near is None or float(event["arc_separation_ball_radii"]) < float(
            near["arc_separation_ball_radii"]
        ):
            near = event
    if near is not None:
        moments.append(
            {
                "name": "d_near_miss",
                "t": float(near["t"]) + 0.4 * NEAR_MISS_SECONDS,
                "why": (
                    f"{float(near['arc_separation_ball_radii']):.2f} ball radii "
                    f"from opening {near['opening_id']}, criterion {near['criterion']}"
                ),
            }
        )

    damaged = first("damage_state", lambda e: e["new_state"] == "damaged")
    if damaged is not None:
        moments.append(
            {"name": "e_damaged_panel", "t": float(damaged["t"]) + 0.35,
             "why": f"shell {damaged['shell_id']} panel {damaged['panel_id']}"}
        )

    # Prefer a fractured panel; a run with none still has criticals.
    worst = first("damage_state", lambda e: e["new_state"] == "fractured")
    if worst is None:
        worst = first("damage_state", lambda e: e["new_state"] == "critical")
    if worst is not None:
        moments.append(
            {"name": "f_critical_panel", "t": float(worst["t"]) + 0.35,
             "why": f"{worst['new_state']} on shell {worst['shell_id']} "
                    f"panel {worst['panel_id']}"}
        )

    # The most interesting break is one more than one ball paid for.
    shared = first("panel_break", lambda e: int(e["contributors"]) > 1)
    if shared is None:
        shared = first("panel_break")
    if shared is not None:
        moments.append(
            {
                "name": "g_panel_break",
                "t": float(shared["t"]) + 0.25 * BREAK_RETRACT_SECONDS,
                "why": (
                    f"shell {shared['shell_id']} panel {shared['panel_id']}, "
                    f"{shared['hits']} hits from {shared['contributors']} balls"
                ),
            }
        )

    # The last moment before the escape at which the population is at its peak.
    peak_t = duration
    peak = 0
    for ball in document["balls"]:
        birth = float(ball["birth_time"])
        if birth <= 0.0:
            continue
        count = len([b for b in document["balls"] if float(b["birth_time"]) <= birth])
        if count >= peak and birth < duration - 0.2:
            peak = count
            peak_t = birth
    moments.append(
        {"name": "h_late_population", "t": min(duration - 0.05, peak_t + 0.60),
         "why": f"{peak} balls alive"}
    )

    escape = last("escape")
    if escape is not None:
        moments.append(
            {
                "name": "i_final_escape",
                "t": float(escape["t"]) + 0.45 * ESCAPE_FLARE_SECONDS,
                "why": (
                    f"ball {escape['ball_id']}, generation {escape['generation']}, "
                    f"route {escape['route']}"
                ),
            }
        )

    order = {name: index for index, name in enumerate(STILL_ORDER)}
    moments.sort(key=lambda entry: order.get(entry["name"], 99))
    return moments


# --------------------------------------------------------------------------
# One report per candidate
# --------------------------------------------------------------------------


def measure_document(document: dict[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Everything the brief asks to be measured, for one seed."""
    _require_valid(document)
    composition = composition_report(document)
    # The samples are for a chart nobody is drawing; the report keeps the
    # summary and drops them so a manifest of seven seeds stays readable.
    samples = composition.pop("samples")
    damage = damage_report(document)
    timeline = damage.pop("timeline")
    return {
        "seed": int(document["seed"]),
        "digest": document["digest"],
        "summary": {
            key: document["summary"][key]
            for key in (
                "duration", "escaped", "escape_ball", "escape_time",
                "max_population", "max_generation", "breaks", "near_misses",
                "collisions", "spawns",
            )
        },
        "escape_generation": _escape_generation(document),
        "composition": composition,
        "shells": shell_geometry_report(document),
        "safe_area": safe_area_report(document, fps=fps),
        "readability": readability_report(document, fps=fps),
        "damage": damage,
        "moments": event_moments(document),
        "occupancy_samples": len(samples),
        "damage_samples": len(timeline),
    }


def _escape_generation(document: dict[str, Any]) -> int | None:
    for event in reversed(document["events"]):
        if event["kind"] == "escape":
            return int(event["generation"])
    return None


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


def candidate_seeds(shortlist: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the hard gates and Phase 3B review selection to the shortlist."""
    low, high = CANDIDATE_RULE["duration_seconds"]
    split_max = CANDIDATE_RULE["first_spawn_seconds_max"]
    pop_low, pop_high = CANDIDATE_RULE["population_total"]
    selected = set(int(seed) for seed in shortlist.get("review_seeds", CANDIDATE_SEEDS))
    kept: list[dict[str, Any]] = []
    for candidate in shortlist["candidates"]:
        if int(candidate["seed"]) not in selected:
            continue
        if candidate["flags"]:
            continue
        if not low <= float(candidate["duration"]) <= high:
            continue
        if float(candidate["first_spawn"]) > split_max:
            continue
        if not pop_low <= int(candidate["population_total"]) <= pop_high:
            continue
        kept.append(
            {
                "seed": int(candidate["seed"]),
                "duration": float(candidate["duration"]),
                "first_split": float(candidate["first_spawn"]),
                "population": int(candidate["population_total"]),
                "generations": int(candidate["generations"]),
                "escape_route": candidate["escape_route"],
                "escape_generation": int(candidate["escape_generation"]),
                "escape_by": (
                    "founder" if int(candidate["escape_generation"]) == 0
                    else "descendant"
                ),
                "progression_opening": int(candidate["progression_opening"]),
                "progression_break": int(candidate["progression_break"]),
                "breaks": int(candidate["breaks"]),
                "shared_breaks": int(candidate["shared_breaks"]),
                "near_misses": int(candidate["near_misses"]),
                "escalation": float(candidate["escalation"]["meaningful"]),
                "digest": candidate["digest"],
            }
        )
    order = {seed: index for index, seed in enumerate(CANDIDATE_SEEDS)}
    kept.sort(key=lambda entry: order.get(entry["seed"], len(order)))
    return kept


def candidate_manifest(shortlist: dict[str, Any]) -> dict[str, Any]:
    """The committed manifest: the rule, the seeds, and what they span.

    Audio Phase 2B renders the same list, so the list has to be a file rather
    than a paragraph, and it carries the Phase 1 digests so a seed that has
    silently become a different run fails loudly instead of sounding wrong.
    """
    kept = candidate_seeds(shortlist)
    routes = {"opening": 0, "break": 0}
    who = {"founder": 0, "descendant": 0}
    for entry in kept:
        routes[entry["escape_route"]] += 1
        who[entry["escape_by"]] += 1
    return {
        "format": 1,
        "phase": "category3-test2-multiplying-shell/adjust-v3b",
        "config_digest": shortlist["config_digest"],
        "expected_config_digest": EXPECTED_CONFIG_DIGEST,
        "shortlist_seeds": list(shortlist["seeds"]),
        "rule": CANDIDATE_RULE,
        "seeds": [entry["seed"] for entry in kept],
        "candidates": kept,
        "coverage": {
            "count": len(kept),
            "escape_route": routes,
            "escaping_ball": who,
            "duration_seconds": [
                min(e["duration"] for e in kept),
                max(e["duration"] for e in kept),
            ],
            "first_split_seconds": [
                min(e["first_split"] for e in kept),
                max(e["first_split"] for e in kept),
            ],
            "population": [
                min(e["population"] for e in kept),
                max(e["population"] for e in kept),
            ],
            "opening_dominant": [
                e["seed"] for e in kept
                if e["progression_opening"] >= 3 * max(1, e["progression_break"])
            ],
            "break_heavy": [
                e["seed"] for e in kept
                if e["progression_break"] >= 0.6 * e["progression_opening"]
            ],
        },
    }


# --------------------------------------------------------------------------
# The render configuration, as one hashable object
# --------------------------------------------------------------------------


def render_config() -> dict[str, Any]:
    """Every number the renderer draws with, in one dictionary.

    Its digest goes in the report and in the manifest. Two renders that print
    the same digest were made by the same look; a change to any constant here
    changes it, which is the only way a still in a report can be tied to the
    settings that produced it after the fact.
    """
    return {
        "format": 1,
        "schema": EXPECTED_SCHEMA_VERSION,
        "config_digest": EXPECTED_CONFIG_DIGEST,
        "frame": [FRAME_WIDTH, FRAME_HEIGHT],
        "view_diameter_fraction": VIEW_DIAMETER_FRACTION,
        "arena_centre": [ARENA_CENTRE_X_FRACTION, ARENA_CENTRE_Y_FRACTION],
        "view_radius_pad": VIEW_RADIUS_PAD,
        "camera_hfov_degrees": CAMERA_HFOV_DEGREES,
        "camera_near": CAMERA_NEAR,
        "camera_frustum_size": CAMERA_FRUSTUM_SIZE,
        "camera_frustum_offset": list(CAMERA_FRUSTUM_OFFSET),
        "frame_lead_seconds": FRAME_LEAD_SECONDS,
        "frame_ease_seconds": FRAME_EASE_SECONDS,
        "ball_draw_scale": BALL_DRAW_SCALE,
        "halo_scale": HALO_SCALE,
        "ball_rim": [BALL_RIM_SCALE, BALL_RIM_Z],
        "layer_z": [TRAIL_Z, HALO_Z, EFFECT_Z],
        "trail_width": [TRAIL_HEAD_WIDTH, TRAIL_TAIL_WIDTH],
        "trail_seconds": TRAIL_SECONDS,
        "trail_samples": TRAIL_SAMPLES,
        "panel_depth": list(PANEL_DEPTH),
        "post_depth_factor": POST_DEPTH_FACTOR,
        "panel_chamfer": PANEL_CHAMFER,
        "panel_segments": PANEL_SEGMENTS,
        "shell_albedo_value": list(SHELL_ALBEDO_VALUE),
        "shell_metallic": list(SHELL_METALLIC),
        "shell_roughness": list(SHELL_ROUGHNESS),
        "damage_emission_energy": list(DAMAGE_EMISSION_ENERGY),
        "damage_crack_count": list(DAMAGE_CRACK_COUNT),
        "damage_mark_chord": DAMAGE_MARK_CHORD,
        "fracture": [FRACTURE_GAP, FRACTURE_TILT_DEGREES, FRACTURE_RECESS],
        "spawn": [SPAWN_FLASH_SECONDS, SPAWN_FLASH_RADIUS, SPAWN_LINK_SECONDS],
        "near_miss_seconds": NEAR_MISS_SECONDS,
        "break": [
            BREAK_FLASH_SECONDS, BREAK_RETRACT_SECONDS, BREAK_DEBRIS_SECONDS,
            BREAK_DEBRIS_COUNT, BREAK_RING_SECONDS, BREAK_RING_RADIUS,
        ],
        "escape": [ESCAPE_FLARE_SECONDS, ESCAPE_RING_SECONDS],
        "ending": [RELEASE_SECONDS, END_HOLD_SECONDS],
        "background": list(BACKGROUND_RGB),
        "floor": list(FLOOR_RGB),
        "founder": list(FOUNDER_RGB),
        "families": [list(rgb) for rgb in FAMILY_RGB],
        "generation": [
            GENERATION_WHITEN, GENERATION_WHITEN_MAX, GENERATION_ENERGY_STEP,
        ],
        "panel": list(PANEL_RGB),
        "face": [list(FACE_RGB), FACE_ENERGY],
        "back": [list(BACK_RGB), BACK_ENERGY],
        "post": [
            list(POST_RGB), list(POST_HOT_RGB), list(POST_EDGE_RGB),
            POST_EDGE_ENERGY, POST_BASE_ENERGY, POST_EDGE_DEPTH,
        ],
        "backdrop": [BACKDROP_Z, GLOW_POOL_Z, GLOW_POOL_RADII, GLOW_POOL_ALPHA],
        "debris": [
            BREAK_DEBRIS_SIZE, BREAK_DEBRIS_SPEED, BREAK_DEBRIS_SPEED_SPREAD,
        ],
        "damage_colours": [
            list(CRACK_RGB), list(CRITICAL_RGB), list(FRACTURE_RGB),
            list(BREAK_FLASH_RGB),
        ],
        "safe_area": DEFAULT_SAFE_AREA.fingerprint(),
    }


def render_config_digest() -> str:
    blob = json.dumps(render_config(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
