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

    `race2.track.capped_profile` flattens everything above 0.62 layout units.
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


def test_the_renderer_does_not_touch_the_contained_stage():
    """Race #2's scene builds no environment of its own and edits none.

    The other session owns `environment_stage.gd` and the V27 profiles. This
    asserts the Race #2 scene only *calls* the shared seam.
    """
    import pathlib

    scene = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"
    text = scene.read_text(encoding="utf-8")
    assert "environment_stage" not in text
    assert "contained_hall" not in text
    # It resolves a profile and asks `course_world` to build one; it never
    # constructs a light, a sky or a backdrop itself.
    assert "World.build_environment" in text
    assert "World.build_lights" in text
    assert "DirectionalLight3D.new" not in text
    assert "ProceduralSkyMaterial" not in text
