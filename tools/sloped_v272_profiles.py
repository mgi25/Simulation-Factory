"""Write the V27.2 profile, and lend the diagnostics that name the surface.

    python tools/sloped_v272_profiles.py

**One file is written and committed**: `contained_hall_v272`. Everything else
this pass needs to take a measurement - a depth-band marker and ten surface
probes - is built, rendered and deleted inside :func:`temporary`, and
`index.json` is restored byte for byte afterwards.

## Why the diagnostics are ephemeral

V27.1 left `_marker_v271`, `_probe_v271` and `_probe_v271_pad` permanently in
the registry, and the brief for this pass asks that no more probe artefacts
join them. That is the right call for a reason beyond tidiness: a probe is a
*question*, not a theme, and a registry that carries one profile of art per ten
profiles of instrumentation stops being a list of what the show can look like.

Reproducibility does not depend on the files surviving, because the generator
is deterministic, committed, and tested: `tests/test_sloped_v272_contained.py`
regenerates every diagnostic in memory and checks its shape, and the render
stages rebuild them on demand. What would *not* be reproducible is a probe that
had been hand-edited after it was generated, which is exactly the artefact this
arrangement cannot produce.

## Why an isolate probe rather than a second material probe

`hall_panel_dark` paints the lower wall, the merge bay's backing and the fork's
wings; `hall_deck_dark` paints the outer deck ring and, since V27.1, the finish
pad. A probe that gives each *material* a hue therefore cannot answer "which
object", and at the merge that is the only question worth asking.

So each isolate probe re-paints exactly one object with `hall_grate` - the one
key in `lab_palette`'s hall family that `contained_hall` builds nothing from -
and leaves every other surface on the base probe's own hue. The grate hue's
cover in that frame *is* that object's cover. No attribution, no subtraction,
and no hue shared with the machine, which is the failure mode V27.1 §3.1 hit
when it painted `hall_trim` white.

## A list override is a whole list

`environment_profile.merge` recurses into dictionaries and **replaces** arrays.
So an override that wants to change `world.shell.bands[2].material` has to
carry all four bands, not one. :func:`_override` does that by copying the list
out of the *resolved* parent - never by hand - so a probe cannot silently drop
a band the profile it is probing actually has.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
from typing import Any, Iterator, Sequence

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sloped import environment as env  # noqa: E402
from sloped import v27_contained as v27  # noqa: E402
from sloped import v271_finish as v271  # noqa: E402
from sloped import v272_merge as v272  # noqa: E402

PROFILE_DIR = env.PROFILE_ROOT
INDEX_PATH = os.path.join(PROFILE_DIR, "index.json")


def _path_of(profile_id: str) -> str:
    return os.path.join(PROFILE_DIR, f"{profile_id}.json")


def _text(document: dict) -> str:
    return json.dumps(document, indent=2) + "\n"


# --- the shipped profile ----------------------------------------------------

#: The delta, as a path into the profile and the value to write there.
#:
#: Measured, not chosen, and it is not the field the brief expected.
#:
#: `--stage isolate` names the object: `hall_panel_dark` is 28.5% of the merge
#: background at luma 47.7, against a landform at 25.5 - the merge bay's own
#: backing slab and the lower wall at radius 92, which share the key. But a
#: value ladder on that material barely moved it: cutting the albedo by 56 per
#: cent moved the surface 6 luma, because a black, un-emissive `hall_panel_dark`
#: still renders at 31 of its 46.
#:
#: The 31 is a **specular lobe**. `lab_palette._matte` sets albedo, metallic and
#: roughness and leaves `metallic_specular` at StandardMaterial3D's default
#: 0.5, and at roughness 0.88 that lobe is broad enough to lay an even sheen
#: across the whole surface from all five of the rig's directional lights. It
#: is a **flat lift and not a highlight**: the wall's own 5th-to-95th
#: percentile spread is 0.8 luma with the lobe and 0.8 luma without it, so
#: removing it costs no modelling at all. `hall_rib`'s lobe, by contrast,
#: spreads 27.4 luma across the surface - that one is the vertical highlight
#: band the enclosure is read for, and it is not touched.
#:
#: So the delta is one leaf, and the leaf is a reflectance rather than a value.
#: The report's §4 is the ladder that chose 0.06 over 0.00.
DELTA_PATH: tuple[Any, ...] = ("palette", "hall_panel_dark", "specular")
DELTA_VALUE = 0.06

#: What the parent has there: **nothing**. `contained_hall`'s `hall_panel_dark`
#: row never named `specular`, so the 0.5 it was running at is
#: `StandardMaterial3D`'s default rather than an authored decision - which is
#: why no earlier pass had a field to look at. The test module asserts the
#: parent's resolved row has no `specular` key and the child's is exactly this.
DELTA_FROM = None
DELTA_DEFAULT = 0.5

#: One sentence, for the profile's own `summary` field.
DELTA_SUMMARY = (
    "contained_hall_v271 with one leaf added: hall_panel_dark's specular, "
    "which no profile had ever named, taken from StandardMaterial3D's default "
    "0.5 to 0.06. That material is the merge bay's backing slab and the lower "
    "wall at radius 92 - 28.5% of the merge background at luma 47.7 - and 31 "
    "of those 47 luma are a specular lobe so broad at roughness 0.88 that it "
    "lays an even sheen over the whole surface. It carries no form: the wall's "
    "own luma spread is 0.8 either way. No geometry, no new material key, no "
    "value change, no light, no grade, no camera, and the depth-band marker "
    "renders byte-identically because an unshaded marker surface has no "
    "specular response to change"
)


def corrected() -> dict:
    """`contained_hall_v271` with one reflectance taken down.

    A palette row is a dictionary, so `environment_profile.merge` recurses into
    it and this override carries the single field. Everything else about
    `hall_panel_dark` - its albedo, its roughness, its soft light and its
    lifted black point - is inherited unchanged, and the test module resolves
    both profiles and diffs every leaf to say so.
    """
    parent = env.resolve(v272.PARENT)
    return {
        "id": v272.PROFILE,
        "title": "A'' - Premium machine hall, merge corrected",
        "family": "contained",
        "summary": DELTA_SUMMARY,
        "extends": v272.PARENT,
        **_override(parent, DELTA_PATH, DELTA_VALUE),
    }


# --- the diagnostics --------------------------------------------------------


def _override(resolved: dict, path: Sequence[Any], value: Any) -> dict:
    """The smallest override document that writes `value` at `path`.

    Dictionaries merge, so a chain of dictionary keys can be emitted as a chain
    of one-key dictionaries. An **array does not merge** - it replaces - so the
    first integer in the path forces the whole enclosing list to be copied out
    of `resolved` and re-emitted with that one element edited.
    """
    for step, key in enumerate(path):
        if isinstance(key, int):
            head, tail = path[:step], path[step + 1:]
            source: Any = resolved
            for part in head:
                source = source[part]
            if not isinstance(source, list):
                raise TypeError(f"{'.'.join(map(str, head))} is not a list")
            listed = copy.deepcopy(source)
            cursor: Any = listed[key]
            for part in tail[:-1]:
                cursor = cursor[part]
            cursor[tail[-1]] = value
            out: Any = listed
            for part in reversed(head):
                out = {part: out}
            return out
    out = value
    for part in reversed(list(path)):
        out = {part: out}
    return out


def marker(over: str = v272.PROFILE) -> dict:
    """A depth-band twin of `over`, on `v27.MARKED`'s own table.

    Generated rather than aliased onto `_marker_v271`, for the reason V27.1
    gave about its own: an alias is a claim that two profiles paint the same
    bands and a render is a proof of it. `--stage listcheck` renders both and
    compares hashes.
    """
    palette: dict = {}
    for band, keys in v27.MARKED.items():
        hue = "#%02X%02X%02X" % v27.layer(band).hue
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    return {
        "id": v272.MARKER,
        "title": f"Marker over {over} (diagnostic, ephemeral)",
        "family": "diagnostic",
        "summary": (
            "%s with every stage surface painted the flat hue of its depth "
            "band, so a render of it can be segmented by depth" % over
        ),
        "extends": over,
        "palette": palette,
    }


def _probe_palette() -> dict:
    palette: dict = {}
    for key, hue in v271.SURFACES.items():
        palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    palette[v272.ISOLATE_KEY] = {"albedo": ISOLATE_HUE, "unshaded": True,
                                 "no_fog": True}
    for key, hue in v271.SURFACE_LIGHTS.items():
        # A lit strip carries its colour in `emission`; an albedo row would
        # leave it exactly as bright and exactly as warm as it was.
        palette[key] = {"emission": hue, "energy": 1.0}
    for key in v27.MARKED["terrain"]:
        palette[key] = {"albedo": v271.SURFACE_GROUND, "unshaded": True,
                        "no_fog": True}
    return palette


#: The isolate hue. At least 114 units from every hue in `v271.SURFACES`, from
#: the ground's grey and from both lit strips - checked in
#: `tests/test_sloped_v272_contained.py`, because a probe whose hues collide is
#: the instrument bug V27.1 hit twice and this pass hit once more.
#:
#: **The mask does not depend on it**, because `_isolate_mask` differences two
#: probes rather than looking for a colour. It is kept far from its neighbours
#: anyway, so the base probe's material classifier is unaffected and so a
#: future reader who does reach for the hue is not handed a trap. The first
#: value here was `#00FF80`, 64 units from `hall_panel`'s `#00FF40`, which is
#: exactly that trap.
#:
#: Deliberately not white, which is the most distant choice on paper: white is
#: the machine's own pearl and the finish chute's cream, and V27.1 §3.1 is what
#: comes of handing a classifier the one hue the machine also wears.
ISOLATE_HUE = "#00A0A0"


def probe(over: str = v272.PARENT) -> dict:
    """Every hall material its own hue - not its band's."""
    return {
        "id": v272.PROBE,
        "title": f"Probe over {over} (diagnostic, ephemeral)",
        "family": "diagnostic",
        "summary": (
            "%s with every hall material painted its own flat hue rather than "
            "its depth band's, so a bright area in a merge frame can be named "
            "instead of attributed" % over
        ),
        "extends": over,
        "palette": _probe_palette(),
    }


def isolate_probe(key: str, over: str = v272.PARENT) -> dict:
    """The base probe with exactly one object re-materialled to `hall_grate`."""
    one = v272.isolate(key)
    resolved = env.resolve(over)
    found = resolved
    for part in one.path:
        found = found[part]
    if found != one.material:
        raise ValueError(
            f"isolate {key}: {'.'.join(map(str, one.path))} is {found!r}, "
            f"the table says {one.material!r}")
    document = {
        "id": v272.isolate_id(key),
        "title": f"Probe over {over}, {one.title} isolated (ephemeral)",
        "family": "diagnostic",
        "summary": (
            "the V27.2 surface probe with %s re-materialled to %s, the one "
            "hall key contained_hall builds nothing from, so the isolate hue's "
            "cover is that object's cover exactly" % (one.title,
                                                      v272.ISOLATE_KEY)
        ),
        "extends": over,
        "palette": _probe_palette(),
    }
    document.update(_override(resolved, one.path, v272.ISOLATE_KEY))
    return document


def diagnostics(over: str = v272.PARENT, with_marker: str | None = None) -> list[dict]:
    """Every ephemeral profile, in one list."""
    out = [probe(over)]
    out += [isolate_probe(one.key, over) for one in v272.ISOLATES]
    if with_marker:
        out.append(marker(with_marker))
    return out


# --- writing, and un-writing ------------------------------------------------


def _read_index() -> bytes:
    with open(INDEX_PATH, "rb") as handle:
        return handle.read()


def _write_index(raw: bytes) -> None:
    with open(INDEX_PATH, "wb") as handle:
        handle.write(raw)


@contextlib.contextmanager
def temporary(profiles: Sequence[dict]) -> Iterator[list[str]]:
    """Register `profiles`, yield their ids, then remove every trace.

    `index.json` is restored from the bytes it had on entry rather than by
    removing the ids that were added, so a run that is interrupted between the
    two writes cannot leave the file reordered.

    **A profile whose file already exists is refused**, not overwritten. That
    is the guard that stops an exit path from deleting a committed profile: the
    only files this removes are files it created in the same block.
    """
    original = _read_index()
    written: list[str] = []
    try:
        for document in profiles:
            path = _path_of(str(document["id"]))
            if os.path.exists(path):
                raise FileExistsError(
                    f"{path} already exists; a temporary profile may not "
                    f"shadow a committed one")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(_text(document))
            written.append(path)
        index = json.loads(original.decode("utf-8"))
        for document in profiles:
            if document["id"] not in index["profiles"]:
                index["profiles"].append(document["id"])
        with open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(index, indent=2) + "\n")
        yield [str(one["id"]) for one in profiles]
    finally:
        _write_index(original)
        for path in written:
            if os.path.isfile(path):
                os.remove(path)


def leftovers() -> list[str]:
    """Any V27.2 diagnostic still on disk or still in the index.

    Empty is the only acceptable answer and the test module asserts it.
    """
    listed = set(json.loads(_read_index().decode("utf-8"))["profiles"])
    names = [v272.PROBE, v272.MARKER] + [v272.isolate_id(one.key)
                                         for one in v272.ISOLATES]
    out = []
    for name in names:
        if os.path.isfile(_path_of(name)):
            out.append(f"{name}.json on disk")
        if name in listed:
            out.append(f"{name} in index.json")
    return out


def write() -> list[str]:
    """Write the one committed profile, and register it."""
    written: list[str] = []
    document = corrected()
    path = _path_of(str(document["id"]))
    text = _text(document)
    old = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            old = handle.read()
    if old != text:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written.append(path)
    index = json.loads(_read_index().decode("utf-8"))
    if document["id"] not in index["profiles"]:
        index["profiles"].append(document["id"])
        with open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(index, indent=2) + "\n")
        written.append(INDEX_PATH)
    return written


def main() -> int:
    stale = leftovers()
    for one in stale:
        print("! leftover diagnostic: " + one)
    written = write()
    if not written:
        print("profiles are up to date")
    for path in written:
        print("wrote " + os.path.relpath(path, PROJECT_ROOT))
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
