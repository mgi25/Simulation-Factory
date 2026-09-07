"""The one place layout units and simulation units meet.

## The problem

Two frozen contracts disagree about how big a marble is.

`marble3d.units` says 0.5 world units, and that number is not a preference. It
is the similarity transform the physics core is built on: Bullet's fixed
tolerances - a 0.04 default collision margin, a contact-breaking threshold, a
CCD penetration budget - are absolute lengths, so a machine authored fifty
times below the scale the engine expects does not survive it. The core's own
docstring records what that cost the physics lab: a marble at rest on a bowl
wall flung from radius 0.30 to 0.43 in half a second, gaining 0.7 m/s out of
nothing, because every contact was being generated a margin deep.

The approved sloped course says 0.285, because that is what its channel, its
eight start bays, its spinner blades and its finish lanes were authored
around, and `marble-sloped-course-lab` is locked. Its silhouette is the
deliverable; re-proportioning it is exactly what section 7 of the brief
forbids.

## The resolution

Simulate at the core's scale and present at the layout's. One factor:

    LAYOUT_TO_SIM = 0.5 / 0.285 = 1.754386

Every length read out of the layout - a control point, a channel width, a
floor radius, a bay pitch, a blade reach - is multiplied by it on the way in.
Nothing is divided by it on the way out inside Python: the replay is written
in simulation units, because the replay is the physics' own record and a
record in units the physics does not use is a record that can disagree with
the run that produced it.

The conversion happens once more, in Godot, and in one line: the marbles are
parented to a node scaled by `SIM_TO_LAYOUT`. A uniform scale on a parent
scales its children's translations *and* their radii, so one number puts an
0.5-unit marble at the right size and the right place on a course authored for
an 0.285-unit one. There is no second multiply to forget.

## Why this is a scale and not a re-tuning

Under `L -> S*L`, `g -> S*g`, Newton's second law is invariant in time: every
length, velocity and acceleration scales by S and every time, angular
velocity, dimensionless ratio and collision outcome does not. So the sloped
course simulated at 1.754386x its authored size under the core's 245.25 wu/s^2
is geometrically similar to the same course at authored size under 139.79, and
it runs on the same clock - a 40-second race is 40 seconds either way. What
changes is that every calibrated absolute in `marble3d.config` - the 0.001
mesh margin, the 0.2 swept-sphere radius, the 0.5-diameter travel budget, the
4%-of-a-radius sagitta - stays exactly the number that was measured, and
240 Hz means what it meant on `marble-v1`.

The alternative - simulating at 0.285 and scaling those constants down to
match - would mean re-deriving six measured numbers from a similarity argument
instead of applying the argument once, here.
"""

from __future__ import annotations

from marble3d.units import MARBLE_RADIUS

__all__ = [
    "LAYOUT_MARBLE_RADIUS",
    "LAYOUT_TO_SIM",
    "SIM_TO_LAYOUT",
    "to_sim",
    "to_sim_point",
    "to_layout",
    "to_layout_point",
    "describe",
]

# What the approved course was authored around: `course_layout.gd`'s
# MARBLE_RADIUS, and the same number in physics_layout.json's `marble` block.
LAYOUT_MARBLE_RADIUS = 0.285

LAYOUT_TO_SIM = MARBLE_RADIUS / LAYOUT_MARBLE_RADIUS      # 1.754386...
SIM_TO_LAYOUT = LAYOUT_MARBLE_RADIUS / MARBLE_RADIUS      # 0.57


def to_sim(length: float) -> float:
    """A layout length in simulation units."""
    return float(length) * LAYOUT_TO_SIM


def to_sim_point(point) -> tuple[float, float, float]:
    """A layout point in simulation units. Uniform - the frames agree."""
    return (
        float(point[0]) * LAYOUT_TO_SIM,
        float(point[1]) * LAYOUT_TO_SIM,
        float(point[2]) * LAYOUT_TO_SIM,
    )


def to_layout(length: float) -> float:
    """A simulation length back in layout units. For reporting and for Godot."""
    return float(length) * SIM_TO_LAYOUT


def to_layout_point(point) -> tuple[float, float, float]:
    return (
        float(point[0]) * SIM_TO_LAYOUT,
        float(point[1]) * SIM_TO_LAYOUT,
        float(point[2]) * SIM_TO_LAYOUT,
    )


def describe() -> str:
    return (
        f"layout marble radius {LAYOUT_MARBLE_RADIUS} -> sim {MARBLE_RADIUS}\n"
        f"layout -> sim  x{LAYOUT_TO_SIM:.9f}\n"
        f"sim -> layout  x{SIM_TO_LAYOUT:.9f}   (Godot: one scale on the marble root)"
    )
