"""V23 is an environment lab over an accepted film. These pin what it may not do.

The whole value of this pass rests on one property: **a render with no
environment profile is the V22.1 picture**. If that is not true then the
comparison sheets are not a comparison of environments, they are a comparison of
environments plus whatever else the lab changed on the way past, and every
conclusion in `docs/sloped_race_v23_environment.md` is worth nothing.

So most of what follows is about isolation rather than about colour:

* **No production file moved.** The lab is nine new files and zero edits. That
  is checkable against `origin/main` and it is checked, because "additive" is
  the kind of claim that stays true right up until the moment somebody fixes a
  small thing in a shared file.
* **The default does nothing.** `course_env.apply` with an empty name must
  return before it touches the scene, and the render scene must only pass a
  profile when `--env=` was given.
* **A profile may only retint the world.** `WORLD_KEYS` is the boundary between
  the environment and the machine, and the three keys the dressing shares with
  the course - `graphite`, `graphite_deep`, `lit_cyan_line_hero` - must not be
  on it. This is the check that stops a direction recolouring the start
  module's edge lighting while it is recolouring six pylon beacons.
* **Nothing locked is named.** No profile may mention a camera, a replay, a
  seed, a route, a module or a marble. The brief lists those as locked and the
  cheapest way to keep them locked is to refuse to let a profile spell them.
* **The two halves agree.** `sloped.v23_env.DIRECTIONS` and
  `course_env_profiles.PROFILES` are written in different languages in different
  files and are the same list; a direction added to one and not the other would
  render as a silent baseline.

The measures get their own tests because each of them is a number the write-up
argues from, and two of the three that were tried turned out to measure
something other than their name. `plateaus` in particular is pinned to the
behaviour that survived - it detects a flat wall - and explicitly not to any
ranking between non-flat backdrops.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sloped import v23_env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_ASSETS = os.path.join(ROOT, "godot", "assets", "marble_machine", "course")
PROFILES_GD = os.path.join(GODOT_ASSETS, "course_env_profiles.gd")
ENV_GD = os.path.join(GODOT_ASSETS, "course_env.gd")
SCENE_GD = os.path.join(ROOT, "godot", "scripts", "v23_env_scene.gd")
RENDER_GD = os.path.join(ROOT, "godot", "scripts", "v23_env_render.gd")

# Every file the lab is allowed to consist of. The test that uses this is the
# one that makes "additive" a fact rather than an intention.
LAB_FILES = {
    "godot/assets/marble_machine/course/course_env.gd",
    "godot/assets/marble_machine/course/course_env_profiles.gd",
    "godot/scripts/v23_env_scene.gd",
    "godot/scripts/v23_env_render.gd",
    "godot/scenes/V23EnvRender.tscn",
    "sloped/v23_env.py",
    "tools/sloped_v23_env.py",
    "tests/test_sloped_v23_env.py",
    "docs/sloped_race_v23_environment.md",
}

# The lab's own proof directory. Sheets and the measure table are outputs
# rather than code, they are what the write-up argues from, and the repository
# keeps earlier passes' validation artefacts in the branch the same way.
LAB_ARTEFACTS = "docs/validation/sloped_race_v1/v23_environment/"


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# --- isolation --------------------------------------------------------------


def test_the_lab_changed_no_production_file():
    """Every path the environment-direction lab commit touched is a lab file.

    The brief asked for additive prototype work and said that any change to a
    production render file had to be isolated and documented. The strongest
    form of that is no change at all, and this is where that is checked rather
    than asserted - including the four files it would have been most natural to
    edit: `course_world.gd`, `course_terrain.gd`, `course_dressing.gd` and
    `course_scene.gd`.

    Scoped to the lab's own commit rather than to the whole branch. On the
    lab branch the two were the same thing; on `v23-integration` they are not,
    because the environment *system* deliberately rewrites `course_world.gd`
    and `course_scene.gd`. Widening this to the branch would either fail on a
    legitimate integration or have to whitelist those files, and both of those
    stop it from saying anything about the lab. So it asks the narrower
    question that is still true and still worth asking: the art lab that
    answered the direction question paid for itself in lab files only.
    """
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                                  text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):  # pragma: no cover
            return None
        return done.stdout if done.returncode == 0 else None

    # The commit that introduced the lab's own entry point, wherever it sits in
    # history - the cherry-pick onto the integration branch rewrote its sha.
    found = git("log", "--diff-filter=A", "--format=%H", "-1", "--",
                "tools/sloped_v23_env.py")
    if not found or not found.strip():  # pragma: no cover
        pytest.skip("git is unavailable, or the lab commit is not in history")
    listing = git("show", "--name-only", "--format=", found.strip())
    if listing is None:  # pragma: no cover
        pytest.skip("git is unavailable")
    changed = {line.strip() for line in listing.splitlines() if line.strip()}
    assert changed, "expected the lab commit to touch files"
    code = {one for one in changed if not one.startswith(LAB_ARTEFACTS)}
    assert code <= LAB_FILES, (
        "the V23 lab must be additive; these are not lab files: "
        + ", ".join(sorted(code - LAB_FILES))
    )


GODOT_BIN = (os.environ.get("GODOT_BIN") or os.environ.get("GODOT4_BIN") or "")
REPLAY = os.path.join(ROOT, "output", "sloped_race_v1", "race_5432.json")
TRACK = os.path.join(ROOT, "output", "sloped_race_v1", "cameras_v221_5432.json")
CONTRACT = os.path.join(ROOT, "output", "sloped_race_v1", "start_contract_5432.json")


@pytest.mark.skipif(
    not (GODOT_BIN and os.path.isfile(GODOT_BIN) and os.path.isfile(REPLAY)
         and os.path.isfile(TRACK) and os.path.isfile(CONTRACT)),
    reason="needs $GODOT_BIN and the locked replay and solved V22.1 track",
)
def test_the_lab_renderer_with_no_profile_is_byte_identical_to_production(tmp_path):
    """The claim the whole pass rests on, checked on pixels rather than on code.

    Three moments - the grid, the spinner corridor and the finish - rendered
    twice: once through `SlopedRaceRender.tscn`, which is what production ships,
    and once through the lab's `V23EnvRender.tscn` with no `--env=`. The PNGs
    must hash the same. Anything less and the comparison sheets are comparing
    environments plus whatever else the lab did on the way past.

    Slow (two Godot launches) and skipped wherever Godot or the generated inputs
    are absent, which is most CI. It is here because it is the one test that can
    fail for a reason no amount of reading the source would reveal.
    """
    import hashlib

    flags = [
        f"--replay={REPLAY}", f"--cameras={TRACK}", f"--start-contract={CONTRACT}",
        "--at=0.600,10.200,21.400", "--width=1080", "--height=1920",
        "--layout=b", "--detail=hero", "--routes=both", "--finish-sign=double",
    ]
    digests = []
    for scene in ("res://scenes/SlopedRaceRender.tscn",
                  "res://scenes/V23EnvRender.tscn"):
        out = tmp_path / scene.rsplit("/", 1)[-1]
        out.mkdir()
        done = subprocess.run(
            [GODOT_BIN, "--path", os.path.join(ROOT, "godot"), scene, "--",
             f"--out-dir={out}", *flags],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
        assert done.returncode == 0, done.stderr[-2000:]
        names = sorted(one.name for one in out.glob("*.png"))
        assert len(names) == 3, names
        digests.append([
            hashlib.sha256((out / name).read_bytes()).hexdigest() for name in names
        ])
    assert digests[0] == digests[1], (
        "a lab render with no profile must be the production render, byte for byte"
    )


def test_the_scene_extends_production_rather_than_copying_it():
    """The lab scene is a subclass and the lab renderer is a subclass.

    A copy would drift: the moment the production scene gains a fix, a copied
    lab scene is photographing a different course from the one it claims to be
    comparing environments on.
    """
    assert 'extends "res://scripts/sloped_race_scene.gd"' in read(SCENE_GD)
    assert 'extends "res://scripts/sloped_race_render.gd"' in read(RENDER_GD)


def test_no_profile_means_no_change():
    """`apply` returns before touching anything when the name is empty."""
    body = read(ENV_GD)
    guard = body.index("if name.is_empty():")
    first_touch = body.index("report[\"environment\"] = _apply_environment")
    assert guard < first_touch, "the empty-name guard must precede every apply"
    # And the scene must not call `apply` at all in that case.
    scene = read(SCENE_GD)
    assert 'if name.is_empty():' in scene
    assert scene.index('if name.is_empty():') < scene.index("Env.apply(")


# --- the boundary between the world and the machine -------------------------


SHARED_WITH_THE_MACHINE = ("graphite", "graphite_deep", "graphite_soft",
                           "lit_cyan_line_hero", "lit_white", "lit_window",
                           "pearl_track", "pearl_shell", "chrome", "gold")


def world_keys() -> list[str]:
    body = read(ENV_GD)
    block = body[body.index("const WORLD_KEYS"):]
    block = block[:block.index("]")]
    return re.findall(r'"([a-z_0-9]+)"', block)


def test_world_keys_exclude_everything_the_machine_is_built_from():
    keys = world_keys()
    assert keys, "WORLD_KEYS should not be empty"
    for shared in SHARED_WITH_THE_MACHINE:
        assert shared not in keys, (
            f"{shared!r} builds part of the machine as well as the world; a "
            "profile must not be able to retint it through the palette cache"
        )


def test_every_material_a_profile_names_is_a_world_key():
    """The profiles may only name keys `course_env` will accept.

    `_apply_materials` pushes an error for anything else at runtime, which
    catches it in a render log. This catches it before a render.
    """
    body = read(PROFILES_GD)
    allowed = set(world_keys())
    # Only the `materials` blocks, which run from the line to the matching
    # close - taken by slicing between the block markers rather than by parsing
    # GDScript, because the file is generated by hand and read by Godot.
    for block in re.findall(r'"materials": \{(.*?)\n\t\},', body, re.S):
        for key in re.findall(r'\n\t\t"([a-z_0-9]+)":', block):
            assert key in allowed, f"{key!r} is not a world-only material key"


# --- what a profile may not mention -----------------------------------------

FORBIDDEN = (
    "camera", "replay", "5432", "seed", "physics", "marble", "racer",
    "collider", "course_layout", "cameras_v221", "route", "fps",
)


def test_no_profile_names_anything_the_brief_locked():
    """A direction describes an evening, not a race.

    Comments are stripped first: the prose in this file discusses cameras and
    replays constantly and should be able to keep doing so. What is checked is
    the data.
    """
    body = read(PROFILES_GD)
    code = "\n".join(
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    )
    lowered = code.lower()
    for word in FORBIDDEN:
        assert word not in lowered, (
            f"a profile mentions {word!r}; the brief locks it and a profile has "
            "no business naming it"
        )


# --- the two halves agree ---------------------------------------------------


def test_python_and_gdscript_list_the_same_directions():
    body = read(PROFILES_GD)
    block = body[body.index("const PROFILES := {"):]
    block = block[:block.index("}")]
    in_godot = set(re.findall(r'"([a-z_]+)":', block))
    in_python = {one.key for one in v23_env.DIRECTIONS}
    assert in_godot == in_python, (
        "a direction in one half and not the other renders as a silent "
        f"baseline: godot {sorted(in_godot)}, python {sorted(in_python)}"
    )


def test_the_baseline_is_the_empty_profile_and_is_first():
    assert v23_env.ALL[0] is v23_env.BASELINE
    assert v23_env.BASELINE.key == ""
    assert all(one.key for one in v23_env.DIRECTIONS)


def test_the_brief_asks_for_at_least_three_distinct_directions():
    assert len(v23_env.DIRECTIONS) >= 3
    assert len({one.key for one in v23_env.DIRECTIONS}) == len(v23_env.DIRECTIONS)


# --- the moments ------------------------------------------------------------


REQUIRED_STAGES = ("preview", "start", "descent", "obstacle", "fork",
                   "branches", "merge", "finish")


def test_every_stage_the_brief_lists_has_a_comparison_frame():
    keys = " ".join(one.key for one in v23_env.MOMENTS)
    for stage in REQUIRED_STAGES:
        assert stage in keys, f"no comparison frame covers {stage!r}"


def test_race_moments_fall_inside_the_v221_track():
    """The V22.1 race track runs 0 to 22.317 output seconds."""
    for one in v23_env.RACE_MOMENTS:
        assert 0.0 <= one.second <= 22.317, one


def test_preview_moments_fall_inside_the_preview():
    for one in v23_env.PREVIEW_MOMENTS:
        assert 0.0 <= one.second <= 3.483, one


def test_moment_keys_are_unique():
    keys = [one.key for one in v23_env.MOMENTS]
    assert len(set(keys)) == len(keys)


def test_seconds_for_splits_by_track():
    assert len(v23_env.seconds_for("race")) == len(v23_env.RACE_MOMENTS)
    assert len(v23_env.seconds_for("preview")) == len(v23_env.PREVIEW_MOMENTS)
    assert len(v23_env.MOMENTS) == (
        len(v23_env.RACE_MOMENTS) + len(v23_env.PREVIEW_MOMENTS)
    )


# --- the measures -----------------------------------------------------------


def solid(rgb: tuple[int, int, int], height: int = 400, width: int = 200):
    return np.full((height, width, 3), rgb, dtype=np.uint8)


def test_headroom_is_positive_when_the_subject_beats_the_backdrop():
    """A bright machine on a dark backdrop, as a two-band frame."""
    frame = np.zeros((400, 200, 3), dtype=np.uint8)
    frame[:100] = (20, 22, 30)      # backdrop band: dark
    frame[100:] = (240, 240, 236)   # the machine: bright
    measures = v23_env.frame_measures(frame)
    assert measures["headroom"] > 50.0
    # And the other way round, which is the V22.1 fault.
    flipped = frame[::-1].copy()
    assert v23_env.frame_measures(flipped)["headroom"] < 0.0


def test_backdrop_warmth_is_signed_and_reads_the_top_band_only():
    warm = np.zeros((400, 200, 3), dtype=np.uint8)
    warm[:100] = (220, 170, 110)    # tan sky
    warm[100:] = (30, 40, 70)       # cool ground, must not be counted
    assert v23_env.frame_measures(warm)["warmth"] > 20.0
    cool = np.zeros((400, 200, 3), dtype=np.uint8)
    cool[:100] = (30, 60, 100)
    cool[100:] = (220, 170, 110)
    assert v23_env.frame_measures(cool)["warmth"] < 0.0


def test_plateaus_calls_a_flat_wall_one_plane():
    """The one thing this measure is trusted for. See `v23_env.plateaus`."""
    lightness = np.full((480, 1080), 12.0)
    assert v23_env.plateaus(lightness) == 1
    # A hair of noise is still a wall: the floor is on the range, not the std.
    noisy = lightness + np.linspace(0.0, 2.0, 480)[:, None]
    assert v23_env.plateaus(noisy) == 1


def test_plateaus_separates_a_stack_of_bands():
    bands = np.concatenate([
        np.full((80, 200), value) for value in (8.0, 20.0, 33.0, 46.0, 60.0, 74.0)
    ])
    assert v23_env.plateaus(bands) >= 5


def test_plateaus_is_scale_free():
    """Halving a backdrop's contrast must not halve its plane count.

    This is the property the two rejected measures did not have, and it is the
    whole reason the band is normalised before it is binned.
    """
    bands = np.concatenate([
        np.full((80, 200), value) for value in (8.0, 20.0, 33.0, 46.0, 60.0, 74.0)
    ])
    assert v23_env.plateaus(bands) == v23_env.plateaus(bands * 0.35 + 5.0)


def test_clip_share_matches_the_v21_thresholds():
    frame = np.zeros((400, 200, 3), dtype=np.uint8)
    frame[:40] = 255
    measures = v23_env.frame_measures(frame)
    assert measures["flat_white"] == pytest.approx(10.0, abs=0.01)
    assert measures["near_clip"] == pytest.approx(10.0, abs=0.01)


def test_frame_measures_rejects_a_non_rgb_array():
    with pytest.raises(ValueError):
        v23_env.frame_measures(np.zeros((10, 10), dtype=np.uint8))


def test_separation_sees_a_marble_against_its_surround():
    frame = np.full((400, 400, 3), (210, 208, 200), dtype=np.uint8)
    ys, xs = np.mgrid[0:400, 0:400]
    frame[(xs - 200) ** 2 + (ys - 200) ** 2 <= 26 ** 2] = (220, 30, 40)
    found = v23_env.separation(frame, [(200.0, 200.0, 40.0)])
    assert len(found) == 1
    whole, chroma = found[0]
    assert whole > 40.0 and chroma > 30.0


def test_separation_reports_nothing_for_a_marble_off_frame():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert v23_env.separation(frame, [(500.0, 500.0, 12.0)]) == []
    assert v23_env.separation(frame, [(50.0, 50.0, 1.0)]) == []


def test_median_handles_both_parities_and_the_empty_case():
    assert v23_env.median([]) == 0.0
    assert v23_env.median([3.0, 1.0, 2.0]) == 2.0
    assert v23_env.median([4.0, 1.0, 2.0, 3.0]) == 2.5


# --- the output clock -------------------------------------------------------


def test_output_to_replay_is_slope_one_inside_a_window():
    track = {"edit": [
        {"cut": "a", "out": [0.0, 2.0], "replay": [0.5, 2.5]},
        {"cut": "b", "out": [2.0, 5.0], "replay": [4.0, 7.0]},
    ]}
    assert v23_env.output_to_replay(track, 0.0) == pytest.approx(0.5)
    assert v23_env.output_to_replay(track, 1.5) == pytest.approx(2.0)
    assert v23_env.output_to_replay(track, 3.0) == pytest.approx(5.0)


def test_output_to_replay_holds_at_the_end_rather_than_running_off():
    track = {"edit": [{"cut": "a", "out": [0.0, 2.0], "replay": [0.5, 2.5]}]}
    assert v23_env.output_to_replay(track, 99.0) == pytest.approx(2.5)


def test_output_to_replay_is_identity_without_an_edit():
    assert v23_env.output_to_replay({}, 1.25) == pytest.approx(1.25)
    assert v23_env.output_to_replay({"edit": []}, 1.25) == pytest.approx(1.25)


# --- the profiles themselves ------------------------------------------------


def test_every_profile_carries_a_title_and_a_note():
    body = read(PROFILES_GD)
    for name in ("AURORA", "COLLECTOR", "GRAPHITE"):
        block = body[body.index(f"const {name} := {{"):]
        block = block[:block.index("\n}\n")]
        assert '"title":' in block, name
        assert '"note":' in block, name


def test_every_feature_a_profile_asks_for_is_one_course_env_builds():
    """A typo in a feature name would push an error and build nothing."""
    handled = set(re.findall(
        r'\n\t\t\t"([a-z_]+)":\n\t\t\t\t_',
        read(ENV_GD),
    ))
    assert handled, "expected course_env._apply_features to handle some features"
    asked = set(re.findall(r'"features": \[([^\]]*)\]', read(PROFILES_GD)))
    wanted = {
        one.strip().strip('"')
        for entry in asked for one in entry.split(",") if one.strip()
    }
    assert wanted <= handled, f"unhandled features: {sorted(wanted - handled)}"


def test_the_directions_disagree_about_the_sky():
    """Three directions, not three grades.

    The cheapest machine-checkable form of "genuinely different, not tiny
    variations": no two of them may share a sky top colour, a fog colour or a
    background energy.
    """
    body = read(PROFILES_GD)
    for field, pattern in (
        ("sky top", r'"top": "(#[0-9A-Fa-f]{6})"'),
        ("fog colour", r'"colour": "(#[0-9A-Fa-f]{6})", "energy"'),
        ("background energy", r'"background_energy": ([0-9.]+)'),
    ):
        found = re.findall(pattern, body)
        assert len(found) >= 3, (field, found)
        head = found[:3]
        assert len(set(head)) == 3, f"two directions share a {field}: {head}"
