"""Render-only cross-section transforms for the Race #2 channel.

## Why this module exists at all

`race2.export._run_rings` and `sloped.track.TrackRun.local_colliders` build the
same rings from the same `section_at`. That is the arrangement
`race2.export`'s own docstring argues for - "the renderer is handed the collider
the physics actually used, and a disagreement between what is simulated and what
is photographed is not possible rather than merely tested for" - and it is why
V31.1 could not touch the geometry at all: every vertex it might have moved was
a vertex the marbles run on.

V31.1 then measured the cost of that arrangement. The cradle - the surface a
marble rolls on - covers **0.000% of the frame on eight of thirteen sampled
moments**. The V32.1 brief and V31.1 both read that as the deck being hidden
behind the near guard.

**It is not.** The channel is an open strip of single-sided triangles, and
`race2_scene._strip_mesh` winds it so that the side Godot draws is the *outside
of the shell*: the underside of the cradle and the outer face of each guard. The
running surface is not behind anything. It is backfacing to every camera above
the track, and the rasteriser discards it before depth is ever considered. The
white ribbon in the delivered film is the outside of the near rail.

That is why `FACES` below exists and why it, rather than any cross-section here,
is what moves the number. What the cross-sections do is second-order and real:
once the deck is drawn at all, the near guard's outer face genuinely does stand
in front of some of it, and lowering or leaning that face is what widens the
lane the viewer reads.

So this pass needs one new thing per layer. For the picture's *shape*: a place
where the picture of the channel may differ from the collider of it, stated as a
function rather than as a second hand-built course. That place is here, and it
is applied at exactly one call site - `race2.export._run_rings` - so
`local_colliders()` cannot see it even by accident.

## What a variant may and may not do

A variant is a pure map from one cross-section to another of **the same length**
(the strip builder joins rings column by column and `u = column / 20` is what
`race2_track_surface` paints its bands from, so a variant that changed the point
count would repaint the track as well as reshape it).

It may move `up` downward. It may move `across` outward. It may never do either
in the other direction, because inward and upward is where the marbles are and a
render face inside the collider is a face a marble drives through:

    |across_render(i)| >= |across_collider(i)|    every point
    up_render(i)       <= up_collider(i)          every point

Both are asserted in `tests/test_race2_v321_geometry.py`, against the built
course rather than against the bare profile, so a run with an opened wall or a
guard boost is checked as it is actually swept.

## The numbers the variants are shaped around

At Race #2's scale of 2.0, `race2.track.capped_profile(2.0)` is 21 points:

    cradle   across 0.000 .. +-1.880   up -0.520 .. -0.098    a dish 0.422 deep
    lip      across +-1.900 .. +-2.000 up -0.020 .. +0.530
    guard    across +-2.004            up +0.560 .. +0.580    (capped from 1.08)

**The rail stands 0.678 above the cradle's own edge in 0.124 of lateral run** -
a face at 79.6 degrees, five eighths of the section's height packed into three
per cent of its width. With the strip drawn on both sides, that face is what is
left standing between the RB camera and the deck, and it is what A, B and C
move.

And the fence is load-bearing, but only just. Over the delivered race, of the
marble-frames inside a channel, 1.4% have the marble laterally out on the lip or
the guard at all, and the highest contact any marble makes against that face is
about three quarters of the way up it. `LOAD_BEARING` is that measurement, and
every variant is measured against it. One marble-frame in 7765 leans higher
than any of them keeps the face, and what that costs is a number in the table
rather than a risk in a sentence.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

__all__ = [
    "LOAD_BEARING_MAX",
    "LOAD_BEARING_P99",
    "VARIANTS",
    "WELD",
    "FACES",
    "known",
    "transform",
    "describe",
    "cradle_edges",
]

Section = list[tuple[float, float]]

# How high up the guard face a marble in the delivered race actually leans, as a
# fraction of the face's own height above the cradle edge. Measured by
# `tools/race2_v321_geometry.py contacts`, seed 8, over every frame of the
# 19.1667 s film, and re-derived by
# `tests/test_race2_v321_geometry.py::test_the_load_bearing_numbers_are_measured`.
#
# **The constraint is far weaker than it looks, and that is the finding.** Of
# 7765 marble-frames inside a channel, 109 rest on the lip or the face at all,
# and of those exactly **one** - m3, in `corr1`, at t = 2.433, a single 1/60 s
# frame - reaches above 0.45 of the face. The ninety-ninth percentile is 0.396.
# So a render face kept at 0.70 of the collider's is a face that still exists
# under every contact in the film but one, and that one overshoots it by 0.106
# layout units, which is 0.37 of a marble radius for one frame.
LOAD_BEARING_P99 = 0.396
LOAD_BEARING_MAX = 0.856


def cradle_edges(section: Sequence[tuple[float, float]]) -> tuple[int, int]:
    """The indices of the two points that are the cradle's own edges.

    Found rather than hard-coded: `sloped.track.channel_profile` puts
    `CRADLE_POINTS` on each half and the count is a module constant a future
    course could change. The cradle's edge is the last point, walking outward
    from the centre, whose surface is still shallower than 45 degrees - the
    first point past it is the lip, which turns by 53.7.
    """
    middle = len(section) // 2
    east = middle
    for index in range(middle, len(section) - 1):
        a0, u0 = section[index]
        a1, u1 = section[index + 1]
        if a1 - a0 < 1e-9:
            break
        if (u1 - u0) / (a1 - a0) > 1.0:
            break
        east = index + 1
    return len(section) - 1 - east, east


def _rise_scale(section: Section, factor: float) -> Section:
    """Every point above the cradle edge, with its rise above that edge scaled.

    Lateral positions are untouched, so the face keeps its own curve and only
    loses height. The conservative move, and the one with no second effect to
    argue about.
    """
    west, east = cradle_edges(section)
    edge_up = section[east][1]
    out: Section = []
    for index, (across, up) in enumerate(section):
        if west <= index <= east:
            out.append((across, up))
            continue
        out.append((across, edge_up + (up - edge_up) * factor))
    return out


def _flare(section: Section, factor: float, out_gain: float) -> Section:
    """Lower the face and lean its top outward: a bank rather than a fence.

    The lateral move is proportional to the height the point lost, which keeps
    the face a straight taper rather than a curve with a kink in it, and it is
    always outward, so no render vertex moves into the channel.
    """
    west, east = cradle_edges(section)
    edge_up = section[east][1]
    out: Section = []
    for index, (across, up) in enumerate(section):
        if west <= index <= east:
            out.append((across, up))
            continue
        rise = up - edge_up
        side = 1.0 if index > east else -1.0
        out.append((across + side * rise * (1.0 - factor) * out_gain,
                    edge_up + rise * factor))
    return out


def _bench(section: Section, factor: float, width: float) -> Section:
    """A render-only shoulder: the whole face carried outward, shape intact.

    Every point above the cradle edge slides outward by the same `width`, so
    the face keeps its own curve and its own angle and the span it vacates -
    from the cradle's edge to the new foot - becomes a flat shelf at the
    cradle's edge height. The ribbon gains a broad pale band **outside** the
    collider, where a low camera can see it, with the face standing on that
    band as a kerb.

    The first draft slid the foot further than the crown, which stood the face
    back over the shelf as an overhang and made `across` non-monotone. Sliding
    the whole face by one number is what keeps the section a function of
    `across`, which every reader of it - the strip builder, the band texture,
    `sloped.track._interpolate_rise` - assumes.

    Nothing can ever touch the shelf: it lies outside the collision wall, so
    this is the one variant that changes nothing at all about where a marble may
    be seen resting.
    """
    west, east = cradle_edges(section)
    edge_up = section[east][1]
    out: Section = []
    for index, (across, up) in enumerate(section):
        if west <= index <= east:
            out.append((across, up))
            continue
        side = 1.0 if index > east else -1.0
        out.append((across + side * width, edge_up + (up - edge_up) * factor))
    return out


# Each variant: a title, the transform, and the sentence that says what it is.
# The three are the brief's Part C, built from the geometry Part A measured.
VARIANTS: dict[str, dict[str, object]] = {
    "CONTROL": {
        "title": "the V32 channel, unchanged",
        "apply": lambda section: [(a, u) for a, u in section],
        "note": "the collider, photographed - what V32 ships",
    },
    "A": {
        "title": "lower visual guard",
        # 0.70 clears the 99th percentile of contacts (0.396) with three times
        # the margin, and is under the single 0.856 outlier by 0.106 layout
        # units for one frame of 1150. Lateral positions untouched.
        "apply": lambda section: _rise_scale(section, 0.70),
        "note": "the face's rise above the cradle edge scaled to 0.70 with its "
                "lateral positions unmoved - the conservative reveal",
    },
    "B": {
        "title": "tapered guard, deck exposed",
        "apply": lambda section: _flare(section, 0.70, 2.20),
        "note": "the face scaled to 0.70 and its top leaned outward by 2.20 of "
                "the height it lost - a bank the camera looks over rather than "
                "a fence it looks at",
    },
    "C": {
        "title": "render-only shoulder",
        "apply": lambda section: _bench(section, 0.90, 0.55),
        "note": "the face kept at 0.90 and carried 0.55 outward onto a flat "
                "shelf at the cradle's height, outside the collider, where "
                "nothing can touch it",
    },
}

# How much of the channel strip the renderer draws, per variant.
#
# **This is the pass's real finding and it is not a cross-section at all.** The
# strip is single-sided and wound so that Godot draws its *outside* - the
# underside of the cradle, the outer face of each guard - and culls the running
# surface. So the deck was never behind the rail: it was backfacing, and no
# variant that moves a vertex could have revealed a polygon the rasteriser
# discards before depth is considered. `both` is `cull_mode = CULL_DISABLED` on
# the channel material and nothing else; see `race2_track_surface.faces`.
FACES = {
    "CONTROL": "front",
    "S": "both",
    "A": "both",
    "B": "both",
    "C": "both",
}

# Whether consecutive runs share an edge in the render mesh. Off for CONTROL,
# which has to reproduce V32 byte for byte; on for every candidate, because the
# seam it closes is only visible once the deck is drawn and closing it is not a
# choice any of them should be asked to make separately. See
# `race2.export.RENDER_WELD` for the measurement.
WELD = {"CONTROL": False, "S": True, "A": True, "B": True, "C": True}

# `S` is the winding fix with the collider's own section: the restraint
# candidate, and the control for every other one. It is not a fourth
# cross-section - `transform("S", ...)` is the identity.
VARIANTS["S"] = {
    "title": "the winding fix alone",
    "apply": lambda section: [(a, u) for a, u in section],
    "note": "the collider's own section, drawn on both sides and welded at the "
            "run joins - no cross-section vertex moves",
}


def known(name: str) -> bool:
    return not name or name in VARIANTS


def transform(name: str, section: Sequence[tuple[float, float]]) -> Section:
    """One cross-section, mapped for the renderer.

    `CONTROL` and the empty name are the identity, and that is the property
    every other lock in this branch is checked through: a render with no variant
    has to reproduce V32's geometry file byte for byte.
    """
    rows: Section = [(float(a), float(u)) for a, u in section]
    if not name or name in ("CONTROL", "S"):
        return rows
    if name not in VARIANTS:
        raise KeyError(f"unknown render section variant: {name}")
    apply: Callable[[Section], Section] = VARIANTS[name]["apply"]  # type: ignore[assignment]
    out = apply(rows)
    if len(out) != len(rows):
        raise ValueError(f"{name} changed the section's point count")
    return [(float(a), float(u)) for a, u in out]


def describe(name: str, section: Sequence[tuple[float, float]]) -> dict[str, float]:
    """The numbers a reader wants about one variant's section, in layout units."""
    rows: Section = [(float(a), float(u)) for a, u in section]
    out = transform(name, rows)
    _west, east = cradle_edges(rows)
    edge_across, edge_up = rows[east]
    top = max(u for _a, u in out)
    floor = min(u for _a, u in out)
    half = max(a for a, _u in out)
    control_face = max(u for _a, u in rows) - edge_up
    return {
        "points": float(len(out)),
        "cradle_half": edge_across,
        "cradle_depth": edge_up - floor,
        "section_half": half,
        "face_height": top - edge_up,
        "face_height_control": control_face,
        "face_run": half - edge_across,
        "face_angle_deg": math.degrees(
            math.atan2(top - edge_up, max(half - edge_across, 1e-9))
        ),
        "load_bearing_p99": control_face * LOAD_BEARING_P99,
        "load_bearing_max": control_face * LOAD_BEARING_MAX,
        "clears_p99": float((top - edge_up) >= control_face * LOAD_BEARING_P99),
        "overshoot_max": max(0.0, control_face * LOAD_BEARING_MAX - (top - edge_up)),
    }
