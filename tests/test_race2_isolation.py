"""That Race #2 changed nothing about Race #1, and depends on no environment.

Two claims, and both are the sort that is true until someone refactors.

**Race #1 is untouched.** `race2` imports `sloped.track`, `sloped.stations`,
`sloped.trapdoor`, `sloped.solids`, `sloped.pathing`, `sloped.layout` and
`sloped.scale` for their primitives. Every one of those is shared with a course
whose frames are committed, so the test is that the sloped course still builds
to the same geometry and that `sloped.contract` still agrees with its recorded
layout.

**Race #2 is environment-independent.** Nothing in the package reads an
environment profile, a light rig, a palette or a backdrop. The course is built
from geometry and the camera from the race; the only place an environment is
named at all is the renderer's default, which is a string the scene passes
straight to Race #1's own `course_world`. That is what makes a contained hall a
drop-in rather than a port.
"""

from __future__ import annotations

import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_race_one_still_agrees_with_its_recorded_layout():
    """`sloped.contract` over all seven runs, unchanged.

    If a Race #2 edit had reached `sloped.track` or `sloped.pathing`, this is
    where it would show: the contract compares the reconstruction against a
    record written from the built Godot scene, point by point.
    """
    from sloped import contract

    findings = contract.check()
    assert not findings, [f"{f.check}/{f.subject}: {f.detail}" for f in findings]


def test_race_one_course_still_checks_out():
    from sloped.course import check

    findings = check()
    assert not findings, [f"{f.check}/{f.subject}: {f.detail}" for f in findings]


def test_race_one_channel_profile_is_not_capped():
    """The wall cap belongs to `race2.track` and must not leak into `sloped`.

    `race2.track.capped_profile` flattens everything above `WALL_CAP`.
    Race #1's own profile reaches `CONTAINMENT_TOP` and its committed frames
    were photographed with that rail.
    """
    from sloped import layout
    from sloped.track import channel_profile

    section = channel_profile(1.0)
    top = max(up for _across, up in section)
    assert top == pytest.approx(layout.CONTAINMENT_TOP, abs=1e-9)


def test_nothing_in_race2_imports_an_environment():
    """No module in the package reads a profile, a palette or a light.

    Read off the source, because the claim is about the dependency graph and a
    docstring cannot be run. The renderer names one environment as a default;
    that lives in GDScript and is a string the scene hands to Race #1's own
    `course_world`, which is the seam a contained hall arrives through.
    """
    import pathlib

    forbidden = (
        "environment_profile",
        "course_env",
        "lab_palette",
        "aurora_valley",
        "alpine_neon",
        "contained_hall",
        "environment_stage",
    )
    package = pathlib.Path(REPO) / "race2"
    for path in sorted(package.glob("*.py")):
        # Code only. `race2.camera` derives its preferred lens side from the
        # key light's rotation and *cites* the profile the number came from in
        # a comment; a test that rejected the citation would be telling the
        # next reader to delete the provenance.
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            for name in forbidden:
                assert name not in stripped, f"{path.name}: {stripped}"


def test_race2_does_not_edit_the_shared_primitives():
    """The three `sloped` modules Race #2 leans on are imported, not patched.

    A monkeypatch of `sloped.track.channel_profile` would make every Race #1
    frame in the repository irreproducible and would pass every other test in
    this file.
    """
    import pathlib

    package = pathlib.Path(REPO) / "race2"
    for path in sorted(package.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith("sloped."), f"{path.name}: {stripped}"
            assert "setattr(sloped" not in stripped, f"{path.name}: {stripped}"


def _scene_code() -> str:
    """`race2_scene.gd` with its comments removed.

    The assertions below are about what the scene *does*, and V29 gave it a
    long comment block naming the very modules and profiles those assertions
    forbid. Testing the raw text would then fail on prose, which is how a
    correct test gets deleted for being wrong. The file has no `#` inside a
    string literal - there is a test for that immediately below - so cutting
    at the first `#` on each line leaves exactly the code.
    """
    import pathlib

    scene = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"
    lines = []
    for line in scene.read_text(encoding="utf-8").splitlines():
        cut = line.find("#")
        lines.append(line if cut < 0 else line[:cut])
    return '\n'.join(lines)


def test_the_scene_has_no_hash_inside_a_string_literal():
    """What `_scene_code` depends on, asserted rather than assumed."""
    import pathlib
    import re

    scene = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"
    for number, line in enumerate(
            scene.read_text(encoding="utf-8").splitlines(), start=1):
        for literal in re.findall(r'"[^"]*"', line):
            assert "#" not in literal, f"line {number}: {literal}"


def test_the_renderer_does_not_touch_the_contained_stage():
    """Race #2's scene builds no environment of its own and edits none.

    **V29 changed what this test can say and not what it is for.** Race #2 now
    builds a stage - that is the whole of the V29 integration - so the old form
    of this test, which asserted the string `environment_stage` was absent, is
    asserting the opposite of the shipped behaviour. What it was *for* is that
    the scene owns none of the environment: it calls the shared seam and does
    not reimplement, edit or special-case any part of it. That survives V29
    intact and is what is asserted here.
    """
    code = _scene_code()

    # It reaches the stage through `environment_world.build`, the one entry
    # point Race #1 uses, rather than preloading the stage module and calling
    # its builders itself.
    assert "environment_world.gd" in code
    assert "EnvWorld.build(" in code
    assert "environment_stage.gd" not in code
    assert "Stage.build(" not in code

    # It defines none of the stage's own builders.
    for builder in ("func _shell", "func _pylons", "func _canopy",
                    "func _bays", "func _deck("):
        assert builder not in code, builder

    # It special-cases no profile. The hall is reached by `--environment=`,
    # like every other world, and the default is still the one camera A was
    # developed against.
    assert "contained_hall" not in code
    assert "contained_base" not in code
    assert 'DEFAULT_ENVIRONMENT := "aurora_valley_v26"' in code

    # It resolves a profile and asks `course_world` to build one; it never
    # constructs a light, a sky or a backdrop itself.
    assert "World.build_environment" in code
    assert "World.build_lights" in code
    assert "DirectionalLight3D.new" not in code
    assert "ProceduralSkyMaterial" not in code
