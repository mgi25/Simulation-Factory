"""The canonical multiplying-shell run, written down once so a consumer can only replay it.

The visual and audio phases will be built from this document and nothing else.
The rule they inherit is the one Test #1 settled and the single-ball Test #2
made enforceable:

    a consumer of this document may read a trajectory and may not compute one.

A rotating-polygon billiard has a positive Lyapunov exponent - `shell_arena`
sets out why the shells are polygons precisely so that it does - and a second
copy of the physics in a Godot scene or a synthesiser, however honest, diverges
from this one within a few seconds. With a population of balls the divergence
is worse rather than better, because a break caused by ball 7 at t = 11.2
changes what ball 3 does at t = 11.4, so a consumer that re-simulates gets not
just a different trajectory but a different *cast*.

## What is in the document, and why each part has to be

- **`balls`** - one record per ball: id, parent, generation, birth time, birth
  shell, lineage, the shells it was credited for and the regions it stood in.
  A renderer tints a lineage with this; a sequencer gives a lineage a voice
  with it. It is the thing the single-ball schema had no way to express.
- **`flights`** - keyed by ball id, one record per straight-line arc: `t`,
  position and velocity at its start. Gravity is zero and speed is constant, so
  this *is* the trajectory, complete and exact. A ball does not exist before
  its first flight, which is how a renderer knows when to fade it in.
- **`shells`** - radius, panel count, thickness, initial angle, angular
  velocity and the slots that start open. A consumer places a panel by rotating
  the shell to `theta0 + omega*t`; it re-derives nothing from the seed.
- **`panel_states`** - every panel that broke, with the time it broke and every
  damage-state transition it went through. A renderer replaying `t` draws a
  panel in the last state it entered at or before `t`, and draws nothing if it
  has broken. That is the whole rule, and it is why the visual branch does not
  have to replay the damage events in order to get the geometry right.
- **`events`** - the full stream, in time order, exactly as
  `satisfying.multishell.EVENT_SCHEMA` defines it.
- **`summary`** and **`difficulty`** - outcome, counts and the per-shell
  difficulty table. Redundant against the events on purpose: a test that checks
  a metric should not have to re-derive the metric it is checking.
- **`digest`** - `MultishellRun.state_digest`. A render and a report that print
  the same digest are the same run.

## Floats

Every number is a Python float and JSON round-trips a double exactly -
`json.dumps` emits `repr`, the shortest string that reads back as the same
double, and Godot's `JSON.parse` reads doubles. `verify_document` asserts it by
re-simulating the seed and comparing digests, which is the only check that
would catch a future "round to six decimals to make the file smaller".
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Sequence

from satisfying.multishell import (
    DEFAULT_CONFIG,
    SCHEMA_VERSION,
    MultishellConfig,
    MultishellRun,
    difficulty_profile,
    simulate,
)

__all__ = [
    "playback_document",
    "document_for",
    "write_playback",
    "read_playback",
    "document_digest",
    "verify_document",
    "position_at",
    "population_at",
    "panel_state_at",
]


def _pair(values: Sequence[float]) -> list[float]:
    return [float(values[0]), float(values[1])]


def _event_document(run: MultishellRun) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in run.events:
        record: dict[str, Any] = {"kind": ev.kind, "t": float(ev.t)}
        for key, value in ev.data.items():
            record[key] = list(value) if isinstance(value, tuple) else value
        out.append(record)
    return out


def _panel_states(run: MultishellRun) -> list[dict[str, Any]]:
    """Every panel that ever changed, with its whole history of states."""
    index: dict[tuple[int, int], dict[str, Any]] = {}
    for ev in run.events:
        if ev.kind == "damage_state":
            key = (ev.data["shell_id"], ev.data["panel_id"])
            entry = index.setdefault(
                key,
                {
                    "shell_id": key[0],
                    "panel_id": key[1],
                    "transitions": [],
                    "break_time": None,
                    "broken_by": None,
                },
            )
            entry["transitions"].append(
                {
                    "t": float(ev.t),
                    "state": ev.data["new_state"],
                    "fraction": float(ev.data["fraction"]),
                }
            )
        elif ev.kind == "panel_break":
            key = (ev.data["shell_id"], ev.data["panel_id"])
            entry = index.setdefault(
                key,
                {
                    "shell_id": key[0],
                    "panel_id": key[1],
                    "transitions": [],
                    "break_time": None,
                    "broken_by": None,
                },
            )
            entry["break_time"] = float(ev.t)
            entry["broken_by"] = ev.data["ball_id"]
            entry["contributors"] = ev.data["contributors"]
    return [index[key] for key in sorted(index)]


def playback_document(run: MultishellRun) -> dict[str, Any]:
    """The whole run, as the only thing a consumer is allowed to read."""
    return {
        "schema": SCHEMA_VERSION,
        "seed": int(run.seed),
        "config": run.config.as_dict(),
        "config_digest": run.config.digest(),
        "difficulty": difficulty_profile(run.config),
        "arena": run.arena.as_dict(),
        "shells": [s.as_dict() for s in run.arena.shells],
        "balls": [b.as_dict() for b in run.balls],
        "flights": {
            str(ball_id): [
                {"t": float(f.t), "x": float(f.x), "y": float(f.y), "vx": float(f.vx), "vy": float(f.vy)}
                for f in flights
            ]
            for ball_id, flights in sorted(run.flights.items())
        },
        "panel_states": _panel_states(run),
        "population_samples": [[float(t), int(n)] for t, n in run.population_samples],
        "events": _event_document(run),
        "summary": run.summary(),
        "digest": run.state_digest(),
    }


def document_for(seed: int, config: MultishellConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    return playback_document(simulate(seed, config))


def write_playback(document: dict[str, Any], path: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return path


def read_playback(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def document_digest(document: dict[str, Any]) -> str:
    """A fingerprint of the file, distinct from the run's state digest."""
    blob = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _config_from(document: dict[str, Any]) -> MultishellConfig:
    return MultishellConfig.from_dict(document["config"])


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    """Re-simulate the seed and check the document is that run, exactly."""
    config = _config_from(document)
    run = simulate(int(document["seed"]), config)
    fresh = playback_document(run)
    checks = {
        "schema": document.get("schema") == SCHEMA_VERSION,
        "config_digest": document.get("config_digest") == config.digest(),
        "state_digest": document.get("digest") == run.state_digest(),
        "event_count": len(document.get("events", [])) == len(fresh["events"]),
        "ball_count": len(document.get("balls", [])) == len(fresh["balls"]),
        "flight_count": sum(len(v) for v in document.get("flights", {}).values())
        == sum(len(v) for v in fresh["flights"].values()),
        "document_digest": document_digest(document) == document_digest(fresh),
    }
    return {"ok": all(checks.values()), "checks": checks, "digest": run.state_digest()}


# --------------------------------------------------------------------------
# Reading a document back
# --------------------------------------------------------------------------


def position_at(document: dict[str, Any], ball_id: int, t: float) -> tuple[float, float] | None:
    """Where ball `ball_id` is at time `t`, or None if it does not exist yet."""
    flights = document["flights"].get(str(ball_id))
    if not flights or t < flights[0]["t"]:
        return None
    chosen = flights[0]
    for flight in flights:
        if flight["t"] <= t:
            chosen = flight
        else:
            break
    dt = t - chosen["t"]
    return (chosen["x"] + chosen["vx"] * dt, chosen["y"] + chosen["vy"] * dt)


def population_at(document: dict[str, Any], t: float) -> int:
    """How many balls exist at time `t`."""
    count = 0
    for at, n in document["population_samples"]:
        if at <= t:
            count = int(n)
        else:
            break
    return count


def panel_state_at(document: dict[str, Any], shell_id: int, panel_id: int, t: float) -> str:
    """The panel's damage state at `t`: one of `DAMAGE_STATES`.

    A panel with no history has never been touched and is `healthy`. One that
    has broken stays `broken` for good - there is no repair anywhere in the
    model, which is what makes an early ball's damage worth something to a
    later one.
    """
    for entry in document["panel_states"]:
        if entry["shell_id"] != shell_id or entry["panel_id"] != panel_id:
            continue
        state = "healthy"
        for transition in entry["transitions"]:
            if transition["t"] <= t:
                state = transition["state"]
            else:
                break
        return state
    return "healthy"
