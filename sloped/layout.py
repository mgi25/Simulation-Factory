"""Layout B, ZIG-ZAG RACEWAY, transcribed from the branch that locked it.

## Why the control points and not the recorded centreline

`docs/validation/sloped_course/physics_layout.json` is the geometry contract
and this module is checked against it, but it is not the source read here, for
one reason: its `centreline` is `_thinned(path, 26)` - every fifth sample of a
132-point curve. Interpolating 26 points back into a channel gives a path that
crosses the real one at 26 places and cuts the corner between them, and the
corners are where the hairpins are.

The control points in `course_layout.gd` are what the visible track was built
from, so `sloped.pathing.build_path` applied to them reproduces the built curve
exactly rather than approximately. The JSON then becomes what a contract should
be: an independent record to check the reconstruction against.
`sloped.contract.check()` does that, on every one of the 26 recorded points of
all seven runs, plus the recorded lengths, drops, widths, floor offsets, bank
extremes and module anchors.

Everything in this module is in **layout units** - the units the stills were
photographed in. `sloped.scale` is the only thing that converts.

## The numbers that came out of `v2_track.gd`

The channel cross-section is not in the JSON at all - the JSON records the
clear width and the floor offset and stops - so the profile below is
transcribed from the asset. It matters more than the width does: the floor is a
*circular cradle* of radius 2.20 whose lowest point is 0.26 under the
centreline, and a marble in a cradle is centred by its own weight where a
marble on a flat pan wanders between the walls and ticks off each one.
"""

from __future__ import annotations

import math

__all__ = [
    "TITLE",
    "LAYOUT_KEY",
    "MARBLE_RADIUS",
    "HERO_SCALE",
    "BRANCH_SCALE",
    "CHANNEL_HALF",
    "HERO_CLEAR_WIDTH",
    "FLOOR_RADIUS",
    "FLOOR_Y",
    "LIP_CROWN",
    "GUARD_BASE",
    "GUARD_HEIGHT",
    "GUARD_INNER",
    "CONTAINMENT_TOP",
    "RUNS",
    "NODES",
    "TERRAIN",
    "BAYS",
    "BAY_PITCH",
    "GROOVE_LENGTH",
    "DECK_TOP",
    "GATE_Z",
    "GATE_HEIGHT",
    "START_BACK_HALF",
    "START_FRONT_HALF",
    "MIXER_PIN_RADIUS",
    "MIXER_PIN_PITCH",
    "MIXER_ROW_Z",
    "MIXER_ROW_COUNTS",
    "SPINNER_Z",
    "SPINNER_PHASE",
    "SPINNER_BLADES",
    "SPINNER_BLADE_THICK",
    "SPINNER_TIP_VISUAL",
    "SPLIT_WEDGE",
    "FINISH_LANES",
    "FINISH_LANE_PITCH",
    "floor_y_at",
    "run",
    "run_names",
    "channel_half_for",
    "cradle_radius_for",
    "floor_offset_for",
]

TITLE = "B  ZIG-ZAG RACEWAY"
LAYOUT_KEY = "b"

# `course_layout.gd`
MARBLE_RADIUS = 0.285
HERO_SCALE = 1.0
BRANCH_SCALE = 0.82

# --- the channel profile, from `v2_track.gd` -----------------------------
#
# PROFILE_SCALE there is HERO_CLEAR_WIDTH / (CHANNEL_HALF * 2) = 1.0 exactly,
# so it is absent here rather than carried as a multiplication by one.

CHANNEL_HALF = 0.94            # authored half width between the inner walls
HERO_CLEAR_WIDTH = 1.88        # three 0.57 racers abreast plus clearance
FLOOR_RADIUS = 2.20            # the running cradle's radius
FLOOR_Y = -0.260               # the cradle's lowest point, under the centreline
LIP_CROWN = 0.302              # the top of the rolled lip
GUARD_BASE = 0.280             # where the acrylic guard stands on the lip
GUARD_HEIGHT = 0.26
GUARD_INNER = 1.002            # the guard's inner face, across the channel
CONTAINMENT_TOP = GUARD_BASE + GUARD_HEIGHT      # 0.540

# The inner face of the rolled lip, from `v2_track.channel_section`'s authored
# half - the four points between the cradle's edge and the crown. This is the
# surface a marble climbing the wall actually meets, so the collider traces it
# rather than standing a straight wall at the cradle's edge and leaving a gap
# the marble would visibly pass through.
LIP_INNER = (
    (0.950, -0.010),
    (0.970, 0.080),
    (0.985, 0.180),
    (1.000, 0.265),
)


def floor_y_at(across: float, half: float = CHANNEL_HALF) -> float:
    """`v2_track._floor_y_at`: the running cradle, a circular arc.

    Clamped at the channel edge exactly as the asset clamps it, so the collider
    and the visible floor agree at the one place the difference would show.
    """
    span = min(abs(across), half)
    rise = FLOOR_RADIUS - math.sqrt(max(FLOOR_RADIUS * FLOOR_RADIUS - span * span, 0.0))
    return FLOOR_Y + rise


# --- the seven runs -----------------------------------------------------

RUNS = (
    {
        "name": "launch",
        "role": "descent",
        "scale": HERO_SCALE,
        "bank_gain": 2.6,
        "bank_max": 18.0,
        "controls": (
            (-17.00, 37.90, -33.60),
            (-16.20, 37.10, -32.30),
            (-14.80, 35.40, -31.00),
            (-12.40, 33.40, -29.80),
            (-9.40, 32.20, -29.00),
            (-6.80, 31.60, -28.50),
        ),
    },
    {
        "name": "leg1",
        "role": "long",
        "scale": HERO_SCALE,
        "bank_gain": 3.6,
        "bank_max": 28.0,
        "controls": (
            (-6.80, 31.60, -28.50),
            (0.60, 30.20, -27.40),
            (6.20, 29.00, -26.20),
            (11.60, 27.60, -24.40),
            (16.00, 26.20, -21.80),
            (18.60, 24.90, -18.80),
            (18.80, 24.00, -16.00),
            (17.00, 23.50, -13.80),
            (14.00, 23.20, -12.60),
            (11.20, 23.15, -12.40),
        ),
    },
    {
        "name": "leg2",
        "role": "long",
        "scale": HERO_SCALE,
        "bank_gain": 3.0,
        "bank_max": 22.0,
        "controls": (
            (11.20, 23.15, -12.40),
            (3.80, 22.20, -11.40),
            (-1.80, 21.20, -10.20),
            (-7.40, 20.20, -8.60),
            (-12.60, 19.40, -6.20),
            (-16.20, 18.60, -3.00),
            (-16.80, 17.90, 0.40),
            (-14.40, 17.50, 2.40),
            (-11.40, 17.20, 2.90),
            (-9.00, 17.05, 3.16),
            (-6.40, 16.90, 3.50),
        ),
    },
    {
        "name": "leg3",
        "role": "long",
        "scale": HERO_SCALE,
        "bank_gain": 3.4,
        "bank_max": 26.0,
        "controls": (
            (-6.40, 16.90, 3.50),
            (-0.60, 16.00, 4.60),
            (5.40, 15.00, 6.20),
            (10.60, 13.90, 8.60),
            (13.60, 12.70, 11.80),
            (13.20, 11.70, 14.80),
            (10.40, 11.00, 16.80),
            (7.40, 10.70, 17.60),
            (6.00, 10.60, 17.80),
        ),
    },
    {
        "name": "blue",
        "role": "branch",
        "scale": BRANCH_SCALE,
        "bank_gain": 3.0,
        "bank_max": 24.0,
        "controls": (
            (5.20, 10.40, 18.55),
            (-0.80, 9.30, 21.40),
            (-6.80, 8.50, 23.40),
            (-12.40, 7.60, 25.40),
            (-15.20, 6.70, 28.60),
            (-13.40, 5.90, 31.80),
            (-9.60, 5.40, 33.80),
            (-6.00, 5.18, 34.60),
            (-3.20, 5.00, 35.40),
            (-1.10, 4.90, 36.05),
        ),
    },
    {
        "name": "orange",
        "role": "branch",
        "scale": BRANCH_SCALE,
        "bank_gain": 4.0,
        "bank_max": 32.0,
        "controls": (
            (6.90, 10.40, 18.55),
            (13.00, 9.20, 21.00),
            (18.40, 8.20, 23.60),
            (21.00, 7.20, 27.00),
            (19.40, 6.30, 30.60),
            (15.00, 5.60, 33.20),
            (10.00, 5.20, 34.60),
            (5.60, 5.18, 34.70),
            (3.20, 5.00, 35.45),
            (1.10, 4.90, 36.05),
        ),
    },
    {
        "name": "final",
        "role": "sprint",
        "scale": HERO_SCALE,
        "bank_gain": 2.2,
        "bank_max": 14.0,
        "controls": (
            (0.00, 4.85, 36.40),
            (2.60, 4.15, 37.60),
            (5.80, 3.30, 39.00),
            (9.20, 2.55, 40.40),
            (12.60, 1.95, 41.70),
            (15.80, 1.45, 42.90),
            (18.40, 1.12, 43.90),
            (19.80, 1.02, 44.40),
        ),
    },
)

NODES = {
    "start": (-18.60, 38.55, -37.20),
    "mix": (-5.60, 31.45, -28.35),
    "obstacle": (-9.00, 17.05, 3.16),
    "split": (6.00, 10.50, 18.00),
    "merge": (0.00, 4.88, 36.10),
    "finish": (24.20, 0.70, 46.20),
}

TERRAIN = {
    "top_y": 39.6,
    "z_top": -34.0,
    "grade": 0.45,
    "steps": ((-30.0, 5.2, 4.4), (-13.0, 2.2, 5.0), (1.5, 2.4, 5.0), (16.0, 2.2, 5.4), (32.0, 2.8, 6.0)),
    "left_at": 20.0,
    "left_span": 26.0,
    "left_rise": 17.0,
    "gorge_at": 15.0,
    "gorge_span": 24.0,
    "gorge_depth": 28.0,
    "pads": (
        (-19.4, -38.9, 6.6, 7.0, 37.2),
        (-8.6, 3.2, 5.0, 6.0, 16.4),
        (6.0, 18.0, 4.6, 6.0, 9.8),
        (24.2, 46.2, 11.0, 12.5, -2.4),
    ),
}

# --- module geometry, from `course_modules.gd` --------------------------

BAYS = 8
BAY_PITCH = 0.63
GROOVE_LENGTH = 3.40
DECK_TOP = 0.0
START_BACK_HALF = 6.30 * 0.5 - 0.42      # 2.73, the trough at the gate
START_FRONT_HALF = 1.02                  # and where it hands off to the channel
GATE_Z = -GROOVE_LENGTH + 0.18           # -3.22
GATE_HEIGHT = 0.42                       # the paddle that holds one racer

MIXER_PIN_RADIUS = 0.075
MIXER_PIN_PITCH = 0.52
MIXER_ROW_Z = (-0.24, 0.24)
MIXER_ROW_COUNTS = (5, 4)

SPINNER_Z = (-1.62, 0.0, 1.62)
SPINNER_PHASE = 1.05                     # radians between neighbours, from the asset
SPINNER_BLADES = 4
SPINNER_BLADE_THICK = 0.15
SPINNER_TIP_VISUAL = 1.39                # blade box 1.34 long at radius 0.72

SPLIT_WEDGE = {"width": 1.05, "height": 1.20, "length": 3.40, "at": (0.0, -0.05, 1.30)}

FINISH_LANES = 8
FINISH_LANE_PITCH = 1.32


# --- accessors ----------------------------------------------------------


def run_names() -> tuple[str, ...]:
    return tuple(str(entry["name"]) for entry in RUNS)


def run(name: str) -> dict:
    for entry in RUNS:
        if entry["name"] == name:
            return entry
    raise KeyError(f"layout B has no run {name!r}; it has {run_names()}")


def channel_half_for(name: str) -> float:
    """The clear half width of one run, in layout units."""
    return CHANNEL_HALF * float(run(name)["scale"])


def cradle_radius_for(name: str) -> float:
    return FLOOR_RADIUS * float(run(name)["scale"])


def floor_offset_for(name: str) -> float:
    return FLOOR_Y * float(run(name)["scale"])
