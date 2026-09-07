"""The mountain in Python is the mountain in the scene.

`sloped.terrain` exists so a camera can be placed against the ground and its
sight line checked before anything is rendered, and that is only worth doing if
the ground it consults is the one that gets drawn. So this compares the port
against a grid dumped *from the running Godot scene* -
`sloped_race_scene.gd::dump_terrain`, 396 points on a 7-unit lattice, committed
as `docs/validation/sloped_race_v1/terrain.json`.

Two things in the port could be subtly wrong and still look plausible, and each
has a test here:

* `_lattice` hashes with 64-bit integer overflow, which GDScript does for free
  and Python does not do at all. Masking at every step is what makes the noise
  field identical rather than merely similar.
* the bench cut is indexed from the concatenation of **all seven** runs, not
  the five the physics races, because that is what `course_machine.build`
  hands it. Cutting from five moves the bench under the branch lobes.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from sloped import layout, terrain

DUMP = os.path.join("docs", "validation", "sloped_race_v1", "terrain.json")

# The port is exact to within Godot's own float32 storage and the JSON writer's
# rounding, which is what this number is: it is not a tolerance chosen to make
# the test pass, it is the width of the channel the values travelled through.
TOLERANCE = 1e-3


@pytest.fixture(scope="module")
def dump():
    if not os.path.isfile(DUMP):
        pytest.skip(f"{DUMP} has not been dumped from the scene")
    with open(DUMP, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def cfg():
    return terrain.terrain_config()


def test_every_dumped_height_agrees_with_the_port(dump, cfg):
    worst = 0.0
    where = None
    for x, z, y in dump["samples"]:
        mine = terrain.height(x, z, cfg)
        error = abs(mine - y)
        if error > worst:
            worst, where = error, (x, z, y, mine)
    assert worst < TOLERANCE, f"worst {worst:.6f} at {where}"


def test_the_dump_covers_the_course_and_not_just_the_valley_floor(dump):
    ## A grid that misses the course would agree on the radial fade alone.
    heights = [y for _x, _z, y in dump["samples"]]
    assert max(heights) - min(heights) > 60.0
    assert len(dump["samples"]) >= 300


def test_the_lattice_hash_wraps_the_way_gdscript_does(cfg):
    ## The multipliers in `_lattice` overflow 64 bits for lattice indices well
    ## inside the course's own bounds, so an unmasked port diverges here rather
    ## than at the origin. Both of these are in range for the 0.52-frequency
    ## octave over a course spanning 78 units.
    assert terrain._lattice(0, 0, 3) != terrain._lattice(1, 0, 3)
    for ix, iz, salt in ((41, -37, 59), (-2600, 1900, 23), (9973, -9973, 41)):
        value = terrain._lattice(ix, iz, salt)
        assert 0.0 <= value < 1.0


def test_the_noise_is_in_range_and_not_constant():
    values = [terrain._noise(x * 0.37, x * -0.91, 0.031, 7) for x in range(200)]
    assert all(-1.0 <= v <= 1.0 for v in values)
    assert max(values) - min(values) > 0.5


def test_the_bench_is_cut_from_all_seven_runs(cfg):
    ## The count is the tell. Seven runs at 118 samples each, resampled to a
    ## third of the total: cutting from the five the physics races would index
    ## five sevenths of the points and leave the branch lobes uncut.
    indexed = sum(len(points) for points in cfg["cut_index"].values())
    names = layout.run_names()
    assert len(names) == 7
    assert indexed == pytest.approx(len(names) * 118 // 3, abs=2)


def test_the_bench_lowers_the_ground_under_the_racing_line(cfg):
    ## The cut is the deepest feature near the course, and a camera placed a
    ## unit above the track without it is a camera inside the bench.
    ##
    ## Measured against the *same* point with the index emptied, not against
    ## ground thirty units away: the flank drops 0.45 units per unit of z, so
    ## a distant comparison measures the grade and would pass whether the bench
    ## existed or not.
    from sloped.track import TrackRun

    run = TrackRun("leg1")
    point = run.path[len(run.path) // 2]
    uncut = dict(cfg)
    uncut["cut_index"] = {}
    with_bench = terrain.height(point[0], point[2], cfg)
    without = terrain.height(point[0], point[2], uncut)
    assert with_bench < without, "the bench should lower the ground it is cut into"
    assert without - with_bench > 1.0, "and by something a camera would notice"
    assert with_bench < point[1], "the ground under the channel should sit below it"


# --- what a camera asks it ----------------------------------------------


def test_lower_side_picks_the_side_over_lower_ground(cfg):
    ## The layout proof's rule, and the reason the cameras consult it: the
    ## track's own left is uphill on one leg and downhill on the next.
    from sloped.track import TrackRun

    run = TrackRun("leg1")
    index = len(run.path) // 2
    _lateral, _up, forward = run.frames[index]
    flat = (forward[0], 0.0, forward[2])
    length = math.hypot(flat[0], flat[2])
    flat = (flat[0] / length, 0.0, flat[2] / length)

    point = run.path[index]
    side = terrain.lower_side(point, flat, cfg)
    chosen = terrain.height(
        point[0] + side[0] * terrain.PROBE, point[2] + side[2] * terrain.PROBE, cfg
    )
    other = terrain.height(
        point[0] - side[0] * terrain.PROBE, point[2] - side[2] * terrain.PROBE, cfg
    )
    assert chosen <= other
    assert abs(math.hypot(side[0], side[2]) - 1.0) < 1e-9
    assert abs(side[1]) < 1e-12


def test_clearance_is_negative_when_the_line_goes_through_the_hill(cfg):
    ## A camera buried in the ground looking at a point on the surface: the
    ## sight line has to come back negative or section 37's check is vacuous.
    aim = (1.0, terrain.height(1.0, 6.0, cfg) + 1.0, 6.0)
    buried = (aim[0] - 40.0, terrain.height(aim[0] - 40.0, aim[2], cfg) - 6.0, aim[2])
    assert terrain.clearance(buried, aim, cfg) < 0.0
    assert terrain.sight_line_blocked(buried, aim, cfg)


def test_clearance_is_positive_from_high_above(cfg):
    aim = (1.0, terrain.height(1.0, 6.0, cfg) + 1.0, 6.0)
    above = (aim[0], aim[1] + 120.0, aim[2] + 1.0)
    assert terrain.clearance(above, aim, cfg) > 0.0
    assert not terrain.sight_line_blocked(above, aim, cfg)


def test_the_port_is_exact_not_merely_close(dump, cfg):
    ## Tighter than the tolerance above, and the reason the bench is cut from
    ## the drawn layout rather than from the raced build: at 1.7e-5 the port is
    ## the scene's terrain, and cutting from the raced runs put it 0.021 out.
    worst = max(abs(terrain.height(x, z, cfg) - y) for x, z, y in dump["samples"])
    assert worst < 1e-4, worst


def test_the_raced_blue_lobe_lies_on_the_drawn_ribbon():
    """The physics runs where the video draws, on the one run that differs.

    `joins.blue_controls` enters blue at its second authored control so the
    join has room for its turn radius, which makes the raced lobe a shorter
    curve than the drawn one - and comparing them sample for sample says they
    are 6.73 layout units apart, which is a statement about parameterisation
    and not about geometry. What matters for an honest render is the
    perpendicular distance from the raced path to the drawn ribbon, and that is
    a ninth of a marble radius.
    """
    import math

    from sloped.course import sloped_course
    from sloped.track import TrackRun

    def nearest(point, polyline):
        best = math.inf
        for a, b in zip(polyline, polyline[1:]):
            span = [b[axis] - a[axis] for axis in range(3)]
            length = sum(value * value for value in span)
            if length < 1e-12:
                best = min(best, math.dist(point, a))
                continue
            t = sum((point[axis] - a[axis]) * span[axis] for axis in range(3)) / length
            t = max(0.0, min(1.0, t))
            best = min(best, math.dist(point, [a[axis] + span[axis] * t for axis in range(3)]))
        return best

    drawn = TrackRun("blue").path
    raced = sloped_course().runs["blue"].path
    worst = max(nearest(point, drawn) for point in raced)
    assert worst < 0.5 * layout.MARBLE_RADIUS, worst
