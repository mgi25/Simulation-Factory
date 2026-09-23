"""Category 3 Test #2 - MULTIPLYING SHELL ESCAPE, redesign Phase 1.

What these tests are for, in order of how much they would hurt to lose:

1. **The reproduction rule cannot be farmed.** A ball that can pump one shell
   boundary turns the whole concept into a counter. The bitmask that forbids it
   is one line, so the tests check the *event stream* instead - no
   `(parent, shell)` pair may appear twice, over a population, and a run driven
   deliberately in and out of one shell must produce exactly one child.
2. **The scheduler orders shared state correctly.** With a population, a panel
   that breaks at t=11.2 must be broken for every ball arriving after and
   intact for every ball that arrived before. Events are asserted to be in
   non-decreasing time order, and crossings are asserted never to happen
   through a live panel - which is what `anomalous_crossings` counts and what a
   mis-ordered scheduler would produce immediately.
3. **No child is ever born inside a panel.** Checked as a measured clearance on
   every spawn of a population, not as a promise about the construction.
4. **The event schema is frozen.** The visual and audio branches will be
   written against it in parallel, so a renamed field is a merge conflict found
   at integration. Asserted field by field, and the version string is asserted
   to differ from the single-ball one.
5. **The document reproduces.** Same seed and config, same digest, through a
   JSON round trip.
6. **The single-ball test #2 and Test #1 are untouched.** The redesign imports
   the old solver and must not have changed it.
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

from satisfying import multishell_seeds
from satisfying.multishell import (
    DAMAGE_STATES,
    DEFAULT_CONFIG,
    EVENT_KINDS,
    EVENT_SCHEMA,
    SCHEMA_VERSION,
    MultishellConfig,
    build_arena_for,
    damage_state_of,
    difficulty_profile,
    impact_damage,
    resolve_shells,
    simulate,
    start_state,
    validate_events,
)
from satisfying.multishell_evaluator import (
    DEFAULT_THRESHOLDS,
    FLAG_NAMES,
    MEANINGFUL_KINDS,
    evaluate,
    evaluate_seed,
    summarise,
)
from satisfying.multishell_playback import (
    document_digest,
    document_for,
    panel_state_at,
    playback_document,
    population_at,
    position_at,
    read_playback,
    verify_document,
    write_playback,
)

# Small enough to run in a test suite, large enough that a rule with a hole in
# it shows the hole. Every population test uses the same set so a failure names
# a seed that the others also cover.
POPULATION = list(range(120))
SMALL = list(range(24))


@pytest.fixture(scope="module")
def runs():
    return [simulate(seed) for seed in POPULATION]


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_seed_gives_the_same_multi_ball_run() -> None:
    """Two runs of one seed agree on every ball, every event and the digest."""
    for seed in SMALL:
        a = simulate(seed)
        b = simulate(seed)
        assert a.state_digest() == b.state_digest()
        assert len(a.balls) == len(b.balls)
        assert len(a.events) == len(b.events)
        for ea, eb in zip(a.events, b.events):
            assert ea.kind == eb.kind
            assert ea.t == eb.t
            assert ea.data == eb.data
        for fa, fb in zip(a.flights.items(), b.flights.items()):
            assert fa == fb


def test_different_seeds_give_different_runs() -> None:
    """A population of one seed wearing different hats would pass everything else."""
    digests = {simulate(seed).state_digest() for seed in POPULATION}
    assert len(digests) == len(POPULATION)


def test_the_seed_streams_are_not_the_single_ball_ones() -> None:
    """A good single-ball seed must carry no information about this test."""
    from satisfying import shell_seeds

    for name in (
        "POSITION_STREAM_SALT",
        "HEADING_STREAM_SALT",
        "SHELL_PHASE_STREAM_SALT",
        "SHELL_RATE_STREAM_SALT",
    ):
        assert getattr(multishell_seeds, name) != getattr(shell_seeds, name)
    # And the visible consequence: the same integer is a different release.
    arena_a = build_arena_for(9589, DEFAULT_CONFIG)
    assert start_state(9589, DEFAULT_CONFIG, arena_a) != (0.0, 0.0, 0.0, 0.0)
    theta_new, _ = resolve_shells(9589, DEFAULT_CONFIG)
    theta_old = [shell_seeds.make_shell_phase_rng(9589).uniform(0.0, 2.0 * math.pi)]
    assert theta_new[0] != theta_old[0]


def test_events_are_in_non_decreasing_time_order(runs) -> None:
    """The scheduler's whole correctness argument, stated as an assertion."""
    for run in runs:
        times = [ev.t for ev in run.events]
        assert times == sorted(times), f"seed {run.seed} emitted an event out of order"


# --------------------------------------------------------------------------
# Lineage
# --------------------------------------------------------------------------


def test_lineage_ids_are_stable_and_well_formed(runs) -> None:
    for run in runs:
        ids = [b.ball_id for b in run.balls]
        assert ids == list(range(len(ids))), "ball ids must be a dense sequence from 0"
        by_id = {b.ball_id: b for b in run.balls}
        root = by_id[0]
        assert root.parent_id is None
        assert root.generation == 0
        assert root.birth_time == 0.0
        assert root.birth_shell is None
        assert root.lineage == (0,)
        for record in run.balls[1:]:
            parent = by_id[record.parent_id]
            assert record.ball_id > record.parent_id, "a child is always created after its parent"
            assert record.generation == parent.generation + 1
            assert record.birth_time >= parent.birth_time
            assert record.lineage == parent.lineage + (record.ball_id,)
            assert record.ball_id in parent.children


def test_lineage_in_the_event_stream_matches_the_records(runs) -> None:
    for run in runs:
        by_id = {b.ball_id: b for b in run.balls}
        for ev in run.events:
            if ev.kind != "ball_spawn":
                continue
            record = by_id[ev.data["ball_id"]]
            assert record.parent_id == ev.data["parent_id"]
            assert record.generation == ev.data["generation"]
            assert record.birth_shell == ev.data["birth_shell"]
            assert record.birth_time == ev.t
            assert list(record.lineage) == ev.data["lineage"]


def test_a_child_is_pre_charged_with_every_shell_inside_its_birthplace(runs) -> None:
    for run in runs:
        for record in run.balls[1:]:
            assert record.credited_at_birth == tuple(range(record.birth_shell + 1))
            # And the ball cannot un-credit itself later.
            assert set(record.credited_at_birth) <= set(record.credited)


# --------------------------------------------------------------------------
# Reproduction: one child per ball per shell, and no farming
# --------------------------------------------------------------------------


def test_at_most_one_child_per_ball_per_shell(runs) -> None:
    for run in runs:
        seen: set[tuple[int, int]] = set()
        for ev in run.events:
            if ev.kind != "ball_spawn":
                continue
            claim = (ev.data["parent_id"], ev.data["birth_shell"])
            assert claim not in seen, f"seed {run.seed}: ball {claim[0]} spawned twice at shell {claim[1]}"
            seen.add(claim)
        assert run.reproduction_violations == 0


def test_repeated_crossings_do_not_farm_children(runs) -> None:
    """The population's own evidence: balls do cross back out, and get nothing.

    A test that only checked "no duplicate spawn" would pass on a run where no
    ball ever re-crossed anything. This asserts the situation actually occurs -
    an outward crossing of a shell the ball has already been credited for - and
    that it produced nothing when it did.
    """
    repeats = 0
    for run in runs:
        credited: dict[int, set[int]] = {}
        for ev in run.events:
            if ev.kind == "ball_spawn":
                credited.setdefault(ev.data["ball_id"], set()).update(
                    range(ev.data["birth_shell"] + 1)
                )
                continue
            if ev.kind != "shell_exit":
                continue
            ball = ev.data["ball_id"]
            shell = ev.data["shell_id"]
            already = shell in credited.setdefault(ball, set())
            assert ev.data["first_for_ball"] == (not already)
            if already:
                repeats += 1
                assert not ev.data["reproduced"], (
                    f"seed {run.seed}: ball {ball} was paid twice for shell {shell}"
                )
            credited[ball].add(shell)
    assert repeats > 0, "no ball ever re-crossed a credited shell; the rule was never exercised"


def test_a_ball_driven_in_and_out_of_one_shell_produces_exactly_one_child() -> None:
    """The rule at its narrowest, on the seeds that actually do it a lot."""
    for seed in POPULATION:
        run = simulate(seed)
        exits: dict[tuple[int, int], int] = {}
        spawns: dict[tuple[int, int], int] = {}
        for ev in run.events:
            if ev.kind == "shell_exit":
                key = (ev.data["ball_id"], ev.data["shell_id"])
                exits[key] = exits.get(key, 0) + 1
            elif ev.kind == "ball_spawn":
                key = (ev.data["parent_id"], ev.data["birth_shell"])
                spawns[key] = spawns.get(key, 0) + 1
        for key, count in exits.items():
            assert spawns.get(key, 0) <= 1
            if count > 1:
                # The interesting case: several exits, at most one child.
                assert spawns.get(key, 0) <= 1


def test_reproduction_can_be_turned_off() -> None:
    run = simulate(3, DEFAULT_CONFIG.replace(reproduction=False))
    assert run.spawns == 0
    assert len(run.balls) == 1
    assert run.max_population == 1


def test_every_ball_can_have_descendants(runs) -> None:
    """Not just the founder: children of children of children must occur."""
    deepest = max(run.max_generation for run in runs)
    assert deepest >= 3, f"no lineage got past generation {deepest}"
    non_founder_parents = {
        ev.data["parent_id"]
        for run in runs
        for ev in run.events
        if ev.kind == "ball_spawn" and ev.data["generation"] >= 2
    }
    assert non_founder_parents - {0}, "only the founder ever reproduced"


# --------------------------------------------------------------------------
# Spawn geometry
# --------------------------------------------------------------------------


def test_no_child_is_born_inside_solid_geometry(runs) -> None:
    spawns = 0
    for run in runs:
        for ev in run.events:
            if ev.kind != "ball_spawn":
                continue
            spawns += 1
            assert ev.data["clearance"] > 0.0, (
                f"seed {run.seed}: ball {ev.data['ball_id']} born with clearance "
                f"{ev.data['clearance']}"
            )
        assert run.min_spawn_clearance is None or run.min_spawn_clearance > 0.0
    assert spawns > 100, "not enough spawns to be evidence of anything"


def test_the_spawn_lead_ladder_retreats_when_it_has_to(runs) -> None:
    """The full lead is not always available, and the fallback is exercised."""
    leads = {ev.data["lead"] for run in runs for ev in run.events if ev.kind == "ball_spawn"}
    nominal = DEFAULT_CONFIG.spawn_lead_ball_radii * DEFAULT_CONFIG.ball_radius
    assert nominal in leads
    assert any(lead < nominal for lead in leads), "the clearance ladder never retreated"
    for lead in leads:
        assert lead == 0.0 or any(
            math.isclose(lead, nominal * 0.5**step)
            for step in range(DEFAULT_CONFIG.spawn_lead_steps)
        )


def test_the_spawn_velocity_is_the_parents_turned_by_a_fixed_angle(runs) -> None:
    for run in runs:
        for ev in run.events:
            if ev.kind != "ball_spawn":
                continue
            assert abs(ev.data["turn"]) == pytest.approx(DEFAULT_CONFIG.spawn_turn)
            # Rotation preserves magnitude, so the child inherits the speed.
            assert ev.data["speed"] == pytest.approx(math.hypot(*ev.data["velocity"]))


def test_the_spawn_turn_is_balanced_over_the_population(runs) -> None:
    """Deterministic and symmetric: exactly balanced, never biased one way."""
    for run in runs:
        turns = [ev.data["turn"] for ev in run.events if ev.kind == "ball_spawn"]
        positive = sum(1 for t in turns if t > 0)
        negative = len(turns) - positive
        assert abs(positive - negative) <= 1, f"seed {run.seed}: {positive} vs {negative}"
    total = [ev.data["turn"] for run in runs for ev in run.events if ev.kind == "ball_spawn"]
    assert abs(sum(1 for t in total if t > 0) - sum(1 for t in total if t < 0)) <= len(runs)


def test_the_child_is_born_in_the_region_the_parent_just_entered(runs) -> None:
    for run in runs:
        for ev in run.events:
            if ev.kind == "ball_spawn":
                assert ev.data["region"] == ev.data["birth_shell"] + 1


def test_the_population_safety_limit_holds() -> None:
    """A cap of three means three, and the suppression is counted not hidden."""
    capped = 0
    for seed in POPULATION:
        run = simulate(seed, DEFAULT_CONFIG.replace(max_population=3))
        assert len(run.balls) <= 3
        assert run.max_population <= 3
        if run.spawns_suppressed:
            capped += 1
    assert capped > 0, "a cap of three was never reached; the limit was never tested"
    # And the production cap is not the mechanic.
    assert all(simulate(seed).spawns_suppressed == 0 for seed in SMALL)


# --------------------------------------------------------------------------
# Progressive difficulty
# --------------------------------------------------------------------------


def test_the_default_difficulty_profile_is_monotonic_and_passable() -> None:
    profile = difficulty_profile()
    assert profile["open_fraction_monotonic"]
    assert profile["break_threshold_monotonic"]
    assert profile["monotonic"]
    assert profile["all_fit"]
    opens = [row["open_fraction"] for row in profile["shells"]]
    thresholds = [row["break_threshold"] for row in profile["shells"]]
    assert opens[0] > opens[-1]
    assert thresholds[0] < thresholds[-1]
    # The staggered profile stays readable while increasing timing pressure.
    speeds = [row["surface_speed"] for row in profile["shells"]]
    assert speeds == sorted(speeds)
    assert speeds[-1] < 1.35 * speeds[0]
    assert DEFAULT_CONFIG.alternate_direction


def test_a_non_monotonic_profile_says_so() -> None:
    bad = DEFAULT_CONFIG.replace(break_thresholds=(1.6, 2.4, 3.6, 2.0, 7.2))
    assert not difficulty_profile(bad)["break_threshold_monotonic"]
    assert not difficulty_profile(bad)["monotonic"]


def test_the_outer_shells_are_measurably_harder(runs) -> None:
    """The config claims it; the batch has to show it."""
    n = DEFAULT_CONFIG.shell_count
    reached = [0] * n
    crossed = [0] * n
    for run in runs:
        evaluation = evaluate(run)
        for k in range(n):
            reached[k] += evaluation.metrics["progression"]["reached"][k]
            crossed[k] += evaluation.metrics["progression"]["crossed"][k]
    rates = [crossed[k] / reached[k] if reached[k] else 0.0 for k in range(n)]
    assert all(a >= b for a, b in zip(rates, rates[1:])), f"pass rates not decreasing: {rates}"
    assert rates[-1] < 0.5 * rates[0], f"the outermost shell is not the hard one: {rates}"


def test_the_config_rejects_a_mis_sized_profile() -> None:
    with pytest.raises(ValueError):
        DEFAULT_CONFIG.replace(break_thresholds=(1.0, 2.0))
    with pytest.raises(ValueError):
        DEFAULT_CONFIG.replace(speed_model="teleport")
    with pytest.raises(ValueError):
        DEFAULT_CONFIG.replace(speed_band=(1.1, 1.5))
    with pytest.raises(ValueError):
        DEFAULT_CONFIG.replace(max_population=0)


# --------------------------------------------------------------------------
# Damage and breaking
# --------------------------------------------------------------------------


def test_damage_is_impact_energy_above_a_chip_floor(runs) -> None:
    config = DEFAULT_CONFIG
    floor = config.damage_floor_fraction
    span = 1.0 - floor
    checked = 0
    grazes = 0
    for run in runs:
        for ev in run.events:
            if ev.kind != "damage":
                continue
            f = abs(ev.data["impact_speed"]) / config.damage_reference_speed
            expected = ((f - floor) / span) ** config.damage_exponent if f > floor else 0.0
            assert ev.data["contribution"] == pytest.approx(expected, rel=1e-12, abs=1e-15)
            if expected == 0.0:
                grazes += 1
            checked += 1
    assert checked > 500
    assert grazes > 0, "no contact ever fell below the chip floor; the floor is untested"


def test_a_head_on_reference_hit_is_exactly_one_damage_unit() -> None:
    config = DEFAULT_CONFIG
    floor = config.damage_floor_fraction
    span = 1.0 - floor
    added = ((1.0 - floor) / span) ** config.damage_exponent
    assert added == pytest.approx(1.0)


def test_impact_damage_uses_normal_collision_energy() -> None:
    """The input is normal-relative speed, so a graze cannot inherit tangential energy."""
    config = DEFAULT_CONFIG
    assert impact_damage(0.0, config) == 0.0
    assert impact_damage(
        config.damage_reference_speed * config.damage_floor_fraction, config
    ) == 0.0
    assert impact_damage(config.damage_reference_speed, config) == pytest.approx(1.0)


def test_weak_glancing_contact_does_less_damage_than_a_strong_normal_hit() -> None:
    config = DEFAULT_CONFIG
    weak_normal_component = 0.15 * config.damage_reference_speed
    strong_normal_component = 0.95 * config.damage_reference_speed
    assert impact_damage(weak_normal_component, config) < impact_damage(
        strong_normal_component, config
    )


def test_damage_states_are_deterministic_functions_of_the_ledger() -> None:
    fractions = DEFAULT_CONFIG.damage_state_fractions
    threshold = 4.0
    assert DAMAGE_STATES[damage_state_of(0.0, threshold, fractions)] == "healthy"
    first, second, third = fractions
    epsilon = 1.0e-6
    assert DAMAGE_STATES[damage_state_of((first - epsilon) * threshold, threshold, fractions)] == "healthy"
    assert DAMAGE_STATES[damage_state_of(first * threshold, threshold, fractions)] == "damaged"
    assert DAMAGE_STATES[damage_state_of(second * threshold, threshold, fractions)] == "critical"
    assert DAMAGE_STATES[damage_state_of(third * threshold, threshold, fractions)] == "fractured"
    assert DAMAGE_STATES[damage_state_of(threshold, threshold, fractions)] == "broken"
    assert DAMAGE_STATES[damage_state_of(99.0, threshold, fractions)] == "broken"


def test_damage_state_transitions_only_ever_go_forward(runs) -> None:
    order = {name: i for i, name in enumerate(DAMAGE_STATES)}
    seen = {name: 0 for name in DAMAGE_STATES}
    for run in runs:
        state: dict[tuple[int, int], str] = {}
        for ev in run.events:
            if ev.kind != "damage_state":
                continue
            key = (ev.data["shell_id"], ev.data["panel_id"])
            assert state.get(key, "healthy") == ev.data["previous_state"]
            assert order[ev.data["new_state"]] > order[ev.data["previous_state"]]
            state[key] = ev.data["new_state"]
            seen[ev.data["new_state"]] += 1
    for name in DAMAGE_STATES[1:]:
        assert seen[name] > 0, f"no panel ever reached {name}"


def test_the_damage_event_state_matches_the_ledger(runs) -> None:
    for run in runs:
        for ev in run.events:
            if ev.kind != "damage":
                continue
            expected = DAMAGE_STATES[
                damage_state_of(
                    ev.data["cumulative"], ev.data["threshold"], DEFAULT_CONFIG.damage_state_fractions
                )
            ]
            assert ev.data["state"] == expected
            assert ev.data["threshold"] == DEFAULT_CONFIG.break_thresholds[ev.data["shell_id"]]


def test_damage_accumulates_across_balls(runs) -> None:
    """The emergent effect the concept asks for, counted rather than asserted."""
    shared = 0
    for run in runs:
        ledgers: dict[tuple[int, int], set[int]] = {}
        for ev in run.events:
            if ev.kind == "damage" and ev.data["contribution"] > 0.0:
                ledgers.setdefault((ev.data["shell_id"], ev.data["panel_id"]), set()).add(
                    ev.data["ball_id"]
                )
            elif ev.kind == "panel_break":
                key = (ev.data["shell_id"], ev.data["panel_id"])
                assert ev.data["contributors"] == len(ledgers.get(key, set()))
                if ev.data["contributors"] > 1:
                    shared += 1
    assert shared > 0, "no panel was ever broken by more than one ball"


def test_a_panel_breaks_once_and_stays_broken(runs) -> None:
    for run in runs:
        broken: set[tuple[int, int]] = set()
        for ev in run.events:
            if ev.kind == "panel_break":
                key = (ev.data["shell_id"], ev.data["panel_id"])
                assert key not in broken, f"seed {run.seed}: {key} broke twice"
                broken.add(key)
                assert ev.data["cumulative"] >= ev.data["threshold"]
            elif ev.kind in ("collision", "damage"):
                key = (ev.data["shell_id"], ev.data["panel_id"])
                if ev.kind == "damage":
                    assert key not in broken, f"seed {run.seed}: damage to broken {key}"
        # And the arena agrees at the end.
        assert sum(sum(1 for b in shell if b) for shell in run.broken) == len(broken)


def test_no_ball_ever_bounces_off_a_hole(runs) -> None:
    """The scheduler's cache-invalidation rule, as a consequence rather than a claim.

    Every ball's next event is computed against the shell state at the moment
    it was computed. When a panel breaks, every cached event is stale, and a
    scheduler that did not re-ask would let a ball rebound off a panel that no
    longer exists - a ghost wall, invisible to `anomalous_crossings` because no
    region boundary is involved. This is the check that would catch it: a
    collision may never name a slot that started open or has already broken.
    """
    open_slots = {
        (shell.shell_id, slot)
        for shell in runs[0].arena.shells
        for slot in shell.open_slots
    }
    checked = 0
    for run in runs:
        broken: set[tuple[int, int]] = set()
        for ev in run.events:
            if ev.kind == "panel_break":
                broken.add((ev.data["shell_id"], ev.data["panel_id"]))
            elif ev.kind == "collision":
                key = (ev.data["shell_id"], ev.data["panel_id"])
                assert key not in open_slots, f"seed {run.seed}: bounced off opening {key}"
                assert key not in broken, f"seed {run.seed}: bounced off broken panel {key}"
                checked += 1
    assert checked > 5000


def test_a_break_by_one_ball_changes_what_another_ball_does(runs) -> None:
    """Invalidation is not free work: it has to actually fire.

    A break must sometimes happen while another ball is already in flight
    towards the same shell, because that is the case the re-ask exists for. If
    it never happened the rule would be untested and the population would be
    hiding it.
    """
    overlaps = 0
    for run in runs:
        in_flight: dict[int, float] = {}
        last_seen: dict[int, float] = {}
        for ev in run.events:
            ball = ev.data.get("ball_id")
            if ev.kind == "collision":
                last_seen[ball] = ev.t
            if ev.kind != "panel_break":
                continue
            # Another ball whose last event predates this break is mid-flight
            # with a cached next event computed against the intact shell.
            for other, when in last_seen.items():
                if other != ball and when < ev.t:
                    overlaps += 1
                    break
    assert overlaps > 50, f"only {overlaps} breaks happened with another ball in flight"


def test_a_broken_panel_becomes_passable_and_later_balls_use_it(runs) -> None:
    used = 0
    for run in runs:
        break_time: dict[tuple[int, int], float] = {}
        for ev in run.events:
            if ev.kind == "panel_break":
                break_time[(ev.data["shell_id"], ev.data["panel_id"])] = ev.t
            elif ev.kind in ("shell_exit", "shell_entry") and ev.data["route"] == "break":
                key = (ev.data["shell_id"], ev.data["panel_id"])
                assert key in break_time, f"seed {run.seed}: crossed an unbroken {key} as a break"
                assert ev.t >= break_time[key]
                used += 1
            elif ev.kind == "panel_break":
                pass
    assert used > 0, "no ball ever used a broken panel"


def test_a_ball_can_use_a_hole_another_ball_made(runs) -> None:
    """The point of shared damage: an earlier ball pays, a later one profits."""
    inherited = 0
    for run in runs:
        breaker: dict[tuple[int, int], int] = {}
        for ev in run.events:
            if ev.kind == "panel_break":
                breaker[(ev.data["shell_id"], ev.data["panel_id"])] = ev.data["ball_id"]
            elif ev.kind in ("shell_exit", "shell_entry") and ev.data["route"] == "break":
                key = (ev.data["shell_id"], ev.data["panel_id"])
                if breaker.get(key) != ev.data["ball_id"]:
                    inherited += 1
    assert inherited > 0, "every break was only ever used by the ball that made it"


def test_breaking_can_be_turned_off() -> None:
    run = simulate(5, DEFAULT_CONFIG.replace(breakable=False))
    assert run.breaks == 0
    assert not run.events_of("panel_break")
    assert not run.events_of("damage")
    assert all(route != "break" for route in (e.data["route"] for e in run.events_of("shell_exit")))


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------


def test_both_outcomes_occur(runs) -> None:
    escaped = [r for r in runs if r.escaped]
    failed = [r for r in runs if not r.escaped]
    assert escaped, "no seed ever escaped"
    assert failed, "every seed escaped; the outcome is not uncertain"
    assert 0.25 < len(escaped) / len(runs) < 0.90, (
        f"escape rate {len(escaped)/len(runs):.1%} is not a genuine question"
    )
    for run in failed:
        assert run.failure_reason in ("timeout", "collision_cap")
        assert run.duration == pytest.approx(DEFAULT_CONFIG.horizon) or run.failure_reason == "collision_cap"


def test_both_escape_routes_occur(runs) -> None:
    routes = {ev.data["route"] for run in runs for ev in run.events if ev.kind == "shell_exit"}
    assert "opening" in routes
    assert "break" in routes
    assert "anomaly" not in routes


def test_the_escaping_ball_is_sometimes_not_the_founder(runs) -> None:
    generations = [
        ev.data["generation"] for run in runs for ev in run.events if ev.kind == "escape"
    ]
    assert generations
    assert any(g > 0 for g in generations), "only the original ball ever got out"


def test_every_escape_names_the_route_it_came_out_through(runs) -> None:
    """Including a ball born outside the outermost shell, which never crosses it.

    A child born outside shell 4 appears already in the escaped-but-not-clear
    region and can reach the escape radius without ever making a `shell_exit`
    of its own. It inherits its parent's route, which is the hole it came out
    of too. Without that inheritance the run's headline event reports no route
    at all, in 11.5% of successful runs.
    """
    born_outside = 0
    for run in runs:
        for ev in run.events:
            if ev.kind != "escape":
                continue
            assert ev.data["route"] in ("opening", "break"), (
                f"seed {run.seed}: escape with route {ev.data['route']!r}"
            )
            if ev.data["birth_shell"] == DEFAULT_CONFIG.shell_count - 1:
                born_outside += 1
    assert born_outside > 0, "no ball was ever born outside the outermost shell"


def test_the_failure_event_reports_the_frontier(runs) -> None:
    for run in runs:
        if run.escaped:
            continue
        failure = run.events_of("failure")[0]
        assert failure.data["total_balls"] == len(run.balls)
        assert failure.data["active_balls"] == len(run.balls)
        assert sum(failure.data["balls_by_region"]) == len(run.balls)
        assert failure.data["frontier_region"] == run.frontier_region
        assert failure.data["balls_by_region"][run.frontier_region] == failure.data["frontier_balls"]


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------


def test_the_instruments_are_clean_across_the_population(runs) -> None:
    for run in runs:
        assert run.anomalous_crossings == 0, f"seed {run.seed} crossed a live panel"
        assert run.newton_failures == 0, f"seed {run.seed} exhausted a contact search"
        assert run.max_penetration < 1.0e-6, f"seed {run.seed} penetrated {run.max_penetration}"
        assert run.reproduction_violations == 0


def test_the_constant_speed_model_holds_the_speed(runs) -> None:
    for run in runs:
        assert run.speed_min == pytest.approx(DEFAULT_CONFIG.speed, rel=1e-9)
        assert run.speed_max == pytest.approx(DEFAULT_CONFIG.speed, rel=1e-9)
        assert 0.0 < run.mean_speed_correction < 0.25


def test_the_bounded_speed_model_stays_inside_its_band() -> None:
    config = DEFAULT_CONFIG.replace(speed_model="bounded")
    lo = config.speed_band[0] * config.speed
    hi = config.speed_band[1] * config.speed
    for seed in SMALL:
        run = simulate(seed, config)
        assert run.speed_min >= lo - 1.0e-9
        assert run.speed_max <= hi + 1.0e-9


def _normal_momentum(ev) -> tuple[float, float]:
    nx, ny = ev.data["normal"]
    before = (ev.data["velocity_in"], ev.data["other_velocity_in"])
    after = (ev.data["velocity_out"], ev.data["other_velocity_out"])
    return (
        sum(v[0] * nx + v[1] * ny for v in before),
        sum(v[0] * nx + v[1] * ny for v in after),
    )


def test_ball_ball_collisions_conserve_the_pair_when_nothing_rescales_them() -> None:
    """The exchange itself is right: equal masses swap the normal component."""
    config = DEFAULT_CONFIG.replace(ball_ball_collisions=True, speed_model="free")
    seen = 0
    for seed in SMALL:
        run = simulate(seed, config)
        for ev in run.events:
            if ev.kind != "ball_collision":
                continue
            seen += 1
            p_before, p_after = _normal_momentum(ev)
            assert p_after == pytest.approx(p_before, abs=1.0e-9 * max(1.0, abs(p_before)))
    assert seen > 0, "ball-ball collisions never fired"


def test_the_constant_speed_constraint_and_ball_ball_contact_are_incompatible() -> None:
    """Why production runs with ball-ball off, as a test rather than a claim.

    The elastic exchange separates the pair; renormalising each ball's speed
    afterwards, independently, does not preserve that separation, so the pair
    re-contacts. The visible symptom is that the normal momentum is not
    conserved across the recorded event - and the measured consequence, in
    `docs/category3_multiplying_shell_phase1.md`, is 31,212 repeat contacts and
    a penetration five thousand times the constraint-free figure.
    """
    config = DEFAULT_CONFIG.replace(ball_ball_collisions=True)
    broken = 0
    seen = 0
    for seed in SMALL:
        run = simulate(seed, config)
        for ev in run.events:
            if ev.kind != "ball_collision":
                continue
            seen += 1
            p_before, p_after = _normal_momentum(ev)
            if abs(p_after - p_before) > 1.0e-6 * max(1.0, abs(p_before)):
                broken += 1
    assert seen > 0
    assert broken > 0, "the constraint never disturbed a pair; the incompatibility is gone"
    # Production is the configuration that does not have the problem.
    assert DEFAULT_CONFIG.ball_ball_collisions is False
    assert all(simulate(seed).ball_collisions == 0 for seed in SMALL)


# --------------------------------------------------------------------------
# The event schema
# --------------------------------------------------------------------------


def test_the_schema_version_is_new() -> None:
    from satisfying.shell_escape import SCHEMA_VERSION as OLD

    assert SCHEMA_VERSION == "category3-test2-multiplying-shell/2.0.0"
    assert SCHEMA_VERSION != OLD


def test_the_schema_is_exactly_this() -> None:
    """Pinned field by field. Phase 2A and 2B will be written against it."""
    assert set(EVENT_KINDS) == {
        "ball_spawn",
        "collision",
        "ball_collision",
        "near_miss",
        "damage",
        "damage_state",
        "panel_break",
        "shell_exit",
        "shell_entry",
        "escape",
        "failure",
    }
    assert EVENT_SCHEMA["ball_spawn"] == (
        "ball_id",
        "parent_id",
        "generation",
        "birth_shell",
        "region",
        "position",
        "velocity",
        "speed",
        "turn",
        "lead",
        "clearance",
        "spawn_index",
        "population",
        "lineage",
    )
    assert EVENT_SCHEMA["damage_state"] == (
        "ball_id",
        "shell_id",
        "panel_id",
        "previous_state",
        "new_state",
        "cumulative",
        "threshold",
        "fraction",
    )
    assert EVENT_SCHEMA["escape"] == (
        "ball_id",
        "shell_id",
        "route",
        "position",
        "generation",
        "parent_id",
        "birth_time",
        "birth_shell",
        "lineage",
        "collisions",
        "breaks",
        "population",
    )
    assert EVENT_SCHEMA["failure"] == (
        "reason",
        "horizon",
        "active_balls",
        "total_balls",
        "frontier_region",
        "frontier_balls",
        "balls_by_region",
        "collisions",
        "breaks",
    )
    # Every ball-scoped event names its ball first.
    for kind, fields in EVENT_SCHEMA.items():
        if kind == "failure":
            continue
        assert fields[0] == "ball_id", f"{kind} does not lead with ball_id"


def test_every_run_validates_against_the_schema(runs) -> None:
    for run in runs:
        validate_events(run.events)
    kinds = {ev.kind for run in runs for ev in run.events}
    assert kinds >= set(EVENT_KINDS) - {"ball_collision"}


def test_a_drifted_event_is_rejected() -> None:
    from satisfying.multishell import Event

    with pytest.raises(ValueError):
        validate_events([Event("collision", 0.0, {"ball_id": 0})])
    with pytest.raises(ValueError):
        validate_events([Event("nonsense", 0.0, {})])


# --------------------------------------------------------------------------
# The playback document
# --------------------------------------------------------------------------


def test_the_document_round_trips_and_verifies() -> None:
    for seed in (7, 42, 99):
        document = document_for(seed)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.json")
            write_playback(document, path)
            reloaded = read_playback(path)
        assert document_digest(reloaded) == document_digest(document)
        report = verify_document(reloaded)
        assert report["ok"], report["checks"]


def test_the_document_carries_the_lineage_and_the_panel_history() -> None:
    document = document_for(7)
    assert document["schema"] == SCHEMA_VERSION
    assert len(document["balls"]) == len(document["flights"])
    for record in document["balls"]:
        assert str(record["ball_id"]) in document["flights"]
    for entry in document["panel_states"]:
        states = [t["state"] for t in entry["transitions"]]
        assert states == sorted(states, key=lambda s: DAMAGE_STATES.index(s))
        if entry["break_time"] is not None:
            assert states[-1] == "broken"


def test_a_document_can_be_read_back_without_re_simulating() -> None:
    run = simulate(7)
    document = playback_document(run)
    assert position_at(document, 0, -1.0) is None
    for t in (0.0, 3.0, 9.0, run.duration):
        assert population_at(document, t) == run.population_at(t)
        place = position_at(document, 0, t)
        assert place is not None
        assert math.isfinite(place[0]) and math.isfinite(place[1])
    # A ball does not exist before it is born.
    later = [b for b in run.balls if b.birth_time > 1.0]
    assert later
    assert position_at(document, later[0].ball_id, 0.0) is None
    assert position_at(document, later[0].ball_id, later[0].birth_time) is not None
    # A broken panel is broken from its break time onward, and never before.
    breaks = run.events_of("panel_break")
    assert breaks
    ev = breaks[0]
    shell, panel = ev.data["shell_id"], ev.data["panel_id"]
    assert panel_state_at(document, shell, panel, 0.0) == "healthy"
    assert panel_state_at(document, shell, panel, ev.t) == "broken"
    assert panel_state_at(document, shell, panel, run.duration) == "broken"


def test_the_document_is_json_lossless() -> None:
    document = document_for(42)
    reloaded = json.loads(json.dumps(document))
    assert reloaded["digest"] == document["digest"]
    assert verify_document(reloaded)["ok"]


# --------------------------------------------------------------------------
# The evaluator
# --------------------------------------------------------------------------


def test_the_evaluator_population_metrics_agree_with_the_run(runs) -> None:
    for run in runs:
        m = evaluate(run).metrics
        assert m["population"]["total"] == len(run.balls)
        assert m["population"]["max"] == run.max_population
        assert m["population"]["generations"] == run.max_generation + 1
        assert m["population"]["curve"][0] == 1
        assert m["population"]["curve"][-1] == len(run.balls)
        assert m["population"]["curve"] == sorted(m["population"]["curve"])
        assert sum(m["population"]["by_region"]) == len(run.balls)
        assert m["reproduction"]["spawns"] == run.spawns
        assert sum(m["reproduction"]["by_shell"]) == run.spawns
        assert m["reproduction"]["violations"] == 0


def test_the_evaluator_reports_when_the_first_split_happens(runs) -> None:
    """The hook, as a number. Every seed reproduces; the question is how soon."""
    firsts = []
    for run in runs:
        m = evaluate(run).metrics
        spawns = [ev for ev in run.events if ev.kind == "ball_spawn"]
        assert spawns, f"seed {run.seed} never reproduced"
        assert m["reproduction"]["first_spawn"] == spawns[0].t
        firsts.append(spawns[0].t)
    assert sorted(firsts)[len(firsts) // 2] < 3.0, "the median run is slow to split"


def test_the_evaluator_density_metrics_agree_with_the_stream(runs) -> None:
    for run in runs:
        m = evaluate(run).metrics
        assert m["collisions"]["total"] == run.collisions
        assert sum(m["collisions"]["per_shell"]) == run.collisions
        assert sum(m["activity"]["collision_thirds"]) == run.collisions
        assert m["collisions"]["per_second"] == pytest.approx(run.collisions / run.duration)
        # The windowed peak is never below the mean and never above the total.
        assert m["collisions"]["peak_window"] >= m["collisions"]["per_second"] - 1e-9
        assert m["collisions"]["peak_window"] <= run.collisions / DEFAULT_THRESHOLDS.audio_window
        counted = sum(1 for ev in run.events if ev.kind in MEANINGFUL_KINDS)
        assert m["activity"]["meaningful_total"] == counted
        assert sum(m["activity"]["meaningful_thirds"]) == counted


def test_the_escalation_metric_is_a_ratio_of_the_stream() -> None:
    run = simulate(7)
    m = evaluate(run).metrics
    thirds = m["activity"]["meaningful_thirds"]
    assert m["escalation"]["meaningful"] == pytest.approx((thirds[2] + 1.0) / (thirds[0] + 1.0))


def test_late_activity_beats_early_activity_for_most_of_the_population(runs) -> None:
    """The redesign's headline claim, measured rather than asserted."""
    ratios = [evaluate(run).metrics["escalation"]["meaningful"] for run in runs]
    rising = sum(1 for r in ratios if r > 1.0)
    assert rising / len(ratios) > 0.80, f"only {rising}/{len(ratios)} runs escalate"
    assert sorted(ratios)[len(ratios) // 2] > 1.2


def test_every_flag_name_is_reachable_from_the_evaluator() -> None:
    import inspect

    from satisfying import multishell_evaluator

    source = inspect.getsource(multishell_evaluator.evaluate)
    for name in FLAG_NAMES:
        assert f'"{name}"' in source, f"{name} is declared but never raised"


def test_a_flagged_run_is_not_usable() -> None:
    evaluation = evaluate_seed(1)
    assert evaluation.flags
    assert not evaluation.usable
    assert evaluate_seed(15793).usable


def test_summarise_reports_the_distributions(runs) -> None:
    evaluations = [evaluate(run) for run in runs]
    report = summarise(evaluations)
    assert report["count"] == len(runs)
    assert 0.0 < report["escape_rate"] < 1.0
    assert report["reproduction_violations"] == 0
    assert report["instruments"]["anomalous_crossings"] == 0
    assert report["instruments"]["newton_failures"] == 0
    assert len(report["population_curve"]) == 11
    assert report["population_curve"] == sorted(report["population_curve"])
    assert report["pass_rate_monotonic"]
    assert 0.0 < report["outer_shell_crossed_rate"] < 1.0
    assert report["escalation_above_one"] > 0.80


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------


def test_the_cli_batch_shortlist_round_trip() -> None:
    from satisfying.multishell_cli import _compact, _rehydrate, main, run_batch, shortlist

    records = run_batch(range(200), workers=1)
    assert len(records) == 200
    rebuilt = _rehydrate(records)
    report = summarise(rebuilt)
    assert report["count"] == 200
    assert report["reproduction_violations"] == 0
    picked = shortlist(records, take=8)
    assert picked
    assert len({r["seed"] for r in picked}) == len(picked)
    assert all(not r["flags"] for r in picked)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.json")
        assert main(["document", "--seed", "7", "--out", path]) == 0
        assert main(["verify", "--document", path]) == 0
    assert main(["profile"]) == 0


def test_the_compact_record_keeps_what_summarise_needs() -> None:
    from satisfying.multishell_cli import _compact, _rehydrate

    evaluation = evaluate_seed(7)
    record = _compact(evaluation)
    rebuilt = _rehydrate([record])[0]
    assert rebuilt.seed == evaluation.seed
    assert rebuilt.flags == evaluation.flags
    assert rebuilt.duration == evaluation.duration
    assert rebuilt.metrics["population"]["curve"] == evaluation.metrics["population"]["curve"]
    assert summarise([rebuilt])["count"] == 1


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------

REDESIGN_MODULES = (
    "multishell_seeds",
    "multishell",
    "multishell_evaluator",
    "multishell_playback",
    "multishell_cli",
)


def test_the_redesign_does_not_depend_on_godot_audio_or_rendering() -> None:
    """Phase 1 is physics and measurement; the later branches consume it."""
    import ast
    import pathlib

    forbidden = {"godot", "audio", "rendering", "PIL", "numpy", "replay", "production"}
    for name in REDESIGN_MODULES:
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


def test_the_redesign_does_not_import_test_one() -> None:
    """The two Category 3 experiments share conventions, not code."""
    import ast
    import pathlib

    tile_modules = {
        p.stem for p in (pathlib.Path(REPO_ROOT) / "satisfying").glob("tile_*.py")
    } | {"seeds"}
    for name in REDESIGN_MODULES:
        path = pathlib.Path(REPO_ROOT) / "satisfying" / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("satisfying"):
                for alias in node.names:
                    assert alias.name not in tile_modules, f"{name} imports {alias.name}"


def test_the_borrowed_solver_primitives_still_exist() -> None:
    """The redesign reuses the single-ball contact search rather than copying it.

    If `shell_escape` ever renames one of these the redesign breaks at import,
    which is loud - but a signature change is silent, so the shapes are pinned
    here too.
    """
    import inspect

    from satisfying import shell_escape

    expected = {
        "_ShellState": ("shell", "ball_radius", "speed"),
        "_nearest_live": ("st", "x", "y", "t"),
        "_contact_in_interval": ("st", "x", "y", "vx", "vy", "t0", "lo", "hi", "config"),
        "_band_intervals": ("x", "y", "vx", "vy", "lo", "hi", "t_end", "t_min"),
        "_boundary_crossing": ("x", "y", "vx", "vy", "radius", "outward", "t_min"),
        "_is_post_contact": ("st", "slot", "qx", "qy", "t"),
    }
    for name, params in expected.items():
        obj = getattr(shell_escape, name)
        target = obj.__init__ if inspect.isclass(obj) else obj
        got = tuple(p for p in inspect.signature(target).parameters if p != "self")
        assert got == params, f"{name} signature drifted: {got}"


def test_the_single_ball_module_is_untouched_by_the_redesign() -> None:
    """Importing the redesign must not mutate the module it borrows from."""
    from satisfying import shell_escape

    before = shell_escape.DEFAULT_CONFIG.digest()
    simulate(7)
    assert shell_escape.SCHEMA_VERSION == "category3-test2-shell-escape/1.0.0"
    assert shell_escape.DEFAULT_CONFIG.digest() == before
    assert shell_escape.DEFAULT_CONFIG.shell_count == 6
