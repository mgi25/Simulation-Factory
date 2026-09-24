"""The canonical Test #2 run, written down once so a consumer can only replay it.

Phase 2A will build the visuals and Phase 2B the audio, in parallel, from this
document and nothing else. The rule those phases inherit is the one Test #1
settled and this module makes enforceable:

    a consumer of this document may read a trajectory and may not compute one.

That is not a style preference. A rotating-polygon billiard has a positive
Lyapunov exponent - `satisfying.shell_arena` sets out why the shells are
polygons precisely so that it does - and a second copy of the physics in a
Godot scene or a synthesiser, however honest, diverges from this one within a
few seconds. There would then be two answers to "did the ball escape" and no
way to tell which the audio was scored against.

## What is in the document, and why each part has to be

- **`flights`** - one record per straight-line arc: `t`, position and velocity
  at its start. Gravity is zero and speed is constant, so this *is* the
  trajectory, complete and exact. A renderer asked for the ball at time `t`
  finds the last flight starting at or before `t` and evaluates `p + v*dt`.
  Closed form, so the renderer's frame rate cannot move the ball.
- **`shells`** - radius, panel count, thickness, initial angle, angular
  velocity and the slots that start open, per shell. A consumer places a panel
  by rotating the shell to `theta0 + omega*t`; it does not re-derive anything
  from the seed. The shells carry their own geometry so that a renderer with a
  different trigonometric convention cannot draw a panel where the ball never
  hit one.
- **`panel_states`** - every panel that broke, with the time it broke. A
  renderer replaying `t` draws a panel if it started closed and has not broken
  by `t`; that is the whole rule, and it is why `panel_break` events do not
  have to be replayed in order to get the geometry right.
- **`events`** - the full stream, in time order, exactly as
  `satisfying.shell_escape.EVENT_SCHEMA` defines it. This is what the audio
  branch scores and what the visual branch cues from.
- **`summary`** - outcome, duration, counts. Redundant against the events on
  purpose: a test that checks a metric should not have to re-derive the metric
  it is checking.
- **`digest`** - `ShellEscapeRun.state_digest`, the SHA-256 over the raw bytes
  of every collision, break and crossing. A render and a report that print the
  same digest are the same run; two that differ are not, however similar the
  numbers look.

## Floats

Every number is a Python float and JSON round-trips a double exactly -
`json.dumps` emits `repr`, the shortest string that reads back as the same
double, and Godot's `JSON.parse` reads doubles. So the document is lossless.
`verify_document` asserts it by re-simulating the seed and comparing digests,
which is the only check that would catch a future "round to six decimals to
make the file smaller".

## What this module deliberately does not do

It knows nothing about pixels, colours, cameras, frame rates, pitches or
instruments. A playback document is the same for a 30 fps preview and a 60 fps
delivery, and the same for a piano and a marimba - which is what makes
"rendering did not influence physics" a statement with content rather than a
hope.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from satisfying.shell_escape import (
    DEFAULT_CONFIG,
    EVENT_SCHEMA,
    SCHEMA_VERSION,
    ShellEscapeConfig,
    ShellEscapeRun,
    simulate,
)

__all__ = [
    "DOCUMENT_VERSION",
    "playback_document",
    "write_playback",
    "read_playback",
    "verify_document",
    "position_at",
    "region_at",
    "panel_closed_at",
    "document_digest",
]

# The document format. Distinct from `SCHEMA_VERSION`, which versions the event
# stream: a new top-level key here is not a change to what an event means.
DOCUMENT_VERSION = "category3-test2-shell-escape-playback/1.0.0"


def _pair(values: Sequence[float]) -> list[float]:
    return [float(values[0]), float(values[1])]


def _event_document(run: ShellEscapeRun) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in run.events:
        record: dict[str, Any] = {"kind": ev.kind, "t": float(ev.t)}
        for name in EVENT_SCHEMA[ev.kind]:
            value = ev.data[name]
            record[name] = _pair(value) if isinstance(value, tuple) else value
        out.append(record)
    return out


def _panel_states(run: ShellEscapeRun) -> list[dict[str, Any]]:
    """Which panels broke and when. Openings are in the shell record instead."""
    broken: list[dict[str, Any]] = []
    for ev in run.events:
        if ev.kind == "panel_break":
            broken.append(
                {
                    "shell_id": ev.data["shell_id"],
                    "panel_id": ev.data["panel_id"],
                    "t": float(ev.t),
                }
            )
    return broken


def playback_document(run: ShellEscapeRun) -> dict[str, Any]:
    """The whole run as plain JSON-ready data."""
    return {
        "document_version": DOCUMENT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "seed": int(run.seed),
        "config": run.config.as_dict(),
        "config_digest": run.config.digest(),
        "arena": run.arena.as_dict(),
        "shells": [shell.as_dict() for shell in run.arena.shells],
        "flights": [
            {"t": float(f.t), "p": [float(f.x), float(f.y)], "v": [float(f.vx), float(f.vy)]}
            for f in run.flights
        ],
        "panel_states": _panel_states(run),
        "events": _event_document(run),
        "summary": run.summary(),
        "digest": run.state_digest(),
    }


def document_for(seed: int, config: ShellEscapeConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    return playback_document(simulate(seed, config))


def write_playback(document: dict[str, Any], path: str) -> str:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1, sort_keys=False)
        handle.write("\n")
    return path


def read_playback(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def document_digest(document: dict[str, Any]) -> str:
    """The digest a consumer should quote when reporting on this run."""
    return str(document["digest"])


def _config_from(document: dict[str, Any]) -> ShellEscapeConfig:
    raw = dict(document["config"])
    for key in ("panel_counts", "openings_per_shell", "opening_slots"):
        raw[key] = tuple(raw[key])
    return ShellEscapeConfig(**raw)


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    """Re-simulate the document's seed and compare, field by field.

    Returns the comparison rather than a bare bool, because "the digests
    differ" and "the digests agree but the event count does not" are different
    failures and a caller that gets `False` cannot tell them apart.
    """
    fresh = simulate(document["seed"], _config_from(document))
    fresh_doc = playback_document(fresh)
    return {
        "seed": document["seed"],
        "digest_matches": document["digest"] == fresh_doc["digest"],
        "config_digest_matches": document["config_digest"] == fresh_doc["config_digest"],
        "schema_version_matches": document["schema_version"] == fresh_doc["schema_version"],
        "event_count_matches": len(document["events"]) == len(fresh_doc["events"]),
        "flight_count_matches": len(document["flights"]) == len(fresh_doc["flights"]),
        "kinds_match": [e["kind"] for e in document["events"]]
        == [e["kind"] for e in fresh_doc["events"]],
        "document_digest": document["digest"],
        "fresh_digest": fresh_doc["digest"],
    }


# --------------------------------------------------------------------------
# Reading the document back, the way a consumer will
# --------------------------------------------------------------------------


def _flight_index_at(flights: Sequence[dict[str, Any]], t: float) -> int:
    lo, hi = 0, len(flights) - 1
    if t <= flights[0]["t"]:
        return 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if flights[mid]["t"] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo


def position_at(document: dict[str, Any], t: float) -> tuple[float, float]:
    """Where the ball is at `t`, from the document alone.

    This is the function a renderer is expected to use, and it is here rather
    than in the renderer so that there is exactly one of it.
    """
    flights = document["flights"]
    index = _flight_index_at(flights, t)
    flight = flights[index]
    dt = t - flight["t"]
    return (flight["p"][0] + flight["v"][0] * dt, flight["p"][1] + flight["v"][1] * dt)


def region_at(document: dict[str, Any], t: float) -> int:
    """Which region the ball is in at `t`, by replaying the crossings."""
    region = 0
    for event in document["events"]:
        if event["t"] > t:
            break
        if event["kind"] in ("shell_exit", "shell_entry"):
            region = event["to_region"]
    return region


def panel_closed_at(document: dict[str, Any], shell_id: int, panel_id: int, t: float) -> bool:
    """Is there material in this slot at `t`? The renderer's whole draw rule."""
    shell = document["shells"][shell_id]
    if panel_id in shell["open_slots"]:
        return False
    for record in document["panel_states"]:
        if record["shell_id"] == shell_id and record["panel_id"] == panel_id:
            return t < record["t"]
    return True
