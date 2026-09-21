"""The canonical run, written down once so a renderer can only replay it.

Phase 2 settled that the analytic solver in `satisfying.tile_escape` is the
source of truth for what happens in a tile-escape run. Phase 3 adds a renderer,
and a renderer is exactly the place where a second, disagreeing copy of the
physics tends to appear: a Godot scene with a `RigidBody2D`, a `move_and_slide`,
or even an honest re-implementation of the same reflection would be a second
simulation, and two simulations of a chaotic billiard diverge. Not "might" -
a convex billiard has a positive Lyapunov exponent, so a difference of one ulp
in the release position is a different arena half within a few seconds.

So this module publishes the run as **data**, and the rule for Phase 3 is that
Godot may read this document and may not compute a trajectory.

## What is in the document, and why each part has to be

- **`flights`** - one record per parabolic arc: `t`, position and velocity at
  its start. This is the trajectory, complete and exact. A renderer asked for
  the ball at time `t` finds the last flight starting at or before `t` and
  evaluates `p + v*dt - 0.5*g*dt^2`. That is a closed form, not an integration,
  so the renderer's frame rate cannot change where the ball is. Render at 24,
  30, 60 or 1000 fps and every frame samples the same curve.
- **`collisions`** - every contact, new or repeat, with the tile it touched and
  the contact point. The renderer uses these for hit feedback; the *repeat*
  ones are here precisely so a renderer can show a bounce without implying
  progress.
- **`activations`** - the new hits alone, in order, as `(time, tile_index)`.
  Strictly redundant against `collisions`, and present anyway, because this is
  the sequence the playback-accuracy test compares against and a test should
  not have to re-derive the thing it is checking.
- **`arena`** - the vertices and every tile's two endpoints, in simulation
  units. The renderer builds its geometry from these numbers rather than
  recomputing `polygon_arena`, so a renderer with a different trigonometric
  convention cannot draw a tile in a place the ball never hit.
- **`digest`** - `TileEscapeRun.state_digest`, the SHA-256 over the raw bytes
  of every collision. A renderer that loads a document can print this, and a
  human comparing a render against a report can tell in one line whether they
  are looking at the same run.

## Floats

Every number is written as a Python float and JSON round-trips a double
exactly - `json.dumps` emits `repr`, which is the shortest string that reads
back as the same double, and Godot's `JSON.parse` reads doubles. So the
document is lossless. `verify_document` asserts it: it re-simulates the seed
and compares the digest of the reloaded document against the fresh run, which
is the only check that would catch a future "round to six decimals to make the
file smaller".

## What this module deliberately does not do

It does not know about pixels, colours, cameras or frame rates. A playback
document is the same for a 30 fps preview and a 60 fps delivery, and that is
what makes "rendering did not influence physics" a statement with content
rather than a hope.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Sequence

from satisfying.tile_arena import Arena
from satisfying.tile_escape import TileEscapeConfig, TileEscapeRun, simulate

__all__ = [
    "PLAYBACK_FORMAT",
    "PlaybackMismatch",
    "arena_document",
    "playback_document",
    "write_playback",
    "read_playback",
    "reload_run",
    "verify_document",
    "position_at",
    "activated_count_at",
    "activation_frames",
]

# Bumped when a field is removed or its meaning changes, never when one is
# added. A renderer checks it and refuses a document it cannot read, because a
# silently-missing field renders a plausible wrong video.
PLAYBACK_FORMAT = 1


class PlaybackMismatch(RuntimeError):
    """A document and the run it claims to describe disagree."""


def _pair(point: Sequence[float]) -> list[float]:
    return [float(point[0]), float(point[1])]


def arena_document(arena: Arena) -> dict[str, Any]:
    """The geometry a renderer needs, in simulation units."""
    return {
        "sides": arena.sides,
        "tiles_per_side": arena.tiles_per_side,
        "total_tiles": arena.total_tiles,
        "circumradius": arena.circumradius,
        "apothem": arena.apothem,
        "orientation": arena.orientation,
        "side_length": arena.side_length,
        "tile_length": arena.tile_length,
        "vertices": [_pair(v) for v in arena.vertices],
        "tiles": [
            {
                "index": tile.index,
                "tile_id": tile.tile_id,
                "side": tile.side,
                "slot": tile.slot,
                "start": _pair(tile.start),
                "end": _pair(tile.end),
                "midpoint": _pair(tile.midpoint),
                "outward_normal": _pair(tile.outward_normal),
                "length": tile.length,
            }
            for tile in arena.tiles
        ],
    }


def playback_document(run: TileEscapeRun) -> dict[str, Any]:
    """Everything a renderer needs, and nothing it could use to re-simulate."""
    activations = sorted(
        (hit.time, hit.tile_index) for hit in run.collisions if hit.is_new
    )
    return {
        "format": PLAYBACK_FORMAT,
        "kind": "category3_tile_escape_playback",
        "seed": run.seed,
        "digest": run.state_digest(),
        "config": run.config.as_dict(),
        "arena": arena_document(run.arena),
        "completed": run.completed,
        "completion_seconds": run.completion_time,
        "end_seconds": run.end_time,
        "stop_reason": run.stop_reason,
        "total_tiles": run.total_tiles,
        "activated_tiles": run.activated_tiles,
        "flights": [
            {
                "t": flight.t_start,
                "p": _pair(flight.position),
                "v": _pair(flight.velocity),
            }
            for flight in run.flights
        ],
        "collisions": [
            {
                "t": hit.time,
                "tile": hit.tile_index,
                "side": hit.side,
                "slot": hit.slot,
                "new": hit.is_new,
                "count": hit.activated_after,
                "contact": _pair(hit.contact),
                "normal_speed": hit.normal_speed,
                "incoming_speed": hit.incoming_speed,
                "graze_ratio": hit.graze_ratio,
            }
            for hit in run.collisions
        ],
        "activations": [
            {"t": t, "tile": index, "count": n + 1}
            for n, (t, index) in enumerate(activations)
        ],
    }


def write_playback(run: TileEscapeRun, path: str) -> str:
    """Write the document, creating the directory. Returns the path."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(playback_document(run), handle)
    return path


def read_playback(path: str) -> dict[str, Any]:
    """Read a document and refuse one this code does not understand."""
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("kind") != "category3_tile_escape_playback":
        raise PlaybackMismatch(f"{path} is not a tile-escape playback document")
    if int(document.get("format", -1)) != PLAYBACK_FORMAT:
        raise PlaybackMismatch(
            f"{path} is playback format {document.get('format')}, this build "
            f"reads {PLAYBACK_FORMAT}"
        )
    return document


def reload_run(document: dict[str, Any]) -> TileEscapeRun:
    """Re-simulate the seed the document names, at the config it records.

    This is the *checking* path, not the rendering path. Nothing in a render
    calls it; `verify_document` does, and so does the test that proves the
    document is lossless.
    """
    from satisfying.tile_arena import polygon_arena

    config = TileEscapeConfig(**document["config"])
    arena_fields = document["arena"]
    arena = polygon_arena(
        sides=int(arena_fields["sides"]),
        tiles_per_side=int(arena_fields["tiles_per_side"]),
        circumradius=float(arena_fields["circumradius"]),
        orientation=float(arena_fields["orientation"]),
    )
    return simulate(int(document["seed"]), config, arena)


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    """Re-simulate and confirm the document still describes that run.

    Returns the comparison rather than a bare bool, because "the digests
    differ" and "the digests agree but the activation order does not" are
    different bugs and a caller writing a report wants to say which.
    """
    fresh = playback_document(reload_run(document))
    document_order = [entry["tile"] for entry in document["activations"]]
    fresh_order = [entry["tile"] for entry in fresh["activations"]]
    document_times = [entry["t"] for entry in document["activations"]]
    fresh_times = [entry["t"] for entry in fresh["activations"]]
    return {
        "seed": document["seed"],
        "digest_matches": document["digest"] == fresh["digest"],
        "activation_order_matches": document_order == fresh_order,
        "activation_times_match_exactly": document_times == fresh_times,
        "completion_matches": (
            document["completion_seconds"] == fresh["completion_seconds"]
        ),
        "collision_count_matches": (
            len(document["collisions"]) == len(fresh["collisions"])
        ),
        "document_digest": document["digest"],
        "fresh_digest": fresh["digest"],
    }


# --------------------------------------------------------------------------
# Evaluation of the document, in the same closed form the renderer must use.
# --------------------------------------------------------------------------


def _flight_index_at(flights: Sequence[dict[str, Any]], t: float) -> int:
    lo, hi = 0, len(flights) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if flights[mid]["t"] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo


def position_at(document: dict[str, Any], t: float) -> tuple[float, float]:
    """The ball at time `t`, from the flights alone.

    The reference implementation of what the renderer does. The playback audit
    asks Godot for the same instants and compares, which is how "Godot did not
    change the trajectory" becomes a number instead of an assurance.
    """
    # The document defines the trajectory on [0, end_seconds] and nowhere else.
    # A run that stopped on completion has no flight after its last contact, so
    # evaluating the final flight past that instant extrapolates the ball
    # straight through the wall - 0.6 s past a completion at 85 wu/s puts it 51
    # world units out, well off a frame 20 units wide, and the first completion
    # still rendered showed a finished arena with no ball in it. Clamping is
    # the honest reading: past the end there is nothing to draw, so the ball
    # holds where the run left it.
    t = min(t, float(document["end_seconds"]))
    flight = document["flights"][_flight_index_at(document["flights"], t)]
    dt = max(0.0, t - flight["t"])
    px, py = flight["p"]
    vx, vy = flight["v"]
    gravity = float(document["config"]["gravity"])
    return (px + vx * dt, py + vy * dt - 0.5 * gravity * dt * dt)


def activated_count_at(document: dict[str, Any], t: float) -> int:
    """How many tiles are lit at time `t`. Activations are sorted, so bisect."""
    activations = document["activations"]
    lo, hi = 0, len(activations)
    while lo < hi:
        mid = (lo + hi) // 2
        if activations[mid]["t"] <= t:
            lo = mid + 1
        else:
            hi = mid
    return lo


def activation_frames(document: dict[str, Any], fps: float) -> list[int]:
    """The first rendered frame on which each activation is visible.

    A frame at index `i` shows the world at `t = i / fps`, so a tile activating
    at `t_a` is lit from the first frame whose time is at or after `t_a`: index
    `ceil(t_a * fps)`. This is exact arithmetic on the canonical times, and it
    is what the Godot audit is compared against - so a renderer that rounded
    the other way, or that advanced its clock by accumulating `delta` instead
    of indexing it, fails rather than producing a video one frame out that
    looks fine.
    """
    frames: list[int] = []
    for entry in document["activations"]:
        exact = entry["t"] * fps
        frame = math.ceil(exact)
        # A time landing exactly on a frame boundary is visible on that frame
        # and `ceil` already gives it; the guard is for the float that sits a
        # few ulp under an integer.
        if abs(exact - round(exact)) < 1.0e-9:
            frame = int(round(exact))
        frames.append(frame)
    return frames
