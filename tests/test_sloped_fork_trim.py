"""The fork's entry trim and its sorting crest.

Two pieces of geometry that only make sense together. `sloped.joins.fork_trim`
folds away the part of orange's section that used to hang over leg3's channel,
which leaves the two runs sharing one edge; `sloped.course.FORK_CREST` is then
the height of the only thing standing on that shared edge, and therefore the
one number the route split is set by.

Both are *solved* rather than tabulated - the trim against another run's built
surface, the crest through `TrackRun.wall_factor`'s sixth entry - so what is
pinned here is the solve's own contract: that the cut lands on leg3's east
cradle edge, that it releases itself once nothing overhangs, that the section
keeps the point count `sweep_rings` insists on, and that the crest the course
installs is the constant that carries the scan.
"""

from __future__ import annotations

import math

import pytest

from sloped import joins, layout
from sloped.course import FORK_CREST, sloped_course
from sloped.track import TrackRun

# The trim is active for this many samples on the built course, and releases
# from there on. Not a target - a measurement, and the reason the overhang was
# only ever eight samples long. `FORK_TRIM_WINDOW` solves well past it.
ACTIVE_STEPS = 8


@pytest.fixture(scope="module")
def forked():
    return sloped_course(routes="both").runs


# --- the trim machinery, on a run of its own ------------------------------


def test_a_run_without_a_trim_is_untouched():
    plain = TrackRun("leg3")
    assert plain.entry_trim is None
    assert plain.entry_trim_at(4) is None
    assert plain.section_at(4) == plain.section


def test_a_trim_past_the_table_is_no_trim():
    run = TrackRun("leg3", entry_trim=[0.0, -0.5])
    assert run.entry_trim_at(1) == -0.5
    assert run.entry_trim_at(2) is None
    assert run.section_at(2) == run.section


def test_the_trim_keeps_the_section_point_count():
    """`sweep_rings` refuses unequal rings, so the fold cannot delete points."""
    run = TrackRun("leg3")
    width = len(run.section)
    run.set_entry_trim([-0.7, -0.4, -0.1, 0.0, None])
    for index in range(5):
        assert len(run.section_at(index)) == width


def _seam_rise(section, cut: float) -> float:
    """The untrimmed section's height at the cut, by linear interpolation."""
    for (west, low), (east, high) in zip(section, section[1:]):
        if west <= cut <= east:
            if east - west < 1e-12:
                return high
            return low + (high - low) * (cut - west) / (east - west)
    raise AssertionError(f"{cut} is not inside the section")


def test_the_folded_points_hang_at_the_cut_and_below_the_seam():
    run = TrackRun("leg3")
    run.set_entry_trim([-0.4])
    cut = -0.4 * run.scale
    seam = _seam_rise(run.section, cut)
    trimmed = run.section_at(0)
    folded = [point for point in trimmed if point[0] == pytest.approx(cut)]
    assert folded, "the fold has to leave points at the cut"
    # Deepest first, climbing toward the seam but never reaching it, so the
    # skirt is a downward-facing wall rather than a ledge to rest on.
    rises = [rise for _across, rise in folded]
    assert rises == sorted(rises), "the skirt climbs toward the seam"
    assert all(rise < seam for rise in rises), "nothing folded reaches the seam"
    assert seam - min(rises) == pytest.approx(run.TRIM_SKIRT * run.scale, rel=1e-9)
    # The shallowest hangs one step down, which is what keeps it off the seam.
    step = (run.TRIM_SKIRT * run.scale) / len(folded)
    assert seam - max(rises) == pytest.approx(step, rel=1e-9)
    # And nothing survives west of the cut.
    assert min(across for across, _rise in trimmed) == pytest.approx(cut)


def test_no_point_lands_exactly_on_the_seam():
    """A point on the seam duplicates the section's own centreline point at a
    trim of zero, which is a zero-area triangle rather than a surface."""
    run = TrackRun("leg3")
    run.set_entry_trim([0.0])
    trimmed = run.section_at(0)
    seam_rise = max(rise for across, rise in trimmed if across == pytest.approx(0.0))
    at_cut = [rise for across, rise in trimmed if across == pytest.approx(0.0)]
    assert len(at_cut) > 1, "the fold and the centreline both sit at across zero"
    assert min(at_cut) < seam_rise, "the folded points stay below the centreline"


def test_setting_a_trim_drops_the_cached_collider():
    run = TrackRun("leg3")
    run.local_colliders()
    assert run._mesh is not None
    run.set_entry_trim([-0.5])
    assert run._mesh is None


# --- the solve, against the built course ----------------------------------


def _horizontal_across(leg3, index: int):
    """`across` in leg3's frame with the roll taken out, as `fork_trim` reads it.

    Re-derived here rather than imported, so the test is an independent check
    of the solve rather than a restatement of it.
    """
    centre = leg3.sim_path[index]
    forward = leg3.tangents[index]
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    side = (side[0] / length, 0.0, side[2] / length) if length > 1e-9 else (1.0, 0.0, 0.0)

    def across_of(point) -> float:
        return sum((point[axis] - centre[axis]) * side[axis] for axis in range(3))

    return across_of


def test_the_built_course_installs_the_trim(forked):
    table = forked["orange_lead"].entry_trim
    assert table is not None
    assert len(table) == joins.FORK_TRIM_WINDOW
    assert all(value is None for value in table[ACTIVE_STEPS:])
    assert all(value is not None for value in table[:ACTIVE_STEPS])


def test_the_cut_lands_on_leg3s_east_cradle_edge(forked):
    """The whole point of the solve, checked one sample at a time."""
    leg3, lead = forked["leg3"], forked["orange_lead"]
    half = layout.CHANNEL_HALF
    for step in range(1, ACTIVE_STEPS):
        here = min(joins.FORK_SAMPLE + step, len(leg3.sim_path) - 1)
        across_of = _horizontal_across(leg3, here)
        edge = across_of(leg3.surface_point(here, half))
        cut = across_of(lead.surface_point(step, lead.entry_trim[step]))
        assert cut == pytest.approx(edge, abs=1e-9), f"step {step}"


def test_the_mouths_own_step_is_clamped_to_the_centreline(forked):
    """At the mouth orange's cradle bottom is *west* of leg3's east edge, so
    there is no crossing to solve for and the trim is the centreline itself."""
    leg3, lead = forked["leg3"], forked["orange_lead"]
    across_of = _horizontal_across(leg3, joins.FORK_SAMPLE)
    edge = across_of(leg3.surface_point(joins.FORK_SAMPLE, layout.CHANNEL_HALF))
    assert lead.entry_trim[0] == 0.0
    assert across_of(lead.surface_point(0, 0.0)) < edge


def test_the_trim_never_cuts_past_the_cradle(forked):
    lead = forked["orange_lead"]
    for value in lead.entry_trim[:ACTIVE_STEPS]:
        assert -layout.CHANNEL_HALF < value <= 0.0


def test_the_trim_deepens_as_the_channels_part(forked):
    active = forked["orange_lead"].entry_trim[1:ACTIVE_STEPS]
    assert active == sorted(active, reverse=True), "the cut moves west, monotonically"


def test_the_trim_releases_itself_once_nothing_overhangs(forked):
    """Where the table is None, orange's own west cradle edge is already east
    of leg3's - so the release is a consequence of the geometry, not a window."""
    leg3, lead = forked["leg3"], forked["orange_lead"]
    half = layout.CHANNEL_HALF
    for step in range(ACTIVE_STEPS, joins.FORK_TRIM_WINDOW):
        here = min(joins.FORK_SAMPLE + step, len(leg3.sim_path) - 1)
        across_of = _horizontal_across(leg3, here)
        edge = across_of(leg3.surface_point(here, half))
        west = across_of(lead.surface_point(step, -half))
        assert west >= edge, f"step {step} still overhangs"


def test_the_channels_are_more_than_a_marble_apart_before_the_ridge_ends(forked):
    """Why `ForkRidge` is load-bearing rather than decorative.

    Past the release the two channels separate fast, and the ridge is the only
    thing between them. This records where the separation passes a marble
    diameter against where the ridge stops, because a marble arriving between
    those two samples has nothing under it.
    """
    leg3, lead = forked["leg3"], forked["orange_lead"]
    half = layout.CHANNEL_HALF
    gaps = []
    for step in range(ACTIVE_STEPS, joins.FORK_TRIM_WINDOW):
        here = min(joins.FORK_SAMPLE + step, len(leg3.sim_path) - 1)
        across_of = _horizontal_across(leg3, here)
        gaps.append(
            across_of(lead.surface_point(step, -half))
            - across_of(leg3.surface_point(here, half))
        )
    assert gaps[0] < 0.1, "they are still touching where the trim releases"
    within_ridge = gaps[: joins.FORK_WINDOW_BLUE - ACTIVE_STEPS]
    assert within_ridge == sorted(within_ridge), "the channels only ever part"
    wide = next(step for step, gap in enumerate(gaps, ACTIVE_STEPS) if gap > 1.0)
    assert wide < joins.FORK_WINDOW_BLUE, (
        f"the gap passes a marble at step {wide}, and the ridge runs to "
        f"{joins.FORK_WINDOW_BLUE}: the ridge is what spans it"
    )


# --- the crest -------------------------------------------------------------


def test_a_five_entry_window_still_opens_to_the_default_floor():
    run = TrackRun("leg3", open_side=(1.0, 10, 12, 20, 22))
    assert run.wall_factor(16) == run.OPEN_FLOOR


def test_the_sixth_entry_sets_the_open_fraction():
    run = TrackRun("leg3", open_side=(1.0, 10, 12, 20, 22, 0.55))
    assert run.wall_factor(16) == pytest.approx(0.55)


def test_the_window_is_full_height_outside_and_eases_within():
    run = TrackRun("leg3", open_side=(1.0, 10, 12, 20, 22, 0.40))
    assert run.wall_factor(10) == 1.0
    assert run.wall_factor(22) == 1.0
    assert run.wall_factor(9) == 1.0
    assert run.wall_factor(30) == 1.0
    # Easing down, then held, then easing back.
    assert 0.40 < run.wall_factor(11) < 1.0
    assert run.wall_factor(12) == pytest.approx(0.40)
    assert run.wall_factor(20) == pytest.approx(0.40)
    assert 0.40 < run.wall_factor(21) < 1.0


def test_a_taller_crest_is_a_taller_wall_everywhere_in_the_window():
    low = TrackRun("leg3", open_side=(1.0, 10, 12, 20, 22, 0.05))
    high = TrackRun("leg3", open_side=(1.0, 10, 12, 20, 22, 0.55))
    for index in range(11, 22):
        assert high.wall_factor(index) >= low.wall_factor(index)


def test_the_forked_course_installs_the_crest_constant(forked):
    open_side = forked["leg3"].open_side
    assert len(open_side) == 6
    assert open_side[5] == FORK_CREST
    assert open_side[1:5] == tuple(
        joins.FORK_SAMPLE + offset for offset in joins.FORK_GUARD_WINDOW
    )


def test_the_blue_course_has_no_fork_window_at_all():
    """Nothing here reaches the shipped route: with `routes="blue"` leg3's east
    guard is never opened and orange's lead is never built."""
    blue = sloped_course(routes="blue").runs
    assert blue["leg3"].open_side is None
    assert "orange_lead" not in blue
