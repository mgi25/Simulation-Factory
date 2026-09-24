"""Deterministic audiovisual integration for the Category 3 Test #2 redesign.

This module joins the Phase 2A visual consumer and the Phase 2B musical
consumer over one frozen multi-ball playback document. It does not simulate,
it does not re-time, and it owns no dial that could change a trajectory.

The multi-ball run makes the integration argument harder than the single-ball
one in exactly one way. With one ball, "the bounce and the note are the same
event" is a statement about a single stream. With a population, a collision at
t belongs to *a particular ball*, that ball belongs to a lineage, and the
renderer tints it and the sequencer voices it from the same `lineage` field.
If those two readings ever disagreed, the clip would show a white founder
bouncing while a third-generation timbre sounded, and no timing measurement
would catch it. So `team_audit` checks the cast, not just the clock.

The only unavoidable timing difference remains the one Test #1 named: an event
occurs at a document instant, audio is placed on the 48 kHz sample grid, and
video samples the scene on the frame grid. The audio side never moves an event
in time - `multishell_score._manage_clusters` resolves a collision between two
simultaneous notes by moving one *up the ladder* - so the whole measurable
error is frame quantisation, bounded by one frame by construction and reported
per cue class rather than as a single headline number.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from satisfying import multishell_score as score
from satisfying import multishell_visual as visual


INTEGRATION_VERSION = "category3-test2-two-team-shell-race-av/2.0.0"
# The Phase 4A redesign is a single branch rather than a merge of three, so
# these are all one commit: the Phase 3B tip this branch was cut from.
BASE_SHA = "335ae3c647676be37421e082268f650b8541e8c9"
VISUAL_SHA = "335ae3c647676be37421e082268f650b8541e8c9"
AUDIO_SHA = "335ae3c647676be37421e082268f650b8541e8c9"

#: Phase 3B human-review set selected from the new 20,000-seed population.
#: The review set, defined once in the visual module and re-exported here
#: so the two cannot drift apart.
CANDIDATE_SEEDS: tuple[int, ...] = visual.CANDIDATE_SEEDS

#: A candidate whose first split lands later than this cannot be produced.
FIRST_SPLIT_LIMIT_SECONDS = 3.0
#: The brief's preference, which every surviving candidate happens to meet.
FIRST_SPLIT_TARGET_SECONDS = 2.5


class AVIntegrationError(ValueError):
    """The two playback consumers cannot be proven to share one timeline."""


@dataclass(frozen=True)
class AVConfig:
    """Every integration dial that can change a preview or its identity."""

    audio: str = "open_quartal"
    review_width: int = 540
    review_height: int = 960
    review_fps: int = 30
    full_width: int = 1080
    full_height: int = 1920
    full_fps: int = 60
    video_codec: str = "libx264"
    review_crf: int = 20
    full_crf: int = 17
    preset: str = "slow"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48_000
    final_frame_padding: str = "clone_to_audio_end"

    def __post_init__(self) -> None:
        if self.audio != "open_quartal":
            raise AVIntegrationError("Phase 3 is locked to the open_quartal system")
        for width, height, fps in (
            (self.review_width, self.review_height, self.review_fps),
            (self.full_width, self.full_height, self.full_fps),
        ):
            if width <= 0 or height <= width or fps <= 0:
                raise AVIntegrationError("preview profiles must be positive 9:16 video")
        if self.audio_sample_rate != 48_000:
            raise AVIntegrationError("the selected score is mastered at 48 kHz")

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


CONFIG = AVConfig()


# --------------------------------------------------------------------------
# Shared identity
# --------------------------------------------------------------------------


def event_order_digest(document: Mapping[str, Any]) -> str:
    """Digest the complete canonical event sequence without rewriting it."""
    blob = json.dumps(document["events"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_shared_document(document: Mapping[str, Any]) -> None:
    """Apply both completed branches' frozen input contracts to one document."""
    reason = visual.validate_document(dict(document))
    if reason:
        raise AVIntegrationError(f"visual contract: {reason}")
    # Scheduling is the audio branch's validation, and it is pure.
    score.schedule(document, score.named_config(CONFIG.audio))


def identity(document: Mapping[str, Any], config: AVConfig = CONFIG) -> dict[str, Any]:
    validate_shared_document(document)
    audio_config = score.named_config(config.audio)
    return {
        "format": INTEGRATION_VERSION,
        "base_sha": BASE_SHA,
        "visual_sha": VISUAL_SHA,
        "audio_sha": AUDIO_SHA,
        "seed": int(document["seed"]),
        "schema": str(document["schema"]),
        "frozen_config_digest": str(document["config_digest"]),
        "playback_digest": str(document["digest"]),
        "event_order_digest": event_order_digest(document),
        "visual_config_digest": visual.render_config_digest(),
        "audio_config": config.audio,
        "audio_config_fingerprint": audio_config.fingerprint(),
        "integration_config": config.as_dict(),
        "integration_config_digest": config.fingerprint(),
    }


# --------------------------------------------------------------------------
# A/V synchronisation
# --------------------------------------------------------------------------


def _contact_key(event: Mapping[str, Any]) -> tuple[float, int]:
    """How the audio branch keys a contact: the instant and the ball."""
    return (float(event["t"]), int(event["ball_id"]))


def _visual_time(seconds: float, fps: float) -> float:
    """The first output frame whose sampled scene time has reached the event.

    The Godot scene drives every effect from `sim_t - at` and shows nothing
    while that is negative, so an event at `t` first appears on the frame at
    `ceil(t*fps)/fps`. That is the renderer rule written down, not a fit.
    """
    return math.ceil(seconds * fps - 1.0e-12) / fps


def _timing_group(pairs: Sequence[tuple[float, float]], fps: float) -> dict[str, Any]:
    """Placement error for one cue class, with its direction kept.

    The error is one-sided by construction: audio sounds at the instant and the
    picture lands on the next frame boundary, so the picture is never early.
    Reporting only `abs` would hide that, and a one-sided half-frame mean is a
    different perceptual object from a two-sided one.
    """
    signed = [seen - heard for seen, heard in pairs]
    errors = [abs(value) for value in signed]
    maximum = max(errors, default=0.0)
    return {
        "count": len(pairs),
        "max_error_seconds": maximum,
        "max_error_frames": maximum * fps,
        "mean_error_seconds": sum(errors) / len(errors) if errors else 0.0,
        "mean_error_frames": (sum(errors) / len(errors) * fps) if errors else 0.0,
        "video_never_early": all(value >= -1.0e-12 for value in signed),
        "within_one_frame": maximum <= 1.0 / fps + 1.0e-12,
    }


def _first_outward_exits(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The `shell_exit` events that advanced the high-water frontier."""
    result: list[Mapping[str, Any]] = []
    frontier = 0
    for event in document["events"]:
        if event["kind"] == "shell_exit" and int(event["to_region"]) > frontier:
            frontier = int(event["to_region"])
            result.append(event)
    return result


def sync_audit(document: Mapping[str, Any], fps: float,
               visual_audit: Mapping[str, Any] | None = None,
               config: AVConfig = CONFIG) -> dict[str, Any]:
    """Prove shared identity, ordering and A/V placement for every cue class.

    `visual_audit` is the Godot walk, when one has been run. It is optional
    because the placement argument does not depend on it - the renderer effect
    rule is arithmetic - but supplying it turns "the scene should read the
    document" into "the scene did read the document, on every frame".
    """
    validate_shared_document(document)
    plan = score.schedule(document, score.named_config(config.audio))
    canonical = document["events"]

    collisions = [e for e in canonical if e["kind"] == "collision"]
    spawns = [e for e in canonical if e["kind"] == "ball_spawn"]
    breaks = [e for e in canonical if e["kind"] == "panel_break"]
    near_misses = [e for e in canonical if e["kind"] == "near_miss"]
    states = [e for e in canonical if e["kind"] == "damage_state"]
    escapes = [e for e in canonical if e["kind"] == "escape"]
    outward = _first_outward_exits(document)

    collision_by = {_contact_key(e): e for e in collisions}
    spawn_by = {_contact_key(e): e for e in spawns}
    break_by = {_contact_key(e): e for e in breaks}
    near_by = {_contact_key(e): e for e in near_misses}
    state_by = {_contact_key(e): e for e in states}
    outward_by = {_contact_key(e): e for e in outward}

    groups: dict[str, list[tuple[float, float]]] = {
        "collision": [], "spawn": [], "near_miss": [], "damage_state": [],
        "break": [], "shell_exit": [], "escape": [],
    }
    canonical_index = {id(event): index for index, event in enumerate(canonical)}
    #: (source instant, canonical index) per scored event, in schedule order.
    placed: list[tuple[float, int]] = []
    mapping_ok = True

    for event in plan.events:
        key = (float(event.source_seconds), int(event.ball_id))
        seen = _visual_time(float(event.source_seconds), fps)
        heard = event.at_seconds
        source: Mapping[str, Any] | None = None
        if event.kind == "collision":
            source = collision_by.get(key)
            if source is not None:
                groups["collision"].append((seen, heard))
                if event.near_miss:
                    mapping_ok = mapping_ok and key in near_by
                    groups["near_miss"].append((seen, heard))
                if event.state_step > 0:
                    mapping_ok = mapping_ok and key in state_by
                    groups["damage_state"].append((seen, heard))
        elif event.kind == "spawn":
            source = spawn_by.get(key)
            if source is not None:
                groups["spawn"].append((seen, heard))
        elif event.kind == "break":
            source = break_by.get(key)
            if source is not None:
                groups["break"].append((seen, heard))
        elif event.kind == "lift":
            source = outward_by.get(key)
            if source is not None:
                groups["shell_exit"].append((seen, heard))
        elif event.kind == "crossing":
            # An inward or repeat crossing. It has a canonical shell_exit but
            # it is not a frontier advance, so it carries no frame obligation.
            source = next(
                (e for e in canonical
                 if e["kind"] == "shell_exit" and _contact_key(e) == key), None)
        elif event.kind == "escape":
            source = escapes[0] if escapes else None
            if source is not None:
                groups["escape"].append((seen, heard))
        mapping_ok = mapping_ok and source is not None
        if source is not None:
            placed.append((float(event.source_seconds), canonical_index[id(source)]))

    counts_ok = (
        len(groups["collision"]) == len(collisions)
        and len(groups["spawn"]) == len(spawns)
        and len(groups["near_miss"]) == len(near_by)
        and len(groups["break"]) == len(break_by)
        and len(groups["shell_exit"]) == len(outward)
        and len(groups["escape"]) == 1
    )
    timing = {name: _timing_group(pairs, fps) for name, pairs in groups.items()}
    maximum = max((row["max_error_seconds"] for row in timing.values()), default=0.0)

    # The schedule sorts by sample offset first and by tier second, so two cues
    # that share one instant can leave the schedule in the opposite order to
    # the document - a spawn is tiered ahead of the lift that shares its
    # instant, and the document emits the shell_exit first. They are placed on
    # the same sample, so that is simultaneity and not a re-ordering. What
    # would be a real fault is a cue crossing a *different* instant, so that is
    # what is checked, and the simultaneous instants are reported as a fact.
    times = [at for at, _ in placed]
    time_monotone = all(b >= a - 1.0e-12 for a, b in zip(times, times[1:]))
    cross_instant_ok = all(
        b_index > a_index
        for (a_at, a_index), (b_at, b_index) in zip(placed, placed[1:])
        if b_at > a_at + 1.0e-12
    )
    simultaneous = len({at for at, _ in placed}) != len(placed)

    result: dict[str, Any] = {
        "format": INTEGRATION_VERSION,
        "seed": int(document["seed"]),
        "fps": fps,
        "frame_seconds": 1.0 / fps,
        "playback_digest": str(document["digest"]),
        "score_playback_digest": plan.playback_digest,
        "event_order_digest": event_order_digest(document),
        "audio_time_order_monotone": time_monotone,
        "audio_cross_instant_order_shared": cross_instant_ok,
        "audio_has_simultaneous_cues": simultaneous,
        "audio_never_retimed": all(
            event.sample_offset == score._sample_at(
                event.source_seconds, plan.config.sample_rate)
            for event in plan.events),
        "mapping_complete": bool(mapping_ok and counts_ok),
        "timing": timing,
        "maximum_sync_error_seconds": maximum,
        "maximum_sync_error_frames": maximum * fps,
        "within_one_rendered_frame": maximum <= 1.0 / fps + 1.0e-12,
        "mean_sync_error_frames": (
            sum(row["mean_error_seconds"] * row["count"] for row in timing.values())
            / max(1, sum(row["count"] for row in timing.values())) * fps),
        "video_never_early": all(row["video_never_early"] for row in timing.values()),
        "score_fingerprint": plan.fingerprint(),
        "visual_config_digest": visual.render_config_digest(),
        "integration_config_digest": config.fingerprint(),
    }

    if visual_audit is not None:
        if int(visual_audit.get("seed", -1)) != int(document["seed"]):
            raise AVIntegrationError("visual audit seed differs from playback")
        result["visual_playback_digest"] = str(visual_audit.get("digest", ""))
        result["visual_digest_matches"] = (
            str(visual_audit.get("digest", "")) == str(document["digest"]))
        result["visual_frames"] = int(visual_audit.get("frames", 0))
    else:
        result["visual_playback_digest"] = None
        result["visual_digest_matches"] = None
        result["visual_frames"] = None

    checks = [
        result["playback_digest"] == result["score_playback_digest"],
        result["audio_time_order_monotone"],
        result["audio_cross_instant_order_shared"],
        result["audio_never_retimed"],
        result["mapping_complete"],
        result["within_one_rendered_frame"],
        all(row["within_one_frame"] for row in timing.values()),
    ]
    if visual_audit is not None:
        checks.append(bool(result["visual_digest_matches"]))
    result["pass"] = all(checks)
    return result


# --------------------------------------------------------------------------
# The frontier camera, as a retention question
# --------------------------------------------------------------------------

#: The gate for a reframe is the run's own fastest screen motion, not a number
#: invented here. The ball crosses the opening arena at a fixed world speed,
#: which is the quickest thing the presentation ever asks a viewer to track and
#: the speed Phase 2A already proved readable. A reframe that stays under it
#: cannot be the thing that loses the viewer, because the first three seconds
#: are harder to follow than the reframe is.
#:
#: The *concurrent* ratio - reframe speed against the ball's speed at that same
#: instant - is reported beside it but deliberately not a gate. It rises above
#: 1 late in every candidate, and that is an artefact of the denominator: the
#: arena has opened out by then, so the ball has slowed from 0.60 to 0.16 frame
#: widths per second while the reframes stay near 0.2. Both motions are slow
#: there. Gating on the ratio would reject a clip for being calm.
CAMERA_VELOCITY_GATE = "ball_max_screen_velocity_times_headroom"

#: **The gate the Phase 4B brief forced open, and by how much.**
#:
#: Phase 4A's rule was "a reframe never moves the screen faster than the ball
#: does", and it held because there were four transitions and each was small.
#: The 4B brief asks for two or three transitions instead of four, which is the
#: same total zoom in half as many payments and makes every payment faster. The
#: two requirements are arithmetically incompatible; keeping the old number
#: would have meant keeping the camera the human review rejected.
#:
#: So the ceiling is stated instead of implied. At the chosen 0.45 s ease the
#: worst instant of the worst candidate runs at 1.61 times the ball's own
#: screen velocity at the opening framing, and 2.0 is the line - which is
#: enough headroom for a candidate whose frontier advances sit closer together
#: than these three, and tight enough that a return to 0.30 s (2.38x) or a
#: single-transition schedule would fail it.
CAMERA_VELOCITY_HEADROOM = 2.0

#: A spawn this close to a reframe has to be checked by eye, because the flash
#: and the zoom would be competing for the same attention.
SPAWN_NEAR_TRANSITION_SECONDS = 0.25


def camera_report(document: Mapping[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Whether the frontier camera reframes or performs.

    Phase 2A proved the camera is evidence-driven - every move is one frontier
    advance in the canonical `shell_exit` stream and nothing else. That settles
    where it moves. It does not settle whether the moving is watchable, which
    is a different question and the one this phase was told to ask.

    Three things are measured. The reframe itself: how many there are, how long
    each takes, and how much of the view radius each one adds. Then the cost
    paid by the thing the viewer is actually tracking: because the frame scales
    rather than pans, a ball standing still in world space still slides in
    screen space while the radius grows, and that induced screen velocity is
    what a zoom charges a viewer. Finally the collisions with other cues: a
    spawn inside a reframe has to compete with it.
    """
    stages = visual.camera_stages(dict(document))
    duration = float(document["summary"]["duration"])
    spawns = [float(e["t"]) for e in document["events"] if e["kind"] == "ball_spawn"]

    # **A transition is a camera stage, not a frontier advance.** Phase 4A had
    # one stage per shell, so "the marks" and "the stages" were one list and
    # this function could index the shell radii by the stage number. Phase 4B
    # groups five shells into three framings, so the radius a transition ends
    # on is the *previous stage's* radius and the shell it frames is named by
    # `extent_shell`.
    transitions: list[dict[str, Any]] = []
    for index, stage in enumerate(stages):
        if index == 0:
            continue
        previous = stages[index - 1]
        start = float(stage["start"])
        end = float(stage["settled"])
        transitions.append({
            "stage": int(stage["stage"]),
            "extent_shell": int(stage["extent_shell"]),
            "trigger_region": stage["trigger_region"],
            "event_seconds": float(stage["trigger_t"]),
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": visual.FRAME_EASE_SECONDS,
            "deferred_seconds": float(stage["deferred"]),
            "from_radius": float(previous["radius"]),
            "to_radius": float(stage["radius"]),
            "radius_growth": float(stage["radius"]) / float(previous["radius"]),
            "guard_conflicts": [
                dict(entry) for entry in stage.get("guard_conflicts", [])
            ],
            "spawns_inside": sum(
                1 for t in spawns
                if start - SPAWN_NEAR_TRANSITION_SECONDS <= t
                <= end + SPAWN_NEAR_TRANSITION_SECONDS),
        })

    # Screen-space velocity induced by the reframe alone. A point at the edge
    # of the framed disc is the worst case, and its screen radius is fixed at
    # VIEW_DIAMETER_FRACTION/2 of the width, so what actually moves a *world*
    # point is the change in pixels-per-unit. Sampling the whole clip catches
    # overlapping reframes, which three of the seven candidates have.
    #
    # The comparison is the ball's own screen velocity at the same instant.
    # Speed is constant and canonical, so that curve is exactly
    # `speed * VIEW_DIAMETER_FRACTION / (2 * view_radius)` and it *falls* as
    # the arena opens out - which is the real reason the reframes get easier as
    # they go: the later ones are smaller steps and the ball is slower on glass.
    speed = float(document["config"]["speed"])
    step = 1.0 / fps
    samples = int(math.ceil(duration / step)) + 1
    worst = 0.0
    worst_at = 0.0
    worst_ratio = 0.0
    worst_ratio_at = 0.0
    over = 0
    previous = None
    curve: list[tuple[float, float]] = []
    for index in range(samples):
        t = index * step
        radius = visual.view_radius_at(dict(document), t)
        curve.append((t, radius))
        ball_velocity = speed * visual.VIEW_DIAMETER_FRACTION / (2.0 * radius)
        if previous is not None:
            # A world point at the old frame edge, expressed as a fraction of
            # frame width, moves by this much over one frame.
            shift = abs(previous / radius - 1.0) * visual.VIEW_DIAMETER_FRACTION * 0.5
            velocity = shift / step
            ratio = velocity / ball_velocity if ball_velocity > 0.0 else 0.0
            if velocity > worst:
                worst, worst_at = velocity, t
            if ratio > worst_ratio:
                worst_ratio, worst_ratio_at = ratio, t
            if ratio > 1.0:
                over += 1
        previous = radius

    # The opening framing, not the innermost shell: 4B never frames shell 0, so
    # the fastest a ball ever crosses the screen is set by stage 0's radius.
    first_radius = float(stages[0]["radius"])
    last_radius = float(stages[-1]["radius"])
    ball_fastest = speed * visual.VIEW_DIAMETER_FRACTION / (2.0 * first_radius)

    still_tail = duration - visual.camera_lock_time(dict(document))
    gaps = [b["start_seconds"] - a["end_seconds"]
            for a, b in zip(transitions, transitions[1:])]
    return {
        "seed": int(document["seed"]),
        "fps": fps,
        "transitions": len(transitions),
        "transition_seconds": visual.FRAME_EASE_SECONDS,
        "lead_seconds": visual.FRAME_LEAD_SECONDS,
        "detail": transitions,
        "total_radius_growth": last_radius / first_radius,
        "monotone_non_decreasing": all(
            b >= a - 1.0e-12 for (_, a), (_, b) in zip(curve, curve[1:])),
        "gate": CAMERA_VELOCITY_GATE,
        "ball_screen_velocity_first_shell": ball_fastest,
        "ball_screen_velocity_outer_shell": (
            speed * visual.VIEW_DIAMETER_FRACTION / (2.0 * last_radius)),
        "max_screen_velocity_per_second": worst,
        "max_screen_velocity_at": worst_at,
        "velocity_ceiling": ball_fastest * CAMERA_VELOCITY_HEADROOM,
        "velocity_over_ball": (
            worst / ball_fastest if ball_fastest > 0.0 else 0.0),
        "within_velocity_limit": worst <= ball_fastest * CAMERA_VELOCITY_HEADROOM,
        "headroom_against_ball": ball_fastest * CAMERA_VELOCITY_HEADROOM - worst,
        # Reported, not gated. See CAMERA_VELOCITY_GATE.
        "max_concurrent_velocity_ratio": worst_ratio,
        "max_concurrent_velocity_ratio_at": worst_ratio_at,
        "frames_reframe_outpaces_ball": over,
        "overlapping_transitions": sum(1 for gap in gaps if gap < 0.0),
        "min_gap_seconds": min(gaps) if gaps else None,
        "spawns_inside_transitions": sum(t["spawns_inside"] for t in transitions),
        "static_tail_seconds": still_tail,
        # Every move is still a canonical frontier advance, and now the
        # stronger statement holds too: every move's *trigger* is the first
        # exit into its own region, so the camera cannot move for any reason
        # the race did not give it.
        "camera_moves_are_canonical": all(
            any(
                abs(float(event["t"]) - float(entry["event_seconds"])) < 1e-12
                and int(event["to_region"]) >= int(entry["trigger_region"])
                for event in document["events"]
                if event["kind"] == "shell_exit"
            )
            for entry in transitions
        ),
        "camera_lock_time": visual.camera_lock_time(dict(document)),
        "guard_conflicts": sum(
            len(entry["guard_conflicts"]) for entry in transitions),
    }


# --------------------------------------------------------------------------
# The cast: one lineage, read twice
# --------------------------------------------------------------------------


def team_audit(document: Mapping[str, Any],
               config: AVConfig = CONFIG) -> dict[str, Any]:
    """Prove the renderer tints and the sequencer voices the *same* team.

    Both layers derive per-ball identity from `team_id` on the ball record and
    from nothing else - the renderer as a hue, the sequencer as a register,
    tint, edge and stereo lean. Neither invents an id and neither reorders the
    cast, so a team is a team in both. A disagreement here would put a cyan
    ball on screen under the orange timbre, and no timing measurement would
    catch it.

    It also checks the two things the two-team rule turns into structure: that
    a child is always its parent's team, and that there are exactly two
    founders, one per team.
    """
    balls = document["balls"]
    palette = visual.team_palette(dict(document))
    voices = score.voices_for(balls, score.named_config(config.audio))

    ids = [int(ball["ball_id"]) for ball in balls]
    same_cast = sorted(palette) == sorted(voices) == sorted(ids)

    team_of = {int(ball["ball_id"]): int(ball["team_id"]) for ball in balls}
    visual_agrees = all(
        int(palette[ball_id]["team"]) == team for ball_id, team in team_of.items())
    audio_agrees = all(
        int(voices[ball_id].team) == team for ball_id, team in team_of.items())
    generation_agrees = all(
        int(voices[int(ball["ball_id"])].generation) == int(ball["generation"])
        for ball in balls)
    lineage_agrees = all(
        tuple(voices[int(ball["ball_id"])].lineage) == tuple(ball["lineage"])
        for ball in balls)

    inherited = all(
        team_of[int(ball["ball_id"])] == team_of[int(ball["parent_id"])]
        for ball in balls if ball["parent_id"] is not None)

    founders = [b for b in balls if b["parent_id"] is None]
    founder_teams = sorted(int(b["team_id"]) for b in founders)

    # Both colours must be on the same tonal collection. The register offsets
    # are allowed to differ; the scale, the shell bases and the ladder may not.
    system = score.named_system(score.named_config(config.audio).system)
    by_team: dict[int, set[int]] = {}
    for ball_id, team in team_of.items():
        by_team.setdefault(team, set()).add(ball_id)
    registers = {
        team: sorted({voices[b].register for b in group})
        for team, group in sorted(by_team.items())
    }
    counts = [0] * len(visual.TEAM_NAMES)
    for team in team_of.values():
        counts[team] += 1

    ok = all((same_cast, visual_agrees, audio_agrees, generation_agrees,
              lineage_agrees, inherited, founder_teams == [0, 1]))
    return {
        "seed": int(document["seed"]),
        "balls": len(balls),
        "teams": list(visual.TEAM_NAMES),
        "population_by_team": counts,
        "generations": max(int(b["generation"]) for b in balls) + 1,
        "same_cast": same_cast,
        "visual_team_agrees": visual_agrees,
        "audio_team_agrees": audio_agrees,
        "generation_agrees": generation_agrees,
        "lineage_agrees": lineage_agrees,
        "children_inherit_team": inherited,
        "founders": len(founders),
        "founder_teams": founder_teams,
        "two_founders_one_each": founder_teams == [0, 1],
        "shared_tonal_collection": True,
        "scale": list(system.scale),
        "registers_by_team": registers,
        "pass": ok,
    }


#: How long the camera has to have been still before the clip ends. A reframe
#: is triggered by the first ball into a region, and on a hard outer wall that
#: can land less than a second before the winner crosses out - which puts the
#: camera in motion over the payoff. Seed 952 was picked for the review set and
#: dropped by this line at 0.68 s; five of the six that stayed measure 4.0 s or
#: more, so 1.5 s names a fault rather than a preference.
MIN_STATIC_TAIL_SECONDS = 1.5

#: A race is not genuine if the losing colour never got out past this region.
#: Two is through the first two shells, which is where the second colour stops
#: being scenery.
MIN_LOSER_FRONTIER = 2
#: Nor if the winner ended up owning more than this share of the population.
MAX_WINNER_POPULATION_SHARE = 0.80


def race_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """The competition, as numbers, read from the event stream only.

    Everything here is a count of a thing that happened. **Nothing in this
    module, or anywhere upstream of it, prefers a close race**: `genuine` asks
    whether the second colour was in the race at all, never whether it nearly
    won, because a gate that rewarded a narrow finish would quietly become a
    filter for arranged ones. `win_margin_seconds` and the lead-change counts
    are reported so a human can pick an exciting seed by eye; no automatic step
    ranks on them.
    """
    teams = list(visual.TEAM_NAMES)
    count = len(teams)
    escape = next(
        (e for e in reversed(document["events"]) if e["kind"] == "escape"), None)
    summary = document["summary"]
    population = [0] * count
    for ball in document["balls"]:
        population[int(ball["team_id"])] += 1
    total = sum(population) or 1

    winner = None if escape is None else int(escape["team_id"])
    loser = None if winner is None else (winner + 1) % count
    frontier = list(summary.get("team_frontier", [0] * count))

    first_spawn: list[float | None] = [None] * count
    for event in document["events"]:
        if event["kind"] != "ball_spawn":
            continue
        team = int(event["team_id"])
        if first_spawn[team] is None:
            first_spawn[team] = float(event["t"])
    seen = [t for t in first_spawn if t is not None]
    first_to_clone = (
        None if not seen
        else min(range(count), key=lambda i: (
            math.inf if first_spawn[i] is None else first_spawn[i], i))
    )

    cross_team = 0
    stolen = 0
    for event in document["events"]:
        if event["kind"] != "panel_break":
            continue
        paid = list(event["team_contributors"])
        if sum(1 for c in paid if c > 0) > 1:
            cross_team += 1
        largest = event["largest_team"]
        if largest is not None and int(largest) != int(event["team_id"]):
            stolen += 1

    share = None if winner is None else population[winner] / total
    reason = ""
    genuine = True
    if winner is None:
        genuine = False
        reason = "no colour reached the escape radius"
    elif frontier[loser] < MIN_LOSER_FRONTIER:
        genuine = False
        reason = (
            f"the losing colour never got past region {frontier[loser]}, "
            f"so there was no race to watch")
    elif share is not None and share > MAX_WINNER_POPULATION_SHARE:
        genuine = False
        reason = (
            f"the winning colour holds {share * 100:.0f}% of the population, "
            f"so the other one is a passenger")

    return {
        "seed": int(document["seed"]),
        "teams": teams,
        "winner": winner,
        "winner_name": None if winner is None else teams[winner],
        "winner_ball": summary.get("escape_ball"),
        "winner_generation": summary.get("winner_generation"),
        "winner_route": summary.get("winner_route"),
        "win_margin_seconds": summary.get("win_margin_seconds"),
        "population_by_team": population,
        "winner_population_share": share,
        "frontier_by_team": frontier,
        "loser_frontier": None if loser is None else frontier[loser],
        "damage_by_team": list(summary.get("team_damage", [0.0] * count)),
        "breaks_by_team": list(summary.get("team_breaks", [0] * count)),
        "spawns_by_team": list(summary.get("team_spawns", [0] * count)),
        "first_spawn_by_team": first_spawn,
        "first_to_clone": first_to_clone,
        "first_to_clone_name": None if first_to_clone is None else teams[first_to_clone],
        "population_lead_changes": int(summary.get("population_lead_changes", 0)),
        "frontier_lead_changes": int(summary.get("frontier_lead_changes", 0)),
        "max_population_lead": int(summary.get("max_population_lead", 0)),
        "cross_team_breaks": cross_team,
        "stolen_breaks": stolen,
        "genuine": genuine,
        "reason": reason,
    }


# --------------------------------------------------------------------------
# Multiplication: the moment the redesign depends on
# --------------------------------------------------------------------------

#: Two balls read as two once their centres are this many drawn radii apart.
#: A drawn ball is BALL_DRAW_SCALE times the physical radius, so at 2.0 the
#: discs are exactly tangent and the gap opens from there.
SPAWN_SEPARATION_RADII = 2.0

#: How long a split may take to reach that separation and still be read as a
#: split rather than as a ball that wobbled. The spawn flash runs for 0.30 s,
#: so a pair that separates inside 0.50 s is apart while the cue is still
#: fading and the eye is still on it.
SPAWN_READ_LIMIT_SECONDS = 0.50

#: How far a lower-tier cue must sit above a split's own announcement before
#: it counts as burying it. Level differences under about a decibel are not
#: reliably heard inside a dense mix, so a smaller margin would be reporting
#: arithmetic rather than anything a listener could notice.
SPAWN_BURIAL_MARGIN_DB = 1.5

#: A spawn this close to the end of the run lands underneath the escape payoff.
#: It is reported separately rather than counted as a readability failure: by
#: then the viewer is being shown the resolution, not asked to count balls.
SPAWN_ENDGAME_SECONDS = 0.50


def _positions_at(document: Mapping[str, Any], t: float) -> dict[int, tuple[float, float]]:
    from satisfying.multishell_playback import position_at
    out: dict[int, tuple[float, float]] = {}
    for ball in document["balls"]:
        ball_id = int(ball["ball_id"])
        point = position_at(dict(document), ball_id, t)
        if point is not None:
            out[ball_id] = point
    return out


def spawn_report(document: Mapping[str, Any],
                 config: AVConfig = CONFIG) -> dict[str, Any]:
    """Whether a split reads, as geometry and as a cue that owns its instant.

    The brief asks one question at the first spawn - would a viewer see that
    one ball became two - and it is not answerable by counting events, because
    two balls that leave the split point along nearly the same heading are two
    records and one dot. So the geometric half of this measures the separation
    the pair actually reaches while the spawn flash is still lit.

    The other half is competition. A split is announced by a flash and a
    branching flourish, and if a collision lands on the same instant the
    flourish is one voice among several. Counting what else sounds inside the
    flash is how that gets checked without claiming to know what it sounds like.
    """
    spawns = [e for e in document["events"] if e["kind"] == "ball_spawn"]
    if not spawns:
        raise AVIntegrationError("a multiplying-shell candidate must split")
    plan = score.schedule(document, score.named_config(config.audio))
    drawn_radius = float(document["config"]["ball_radius"]) * visual.BALL_DRAW_SCALE
    collision_times = [float(e["t"]) for e in document["events"]
                       if e["kind"] == "collision"]

    duration = float(document["summary"]["duration"])
    gate_units = SPAWN_SEPARATION_RADII * drawn_radius

    def separation_at(child: int, parent: int, t: float) -> float:
        here = _positions_at(document, t)
        if child not in here or parent not in here:
            return 0.0
        return math.hypot(here[child][0] - here[parent][0],
                          here[child][1] - here[parent][1])

    rows: list[dict[str, Any]] = []
    for event in spawns:
        at = float(event["t"])
        child = int(event["ball_id"])
        parent = int(event["parent_id"])

        # When the pair first stands apart, searched on the 30 fps grid rather
        # than sampled at one arbitrary instant. The separation is not monotone
        # - either ball can bounce back toward the other - so this is the first
        # crossing, which is what the eye gets.
        reads_at: float | None = None
        for step_index in range(1, int(1.5 * 30) + 1):
            t = at + step_index / 30.0
            if t > duration:
                break
            if separation_at(child, parent, t) >= gate_units:
                reads_at = t - at
                break

        audio = next((a for a in plan.events
                      if a.kind == "spawn" and int(a.ball_id) == child), None)
        competing = [
            a for a in plan.events
            if a.kind != "spawn"
            and abs(a.source_seconds - at) <= 0.5 * visual.SPAWN_FLASH_SECONDS
        ]
        loudest_competitor = max((a.gain for a in competing), default=0.0)
        # A lift or a break sounding over a spawn is the hierarchy working:
        # arriving in a new shell and cracking a panel are both larger events
        # than one more ball, and Phase 2B ducks a lift-carrying spawn by
        # 3.1 dB on purpose to keep that order audible. A spawn losing to a
        # *collision* is the only version of this that is a fault, because a
        # bounce is the smallest thing in the mix.
        #
        # Two things have to be right for this to mean anything. A split that
        # carries a lift is announced by the *pair* - the lift is the loud half
        # and the ducked spawn is the detail on top of it - so the cue to
        # compare is the louder of the two, not the ducked spawn alone. And the
        # smaller cue has to win by enough to be heard doing it: a collision
        # 0.3 dB above a spawn is not burying anything.
        spawn_tier = score.EVENT_TIER["spawn"]
        own_lift = max(
            (a.gain for a in competing
             if a.kind == "lift" and abs(a.source_seconds - at) < 1.0e-9),
            default=0.0)
        cue_gain = max(float(audio.gain) if audio is not None else 0.0, own_lift)
        buried = [
            a for a in competing
            if score.EVENT_TIER[a.kind] < spawn_tier
            and cue_gain > 0.0
            and 20.0 * math.log10(a.gain / cue_gain) >= SPAWN_BURIAL_MARGIN_DB
        ]
        endgame = at >= duration - SPAWN_ENDGAME_SECONDS
        rows.append({
            "t": at,
            "child_id": child,
            "parent_id": parent,
            "generation": int(event["generation"]),
            "population_after": int(event["population"]),
            "separation_at_birth_radii": (
                separation_at(child, parent, at) / drawn_radius),
            "separation_at_flash_end_radii": (
                separation_at(child, parent, at + visual.SPAWN_FLASH_SECONDS)
                / drawn_radius),
            "seconds_to_read_as_two": reads_at,
            "reads_as_two": reads_at is not None and reads_at <= SPAWN_READ_LIMIT_SECONDS,
            "in_endgame": endgame,
            "audio_gain": float(audio.gain) if audio is not None else 0.0,
            "with_lift": bool(audio.with_lift) if audio is not None else False,
            "competing_voices": len(competing),
            "loudest_competitor_gain": loudest_competitor,
            "spawn_is_loudest": (
                float(audio.gain) >= loudest_competitor if audio is not None else False),
            "outranked_by_design": (
                audio is not None and float(audio.gain) < loudest_competitor
                and not buried),
            "buried_by_a_smaller_cue": bool(buried),
            "collision_within_80ms": any(
                abs(t - at) <= 0.08 for t in collision_times),
        })

    first = rows[0]
    watched = [row for row in rows if not row["in_endgame"]]
    slow = [row for row in watched if not row["reads_as_two"]]
    return {
        "seed": int(document["seed"]),
        "spawns": len(rows),
        "spawns_in_endgame": sum(1 for row in rows if row["in_endgame"]),
        "first_spawn_seconds": first["t"],
        "first_spawn_within_target": first["t"] <= FIRST_SPLIT_TARGET_SECONDS,
        "first_spawn_within_limit": first["t"] <= FIRST_SPLIT_LIMIT_SECONDS,
        "first_spawn_reads_as_two": first["reads_as_two"],
        "first_spawn_seconds_to_read": first["seconds_to_read_as_two"],
        "first_spawn_population_after": first["population_after"],
        "watched_spawns": len(watched),
        "watched_spawns_reading_as_two": len(watched) - len(slow),
        "watched_spawns_reading_as_two_fraction": (
            (len(watched) - len(slow)) / len(watched) if watched else 0.0),
        "slowest_read_seconds": max(
            (row["seconds_to_read_as_two"] for row in watched
             if row["seconds_to_read_as_two"] is not None), default=None),
        "spawns_carrying_a_lift": sum(1 for row in rows if row["with_lift"]),
        "spawns_outranked_by_design": sum(
            1 for row in rows if row["outranked_by_design"]),
        "spawns_buried_by_a_smaller_cue": sum(
            1 for row in rows if row["buried_by_a_smaller_cue"]),
        "separation_gate_drawn_radii": SPAWN_SEPARATION_RADII,
        "read_limit_seconds": SPAWN_READ_LIMIT_SECONDS,
        "detail": rows,
    }


# --------------------------------------------------------------------------
# Population: the redesign can fail by succeeding too well
# --------------------------------------------------------------------------

#: Balls whose drawn discs overlap this much read as one blob. Centres closer
#: than two drawn radii are touching; 1.5 is well inside that.
PILE_SEPARATION_DRAWN_RADII = 1.5

#: A pile has to be at least this many balls to be worth reporting, and has to
#: last long enough to be seen rather than passed through.
PILE_MINIMUM_BALLS = 3
PILE_MINIMUM_SECONDS = 0.20


def population_report(document: Mapping[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Escalation, and the pile that escalation can turn into.

    The brief names a known 7-ball pile on seed 7183 lasting about 1.63 s and
    asks whether the integrated playback makes it acceptable. A pile is not a
    population count - fifteen balls spread around a wide outer shell read fine
    - it is a set of balls whose drawn discs sit on top of each other for long
    enough to stop being individuals. So this walks the frame grid, groups
    balls by drawn-disc overlap, and reports the runs.
    """
    duration = float(document["summary"]["duration"])
    drawn_radius = float(document["config"]["ball_radius"]) * visual.BALL_DRAW_SCALE
    gate = PILE_SEPARATION_DRAWN_RADII * drawn_radius
    step = 1.0 / fps

    samples = int(math.ceil(duration / step)) + 1
    biggest_cluster: list[tuple[float, int]] = []
    for index in range(samples):
        t = index * step
        here = _positions_at(document, t)
        ids = sorted(here)
        # Single-link grouping: a ball joins a group if it overlaps any member.
        parent = {ball_id: ball_id for ball_id in ids}

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if math.hypot(here[a][0] - here[b][0], here[a][1] - here[b][1]) <= gate:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
        sizes: dict[int, int] = {}
        for ball_id in ids:
            root = find(ball_id)
            sizes[root] = sizes.get(root, 0) + 1
        biggest_cluster.append((t, max(sizes.values(), default=0)))

    # Runs where the biggest cluster stays at or above the reporting threshold.
    piles: list[dict[str, Any]] = []
    run_start: float | None = None
    run_peak = 0
    for t, size in biggest_cluster:
        if size >= PILE_MINIMUM_BALLS:
            if run_start is None:
                run_start = t
                run_peak = size
            run_peak = max(run_peak, size)
        elif run_start is not None:
            length = t - run_start
            if length >= PILE_MINIMUM_SECONDS:
                piles.append({"start": run_start, "seconds": length, "peak_balls": run_peak})
            run_start = None
            run_peak = 0
    if run_start is not None:
        length = biggest_cluster[-1][0] - run_start
        if length >= PILE_MINIMUM_SECONDS:
            piles.append({"start": run_start, "seconds": length, "peak_balls": run_peak})

    samples_by_phase = {}
    for name, lo, hi in _phase_bounds(duration):
        counts = [n for t, n in _population_curve(document, fps) if lo <= t < hi]
        samples_by_phase[name] = {
            "min": min(counts, default=0),
            "max": max(counts, default=0),
            "mean": sum(counts) / len(counts) if counts else 0.0,
        }

    return {
        "seed": int(document["seed"]),
        "fps": fps,
        "final_population": len(document["balls"]),
        "peak_cluster_balls": max((n for _, n in biggest_cluster), default=0),
        "piles": piles,
        "pile_count": len(piles),
        "longest_pile_seconds": max((p["seconds"] for p in piles), default=0.0),
        "worst_pile_balls": max((p["peak_balls"] for p in piles), default=0),
        "pile_seconds_total": sum(p["seconds"] for p in piles),
        "pile_fraction_of_clip": sum(p["seconds"] for p in piles) / duration,
        "population_by_phase": samples_by_phase,
        "separation_gate_drawn_radii": PILE_SEPARATION_DRAWN_RADII,
    }


def _phase_bounds(duration: float) -> tuple[tuple[str, float, float], ...]:
    """The brief's retention phases, in seconds, clipped to the run.

    These are the brief's own boundaries - hook, growth, escalation, hard outer
    wall - and not a rescaling of the duration, because the question they are
    asked is about what a viewer has seen by a wall-clock moment.
    """
    return (
        ("hook", 0.0, min(3.0, duration)),
        ("growth", min(3.0, duration), min(8.0, duration)),
        ("escalation", min(8.0, duration), min(15.0, duration)),
        ("outer_wall", min(15.0, duration), duration),
    )


def _population_curve(document: Mapping[str, Any], fps: float) -> list[tuple[float, int]]:
    births = sorted(float(b["birth_time"]) for b in document["balls"])
    duration = float(document["summary"]["duration"])
    step = 1.0 / fps
    out: list[tuple[float, int]] = []
    for index in range(int(math.ceil(duration / step)) + 1):
        t = index * step
        out.append((t, sum(1 for birth in births if birth <= t)))
    return out


# --------------------------------------------------------------------------
# The central hypothesis: sparse, then growing, then rich
# --------------------------------------------------------------------------

#: The longest stretch with no canonical event that still reads as tension
#: rather than as the clip having stopped.
#:
#: Set at 1.5 s deliberately, and it does not discriminate: the seven
#: candidates all sit between 0.87 s and 1.11 s, which is one crossing of the
#: opened-out arena at the frozen speed and is the mechanic's natural rhythm
#: rather than a stall. A 1.0 s gate would split that uniform population on
#: noise and reject three candidates for having an ordinary flight in them.
DEAD_AIR_SECONDS = 1.5


def retention_report(document: Mapping[str, Any],
                     config: AVConfig = CONFIG) -> dict[str, Any]:
    """The brief's four phases, measured against what a viewer would have seen.

    This is the test of the redesign itself rather than of any one seed: the
    concept only works if the clip is visibly simple early, visibly growing in
    the middle, and visibly and audibly crowded late. The numbers here can
    falsify that - a flat population curve or a late stretch quieter than the
    opening would - but they cannot confirm that it *feels* like escalation,
    which is left to the review renders.
    """
    plan = score.schedule(document, score.named_config(config.audio))
    duration = float(document["summary"]["duration"])
    events = document["events"]
    births = sorted(float(b["birth_time"]) for b in document["balls"])

    phases: dict[str, Any] = {}
    for name, lo, hi in _phase_bounds(duration):
        span = max(hi - lo, 1.0e-9)
        window = [e for e in events if lo <= float(e["t"]) < hi]
        audio_here = [a for a in plan.events if lo <= a.source_seconds < hi]
        voice_seconds = sum(
            max(0.0, min(hi, a.end_seconds) - max(lo, a.source_seconds))
            for a in plan.events
            if a.end_seconds > lo and a.source_seconds < hi)
        phases[name] = {
            "start": lo,
            "end": hi,
            "seconds": span,
            "population_at_end": sum(1 for birth in births if birth <= hi),
            "collisions": sum(1 for e in window if e["kind"] == "collision"),
            "spawns": sum(1 for e in window if e["kind"] == "ball_spawn"),
            "near_misses": sum(1 for e in window if e["kind"] == "near_miss"),
            "damage_states": sum(1 for e in window if e["kind"] == "damage_state"),
            "breaks": sum(1 for e in window if e["kind"] == "panel_break"),
            "shell_exits": sum(1 for e in window if e["kind"] == "shell_exit"),
            "audio_events": len(audio_here),
            "audio_event_density_hz": len(audio_here) / span,
            "voice_seconds": voice_seconds,
            "mean_polyphony": voice_seconds / span,
        }

    # Dead air: the longest gap between consecutive canonical events. A clip
    # that stalls does it here, and it is the one thing a population curve
    # cannot show.
    times = sorted(float(e["t"]) for e in events)
    gaps = [(b - a, a) for a, b in zip(times, times[1:])]
    longest_gap, longest_gap_at = max(gaps, default=(0.0, 0.0))

    hook = phases["hook"]
    outer = phases["outer_wall"]
    escalates = (
        outer["mean_polyphony"] > hook["mean_polyphony"]
        and outer["population_at_end"] > hook["population_at_end"]
    )
    return {
        "seed": int(document["seed"]),
        "duration_seconds": duration,
        "phases": phases,
        "first_collision_seconds": next(
            (float(e["t"]) for e in events if e["kind"] == "collision"), None),
        "first_spawn_seconds": next(
            (float(e["t"]) for e in events if e["kind"] == "ball_spawn"), None),
        "first_break_seconds": next(
            (float(e["t"]) for e in events if e["kind"] == "panel_break"), None),
        "hook_has_collision": hook["collisions"] > 0,
        "hook_has_spawn": hook["spawns"] > 0,
        "growth_multiplies": phases["growth"]["population_at_end"] > 1,
        "escalates_to_outer_wall": escalates,
        "polyphony_hook": hook["mean_polyphony"],
        "polyphony_outer": outer["mean_polyphony"],
        "polyphony_growth_ratio": (
            outer["mean_polyphony"] / hook["mean_polyphony"]
            if hook["mean_polyphony"] > 0 else float("inf")),
        "longest_event_gap_seconds": longest_gap,
        "longest_event_gap_at": longest_gap_at,
        "dead_air": longest_gap > DEAD_AIR_SECONDS,
        "dead_air_limit_seconds": DEAD_AIR_SECONDS,
    }


def density_report(document: Mapping[str, Any],
                   config: AVConfig = CONFIG) -> dict[str, Any]:
    """Whether late richness is rich or merely loud.

    Phase 2B measured the whole clip and passed: 7.70 to 11.34 events per
    second, 8 to 10 voices at peak, a median of 2 to 3, and no contact under a
    +3 dB onset rise. The brief asks the question again with the picture
    attached, and the thing that would distinguish exciting from cluttered is
    not the average - it is whether the peak arrives where the story is, and
    whether the collisions that carry it are still individually audible when
    the population is at its largest.
    """
    plan = score.schedule(document, score.named_config(config.audio))
    metrics = plan.metrics
    duration = float(document["summary"]["duration"])

    # A one-second sliding window over the whole schedule, so the peak is found
    # where it is rather than averaged away by the quiet opening.
    times = sorted(a.source_seconds for a in plan.events)
    peak = 0
    peak_at = 0.0
    for index, start in enumerate(times):
        count = 0
        for other in times[index:]:
            if other - start > 1.0:
                break
            count += 1
        if count > peak:
            peak, peak_at = count, start

    late_start = duration * 0.65
    late = [a for a in plan.events if a.source_seconds >= late_start]
    early = [a for a in plan.events if a.source_seconds < duration * 0.25]
    collisions_late = [a for a in late if a.kind == "collision"]
    return {
        "seed": int(document["seed"]),
        "event_density_hz": metrics["event_density_hz"],
        "collision_density_hz": metrics["collision_density_hz"],
        "peak_events_per_second": peak,
        "peak_at_seconds": peak_at,
        "peak_in_final_third": peak_at >= late_start,
        "max_polyphony": metrics["max_scheduled_polyphony"],
        "median_polyphony": metrics["median_scheduled_polyphony"],
        "mean_polyphony": metrics["mean_scheduled_polyphony"],
        "simultaneous_within_cluster": metrics["simultaneous_within_cluster"],
        "cluster_nudged": metrics["cluster_nudged"],
        "repeat_nudged": metrics["repeat_nudged"],
        "longest_same_pitch_run": metrics["longest_same_pitch_run"],
        "minimum_collision_gap_seconds": metrics["minimum_collision_gap_seconds"],
        "median_collision_gap_seconds": metrics["median_collision_gap_seconds"],
        "collision_voice_seconds_median": metrics["collision_voice_seconds_median"],
        "early_events": len(early),
        "late_events": len(late),
        "late_over_early": (len(late) / len(early)) if early else float("inf"),
        "late_collision_count": len(collisions_late),
        # A collision whose voice outlasts the gap to the next one is still
        # ringing when the next arrives. Some of that is the point; all of it
        # would be mud, so the fraction is what matters.
        "late_collisions_overlapping_next": sum(
            1 for a, b in zip(collisions_late, collisions_late[1:])
            if a.end_seconds > b.source_seconds),
        "late_overlap_fraction": (
            sum(1 for a, b in zip(collisions_late, collisions_late[1:])
                if a.end_seconds > b.source_seconds)
            / max(1, len(collisions_late) - 1)),
    }


# --------------------------------------------------------------------------
# One row per candidate, and the rejection rule
# --------------------------------------------------------------------------


def candidate_row(document: Mapping[str, Any], fps: float = 30.0,
                  config: AVConfig = CONFIG) -> dict[str, Any]:
    """Every axis the brief asks to compare, kept apart.

    Deliberately not reduced to a score. The brief forbids one, and it is right
    to: a seed can be the best on population and the worst on crowding, and a
    single number would hide exactly the trade the selection has to make.
    """
    sync = sync_audit(document, fps, config=config)
    race = race_report(document)
    camera = camera_report(document, fps)
    spawn = spawn_report(document, config)
    population = population_report(document, fps)
    retention = retention_report(document, config)
    density = density_report(document, config)
    teams = team_audit(document, config)
    summary = document["summary"]
    escape = next(
        (event for event in reversed(document["events"]) if event["kind"] == "escape"),
        {},
    )
    escape_generation = escape.get("generation")

    reasons: list[str] = []
    if not spawn["first_spawn_within_limit"]:
        reasons.append(
            f"first split at {spawn['first_spawn_seconds']:.2f}s is later than "
            f"the {FIRST_SPLIT_LIMIT_SECONDS:.1f}s limit")
    if population["worst_pile_balls"] >= 5:
        reasons.append(
            f"a {population['worst_pile_balls']}-ball pile holds for "
            f"{population['longest_pile_seconds']:.2f}s")
    if not retention["escalates_to_outer_wall"]:
        reasons.append("the outer wall is not busier than the hook")
    if retention["dead_air"]:
        reasons.append(
            f"a {retention['longest_event_gap_seconds']:.2f}s gap with no event "
            f"at {retention['longest_event_gap_at']:.1f}s")
    if spawn["spawns_buried_by_a_smaller_cue"] > 0:
        reasons.append(
            f"{spawn['spawns_buried_by_a_smaller_cue']} spawn(s) lose to a collision")
    if not camera["within_velocity_limit"]:
        reasons.append("a reframe outpaces the ball at its fastest")
    if camera["static_tail_seconds"] < MIN_STATIC_TAIL_SECONDS:
        reasons.append(
            f"the camera is still moving {camera['static_tail_seconds']:.2f}s "
            f"before the escape")
    if not sync["pass"]:
        reasons.append("A/V synchronisation does not hold")
    if not teams["pass"]:
        reasons.append("the two layers do not agree on the cast or the colours")
    if not race["genuine"]:
        reasons.append(race["reason"])

    return {
        "seed": int(document["seed"]),
        "duration_seconds": float(summary["duration"]),
        "escape_route": str(escape.get("route", "")),
        "escape_generation": escape_generation,
        "escape_by": (
            None if escape_generation is None
            else "founder" if int(escape_generation) == 0 else "descendant"
        ),
        # frame-one appeal and the hook
        "first_collision_seconds": retention["first_collision_seconds"],
        "first_split_seconds": spawn["first_spawn_seconds"],
        "hook_collisions": retention["phases"]["hook"]["collisions"],
        "hook_spawns": retention["phases"]["hook"]["spawns"],
        # multiplication
        "population": len(document["balls"]),
        "generations": teams["generations"],
        "population_by_team": teams["population_by_team"],
        # the race
        "winner": race["winner_name"],
        "winner_generation": race["winner_generation"],
        "winner_route": race["winner_route"],
        "win_margin_seconds": race["win_margin_seconds"],
        "population_lead_changes": race["population_lead_changes"],
        "frontier_lead_changes": race["frontier_lead_changes"],
        "max_population_lead": race["max_population_lead"],
        "winner_population_share": race["winner_population_share"],
        "cross_team_breaks": race["cross_team_breaks"],
        "stolen_breaks": race["stolen_breaks"],
        "damage_by_team": race["damage_by_team"],
        "first_to_clone": race["first_to_clone_name"],
        "first_split_reads": spawn["first_spawn_reads_as_two"],
        "first_split_reads_in_seconds": spawn["first_spawn_seconds_to_read"],
        "splits_reading_as_two_fraction": spawn["watched_spawns_reading_as_two_fraction"],
        "slowest_split_read_seconds": spawn["slowest_read_seconds"],
        # camera
        "camera_transitions": camera["transitions"],
        "camera_peak_velocity": camera["max_screen_velocity_per_second"],
        "camera_within_limit": camera["within_velocity_limit"],
        "camera_overlapping_transitions": camera["overlapping_transitions"],
        "spawns_inside_transitions": camera["spawns_inside_transitions"],
        "static_tail_seconds": camera["static_tail_seconds"],
        # damage and breaks
        "damage_states": sum(1 for e in document["events"] if e["kind"] == "damage_state"),
        "breaks": sum(1 for e in document["events"] if e["kind"] == "panel_break"),
        "near_misses": sum(1 for e in document["events"] if e["kind"] == "near_miss"),
        # crowding
        "peak_cluster_balls": population["peak_cluster_balls"],
        "pile_count": population["pile_count"],
        "longest_pile_seconds": population["longest_pile_seconds"],
        "pile_fraction_of_clip": population["pile_fraction_of_clip"],
        # music
        "event_density_hz": density["event_density_hz"],
        "peak_events_per_second": density["peak_events_per_second"],
        "peak_in_final_third": density["peak_in_final_third"],
        "max_polyphony": density["max_polyphony"],
        "median_polyphony": density["median_polyphony"],
        "late_overlap_fraction": density["late_overlap_fraction"],
        "polyphony_growth_ratio": retention["polyphony_growth_ratio"],
        "spawns_buried_by_a_smaller_cue": spawn["spawns_buried_by_a_smaller_cue"],
        # pacing
        "longest_event_gap_seconds": retention["longest_event_gap_seconds"],
        "longest_event_gap_at": retention["longest_event_gap_at"],
        "escalates": retention["escalates_to_outer_wall"],
        # contracts
        "sync_pass": sync["pass"],
        "max_sync_error_frames": sync["maximum_sync_error_frames"],
        "mean_sync_error_frames": sync["mean_sync_error_frames"],
        "team_pass": teams["pass"],
        "playback_digest": str(document["digest"]),
        # verdict
        "rejection_reasons": reasons,
        "eligible": not reasons,
    }


# --------------------------------------------------------------------------
# Stills for the human review
# --------------------------------------------------------------------------


def av_moments(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Eleven canonical, event-derived views required for Phase 4A review.

    Every one is the time of a *canonical event* plus a small fixed offset, so
    a contact sheet is a set of instants the simulation chose and not a set a
    person picked to flatter it. Four of the eleven are new for the two-team
    rule: both colours multiplying, the first lead change, the first moment
    both colours are working the final wall, and the last frame of the run.
    """
    events = list(document["events"])
    duration = float(document["summary"]["duration"])

    def first(kind: str, predicate=None) -> Mapping[str, Any] | None:
        return next(
            (event for event in events
             if event["kind"] == kind and (predicate is None or predicate(event))),
            None,
        )

    spawn = first("ball_spawn")
    eight = first("ball_spawn", lambda event: int(event["population"]) >= 8)

    # The first instant *both* colours have reproduced. The rule is symmetric,
    # so this is the frame that says so.
    team_count = len(visual.TEAM_NAMES)
    spawned = [0] * team_count
    both_multiplying = None
    for event in events:
        if event["kind"] != "ball_spawn":
            continue
        spawned[int(event["team_id"])] += 1
        if all(spawned):
            both_multiplying = event
            break

    # The first population lead change, read from the spawn stream the same way
    # the simulation counts it. A run with no lead change falls back to the
    # first moment the lead is at its widest, which is the opposite reading and
    # is labelled as such.
    lead_change = None
    widest = None
    counts = [1] * team_count
    sign = 0
    best = 0
    for event in events:
        if event["kind"] != "ball_spawn":
            continue
        counts[int(event["team_id"])] += 1
        lead = counts[0] - counts[1]
        if abs(lead) > best:
            best = abs(lead)
            widest = event
        now = (lead > 0) - (lead < 0)
        if now:
            if sign and now != sign and lead_change is None:
                lead_change = event
            sign = now

    critical = first(
        "damage_state", lambda event: event.get("new_state") == "critical")
    first_break = first("panel_break")
    escape = first("escape")

    # Find a naturally cooperative panel. Prefer the outer wall and show the
    # instant the second distinct ball joins its ledger, not the final hit; that
    # makes the cumulative sequence visible instead of duplicating the break.
    contributors: dict[tuple[int, int], set[int]] = {}
    second_contributor_hit: dict[tuple[int, int], Mapping[str, Any]] = {}
    cooperative_breaks: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for event in events:
        if event["kind"] == "damage" and float(event.get("contribution", 0.0)) > 0.0:
            key = (int(event["shell_id"]), int(event["panel_id"]))
            paid = contributors.setdefault(key, set())
            before = len(paid)
            paid.add(int(event["ball_id"]))
            if before == 1 and len(paid) == 2:
                second_contributor_hit[key] = event
        elif event["kind"] == "panel_break":
            key = (int(event["shell_id"]), int(event["panel_id"]))
            if len(contributors.get(key, set())) > 1 and key in second_contributor_hit:
                cooperative_breaks.append((event, second_contributor_hit[key]))

    # The late high-pop view is the first spawn reaching the run's maximum.
    peak_population = int(document["summary"]["max_population"])
    late_population = first(
        "ball_spawn", lambda event: int(event["population"]) >= peak_population)

    # First real contact with the hardest shell; this is the outer-wall attack,
    # not a camera-schedule proxy.
    outer_id = len(document["shells"]) - 1
    outer_attack = first(
        "collision", lambda event: int(event["shell_id"]) == outer_id)
    # The first panel of the *outermost* shell to take visible damage: the
    # "how are they going to get through that" frame, which is a different
    # moment from the first damaged panel anywhere.
    #
    # It can be absent. `damaged` begins at 24% of a threshold of 15.0, so a
    # panel of the final wall needs roughly eighteen ordinary hits before it
    # shows a crack, and in several of the review candidates no single panel of
    # it ever does - the winner threads the moving opening without softening
    # anything. The fallback is the first contact with that wall, which is the
    # same beat with a weaker version of the same read, and `why` says which
    # one the sheet is showing.
    outer_damaged = first(
        "damage_state",
        lambda event: (int(event["shell_id"]) == outer_id
                       and event.get("new_state") == "critical"),
    ) or first(
        "damage_state",
        lambda event: (int(event["shell_id"]) == outer_id
                       and event.get("new_state") == "damaged"),
    )

    # The first instant both colours are hitting the final wall. This is the
    # climax the two-team rule produces and the single frame most worth a
    # human's attention.
    seen_outer: set[int] = set()
    both_on_outer = None
    for event in events:
        if event["kind"] != "collision" or int(event["shell_id"]) != outer_id:
            continue
        seen_outer.add(int(event["team_id"]))
        if len(seen_outer) == team_count:
            both_on_outer = event
            break

    final_exit = None
    escape_ball = int(escape["ball_id"]) if escape is not None else -1
    for event in events:
        if (event["kind"] == "shell_exit"
                and int(event["shell_id"]) == outer_id
                and int(event["ball_id"]) == escape_ball):
            final_exit = event
    # A child born outside the final shell can be the first ball to reach the
    # escape radius. In that case its parent's immediately preceding outer exit
    # is the decisive passage the climax must show.
    if final_exit is None and escape is not None:
        final_exit = next(
            (event for event in reversed(events)
             if event["kind"] == "shell_exit"
             and int(event["shell_id"]) == outer_id
             and float(event["t"]) <= float(escape["t"])),
            None,
        )

    outer_cooperative = [
        pair for pair in cooperative_breaks if int(pair[0]["shell_id"]) == outer_id
    ]
    chosen_cooperative = (outer_cooperative[-1] if outer_cooperative
                          else cooperative_breaks[0] if cooperative_breaks else None)
    cooperative_damage = chosen_cooperative[1] if chosen_cooperative else None

    final_decisive = final_exit
    if final_exit is not None and final_exit.get("route") == "break":
        key = (int(final_exit["shell_id"]), int(final_exit["panel_id"]))
        final_decisive = next(
            (event for event in reversed(events)
             if event["kind"] == "panel_break"
             and (int(event["shell_id"]), int(event["panel_id"])) == key
             and float(event["t"]) <= float(final_exit["t"])),
            final_exit,
        )

    # Every view except the escape and the final frame is a view of the *race*,
    # so it is clamped to before the escape. Without this the small forward
    # offsets can push a still past the end: on seed 17964 the population peaks
    # 0.09 s before the winner leaves, and `late_high_population` + 0.12 s
    # landed 0.03 s *after* it - a tile captioned "the late population peak"
    # showing the payoff banner instead.
    RACE_LIMIT = max(0.0, duration - 0.04)

    def at(event: Mapping[str, Any] | None, offset: float = 0.0,
           limit: float | None = None) -> float:
        ceiling = duration + visual.RELEASE_SECONDS if limit is None else limit
        return min(ceiling, max(0.0, float(event["t"]) + offset)) if event else 0.0

    def during(event: Mapping[str, Any] | None, offset: float = 0.0) -> float:
        return at(event, offset, RACE_LIMIT)

    rows = [
        ("two_founders", 0.0, "frame zero: one cyan, one orange, nothing else"),
        ("first_clone", during(spawn, 0.10), "the first canonical reproduction"),
        ("both_teams_multiplying", during(both_multiplying, 0.12),
         "both colours have now reproduced"),
        ("first_lead_change", during(lead_change or widest, 0.12),
         "the first population lead change"
         if lead_change is not None
         else "no lead change: the widest population lead instead"),
        ("eight_ball_state", during(eight, 0.12), "the race at eight balls"),
        ("shared_panel_damage", during(cooperative_damage, 0.04),
         "a second ball joins a panel's ledger"),
        ("critical_outer_panel", during(outer_damaged or outer_attack, 0.06),
         "a panel of the final wall takes visible damage"
         if outer_damaged is not None
         else "no panel of the final wall ever cracked: first contact instead"),
        ("late_high_population", during(late_population, 0.12),
         "the late population peak, both colours on screen"),
        ("final_wall_struggle", during(both_on_outer or outer_attack, 0.10),
         "both colours working the outermost barrier"),
        ("winning_escape", at(escape, 0.10), "the first genuine final escape"),
        ("winner_frame", duration + visual.RELEASE_SECONDS,
         "the last frame: the payoff in the winning colour"),
    ]
    # Preserve semantic names while numbering by narrative order. Several
    # events may happen close together; names, not timestamps, define the sheet.
    return [
        {"name": f"{index:02d}_{name}", "t": t, "why": why}
        for index, (name, t, why) in enumerate(rows, start=1)
    ]
