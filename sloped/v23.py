"""V23's visual configuration: one environment, one machine pass, one place.

**V23 is a repaint, not a re-cut.** Every frame of V22.1 comes back at the same
instant of the same race, from the same camera, under the same edit. What
changes is the world the race happens in and the colours the machine is painted
in, and those are two independent selections:

    environment = aurora_valley    the sky, the haze, the ranges, the ground,
                                   the light rig and the zone practicals
    machine     = v23b             the body, the structure and the zone lines

Neither reaches the other. `aurora_valley.json` names twenty world surfaces and
`lab_palette.MACHINE_PASSES["v23b"]` names twenty-five machine surfaces, and the
two sets do not intersect - `tests/test_sloped_v23_integration.py` fails if they
ever do. That is what makes a future country skin or a second course a matter of
swapping one of these two strings rather than forking a theme.

**Why the strings live here rather than in the two tools that need them.**
`tools/sloped_v22.py` renders the masters and `tools/sloped_short.py` cuts the
film, and each has its own edition table. If the pair were written out in both,
an edition could be rendered under one world and QC'd against another, and
nothing would say so - the frames would simply be of a film nobody assembled.
So both tables import `SCENE_FLAGS` from here, and there is exactly one line in
the repository that says what V23 looks like.
"""

from __future__ import annotations

#: The `EnvironmentProfile` V23's world is built from. See
#: `godot/assets/marble_machine/environment/profiles/aurora_valley.json`.
ENVIRONMENT = "aurora_valley"

#: The machine colour pass V23's machine is painted under. See
#: `lab_palette.MACHINE_PASSES`. The lab shipped three; this is the balanced
#: one - `v23a` is subtler than the brief asks for and `v23c` trades marble
#: readability for zone identity.
MACHINE = "v23b"

#: **V22.1's one render flag, kept.** V23's finish parks up-course of the line,
#: which is the one place on the course from which the FINISH board is
#: unreadable: its face and its letters are on the down-course side. Dropping
#: this would change the picture at the finish for a reason that has nothing to
#: do with V23, so it travels with the edit it belongs to.
FINISH_SIGN = "--finish-sign=double"

#: What `tools/sloped_v22.py` hands Godot for a V23 render.
SCENE_FLAGS: tuple[str, ...] = (
    FINISH_SIGN,
    f"--environment={ENVIRONMENT}",
    f"--machine={MACHINE}",
)
