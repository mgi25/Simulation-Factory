"""The unconstricted start, and the instrument that measured it.

Two things are pinned here.

The **geometry**: that the architecture is what it claims to be. Its whole
premise is the absence of an early constriction, so the apron's width ratio,
the flatness of its pan and the fact that nothing narrows before the launch are
not incidental details - they are the hypothesis, and a regression in any of
them would leave a start called `wide_launch` that is a taper.

The **metric**: that "the field mixed" means what it should. The first version
of this lab counted midline crossings and reported 95% of racers crossing,
which a wide banked field satisfies trivially - the launch rolls 18 degrees and
the whole field slides over the centreline together, reordering nothing. A
metric that a bulk translation passes is worse than no metric, because it reads
as evidence. `lateral_order_correlation` is the replacement and these tests are
what stop it regressing to the same mistake.
"""

from __future__ import annotations

import math

import pytest

from sloped import course as _course
from sloped import layout
from sloped.startlab import (
    BARE_FAN,
    BENCH_PLANS,
    LAB_CHECKPOINTS,
    WIDE_BANK_MAX,
    WIDE_CANDIDATES,
    WIDE_FACTOR,
    TrialResult,
    start_machine,
    summarise,
)
from sloped.track import TrackRun
from sloped.widelaunch import WideLaunch, apron_table


@pytest.fixture(scope="module")
def start():
    launch = TrackRun("launch", width_profile=(WIDE_FACTOR, 117, 118))
    return WideLaunch("start", launch)


# --- the fifth topology is registered and distinct ------------------------


def test_wide_launch_is_a_registered_start_kind():
    assert WideLaunch.START_KIND == "wide_launch"
    assert _course.START_CLASSES["wide_launch"] is WideLaunch
    # Membership and distinctness, not a count - see the note in
    # tests/test_sloped_start_kind.py.
    assert "wide_launch" in _course.START_KINDS
    assert len(set(_course.START_KINDS)) == len(_course.START_KINDS)


def test_every_topology_still_builds_the_class_its_name_promises():
    """The four gates from V1.5 must keep holding as kinds are added."""
    for kind in _course.START_KINDS:
        machine = start_machine(plan=BENCH_PLANS[kind])
        assert machine.start_kind == kind
        assert type(machine.modules["start"]) is _course.START_CLASSES[kind]


def test_the_shipped_course_is_untouched():
    assert _course.START_KIND == "fan"
    assert _course.check() == []


# --- the architecture is the absence of a constriction --------------------


def test_the_apron_does_not_narrow(start):
    """The premise. `START_BACK_HALF` is 2.73 and the widened launch's entry
    half is 2.786, so the apron between them is a constant-width ramp - not a
    property that was chosen, one that the two numbers happen to have."""
    table = apron_table(start)
    assert table["spread"]["width_ratio"] < 1.05
    assert min(row["width"] for row in table["rows"]) > 5.0


def test_several_marbles_fit_abreast_the_whole_way(start):
    """Section 4: at the mixing checkpoint racers must still be able to travel
    side by side and change lateral position freely."""
    table = apron_table(start)
    assert table["spread"]["narrowest_marbles_abreast"] >= 8


def test_the_pan_is_flat_across_where_the_field_rests(start):
    """A dished pan rests its outer bays higher, which is a per-bay energy
    difference; the fan's trough had one for three sessions unnoticed."""
    seats = start.marble_starts()
    heights = [seat.position[1] for seat in seats]
    assert max(heights) - min(heights) < 1e-9
    for row in apron_table(start)["rows"][:5]:
        assert row["cross_slope_deg"] == pytest.approx(0.0, abs=1e-6)


def test_there_are_no_grooves_and_so_no_lanes(start):
    """Section 6: once the gate opens the racers enter one shared surface."""
    assert start.GROOVE_TO == 0.0
    for u in (0.0, 0.05, 0.2, 0.5, 1.0):
        for across in (-1.0, -0.315, 0.0, 0.315, 1.0):
            assert start._groove(u, across) == 0.0


def test_the_apron_has_a_floor_behind_the_resting_line(start):
    """Twice-learnt: a marble seeded on the mesh's first row tips backwards off
    it. V1.5's radial apron had the same hole in a different shape."""
    assert start.heel_u < 0.0
    heel = start.centre_at(start.heel_u)
    assert heel[2] == pytest.approx(start.PAN_BACK, abs=1e-9)
    # And the heel is *above* the line, so a resting marble rolls forward.
    assert heel[1] > start.pan_floor


def test_the_apron_never_climbs(start):
    previous = None
    for step in range(241):
        u = start.heel_u + (1.0 - start.heel_u) * step / 240.0
        point = start.centre_at(u)
        if previous is not None:
            assert point[1] <= previous + 1e-12
        previous = point[1]


def test_the_grade_matches_the_launch_at_the_seam(start):
    """A corner at the seam throws a marble: 6 degrees at 20 layout units per
    second is a 0.6-unit hop."""
    assert start.grade_deg(1.0) == pytest.approx(start.SEAM_GRADE, abs=0.01)
    assert start.grade_deg(0.0) == pytest.approx(start.HEAD_GRADE, abs=0.01)


def test_the_lift_is_derived_and_far_below_the_radials(start):
    """Section 16: the radial start's 4.30 is not inherited."""
    assert start.lift < 1.5
    # And it is exactly what the grade profile over the plan run asks for.
    assert start.fall(1.0) == pytest.approx(
        start.plan_run * start.mean_grade(), rel=1e-9
    )


def test_the_paddles_stand_at_their_own_bays(start):
    """`StartGrid.local_actuators` places from the fan's trough; V1.5's radial
    start inherited that and a paddle ended up out on the apron."""
    paddles = [a for a in start.local_actuators() if a.name.startswith("paddle")]
    seats = start.marble_starts()
    assert len(paddles) == layout.BAYS
    for index, paddle in enumerate(paddles):
        assert math.dist(paddle.rest.position, seats[index].position) < 1.0


def test_the_wide_runs_carry_a_gentler_bank():
    """Bank times width is lateral energy, and 18 degrees over a 2.79 half
    width gives a marble more than the guard can hold."""
    machine = start_machine(plan=WIDE_CANDIDATES["open-sweep"])
    for name in ("launch", "leg1"):
        banks = [abs(math.degrees(b)) for b in machine.runs[name].banks]
        assert max(banks) <= WIDE_BANK_MAX + 1e-6
    # And the centreline is untouched, so the checkpoints still mean what they
    # meant: bank rolls the section, it does not move the path.
    plain = TrackRun("launch")
    wide = machine.runs["launch"]
    assert wide.sim_arc[-1] == pytest.approx(plain.sim_arc[-1], abs=1e-9)


def test_the_mesh_is_clean(start):
    from marble3d.validation import check_mesh

    assert check_mesh(start.local_colliders()[0], expect_components=None) == []


# --- the three candidates, and only three --------------------------------


def test_there_are_three_candidates_and_they_share_everything_but_the_mixing():
    """Section 7: structural alternatives, not a parameter scan."""
    assert len(WIDE_CANDIDATES) == 3
    for plan in WIDE_CANDIDATES.values():
        assert plan.start_kind == "wide_launch"
        assert plan.launch_width == WIDE_CANDIDATES["open-sweep"].launch_width
        assert plan.leg1_width == WIDE_CANDIDATES["open-sweep"].leg1_width
        assert plan.wide_bank_max == WIDE_CANDIDATES["open-sweep"].wide_bank_max


def test_the_wide_candidates_carry_no_channel_sized_furniture():
    """The shipped mixer and wheel are sized for 1.88; on a 5.57-wide field
    they stop spanning the course and become obstructions in its middle."""
    assert WIDE_CANDIDATES["open-sweep"].wheels == ()
    assert WIDE_CANDIDATES["open-sweep"].mixers == ()
    assert BARE_FAN.start_kind == "fan"
    assert BARE_FAN.mixers == () and BARE_FAN.wheels == ()


def test_the_narrowing_finishes_before_leg1_rolls_into_its_turn():
    """`lw-plain` narrowed into a banked turn and lost 34% of the field."""
    factor, hold_to, blend_to = WIDE_CANDIDATES["open-sweep"].leg1_width
    assert blend_to <= 78, "the narrowing must end before leg1[80]"
    assert blend_to - hold_to >= 40, "and it must be long"
    plain = TrackRun("leg1")
    assert abs(math.degrees(plain.banks[hold_to])) < 4.0


# --- the metric that a bulk translation must not pass --------------------


def _result(kind: str, seed: int, across: dict[int, float]) -> TrialResult:
    names = [name for name, _ in LAB_CHECKPOINTS]
    return TrialResult(
        start_kind=kind,
        seed=seed,
        seconds=0.0,
        slot_of={m: m for m in range(8)},
        ranks={n: {m: m + 1 for m in range(8)} for n in names},
        progress={n: {m: float(m) for m in range(8)} for n in names},
        exit_order={m: m + 1 for m in range(8)},
        collisions={m: 0 for m in range(8)},
        wall_ticks={m: 0 for m in range(8)},
        across={n: dict(across) for n in names},
        reach={m: 1.0 for m in range(8)},
        crossings={m: 1 for m in range(8)},
        lost={},
        stuck={},
        through={m: 1.0 for m in range(8)},
        reached=len(LAB_CHECKPOINTS),
    )


def test_a_field_that_only_translates_reports_its_order_kept():
    """**The whole point of the metric.** Every racer has crossed the midline
    and not one has changed places with another; the answer must be 1.0.
    """
    translated = {slot: (slot - 3.5) * 0.2 + 5.0 for slot in range(8)}
    report = summarise([_result("wide_launch", s, translated) for s in range(4)])
    for name, _ in LAB_CHECKPOINTS:
        assert report["lateral_order_correlation"][name] == pytest.approx(1.0)


def test_a_field_whose_lateral_order_is_reversed_reports_minus_one():
    reversed_order = {slot: -(slot - 3.5) * 0.2 for slot in range(8)}
    report = summarise([_result("wide_launch", s, reversed_order) for s in range(4)])
    assert report["lateral_order_correlation"]["exit"] == pytest.approx(-1.0)


def test_a_shuffled_field_reports_no_lateral_order():
    """Averaged over trials whose shuffles differ, a mixed field tends to 0."""
    shuffles = [
        {0: 0.3, 1: -0.5, 2: 0.9, 3: -0.1, 4: 0.5, 5: -0.9, 6: 0.1, 7: -0.3},
        {0: -0.9, 1: 0.5, 2: -0.1, 3: 0.9, 4: -0.5, 5: 0.1, 6: -0.3, 7: 0.3},
    ]
    report = summarise(
        [_result("wide_launch", index, order) for index, order in enumerate(shuffles)]
    )
    assert abs(report["lateral_order_correlation"]["exit"]) < 0.35


def test_the_report_names_where_the_field_was_lost():
    """A percentage cannot say whether the loss is the release, the seam, the
    open field or the narrowing, and those are four different repairs."""
    base = _result("wide_launch", 0, {m: 0.0 for m in range(8)})
    base.lost[3] = ("leg1", 90)
    base.lost[4] = ("leg1", 92)
    base.stuck[5] = ("launch", 10)
    report = summarise([base])
    assert report["loss_sites"]["leg1[70..79%]"] == 2
    assert report["loss_sites"]["launch[0..9%]"] == 1


def test_summarise_still_reports_the_slot_and_centre_correlations():
    """Two shapes of bias, and a plain slot correlation cannot see the second:
    a centre-versus-edge advantage is symmetric."""
    report = summarise(
        [_result("wide_launch", s, {m: 0.0 for m in range(8)}) for s in range(3)]
    )
    # slot i always ranks i+1 here, so the slot correlation is exactly +1.
    assert report["slot_rank_correlation"]["exit"] == pytest.approx(1.0)
    assert report["centre_rank_correlation"]["exit"] is not None
