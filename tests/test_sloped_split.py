"""The fork, the two instrument bugs that hid it, and the geometry that fixes it.

`docs/sloped_race_v1.md` reported the orange route unreachable over 600 races
and six divider configurations. Two of those three sentences were about
instruments rather than about geometry, and both are pinned here so the claim
cannot come back.
"""

from __future__ import annotations

import math

import pytest

from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from sloped import joins, layout
from sloped.course import MERGE_GUARD_WINDOW, sloped_course
from sloped.race import ROUTE_RUNS, SlopedRace
from sloped.scale import to_sim
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


def test_the_merge_apron_stays_flush_with_blue_where_it_overlaps_it():
    """`blue[100..119]` was the dominant loss site in V1 and V1.1.

    The apron's floor used to continue upstream past blue's mouth on the chord
    to the sprint - falling at 0.159 per unit of `along` where blue's own
    channel falls at 0.200 - so the apron, a height field spanning the full
    width, rose into a shelf across blue's channel: +0.114 simulation units at
    the apron's back edge. A marble needs 7.5 wu/s to climb that, so the fast
    ones never noticed and the slow ones stopped dead.
    """
    machine = sloped_course()
    blue = machine.runs["blue"]
    merge = machine.modules["merge"]

    def apron_frame(point):
        offset = [point[axis] - merge.origin[axis] for axis in range(3)]
        return (
            sum(offset[axis] * merge.forward[axis] for axis in range(3)),
            sum(offset[axis] * merge.lateral[axis] for axis in range(3)),
            sum(offset[axis] * merge.up[axis] for axis in range(3)),
        )

    back = merge.BACK * 1.754386
    worst = 0.0
    for index in range(len(blue.sim_path) - 24, len(blue.sim_path)):
        along, across, rise = apron_frame(blue.surface_point(index, 0.0))
        if along < back:
            continue                       # upstream of the apron's own edge
        worst = max(worst, merge._floor(along, across) - rise)
    # What is left is blue's centreline riding the sprint cradle's wall, which
    # is a curved surface rather than a step, and it is a third of what a step
    # a marble could not climb would be.
    assert worst < 0.05, f"the apron stands {worst:.4f} over blue's channel"


def test_the_shoulder_is_flush_with_the_channel_and_never_over_it():
    """The property that replaced the chord, and the defect it replaced.

    The apron used to carry blue across the junction on a height field, and the
    two corrections made to that height field were both to its *gradient* -
    first the chord to the sprint, then blue's own fall. Neither could fix what
    was wrong, because the apron's cradle was centred on the sprint's
    centreline while blue's is up to 0.52 units off it, and its
    cradle-to-shoulder changeover ignored the width flare entirely.

    So there is no gradient to pin any more. What is pinned instead is that the
    shoulder's inner edge **is** the channel's own clear edge at every station,
    to within rounding, and that its surface there is the channel's own surface
    - which is what makes a step across the seam impossible rather than small.
    """
    machine = sloped_course()
    merge = machine.modules["merge"]
    runs = machine.runs
    back, front = to_sim(merge.BACK), to_sim(merge.FRONT)
    for step in range(21):
        along = back + (front - back) * step / 20
        centre, rise, half, edge, guard, scale = merge._channel_at(along)
        assert guard > half, (along, half, guard)
        for side in (-1.0, 1.0):
            inner, outer = merge._bounds(side)(along)
            assert abs(inner - (centre + side * half)) < 1e-9, (along, side)
            assert abs(outer) >= abs(inner), (along, side, inner, outer)
            # The shoulder's own height at its inner edge is the cradle's rise
            # at the clear edge, so the two surfaces meet rather than step.
            assert abs(merge._floor(along, inner) - (rise + edge)) < 1e-6, (along, side)


def test_the_shoulder_reads_the_width_flare_the_old_apron_ignored():
    """`final[0]` is 1.140 of its authored width, and that has to show.

    The old apron took its cradle-to-shoulder changeover from
    `CHANNEL_HALF * scale` - 1.649 units - while the sprint's own cradle edge
    is at 1.880, so the shoulder's quadratic rise began 0.23 units *inside* the
    running surface and stood 0.083 above the channel's floor at a lateral
    fraction of 0.85. Pinned numerically, because the two expressions differ by
    a factor nothing in the old code named.
    """
    machine = sloped_course()
    merge = machine.modules["merge"]
    sprint = machine.runs["final"]
    _centre, _rise, half, _edge, _guard, _scale = merge._channel_at(0.0)
    assert half > to_sim(layout.CHANNEL_HALF) + 0.2, half
    assert abs(half - 0.5 * sprint.clear_width * sprint.widths[0]) < 1e-9, half


def test_the_apron_front_is_closed_and_the_rim_hands_over_to_the_rail():
    """No free lip, and the handover is at one station.

    The apron used to span `across` +/-4.035 out to `along` +2.982 with side
    walls, no front wall and no floor beyond it, so anything riding the
    shoulder outside the channel ran off the edge - `final[9..11]`, 14 of 128
    in six of seven of V1.10's fork configurations. Two properties close it:
    the rim eases in to the channel by the front, and the front is where the
    sprint's rails are back to full height.
    """
    from sloped.course import MERGE_GUARD_WINDOW

    machine = sloped_course()
    merge = machine.modules["merge"]
    sprint = machine.runs["final"]
    front = to_sim(merge.FRONT)
    _c, _r, half, _e, _g, _s = merge._channel_at(front)
    assert merge.rim(front) == half + merge.RIM_MIN
    assert merge.rim(to_sim(merge.TAPER_FROM)) > half + 2.0 * MARBLE_DIAMETER
    # The rails are full height by the sample the apron ends on, and not five
    # samples later the way they were when the apron ended at 1.70.
    # The property, stated as coverage rather than as a coincidence of one
    # sample: from the apron's front edge onward there is no station where the
    # sprint's rail is anything but full height. When the apron ended at 1.70
    # layout units the window still had five samples to run.
    closes = MERGE_GUARD_WINDOW[4]
    assert sprint.wall_factor(closes) == 1.0
    for index in range(len(sprint.sim_path)):
        along, _across, _rise = _in_frame(merge, sprint.surface_point(index, 0.0))
        if along >= front:
            assert sprint.wall_factor(index) == 1.0, (index, along)
    along, _across, _rise = _in_frame(merge, sprint.surface_point(closes, 0.0))
    assert along <= front, (along, front)


def _in_frame(merge, point):
    offset = [point[axis] - merge.origin[axis] for axis in range(3)]
    return (
        sum(offset[axis] * merge.forward[axis] for axis in range(3)),
        sum(offset[axis] * merge.lateral[axis] for axis in range(3)),
        sum(offset[axis] * merge.up[axis] for axis in range(3)),
    )


def test_no_merge_probe_needs_an_exemption_any_more():
    """The exemption the chord correction needed, and why it is gone.

    With the apron following blue's gradient the two surfaces agreed to about
    0.03 at the apron's back edge, so a ray aimed at one reached the other and
    the exemption had to be bounded. The rebuild removes the overlap instead of
    bounding it.
    """
    from marble3d.world import MarbleWorld
    from marble3d.config import DEFAULT_CONFIG
    from marble3d.validation import probe_world
    from sloped.course import check_probes

    machine = sloped_course()
    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine.build(world)
        assert check_probes(machine, world) == []
        # **Nothing is excused any more.** The exemption this test was written
        # to bound existed because the apron and blue's channel were two
        # surfaces over the same ground and a ray aimed at one reached the
        # other. The shoulder is only ever outside the channel now, so every
        # merge probe is answered by the merge.
        raw = [f for f in probe_world(world, machine.probes())]
        merge_findings = [f for f in raw if f.subject.startswith("merge.")]
        assert merge_findings == [], [str(f) for f in merge_findings]
    finally:
        world.close()


def test_oranges_mouth_puts_its_floor_on_leg3s_lip():
    """Not its centreline on the lip, which is 0.456 lower.

    A channel's running floor sits `FLOOR_Y` below its centreline, so placing
    orange's *centreline* on leg3's east lip started orange's floor 0.456
    simulation units under the surface a marble crosses from - a drop at the
    seam rather than a join, and it grew to 0.76 eight samples on.
    """
    machine = sloped_course(routes="both")
    leg3 = machine.runs["leg3"]
    lead = machine.runs["orange_lead"]
    sample = joins.FORK_SAMPLE

    lip = leg3.surface_point(sample, layout.CHANNEL_HALF * leg3.scale)
    floor = lead.surface_point(0, 0.0)
    assert math.dist(
        (lip[0], lip[2]), (floor[0], floor[2])
    ) < 0.2, "orange's mouth is not over leg3's lip"
    assert abs(floor[1] - lip[1]) < 0.12, (
        f"orange's floor is {floor[1] - lip[1]:+.3f} from leg3's lip; "
        "the mouth needs lifting by the channel's own floor offset"
    )


def test_the_orange_seam_has_no_cliff_through_the_crossing_window():
    """The gap that made every crossing marble an ejection."""
    machine = sloped_course(routes="both")
    leg3 = machine.runs["leg3"]
    lead = machine.runs["orange_lead"]
    worst = 0.0
    for sample in range(joins.FORK_SAMPLE, joins.FORK_SAMPLE + 10):
        lip = leg3.surface_point(sample, layout.CHANNEL_HALF * leg3.scale)
        best = None
        for index in range(len(lead.sim_path)):
            for step in range(-4, 5):
                point = lead.surface_point(
                    index, (step / 4.0) * layout.CHANNEL_HALF * lead.scale
                )
                flat = math.hypot(point[0] - lip[0], point[2] - lip[2])
                if best is None or flat < best[0]:
                    best = (flat, point[1])
        if best is not None and best[0] < 0.6:
            worst = max(worst, abs(best[1] - lip[1]))
    # A third of a marble diameter. It was 0.76 before the mouth was lifted and
    # the hold gradient taken from the lip rather than the centreline.
    assert worst < 0.35, f"the seam drops {worst:.3f} inside the crossing window"


def test_the_merge_lead_closes_both_seams_on_the_contact_point():
    """What has to be continuous is where the marble touches, not the centreline.

    The two runs' profile scales differ, so their centrelines sit at different
    heights over their own cradle bottoms; `merge_lead_path` lifts its start by
    `FLOOR_Y * (blue.scale - sprint.scale)` to make the contacts meet. Pinned in
    both directions, because getting the sign wrong would put the lead's floor
    0.05 units under blue's and the seam would still look closed on the
    centreline.
    """
    machine = sloped_course()
    blue = machine.runs["blue"]
    lead = machine.runs["merge_lead"]
    sprint = machine.runs["final"]
    entry = math.dist(
        blue.surface_point(len(blue.sim_path) - 1, 0.0), lead.surface_point(0, 0.0)
    )
    exit_gap = math.dist(
        lead.surface_point(len(lead.sim_path) - 1, 0.0), sprint.surface_point(0, 0.0)
    )
    assert entry < 0.01, entry
    assert exit_gap < 0.02, exit_gap
    # And the headings agree far more closely than the seam budget asks.
    assert abs(lead.heading_deg(0) - blue.heading_deg(len(blue.sim_path) - 1)) < 2.0
    assert abs(lead.heading_deg(len(lead.sim_path) - 1) - sprint.heading_deg(0)) < 2.0


def test_the_leads_surface_is_never_above_blues_at_the_seam():
    """The direction of the step across the seam, at every lateral position.

    A scale-1.0 cradle is deeper than a scale-0.82 one, so a lead narrow enough
    to match blue's edge stands *above* it - an uphill lip at the running edge,
    which is the whole defect this rebuild removes. `MERGE_LEAD_WIDTH` opens at
    1.00 for that reason and the property is checked rather than the constant.
    """
    machine = sloped_course()
    blue = machine.runs["blue"]
    lead = machine.runs["merge_lead"]
    last = len(blue.sim_path) - 1
    for step in range(21):
        fraction = -1.0 + 2.0 * step / 20
        profile = fraction * layout.CHANNEL_HALF
        on_blue = blue.surface_point(last, profile)
        # the same physical lateral offset, in the lead's own profile units
        offset = 0.5 * blue.clear_width * blue.widths[last] * fraction
        lead_profile = offset / (0.5 * lead.clear_width * lead.widths[0]) * layout.CHANNEL_HALF
        on_lead = lead.surface_point(0, lead_profile)
        assert on_lead[1] <= on_blue[1] + 1e-6, (fraction, on_lead[1], on_blue[1])


def test_the_east_rim_yields_to_orange_and_the_east_wall_stops_short_of_it():
    """Orange's tail crosses the apron, so the apron cannot wall across it.

    Measured before this was written: the front taper's east wall stood at
    across +2.69 while orange's centreline was at +3.27, and a marble at 40 wu/s
    lost 19.13 wu/s in a single tick against it. Two properties, both derived:
    the rim never reaches past orange's near edge, and the wall ends where
    orange's channel comes inside the sprint's own.
    """
    machine = sloped_course(routes="both")
    merge = machine.modules["merge"]
    back, front = to_sim(merge.BACK), to_sim(merge.FRONT)
    crossed = 0
    for step in range(41):
        along = back + (front - back) * step / 40
        near = merge.orange_near(along)
        if near is None:
            continue
        crossed += 1
        centre = merge._channel_at(along)[0]
        east = centre + merge.rim(along, +1.0)
        assert east <= max(near, centre + merge._channel_at(along)[2] + merge.RIM_MIN) + 1e-9
    assert crossed > 5, crossed
    assert merge.describe()["east_wall_ends"] < front
    # The blue-only course has no orange, so nothing is clamped and the rim
    # tapers the whole way.
    plain = sloped_course(routes="blue").modules["merge"]
    assert plain.orange_near(0.0) is None
    assert plain.describe()["east_wall_ends"] == round(to_sim(plain.FRONT), 4)


def test_the_shoulder_descends_in_world_height_on_every_line():
    """A taper has to remove shoulder, not lift it.

    Normalising the funnel by the *local* rim makes the region outside the rim a
    plateau at full funnel height, and the plateau's inner edge moves inward as
    the rim narrows. Measured in the apron's own frame that reads as a 0.3857
    climb, which is an artefact of the frame - its forward axis descends at 13.7
    degrees - but the plateau is real. Checked in world height, which is the
    quantity gravity reads.
    """
    machine = sloped_course(routes="both")
    merge = machine.modules["merge"]

    def world_y(along, across):
        rise = merge._floor(along, across)
        return (
            merge.origin[1]
            + merge.forward[1] * along
            + merge.lateral[1] * across
            + merge.up[1] * rise
        )

    for across in (-2.19, -2.60, -3.20, +2.19, +3.20):
        lowest = None
        worst = 0.0
        for step in range(121):
            along = -4.0 + 8.5 * step / 120
            y = world_y(along, across)
            lowest = y if lowest is None else min(lowest, y)
            worst = max(worst, y - lowest)
        # A tenth of a diameter, which is 4.4 wu/s of escape speed; the seam
        # between blue's half width and the lead's contributes 0.055 of it.
        assert worst < 0.10, (across, worst)


def test_the_merge_trim_is_solved_and_not_installed():
    """The falsified fold, pinned so it cannot be reinstalled by accident.

    `merge_trim` removes orange's mouth from over the sprint's east running
    edge, by exactly the argument `fork_trim` is built on, and it made orange
    worse: 22 of 28 to 19 in traffic and 17 to 2 alone. At the fork the folded
    part has leg3's bank under it at the same height; here the sprint's floor is
    0.34 to 0.9 below, so the fold drops the marble instead of handing it over.
    """
    machine = sloped_course(routes="both")
    orange = machine.runs["orange"]
    assert orange.exit_trim is None, "merge_trim is falsified; see joins.merge_trim"
    # And it still solves, so the measurement stays reproducible.
    table = joins.merge_trim(orange, machine.runs["final"], machine.runs["merge_lead"])
    active = [v for v in table if v is not None]
    assert len(active) >= 4, table
    assert all(-layout.CHANNEL_HALF <= v <= layout.CHANNEL_HALF for v in active)


def test_the_apron_holds_a_marble_on_its_shoulder_and_not_beyond_it():
    """`MergeCatch.holds` is what excuses the run-relative containment tests.

    Orange is designed to cross the shoulder, so a marble standing on it is not
    off the course - eleven of 28 were being booked as escapes in that state.
    The exemption has to stop somewhere, and it stops at the rim and the roof.
    """
    machine = sloped_course(routes="both")
    merge = machine.modules["merge"]

    def point(along, across, rise):
        return tuple(
            merge.origin[axis]
            + merge.forward[axis] * along
            + merge.lateral[axis] * across
            + merge.up[axis] * rise
            for axis in range(3)
        )

    along = -1.0
    centre, _rise, half, _edge, _guard, _scale = merge._channel_at(along)
    on_shoulder = centre - (half + 0.5 * (merge.rim(along, -1.0) - half))
    floor = merge._floor(along, on_shoulder)
    assert merge.holds(point(along, on_shoulder, floor + MARBLE_RADIUS))
    # Outside the rim, above the roof, and behind the back edge: all no.
    assert not merge.holds(point(along, centre - merge.rim(along, -1.0) - 2.0, floor))
    assert not merge.holds(point(along, on_shoulder, floor + to_sim(merge.ROOF) + 1.0))
    assert not merge.holds(point(to_sim(merge.BACK) - 3.0, on_shoulder, floor))


# --- V1.13: the fork ridge, and the knob that could not move ---------------


def _ridge_stations(machine):
    """(step, leg3 sample, gap, crest height) for every ridge station."""
    ridge = machine.modules["fork"]
    leg3, lead = ridge.run, ridge.other
    out = []
    for step in range(ridge.window + 1):
        here = min(ridge.index + step, len(leg3.sim_path) - 1)
        there = min(step, len(lead.sim_path) - 1)
        west = leg3.surface_point(here, layout.CHANNEL_HALF)
        east = lead.surface_point(there, -layout.CHANNEL_HALF)
        lateral = leg3.frames[here][0]
        gap = sum((east[axis] - west[axis]) * lateral[axis] for axis in range(3))
        if gap <= ridge.HAIRLINE * MARBLE_DIAMETER:
            continue
        out.append((step, here, gap, min(leg3.containment, ridge.MAX_FLANK * 0.5 * gap)))
    return out


def test_the_fork_mouth_reads_its_constant_at_call_time():
    """`ORANGE_MOUTH_ACROSS` used to be bound as a default argument.

    Python evaluates a default once, when the `def` runs, so setting the module
    attribute afterwards moved nothing - and `tools/sloped_fork_lab.py`'s
    `mouth_across` knob, listed since V1.10, had never changed a row it
    appeared in. This is the regression test for that, and it is written
    against `fork_mouth` rather than against the knob because the knob is a
    scan harness and the bug was in the geometry.
    """
    shipped, _heading, _grade = joins.fork_mouth()
    explicit, _h, _g = joins.fork_mouth(joins.ORANGE_MOUTH_ACROSS)
    assert shipped == explicit

    before = joins.ORANGE_MOUTH_ACROSS
    try:
        joins.ORANGE_MOUTH_ACROSS = 0.65
        moved, _h, _g = joins.fork_mouth()
    finally:
        joins.ORANGE_MOUTH_ACROSS = before
    # 0.29 of a profile unit down a 26-degree bank is a real distance; anything
    # under a tenth of a marble diameter means the constant is being ignored.
    assert math.dist(shipped, moved) > 0.1 * MARBLE_DIAMETER


def test_both_fork_guards_shut_where_the_two_cradles_part():
    """The opening ends where the shared floor does, not seven samples later.

    Running either window on to the ridge's own last station is the obvious
    repair and it is falsified - 0.396 finish to 0.188 over 12 seeds - because
    the guards are not walling off a corridor, they are keeping the field out
    of one. What the scan settles is that both should shut at the **parting**:
    the last sample at which leg3's east cradle edge and orange's west cradle
    edge still overlap. See `docs/sloped_race_v113_fork.md`.
    """
    machine = sloped_course(routes="both")
    stations = _ridge_stations(machine)
    assert stations, "the two channels never part; there would be no fork"
    parting = stations[0][0]

    for name, window in (
        ("leg3's east guard", joins.FORK_GUARD_WINDOW),
        ("orange's west guard", joins.FORK_LEAD_WINDOW),
    ):
        _open_from, _full_open, last_open, full_again = window
        assert last_open <= parting, (
            f"{name} is still open at step {last_open}, past the parting at {parting}"
        )
        assert full_again <= parting + 2, (
            f"{name} takes until step {full_again} to close, {full_again - parting} "
            "past the parting - a long partial opening measured 0.156 finish"
        )


def test_the_ridge_is_a_conveyor_and_its_downstream_end_is_open():
    """The mechanism this session found, pinned so it cannot be mislaid.

    The ridge spans the gap between the two cradle edges and stops at its own
    last station, and past that station there is no floor between the two
    channels at all. That is why touching it is fatal: over 24 seeds at crest
    0.12, 35 racers touched it and 6 finished.

    The test does not assert that the ridge is *wrong* - it is the only thing
    holding the gap up. It asserts the two facts a repair has to face: that its
    last station is inside the fork window rather than somewhere the marble is
    already contained, and that the gap it is spanning there is more than a
    marble wide, so the end is a hole and not a seam.
    """
    machine = sloped_course(routes="both")
    stations = _ridge_stations(machine)
    step, sample, gap, _height = stations[-1]
    assert gap > MARBLE_DIAMETER, (
        f"the ridge ends at leg3[{sample}] over a gap of {gap:.3f}, which is "
        "under a diameter - if this ever passes the end has become a seam and "
        "the conveyor finding needs remeasuring"
    )
    leg3 = machine.runs["leg3"]
    lead = machine.runs["orange_lead"]
    assert leg3.wall_factor(sample) >= 0.99
    assert lead.wall_factor(min(step, len(lead.sim_path) - 1)) >= 0.99


def test_the_ridge_rise_limit_is_off_and_still_works():
    """`ForkRidge.RISE_SLEW` is uninstalled, and the class still carries it.

    Same rule as `sloped.joins.merge_trim`: a mechanism that is measured and
    falsified stays in the tree with its measurement, because the next session
    should not have to rediscover that it does nothing. Off, the crest climbs
    0.179 to 0.218 of world height a sample through `leg3[91..94]`; on, it is
    flat to two thousandths. Neither moves a marble.
    """
    from sloped.stations import ForkRidge

    assert ForkRidge.RISE_SLEW is None

    def crest_heights(slew):
        before = ForkRidge.RISE_SLEW
        try:
            ForkRidge.RISE_SLEW = slew
            ridge = sloped_course(routes="both").modules["fork"]
            return [
                0.5 * (west[1] + east[1]) + up[1] * height
                for west, east, up, height in ridge._stations()
            ]
        finally:
            ForkRidge.RISE_SLEW = before

    loose = crest_heights(None)
    tight = crest_heights(1.0)
    rise = lambda series: max(b - a for a, b in zip(series, series[1:]))
    assert rise(loose) > 0.15, "the ramp this exists for has gone; remeasure it"
    assert rise(tight) < 0.02, "the limit no longer flattens the crest"
