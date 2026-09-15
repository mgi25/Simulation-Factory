"""What V26 must be true of: the format is V24's, the world is V25.2's.

V26 is an integration and not a pass, so almost everything here is an assertion
that something did **not** change. The suite is organised by who owns what,
because that is the only thing an integration can get wrong:

* **the four dimensions are four strings**, declared once in `sloped/v26.py`,
  reaching the scene through four independent options, naming disjoint surfaces;
* **the format is V24's, by identity rather than by copy.** `sloped/v26.py`
  imports V24's hook, windows, omissions, mark and payoff; the render edition
  points at V24's own solved camera track file. "V26 keeps V24's camera timing"
  is therefore a property of the file list, not a measurement;
* **the physics is untouched**, which is the same claim V24's suite makes and is
  re-made here because an integration is exactly where it would break;
* **history still builds.** V20, V21, V21.1, V22, V22.1, V23 and V24 gained
  nothing, lost nothing, and cannot see a V26 field.

The replay and the solved tracks are generated output and not in the branch, so
tests that need them skip rather than fail. The rendered master is likewise
generated, so the picture tests skip without it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import v23, v24, v24_hook, v24_payoff, v26

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PROFILES = GODOT / "assets" / "marble_machine" / "environment" / "profiles"
V252_JSON = PROFILES / "aurora_valley_v252.json"
V26_JSON = PROFILES / "aurora_valley_v26.json"
PALETTE_GD = GODOT / "assets" / "marble_machine" / "lab_palette.gd"
COURSE_SCENE_GD = GODOT / "scripts" / "course_scene.gd"
RACE_SCENE_GD = GODOT / "scripts" / "sloped_race_scene.gd"
RACER_VISUAL_GD = GODOT / "assets" / "marble_machine" / "racers" / "racer_visual.gd"

PALETTE = PALETTE_GD.read_text(encoding="utf-8")
COURSE_SCENE = COURSE_SCENE_GD.read_text(encoding="utf-8")
RACE_SCENE = RACE_SCENE_GD.read_text(encoding="utf-8")

OUT_DIR = os.path.join("output", "sloped_race_v1")
REPLAY = os.path.join(OUT_DIR, "race_5432.json")
V24_TRACK = os.path.join(OUT_DIR, "cameras_v24_5432.json")
V26_MASTER = os.path.join(OUT_DIR, "v26", "race_master.mp4")

SEED = 5432
DIGEST = "aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6"
FINISH_ORDER = [5, 2, 7, 4, 1, 6, 3, 0]
WINNER = 5
WINNER_LABEL = "PURPLE"
WINNER_HUE = (0x8E, 0x3F, 0xD4)

# V24's, and V26's because they are the same numbers reached by import.
DURATION = 20.116666
FRAMES = 1208
RUNTIME = (19.8, 20.4)
OMISSION_COUNT = 3
HOOK_NAME = "b_gate"
MARK_BASELINE = 269
FRAME_ZERO_MEDIAN_PX = 146.24

#: What frame zero's mark has to clear, column by column, at phone size. The bar
#: is `v24_hook.MIN_TEXT_CONTRAST` and this is the margin V26 actually has - a
#: regression that halved it would still pass the bar and is worth catching.
MARK_CONTRAST_FLOOR = 6.0

#: The weakest racer-against-its-surround separation frame zero may fall to, in
#: CIE dE. V24 renders 47.1 here and V26 renders 65.9 - the darker V25.2 world
#: helps rather than hurts - so this floor is set at V24's own delivered value:
#: V26 is not allowed to become worse than the film it is replacing.
MIN_FRAME_ZERO_DE = 47.0

#: How many of the winner's own 18 ring frames must actually have the winner in
#: the picture under them. V24 delivers 13, V26 delivers 11, and V26 rendered on
#: the unfixed `aurora_valley_v252` delivers 6. See
#: `test_the_winner_is_under_its_own_ring`.
MIN_RING_FRAMES_ON_WINNER = 10


def _tool(name: str):
    """Load one of the entry points by path; neither is an importable module."""
    spec = importlib.util.spec_from_file_location(
        "_v26_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _machine_keys(name: str) -> set[str]:
    """The surface keys one `MACHINE_PASSES` entry names."""
    block = re.search(r"const MACHINE_PASSES := \{(.*?)\n\}\n", PALETTE, re.S)
    assert block, "MACHINE_PASSES is not declared in lab_palette.gd"
    body = block.group(1)
    entry = re.search(r'"%s":\s*\{' % re.escape(name), body)
    assert entry, "no machine pass named %r" % name
    start = entry.end() - 1
    depth = 0
    for index in range(start, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                break
    return set(re.findall(r'^\t\t"([a-z0-9_]+)"\s*:', body[start:index + 1], re.M))


@pytest.fixture(scope="module")
def short():
    return _tool("sloped_short")


@pytest.fixture(scope="module")
def render():
    return _tool("sloped_v22")


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY):
        pytest.skip(f"{REPLAY} is generated output and is not in the branch")
    with open(REPLAY, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def track():
    if not os.path.isfile(V24_TRACK):
        pytest.skip(f"{V24_TRACK} is generated output and is not in the branch")
    with open(V24_TRACK, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def frame_zero(track, replay):
    return v24_hook.first_frame_report(track, replay)


@pytest.fixture(scope="module")
def v26_frame_zero():
    """V26's own rendered frame zero, out of the delivered master."""
    import shutil
    import subprocess
    import tempfile

    if not os.path.isfile(V26_MASTER):
        pytest.skip(f"{V26_MASTER} is generated output and is not in the branch")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is not on PATH")
    from PIL import Image

    out = os.path.join(tempfile.mkdtemp(), "frame0.png")
    done = subprocess.run(
        [ffmpeg, "-y", "-i", V26_MASTER, "-frames:v", "1", out],
        capture_output=True, text=True,
    )
    if done.returncode != 0 or not os.path.isfile(out):
        pytest.skip("could not read frame zero out of the V26 master")
    return Image.open(out)


# --- the V26 configuration exists and says one thing each -------------------


def test_the_v26_config_exists_and_names_all_four_dimensions():
    assert v26.BASE_ENVIRONMENT == "aurora_valley_v252"
    assert v26.ENVIRONMENT == "aurora_valley_v26"
    assert v26.MACHINE == "v23b"
    assert v26.RACERS == "meridian"
    assert v26.PREVIEW is None
    summary = v26.describe()
    for token in ("aurora_valley_v26", "v23b", "meridian", "preview=none"):
        assert token in summary, summary


def test_the_four_strings_are_written_once():
    """**One source of truth**, which is the brief's own requirement.

    Neither edition table may spell a V26 dimension out; both take the tuple
    `sloped/v26.py` builds. If a string were written twice, an edition could be
    rendered under one world and QC'd against another and nothing would say so.
    """
    for name in ("sloped_short", "sloped_v22"):
        text = (ROOT / "tools" / (name + ".py")).read_text(encoding="utf-8")
        body = text[text.index('"v26": {'):]
        body = body[:body.index("\n    },")]
        for spelled in ("aurora_valley_v26", "aurora_valley_v252", "meridian"):
            assert spelled not in body, (
                f"{name} spells {spelled!r} out; it belongs in sloped/v26.py")


def test_the_scene_flags_carry_one_flag_per_dimension(render):
    flags = render.EDITIONS["v26"]["scene"]
    assert flags == v26.SCENE_FLAGS
    assert "--environment=aurora_valley_v26" in flags
    assert "--machine=v23b" in flags
    assert "--racers=meridian" in flags
    assert "--finish-sign=double" in flags
    # One flag each and nothing else: a fifth string here would be a theme.
    assert len(flags) == 4


def test_the_machine_string_is_v23s_own_rather_than_a_copy():
    assert v26.MACHINE is v23.MACHINE
    assert v26.FINISH_SIGN is v23.FINISH_SIGN


# --- the world is V25.2's, registered, valid, and unchanged -----------------


def test_both_profiles_are_registered_and_resolve_clean():
    for name in (v26.BASE_ENVIRONMENT, v26.ENVIRONMENT):
        assert name in env.ids(), name
        profile = env.resolve(name)
        assert env.validate(profile) == [], name
        assert profile["id"] == name


def test_the_v26_profile_is_one_leaf_of_geometry_over_v252():
    """**The whole of V26's claim on the world, as an assertion.**

    V26 does not retune V25.2. It moves one scarp out of the line between V24's
    finish camera and the winner's crossing, and `environment.flatten` is asked
    to prove that is all it moves: the only leaves that may differ are the
    profile's own identity fields and `world.scarps.sites`, and inside that list
    only entry 8, and only in x.

    See `sloped/v26.py` for the measurement that justifies the move - the winner
    is the picture under its own ring in 6 of 18 frames on `aurora_valley_v252`
    and 11 of 18 on this profile, against V24's 13.
    """
    base = env.flatten(env.resolve(v26.BASE_ENVIRONMENT))
    ours = env.flatten(env.resolve(v26.ENVIRONMENT))
    differ = {k for k in set(base) | set(ours) if base.get(k) != ours.get(k)}
    assert differ <= {"id", "title", "summary", "extends", "world.scarps.sites"}, (
        "V26 changes more of the world than the one scarp: %s" % sorted(differ))
    assert "world.scarps.sites" in differ
    before = base["world.scarps.sites"]
    after = ours["world.scarps.sites"]
    assert len(before) == len(after), "V26 added or removed a scarp"
    moved = [i for i, (a, b) in enumerate(zip(before, after)) if list(a) != list(b)]
    assert moved == [8], moved
    assert list(after[8]) == [34.0, 34.0, 90.0, 1.0]
    # Moved *away* from the course, so the builder's own clearance can only grow.
    assert after[8][0] > before[8][0]
    assert after[8][1:] == before[8][1:]


def test_the_v26_profile_extends_v252_rather_than_copying_it():
    doc = json.loads(V26_JSON.read_text(encoding="utf-8"))
    assert doc["extends"] == v26.BASE_ENVIRONMENT
    # Only the one section is restated. A profile that pasted V25.2's palette
    # would stop tracking it, which is the failure this guards.
    assert set(doc["world"]) == {"scarps"}
    assert "palette" not in doc
    assert "lights" not in doc


def test_v26_does_not_edit_the_v252_profile_itself():
    """V26 selects the world. It does not get to retune it.

    The brief's Part T: this is an integration pass. If the V25.2 look needed
    changing, that is a V25.3 and it is not this branch's to open.
    """
    import subprocess

    rel = V252_JSON.relative_to(ROOT).as_posix()
    done = subprocess.run(
        ["git", "diff", "--stat", "9496dd1", "HEAD", "--", rel],
        cwd=ROOT, capture_output=True, text=True,
    )
    if done.returncode != 0:
        pytest.skip("git is unavailable or the base commit is not present")
    assert done.stdout.strip() == "", (
        "V26 edited the V25.2 profile:\n" + done.stdout)


def test_the_environment_and_the_machine_name_disjoint_surfaces():
    """The architectural rule, as an assertion, re-made for V26's own pair.

    V23 proved it for `aurora_valley` x `v23b`. V25.2's profile names more world
    surfaces than V23's did, so the overlap it could create with the machine
    pass is a new one and this is where it would show.
    """
    world = set(env.resolve(v26.ENVIRONMENT)["palette"])
    machine = _machine_keys(v26.MACHINE)
    assert world, "the V25.2 profile names no surfaces"
    assert machine, "%s names no surfaces" % v26.MACHINE
    assert not (world & machine), (
        "environment and machine both name: %s" % sorted(world & machine))


def test_the_four_switches_do_not_reach_each_other_in_the_scene():
    """Four options, four doors. None of them may shadow another."""
    assert 'var _machine := ""' in COURSE_SCENE
    assert 'var _environment_id := ""' in COURSE_SCENE
    assert 'Palette.new("tower", _contrast, _machine)' in COURSE_SCENE
    assert "EnvBuilder.apply_palette(_palette, _environment)" in COURSE_SCENE
    for call in ("World.build_environment(", "World.build_lights("):
        start = COURSE_SCENE.index(call)
        args = COURSE_SCENE[start:COURSE_SCENE.index(")", start)]
        assert "_machine" not in args
    # The racer surface is the fourth, and it is read in the race scene rather
    # than the course scene because it is a property of the racers, not the
    # world or the machine.
    assert 'early.get("racers", DEFAULT_RACERS)' in RACE_SCENE
    # The race scene reads the racer surface and nothing else of the other
    # three: no `--machine=` and no `--environment=` is parsed here, so it
    # cannot override what `course_scene` resolved. (`course_machine` appears
    # in comments, which is why this looks for the option read, not the word.)
    for option in ("machine", "environment", "contrast"):
        assert f'early.get("{option}"' not in RACE_SCENE or option == "contrast"
        assert f'options.get("{option}"' not in RACE_SCENE


# --- the format is V24's, by identity ---------------------------------------


def test_the_hook_is_v24s_b_gate_object_and_not_a_copy():
    assert v26.HOOK is v24.HOOK
    assert v24_hook.HOOKS[HOOK_NAME] is v26.HOOK
    assert v26.HOOK.opens_at == 0.2


def test_the_mark_is_pick_a_color_and_it_is_up_at_second_zero():
    assert v26.MARK_IN == 0.0
    assert (v26.MARK_IN, v26.MARK_OUT_FROM, v26.MARK_OUT_TO) == (
        v24.MARK_IN, v24.MARK_OUT_FROM, v24.MARK_OUT_TO)
    assert v26.MARK_BASELINE == v24.MARK_BASELINE == MARK_BASELINE
    assert v24_hook.HOOK_TEXT == "PICK A COLOR"


def test_the_timeline_windows_are_v24s_own_objects():
    assert v26.START_WINDOWS is v24.START_WINDOWS
    assert v26.OMISSIONS is v24.OMISSIONS
    assert v26.RESUME_AT == v24.RESUME_AT
    assert v26.TAIL_AT == v24.TAIL_AT
    assert v26.BEAT == v24.BEAT
    assert v26.EDIT == v24.EDIT == "v24"
    assert v26.build_race_track is v24.build_race_track
    assert v26.build_opening_track is v24.build_opening_track
    assert v26.film_clock is v24.film_clock


def test_there_are_exactly_three_omissions_and_they_are_v24s():
    assert len(v26.OMISSIONS) == OMISSION_COUNT
    names = [name for name, *_ in v26.OMISSIONS]
    assert names == ["spin", "fall", "trap"]
    bounds = {name: (round(low, 3), round(high, 3))
              for name, low, high in v26.OMISSIONS}
    assert bounds["spin"] == (2.05, 4.483)
    assert bounds["fall"] == (6.417, 6.717)
    assert bounds["trap"] == (13.583, 14.033)


def test_there_is_no_course_preview(render, short):
    assert v26.PREVIEW is None
    assert render.EDITIONS["v26"]["preview_track"] is None
    assert render.has_preview("v26") is False
    assert "preview" not in short.EDITIONS["v26"]


def test_there_is_no_frozen_opening_hold(short):
    assert short.EDITIONS["v26"]["hold"] == 0.0
    assert short.EDITIONS["v26"]["cuts"] == ()


def test_the_payoff_is_v24s_plate_and_it_names_purple(short):
    assert v26.PAYOFF == v24_payoff.RECOMMENDED
    assert short.EDITIONS["v26"]["payoff"] == v26.PAYOFF
    assert short.EDITIONS["v26"]["mark"] == "v24"
    assert v26.PAYOFF == "plate"
    card = v24_payoff.build(style=v26.PAYOFF, winner=WINNER,
                            from_place=v24_payoff.WINNER_FROM)
    assert card.label == WINNER_LABEL
    assert card.text_contrast >= 4.5
    # The colour is an area, not a dot: the plate is the sample.
    assert card.colour_pixels > 20000


def test_the_runtime_band_is_v24s(short):
    assert short.EDITIONS["v26"]["runtime"] == RUNTIME
    assert short.EDITIONS["v26"]["runtime"] == short.EDITIONS["v24"]["runtime"]


# --- the camera schedule is V24's file, not a copy of it --------------------


def test_v26_renders_v24s_own_solved_track(render, short):
    """The strongest form of "the camera timing is preserved": one file."""
    assert (render.EDITIONS["v26"]["race_track"]
            == render.EDITIONS["v24"]["race_track"])
    assert (short.EDITIONS["v26"]["track"] == short.EDITIONS["v24"]["track"])
    assert render.race_track_path("v26", SEED) == render.race_track_path("v24", SEED)


def test_v26_refuses_to_re_solve_the_track_it_borrows(render):
    """A V26 solve would overwrite V24's delivered track. It must not run."""
    assert render.borrows_track("v26") == "v24"
    with pytest.raises(render.V22Error) as raised:
        render.stage_solve(SEED, "v26")
    assert "must not re-solve" in str(raised.value)


def test_v26_writes_its_own_files_and_overwrites_nothing_of_v24(render, short):
    assert render.EDITIONS["v26"]["work"] == "v26"
    assert render.work_dir("v26") != render.work_dir("v24")
    for key in ("video", "visual", "silent"):
        assert short.EDITIONS["v26"][key] != short.EDITIONS["v24"][key]
        assert "v26" in short.EDITIONS["v26"][key]
    assert short.EDITIONS["v26"]["master"] != short.EDITIONS["v24"]["master"]


def test_the_edit_map_is_slope_one_everywhere(track):
    """No segment compresses. An omission here is a window boundary."""
    for segment in track["edit"]:
        out = segment["out"][1] - segment["out"][0]
        replay_span = segment["replay"][1] - segment["replay"][0]
        assert abs(out - replay_span) < 1e-9, segment


def test_the_segments_tile_the_output_with_no_gap(track):
    cursor = 0.0
    for segment in track["edit"]:
        assert abs(segment["out"][0] - cursor) < 1e-9, segment
        cursor = segment["out"][1]
    assert abs(cursor - track["duration"]) < 1e-9


def test_the_film_is_v24s_length(track):
    assert abs(track["duration"] - DURATION) < 1e-9
    assert v26.master_frames(track) == FRAMES
    assert RUNTIME[0] <= track["duration"] <= RUNTIME[1]


# --- the physics is untouched ------------------------------------------------


def test_seed_and_digest_are_the_locked_ones(replay):
    assert int(replay["seed"]) == SEED
    assert replay["digest"] == DIGEST


def test_finish_order_is_unchanged(replay):
    order = [int(event["id"]) for event in _finish_line(replay)]
    assert order == FINISH_ORDER
    assert list(v26.FINISH_ORDER) == FINISH_ORDER


def test_the_winner_is_marble_five(replay):
    first = _finish_line(replay)[0]
    assert int(first["id"]) == WINNER == v26.WINNER == v24_payoff.WINNER_INDEX
    assert v26.WINNER_COLOUR == WINNER_LABEL == v24_payoff.COLOUR_NAMES[WINNER]
    from sloped import overlays

    assert tuple(overlays.MARBLE_HUES[WINNER]) == WINNER_HUE
    # The crossing the ring and the card are both scheduled off.
    assert abs(float(first["t"]) - v26.WINNER_CROSSES) < 1e-6


def test_the_recorded_quaternions_are_what_the_film_draws(replay):
    """Meridian draws the replay's own rotation. There is no synthetic spin.

    V24 made this claim and V26 inherits the racer surface unchanged, so the
    claim is re-made here against the same replay: every marble carries a unit
    quaternion per frame, and it is not the identity.
    """
    frames = replay["frames"]
    turned = 0
    for frame in frames[::37]:
        for marble in frame["marbles"]:
            quat = marble.get("q")
            assert quat is not None and len(quat) == 4
            norm = sum(value * value for value in quat) ** 0.5
            assert abs(norm - 1.0) < 1e-3, quat
            if abs(abs(quat[3]) - 1.0) > 1e-4:
                turned += 1
    assert turned > 0, "every recorded quaternion is the identity"


def test_no_v26_module_writes_to_the_replay():
    """`sloped/v26.py` selects. It does not simulate."""
    source = (ROOT / "sloped" / "v26.py").read_text(encoding="utf-8")
    for forbidden in ("def simulate", "random", "seed(", "write_replay", "open("):
        assert forbidden not in source, forbidden


def _finish_line(replay: dict) -> list[dict]:
    """The replay's own finish events, in crossing order.

    Read exactly the way `tests/test_sloped_v24_integration.py` reads them, so
    the two suites agree on what "the finish order" means rather than each
    inventing a reader.
    """
    return sorted(
        (event for event in replay["events"] if event["kind"] == "finish_line"),
        key=lambda event: int(event["order"]),
    )


# --- the picture, where it is the integration that could have broken it -----


def test_frame_zero_still_shows_all_eight_racers_large(frame_zero):
    """Geometric, and therefore identical to V24 by construction.

    The camera track and the replay are V24's own files, so this cannot differ -
    which is the point of asserting it: if it ever does, the borrow broke.
    """
    assert frame_zero["racers"] == frame_zero["of"] == 8
    assert abs(frame_zero["median_px"] - FRAME_ZERO_MEDIAN_PX) < 0.5
    assert frame_zero["t"] == 0.2
    assert min(frame_zero["disc_visible"].values()) > 0.8


def test_the_first_second_still_moves_when_it_did(replay, track):
    motion = v24_hook.motion_report(replay, v26.HOOK, track)
    assert abs(motion["mechanism"] - 0.116667) < 1e-4
    assert abs(motion["camera"] - 0.166667) < 1e-4
    assert abs(motion["racers"] - 0.233333) < 1e-4


def test_the_mark_still_has_somewhere_to_sit_on_the_v252_world(
        v26_frame_zero, frame_zero):
    """**The one Part A risk, as a test.**

    V24's `b_gate` was framed against the V22.1 world, which had no near
    geometry. V25.2 has a great deal of it, and a boulder or a tree landing
    under PICK A COLOR would be a real failure rather than a matter of taste.

    So the plate is re-scored on V26's own rendered frame: `text_plate` must
    still choose the baseline V24 ships, and the worst of the mark's twelve
    columns must clear the bar with margin.
    """
    plate = v24_hook.text_plate(v26_frame_zero, frame_zero)
    assert plate["baseline"] == MARK_BASELINE, (
        "the V25.2 world moved where the mark wants to sit")
    assert plate["contrast"] >= v24_hook.MIN_TEXT_CONTRAST
    assert plate["contrast"] >= MARK_CONTRAST_FLOOR


def test_the_mark_reads_at_phone_size(v26_frame_zero, frame_zero):
    phone = v26_frame_zero.resize(
        (v24_hook.PHONE_WIDTH, v24_hook.PHONE_HEIGHT))
    plate = v24_hook.text_plate(phone, frame_zero)
    assert plate["contrast"] >= v24_hook.MIN_TEXT_CONTRAST


def test_every_racer_reads_against_the_v252_world(v26_frame_zero, frame_zero):
    """Marble-against-background separation, re-measured on the new world.

    The brief's Part C: the meridian marker was validated against V22.1
    backgrounds and the V25.2 world may change local colour contrast. Measured,
    it improves it - the world is darker - and the floor here is V24's own
    delivered worst case, so V26 may not become worse than what it replaces.
    """
    report = v24_hook.legibility_report(v26_frame_zero, frame_zero)
    assert report["legible"] == report["of"] == 8
    assert report["min_de"] >= MIN_FRAME_ZERO_DE


def test_every_racer_reads_at_phone_size(v26_frame_zero, frame_zero):
    phone = v26_frame_zero.resize(
        (v24_hook.PHONE_WIDTH, v24_hook.PHONE_HEIGHT))
    report = v24_hook.legibility_report(phone, frame_zero)
    assert report["legible"] == report["of"] == 8
    assert report["min_de"] >= MIN_FRAME_ZERO_DE


def test_the_winner_is_under_its_own_ring(track, replay):
    """**The defect the V26 profile exists to fix, as a regression test.**

    The ring opens on the crossing and runs 0.3 s, and the payoff lab's whole
    finding was that a mark pointing at a marble nobody can see is worse than no
    mark. Measured on the delivered, overlay-free master - the winner projected
    through the camera track, the pixel read back and matched against the eight
    racer hues - the count is

        V24                              13 of 18
        V26 on `aurora_valley_v252`       6 of 18
        V26 on `aurora_valley_v26`       11 of 18

    The floor here is 10, which is below what V26 measures and far above what
    the unfixed world does: a regression that put the scarp back would report 6
    and fail, and one that cost a frame or two of shading would not.
    """
    import shutil

    silent = os.path.join(OUT_DIR, "real_race_v26_master.mp4")
    if not os.path.isfile(silent):
        pytest.skip(f"{silent} is generated output and is not in the branch")
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not on PATH")
    tool = _tool("sloped_v26")
    film_clock = tool.clock("v26", SEED)
    report = tool.winner_ring(silent, film_clock, track, replay, winner=WINNER)
    assert report["frames"] == 18
    assert report["in_frame"] == 18, (
        "the winner leaves the frame during its own ring")
    assert report["on_winner"] >= MIN_RING_FRAMES_ON_WINNER, (
        "the ring points at the winner in only %d of %d frames; "
        "on aurora_valley_v252 it is 6, which is the scarp"
        % (report["on_winner"], report["frames"]))


# --- history still builds ----------------------------------------------------


def test_no_older_edition_gained_a_v26_flag(render, short):
    for edition in ("v22", "v221", "v23", "v24"):
        flags = render.EDITIONS[edition].get("scene", ())
        assert not any("aurora_valley_v25" in flag or "aurora_valley_v26" in flag
                       for flag in flags), edition
    for edition in ("v20", "v211", "v21", "v22", "v221", "v23"):
        assert short.EDITIONS[edition].get("mark") is None, edition
        assert short.EDITIONS[edition].get("payoff") is None, edition


def test_v24_is_exactly_what_it_was(render, short):
    """The edition V26 is measured against must still build what it built."""
    assert render.EDITIONS["v24"]["scene"] == (
        "--finish-sign=double", "--racers=meridian")
    assert render.EDITIONS["v24"]["preview_track"] is None
    assert render.borrows_track("v24") is None
    assert short.EDITIONS["v24"]["cuts"] == ()
    assert short.EDITIONS["v24"]["hold"] == 0.0
    assert short.EDITIONS["v24"]["runtime"] == RUNTIME
    assert short.EDITIONS["v24"]["video"].endswith("real_race_v24.mp4")


def test_v23_is_exactly_what_it_was(render, short):
    assert v23.ENVIRONMENT == "aurora_valley"
    assert v23.MACHINE == "v23b"
    assert render.EDITIONS["v23"]["scene"] == v23.SCENE_FLAGS
    assert len(v23.SCENE_FLAGS) == 3, "V23 never carried a --racers flag"
    assert "--racers" not in " ".join(v23.SCENE_FLAGS)
    assert render.EDITIONS["v23"]["module"].__name__.endswith("v221")
    assert short.EDITIONS["v23"]["runtime"] == (26.0, 27.0)
    assert short.EDITIONS["v23"]["cues"] == "v221"


def test_v221_and_the_older_editions_are_untouched(short):
    assert short.DEFAULT_EDITION == "v21"
    assert short.EDITIONS["v20"]["cuts"] == ()
    assert short.EDITIONS["v211"]["cuts"] == short.EDITIONS["v21"]["cuts"] == ((49, 133),)
    assert short.EDITIONS["v22"]["cuts"] == short.EDITIONS["v221"]["cuts"] == ()
    assert short.EDITIONS["v221"]["runtime"] == (26.0, 27.0)


def test_the_render_default_edition_did_not_move(render):
    assert render.DEFAULT_EDITION == "v22"


def test_the_racer_default_is_still_the_shipped_sphere():
    """Every edition before V24 re-renders `solid`, because that is the default."""
    source = RACER_VISUAL_GD.read_text(encoding="utf-8")
    assert 'const DEFAULT := "solid"' in source or 'DEFAULT_RACERS := "solid"' in RACE_SCENE
    assert "meridian" in source


def test_the_shipped_environment_default_did_not_move():
    """Nothing V26 does makes a V25.2 world the default for anyone else."""
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    assert index["default"] == "alpine_neon"
    assert 'var _environment_id := ""' in COURSE_SCENE
