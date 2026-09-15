"""V26: V24's format, V25.2's world, V23B's machine - one line each.

**V26 invents nothing.** Two development lines were validated independently
against the same race, and this module is the single place that says how they
are combined:

    V24     the viewer format      what the film *is*: the hook, the length,
                                   the edit, the racer surface, the payoff
    V25.2   the world              what the race is *in*: geometry, rock,
                                   vegetation, terrain, light, atmosphere
    V23B    the machine            what the machine is *painted* in

Neither line touched the other's territory and neither touched the physics. The
proof is not an argument, it is a hash: `race_5432.json` is byte-identical on
`v24-integration` and on `v252-final-world-lookdev`, so the replay this edition
renders is the replay both lines rendered, and the finish order below is the
finish order both of them shipped.

## Why the four strings are four strings

`course_scene` already takes `--environment`, `--machine`, `--racers` and
`--contrast` as four independent options, and it resolves them through four
different doors: the profile is an override table applied over a built
material, the machine pass is a constructor argument to `lab_palette`, the
racer appearance is a texture written into the racer material's own albedo, and
the contrast pass is the grade. None of them can shadow another by accident,
and `tests/test_sloped_v26_integration.py` fails if any of them starts reaching
into another's surfaces.

That orthogonality is the deliverable. A country skin is the next stage of this
project and it is a *fifth* such string; the thing that makes it a string
rather than a fork is that V26 resisted writing a "V26 theme" that bundles a
world and a machine together.

## What V26 does not re-solve

The camera track. `tools/sloped_v22.py --edition v26` points at
`cameras_v24_{seed}.json` - V24's own solved file, not a copy of it and not a
re-solve of it - for exactly the reason V23 points at V22.1's. A repaint that
re-solved its cameras would be asserting that the solve is deterministic rather
than relying on the same numbers. Pointing both editions at one file makes the
camera track identical **by construction**, and there is no drift left for a
test to have to catch. `--stage solve` is therefore not part of a V26 build.

So the edit map, the omission bounds, the hook timing, the ring schedule and
the payoff beat are V24's because they are *literally* V24's: this module
imports them rather than restating them, and
`tests/test_sloped_v26_integration.py` checks that the import is what happened.

## What changes, and the one thing it could have broken

Every V26 frame is a V24 frame with a different world behind it and a different
machine in front of it. The picture changes; the schedule does not.

The risk that carries is the brief's Part A: **the V24 hook was framed against
the V22.1 world, which had no near geometry, and V25.2 has a great deal of
it.** `b_gate` opens at extent 7.2 looking across the gate row - a front
three-quarter that puts the massif behind the mark - and a V25.2 boulder
landing in that sightline would be a real failure rather than a matter of
taste. What was measured, and what it came back as, is in
`docs/sloped_race_v26.md`.
"""

from __future__ import annotations

from sloped import v23, v24, v24_payoff
from sloped.v22 import FPS
from sloped.v24 import (  # noqa: F401  (re-exported: V26's schedule is V24's)
    BEAT,
    HOOK,
    MARK_BASELINE,
    MARK_IN,
    MARK_OUT_FROM,
    MARK_OUT_TO,
    OMISSIONS,
    RESUME_AT,
    START_WINDOWS,
    TAIL_AT,
    WINNER_CROSSES,
    build_opening_track,
    build_race_track,
    build_start_track,
    film_clock,
    master_frames,
)

__all__ = [
    "BASE_ENVIRONMENT",
    "EDIT",
    "ENVIRONMENT",
    "FINISH_ORDER",
    "FINISH_SIGN",
    "FPS",
    "MACHINE",
    "PAYOFF",
    "PREVIEW",
    "RACERS",
    "SCENE_FLAGS",
    "SOURCE",
    "TIMELINE",
    "WINNER",
    "WINNER_COLOUR",
    "describe",
]

# --- the four dimensions ----------------------------------------------------
#
# One assignment each, and nothing below reads any of them except to build the
# flag tuple. This is the "one explicit source of truth" the brief asks for: if
# a country skin, a second course or a V27 wants a different world, it changes
# one string here and nothing else in the repository knows the difference.

#: The world V25.2 shipped, and the world V26 selects from it. See
#: `godot/assets/marble_machine/environment/profiles/aurora_valley_v252.json`
#: and `sloped/v252_world.py`: V25.1's geometry and density with the shading
#: response rebuilt - tempered normals, a baked albedo gradient, a material
#: shadow floor, restrained warmth, broken hero silhouettes, leaning vegetation,
#: a slate obstacle pocket and a warm finish basin.
#:
#: **Not** `aurora_valley`, which is V23's and is what V23 still renders.
BASE_ENVIRONMENT = "aurora_valley_v252"

#: The world V26 actually renders: `aurora_valley_v252` with **one scarp moved
#: three units**, and nothing else. `environment.diff` reports exactly one
#: geometric leaf between the two, `world.scarps.sites[8]`, from
#: `[31.0, 34.0, 90.0, 1.0]` to `[34.0, 34.0, 90.0, 1.0]`.
#:
#: **Why a V26 profile exists at all**, since the brief asks for V25.2's world
#: and this pass is not entitled to retune it.
#:
#: Rendered under `aurora_valley_v252`, the purple winner is behind that scarp
#: for the middle of its own WINNER mark. Measured on the delivered frames -
#: the winner projected through the camera track, the pixel read back off the
#: overlay-free master - the marble is the picture under the ring in
#:
#:     V24                     13 of 18 ring frames
#:     V26 on v252              6 of 18
#:     V26 on this profile     11 of 18
#:
#: so for seven frames of the film's payoff the ring and the word WINNER sit on
#: bare rock. That is the exact defect `sloped/v24_payoff.py` exists to have
#: removed, arriving again by a different door, and Part G of the brief makes
#: the finish hierarchy - winner first - a requirement rather than a preference.
#:
#: **It is a V25.2 defect only under V24's camera.** The scarp is at the same
#: coordinates in V25.1 and V25.2 and is harmless in V25.1. What moved it is
#: that V25.2 *deleted a different scarp* earlier in the list, and the scarp
#: builder seeds each site's variation by its **index**: removing site 4
#: re-rolled every site after it, and this one re-rolled into the finish
#: camera's sightline. V25.2's own proof cameras never looked down that line.
#:
#: The displacement is the smallest that works and it saturates: 1 unit gives
#: 9/18, 2 units 11/18, and 3, 5 and 9 units all give 11/18 as well. Three is
#: taken for the margin, and it moves the scarp *away* from the course, so the
#: clearance the builder already enforces can only increase.
ENVIRONMENT = "aurora_valley_v26"

#: The machine colour language. V23's lab shipped three; `v23b` is the balanced
#: one - `v23a` is subtler than the brief asks for and `v23c` trades marble
#: readability for zone identity. Taken from `sloped.v23` rather than retyped,
#: so the two editions cannot drift apart on the string they agree about. See
#: `lab_palette.MACHINE_PASSES`.
MACHINE = v23.MACHINE

#: The racer surface. `meridian` paints a greyscale marker into the racer
#: material's albedo map, in the mesh's own UV space, so the marble's real
#: rotation - the quaternion the replay already carries - becomes visible
#: without anything animating it. There is no synthetic rolling law here and no
#: independent marker motion: see `sloped/v24_spin.py` and
#: `godot/assets/marble_machine/racers/racer_visual.gd`.
RACERS = v24.RACERS

#: V26 has no course preview, and that is inherited rather than re-decided. The
#: retention numbers behind it are V24's and they are in `sloped/v24.py`: four
#: viewers in five left during the aerial flight over an empty hillside. V25.2's
#: proof cameras flew that hillside again, to validate the world - and they are
#: not footage. See `docs/sloped_race_v26.md`.
PREVIEW = None

#: The finish board flag, carried from V22.1 through V23 and V24 alike: the
#: finish parks up-course of the line, the one place the FINISH board is
#: unreadable, and this copies its letters onto the back face. No collider and
#: no timing is touched.
FINISH_SIGN = v23.FINISH_SIGN

#: What `tools/sloped_v22.py` hands Godot for a V26 render. Four flags, four
#: dimensions, in the order the scene reads them. `--contrast` is absent because
#: V26 takes the race scene's own default, which is the V21 readability pass
#: every edition since V21 has shipped.
SCENE_FLAGS: tuple[str, ...] = (
    FINISH_SIGN,
    f"--environment={ENVIRONMENT}",
    f"--machine={MACHINE}",
    f"--racers={RACERS}",
)

# --- what V26 inherits, by name ---------------------------------------------

#: The edit plan V26 renders. `v24` - the same computed windows, the same
#: slope-1 map, the same three omissions. Not a copy: `build_race_track` above
#: *is* `v24.build_race_track`.
EDIT = v24.EDIT

#: The timeline's owner, for the reports. V26's runtime is V24's runtime because
#: V26's windows are V24's windows.
TIMELINE = "v24"

#: The end card. V24's plate: PURPLE WINS over the winner's own #8E3FD4, with
#: the 6TH -> 1ST comeback line under it.
PAYOFF = v24_payoff.RECOMMENDED

#: The branches this edition was integrated from, for the record and for the
#: test that asserts the sources are the ones the brief named.
SOURCE = {
    "format": "v24-integration",
    "world": "v252-final-world-lookdev",
    "machine": "v23-machine-color-lab",
}

#: Seed 5432's finish order, in finishing position. Not V26's to choose: it is
#: the replay's, it is identical on both source branches, and it is written here
#: so a test can fail loudly if an integration ever moved it.
FINISH_ORDER: tuple[int, ...] = (5, 2, 7, 4, 1, 6, 3, 0)

#: The marble that wins, and the colour the payoff names it by.
WINNER = 5
WINNER_COLOUR = "PURPLE"


def describe() -> str:
    """One line naming all four dimensions, for the render log and the report."""
    preview = "none" if PREVIEW is None else PREVIEW
    return (f"V26: environment={ENVIRONMENT} machine={MACHINE} "
            f"racers={RACERS} edit={EDIT} preview={preview}")
