"""Deterministic race replay export.

The sibling of `replay.exporter`, which does the same job for a duel, and it
keeps the same contract: plain JSON-compatible data only, no timestamps, no
paths and no pickled objects, so the same seed always exports the same file.

It is a separate module rather than a branch inside the duel exporter
because a race and a fight share almost no state. A fight frame is health
and power; a race frame is rank, checkpoint and finishing position. Forcing
both through one function would produce a schema half of whose fields are
null in either mode, and a renderer that has to guess which half it is
reading. What the two *do* share is the contract - and the reader's entry
point into it is `mode`, which every race replay carries and which a
renderer switches on before it reads anything else.

Three things in here are worth knowing about, because each one is a
decision rather than a detail:

* Course geometry is exported in full. A renderer rebuilds the exact course
  from the replay alone and never imports a course builder, for the same
  reason the duel exports its arena layout: what is drawn must be what was
  simulated, not what re-running the generator would produce.

* Spinner transforms are exported per frame. The spinner spec describes the
  motion, but a renderer never evaluates it. It is handed where each arm
  actually was, which is what keeps playback correct the day a spinner can
  be stalled, blocked or stopped by something a formula does not know
  about.

* The camera track is exported per frame. The camera is presentation rather
  than simulation, but it is *derived* presentation: it follows the leading
  group, so reproducing it in a renderer would mean reproducing ranking
  too. Recording where it actually pointed makes the render match the
  preview by construction instead of by agreement.
"""

from __future__ import annotations

import math
from typing import Any

from engine.arena import CANVAS_HEIGHT, CANVAS_WIDTH
from race.camera import FOCUS_GROUP, FOLLOW_RATE, LEAD_FRACTION, RaceCamera
from race.config import (
    PHYSICS_DT,
    PHYSICS_HZ,
    RACE_TIMEOUT_SECONDS,
    RACER_COUNT,
)
from race.course import CoursePiece, RaceCourse, SpinnerSpec
from race.courses import DEFAULT_COURSE
from race.events import RaceEvent
from race.manager import RaceManager
from race.racer import Racer
from race.simulation import RaceSimulation
# Writing is identical for both modes - the same JSON, the same
# separators, the same newline - so it is imported rather than written
# twice.
from replay.exporter import write_replay

__all__ = [
    "RACE_REPLAY_VERSION",
    "MODE_RACE",
    "REPLAY_FPS",
    "TICKS_PER_FRAME",
    "record_race",
    "write_replay",
]

# The race replay's own schema version, on its own counter. It is not the
# duel's v6 and never will be: the two describe different things and will
# grow at different rates, and a reader tells them apart by `mode` before it
# ever looks at a version.
RACE_REPLAY_VERSION = 1

# What a reader switches on. Present in every race replay; a replay without
# it is a duel, which is what makes every file already on disk still valid.
MODE_RACE = "race"
MODE_BATTLE = "battle"

REPLAY_FPS = 60
TICKS_PER_FRAME = PHYSICS_HZ // REPLAY_FPS

# Enough precision for pixel-accurate playback without bloating the file.
# The same figure the duel uses, for the same reason.
DECIMALS = 3


def _round(value: float) -> float:
    return round(float(value), DECIMALS)


def _wrapped_degrees(value: float) -> float:
    """An angle reduced to [0, 360), rounded, and still in range afterwards.

    Rounding last would let 359.9996 land on 360.0 and quietly leave the
    interval it is supposed to be in, so the wrap is applied again after it.
    A racer rolls and a spinner turns for a whole race, so both angles grow
    without bound in the simulation; exporting thousands of degrees would
    cost a renderer float precision for no information. It is also why a
    renderer has to interpolate angles the short way round: here is where an
    angle steps from 359 back to 0.
    """
    return round(value % 360.0, DECIMALS) % 360.0


# --- static course geometry -------------------------------------------------


def _piece(piece: CoursePiece) -> dict[str, Any]:
    """One solid course piece as plain JSON.

    Every piece carries the same keys whichever primitive it is, with the
    fields that primitive does not use left at zero, so a renderer switches
    on `type` and reads one flat shape rather than probing for fields. The
    role and the material are exported alongside the geometry because they
    are what a piece *is* - a bouncy peg and a slick wall are the same box
    to a solver and different objects to a viewer.
    """
    spec = piece.spec
    return {
        "id": piece.piece_id,
        "type": spec.kind,
        "role": piece.role,
        "material": piece.material.name,
        "section": piece.section,
        "x": _round(spec.x),
        "y": _round(spec.y),
        "radius": _round(spec.radius),
        "width": _round(spec.width),
        "height": _round(spec.height),
        "rotation_degrees": _round(spec.rotation_degrees),
        # Jump pads only, and zero everywhere else.
        "impulse": [_round(piece.impulse[0]), _round(piece.impulse[1])],
        "impulse_jitter": _round(piece.impulse_jitter),
    }


def _spinner(spec: SpinnerSpec) -> dict[str, Any]:
    """One spinner's fixed description: hub, arms and how fast it turns.

    A renderer builds the arms from this once and then animates them purely
    from the per-frame transform. `angular_speed` and `start_angle` are
    exported so the layout is readable and reproducible on its own, not so
    that anything downstream integrates them.
    """
    return {
        "id": spec.spinner_id,
        "x": _round(spec.x),
        "y": _round(spec.y),
        "hub_radius": _round(spec.hub_radius),
        "arm_count": spec.arm_count,
        "arm_length": _round(spec.arm_length),
        "arm_thickness": _round(spec.arm_thickness),
        "angular_speed": _round(spec.angular_speed),
        "start_angle": _round(spec.start_angle),
        "reach": _round(spec.reach),
        "material": spec.material.name,
        "section": spec.section,
    }


def _checkpoint(checkpoint) -> dict[str, Any]:
    """One node of the progress graph, corridor and branch included.

    A renderer needs none of this to draw a race, and a debugging overlay
    needs all of it. It is also the only honest record of *why* a racer was
    ranked where it was, which is worth having in the file that claims to
    describe what happened.
    """
    return {
        "index": checkpoint.index,
        "name": checkpoint.name,
        "y": _round(checkpoint.y),
        "respawn": [_round(checkpoint.respawn[0]), _round(checkpoint.respawn[1])],
        "branch": checkpoint.branch,
        "x_min": None if checkpoint.x_min is None else _round(checkpoint.x_min),
        "x_max": None if checkpoint.x_max is None else _round(checkpoint.x_max),
        "progress": _round(checkpoint.value),
    }


def _course(course: RaceCourse) -> dict[str, Any]:
    """The whole static course: enough to rebuild it, and nothing else.

    Deliberately complete. A renderer that had to import the course builder
    to know where a wall is would be a second source of truth for the
    geometry, and the day the two disagreed the replay would be the one
    that was wrong.
    """
    return {
        "id": course.course_id,
        "width": _round(course.width),
        "top": _round(course.top),
        "bottom": _round(course.bottom),
        "height": _round(course.height),
        "out_of_bounds_margin": _round(course.out_of_bounds_margin),
        "metadata": {key: _round(value) for key, value in sorted(course.metadata.items())},
        "sections": [
            {
                "name": section.name,
                "top": _round(section.top),
                "bottom": _round(section.bottom),
            }
            for section in course.sections
        ],
        "pieces": [_piece(piece) for piece in course.pieces],
        "spinners": [_spinner(spec) for spec in course.spinners],
        "checkpoints": [_checkpoint(node) for node in course.checkpoints],
        # The routes through the graph, spelled out. A linear course lists
        # one; a split course lists one per path, and each is a complete
        # start-to-finish sequence rather than a fragment to be assembled.
        "branches": list(course.branches),
        "routes": [
            {
                "branch": branch,
                "checkpoints": [node.index for node in course.route(branch)],
            }
            for branch in (course.branches or ("",))
        ],
        "spawns": [
            {"slot": spawn.slot, "x": _round(spawn.x), "y": _round(spawn.y)}
            for spawn in course.spawns
        ],
        "finish": {
            "index": course.finish_index,
            "name": course.finish.name,
            "y": _round(course.finish_y),
        },
        "max_progress": _round(course.max_progress),
    }


# --- per-frame state --------------------------------------------------------


def _racer_frame(racer: Racer) -> dict[str, Any]:
    """One racer at one sampled moment.

    Velocity is exported although nothing reads it yet. It is the state a
    renderer cannot recover for itself without differentiating positions
    across frames and getting the sampling rate right, and it is what trails,
    impact intensity and motion blur will all be driven from. Three numbers a
    frame is a cheap price for not having to re-export every replay later.
    """
    velocity = racer.velocity
    return {
        "id": racer.racer_id,
        "x": _round(racer.position.x),
        "y": _round(racer.position.y),
        "rotation_degrees": _wrapped_degrees(math.degrees(racer.body.angle)),
        "vx": _round(velocity.x),
        "vy": _round(velocity.y),
        "speed": _round(racer.speed),
        "rank": racer.rank,
        "checkpoint": racer.checkpoint,
        "branch": racer.branch,
        "progress": _round(racer.progress),
        "finished": racer.finished,
        "retired": racer.retired,
        "recoveries": racer.recoveries,
    }


def _frame(manager: RaceManager, camera: RaceCamera) -> dict[str, Any]:
    sim = manager.sim
    return {
        "tick": sim.ticks,
        "race_time": _round(manager.race_time),
        # Where the camera actually was, not where a renderer would have put
        # it. See the module docstring.
        "camera_y": _round(camera.y),
        # The gate is removed rather than moved, so it is a state rather than
        # a transform: a renderer stops drawing the gate pieces on the frame
        # this turns true.
        "gates_open": sim.gates_open,
        "racers": [_racer_frame(racer) for racer in sim.racers],
        # Only the things that move. Their geometry is in the course and is
        # never repeated; this is purely where each one currently is.
        "spinners": [
            {
                "id": spinner.spinner_id,
                "x": _round(spinner.body.position.x),
                "y": _round(spinner.body.position.y),
                "rotation_degrees": _wrapped_degrees(spinner.rotation_degrees),
            }
            for spinner in sim.track.spinners
        ],
    }


def _event(event: RaceEvent) -> dict[str, Any]:
    """One race event as plain JSON.

    Every event carries the same keys, absent values included as null, so a
    renderer reads one shape rather than probing for optional fields per
    type. Both clocks are kept: `tick` is what a renderer ages an effect
    against, `race_time` is what a caption reads.
    """
    return {
        "tick": event.tick,
        "race_time": _round(event.race_time),
        "type": event.type,
        "racer_id": event.racer_id,
        "x": None if event.x is None else _round(event.x),
        "y": None if event.y is None else _round(event.y),
        "value": None if event.value is None else _round(event.value),
        "detail": event.detail,
    }


def _result(manager: RaceManager) -> dict[str, Any]:
    winner = manager.winner
    return {
        "winner_id": None if winner is None else winner.racer_id,
        "winner_name": None if winner is None else winner.name,
        "winner_time": None if winner is None else _round(winner.finish_time or 0.0),
        "finished_tick": manager.completed_tick,
        "duration": None if manager.duration is None else _round(manager.duration),
        "timed_out": manager.timed_out,
        "state": manager.state.value,
        # Crossing order, which is the order a viewer just watched happen.
        # `official_time` carries the recovery penalty beside it rather than
        # re-ranking on it, exactly as the telemetry does.
        "finish_order": [
            {
                "position": position,
                "racer_id": racer.racer_id,
                "name": racer.name,
                "finish_tick": racer.finish_tick,
                "finish_time": _round(racer.finish_time or 0.0),
                "time_penalty": _round(racer.time_penalty),
                "official_time": _round(racer.official_time or 0.0),
            }
            for position, racer in enumerate(manager.finish_order, start=1)
        ],
        "racers_finished": manager.racers_finished,
        "leader_changes": manager.leader_changes,
        "overtakes": manager.overtakes,
        "large_collisions": manager.large_collisions,
        "recoveries": manager.recoveries,
        "retirements": manager.retirements,
        "spinner_contacts": manager.sim.spinner_contacts,
    }


# --- recording --------------------------------------------------------------


def record_race(
    seed: int,
    course_name: str = DEFAULT_COURSE,
    racer_count: int = RACER_COUNT,
    course: RaceCourse | None = None,
) -> dict[str, Any]:
    """Run one race headlessly and capture it as replay data.

    Visual state is sampled every `TICKS_PER_FRAME` physics ticks, which is
    60 frames per simulated second at the 120 Hz physics rate - the same
    rate, from the same clock, as the duel. `course` pins exact geometry the
    way `arena_layout` does for a battle; left out, the named course is
    built from the seed.

    The camera is advanced exactly as the live preview advances it: once per
    exported frame, by the fixed time that frame covers. That is what makes
    the recorded track the one a viewer of the preview would have seen,
    rather than a plausible reconstruction of it.
    """
    sim = RaceSimulation(
        seed, course=course, course_name=course_name, racer_count=racer_count
    )
    manager = RaceManager(sim)
    camera = RaceCamera(sim.course, CANVAS_HEIGHT)
    camera.snap_to(sim.racers)

    frames = [_frame(manager, camera)]
    while not manager.complete:
        for _ in range(TICKS_PER_FRAME):
            if not manager.step():
                break
        camera.update(sim.racers, TICKS_PER_FRAME * PHYSICS_DT)
        frames.append(_frame(manager, camera))

    return {
        "version": RACE_REPLAY_VERSION,
        "mode": MODE_RACE,
        "seed": seed,
        "fps": REPLAY_FPS,
        "physics_hz": PHYSICS_HZ,
        "ticks_per_frame": TICKS_PER_FRAME,
        "limit_seconds": RACE_TIMEOUT_SECONDS,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "course_id": sim.course.course_id,
        # Static for the whole race, so exported once here and never
        # repeated inside a frame.
        "course": _course(sim.course),
        "camera": {
            "viewport_width": _round(CANVAS_WIDTH),
            "viewport_height": _round(CANVAS_HEIGHT),
            "lead_fraction": LEAD_FRACTION,
            "focus_group": FOCUS_GROUP,
            "follow_rate": FOLLOW_RATE,
        },
        "racers": [
            {
                "id": racer.racer_id,
                "name": racer.name,
                "color": list(racer.color),
                "radius": _round(racer.radius),
                "spawn_slot": racer.spawn_slot,
                # Every racer is a rolling ball today. The field is here so
                # the day one is not, a replay says which it was rather than
                # a renderer assuming.
                "contestant_type": "ball",
            }
            for racer in sim.racers
        ],
        "frames": frames,
        # Recorded in the order the race produced them, which is already
        # tick order, so nothing has to be sorted afterwards.
        "events": [_event(event) for event in manager.events],
        "result": _result(manager),
    }
