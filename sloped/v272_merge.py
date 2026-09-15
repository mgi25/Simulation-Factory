"""V27.2: the merge correction, and the instrument that names the surface.

V27.1 closed the finish and its §12.3 named what it left open:

    "The merge is now the weakest moment in the film, at 98.3 against V26's
    120.3 - a 22-luma gap, the largest of the twelve, and three times the
    finish's. It is outside this pass's scope and it is where a V27.2 should
    start."

This is that pass, and it is deliberately the same shape as V27.1's: find the
image-space region, name the object that makes it, prove the naming with a
controlled probe, then change one value. Nothing here redesigns the hall.

## 1  The three merge frames, and why the pass needed two new ones

V27 has one merge moment - `merge`, output 15.267 - and one frame cannot say
whether a weakness is the shot or the section. The merge is a **transition**:
the routes converge under the branches camera, the merge cut runs 0.483 s, and
the final cut picks the machine up again. So this pass measures three:

    merge_approach   14.900   the branches cut, routes converging
    merge            15.267   V27's own moment, unchanged
    post_merge       15.800   the final cut, just after the rejoin

The two new ones are derived from the delivered track's own edit map rather
than chosen - see :data:`EXTRA` - and each sits at least 0.18 s inside the cut
that owns it, because a sample on a cut boundary is a sample of whichever of
two shots the renderer resolved first.

## 2  The instrument is V27.1's, unchanged, and that is the point

:mod:`sloped.v271_finish` replaced V27's hue-agreement segmentation with an
**occlusion** test - a pixel is machine where removing the machine changes it -
after V27's own number turned out to be an artefact of counting the cream
finish chute as background. Nothing in this pass re-derives that. It imports
:func:`sloped.v271_finish.machine_mask`, :func:`~sloped.v271_finish.collar_pair`
and :func:`~sloped.v271_finish.surface_masks` and uses them as they are, so a
V27.2 number and a V27.1 number are the same measurement.

What this module adds is *where* the instrument is pointed, and one honesty
check V27.1 did not need: :data:`LIST_A` and :data:`LIST_B`.

## 3  Two `--at` lists, and the check between them

V27 found that a still is only comparable with a still asked for in the same
`--at` list, because the renderer accumulates between samples inside one
process. This pass needs two lists - the twelve V27 moments, so every
regression guard is directly comparable with V27.1's published table, and the
brief's six proof frames, so the merge boards are internally consistent - and
`merge`, `final_approach`, `winner` and `payoff` appear in both.

That overlap is not a duplication to be tidied away. It is the only direct
measurement of how much the accumulation actually moves a number on this
machine, and `tools/sloped_v272_merge.py --stage listcheck` reports it. A pass
that quotes a figure from one list beside a figure from another without ever
having measured the difference is quoting two rulers.

## 4  Naming an object rather than a material

V27.1's surface probe paints every hall material its own flat hue, which
answers "which material" and not "which object" - and at the finish those were
different questions, because `hall_deck` paints both the deck ring and the
finish landing pad. It needed a second probe, `_probe_v271_pad`, to tell them
apart.

The merge has the same problem four times over: `hall_panel_dark` is the lower
wall, the merge bay's own backing *and* the fork's wings; `hall_deck_dark` is
the outer deck ring and, since V27.1, the finish pad. So :data:`ISOLATES`
generalises that second probe: one probe per candidate object, each
re-materialling exactly that object to `hall_grate` - the one key in the hall
family that `contained_hall` builds nothing from - so the hue's cover in the
probe frame *is* that object's cover, with no attribution step at all.

## 5  Nothing is left behind

The brief's standing instruction is that no more probe artefacts may be left in
the profile registry. Every diagnostic this pass builds - the marker and all of
the isolates - is written, rendered and deleted inside one context manager, and
`index.json` is restored byte for byte. See
:func:`tools.sloped_v272_profiles.temporary`. The only file this pass leaves in
the registry is `contained_hall_v272` itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sloped import v271_finish as v271  # noqa: F401  (the instrument's home)
from sloped import v27_contained as v27
from sloped.v27_contained import (  # noqa: F401  (re-exported: V27's frames)
    CENTRE,
    FPS,
    HEIGHT,
    Moment,
    SEED,
    WIDTH,
    frames_of,
    segment,
    write_json,
)
from sloped.v271_finish import (  # noqa: F401  (re-exported: V27.1's instrument)
    DIFF_FLOOR,
    background_mask,
    collar,
    collar_pair,
    frame_at,
    in_frame,
    luma,
    machine_mask,
    polar,
    separation,
    surface_masks,
)

__all__ = [
    "CLIP",
    "CONTROL",
    "EXTRA",
    "GRANDPARENT",
    "ISOLATES",
    "ISOLATE_KEY",
    "Isolate",
    "LIST_A",
    "LIST_B",
    "MARKER",
    "MERGE",
    "MOMENTS",
    "PARENT",
    "PROBE",
    "PROFILE",
    "PROOF_FRAMES",
    "REGRESSION",
    "TARGET",
    "TARGET_IDEAL",
    "V271_PUBLISHED",
    "clip_seconds",
    "isolate",
    "isolate_id",
    "moment",
    "seconds_of",
]

#: The profile this pass produces, the two it inherits from, and the control.
#:
#: `contained_hall` and `contained_hall_v271` are **not** overwritten. V27's
#: proofs and V27.1's proofs are quoted in their own reports and have to stay
#: reproducible from the profiles that produced them; the test module renders a
#: frame of each and compares hashes to say so.
PROFILE = "contained_hall_v272"
PARENT = "contained_hall_v271"
GRANDPARENT = "contained_hall"
CONTROL = "aurora_valley_v26"

#: The corrected profile's depth-band twin. **Ephemeral**: written for a render
#: and deleted after it, for the reason the module header gives.
MARKER = "_marker_v272"

#: The base surface probe - every hall material its own flat hue, over the
#: parent, so a bright region can be named by material. Ephemeral.
PROBE = "_probe_v272"

#: The material every isolate probe re-paints its one object with.
#:
#: `hall_grate` is the only key in `lab_palette`'s hall family that
#: `contained_hall` builds nothing from, at any radius, in any band. So in an
#: isolate probe its cover is exactly the cover of the one object that was
#: re-materialled, and nothing has to be subtracted or attributed.
ISOLATE_KEY = "hall_grate"


# --- the frames -------------------------------------------------------------

#: The two moments V27 does not have, as **output** seconds on V24's edit.
#:
#: Derived, not chosen. The delivered track's edit map is
#:
#:     branches   out 13.400-15.083   replay 16.733-18.417
#:     merge      out 15.083-15.567   replay 18.417-18.900
#:     final      out 15.567-20.117   replay 18.900-23.450
#:
#: so `merge_approach` is 0.183 s before the merge cut opens and `post_merge`
#: is 0.233 s after it closes, and `replay` is the cut's own replay start plus
#: the offset into it. `tests/test_sloped_v272_contained.py` re-derives both
#: from the delivered file and fails if a boundary ever moves.
#:
#: **Why not on the boundary.** V22.1 found that the frame at a cut boundary
#: can be either shot's, because two cuts claim the same output second and the
#: renderer resolves whichever it reaches first. A sample there measures the
#: edit rather than the picture.
EXTRA: tuple[Moment, ...] = (
    Moment("merge_approach", 14.900, 18.233334, "9a  Merge approach",
           "the last of the branches cut: two routes converging, the merge "
           "apron ahead and the hall's floor filling the lower half"),
    Moment("post_merge", 15.800, 19.133334, "9c  Post-merge",
           "the final cut has picked the pack up again, one route, still "
           "over the merge's own architecture"),
)

#: Every moment this pass can measure: V27's twelve plus the two above, in the
#: order the film plays them.
MOMENTS: tuple[Moment, ...] = tuple(
    sorted(v27.MOMENTS + EXTRA, key=lambda one: one.second))

#: The three the pass is judged on.
MERGE: tuple[str, ...] = ("merge_approach", "merge", "post_merge")

#: The moments that may not regress, and what each one guards.
#:
#: `frame0` is the hook and is expected to be **byte-identical**; the rest are
#: expected not to fall. `obstacle` and `fork_approach`/`split`/`branch` are
#: the brief's obstacle and fork guards.
REGRESSION: tuple[tuple[str, str], ...] = (
    ("frame0", "hook - byte-identical, or the pass has reached the opening"),
    ("mixer", "hook - the rotor, still inside the start"),
    ("release", "hook - the trapdoor"),
    ("descent", "the first open shot"),
    ("obstacle", "obstacle guard"),
    ("fork_approach", "fork guard - the gate coming up"),
    ("split", "fork guard - the choice itself"),
    ("branch", "fork guard - two routes over open air"),
    ("final_approach", "finish guard - V27.1's own correction"),
    ("winner", "finish guard - the crossing"),
    ("payoff", "finish guard - the card"),
)

#: The twelve V27 moments, rendered as one `--at` list so every number this
#: pass prints beside V27.1's published table was taken the way V27.1 took it.
LIST_A: tuple[float, ...] = v27.seconds()

#: The brief's six proof frames, as their own `--at` list.
#:
#: Four of the six are also in :data:`LIST_A`. That is deliberate - see the
#: module header's §3 - and `--stage listcheck` measures what the duplication
#: costs rather than assuming it costs nothing.
PROOF_FRAMES: tuple[str, ...] = (
    "merge_approach", "merge", "post_merge",
    "final_approach", "winner", "payoff",
)


def moment(key: str) -> Moment:
    for entry in MOMENTS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V27.2 moment named {key!r}")


def seconds_of(keys: Sequence[str]) -> tuple[float, ...]:
    return tuple(moment(key).second for key in keys)


LIST_B: tuple[float, ...] = seconds_of(PROOF_FRAMES)


# --- the target -------------------------------------------------------------

#: The brief's bar for machine-to-background separation at the merge, in luma,
#: and the band it would rather land in. V27.1 measured 98.3 and V26 120.3.
TARGET = 110.0
TARGET_IDEAL = (115.0, 120.0)

#: What V27.1 published at the twelve, through the corrected instrument, so the
#: report can put the three worlds side by side without the reader opening the
#: old document. `docs/validation/sloped_race_v1/v271_contained/measures.txt`.
V271_PUBLISHED: dict[str, dict[str, float]] = {
    "frame0": {"v26": 119.5, "v27": 117.0, "v271": 117.0},
    "mixer": {"v26": 107.1, "v27": 114.0, "v271": 114.0},
    "release": {"v26": 120.3, "v27": 124.7, "v271": 124.7},
    "descent": {"v26": 135.0, "v27": 131.0, "v271": 131.0},
    "obstacle": {"v26": 106.2, "v27": 107.8, "v271": 108.8},
    "fork_approach": {"v26": 103.2, "v27": 97.1, "v271": 97.1},
    "split": {"v26": 111.6, "v27": 103.3, "v271": 103.5},
    "branch": {"v26": 116.3, "v27": 107.6, "v271": 109.6},
    "merge": {"v26": 120.3, "v27": 95.9, "v271": 98.3},
    "final_approach": {"v26": 128.4, "v27": 112.0, "v271": 121.2},
    "winner": {"v26": 90.9, "v27": 96.4, "v271": 99.0},
    "payoff": {"v26": 85.3, "v27": 100.1, "v271": 101.3},
}


# --- naming an object rather than a material --------------------------------


@dataclass(frozen=True)
class Isolate:
    """One candidate object, and the profile edit that separates it.

    `path` is where the object's material lives in the resolved profile, as a
    sequence of dict keys and list indices; `title` is what the report calls
    it. The probe generator walks `path`, writes :data:`ISOLATE_KEY` there, and
    nothing else about the profile changes - so the probe is the base probe
    plus one leaf, and the hue's cover is the object's cover.
    """

    key: str
    title: str
    path: tuple[Any, ...]
    material: str
    why: str


#: Every hall object a merge camera could plausibly be looking at, with the one
#: leaf that re-materials it.
#:
#: The list is the candidates, not the answer. It exists so the answer is
#: *measured* - `--stage isolate` renders every one of these and prints their
#: covers side by side - rather than argued from the profile. Five of the eight
#: share `hall_panel_dark` or `hall_deck_dark` with another entry, which is
#: exactly why a material probe could not settle it.
ISOLATES: tuple[Isolate, ...] = (
    Isolate("deck_ring_inner", "deck ring 0, radius 88-124",
            ("world", "deck", "rings", 0, "material"), "hall_deck",
            "the chamber floor the course is set into: the largest single "
            "plate in the room"),
    Isolate("deck_ring_outer", "deck ring 1, radius 122-154",
            ("world", "deck", "rings", 1, "material"), "hall_deck_dark",
            "the outer service level, beyond the wall's foot"),
    Isolate("finish_pad", "the finish landing pad",
            ("world", "deck", "pads", 0, "material"), "hall_deck_dark",
            "V27.1's own correction, which eight of twelve cameras see"),
    Isolate("merge_backing", "the merge bay's backing slab",
            ("world", "bays", "sites", "merge", "material"), "hall_panel_dark",
            "the 46 x 46 slab standing behind the rejoin"),
    Isolate("wall_lower", "the lower wall, radius 92",
            ("world", "shell", "bands", 2, "material"), "hall_panel_dark",
            "the 24-segment band carrying the obstacle's bays; V27.1 §12.2 "
            "named it as the finish's remaining residual"),
    Isolate("wall_drum", "the main drum, radius 122",
            ("world", "shell", "bands", 0, "material"), "hall_panel",
            "the enclosure proper, behind everything"),
    Isolate("wall_near", "the near wall behind the start, radius 90",
            ("world", "shell", "bands", 3, "material"), "hall_panel",
            "six tall segments on the start's own side of the room"),
    Isolate("split_wings", "the fork portal's wings",
            ("world", "bays", "sites", "split", "wing", "material"),
            "hall_panel_dark",
            "two panels splayed at the angle the routes diverge at, which the "
            "merge camera looks back along"),
)


def isolate(key: str) -> Isolate:
    for entry in ISOLATES:
        if entry.key == key:
            return entry
    raise KeyError(f"no V27.2 isolate named {key!r}")


def isolate_id(key: str) -> str:
    """The ephemeral profile name for one isolate probe."""
    return f"_probe_v272_{key}"


# --- the clip ---------------------------------------------------------------

#: The motion clip the brief asks for: branch, merge, post-merge, in one shot
#: list. Output seconds.
#:
#: It starts 0.05 s after the branches cut opens rather than on it, for the
#: boundary reason :data:`EXTRA` gives, and ends 0.53 s into the final cut so
#: the rejoin is *followed* rather than cut away from.
CLIP = (13.450, 16.100)


def clip_seconds(fps: int = FPS) -> tuple[float, ...]:
    start, end = CLIP
    count = int(round((end - start) * fps))
    return tuple(round(start + index / float(fps), 6) for index in range(count))
