"""The Race #2 channel: the approved section, with the wall not scaled up.

## The trench

`sloped.track.channel_profile(scale)` multiplies the *whole* cross-section by
the run's profile scale - the clear width, the cradle radius, the floor drop,
the lip and the guard rail, all by the same factor. That is right for Race #1,
where the scale is 1.0 on the hero runs and 0.82 on the branch lobes and the
marble is the same size in both: a 0.82 branch is a smaller channel for the
same marble, which is what a branch should be.

Race #2 runs at scale 2.0 so that eight racers can spread across a pan, and the
marble is still 0.285. So the width doubled and **the wall doubled with it**:
1.08 layout units of containment above the cradle, against Race #1's 0.54.
That is 3.8 marble radii of rail around a marble that is 1.0 radius tall.

The cost is not containment. It is the camera. Seeing a marble in a channel
over its own near rail needs a depression angle of at least
`atan(containment / half width)`, measured in the channel's banked frame - and
at 1.08 of containment in a 1.5 half-width corridor that is **36 degrees**. The
brief asks for a low or moderate three-quarter view and rules out the map view;
36 degrees of look-down over every corridor is the map view. Seed 140's
`last_impact` was the measurement: four racers dead centre of frame by
projection, none of them visible in the render, every sightline crossing
`corr4`'s own guard at 94% of the way to the marble.

## The fix

Keep the cradle at the run's scale - that is the running surface, and it is
what makes a wide pan a dish rather than a pan - and **cap the rise above the
cradle** at an absolute height instead of a scaled one. Every profile point
above the cap is flattened onto it, so the lip and the rail keep their lateral
positions and lose only the part of their height that was buying nothing.

## What the cap costs, and how it is paid for

A cap alone is not free, and `tools/race2_wall.py` measured the bill over 40
seeds each:

    cap    finish   all-8   escape   look-down
    0.62    77.7%     13%    21.9%      20 deg
    0.85    97.2%     78%     2.5%      18 deg
    1.60    99.9%     99%     0.0%      50 deg   (uncapped, scale 2.0)

The tall wall was doing real work: a marble carrying 20 layout units a second
into a 4.8-radius hairpin rides most of the way up the outside, and at 0.62 it
rides over.

But the *whole run* does not need that wall - only the banked part of it does.
So the cap is 0.70 everywhere and the pans carry a **guard boost** over the
stretch where the bank is, which is the mechanism `sloped.track` already has
for exactly this and describes as "a containment repair belongs to a stretch
and not to a whole run". A pan ends up with 1.65 of rail through its turn and
a corridor with 0.70, and because a pan is also twice as wide the look-down
each demands comes out the same: 25 degrees over a pan, 28 over a corridor.
Both are the three-quarter view the brief asks for, and neither is the map.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from sloped import layout
from sloped.scale import to_sim
from sloped.track import TrackRun, channel_profile

__all__ = ["WALL_CAP", "capped_profile", "RaceRun"]

# How far the section may rise above the cradle's lowest point, in layout
# units, whatever the profile scale is.
#
# `RACE2_WALL_CAP` overrides it, which exists for one job: `tools/race2_wall.py`
# scans the cap against the escape rate, and a scan that had to edit the module
# between runs would be a scan whose runs were not comparable.
WALL_CAP = float(os.environ.get("RACE2_WALL_CAP", "1.10"))


def capped_profile(scale: float, cap: float = WALL_CAP) -> list[tuple[float, float]]:
    """The approved section at `scale`, with everything above `cap` flattened.

    Measured from the cradle's lowest point - `FLOOR_Y * scale` - so the cap is
    a height above the surface a marble rolls on and not above the centreline,
    which is where a reader would otherwise have to do the arithmetic.
    """
    floor = layout.FLOOR_Y * scale
    ceiling = floor + cap
    return [
        (across, min(up, ceiling)) for across, up in channel_profile(scale)
    ]


class RaceRun(TrackRun):
    """A `TrackRun` whose wall height does not scale with its width.

    Everything else is the parent's: the path, the bank law, the width curve,
    the taper, the width profile, the guard windows, the probes, the sockets.
    Only `section` and the containment scalar derived from it change, and they
    change after construction because the parent computes them from
    `channel_profile` in its own `__init__`.
    """

    def __init__(self, *args: Any, wall_cap: float | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.wall_cap = WALL_CAP if wall_cap is None else float(wall_cap)
        self.section = capped_profile(self.scale, self.wall_cap)
        # `containment` is the height a marble may reach before it counts as
        # having left the channel, measured from the cradle. The parent sets it
        # from the unscaled profile's own extremes; with the wall capped it is
        # the cap, and a check that used the old number would call a marble
        # sitting on the flattened rail "contained".
        self.containment = to_sim(self.wall_cap)
        # The collider is cached on first use and the parent may already have
        # built it from the uncapped section.
        self._mesh = None

    def wall_angle(self) -> float:
        """The depression a camera needs to see over the near rail, in degrees.

        Reported so `race2.camera`'s `MIN_LOOKDOWN` can be checked against the
        geometry rather than chosen, and so a future run that narrows past the
        point where the number is reasonable is visible as a number.
        """
        import math

        half = layout.CHANNEL_HALF * self.scale * max(self.widths)
        return math.degrees(math.atan2(self.wall_cap, max(half, 1e-6)))

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data["wall_cap"] = round(self.wall_cap, 4)
        data["wall_angle_deg"] = round(self.wall_angle(), 2)
        return data
