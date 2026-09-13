"""The environment profile registry, read from Python.

``godot/assets/marble_machine/environment/profiles/*.json`` is the source of
truth for what a themed world looks like, and ``environment_profile.gd`` is one
reader of it. This is the other. Nothing is transcribed between them: the same
files are parsed twice, by the two languages that need them, which is the only
arrangement where a Python tool cannot drift from what Godot builds.

That matters more here than it looks. Three of this project's hardest hours
went into instrument bugs - a confident measurement taken against a stale copy
of what was rendered - and a Python mirror of a GDScript table is exactly that
bug with a schedule. So the rule is: **numbers live in JSON, logic is written
twice, and** ``tests/test_sloped_environment.py`` **checks the two readers
agree field for field on every profile in the registry.**

What this module is for:

    resolve()      the finished profile: inheritance, contrast pass, accent
    validate()     every complaint, as strings; empty means usable
    describe()     a one-line summary, the same sentence the scene prints
    diff()         what one profile changes about another, leaf by leaf
    masses_of()    a backdrop layer's masses, authored or generated

It builds nothing and renders nothing. ``tools/sloped_environment.py`` is the
driver; this is the library under it.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Iterable

__all__ = [
    "PROFILE_ROOT",
    "SHAPE_FIELDS",
    "SECTIONS",
    "TERRAIN_SECTIONS",
    "ids",
    "default_id",
    "load",
    "merge",
    "resolve",
    "validate",
    "describe",
    "diff",
    "masses_of",
    "flatten",
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_ROOT = os.path.join(
    REPO, "godot", "assets", "marble_machine", "environment", "profiles"
)

#: Terrain keys a profile may never set - the arguments to
#: ``course_terrain.height``, which :mod:`sloped.terrain` ports exactly and
#: every production camera is solved against. See GEOMETRY IS NOT THEME in
#: ``environment_profile.gd``.
SHAPE_FIELDS = (
    "top_y", "z_top", "grade", "steps", "left_at", "left_span", "left_rise",
    "gorge_at", "gorge_span", "gorge_depth", "crest_rise", "crest_scale",
    "centre_x", "centre_z", "edge_from", "edge_to", "edge_y", "noise", "pads",
    "cut_depth", "cut_inner", "cut_reach", "cut_index",
    "x_min", "x_max", "z_min", "z_max", "cell",
)

SECTIONS = (
    "id", "title", "family", "summary", "extends",
    "sky", "grade", "fog", "ssao", "ssr", "glow", "lights", "backdrop",
    "terrain", "dressing", "zones", "ravine", "accent", "palette", "contrast",
)

TERRAIN_SECTIONS = ("surfaces", "scatter")

IDENTITY = ("id", "title", "family", "summary")

DEFAULT_ID = "alpine_neon"


def _index() -> dict[str, Any]:
    with open(os.path.join(PROFILE_ROOT, "index.json"), encoding="utf-8") as handle:
        return json.load(handle)


def ids() -> list[str]:
    return [str(name) for name in _index().get("profiles", [])]


def default_id() -> str:
    return str(_index().get("default", DEFAULT_ID))


def load(profile_id: str) -> dict[str, Any]:
    """One profile file, unmerged, with its ``extends`` chain still to follow."""
    path = os.path.join(PROFILE_ROOT, f"{profile_id}.json")
    if not os.path.isfile(path):
        raise KeyError(f"no environment profile {profile_id!r}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Deep merge. A dict recurses, anything else replaces, ``None`` erases.

    ``None`` erasing is what lets a child *remove* an inherited list rather
    than shadow it with an empty one that still reads as authored - it is how
    ``canyon_dusk`` drops the twelve hand-placed alpine masses and takes a
    generated mesa ring in their place.
    """
    out = copy.deepcopy(base)
    for key, value in over.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _chain(profile_id: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = profile_id
    while cursor:
        if cursor in seen:
            raise ValueError(f"environment profile {profile_id!r} extends cyclically")
        seen.add(cursor)
        step = load(cursor)
        chain.insert(0, step)
        parent = step.get("extends")
        cursor = None if parent is None else str(parent)
    return chain


def resolve(profile_id: str = "", contrast: str = "") -> dict[str, Any]:
    """The finished profile: inheritance chain, contrast overlay, accent dial.

    The same three steps in the same order as ``environment_profile.resolve``,
    and the test suite renders both and compares.
    """
    wanted = profile_id or default_id()
    profile: dict[str, Any] = {}
    for step in _chain(wanted):
        profile = merge(profile, step)

    # The child's identity survives its parent's; `merge` has no idea these
    # four fields are not theme values.
    own = load(wanted)
    for field in IDENTITY:
        if field in own:
            profile[field] = own[field]
    profile["extends"] = own.get("extends")

    if contrast:
        overlay = profile.get("contrast", {}).get(contrast)
        if overlay:
            profile = merge(profile, overlay)
    profile["contrast_pass"] = contrast
    profile.pop("contrast", None)
    _apply_accent(profile)
    return profile


def _apply_accent(profile: dict[str, Any]) -> None:
    """One dial over the profile's own lit values.

    Deliberately not a global emissive multiplier. It reaches the zone
    practicals, the course spill and any emissive surface the profile itself
    overrides, and it reaches nothing it cannot see a base value for - a dial
    that silently scaled materials it had never been shown would make two
    profiles with identical numbers render differently.
    """
    gain = float(profile.get("accent", {}).get("intensity", 1.0))
    if gain == 1.0:
        return
    for zone in profile.get("zones", {}).values():
        zone["energy"] = float(zone.get("energy", 1.0)) * gain
    practicals = profile.get("dressing", {}).get("practicals", {})
    for slot in ("spill", "under"):
        if slot in practicals:
            lamp = practicals[slot]
            lamp["energy"] = float(lamp.get("energy", 1.0)) * gain
    for spec in profile.get("palette", {}).values():
        if "energy" in spec:
            spec["energy"] = float(spec["energy"]) * gain


# --- validation -----------------------------------------------------------


def validate(profile: dict[str, Any]) -> list[str]:
    """Every complaint, as strings. Empty means the profile is usable."""
    problems: list[str] = []
    for field in ("id", "title", "summary"):
        if not str(profile.get(field, "")).strip():
            problems.append(f"missing {field}")
    for name in profile:
        if name not in SECTIONS and name != "contrast_pass":
            problems.append(f"unknown section {name!r}")

    for name in profile.get("terrain", {}):
        if name in SHAPE_FIELDS:
            problems.append(
                f"terrain.{name} is landform, not theme"
                " - see GEOMETRY IS NOT THEME"
            )
        elif name not in TERRAIN_SECTIONS:
            problems.append(f"unknown terrain key {name!r}")

    for pass_name, overlay in profile.get("contrast", {}).items():
        for name in overlay.get("terrain", {}):
            if name in SHAPE_FIELDS:
                problems.append(
                    f"contrast.{pass_name}.terrain.{name} is landform, not theme"
                )

    for name, light in profile.get("lights", {}).items():
        if float(light.get("energy", 0.0)) < 0.0:
            problems.append(f"lights.{name}.energy is negative")
    return problems


def describe(profile: dict[str, Any]) -> str:
    """The one-line summary the scene prints, rebuilt from the same fields."""
    backdrop = profile.get("backdrop", {})
    masses = sum(
        len(masses_of(backdrop.get(layer, {})))
        for layer in ("near_range", "mid_range", "far_range")
    )
    rocks = sum(
        int(entry.get("count", 0))
        for entry in profile.get("terrain", {}).get("scatter", [])
    )
    return "%s (%s): %d backdrop masses, %d scattered rocks, accent %.2f" % (
        profile.get("title", "?"),
        profile.get("family", "?"),
        masses,
        rocks,
        float(profile.get("accent", {}).get("intensity", 1.0)),
    )


# --- the mass ring generator ----------------------------------------------


def masses_of(layer: dict[str, Any]) -> list[list[Any]]:
    """A backdrop layer's masses, authored or generated.

    Authored wins, because the alpine ranges were placed by eye against a
    specific camera and no generator reproduces that. A theme with no such
    study sets ``masses: null`` and a ``ring``, and gets a deterministic arc
    with the same five columns - so the builder never learns which it is.
    """
    authored = layer.get("masses")
    if isinstance(authored, list):
        return [list(entry) for entry in authored]
    ring = layer.get("ring")
    if not isinstance(ring, dict):
        return []
    out: list[list[Any]] = []
    for index in range(int(ring.get("count", 0))):
        bearing = float(ring.get("bearing_from", 0.0)) + float(
            ring.get("bearing_step", 0.0)
        ) * index
        radius = float(ring.get("radius", 200.0)) + float(
            ring.get("radius_step", 0.0)
        ) * (index % max(int(ring.get("radius_cycle", 1)), 1))
        height = float(ring.get("height", 100.0)) + float(
            ring.get("height_step", 0.0)
        ) * (index % max(int(ring.get("height_cycle", 1)), 1))
        base = float(ring.get("base", 40.0)) + float(
            ring.get("base_step", 0.0)
        ) * (index % max(int(ring.get("base_cycle", 1)), 1))
        salt = int(ring.get("seed_from", 1)) + int(ring.get("seed_step", 8)) * index
        out.append([bearing % 360.0, radius, height, base, salt])
    return out


# --- reading a profile back -----------------------------------------------


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Every leaf of a profile, as ``dotted.path -> value``.

    What ``diff`` compares and what the contract test hashes. Lists are leaves
    rather than paths: a backdrop range is one authored decision, and a diff
    that reported ``masses.7.2`` would bury the change it is meant to show.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value):
            out.update(flatten(value[key], f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: value}


def diff(left: dict[str, Any], right: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """What ``right`` changes about ``left``, leaf by leaf, in path order."""
    a = flatten(left)
    b = flatten(right)
    out: list[tuple[str, Any, Any]] = []
    for path in sorted(set(a) | set(b)):
        before = a.get(path, "-")
        after = b.get(path, "-")
        if before != after:
            out.append((path, before, after))
    return out
