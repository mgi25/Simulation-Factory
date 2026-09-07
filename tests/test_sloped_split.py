"""The fork, the two instrument bugs that hid it, and the geometry that fixes it.

`docs/sloped_race_v1.md` reported the orange route unreachable over 600 races
and six divider configurations. Two of those three sentences were about
instruments rather than about geometry, and both are pinned here so the claim
cannot come back.
"""

from __future__ import annotations

import math

import pytest

from sloped import joins, layout
from sloped.course import MERGE_GUARD_WINDOW, sloped_course
from sloped.race import ROUTE_RUNS, SlopedRace
from sloped.track import TrackRun


# --- the instrument bugs --------------------------------------------------


def test_an_uncommitted_marble_may_be_located_on_either_route():
    """`sloped.race._locate` filtered its candidates by a route the marble had
    not chosen, and the fallback was blue.

    `_route_from_place` only ever returns "orange" for a marble located on
    `orange_lead` or `orange`, so with those two filtered out no marble could
    ever be assigned the orange route - which is what V1's "no configuration
    ever put a marble on the orange lobe" was measuring.
    """
    race = SlopedRace(sloped_course(routes="both"), seed=0)
    try:
        marble = next(iter(race.results))
        assert race.results[marble].route is None
        open_to = race._runs_open_to(marble)
        assert "orange_lead" in open_to and "orange" in open_to
        assert "blue_lead" in open_to and "blue" in open_to

        # Once committed, the search narrows to that route's own runs.
        race.results[marble].route = "orange"
        committed = race._runs_open_to(marble)
        assert committed == tuple(
            name for name in ROUTE_RUNS["orange"] if name in race.runs
        )
        assert "blue" not in committed
    finally:
        race.close()


def test_a_marble_on_oranges_floor_is_not_booked_as_having_left_the_course():
    """`sloped.splitlab` measured containment against the run a marble was
    located on, and orange's mouth is a channel half-width east of leg3's
    centreline - so a marble that crossed correctly onto orange read as two
    half-widths outside leg3 and was retired before it could land.
    """
    from sloped.splitlab import SplitEntry, split_machine

    machine = split_machine(speed=43.0, offsets=(0.0,))
    entry = SplitEntry(machine)
    try:
        orange_lead = machine.runs["orange_lead"]
        # A point sitting on orange's lead, well clear of leg3's channel.
        seat = orange_lead.seat_at(8, 0.0)
        assert entry._outside("orange_lead", 8, seat) <= 0.0
        # ...and the same point measured against leg3 is outside it, which is
        # exactly the reading the first version retired a marble on.
        leg3 = machine.runs["leg3"]
        near = min(
            range(len(leg3.sim_path)), key=lambda i: math.dist(seat, leg3.sim_path[i])
        )
        assert entry._outside("leg3", near, seat) > 0.0
    finally:
        entry.sim.close()


# --- the geometry ---------------------------------------------------------


def test_every_run_falls_all_the_way_down():
    """A gravity course cannot climb, and orange used to.

    Ten consecutive uphill samples, 86 to 95, from a Catmull-Rom overshooting
    through four control heights inside half a unit of each other. Every other
    run was already strictly monotone.
    """
    machine = sloped_course(routes="both")
    for name, run in machine.runs.items():
        climbs = [
            index
            for index in range(1, len(run.path))
            if run.path[index][1] > run.path[index - 1][1] + 1e-9
        ]
        assert climbs == [], f"{name} climbs at samples {climbs[:12]}"


def test_oranges_tail_falls_at_about_blues():
    """The redistributed heights, checked as a gradient rather than as three
    numbers - blue's tail is the reference because blue's marbles finish."""
    machine = sloped_course(routes="both")
    orange = machine.runs["orange"]
    blue = machine.runs["blue"]
    tail = [joins.grade_of(orange.path, index) for index in range(80, 112, 8)]
    reference = joins.grade_of(blue.path, 96)
    for grade in tail:
        assert grade < -0.03, f"orange's tail is nearly level at {grade}"
        assert grade == pytest.approx(reference, abs=0.03)


def test_only_oranges_three_tail_heights_differ_from_the_authored_table():
    """The one deviation from the layout contract, named so it cannot grow."""
    authored = {6: 5.20, 7: 5.18, 8: 5.00}
    controls = layout.run("orange")["controls"]
    for index, (x, y, z) in enumerate(controls):
        if index in authored:
            assert y != pytest.approx(authored[index], abs=1e-6)
            assert abs(y - authored[index]) < 0.15
    # And nothing moved in plan.
    assert [c[0] for c in controls] == [6.90, 13.00, 18.40, 21.00, 19.40, 15.00, 10.00, 5.60, 3.20, 1.10]
    assert [c[2] for c in controls] == [18.55, 21.00, 23.60, 27.00, 30.60, 33.20, 34.60, 34.70, 35.45, 36.05]


def test_oranges_lead_starts_at_leg3s_own_roll():
    """Two cradles rolled 26 degrees apart are not one surface, whatever is put
    between them."""
    machine = sloped_course(routes="both")
    leg3 = machine.runs["leg3"]
    lead = machine.runs["orange_lead"]
    fork_roll = leg3.banks[joins.FORK_SAMPLE]
    assert math.degrees(fork_roll) == pytest.approx(26.0, abs=0.1)
    assert lead.banks[0] == pytest.approx(fork_roll, abs=1e-6)
    # And it decays monotonically to level rather than reversing sign.
    rolls = [math.degrees(b) for b in lead.banks]
    assert all(rolls[i] >= rolls[i + 1] - 1e-9 for i in range(len(rolls) - 1))
    assert rolls[-1] == pytest.approx(0.0, abs=0.5)


def test_oranges_mouth_is_up_leg3s_bank_and_does_not_overhang_it():
    """The mouth is east of leg3's centreline so orange is not a trench under
    it, and at hero width its west lip lands on leg3's centreline rather than
    past it."""
    machine = sloped_course(routes="both")
    leg3 = machine.runs["leg3"]
    lead = machine.runs["orange_lead"]
    sample = joins.FORK_SAMPLE
    lateral, _up, _forward = leg3.frames[sample]
    centre = leg3.sim_path[sample]
    offset = [lead.sim_path[0][axis] - centre[axis] for axis in range(3)]
    across = sum(offset[axis] * lateral[axis] for axis in range(3))
    half = 0.5 * leg3.clear_width * leg3.widths[sample]
    assert across == pytest.approx(half, rel=0.05), "the mouth sits on leg3's east edge"
    lead_half = 0.5 * lead.clear_width * lead.widths[0]
    assert across - lead_half >= -0.05, "orange's west lip overhangs leg3's centreline"
    assert across + lead_half > half, "orange's east guard must be the outer wall"


def test_the_sprints_rails_are_open_where_the_apron_covers_them():
    """A rail standing inside the apron is a ledge with a roof over it."""
    machine = sloped_course(routes="both")
    sprint = machine.runs["final"]
    assert sprint.open_side == MERGE_GUARD_WINDOW
    assert MERGE_GUARD_WINDOW[0] == 0.0, "both rails, not one"
    # Open across the apron, full again before the channel is on its own.
    assert sprint.wall_factor(0) == pytest.approx(TrackRun.OPEN_FLOOR)
    assert sprint.wall_factor(9) == pytest.approx(TrackRun.OPEN_FLOOR)
    assert sprint.wall_factor(20) == pytest.approx(1.0)
    section = sprint.section_at(4)
    full = sprint.section
    lowered = [a for (a, up), (_a2, up2) in zip(section, full) if up < up2 - 1e-9]
    assert any(a > 0 for a in lowered) and any(a < 0 for a in lowered)


def test_the_course_still_assembles_clean_both_ways():
    from sloped.course import check

    for routes in ("blue", "both"):
        assert check(sloped_course(routes=routes)) == []
