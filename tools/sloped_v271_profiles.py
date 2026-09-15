"""Write the V27.1 profiles from one place.

    python tools/sloped_v271_profiles.py

Four files, and three of them are diagnostics:

    contained_hall_v271   the corrected stage. One field over `contained_hall`.
    _marker_v271          its depth-band twin, generated from `v27.MARKED`
    _probe_v271           every hall material its own hue, so a bright area in
                          a finish frame can be named
    _probe_v271_pad       the same, with the finish landing pad separated from
                          the deck ring it shares a material with

**`contained_hall` is not touched and must not be.** V27's proofs are quoted in
its report and have to stay reproducible from the profile that produced them;
`tests/test_sloped_v271_contained.py` renders a V27 frame and checks its hash
against this branch's own baseline. A pass that corrects a measurement by
editing the thing it measured has corrected nothing.

## The delta, in full

    world.deck.pads[0].material   hall_deck -> hall_deck_dark

That is the whole of it. `tools/sloped_v271_finish.py --stage survey` is the
argument for why it is the whole of it: at the three finish moments the hall's
background is one bright object and three dark ones, the bright one covers
27.8% of the final-approach frame at luma 51, and it is this slab.

## The two probes, and why there are two

`hall_deck` paints both the radius 88-124 deck ring and the finish bay's
landing pad, so a probe that gives it one hue cannot say which of them is in
shot. `_probe_v271_pad` re-materials the pad alone, and the answer it gives is
the pass's whole finding: at the final approach 27.83 of the 28.55 points of
`hall_deck` are the pad, at the winner 6.39 of 6.41, at the payoff 3.38 of
3.46. The deck ring is very nearly not in the finish at all.
"""

from __future__ import annotations

import copy
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sloped import v27_contained as v27  # noqa: E402
from sloped import v271_finish as v271  # noqa: E402

PROFILE_DIR = os.path.join(PROJECT_ROOT, "godot", "assets", "marble_machine",
                           "environment", "profiles")


def _parent() -> dict:
    with open(os.path.join(PROFILE_DIR, f"{v271.PARENT}.json"),
              encoding="utf-8") as handle:
        return json.load(handle)


# --- the corrected stage ----------------------------------------------------

#: The pad's new material, and why this one.
#:
#: `hall_deck_dark` is already the outer deck ring's key, so the finish landing
#: is now the same graphite as the floor beyond it rather than a lighter plate
#: laid on top of it - which is a reading of the room as well as a value. The
#: alternatives were measured and are in the report: `hall_beam` gives 119.3
#: luma of separation at the final approach and `hall_panel` 117.0, against
#: this one's 121.2, and none of the three costs a tenth of a per cent of black
#: clipping.
PAD_MATERIAL = "hall_deck_dark"


def corrected() -> dict:
    """`contained_hall` with the finish landing pad taken down a value."""
    parent = _parent()
    pads = copy.deepcopy(parent["world"]["deck"]["pads"])
    pads[0]["material"] = PAD_MATERIAL
    return {
        "id": v271.PROFILE,
        "title": "A' - Premium machine hall, finish corrected",
        "family": "contained",
        "summary": (
            "contained_hall with the finish bay's landing pad dropped from "
            "hall_deck to hall_deck_dark. The pad is the one bright surface "
            "behind the finish machine - 27.8% of the final-approach frame at "
            "luma 51 against V26's 20-luma ravine floor - and it is the whole "
            "of the delta: no geometry is added, no material key is new, and "
            "the hall's architecture, radius, rhythm and lighting are V27's "
            "unchanged"
        ),
        "extends": v271.PARENT,
        "world": {"deck": {"pads": pads}},
    }


# --- the diagnostics --------------------------------------------------------


def marker() -> dict:
    """The corrected profile's depth-band twin, on `v27.MARKED`'s own table."""
    palette: dict = {}
    for band, keys in v27.MARKED.items():
        hue = "#%02X%02X%02X" % v27.layer(band).hue
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    return {
        "id": v271.MARKER,
        "title": f"Marker over {v271.PROFILE} (diagnostic)",
        "family": "diagnostic",
        "summary": (
            "%s with every stage surface painted the flat hue of its depth "
            "band, so a render of it can be segmented by depth" % v271.PROFILE
        ),
        "extends": v271.PROFILE,
        "palette": palette,
    }


def probe(separate_pad: bool = False) -> dict:
    """Every hall material its own hue - not its band's.

    The band marker answers "how much of this frame is wall"; this answers
    "which wall". They are different questions and V27 only had an instrument
    for the first, which is why its §19 could name a cause for the finish
    without being able to point at an object.
    """
    palette: dict = {}
    for key, hue in v271.SURFACES.items():
        palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    for key, hue in v271.SURFACE_LIGHTS.items():
        # A lit strip carries its colour in `emission`; an albedo row would
        # leave it exactly as bright and exactly as warm as it was.
        palette[key] = {"emission": hue, "energy": 1.0}
    for key in v27.MARKED["terrain"]:
        palette[key] = {"albedo": v271.SURFACE_GROUND, "unshaded": True,
                        "no_fog": True}
    doc = {
        "id": "_probe_v271" + ("_pad" if separate_pad else ""),
        "title": "Probe over %s%s (diagnostic)" % (
            v271.PARENT, ", finish pad separated" if separate_pad else ""),
        "family": "diagnostic",
        "summary": (
            "contained_hall with every hall material painted its own flat hue "
            "rather than its depth band's, so a bright area in a finish frame "
            "can be named instead of attributed"
            + (". The finish landing pad is re-materialled so it can be told "
               "apart from the deck ring it otherwise shares a key with"
               if separate_pad else "")
        ),
        "extends": v271.PARENT,
        "palette": palette,
    }
    if separate_pad:
        pads = copy.deepcopy(_parent()["world"]["deck"]["pads"])
        pads[0]["material"] = "hall_glass"
        doc["world"] = {"deck": {"pads": pads}}
    return doc


def profiles() -> list[dict]:
    return [corrected(), marker(), probe(False), probe(True)]


def write() -> list[str]:
    written: list[str] = []
    listed = [one["id"] for one in profiles()]
    for profile in profiles():
        path = os.path.join(PROFILE_DIR, f"{profile['id']}.json")
        text = json.dumps(profile, indent=2) + "\n"
        old = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                old = handle.read()
        if old != text:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            written.append(path)
    index_path = os.path.join(PROFILE_DIR, "index.json")
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    changed = False
    for one in listed:
        if one not in index["profiles"]:
            index["profiles"].append(one)
            changed = True
    if changed:
        with open(index_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(index, indent=2) + "\n")
        written.append(index_path)
    return written


def main() -> int:
    written = write()
    if not written:
        print("profiles are up to date")
    for path in written:
        print("wrote " + os.path.relpath(path, PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
