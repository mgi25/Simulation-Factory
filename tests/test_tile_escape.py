"""Category 3 Phase 1: the eight things the prototype is allowed to be believed on.

The brief lists them, and each one is a test here rather than a sentence in a
report: the tile count, stable tile identity, a first hit activating exactly
one tile, a duplicate hit not moving progress, progress never exceeding the
total, completion only after every tile, reproducible initialisation, and the
ball staying inside the arena.

Two of them are worth a note on method.

**Boundedness is checked twice, and once analytically.** `max_wall_excursion`
is computed inside the solver as the exact maximum of each wall's quadratic
over each flight, so it is a statement about the whole trajectory and not about
the instants a test happened to sample. The sampled check is here as well, at
600 Hz, because an analytic bound computed by the same code it is vouching for
deserves an independent witness.

**Determinism is checked across processes, not only within one.** A
same-process repeat shares a warm interpreter, so it cannot see state that
leaks between runs through module-level caching or a random stream that was not
re-derived. `python -m satisfying.tile_escape_cli --digest-only` in a child
process can, and that is the convention `tests/test_marble3d_determinism.py`
set for this repository.

No Godot, no PyBullet, no pygame: Category 3's physics is a hundred lines of
analytic geometry and the whole file runs in about a second.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

import pytest

from satisfying import seeds
from satisfying.tile_arena import polygon_arena
from satisfying.tile_escape import (
    DEFAULT_CONFIG,
    TileEscapeConfig,
    reachability_margin,
    simulate,
    start_state,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Long enough that every seed tried here completes. The brief's own answer to
# "what if it takes too long" is that that is a Phase 2 pacing problem, so the
# tests give the natural physics as much clock as it needs rather than tuning
# the physics to fit a test.
LONG = TileEscapeConfig(duration=1200.0)
SEEDS = (1, 7, 12, 19)


# --------------------------------------------------------------------------
# The arena: count, identity, and which tile a contact belongs to.
# --------------------------------------------------------------------------


def test_the_arena_generates_the_expected_tile_count() -> None:
    arena = polygon_arena()
    assert arena.sides == 16
    assert arena.tiles_per_side == 3
    assert arena.total_tiles == 48
    assert len(arena.tiles) == 48


@pytest.mark.parametrize(
    ("sides", "per_side", "total"), [(16, 3, 48), (12, 4, 48), (8, 1, 8), (20, 2, 40)]
)
def test_the_tile_count_is_sides_times_tiles_per_side(
    sides: int, per_side: int, total: int
) -> None:
    assert polygon_arena(sides=sides, tiles_per_side=per_side).total_tiles == total


def test_every_tile_has_a_unique_identity() -> None:
    arena = polygon_arena()
    assert len({tile.tile_id for tile in arena.tiles}) == arena.total_tiles
    assert len({tile.index for tile in arena.tiles}) == arena.total_tiles
    assert [tile.index for tile in arena.tiles] == list(range(arena.total_tiles))


def test_tile_identity_is_stable_across_builds() -> None:
    """Identity comes from the geometry, so two arenas agree tile for tile."""
    first, second = polygon_arena(), polygon_arena()
    assert [t.tile_id for t in first.tiles] == [t.tile_id for t in second.tiles]
    assert [t.midpoint for t in first.tiles] == [t.midpoint for t in second.tiles]
    assert [(t.side, t.slot) for t in first.tiles] == [
        (t.side, t.slot) for t in second.tiles
    ]


def test_a_contact_is_attributed_to_the_tile_it_landed_on() -> None:
    """Every tile's own midpoint, and two interior points, map back to it."""
    arena = polygon_arena()
    for tile in arena.tiles:
        for fraction in (0.15, 0.5, 0.85):
            ax, ay = tile.start
            bx, by = tile.end
            point = (ax + (bx - ax) * fraction, ay + (by - ay) * fraction)
            assert arena.tile_for_contact(tile.side, point) is tile


def test_a_contact_at_a_shared_vertex_lands_on_one_tile_and_not_off_the_end() -> None:
    arena = polygon_arena()
    for side in range(arena.sides):
        for vertex in (arena.vertices[side], arena.vertices[(side + 1) % arena.sides]):
            tile = arena.tile_for_contact(side, vertex)
            assert tile.side == side
            assert tile.slot in (0, arena.tiles_per_side - 1)


def test_the_tiles_of_a_side_tile_it_end_to_end_with_no_gap_or_overlap() -> None:
    arena = polygon_arena()
    for side in range(arena.sides):
        run = [t for t in arena.tiles if t.side == side]
        assert run[0].start == pytest.approx(arena.vertices[side])
        assert run[-1].end == pytest.approx(
            arena.vertices[(side + 1) % arena.sides]
        )
        for earlier, later in zip(run, run[1:]):
            assert earlier.end == pytest.approx(later.start)
        assert sum(t.length for t in run) == pytest.approx(arena.side_length)


def test_a_tile_is_longer_than_the_ball_is_wide() -> None:
    """Otherwise one impact could plausibly belong to either of two tiles."""
    arena = polygon_arena()
    assert arena.tile_length > 2.0 * DEFAULT_CONFIG.ball_radius


# --------------------------------------------------------------------------
# Deterministic initialisation.
# --------------------------------------------------------------------------


def test_the_same_seed_gives_the_same_release() -> None:
    for seed in SEEDS:
        assert start_state(seed) == start_state(seed)


def test_different_seeds_give_different_releases() -> None:
    releases = {start_state(seed) for seed in range(1, 17)}
    assert len(releases) == 16


def test_the_release_speed_is_the_config_speed_and_nothing_else() -> None:
    for seed in SEEDS:
        _, (vx, vy) = start_state(seed)
        assert math.hypot(vx, vy) == pytest.approx(DEFAULT_CONFIG.speed)


def test_the_release_point_is_inside_the_arena_with_the_ball_clear_of_the_wall() -> None:
    arena = polygon_arena()
    for seed in range(1, 200):
        position, _ = start_state(seed)
        assert arena.contains(position, DEFAULT_CONFIG.ball_radius)
        assert math.hypot(*position) <= seeds.RELEASE_RADIUS_FRACTION * arena.circumradius


def test_the_same_seed_gives_the_same_run_in_one_process() -> None:
    for seed in SEEDS:
        digests = {simulate(seed, LONG).state_digest() for _ in range(3)}
        assert len(digests) == 1


def test_the_same_seed_gives_the_same_run_in_a_fresh_interpreter() -> None:
    for seed in (7, 12):
        run = simulate(seed, TileEscapeConfig(duration=600.0))
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "satisfying.tile_escape_cli",
                "--seed",
                str(seed),
                "--duration",
                "600",
                "--digest-only",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": REPO_ROOT},
        )
        digest, collisions, activated, finish = completed.stdout.strip().split()
        assert digest == run.state_digest()
        assert int(collisions) == len(run.collisions)
        assert int(activated) == run.activated_tiles
        assert float(finish) == pytest.approx(run.completion_time)


def test_two_seeds_do_not_produce_the_same_run() -> None:
    """The release disc has to actually matter, or a seed is decoration."""
    digests = {simulate(seed, LONG).state_digest() for seed in SEEDS}
    assert len(digests) == len(SEEDS)


# --------------------------------------------------------------------------
# Activation: once per tile, never more.
# --------------------------------------------------------------------------


def test_the_first_hit_on_a_tile_activates_it() -> None:
    run = simulate(7, LONG)
    seen: set[str] = set()
    for hit in run.collisions:
        first_time = hit.tile_id not in seen
        assert hit.is_new is first_time, hit
        seen.add(hit.tile_id)
    assert seen == set(run.first_hit_time)


def test_a_duplicate_hit_does_not_move_progress() -> None:
    run = simulate(7, LONG)
    progress = 0
    duplicates = 0
    for hit in run.collisions:
        if hit.is_new:
            assert hit.activated_after == progress + 1
            progress += 1
        else:
            duplicates += 1
            assert hit.activated_after == progress
    assert duplicates > 0, "a run with no repeat hits would not test anything"
    assert progress == run.activated_tiles


def test_a_tile_is_activated_exactly_once_however_often_it_is_hit() -> None:
    run = simulate(7, LONG)
    activations = sum(1 for hit in run.collisions if hit.is_new)
    assert activations == run.activated_tiles
    assert activations == len(run.first_hit_time)
    for tile_id, first in run.first_hit_time.items():
        hits = [h for h in run.collisions if h.tile_id == tile_id]
        assert [h for h in hits if h.is_new] == hits[:1]
        assert hits[0].time == first
    assert run.metrics["hits_max"] > 1, "no tile was hit twice; test proves nothing"


def test_progress_never_exceeds_the_total_tile_count() -> None:
    for seed in SEEDS:
        run = simulate(seed, LONG)
        assert run.activated_tiles <= run.total_tiles
        assert run.progress_ratio <= 1.0
        assert max(h.activated_after for h in run.collisions) <= run.total_tiles
        assert sum(1 for h in run.collisions if h.is_new) <= run.total_tiles


def test_activation_is_monotone_in_time() -> None:
    run = simulate(7, LONG)
    counts = [run.activated_count_at(t / 4.0) for t in range(int(run.end_time * 4) + 1)]
    assert counts == sorted(counts)
    assert counts[0] == 0
    assert run.activated_count_at(run.end_time) == run.activated_tiles


# --------------------------------------------------------------------------
# Completion.
# --------------------------------------------------------------------------


def test_completion_happens_only_when_every_tile_is_activated() -> None:
    for seed in SEEDS:
        run = simulate(seed, LONG)
        assert run.completed
        assert run.activated_tiles == run.total_tiles
        assert run.unhit_tiles() == ()
        assert run.stop_reason == "complete"
        assert run.collisions[-1].is_new
        assert run.collisions[-1].activated_after == run.total_tiles
        assert run.completion_time == run.collisions[-1].time
        # Nothing was complete one collision earlier.
        assert run.activated_count_at(run.collisions[-2].time) == run.total_tiles - 1


def test_a_run_stopped_early_is_not_complete() -> None:
    run = simulate(7, TileEscapeConfig(duration=20.0))
    assert not run.completed
    assert run.completion_time is None
    assert run.stop_reason == "duration"
    assert 0 < run.activated_tiles < run.total_tiles
    assert len(run.unhit_tiles()) == run.total_tiles - run.activated_tiles


def test_an_arena_whose_top_cannot_be_reached_never_completes() -> None:
    """The one config mistake that silently makes the mechanic impossible.

    With elastic walls the specific energy is fixed at release, so too little
    speed for the gravity leaves the upper tiles unreachable for ever.
    `reachability_margin` is the number that says so before a run is started.
    """
    starved = TileEscapeConfig(speed=8.0, gravity=12.0, duration=400.0)
    assert reachability_margin(starved) < 1.0
    run = simulate(7, starved)
    assert not run.completed
    ceiling = {t.tile_id for t in run.arena.tiles if t.side in (7, 8, 9)}
    assert ceiling.isdisjoint(run.first_hit_time)

    assert reachability_margin(DEFAULT_CONFIG) > 1.0
    assert reachability_margin(TileEscapeConfig(gravity=0.0)) == math.inf


# --------------------------------------------------------------------------
# The ball: bounded, stable, and losing nothing.
# --------------------------------------------------------------------------


def test_the_ball_stays_inside_the_arena_for_the_whole_run() -> None:
    for seed in SEEDS:
        run = simulate(seed, LONG)
        # The analytic bound, over every flight rather than every sample.
        assert run.metrics["max_wall_excursion"] < 1.0e-9
        # And an independent witness at 600 Hz.
        arena = run.arena
        radius = run.config.ball_radius
        steps = int(run.end_time * 600)
        worst = max(
            radius - arena.clearance(run.position_at(step / 600.0))
            for step in range(steps + 1)
        )
        assert worst < 1.0e-9, f"seed {seed} left the arena by {worst}"


def test_the_ball_neither_stalls_nor_runs_away() -> None:
    for seed in SEEDS:
        metrics = simulate(seed, LONG).metrics
        assert metrics["speed_min"] > 1.0, "a ball this slow is a dead simulation"
        assert metrics["speed_max"] < 40.0, "a ball this fast is a solver blowing up"
        assert metrics["energy_drift_relative"] < 1.0e-6
        assert metrics["min_flight_seconds"] > 1.0e-3, "collisions collapsing together"


def test_an_elastic_run_conserves_energy_collision_by_collision() -> None:
    """Every bounce, not just the endpoints: a drift that cancels is still a drift."""
    run = simulate(7, LONG)
    gravity = run.config.gravity
    energies = [
        0.5 * (f.velocity[0] ** 2 + f.velocity[1] ** 2) + gravity * f.position[1]
        for f in run.flights
    ]
    assert max(energies) - min(energies) < 1.0e-5 * energies[0]


def test_a_reflection_preserves_speed_and_reverses_the_wall_normal() -> None:
    run = simulate(7, LONG)
    normals = run.arena.side_outward_normals
    for hit, after in zip(run.collisions, run.flights[1:]):
        nx, ny = normals[hit.side]
        outgoing = math.hypot(*after.velocity)
        assert outgoing == pytest.approx(hit.incoming_speed, rel=1e-9)
        assert after.velocity[0] * nx + after.velocity[1] * ny < 0.0


def test_no_gravity_is_a_valid_configuration() -> None:
    """The horizontal billiard has to work too: it is Phase 2's obvious lever."""
    config = TileEscapeConfig(gravity=0.0, duration=1200.0)
    run = simulate(7, config)
    speeds = [math.hypot(*f.velocity) for f in run.flights]
    assert max(speeds) == pytest.approx(config.speed, rel=1e-9)
    assert min(speeds) == pytest.approx(config.speed, rel=1e-9)
    assert run.metrics["max_wall_excursion"] < 1.0e-9


def test_the_instruments_report_the_pacing_problem_rather_than_hiding_it() -> None:
    """Phase 1's job is to measure the dead periods, so they have to be there."""
    run = simulate(7, LONG)
    metrics = run.metrics
    assert metrics["longest_no_progress_seconds"] > 0.0
    assert metrics["longest_no_progress_collisions"] > 0
    assert metrics["duplicate_hits"] > metrics["new_activations"]
    assert len(metrics["activation_intervals"]) == run.activated_tiles
    assert sum(metrics["activation_intervals"]) == pytest.approx(
        max(run.first_hit_time.values()), abs=1e-3
    )
    assert metrics["longest_confined_run"] >= 1
    assert sum(metrics["hits_by_tile"].values()) == metrics["collisions"]


def test_a_ball_that_does_not_fit_the_arena_is_refused() -> None:
    with pytest.raises(ValueError):
        simulate(1, TileEscapeConfig(ball_radius=20.0))
    with pytest.raises(ValueError):
        polygon_arena(sides=2)
    with pytest.raises(ValueError):
        polygon_arena(circumradius=0.0)


def test_an_even_sided_arena_has_parallel_opposite_walls_and_an_odd_one_has_none() -> None:
    """The geometry behind Phase 1's one real pathology.

    Two parallel walls admit a ball bouncing perpendicular between them for
    ever. An even polygon has eight such pairs; an odd polygon has none, which
    is why `docs/category3_tile_escape_phase1.md` recommends 17 sides.
    """
    even = polygon_arena(sides=16)
    for side in range(8):
        near = even.side_outward_normals[side]
        far = even.side_outward_normals[side + 8]
        assert near[0] == pytest.approx(-far[0], abs=1e-12)
        assert near[1] == pytest.approx(-far[1], abs=1e-12)

    odd = polygon_arena(sides=17)
    for a in range(odd.sides):
        for b in range(a + 1, odd.sides):
            na, nb = odd.side_outward_normals[a], odd.side_outward_normals[b]
            assert na[0] * nb[0] + na[1] * nb[1] > -0.999, (a, b)


def test_the_sixteen_sided_arena_admits_a_two_tile_bounce_loop_and_seventeen_does_not() -> None:
    """The measurement, pinned so a geometry change cannot quietly undo it.

    Seed 134 with no gravity spends dozens of consecutive collisions
    alternating between one floor tile and the ceiling tile opposite it, and
    escapes only because the skin nudge accumulates rounding error. The same
    seed in a 17-sided arena cannot: the thresholds are loose because the exact
    count depends on floating point, but the two orders of magnitude between
    them do not.
    """
    fast = TileEscapeConfig(gravity=0.0, speed=60.0, duration=1200.0)

    sixteen = simulate(134, fast, polygon_arena(sides=16))
    assert sixteen.metrics["longest_confined_run"] >= 20
    trapped = sixteen.metrics["longest_confined_tiles"]
    assert len(trapped) == 2
    first, second = (sixteen.arena.tiles[int(t.split("_")[1])] for t in trapped)
    assert abs(first.side - second.side) == sixteen.arena.sides // 2

    seventeen = simulate(134, fast, polygon_arena(sides=17))
    assert seventeen.metrics["longest_confined_run"] <= 5


# --------------------------------------------------------------------------
# The frame: is the difference between dark and lit actually visible.
# --------------------------------------------------------------------------


def test_a_lit_tile_is_measurably_brighter_than_a_dark_one() -> None:
    """The prototype's readability claim, as a number rather than an opinion.

    Counting bright pixels inside the arena rather than comparing frame means:
    a 9:16 frame is mostly empty background, so a mean over the whole frame
    barely moves between an empty arena and a full one, and the hook line and
    the count would dominate whatever was left.
    """
    pytest.importorskip("PIL")
    from satisfying.tile_render import render_frame

    run = simulate(7, LONG)
    width, height = 540, 960

    def bright(t: float) -> int:
        frame = render_frame(run, t, width=width, height=height, hook="", debug=False)
        arena_only = frame.crop((0, (height - width) // 2, width, (height + width) // 2))
        return sum(1 for value in arena_only.convert("L").getdata() if value > 120)

    start, finish = bright(0.2), bright(run.end_time)
    assert start < 0.1 * finish, (start, finish)
    assert finish > 10_000, finish


def test_the_frame_is_nine_by_sixteen_by_default() -> None:
    pytest.importorskip("PIL")
    from satisfying.tile_render import FRAME_HEIGHT, FRAME_WIDTH, render_frame

    assert FRAME_WIDTH * 16 == FRAME_HEIGHT * 9
    frame = render_frame(simulate(7, LONG), 1.0, width=180, height=320)
    assert frame.size == (180, 320)


# --------------------------------------------------------------------------
# Isolation from the other categories.
# --------------------------------------------------------------------------


def test_category_three_imports_no_other_category_and_no_company_os() -> None:
    """The workstream boundary, machine-checked rather than promised."""
    import ast
    import pathlib

    # The standard library, Pillow, numpy, and Category 3's own package. The
    # boundary this guard holds is the *workstream* one - no race, no duel, no
    # Company OS - so the list grows when Category 3 needs another stdlib
    # module and never when it needs another workstream.
    #
    # `glob`, `shutil` and `subprocess` arrived with Phase 3's Godot driver,
    # which finds the binary, launches it and collects the PNGs it wrote. Every
    # other render driver in this repository does the same three things.
    #
    # `array`, `collections` and `numpy` arrived with Phase 5's soundtrack:
    # a mono cue is an `array("d")`, the limiter's sliding minimum is a
    # `deque`, and every loudness measurement is numpy, which is already a
    # declared dependency of this repository.
    #
    # `concurrent` and `statistics` arrived with Test #2, the shell escape:
    # its Phase 1 answer is a question about a population of ten thousand
    # seeds, so it needs a process pool to produce one and quantiles to report
    # it. Both are stdlib, so both are the kind of growth this list is for.
    allowed = {
        "__future__",
        "argparse",
        "array",
        "collections",
        "concurrent",
        "dataclasses",
        "glob",
        "hashlib",
        "json",
        "math",
        "numpy",
        "os",
        "PIL",
        "random",
        "shutil",
        "statistics",
        "struct",
        "subprocess",
        "sys",
        "time",
        "typing",
        "satisfying",
    }
    # And `audio/`, which is the one package outside `satisfying/` that
    # Category 3 is allowed to reach - but only these three modules of it, and
    # `test_category_three_uses_only_the_leaf_audio_modules` is why that is a
    # boundary rather than a hole.
    allowed_audio = {"audio.synthesis", "audio.wav_io", "audio.loudness"}

    package = pathlib.Path(REPO_ROOT) / "satisfying"
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [
                    f"{node.module}.{alias.name}" if node.module else alias.name
                    for alias in node.names
                ]
            else:
                continue
            for name in names:
                if name.split(".")[0] != "audio":
                    assert name.split(".")[0] in allowed, (
                        f"{path.name} imports {name.split('.')[0]!r}"
                    )
                    continue
                # `from audio import loudness` and `from audio.loudness import x`
                # both have to land on the same three-module allowlist.
                module = name if name.count(".") else name
                while module and module not in allowed_audio:
                    module = module.rsplit(".", 1)[0] if "." in module else ""
                assert module in allowed_audio, (
                    f"{path.name} imports {name!r}; Category 3 may use only "
                    f"{sorted(allowed_audio)}"
                )


def test_category_three_uses_only_the_leaf_audio_modules() -> None:
    """The `audio/` dependency is a leaf, and that is what makes it allowed.

    Phase 5 needed oscillators, a WAV writer and a loudness meter, and the
    repository already had all three. Reimplementing them inside `satisfying/`
    would have meant a second true-peak meter that could drift from the first,
    so the guard above was widened to let Category 3 reach `audio/`.

    Widening it would have been a hole rather than a boundary without this
    test. `audio/soundtrack.py` opens with `from audio import cues` - the
    battle cue library - so importing it for its mastering functions would
    have pulled another workstream's sound design into Category 3's import
    graph. Phase 5's first draft did exactly that, this guard caught it, and
    `satisfying/tile_audio.py` now carries its own sixty-line master stage
    instead.

    So the three modules Category 3 may reach are checked here to import
    nothing but the standard library and numpy. If one of them ever grows a
    dependency on the rest of `audio/`, this fails before the guard above
    starts silently allowing it.
    """
    import ast
    import pathlib

    leaves = ("synthesis", "wav_io", "loudness")
    stdlib_and_numpy = {
        "__future__", "array", "dataclasses", "hashlib", "math", "numpy",
        "os", "struct", "sys", "typing", "wave",
    }
    for name in leaves:
        path = pathlib.Path(REPO_ROOT) / "audio" / f"{name}.py"
        assert path.is_file(), f"audio/{name}.py is gone"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in stdlib_and_numpy, (
                    f"audio/{name}.py imports {root!r}, so it is no longer a "
                    "leaf and Category 3 may no longer depend on it"
                )


#: Category 3's own laboratory tools live under `tools/` because that is where
#: this repository keeps every runnable tool, and they import `satisfying`
#: because measuring Category 3 is what they are for. They are named here
#: rather than exempted by a path pattern, so adding one is a deliberate act.
#:
#: This list exists because the guard below was failing on `main` before it was
#: read: Phase 3B added `multishell_phase3b_lab.py` and left the assertion red,
#: and a red guard is one nobody reads. Anything *not* on this list - a race
#: module, a sloped module, a render tool - still fails, which is what the
#: guard was written to catch.
CATEGORY_THREE_TOOLS = frozenset({
    "multishell_phase3b_lab.py",
    "multishell_phase3b_screen.py",
    "two_team_phase4a_lab.py",
    "two_team_phase4b_lab.py",
    "two_team_phase4c_lab.py",
})


def test_no_other_category_imports_category_three() -> None:
    """By import, not by substring: "satisfying" is also an ordinary English
    word and several race modules use it in prose."""
    import ast
    import pathlib

    root = pathlib.Path(REPO_ROOT)
    for directory in (
        "audio",
        "company",
        "engine",
        "entities",
        "evaluation",
        "intelligence",
        "marble3d",
        "modes",
        "powers",
        "production",
        "race",
        "race2",
        "rendering",
        "replay",
        "sloped",
        "tools",
    ):
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if directory == "tools" and path.name in CATEGORY_THREE_TOOLS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    roots = [(node.module or "").split(".")[0]]
                else:
                    continue
                assert "satisfying" not in roots, path
    # The exemption is a named list, not a hole: every name on it has to be a
    # file that exists and that really does import Category 3, or the list is
    # quietly permitting something it no longer describes.
    for name in CATEGORY_THREE_TOOLS:
        path = root / "tools" / name
        assert path.is_file(), f"{name} is exempted and does not exist"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            (alias.name.split(".")[0] if isinstance(node, ast.Import)
             else (node.module or "").split(".")[0])
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [node])
        }
        assert "satisfying" in imports, f"{name} no longer needs its exemption"
