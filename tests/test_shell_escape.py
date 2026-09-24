"""Category 3 Test #2 - MUSICAL SHELL ESCAPE, Phase 1.

What these tests are for, in order of how much they would hurt to lose:

1. **The solver is right.** A rotating-polygon billiard solved by marching on a
   clearance is exactly the kind of code that is subtly wrong and looks fine.
   `test_solver_agrees_with_the_brute_force_reference` runs every contact
   search of a set of seeds against `satisfying.shell_reference`, which shares
   no reasoning with it, and the run-level instruments -
   `max_penetration`, `anomalous_crossings`, `newton_failures` - are asserted
   to be zero across a population. Both defects found during Phase 1 were
   found by those instruments and would have passed any test that only checked
   that a ball bounced.
2. **The event schema is frozen.** Phase 2A and Phase 2B are going to be
   written against it in parallel, so a renamed field is a merge conflict
   discovered at integration. The schema is asserted field by field.
3. **The document reproduces.** Same seed and config, same digest, byte for
   byte, through a JSON round trip.
4. **The mechanics do what the brief says.** Damage accumulates, a panel
   breaks once, a broken panel becomes passable, both escape routes occur,
   timeouts occur.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from satisfying import shell_seeds
from satisfying.shell_arena import build_arena
from satisfying.shell_escape import (
    DEFAULT_CONFIG,
    EVENT_KINDS,
    EVENT_SCHEMA,
    SCHEMA_VERSION,
    ShellEscapeConfig,
    resolve_shells,
    simulate,
    start_state,
    validate_events,
)
from satisfying.shell_escape_cli import _rehydrate, run_batch, shortlist
from satisfying.shell_evaluator import DEFAULT_THRESHOLDS, evaluate, evaluate_seed, summarise
from satisfying.shell_playback import (
    DOCUMENT_VERSION,
    panel_closed_at,
    playback_document,
    position_at,
    read_playback,
    region_at,
    verify_document,
    write_playback,
)

# Seeds picked once, from a 400-seed scan, for the outcomes they happen to
# have. They are fixtures, not magic: if the physics changes these change, and
# that is the point of naming them here rather than searching at test time.
SEED_ESCAPE_VIA_OPENING = 13
SEED_ESCAPE_VIA_BREAK = 51
SEED_TIMEOUT = 0
SEED_WITH_REGRESSION = 3


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def test_shell_construction_is_deterministic_and_ordered_inner_to_outer() -> None:
    arena_a = build_arena(
        shell_count=3,
        inner_radius=5.0,
        shell_spacing=3.0,
        panel_counts=[10, 11, 12],
        openings_per_shell=[1, 2, 3],
        opening_slots=[1, 1, 1],
        thickness=0.3,
        ball_radius=0.4,
        theta0=[0.1, 0.2, 0.3],
        omega=[0.5, -0.4, 0.3],
    )
    arena_b = build_arena(
        shell_count=3,
        inner_radius=5.0,
        shell_spacing=3.0,
        panel_counts=[10, 11, 12],
        openings_per_shell=[1, 2, 3],
        opening_slots=[1, 1, 1],
        thickness=0.3,
        ball_radius=0.4,
        theta0=[0.1, 0.2, 0.3],
        omega=[0.5, -0.4, 0.3],
    )
    assert arena_a.as_dict() == arena_b.as_dict()

    radii = [shell.radius for shell in arena_a.shells]
    assert radii == sorted(radii), "shell order must be inner to outer"
    assert [shell.shell_id for shell in arena_a.shells] == [0, 1, 2]
    assert [len(shell.openings) for shell in arena_a.shells] == [1, 2, 3]
    assert arena_a.shells[2].openings[0].opening_id == "s2o0"


def test_opening_geometry_is_a_real_hole_the_ball_fits_through() -> None:
    arena = build_arena(
        shell_count=1,
        inner_radius=5.0,
        shell_spacing=3.0,
        panel_counts=[16],
        openings_per_shell=[2],
        opening_slots=[1],
        thickness=0.3,
        ball_radius=0.4,
        theta0=[0.0],
        omega=[0.0],
    )
    shell = arena.shells[0]
    assert shell.open_slots == (0, 8)
    # Every open slot has no panel, every other slot has one.
    for slot in range(shell.panel_count):
        assert (slot in shell.open_slots) == (slot in (0, 8))
    report = arena.fit_report()[0]
    assert report["fits"], report
    assert report["narrowest_gap"] == pytest.approx(
        2.0 * 5.0 * math.sin(math.pi / 16) - 0.3, rel=1e-12
    )
    # A ball wider than the hole is reported as not fitting rather than
    # silently never passing.
    wide = build_arena(
        shell_count=1,
        inner_radius=5.0,
        shell_spacing=3.0,
        panel_counts=[16],
        openings_per_shell=[2],
        opening_slots=[1],
        thickness=0.3,
        ball_radius=1.2,
        theta0=[0.0],
        omega=[0.0],
    )
    assert not wide.fit_report()[0]["fits"]


def test_an_opening_that_wraps_the_slot_seam_is_still_one_opening() -> None:
    arena = build_arena(
        shell_count=1,
        inner_radius=5.0,
        shell_spacing=3.0,
        panel_counts=[8],
        openings_per_shell=[1],
        opening_slots=[3],
        thickness=0.3,
        ball_radius=0.4,
        theta0=[0.0],
        omega=[0.0],
    )
    shell = arena.shells[0]
    assert shell.open_slots == (0, 1, 2)
    assert len(shell.openings) == 1
    assert shell.openings[0].slot_count == 3


def test_shell_rotation_is_deterministic_and_shells_do_not_all_turn_alike() -> None:
    theta_a, omega_a = resolve_shells(1234, DEFAULT_CONFIG)
    theta_b, omega_b = resolve_shells(1234, DEFAULT_CONFIG)
    assert theta_a == theta_b and omega_a == omega_b

    theta_c, omega_c = resolve_shells(1235, DEFAULT_CONFIG)
    assert theta_a != theta_c, "a different seed must place the openings differently"

    assert len(set(omega_a)) == len(omega_a), "no two shells share an angular velocity"
    assert any(w > 0 for w in omega_a) and any(w < 0 for w in omega_a), "directions must differ"
    # Constant surface speed by design: `omega * radius` is the same everywhere
    # up to the seeded jitter, which is what keeps the outer shells from
    # becoming a blur.
    surface = [
        abs(w) * (DEFAULT_CONFIG.inner_radius + k * DEFAULT_CONFIG.shell_spacing)
        for k, w in enumerate(omega_a)
    ]
    assert max(surface) / min(surface) < (1 + DEFAULT_CONFIG.omega_jitter) / (
        1 - DEFAULT_CONFIG.omega_jitter
    ) + 1e-9


def test_rotation_is_in_the_state_not_only_in_the_picture() -> None:
    """A shell's angle at `t` decides where the panel is, not a later redraw.

    The check is that the recorded contact point lies on the panel *placed at
    the collision time*, and does not lie on the same panel placed at `t = 0`.
    A simulation that treated rotation as decoration would pass the second half
    of that and fail the first.
    """
    from satisfying.shell_escape import _segment_distance

    checked = 0
    for event in simulate(SEED_TIMEOUT).events:
        if event.kind != "collision":
            continue
        run = simulate(SEED_TIMEOUT)
        shell = run.arena.shells[event.data["shell_id"]]
        slot = event.data["panel_id"]
        qx, qy = event.data["contact_point"]
        (ax, ay), (bx, by) = shell.panel_segment(slot, event.t)
        now, _x, _y = _segment_distance(qx, qy, ax, ay, bx, by)
        assert now <= 0.5 * shell.thickness + 1e-6, (
            "the contact point is not on the panel where the rotation put it"
        )
        (ax, ay), (bx, by) = shell.panel_segment(slot, 0.0)
        at_zero, _x, _y = _segment_distance(qx, qy, ax, ay, bx, by)
        if event.t > 0.5 and abs(shell.omega) * event.t > 0.2:
            assert at_zero > now + 0.1, "the shell had not turned at all by the collision"
            checked += 1
        if checked >= 5:
            break
    assert checked >= 5, "no collision late enough to show the rotation"


def test_seed_streams_are_independent() -> None:
    """Changing the release point cannot change the heading, or the shells."""
    assert shell_seeds.make_position_rng(7).random() != shell_seeds.make_heading_rng(7).random()
    assert (
        shell_seeds.make_shell_phase_rng(7).random() != shell_seeds.make_shell_rate_rng(7).random()
    )
    # And Test #1's salts are not reused, so a good tile seed says nothing here.
    from satisfying import seeds as tile_seeds

    assert shell_seeds.POSITION_STREAM_SALT != tile_seeds.POSITION_STREAM_SALT
    assert shell_seeds.HEADING_STREAM_SALT != tile_seeds.HEADING_STREAM_SALT


def test_the_ball_starts_inside_the_innermost_shell_and_not_touching_it() -> None:
    for seed in range(50):
        arena_run = simulate(seed, DEFAULT_CONFIG.replace(horizon=0.0))
        x, y, vx, vy = start_state(seed, DEFAULT_CONFIG, arena_run.arena)
        radius = math.hypot(x, y)
        inner = arena_run.arena.shells[0]
        assert radius < inner.apothem - DEFAULT_CONFIG.ball_radius - inner.thickness
        assert math.hypot(vx, vy) == pytest.approx(DEFAULT_CONFIG.speed, rel=1e-12)


# --------------------------------------------------------------------------
# The solver
# --------------------------------------------------------------------------


def test_solver_agrees_with_the_brute_force_reference() -> None:
    """Every contact search, checked against a sampler that shares no logic.

    The reference in `satisfying.shell_reference` walks the flight at a few
    thousand evenly spaced times and looks at every live panel. It is far too
    slow to simulate with and it has no geometric insight in it, which is
    precisely why agreement is evidence.
    """
    import satisfying.shell_escape as module
    from satisfying.shell_reference import first_contact_by_sampling, window_disagreement

    original = module._contact_in_interval
    checks = {"searches": 0, "mismatches": 0, "window": 0.0}

    def checked(state, x, y, vx, vy, t0, lo, hi, config):
        found = original(state, x, y, vx, vy, t0, lo, hi, config)
        checks["searches"] += 1
        samples = 2000
        reference = first_contact_by_sampling(state, x, y, vx, vy, t0, lo, hi, samples=samples)
        checks["window"] = max(
            checks["window"], window_disagreement(state, x + vx * lo, y + vy * lo, t0 + lo)
        )
        grid = (hi - lo) / samples
        got = found[0] if found else None
        if (reference is None) != (got is None):
            checks["mismatches"] += 1
        elif reference is not None and abs(reference - got) > 2.0 * grid + 1e-9:
            checks["mismatches"] += 1
        return found

    module._contact_in_interval = checked
    try:
        for seed in range(6):
            simulate(seed)
    finally:
        module._contact_in_interval = original

    assert checks["searches"] > 500, "the check has to actually have run"
    assert checks["mismatches"] == 0, checks
    assert checks["window"] == 0.0, "the windowed nearest-panel search missed a panel"


def test_the_ball_never_ends_up_inside_a_panel() -> None:
    """`max_penetration` over a population, which is how both bugs were found."""
    worst = 0.0
    for seed in range(200):
        run = simulate(seed)
        worst = max(worst, run.max_penetration)
    assert worst <= DEFAULT_CONFIG.clearance_tolerance * 2.0, worst


def test_no_run_crosses_a_shell_where_a_panel_was_still_standing() -> None:
    for seed in range(200):
        run = simulate(seed)
        assert run.anomalous_crossings == 0, f"seed {seed}"
        assert run.newton_failures == 0, f"seed {seed}"


def test_speed_is_exactly_constant() -> None:
    """The run's clock is the config's `speed` and nothing else."""
    for seed in range(60):
        run = simulate(seed)
        assert run.speed_drift_relative < 1e-12, f"seed {seed}: {run.speed_drift_relative}"
        for flight in run.flights:
            assert math.hypot(flight.vx, flight.vy) == pytest.approx(
                DEFAULT_CONFIG.speed, rel=1e-9
            )


def test_the_speed_constraint_is_reported_and_does_not_steer() -> None:
    """It changes magnitude only, so `max_speed_correction` is the whole story."""
    run = simulate(SEED_TIMEOUT)
    assert run.max_speed_correction > 0.0, "the walls do work; something was taken back out"
    assert run.max_speed_correction < 1.0, "a single contact must not double the speed"
    # With the constraint off, the ball heats up. That is the thing it exists
    # to prevent, and it is asserted rather than described.
    loose = simulate(SEED_TIMEOUT, DEFAULT_CONFIG.replace(constant_speed=False))
    assert loose.speed_drift_relative > 0.05


def test_ignoring_the_panel_motion_makes_contacts_chatter() -> None:
    """Why `panel_momentum_transfer` defaults to 1, asserted rather than asserted-to.

    With the transfer at 0 nothing can push the ball out of a wall sweeping
    into it, so a near-tangential arrival at a post is caught and repeats. The
    seed here is one that does it; the default config does not.
    """
    stuck = simulate(5, DEFAULT_CONFIG.replace(panel_momentum_transfer=0.0))
    sequence = [
        (e.data["shell_id"], e.data["panel_id"]) for e in stuck.events if e.kind == "collision"
    ]
    repeats = sum(1 for i in range(1, len(sequence)) if sequence[i] == sequence[i - 1])
    assert repeats > 20, "this seed is the fixture for the chatter; it stopped chattering"

    fine = simulate(5)
    sequence = [
        (e.data["shell_id"], e.data["panel_id"]) for e in fine.events if e.kind == "collision"
    ]
    repeats = sum(1 for i in range(1, len(sequence)) if sequence[i] == sequence[i - 1])
    assert repeats <= 3, repeats


def test_collision_response_reflects_about_the_contact_normal() -> None:
    run = simulate(SEED_TIMEOUT)
    for event in run.events:
        if event.kind != "collision":
            continue
        nx, ny = event.data["normal"]
        assert math.hypot(nx, ny) == pytest.approx(1.0, abs=1e-9)
        vin = event.data["velocity_in"]
        vout = event.data["velocity_out"]
        # Tangential component is untouched up to the speed renormalisation,
        # which scales both components by the same factor.
        tx, ty = -ny, nx
        tin = vin[0] * tx + vin[1] * ty
        tout = vout[0] * tx + vout[1] * ty
        assert tin * tout > 0 or abs(tin) < 1e-9, "the bounce reversed the tangential direction"
        assert event.data["impact_speed"] > 0.0, "a contact must have been approaching"


def test_the_ball_is_never_steered_towards_an_opening() -> None:
    """No term in the response knows where the holes are.

    A direct check on the code rather than on the trajectory: the reflection is
    a function of the contact normal and the panel's velocity, and `simulate`
    never reads the opening list while resolving one.
    """
    import inspect

    import satisfying.shell_escape as module

    source = inspect.getsource(module.simulate)
    body = source.split("# Damage, then possibly a break")[0]
    for forbidden in ("opening_of_slot", "passable_runs", "open_slots"):
        assert forbidden not in body, f"the collision response reads {forbidden}"


# --------------------------------------------------------------------------
# Damage and breaking
# --------------------------------------------------------------------------


def test_damage_accumulates_and_harder_hits_count_for_more() -> None:
    run = simulate(SEED_TIMEOUT)
    ledger: dict[tuple[int, int], float] = {}
    for event in run.events:
        if event.kind != "damage":
            continue
        key = (event.data["shell_id"], event.data["panel_id"])
        previous = ledger.get(key, 0.0)
        assert event.data["cumulative"] == pytest.approx(previous + event.data["added"], rel=1e-12)
        ledger[key] = event.data["cumulative"]
        expected = (
            abs(event.data["impact_speed"]) / run.config.damage_reference_speed
        ) ** run.config.damage_exponent
        assert event.data["added"] == pytest.approx(expected, rel=1e-12)

    repeated = [key for key, value in ledger.items() if value > 0]
    assert repeated, "nothing was damaged at all"
    adds = [e.data["added"] for e in run.events if e.kind == "damage"]
    assert max(adds) > min(adds) * 2, "impact strength has to matter"


def test_a_panel_breaks_exactly_once_and_stays_broken() -> None:
    run = simulate(SEED_TIMEOUT)
    seen: set[tuple[int, int]] = set()
    for event in run.events:
        if event.kind != "panel_break":
            continue
        key = (event.data["shell_id"], event.data["panel_id"])
        assert key not in seen, f"{key} broke twice"
        seen.add(key)
        assert event.data["cumulative"] >= run.config.break_threshold

    assert seen, "this fixture is supposed to break something"
    # And no damage is recorded against a panel after it breaks.
    broken_at = {
        (e.data["shell_id"], e.data["panel_id"]): e.t for e in run.events if e.kind == "panel_break"
    }
    for event in run.events:
        if event.kind != "damage":
            continue
        key = (event.data["shell_id"], event.data["panel_id"])
        if key in broken_at:
            assert event.t <= broken_at[key]


def test_a_broken_panel_becomes_a_real_passage() -> None:
    """Somebody eventually goes through one, and it is recorded as a break."""
    found = False
    for seed in range(60):
        run = simulate(seed)
        broken = {
            (e.data["shell_id"], e.data["panel_id"]) for e in run.events if e.kind == "panel_break"
        }
        for event in run.events:
            if event.kind not in ("shell_exit", "shell_entry"):
                continue
            if event.data["method"] != "break":
                continue
            key = (event.data["shell_id"], event.data["panel_id"])
            assert key in broken, "crossed a slot recorded as a break that never broke"
            assert event.t > next(
                e.t for e in run.events if e.kind == "panel_break" and (e.data["shell_id"], e.data["panel_id"]) == key
            )
            found = True
    assert found, "no run in the sample used a broken panel"


def test_breaking_can_be_turned_off_entirely() -> None:
    run = simulate(SEED_TIMEOUT, DEFAULT_CONFIG.replace(breakable=False))
    assert run.breaks == 0
    assert not [e for e in run.events if e.kind in ("damage", "panel_break")]
    assert all(
        e.data["method"] != "break" for e in run.events if e.kind in ("shell_exit", "shell_entry")
    )


# --------------------------------------------------------------------------
# Progression and outcomes
# --------------------------------------------------------------------------


def test_regions_change_only_by_one_and_only_through_a_hole() -> None:
    for seed in range(40):
        run = simulate(seed)
        region = 0
        for event in run.events:
            if event.kind not in ("shell_exit", "shell_entry"):
                continue
            assert event.data["from_region"] == region
            assert abs(event.data["to_region"] - region) == 1
            assert event.data["method"] in ("opening", "break")
            region = event.data["to_region"]
        assert region == run.final_region


def test_escape_happens_only_after_leaving_the_outermost_shell() -> None:
    run = simulate(SEED_ESCAPE_VIA_OPENING)
    assert run.escaped
    escape = next(e for e in run.events if e.kind == "escape")
    last_exit = [e for e in run.events if e.kind == "shell_exit"][-1]
    assert last_exit.data["shell_id"] == run.arena.shell_count - 1
    assert last_exit.data["to_region"] == run.arena.shell_count
    assert escape.t >= last_exit.t, "the ball clears the wall after crossing it"
    assert math.hypot(*escape.data["position"]) > run.arena.outer_radius
    assert escape is run.events[-1], "escape is the last thing that happens"


def test_both_escape_routes_occur() -> None:
    opening = simulate(SEED_ESCAPE_VIA_OPENING)
    broken = simulate(SEED_ESCAPE_VIA_BREAK)
    assert opening.escaped and broken.escaped
    assert next(e for e in opening.events if e.kind == "escape").data["method"] == "opening"
    assert next(e for e in broken.events if e.kind == "escape").data["method"] == "break"


def test_a_run_that_does_not_get_out_fails_at_the_horizon() -> None:
    run = simulate(SEED_TIMEOUT)
    assert not run.escaped
    assert run.failure_reason == "timeout"
    assert run.duration == pytest.approx(DEFAULT_CONFIG.horizon)
    failure = run.events[-1]
    assert failure.kind == "failure"
    assert failure.data["reason"] == "timeout"
    assert failure.data["region"] < run.arena.shell_count


def test_the_ball_may_fall_back_inward() -> None:
    run = simulate(SEED_WITH_REGRESSION)
    entries = [e for e in run.events if e.kind == "shell_entry"]
    assert entries, "this fixture is supposed to yo-yo"
    for event in entries:
        assert event.data["to_region"] == event.data["from_region"] - 1
    assert run.max_region > run.final_region


def test_success_is_not_guaranteed_and_failure_is_not_either() -> None:
    outcomes = [simulate(seed).escaped for seed in range(120)]
    assert any(outcomes) and not all(outcomes), "the question has to be a real question"


# --------------------------------------------------------------------------
# Near misses
# --------------------------------------------------------------------------


def test_a_near_miss_is_geometric_and_the_threshold_is_reported() -> None:
    run = simulate(SEED_ESCAPE_VIA_OPENING)
    misses = [e for e in run.events if e.kind == "near_miss"]
    assert misses, "this fixture is supposed to have near misses"
    for event in misses:
        data = event.data
        assert data["angular_separation"] >= 0.0
        assert data["arc_separation"] == pytest.approx(
            data["angular_separation"] * math.hypot(*data["ball_position"]), rel=1e-9
        )
        assert data["arc_separation_ball_radii"] == pytest.approx(
            data["arc_separation"] / run.config.ball_radius, rel=1e-9
        )
        by_arc = data["arc_separation_ball_radii"] <= run.config.near_miss_arc_ball_radii
        by_time = data["time_separation"] <= run.config.near_miss_seconds
        assert by_arc or by_time
        assert data["criterion"] == ("arc+time" if (by_arc and by_time) else ("arc" if by_arc else "time"))
        # And it coincides with a collision on the same shell.
        assert any(
            c.kind == "collision" and c.t == event.t and c.data["shell_id"] == data["shell_id"]
            for c in run.events
        )


def test_a_distant_impact_is_not_a_near_miss() -> None:
    """Tightening the thresholds to nothing must leave no near misses at all."""
    strict = DEFAULT_CONFIG.replace(near_miss_arc_ball_radii=0.0, near_miss_seconds=0.0)
    run = simulate(SEED_ESCAPE_VIA_OPENING, strict)
    assert run.near_misses == 0
    loose = DEFAULT_CONFIG.replace(near_miss_arc_ball_radii=50.0, near_miss_seconds=50.0)
    assert simulate(SEED_ESCAPE_VIA_OPENING, loose).near_misses > run.near_misses


def test_the_near_miss_threshold_does_not_change_the_trajectory() -> None:
    """A reporting threshold must report, never steer."""
    base = simulate(SEED_ESCAPE_VIA_OPENING)
    loose = simulate(
        SEED_ESCAPE_VIA_OPENING,
        DEFAULT_CONFIG.replace(near_miss_arc_ball_radii=50.0, near_miss_seconds=50.0),
    )
    base_hits = [
        (e.t, e.data["position"]) for e in base.events if e.kind == "collision"
    ]
    loose_hits = [
        (e.t, e.data["position"]) for e in loose.events if e.kind == "collision"
    ]
    assert base_hits == loose_hits


def test_near_misses_count_only_outward_attempts_on_the_frontier_shell() -> None:
    for seed in range(20):
        run = simulate(seed)
        for event in run.events:
            if event.kind != "near_miss":
                continue
            assert event.data["shell_id"] == event.data["region"], (
                "a near miss is a miss of the shell the ball is trying to leave"
            )


# --------------------------------------------------------------------------
# The event stream
# --------------------------------------------------------------------------


def test_the_event_schema_is_frozen() -> None:
    """Phase 2A and Phase 2B are written against exactly this."""
    assert SCHEMA_VERSION == "category3-test2-shell-escape/1.0.0"
    assert EVENT_KINDS == (
        "collision",
        "near_miss",
        "damage",
        "panel_break",
        "shell_exit",
        "shell_entry",
        "escape",
        "failure",
    )
    assert EVENT_SCHEMA["collision"] == (
        "shell_id",
        "panel_id",
        "region",
        "position",
        "contact_point",
        "contact_angle",
        "normal",
        "velocity_in",
        "velocity_out",
        "impact_speed",
        "speed",
        "incidence",
        "feature",
        "grazing",
        "radial_outward",
        "panel_local_offset",
    )
    assert EVENT_SCHEMA["near_miss"] == (
        "shell_id",
        "panel_id",
        "opening_id",
        "region",
        "ball_position",
        "ball_angle",
        "opening_centre_angle",
        "opening_half_width",
        "angular_separation",
        "arc_separation",
        "arc_separation_ball_radii",
        "relative_angular_speed",
        "time_separation",
        "signed_lead",
        "criterion",
    )
    assert EVENT_SCHEMA["damage"] == (
        "shell_id",
        "panel_id",
        "added",
        "cumulative",
        "threshold",
        "impact_speed",
    )
    assert EVENT_SCHEMA["panel_break"] == (
        "shell_id",
        "panel_id",
        "position",
        "break_angle",
        "cumulative",
        "hits",
    )
    assert (
        EVENT_SCHEMA["shell_exit"]
        == EVENT_SCHEMA["shell_entry"]
        == (
            "shell_id",
            "panel_id",
            "method",
            "opening_id",
            "from_region",
            "to_region",
            "position",
            "crossing_angle",
            "local_offset",
            "dwell_seconds",
        )
    )
    assert EVENT_SCHEMA["escape"] == ("shell_id", "method", "position", "collisions", "breaks")
    assert EVENT_SCHEMA["failure"] == ("reason", "region", "collisions", "breaks")


def test_every_event_matches_the_schema_exactly() -> None:
    for seed in (SEED_TIMEOUT, SEED_ESCAPE_VIA_OPENING, SEED_ESCAPE_VIA_BREAK):
        validate_events(simulate(seed).events)


def test_events_are_in_time_order_and_grouped_consistently() -> None:
    for seed in range(30):
        run = simulate(seed)
        times = [e.t for e in run.events]
        assert times == sorted(times), f"seed {seed}"
        # A damage event always follows the collision that caused it, at the
        # same instant, on the same panel.
        for index, event in enumerate(run.events):
            if event.kind != "damage":
                continue
            earlier = [
                e
                for e in run.events[:index]
                if e.kind == "collision"
                and e.t == event.t
                and e.data["shell_id"] == event.data["shell_id"]
                and e.data["panel_id"] == event.data["panel_id"]
            ]
            assert earlier, f"seed {seed}: damage with no collision before it"
        # Exactly one terminal event.
        terminal = [e for e in run.events if e.kind in ("escape", "failure")]
        assert len(terminal) == 1
        assert terminal[0] is run.events[-1]


def test_the_flight_list_is_the_trajectory() -> None:
    run = simulate(SEED_ESCAPE_VIA_OPENING)
    for index in range(len(run.flights) - 1):
        here = run.flights[index]
        there = run.flights[index + 1]
        dt = there.t - here.t
        assert dt >= 0.0
        if index + 2 < len(run.flights):
            # A flight ends where the next begins, up to the skin lift applied
            # at a bounce.
            drift = math.hypot(here.x + here.vx * dt - there.x, here.y + here.vy * dt - there.y)
            assert drift < 1e-3, (index, drift)


# --------------------------------------------------------------------------
# The playback document
# --------------------------------------------------------------------------


def test_the_document_reproduces_the_run_exactly() -> None:
    for seed in (SEED_TIMEOUT, SEED_ESCAPE_VIA_OPENING, SEED_ESCAPE_VIA_BREAK):
        document = playback_document(simulate(seed))
        result = verify_document(document)
        assert result["digest_matches"], result
        assert result["config_digest_matches"]
        assert result["event_count_matches"]
        assert result["flight_count_matches"]
        assert result["kinds_match"]


def test_the_document_survives_a_json_round_trip() -> None:
    document = playback_document(simulate(SEED_ESCAPE_VIA_BREAK))
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "run.json")
        write_playback(document, path)
        reloaded = read_playback(path)
    assert reloaded["digest"] == document["digest"]
    assert verify_document(reloaded)["digest_matches"]
    assert reloaded["document_version"] == DOCUMENT_VERSION
    assert reloaded["schema_version"] == SCHEMA_VERSION


def test_the_digest_changes_when_anything_about_the_run_changes() -> None:
    base = simulate(SEED_ESCAPE_VIA_OPENING).state_digest()
    assert simulate(SEED_ESCAPE_VIA_OPENING).state_digest() == base
    assert simulate(SEED_ESCAPE_VIA_OPENING + 1).state_digest() != base
    assert simulate(SEED_ESCAPE_VIA_OPENING, DEFAULT_CONFIG.replace(speed=17.0001)).state_digest() != base
    assert (
        simulate(SEED_ESCAPE_VIA_OPENING, DEFAULT_CONFIG.replace(break_threshold=1.61)).state_digest()
        != base
    )


def test_a_consumer_can_replay_position_region_and_geometry() -> None:
    run = simulate(SEED_ESCAPE_VIA_BREAK)
    document = playback_document(run)
    for fraction in (0.0, 0.17, 0.4, 0.63, 0.99):
        t = fraction * run.duration
        x, y = position_at(document, t)
        # The document's own answer must match the run's flights.
        index = max(i for i, f in enumerate(run.flights) if f.t <= t)
        flight = run.flights[index]
        assert x == pytest.approx(flight.x + flight.vx * (t - flight.t), abs=1e-9)
        assert y == pytest.approx(flight.y + flight.vy * (t - flight.t), abs=1e-9)
        assert 0 <= region_at(document, t) <= run.arena.shell_count

    broke = [e for e in run.events if e.kind == "panel_break"]
    assert broke
    first = broke[0]
    shell_id, panel_id = first.data["shell_id"], first.data["panel_id"]
    assert panel_closed_at(document, shell_id, panel_id, first.t - 1e-6)
    assert not panel_closed_at(document, shell_id, panel_id, first.t + 1e-6)
    open_slot = run.arena.shells[0].open_slots[0]
    assert not panel_closed_at(document, 0, open_slot, 0.0)


def test_the_document_carries_everything_a_later_phase_needs() -> None:
    """The visual and audio branches must not have to import the simulation."""
    document = playback_document(simulate(SEED_ESCAPE_VIA_OPENING))
    for key in (
        "document_version",
        "schema_version",
        "seed",
        "config",
        "arena",
        "shells",
        "flights",
        "panel_states",
        "events",
        "summary",
        "digest",
    ):
        assert key in document, key
    shell = document["shells"][0]
    for key in ("radius", "apothem", "panel_count", "thickness", "theta0", "omega", "open_slots"):
        assert key in shell, key
    assert json.dumps(document), "the document has to be serialisable as it stands"


# --------------------------------------------------------------------------
# The evaluator
# --------------------------------------------------------------------------


def test_the_evaluator_reports_the_things_the_brief_asks_for() -> None:
    evaluation = evaluate_seed(SEED_ESCAPE_VIA_OPENING)
    metrics = evaluation.metrics
    for section in (
        "outcome",
        "progression",
        "collisions",
        "near_misses",
        "damage",
        "routes",
        "stagnation",
        "repetition",
        "escalation",
        "instruments",
    ):
        assert section in metrics, section
    assert metrics["outcome"]["escaped"] is True
    assert len(metrics["escalation"]["collisions"]) == 3
    assert sum(metrics["escalation"]["collisions"]) == metrics["collisions"]["total"]
    assert sum(metrics["escalation"]["near_misses"]) == metrics["near_misses"]["total"]
    assert sum(metrics["escalation"]["breaks"]) == metrics["damage"]["breaks"]
    assert sum(metrics["collisions"]["per_shell"]) == metrics["collisions"]["total"]
    assert sum(metrics["near_misses"]["per_shell"]) == metrics["near_misses"]["total"]
    assert sum(metrics["damage"]["breaks_per_shell"]) == metrics["damage"]["breaks"]
    assert sum(metrics["progression"]["dwell"]) == pytest.approx(metrics["outcome"]["duration"])
    assert metrics["progression"]["shells_passed"] == metrics["outcome"]["max_region"]


def test_route_counts_separate_progression_from_yo_yoing() -> None:
    evaluation = evaluate_seed(SEED_WITH_REGRESSION)
    routes = evaluation.metrics["routes"]
    progression = routes["progression_opening"] + routes["progression_break"]
    assert progression == evaluation.metrics["outcome"]["max_region"]
    assert routes["exit_opening"] + routes["exit_break"] >= progression, (
        "every progression step is an outward crossing, and most runs make more"
    )


def test_flags_name_the_specific_complaint() -> None:
    from satisfying.shell_evaluator import EvaluationThresholds

    fast = evaluate_seed(22)  # escapes in under five seconds
    assert "instant_escape" in fast.flags
    assert not fast.usable

    failed = evaluate_seed(SEED_TIMEOUT)
    assert "failed" in failed.flags

    # A threshold nobody can meet flags everything, which is how a caller
    # checks that a flag is a threshold and not a mood.
    impossible = EvaluationThresholds(min_near_misses=10_000)
    assert "too_few_near_misses" in evaluate_seed(SEED_ESCAPE_VIA_OPENING, thresholds=impossible).flags


def test_the_stagnation_metrics_measure_different_things() -> None:
    metrics = evaluate_seed(SEED_TIMEOUT).metrics["stagnation"]
    assert metrics["longest_no_event"] <= metrics["longest_no_near_miss"] + 1e-9
    assert metrics["longest_no_event"] <= metrics["longest_no_progress"] + 1e-9
    assert metrics["middle_third_stagnation"] <= metrics["longest_no_event"] + 1e-9


def test_a_two_panel_bounce_loop_is_detected() -> None:
    from satisfying.shell_evaluator import _longest_cycle

    assert _longest_cycle([1, 2, 1, 2, 1, 2, 1, 2], 6) == (6, 2)
    assert _longest_cycle([1, 1, 1, 1], 6) == (3, 1)
    run, period = _longest_cycle([1, 2, 3, 4, 5, 6, 7], 6)
    assert run == 0 and period == 0


def test_summarise_reports_distributions_and_never_a_score() -> None:
    evaluations = [evaluate_seed(seed) for seed in range(80)]
    summary = summarise(evaluations)
    assert summary["seeds"] == 80
    assert 0.0 < summary["outcome"]["escape_rate"] < 1.0
    assert set(summary["flags"]) >= {"failed", "instant_escape", "repetitive_orbit"}
    assert "score" not in json.dumps(summary)
    assert summary["instruments"]["runs_with_penetration"] == 0
    assert summary["instruments"]["runs_with_anomalies"] == 0
    assert summary["instruments"]["runs_with_solver_failures"] == 0
    assert 0.0 <= summary["routes"]["progression_opening_share"] <= 1.0


# --------------------------------------------------------------------------
# The batch driver
# --------------------------------------------------------------------------


def test_the_batch_record_carries_what_the_summary_needs() -> None:
    records = run_batch(range(24), workers=1)
    assert len(records) == 24
    rebuilt = summarise(_rehydrate(records))
    direct = summarise([evaluate_seed(seed) for seed in range(24)])
    for key in ("escape_rate", "usable_rate", "in_acceptable_band"):
        assert rebuilt["outcome"][key] == direct["outcome"][key]
    assert rebuilt["routes"]["progression_opening_share"] == pytest.approx(
        direct["routes"]["progression_opening_share"]
    )


def test_the_shortlist_spreads_across_bands_and_keeps_both_endings() -> None:
    records = run_batch(range(600), workers=None)
    picked = shortlist(records, take=12)
    assert picked, "the population should contain clean in-band seeds"
    assert len({r["seed"] for r in picked}) == len(picked)
    for record in picked:
        assert not record["flags"]
        assert DEFAULT_THRESHOLDS.acceptable_low <= record["duration"] <= DEFAULT_THRESHOLDS.acceptable_high
    assert len({r["band"] for r in picked}) >= 2, "a shortlist of one band is a ranked list"
    # And every candidate gives every shell a real share of the runtime. Both
    # of the continuous ranking terms tried before this one collapsed the list
    # to one extreme or the other - all core, or all outer annulus.
    for record in picked:
        spread = sum(1 for value in record["dwell"][:6] if value / record["duration"] >= 0.08)
        assert spread >= 5, (record["seed"], record["dwell"])
        assert record["max_region_share"] <= DEFAULT_THRESHOLDS.max_region_share


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_the_simulation_does_not_depend_on_godot_audio_or_rendering() -> None:
    """Phase 1 is physics and measurement; the later branches consume it."""
    import ast
    import pathlib

    forbidden = {"godot", "audio", "rendering", "PIL", "numpy", "replay", "production"}
    for name in (
        "shell_seeds",
        "shell_arena",
        "shell_escape",
        "shell_playback",
        "shell_evaluator",
        "shell_escape_cli",
        "shell_reference",
    ):
        path = pathlib.Path(REPO_ROOT) / "satisfying" / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root not in forbidden, f"{name} imports {root}"


def test_test_two_does_not_import_test_one() -> None:
    """The two Category 3 experiments share conventions, not code."""
    import ast
    import pathlib

    tile_modules = {
        p.stem for p in (pathlib.Path(REPO_ROOT) / "satisfying").glob("tile_*.py")
    } | {"seeds"}
    for name in ("shell_arena", "shell_escape", "shell_playback", "shell_evaluator"):
        path = pathlib.Path(REPO_ROOT) / "satisfying" / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("satisfying"):
                for alias in node.names:
                    assert alias.name not in tile_modules, f"{name} imports {alias.name}"
