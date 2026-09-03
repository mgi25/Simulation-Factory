"""Phase 5B2 tests: production curation and the batch manifest."""

from __future__ import annotations

import dataclasses
import json
import os

import pytest

from engine.arena_layout import LAYOUT_PROCEDURAL
from evaluation.battle_metrics import BattleMetrics, evaluate_seed
from evaluation.battle_score import ScoreBreakdown, score_battle
from evaluation.candidate import Candidate
from evaluation.candidate_curation import (
    DEFAULT_MIN_SCORE,
    MOTION_CLASSES,
    REJECT_DRAW,
    REJECT_DURATION,
    REJECT_ENVIRONMENT,
    REJECT_INVALID,
    REJECT_LEAKED,
    REJECT_MATCHUP,
    REJECT_MIRROR,
    REJECT_POWER,
    REJECT_SCORE,
    REJECT_SIMILAR,
    REJECT_SPEED,
    REJECT_TIMEOUT,
    CurationConfig,
    count_near_duplicates,
    curate,
    is_mirror,
    is_near_duplicate,
    matchup_key,
    motion_class,
    similarity_signals,
    summarise,
    winner_power,
)
from tools.build_batch import (
    MANIFEST_VERSION,
    REVIEW_PENDING,
    VerificationError,
    batch_id_for,
    build_manifest,
    verify_and_export,
)
from tools.candidate_search import search

SEED = 20000

# Evaluating a pool means simulating every battle in it, so the handful of
# tests that need a real one share these rather than each paying for its own.
POOL_SEEDS = 400
SMALL_POOL_SEEDS = 60


@pytest.fixture(scope="module")
def pool() -> list[Candidate]:
    return search([(seed, LAYOUT_PROCEDURAL) for seed in range(SEED, SEED + POOL_SEEDS)], 1)


@pytest.fixture(scope="module")
def small_pool() -> list[Candidate]:
    return search(
        [(seed, LAYOUT_PROCEDURAL) for seed in range(SEED, SEED + SMALL_POOL_SEEDS)], 1
    )


def metrics(**overrides) -> BattleMetrics:
    base = dict(
        seed=1,
        arena_mode=LAYOUT_PROCEDURAL,
        layout_id="procedural-1",
        powers=("rush", "titan"),
        obstacles=2,
        kinetic_obstacles=1,
        winner_id=0,
        is_draw=False,
        is_timeout=False,
        duration=17.0,
        damaging_hits=8,
        hits_by_subtype=(("impact", 8),),
        power_activations=5,
        activating_fighters=2,
        damaging_fighters=2,
        first_hit_time=2.0,
        longest_idle_gap=5.0,
        lead_changes=3,
        close_fraction=0.7,
        winner_comeback=25.0,
        final_health_gap=20.0,
        winner_health=20.0,
        max_fighter_speed=1800.0,
        obstacle_contacts=25,
        distinct_obstacles_contacted=2,
        kinetic_obstacle_contacts=8,
        layout_shape=(("bumper", 1), ("rotor", 1)),
        state_valid=True,
        entities_leaked=False,
    )
    return BattleMetrics(**{**base, **overrides})


def graded(total: float) -> ScoreBreakdown:
    """A score of an exact value, so a test can place a candidate precisely."""
    return ScoreBreakdown(
        total=total, pacing=total * 0.2, suspense=total * 0.25, action=total * 0.2,
        variety=total * 0.1, arena=total * 0.1, payoff=total * 0.15,
        penalty=0.0, penalties=(),
    )


def candidate(total: float = 90.0, **overrides) -> Candidate:
    return Candidate(metrics=metrics(**overrides), score=graded(total))


def config(**overrides) -> CurationConfig:
    return dataclasses.replace(CurationConfig(size=10, min_score=80.0), **overrides)


# --- matchup, mirror and environment identity -------------------------------


def test_a_matchup_has_no_sides() -> None:
    assert matchup_key(("rush", "titan")) == matchup_key(("titan", "rush"))
    assert matchup_key(("echo", "echo")) == ("echo", "echo")
    assert matchup_key(("rush", "titan")) != matchup_key(("rush", "pulse"))


def test_the_battle_itself_keeps_its_sides() -> None:
    """Only the diversity bookkeeping is unordered; the battle is not."""
    red_first = candidate(powers=("rush", "titan"), winner_id=0)
    blue_first = candidate(powers=("titan", "rush"), winner_id=0)
    assert matchup_key(red_first.metrics.powers) == matchup_key(blue_first.metrics.powers)
    assert red_first.metrics.powers != blue_first.metrics.powers
    assert winner_power(red_first) == "rush"
    assert winner_power(blue_first) == "titan"


def test_mirrors_are_recognised() -> None:
    assert is_mirror(("echo", "echo"))
    assert not is_mirror(("echo", "orbit"))


def test_arenas_are_classed_by_how_much_of_them_moves() -> None:
    assert motion_class(0) == MOTION_CLASSES[0]
    assert motion_class(1) == MOTION_CLASSES[1]
    assert motion_class(2) == MOTION_CLASSES[2]
    assert motion_class(5) == MOTION_CLASSES[2]


def test_an_arena_shape_ignores_where_things_are() -> None:
    """Two layouts of the same make-up compare equal wherever the pieces sit."""
    here = evaluate_seed(SEED, LAYOUT_PROCEDURAL).layout_shape
    assert here == tuple(sorted(here))
    assert all(isinstance(kind, str) and isinstance(n, int) for kind, n in here)
    # No coordinates anywhere in it.
    assert all(isinstance(value, (str, int)) for pair in here for value in pair)


# --- hard production filters ------------------------------------------------


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"is_timeout": True}, REJECT_TIMEOUT),
        ({"is_draw": True, "winner_id": None}, REJECT_DRAW),
        ({"duration": 3.0}, REJECT_DURATION),
        ({"max_fighter_speed": 9000.0}, REJECT_SPEED),
        ({"state_valid": False}, REJECT_INVALID),
        ({"entities_leaked": True}, REJECT_LEAKED),
    ],
)
def test_unpublishable_battles_are_rejected_however_well_they_score(
    overrides, reason
) -> None:
    result = curate([candidate(total=99.0, **overrides)], config())
    assert result.selected == []
    assert result.rejected[reason] == 1


def test_the_quality_floor_is_hard() -> None:
    below = candidate(total=79.9, seed=1)
    above = candidate(total=80.1, seed=2, powers=("echo", "orbit"))
    result = curate([below, above], config(min_score=80.0))
    assert [c.metrics.seed for c in result.selected] == [2]
    assert result.rejected[REJECT_SCORE] == 1


def test_a_short_batch_is_reported_not_quietly_filled() -> None:
    """Running out of good candidates is an answer, not a reason to relax."""
    pool = [candidate(total=70.0, seed=n) for n in range(50)]
    result = curate(pool, config(size=10, min_score=80.0))
    assert result.selected == []
    assert result.shortfall(10) == 10
    reason = result.reason_for_shortfall(10)
    assert reason and "quality floor" in reason
    # The floor is never moved to make the numbers work.
    assert result.rejected[REJECT_SCORE] == 50


def test_a_full_batch_reports_no_shortfall() -> None:
    pool = [
        candidate(total=95.0 - n, seed=n, powers=powers, kinetic_obstacles=n % 3)
        for n, powers in enumerate(
            [("rush", "titan"), ("echo", "orbit"), ("pulse", "rush"),
             ("echo", "titan"), ("orbit", "pulse")]
        )
    ]
    result = curate(pool, config(size=5))
    assert result.size == 5
    assert result.reason_for_shortfall(5) is None


# --- diversity caps ---------------------------------------------------------


def test_one_matchup_cannot_fill_the_batch() -> None:
    pool = [
        candidate(total=95.0 - index * 0.1, seed=index, powers=("rush", "titan"),
                  duration=8.0 + index * 4.0, damaging_hits=4 + index * 3,
                  lead_changes=index, layout_shape=(("bumper", index % 3 + 1),))
        for index in range(10)
    ]
    result = curate(pool, config(size=10, matchup_share=0.20))
    assert result.size == 2
    assert result.rejected[REJECT_MATCHUP] > 0


def test_no_single_power_can_dominate_a_batch() -> None:
    """Every candidate uses echo, so the batch fills only to the power cap."""
    pool = [
        candidate(total=95.0 - index * 0.1, seed=index, powers=("echo", "echo"),
                  duration=8.0 + index * 3.0, damaging_hits=4 + index * 3,
                  lead_changes=index)
        for index in range(20)
    ]
    result = curate(pool, config(size=10, matchup_share=1.0, mirror_share=1.0,
                                 power_share=0.30))
    # 10 battles would be 20 echo appearances; the cap is 30% of that.
    assert result.size * 2 <= config().cap(0.30, of=20) + 2
    assert result.rejected[REJECT_POWER] > 0


def fill_appearances(power: str, count: int) -> list[Candidate]:
    """Battles that between them use `power` exactly `count` times.

    Each one is a cross matchup against a rotating cast, and every one
    differs in length, hits, lead changes and arena, so nothing but the power
    cap can turn any of them away.
    """
    others = ["orbit", "pulse", "rush", "titan", "echo"]
    return [
        candidate(
            total=99.0 - index * 0.1,
            seed=900 + index,
            powers=(power, next(o for o in others[index % len(others):] + others
                                if o != power)),
            duration=8.0 + index * 4.0,
            damaging_hits=4 + index * 4,
            lead_changes=index,
            layout_shape=(("bumper", index % 3 + 1),),
            kinetic_obstacles=index % 3,
        )
        for index in range(count)
    ]


def power_cap_config() -> CurationConfig:
    """Only the power cap binds: every other quota is opened right up."""
    return config(
        size=10,
        power_share=0.30,      # 30% of 20 appearance slots, so a cap of six
        matchup_share=1.0,
        mirror_share=1.0,
        motion_share=1.0,
    )


def test_a_cross_matchup_may_land_exactly_on_the_power_cap() -> None:
    settings = power_cap_config()
    assert settings.power_cap == 6
    pool = fill_appearances("echo", 5) + [
        candidate(total=90.0, seed=1, powers=("echo", "titan"), duration=30.0,
                  damaging_hits=40, lead_changes=9, layout_shape=(("gate", 2),))
    ]
    result = curate(pool, settings)
    assert result.rejected[REJECT_POWER] == 0
    assert 1 in [c.metrics.seed for c in result.selected]
    assert summarise(result.selected)["powers"]["echo"] == settings.power_cap


def test_a_cross_matchup_that_would_pass_the_power_cap_is_rejected() -> None:
    settings = power_cap_config()
    pool = fill_appearances("echo", 6) + [
        candidate(total=90.0, seed=1, powers=("echo", "titan"), duration=30.0,
                  damaging_hits=40, lead_changes=9, layout_shape=(("gate", 2),))
    ]
    result = curate(pool, settings)
    assert result.rejected[REJECT_POWER] == 1
    assert 1 not in [c.metrics.seed for c in result.selected]
    assert summarise(result.selected)["powers"]["echo"] == settings.power_cap


def test_a_mirror_may_land_exactly_on_the_power_cap() -> None:
    """A mirror brings two appearances, and two is exactly what is left."""
    settings = power_cap_config()
    pool = fill_appearances("echo", 4) + [
        candidate(total=90.0, seed=1, powers=("echo", "echo"), duration=30.0,
                  damaging_hits=40, lead_changes=9, layout_shape=(("gate", 2),))
    ]
    result = curate(pool, settings)
    assert result.rejected[REJECT_POWER] == 0
    assert 1 in [c.metrics.seed for c in result.selected]
    assert summarise(result.selected)["powers"]["echo"] == settings.power_cap


def test_a_mirror_that_would_overshoot_the_power_cap_by_one_is_rejected() -> None:
    """The case a running-total check misses: five plus two is seven, not six."""
    settings = power_cap_config()
    pool = fill_appearances("echo", 5) + [
        candidate(total=90.0, seed=1, powers=("echo", "echo"), duration=30.0,
                  damaging_hits=40, lead_changes=9, layout_shape=(("gate", 2),))
    ]
    result = curate(pool, settings)
    assert result.rejected[REJECT_POWER] == 1
    assert 1 not in [c.metrics.seed for c in result.selected]
    assert summarise(result.selected)["powers"]["echo"] <= settings.power_cap


def test_no_batch_ever_exceeds_the_power_cap(pool: list[Candidate]) -> None:
    """The invariant itself, over a real pool rather than a built one."""
    for share in (0.20, 0.30, 0.40):
        settings = config(size=10, power_share=share, matchup_share=1.0,
                          mirror_share=1.0, motion_share=1.0)
        counts = summarise(curate(pool, settings).selected)["powers"]
        assert all(count <= settings.power_cap for count in counts.values())


def test_mirrors_are_allowed_but_capped() -> None:
    mirrors = [
        candidate(total=95.0 - index, seed=index, powers=(power, power),
                  duration=10.0 + index * 3.0, damaging_hits=5 + index * 3,
                  lead_changes=index)
        for index, power in enumerate(["echo", "orbit", "pulse", "rush", "titan"])
    ]
    result = curate(mirrors, config(size=10, mirror_share=0.20, matchup_share=1.0))
    assert 0 < result.size <= 2
    assert result.rejected[REJECT_MIRROR] > 0


def test_one_kind_of_arena_cannot_fill_the_batch() -> None:
    pool = [
        candidate(total=95.0 - index * 0.1, seed=index, kinetic_obstacles=0,
                  powers=("rush", "titan") if index % 2 else ("echo", "orbit"),
                  duration=8.0 + index * 3.0, damaging_hits=4 + index * 3,
                  lead_changes=index)
        for index in range(12)
    ]
    result = curate(pool, config(size=10, motion_share=0.30, matchup_share=1.0))
    assert result.size == 3
    assert result.rejected[REJECT_ENVIRONMENT] > 0


# --- near-duplicate detection -----------------------------------------------


def test_two_battles_of_the_same_shape_are_near_duplicates() -> None:
    first = candidate(total=90.0, seed=1)
    second = candidate(total=89.5, seed=2)
    assert is_near_duplicate(first, second)
    assert len(similarity_signals(first, second)) == 6


def test_different_matchups_are_never_near_duplicates() -> None:
    """Different powers put different things on screen, whatever the numbers."""
    first = candidate(total=90.0, seed=1, powers=("rush", "titan"))
    second = candidate(total=90.0, seed=2, powers=("echo", "orbit"))
    assert not is_near_duplicate(first, second)


def test_the_same_matchup_twice_is_fine_when_the_battles_differ() -> None:
    """A short comeback round a rotor and a long close fight behind a gate."""
    short_rotor = candidate(
        total=90.0, seed=1, powers=("rush", "titan"), duration=13.0,
        damaging_hits=6, lead_changes=1, layout_shape=(("rotor", 1),),
    )
    long_gate = candidate(
        total=85.0, seed=2, powers=("titan", "rush"), duration=21.0,
        damaging_hits=12, lead_changes=5, layout_shape=(("gate", 1), ("bumper", 2)),
        winner_id=1,
    )
    assert not is_near_duplicate(short_rotor, long_gate)
    result = curate([short_rotor, long_gate], config(size=10, matchup_share=1.0))
    assert result.size == 2


def test_the_similarity_threshold_is_adjustable() -> None:
    first = candidate(total=90.0, seed=1, duration=17.0, damaging_hits=8)
    second = candidate(total=90.0, seed=2, duration=25.0, damaging_hits=20,
                       layout_shape=(("gate", 2),))
    signals = len(similarity_signals(first, second))
    assert is_near_duplicate(first, second, threshold=signals)
    assert not is_near_duplicate(first, second, threshold=signals + 1)


def test_near_duplicates_are_dropped_from_a_batch() -> None:
    clones = [candidate(total=90.0 - index * 0.1, seed=index) for index in range(6)]
    result = curate(clones, config(size=10, matchup_share=1.0))
    assert result.size == 1
    assert result.rejected[REJECT_SIMILAR] == 5
    assert count_near_duplicates(result.selected) == 0


# --- the point of the whole exercise ----------------------------------------


def test_curation_trades_a_little_score_for_much_more_variety() -> None:
    """The top of the pool is repetitive; slightly lower down it is not.

    Six near-identical Pulse battles score highest, and a raw top-four would
    take four of them. Curation should reach past them for the varied ones
    just below, giving up a couple of points to do it.
    """
    repetitive = [
        candidate(total=95.0 - index * 0.1, seed=100 + index, powers=("pulse", "pulse"),
                  duration=18.0, damaging_hits=9, lead_changes=3,
                  layout_shape=(("bumper", 2),), kinetic_obstacles=0)
        for index in range(6)
    ]
    varied = [
        candidate(total=93.0, seed=1, powers=("rush", "titan"), duration=11.0,
                  damaging_hits=6, lead_changes=1, kinetic_obstacles=1,
                  layout_shape=(("rotor", 1), ("bumper", 1))),
        candidate(total=92.0, seed=2, powers=("echo", "orbit"), duration=24.0,
                  damaging_hits=14, lead_changes=6, kinetic_obstacles=2,
                  layout_shape=(("gate", 1), ("rotor", 1))),
        candidate(total=91.0, seed=3, powers=("titan", "echo"), duration=16.0,
                  damaging_hits=9, lead_changes=4, kinetic_obstacles=1,
                  layout_shape=(("gate", 1), ("bar", 2))),
    ]
    pool = repetitive + varied

    raw = sorted(pool, key=lambda c: c.rank_key)[:4]
    assert len({matchup_key(c.metrics.powers) for c in raw}) == 1, "the top is repetitive"

    result = curate(pool, config(size=4, mirror_share=0.30))
    chosen = result.selected
    assert len(chosen) == 4
    assert len({matchup_key(c.metrics.powers) for c in chosen}) == 4
    assert count_near_duplicates(chosen) == 0
    assert {motion_class(c.metrics.kinetic_obstacles) for c in chosen} != {"static"}

    raw_mean = sum(c.score.total for c in raw) / len(raw)
    curated_mean = sum(c.score.total for c in chosen) / len(chosen)
    assert curated_mean < raw_mean, "curation should cost a little score"
    assert raw_mean - curated_mean < 4.0, "but not very much of it"
    assert min(c.score.total for c in chosen) >= 80.0, "and never below the floor"


# --- determinism and ordering -----------------------------------------------


def test_curation_is_deterministic(small_pool: list[Candidate]) -> None:
    first = curate(small_pool, config())
    second = curate(small_pool, config())
    assert [c.metrics.seed for c in first.selected] == [
        c.metrics.seed for c in second.selected
    ]
    assert first.rejected == second.rejected


def test_curation_does_not_care_what_order_the_pool_arrives_in(
    small_pool: list[Candidate],
) -> None:
    forwards = curate(small_pool, config())
    backwards = curate(list(reversed(small_pool)), config())
    assert [c.metrics.seed for c in forwards.selected] == [
        c.metrics.seed for c in backwards.selected
    ]


def test_the_batch_comes_out_in_quality_order(pool: list[Candidate]) -> None:
    selected = curate(pool, config(size=8)).selected
    totals = [c.score.total for c in selected]
    assert totals == sorted(totals, reverse=True)


def test_the_batch_is_the_same_however_many_workers_evaluated_it() -> None:
    jobs = [(seed, LAYOUT_PROCEDURAL) for seed in range(SEED, SEED + SMALL_POOL_SEEDS)]
    single = curate(search(jobs, 1), config())
    parallel = curate(search(jobs, 4), config())
    assert [c.metrics.seed for c in single.selected] == [
        c.metrics.seed for c in parallel.selected
    ]


def test_scoring_is_untouched_by_curation(small_pool: list[Candidate]) -> None:
    """Diversity lives in the curator; a battle's score is its own business."""
    lone = evaluate_seed(SEED, LAYOUT_PROCEDURAL)
    before = score_battle(lone).total
    curate(small_pool, config())
    assert score_battle(lone).total == before
    for candidate_in_pool in small_pool:
        assert candidate_in_pool.score == score_battle(candidate_in_pool.metrics)


# --- manifest ---------------------------------------------------------------


def batch_of(pool: list[Candidate], size: int = 5):
    settings = config(size=size)
    return settings, curate(pool, settings)


def test_a_batch_id_is_stable_and_never_a_timestamp() -> None:
    derived = batch_id_for(20000, 10000, LAYOUT_PROCEDURAL, None)
    assert derived == batch_id_for(20000, 10000, LAYOUT_PROCEDURAL, None)
    assert "20000" in derived and "29999" in derived
    assert batch_id_for(0, 10, LAYOUT_PROCEDURAL, "shorts001") == "shorts001"


def test_the_manifest_is_deterministic_and_complete(pool: list[Candidate]) -> None:
    settings, result = batch_of(pool)
    first = build_manifest(result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True)
    second = build_manifest(result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    assert first["version"] == MANIFEST_VERSION == 1
    assert first["batch_id"] == "t1"
    assert first["source"] == {
        "start_seed": SEED, "seed_count": 400, "arena": LAYOUT_PROCEDURAL
    }
    assert first["curation"]["min_score"] == settings.min_score
    assert first["summary"]["count"] == len(first["items"])
    assert set(first["rejected"]) >= {REJECT_SCORE, REJECT_SIMILAR}


def test_every_manifest_item_can_be_audited_and_re_rendered(
    pool: list[Candidate],
) -> None:
    settings, result = batch_of(pool)
    manifest = build_manifest(
        result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True
    )
    for index, (entry, chosen) in enumerate(
        zip(manifest["items"], result.selected), start=1
    ):
        assert entry["index"] == index
        assert entry["seed"] == chosen.metrics.seed
        assert entry["arena_mode"] == chosen.metrics.arena_mode
        assert entry["powers"] == list(chosen.metrics.powers)
        assert entry["score"] == pytest.approx(chosen.score.total, abs=1e-3)
        assert entry["review_status"] == REVIEW_PENDING
        assert entry["label"] == " vs ".join(p.upper() for p in chosen.metrics.powers)
        assert set(entry["components"]) == {
            "pacing", "suspense", "action", "variety", "arena", "payoff", "penalty"
        }
        assert entry["environment"]["motion_class"] in MOTION_CLASSES


def test_manifest_replay_paths_are_relative(pool: list[Candidate]) -> None:
    settings, result = batch_of(pool)
    manifest = build_manifest(
        result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True
    )
    for entry in manifest["items"]:
        path = entry["replay_path"]
        assert not os.path.isabs(path)
        assert ":" not in path and "\\" not in path
        assert path.startswith("replays/") and path.endswith(".json")


def test_a_manifest_without_replays_names_none(pool: list[Candidate]) -> None:
    settings, result = batch_of(pool)
    manifest = build_manifest(
        result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", False
    )
    assert all("replay_path" not in entry for entry in manifest["items"])


# --- replay verification ----------------------------------------------------


def test_verification_passes_when_the_replay_is_the_chosen_battle(
    pool: list[Candidate], tmp_path
) -> None:
    settings, result = batch_of(pool, size=3)
    manifest = build_manifest(
        result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True
    )
    verify_and_export(manifest, result, str(tmp_path), write_files=True)
    for entry in manifest["items"]:
        written = tmp_path / entry["replay_path"]
        assert written.exists()
        replay = json.loads(written.read_text(encoding="utf-8"))
        assert replay["version"] == 6
        assert replay["seed"] == entry["seed"]


def test_verification_fails_loudly_on_a_mismatch(
    pool: list[Candidate], tmp_path
) -> None:
    """A batch that describes the wrong battle must not be written at all."""
    settings, result = batch_of(pool, size=2)
    tampered = dataclasses.replace(
        result.selected[0],
        metrics=dataclasses.replace(result.selected[0].metrics, duration=99.0),
    )
    result.selected[0] = tampered
    manifest = build_manifest(
        result, settings, SEED, 400, LAYOUT_PROCEDURAL, "t1", True
    )
    with pytest.raises(VerificationError, match="not the battle"):
        verify_and_export(manifest, result, str(tmp_path), write_files=False)


# --- summary reporting ------------------------------------------------------


def test_a_summary_describes_the_batch(pool: list[Candidate]) -> None:
    _, result = batch_of(pool)
    found = summarise(result.selected)
    assert found["count"] == result.size
    assert found["score"]["min"] <= found["score"]["mean"] <= found["score"]["max"]
    assert found["timeouts"] == 0
    assert sum(found["powers"].values()) == 2 * result.size
    assert sum(found["motion"].values()) == result.size
    assert found["unique_matchups"] == len(found["matchups"])


def test_an_empty_batch_summarises_without_blowing_up() -> None:
    assert summarise([])["count"] == 0


def test_a_real_batch_clears_every_production_rule(pool: list[Candidate]) -> None:
    settings, result = batch_of(pool, size=8)
    for chosen in result.selected:
        assert chosen.score.total >= settings.min_score >= DEFAULT_MIN_SCORE - 1e-9
        assert not chosen.metrics.is_timeout
        assert not chosen.metrics.is_draw
        assert chosen.metrics.duration >= settings.min_duration
        assert chosen.metrics.max_fighter_speed <= settings.max_speed
        assert chosen.metrics.state_valid
        assert not chosen.metrics.entities_leaked
    assert count_near_duplicates(result.selected) == 0
