"""The contact check has to catch a marble in the geometry and nothing else.

Both of its gates were added *after* the first full check of the production
seed reported seventy findings and every one of them turned out to be the
measurement rather than the physics. That is exactly the situation in which a
check quietly stops checking, so these tests drive each gate from both sides: a
real fault of that kind is still reported, and the specific false positive that
motivated the gate is not.

The synthetic replays here are the smallest thing `check_replay` accepts - one
frame, one marble, placed by hand relative to a known sample of a known run -
because the point is to control the geometry exactly, which no recorded race
lets you do.
"""

from __future__ import annotations

import math

import pytest

from marble3d.units import MARBLE_RADIUS
from sloped.contact import (
    ALONG_TOLERANCE,
    FLOAT_BUDGET,
    PENETRATION_BUDGET,
    RESTING_RISE,
    RESTING_SPEED,
    check_replay,
)
from sloped.course import sloped_course


@pytest.fixture(scope="module")
def machine():
    return sloped_course()


def _replay(position, velocity=(0.0, 0.0, 0.0), run="launch"):
    """One frame, one marble, at a position given in simulation units."""
    return {
        "mode": "marble3d",
        "replay_fps": 60,
        "units": {"render_scale": 0.57, "layout_marble_radius": 0.285},
        "marbles": [{"id": 0, "radius": MARBLE_RADIUS}],
        "events": [{"t": 0.0, "kind": "route", "id": 0, "route": "blue"}],
        "frames": [
            {
                "t": 0.0,
                "marbles": [
                    {
                        "id": 0,
                        "p": [float(v) for v in position],
                        "q": [0.0, 0.0, 0.0, 1.0],
                        "v": [float(v) for v in velocity],
                        "w": [0.0, 0.0, 0.0],
                        "in": run,
                        "s": "running",
                    }
                ],
                "actuators": {},
            }
        ],
    }


# `check_replay` locates a marble by following it, and a marble it has not seen
# before is looked for in the first `WINDOW` samples of each run on its route.
# A synthetic one therefore has to be placed inside that window or the report
# counts it off-channel and measures nothing - which is what the first draft of
# these tests did, at sample 60, and it looked exactly like the check having
# gone blind.
ENTRY_SAMPLE = 10


def _at(machine, run_name: str, sample: int, across: float, up: float, along: float = 0.0):
    """A simulation-unit position offset from one sample's own frame."""
    run = machine.runs[run_name]
    lateral, up_axis, forward = run.frames[sample]
    centre = run.sim_path[sample]
    return [
        centre[axis]
        + lateral[axis] * across
        + up_axis[axis] * up
        + forward[axis] * along
        for axis in range(3)
    ]


# --- the along-track gate ------------------------------------------------


def test_a_marble_buried_in_the_cradle_is_still_reported(machine):
    ## The fault the check exists for: a marble inside the floor at a sample it
    ## really is beside. Half a radius under the cradle's lowest point.
    where = _at(machine, "launch", ENTRY_SAMPLE, across=0.0, up=-0.5 * MARBLE_RADIUS)
    report = check_replay(_replay(where), machine)
    assert report.by_kind().get("penetration") == 1
    assert report.worst_penetration < -PENETRATION_BUDGET


def test_a_marble_upstream_of_a_runs_first_sample_is_not_measured(machine):
    ## The false positive: sixty findings up to -0.4993 at `launch[0]`, all of
    ## them marbles still on the start grid's fan, 1.294 units - 6.3 sample
    ## steps - upstream of the sample they were compared to. There is no
    ## cross-section there to be inside of.
    run = machine.runs["launch"]
    step = math.dist(run.sim_path[0], run.sim_path[1])
    where = _at(machine, "launch", 0, across=1.293, up=-0.282, along=-1.294)
    report = check_replay(_replay(where), machine)
    assert report.findings == []
    assert report.channel_samples == 0
    assert report.off_channel_samples == 1
    # And the gate is loose enough that a sample's own neighbourhood is never
    # excluded: half a step is the most a nearest sample can be off by.
    assert ALONG_TOLERANCE * 0.5 * step > 0.5 * step


def test_the_gate_does_not_excuse_a_marble_beside_its_sample(machine):
    ## The gate must not become an escape hatch. Buried, at a legal along
    ## offset of just under half a sample step, is still a finding.
    run = machine.runs["launch"]
    step = math.dist(run.sim_path[ENTRY_SAMPLE], run.sim_path[ENTRY_SAMPLE + 1])
    where = _at(machine, "launch", ENTRY_SAMPLE, across=0.0, up=-0.5 * MARBLE_RADIUS, along=0.49 * step)
    report = check_replay(_replay(where), machine)
    assert report.by_kind().get("penetration") == 1


# --- the resting gate ---------------------------------------------------


def test_a_slow_marble_held_off_the_floor_is_reported(machine):
    ## A collider that holds a marble up wrongly: barely moving, and a clear
    ## gap under it. This is the float finding's whole purpose.
    where = _at(machine, "leg1", ENTRY_SAMPLE, across=0.0, up=4.0 * FLOAT_BUDGET)
    report = check_replay(_replay(where, velocity=(0.1, 0.0, 0.1)), machine)
    assert report.by_kind().get("floating") == 1
    assert report.worst_float > FLOAT_BUDGET


def test_a_marble_on_its_way_up_after_a_hit_is_not_resting(machine):
    ## The false positive: both float findings on the production seed were
    ## marbles climbing at 1.97 and 1.30 world units a second - one with a
    ## neighbour touching it and an obstacle blade 1.6 units away - whose total
    ## speed dipped under the resting threshold at the top of the arc. Rising
    ## is not resting.
    where = _at(machine, "leg1", ENTRY_SAMPLE, across=0.0, up=4.0 * FLOAT_BUDGET)
    rising = (0.5, 1.97, 0.5)
    assert math.hypot(*rising) < RESTING_SPEED      # slow by the old test
    assert abs(rising[1]) > RESTING_RISE            # and excluded by the new one
    report = check_replay(_replay(where, velocity=rising), machine)
    assert report.findings == []


def test_a_marble_sinking_slowly_is_still_not_resting(machine):
    ## Symmetric by construction, and deliberately so: a marble settling
    ## downward through the gap is mid-fall, not held up by anything.
    where = _at(machine, "leg1", ENTRY_SAMPLE, across=0.0, up=4.0 * FLOAT_BUDGET)
    report = check_replay(_replay(where, velocity=(0.2, -1.5, 0.2)), machine)
    assert report.findings == []


# --- the report itself --------------------------------------------------


def test_a_marble_seated_in_the_cradle_reports_nothing(machine):
    ## The baseline. A marble resting exactly one radius above the cradle's
    ## surface at the centreline is what every other case is measured against,
    ## and it has to be silent or nothing above means anything.
    run = machine.runs["leg1"]
    section = run.section_at(ENTRY_SAMPLE)
    floor = min(section, key=lambda point: point[1])[1]
    from sloped.scale import LAYOUT_TO_SIM

    where = _at(machine, "leg1", ENTRY_SAMPLE, across=0.0, up=floor * LAYOUT_TO_SIM + MARBLE_RADIUS)
    report = check_replay(_replay(where, velocity=(0.0, 0.0, 0.0)), machine)
    assert report.findings == []
    assert report.channel_samples == 1
