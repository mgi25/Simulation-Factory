"""Phase 6B tests: the original soundtrack and its exact timeline.

What is testable here is timing, level and determinism - not whether a hit
sounds good. A cue lands on the sample its tick says it does, a soundtrack is
exactly as long as the render it belongs to, nothing clips, and building the
same replay twice produces the same bytes. Whether the result is satisfying
is a listening question and is answered by listening, not by pytest.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from audio import cues, soundtrack, wav_io
from audio.synthesis import (
    CHANNELS,
    SAMPLE_RATE,
    Noise,
    db_to_gain,
    gain_to_db,
    peak,
    stable_seed,
)
from entities.echo_clone import EchoClone
from entities.orbit_orb import OrbitOrb
from entities.projectile import Projectile
from modes.events import EVENT_ELIMINATION, EVENT_HIT, EVENT_POWER_ACTIVATE, HIT_IMPACT
from powers import POWER_NAMES
from replay.exporter import REPLAY_VERSION

SEED = 21465
ARENA_LEFT = 60.0
ARENA_RIGHT = 1020.0
ARENA_CENTRE = 0.5 * (ARENA_LEFT + ARENA_RIGHT)


def event(
    tick: int,
    kind: str,
    subtype: str | None = None,
    *,
    x: float = ARENA_CENTRE,
    y: float = 900.0,
    magnitude: float | None = None,
    source_id: int | None = 0,
    target_id: int | None = 1,
) -> dict:
    """One replay event, in exactly the shape the exporter writes."""
    return {
        "tick": tick,
        "type": kind,
        "x": x,
        "y": y,
        "source_id": source_id,
        "target_id": target_id,
        "subtype": subtype,
        "magnitude": magnitude,
    }


def make_replay(
    *,
    frames: int = 120,
    events: tuple[dict, ...] = (),
    seed: int = SEED,
    physics_hz: int = 120,
    fps: int = 60,
) -> dict:
    """A replay with only the fields a soundtrack reads."""
    ticks_per_frame = physics_hz // fps
    return {
        "version": REPLAY_VERSION,
        "seed": seed,
        "fps": fps,
        "physics_hz": physics_hz,
        "ticks_per_frame": ticks_per_frame,
        "canvas": {"width": 1080, "height": 1920},
        "arena": {
            "left": ARENA_LEFT,
            "top": 380.0,
            "right": ARENA_RIGHT,
            "bottom": 1540.0,
        },
        "frames": [{"tick": index * ticks_per_frame} for index in range(frames)],
        "events": list(events),
        "result": {"winner_id": 0, "is_draw": False, "finished_tick": frames * 2},
    }


# The hand-made sequence the synthetic check is built on: a Rush activation,
# an impact hit, a Pulse hit, an Echo hit, an Orbit hit, and then the lethal
# hit and the elimination it causes - one of every identity that has a sound.
# Spaced 140 ticks apart, which is further than the longest cue, so no two
# can overlap and every expected sample index is readable arithmetic.
SYNTHETIC_EVENTS = (
    event(60, EVENT_POWER_ACTIVATE, "rush", x=ARENA_LEFT + 100.0),
    event(200, EVENT_HIT, HIT_IMPACT, magnitude=34.0),
    event(340, EVENT_HIT, Projectile.kind, magnitude=18.0, x=ARENA_RIGHT - 100.0),
    event(480, EVENT_HIT, EchoClone.kind, magnitude=12.0),
    event(620, EVENT_HIT, OrbitOrb.kind, magnitude=10.0),
    event(760, EVENT_HIT, HIT_IMPACT, magnitude=40.0),
    event(760, EVENT_ELIMINATION, HIT_IMPACT, magnitude=None),
)
SYNTHETIC_FRAMES = 500


def build(replay: dict, frames: int | None = None, **kwargs) -> soundtrack.Soundtrack:
    count = frames if frames is not None else len(replay["frames"]) + 108
    plan = soundtrack.plan_soundtrack(replay, count)
    return soundtrack.build_soundtrack(replay, plan, **kwargs)


def first_signal(
    buffer, floor: float = 1e-9, start: int = 0, stop: int | None = None
) -> int | None:
    """The first index in [start, stop) carrying any signal at all."""
    end = len(buffer) if stop is None else min(stop, len(buffer))
    for index in range(max(0, start), end):
        if abs(buffer[index]) > floor:
            return index
    return None


def build_pair(length: int = 24_000, cue=None, offset: int = 4_000):
    """Two channels holding one loud burst, for testing a stage directly."""
    from array import array

    left = array("d", bytes(8 * length))
    right = array("d", bytes(8 * length))
    if cue is None:
        for index in range(offset, min(length, offset + 8_000)):
            value = 0.75 * math.sin((index - offset) / 55.0)
            left[index] = value
            right[index] = value
    else:
        from audio.synthesis import add_into

        add_into(left, cue.buffer, offset, 1.0)
        add_into(right, cue.buffer, offset, 1.0)
    return left, right


# --- the exact timeline ---------------------------------------------------


def test_the_production_rates_divide_into_whole_samples() -> None:
    """The one arithmetic fact the whole module is built on."""
    assert soundtrack.SAMPLES_PER_FRAME == 800
    assert soundtrack.SAMPLES_PER_TICK == 400
    assert SAMPLE_RATE == 48000
    assert SAMPLE_RATE / soundtrack.VIDEO_FPS == soundtrack.SAMPLES_PER_FRAME
    assert SAMPLE_RATE / soundtrack.PHYSICS_HZ == soundtrack.SAMPLES_PER_TICK
    # Two physics ticks per output frame, which is why events cannot live
    # inside frames in the first place.
    assert soundtrack.SAMPLES_PER_FRAME == 2 * soundtrack.SAMPLES_PER_TICK


def test_a_tick_maps_to_exactly_four_hundred_samples() -> None:
    assert soundtrack.tick_to_sample(0) == 0
    assert soundtrack.tick_to_sample(1) == 400
    assert soundtrack.tick_to_sample(120) == SAMPLE_RATE
    assert soundtrack.tick_to_sample(1013) == 1013 * 400 == 405200


def test_a_frame_maps_to_exactly_eight_hundred_samples() -> None:
    assert soundtrack.frame_to_sample(0) == 0
    assert soundtrack.frame_to_sample(1) == 800
    assert soundtrack.frame_to_sample(60) == SAMPLE_RATE
    assert soundtrack.frame_to_sample(1426) == 1426 * 800


def test_a_tick_and_the_frame_it_falls_in_agree() -> None:
    """Every even tick is a frame boundary; every odd one is half a frame in."""
    for frame in (0, 1, 17, 500):
        assert soundtrack.tick_to_sample(2 * frame) == soundtrack.frame_to_sample(frame)
        between = soundtrack.tick_to_sample(2 * frame + 1)
        assert between - soundtrack.frame_to_sample(frame) == 400
        assert soundtrack.frame_to_sample(frame + 1) - between == 400


def test_a_negative_tick_or_frame_is_refused() -> None:
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.tick_to_sample(-1)
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.frame_to_sample(-1)
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.total_samples(-1)


def test_a_rate_that_does_not_divide_is_refused_rather_than_rounded() -> None:
    """Rounding here would drift, which is the whole thing this format avoids."""
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.samples_per_tick(44100, 120)
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.samples_per_frame(48000, 7)
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.samples_per_frame(48000, 0)


# --- the plan -------------------------------------------------------------


def test_the_soundtrack_is_the_frame_count_times_eight_hundred() -> None:
    plan = soundtrack.plan_soundtrack(make_replay(frames=861), 969)
    assert plan.gameplay_frames == 861
    assert plan.post_roll_frames == 108
    assert plan.total_samples == 969 * 800 == 775200
    assert plan.duration == pytest.approx(969 / 60)


def test_a_built_soundtrack_is_exactly_the_length_it_planned() -> None:
    track = build(make_replay(frames=100, events=SYNTHETIC_EVENTS[:2]), frames=208)
    assert track.sample_count == 208 * 800
    assert len(track.left) == len(track.right) == 208 * 800
    assert track.plan.total_samples == track.sample_count


def test_the_post_roll_is_part_of_the_soundtrack() -> None:
    """Its samples are real samples, not an allowance FFmpeg pads out."""
    replay = make_replay(frames=100)
    gameplay = soundtrack.plan_soundtrack(replay, 100)
    with_tail = soundtrack.plan_soundtrack(replay, 208)
    assert with_tail.post_roll_frames == 108
    assert with_tail.total_samples - gameplay.total_samples == 108 * 800 == 86400


def test_a_render_shorter_than_its_replay_is_refused() -> None:
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.plan_soundtrack(make_replay(frames=100), 99)


def test_a_replay_sampled_at_another_rate_is_refused() -> None:
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.plan_soundtrack(make_replay(frames=20, physics_hz=90, fps=30), 128)


def test_a_replay_with_no_frames_is_refused() -> None:
    replay = make_replay(frames=10)
    replay["frames"] = []
    with pytest.raises(soundtrack.SoundtrackError):
        soundtrack.plan_soundtrack(replay, 108)


# --- event scheduling -----------------------------------------------------


def test_every_event_is_placed_on_its_tick_times_four_hundred() -> None:
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    track = build(replay)
    assert len(track.schedule) == len(SYNTHETIC_EVENTS)
    for cue, source in zip(track.schedule, SYNTHETIC_EVENTS):
        assert cue.tick == source["tick"]
        assert cue.sample == source["tick"] * 400


def test_a_cue_is_silent_before_its_sample_and_audible_at_it() -> None:
    """The synchronisation check, run against silence rather than the bed.

    Nothing may be heard before the sample a tick maps to, and something must
    be heard within a millisecond of it. A cue's very first sample can be zero
    - a sine starts at zero and an attack ramps from it - so the arrival is
    given the millisecond, while the silence before it is exact.
    """
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    track = build(replay, include_ambience=False)
    millisecond = SAMPLE_RATE // 1000

    for cue in track.schedule:
        quiet_from = max(0, cue.sample - 400)
        assert first_signal(track.left, start=quiet_from, stop=cue.sample) is None
        assert first_signal(track.right, start=quiet_from, stop=cue.sample) is None
        arrival = first_signal(track.left, start=cue.sample, stop=cue.sample + millisecond)
        assert arrival is not None, f"{cue.name} never arrived at sample {cue.sample}"
        assert arrival - cue.sample < millisecond


def test_a_visual_frame_samples_the_tick_a_cue_lands_on() -> None:
    """What the half-frame relationship between 120 Hz and 60 Hz means.

    An event on an even tick happens at the exact moment a frame is sampled,
    so sound and picture coincide. An event on an odd tick happens between
    two samples: its sound is exact, and the nearest rendered frame is half a
    frame - 8.3 ms - away. That is the whole of the error, it is a property
    of sampling at 60 Hz rather than a bug, and it is smaller than a frame.
    """
    for tick in (200, 201):
        sample = soundtrack.tick_to_sample(tick)
        seconds = tick / soundtrack.PHYSICS_HZ
        assert sample == round(seconds * SAMPLE_RATE)
        frame = tick // 2
        offset = abs(seconds - frame / soundtrack.VIDEO_FPS)
        assert offset <= 0.5 / soundtrack.VIDEO_FPS
    assert abs(200 / 120 - 100 / 60) == 0.0
    assert abs(201 / 120 - 100 / 60) == pytest.approx(0.5 / 60)


def test_an_event_after_the_last_frame_is_counted_not_moved() -> None:
    """Clamping it onto the final sample would put it at the wrong moment."""
    late = event(100_000, EVENT_HIT, HIT_IMPACT, magnitude=20.0)
    replay = make_replay(frames=100, events=(late,))
    track = build(replay, frames=208)
    assert track.events_total == 1
    assert track.events_past_end == 1
    assert track.schedule == ()


def test_a_cue_whose_tail_runs_past_the_end_is_truncated_not_refused() -> None:
    """The soundtrack has an exact length and nothing may extend it."""
    replay = make_replay(frames=100, events=(event(414, EVENT_ELIMINATION, HIT_IMPACT),))
    track = build(replay, frames=208)
    assert len(track.schedule) == 1
    assert track.sample_count == 208 * 800
    assert track.schedule[0].sample + track.schedule[0].length > track.sample_count


def test_a_moment_with_no_sound_is_counted_rather_than_guessed_at() -> None:
    replay = make_replay(
        frames=100,
        events=(
            event(40, EVENT_POWER_ACTIVATE, "teleport"),
            event(80, "wall_bounce", None),
        ),
    )
    track = build(replay, frames=208)
    assert track.events_total == 2
    assert track.events_unvoiced == 2
    assert track.schedule == ()


def test_an_unknown_hit_subtype_still_makes_a_sound() -> None:
    """A missing hit is a worse lie than a hit with the wrong identity."""
    unknown = event(40, EVENT_HIT, "grapple", magnitude=20.0)
    replay = make_replay(frames=100, events=(unknown,))
    track = build(replay, frames=208)
    assert [cue.name for cue in track.schedule] == [f"hit/{HIT_IMPACT}"]
    assert track.events_unvoiced == 0


def test_the_cue_counts_name_every_identity_that_played() -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    assert track.cue_counts == {
        "activate/rush": 1,
        "elimination": 1,
        "hit/echo": 1,
        "hit/impact": 2,
        "hit/orbit": 1,
        "hit/projectile": 1,
    }


# --- the identities exist for everything the game can do ------------------


def test_every_power_has_an_activation_sound() -> None:
    """Read from the power registry, so adding a power fails this test."""
    assert set(cues.ACTIVATION_CUES) == set(POWER_NAMES)
    for name in POWER_NAMES:
        cue = cues.activation_cue(name, 1)
        assert cue is not None and cue.name == f"activate/{name}"
        assert peak(cue.buffer) > 0.0


def test_every_kind_of_hit_has_a_sound() -> None:
    """Read from the entity kinds, so a new projectile fails this test."""
    kinds = {HIT_IMPACT, Projectile.kind, EchoClone.kind, OrbitOrb.kind}
    assert set(cues.HIT_CUES) == kinds
    for kind in kinds:
        cue = cues.hit_cue(kind, 20.0, 1)
        assert cue.name == f"hit/{kind}"
        assert peak(cue.buffer) > 0.0


def test_the_five_activations_are_five_different_sounds() -> None:
    rendered = {
        name: bytes(cues.activation_cue(name, 7).buffer) for name in POWER_NAMES
    }
    assert len(set(rendered.values())) == len(POWER_NAMES)


def test_activation_durations_are_the_designed_ones() -> None:
    expected = {
        "rush": 0.190,
        "titan": 0.260,
        "pulse": 0.160,
        "echo": 0.220,
        "orbit": 0.290,
    }
    for name, seconds in expected.items():
        cue = cues.activation_cue(name, 1)
        assert cue.length == round(seconds * SAMPLE_RATE)


def test_an_activation_is_never_louder_than_a_heavy_hit() -> None:
    """A power firing is an announcement; a big hit is the payoff."""
    heaviest = max(
        peak(cues.hit_cue(kind, 100.0, 3).buffer) for kind in cues.HIT_CUES
    )
    for name in POWER_NAMES:
        assert peak(cues.activation_cue(name, 3).buffer) < heaviest


def test_the_elimination_is_the_loudest_single_sound() -> None:
    finish = peak(cues.elimination_cue(3).buffer)
    for kind in cues.HIT_CUES:
        assert finish > peak(cues.hit_cue(kind, 100.0, 3).buffer)
    for name in POWER_NAMES:
        assert finish > peak(cues.activation_cue(name, 3).buffer)
    assert 0.350 <= cues.elimination_cue(3).length / SAMPLE_RATE <= 0.600


def test_the_lethal_hit_is_heard_as_well_as_the_elimination() -> None:
    """Both events are recorded on the same tick and both are played."""
    replay = make_replay(
        frames=200,
        events=(
            event(300, EVENT_HIT, HIT_IMPACT, magnitude=30.0),
            event(300, EVENT_ELIMINATION, HIT_IMPACT),
        ),
    )
    track = build(replay, frames=308)
    assert [cue.name for cue in track.schedule] == [f"hit/{HIT_IMPACT}", "elimination"]
    assert {cue.sample for cue in track.schedule} == {300 * 400}


# --- variety between repeats ----------------------------------------------


def test_repeats_of_the_same_power_are_not_the_same_buffer() -> None:
    """The thing that would make six Orbit activations tiring.

    Orbit's rising cue is pure tone with no noise anywhere in it, so before
    the seeded variation existed every Orbit activation in a battle was
    byte-for-byte the same sound. Every power is checked, not just that one.
    """
    for name in POWER_NAMES:
        rendered = set()
        for tick in (100, 260, 420, 580, 740, 900):
            fired = event(tick, EVENT_POWER_ACTIVATE, name)
            seed = soundtrack.cue_seed(SEED, fired)
            rendered.add(bytes(cues.activation_cue(name, seed).buffer))
        assert len(rendered) == 6, f"{name} repeated itself"


def test_repeats_of_the_same_hit_are_not_the_same_buffer() -> None:
    for kind in cues.HIT_CUES:
        rendered = set()
        for tick in (100, 260, 420, 580):
            landed = event(tick, EVENT_HIT, kind, magnitude=20.0)
            seed = soundtrack.cue_seed(SEED, landed)
            rendered.add(bytes(cues.hit_cue(kind, 20.0, seed).buffer))
        assert len(rendered) == 4, f"hit/{kind} repeated itself"


def test_the_variation_is_small_enough_to_stay_the_same_sound() -> None:
    """A third of a semitone and under a decibel: variety, not a new cue."""
    assert cues.VOICE_PITCH_SPREAD == 0.02
    assert cues.VOICE_LEVEL_TRIM_DB == 0.9
    pitches, trims = zip(*(cues.voice(seed) for seed in range(500)))
    assert min(pitches) >= 1.0 - cues.VOICE_PITCH_SPREAD
    assert max(pitches) <= 1.0 + cues.VOICE_PITCH_SPREAD
    assert min(pitches) < 0.99 and max(pitches) > 1.01
    # Both sides of unity get used, so pitch drifts up as well as down.
    assert any(pitch < 1.0 for pitch in pitches)
    assert any(pitch > 1.0 for pitch in pitches)


def test_the_level_variation_only_ever_trims() -> None:
    """It may not spend headroom the mix has already budgeted."""
    trims = [cues.voice(seed)[1] for seed in range(500)]
    assert max(trims) <= 0.0
    assert min(trims) >= -cues.VOICE_LEVEL_TRIM_DB
    assert min(trims) < -0.8
    for name in POWER_NAMES:
        for seed in range(20):
            assert cues.activation_cue(name, seed).level_dbfs <= cues.LEVEL_ACTIVATE[name]
    for seed in range(20):
        assert cues.elimination_cue(seed).level_dbfs <= cues.LEVEL_ELIMINATION


def test_the_variation_is_reproducible_for_a_seed() -> None:
    assert cues.voice(12345) == cues.voice(12345)
    assert cues.voice(12345) != cues.voice(12346)


def test_variation_does_not_change_how_long_a_cue_is() -> None:
    """Only pitch and level move; the timeline is untouched."""
    for name in POWER_NAMES:
        lengths = {cues.activation_cue(name, seed).length for seed in range(20)}
        assert len(lengths) == 1
    for kind in cues.HIT_CUES:
        lengths = {cues.hit_cue(kind, 20.0, seed).length for seed in range(20)}
        assert len(lengths) == 1


def test_variation_never_pushes_a_cue_over_the_ceiling() -> None:
    for kind in cues.HIT_CUES:
        for seed in range(40):
            assert peak(cues.hit_cue(kind, 1000.0, seed).buffer) < soundtrack.PEAK_CEILING
    for seed in range(40):
        assert peak(cues.elimination_cue(seed).buffer) < soundtrack.PEAK_CEILING


# --- stereo placement -----------------------------------------------------


def test_the_arena_centre_is_dead_centre() -> None:
    assert soundtrack.pan_for_x(ARENA_CENTRE, ARENA_LEFT, ARENA_RIGHT) == 0.0
    assert soundtrack.pan_gains(0.0) == (1.0, 1.0)


def test_pan_follows_the_side_of_the_arena_an_event_is_on() -> None:
    left = soundtrack.pan_for_x(ARENA_LEFT + 50.0, ARENA_LEFT, ARENA_RIGHT)
    right = soundtrack.pan_for_x(ARENA_RIGHT - 50.0, ARENA_LEFT, ARENA_RIGHT)
    assert left < 0.0 < right
    assert soundtrack.pan_gains(left)[0] > soundtrack.pan_gains(left)[1]
    assert soundtrack.pan_gains(right)[1] > soundtrack.pan_gains(right)[0]


def test_pan_is_restrained_and_clamped_at_the_walls() -> None:
    """Never hard-panned, and never further out than the wall itself."""
    assert soundtrack.MAX_PAN == 0.6
    for x in (-5000.0, ARENA_LEFT - 200.0, ARENA_LEFT, ARENA_CENTRE, ARENA_RIGHT, 9000.0):
        pan = soundtrack.pan_for_x(x, ARENA_LEFT, ARENA_RIGHT)
        assert abs(pan) <= soundtrack.MAX_PAN
        gains = soundtrack.pan_gains(pan)
        assert all(0.0 < gain <= 1.0 for gain in gains)
        assert max(gains) == pytest.approx(1.0)


def test_a_degenerate_arena_pans_nothing() -> None:
    assert soundtrack.pan_for_x(500.0, 500.0, 500.0) == 0.0


def test_panning_is_symmetric_about_the_centre() -> None:
    for offset in (10.0, 200.0, 480.0):
        near, far = ARENA_CENTRE - offset, ARENA_CENTRE + offset
        one = soundtrack.pan_gains(soundtrack.pan_for_x(near, ARENA_LEFT, ARENA_RIGHT))
        other = soundtrack.pan_gains(soundtrack.pan_for_x(far, ARENA_LEFT, ARENA_RIGHT))
        assert one == pytest.approx(tuple(reversed(other)))


def test_the_pan_law_follows_the_equal_power_shape() -> None:
    """Cosine and sine of a quarter turn, renormalised to the near channel."""
    for pan in (-0.6, -0.25, 0.0, 0.25, 0.6):
        angle = (pan + 1.0) * math.pi / 4.0
        raw = (math.cos(angle), math.sin(angle))
        expected = tuple(value / max(raw) for value in raw)
        assert soundtrack.pan_gains(pan) == pytest.approx(expected)


def test_a_panned_cue_reaches_both_channels() -> None:
    far_left = event(100, EVENT_HIT, HIT_IMPACT, magnitude=30.0, x=ARENA_LEFT)
    replay = make_replay(frames=200, events=(far_left,))
    track = build(replay, frames=308, include_ambience=False)
    assert peak(track.left) > peak(track.right) > 0.0


# --- magnitude ------------------------------------------------------------


def test_magnitude_is_clamped_into_the_unit_range() -> None:
    for magnitude in (-1000.0, 0.0, 3.9, 4.0, 20.0, 42.0, 500.0, 1e9):
        assert 0.0 <= cues.magnitude_factor(magnitude) <= 1.0
    assert cues.magnitude_factor(cues.HIT_MAGNITUDE_QUIET) == 0.0
    assert cues.magnitude_factor(cues.HIT_MAGNITUDE_LOUD) == 1.0
    assert cues.magnitude_factor(-1.0) == 0.0
    assert cues.magnitude_factor(1e9) == 1.0


def test_a_hit_with_no_recorded_magnitude_still_sounds_like_a_hit() -> None:
    factor = cues.magnitude_factor(None)
    assert 0.0 < factor < 1.0
    assert peak(cues.hit_cue(HIT_IMPACT, None, 1).buffer) > 0.0


def test_magnitude_rises_monotonically_within_its_window() -> None:
    values = [cues.magnitude_factor(magnitude) for magnitude in range(0, 60, 3)]
    assert values == sorted(values)


def test_a_heavy_hit_is_louder_and_longer_than_a_light_one() -> None:
    """The 40 HP hit against the 8 HP hit, for every kind of hit."""
    for kind in cues.HIT_CUES:
        light = cues.hit_cue(kind, 8.0, 11)
        heavy = cues.hit_cue(kind, 40.0, 11)
        assert peak(heavy.buffer) > peak(light.buffer)
        assert heavy.level_dbfs > light.level_dbfs
        assert heavy.length > light.length
        # Audible, but not a different event: a few decibels, not twenty.
        assert 2.0 < heavy.level_dbfs - light.level_dbfs < 12.0


def test_no_magnitude_can_make_a_cue_clip() -> None:
    for kind in cues.HIT_CUES:
        for magnitude in (0.0, 8.0, 40.0, 1000.0, 1e9):
            assert peak(cues.hit_cue(kind, magnitude, 5).buffer) < 1.0


def test_every_cue_peaks_at_the_level_it_was_designed_for() -> None:
    """Peak-normalised then scaled, so the designed number is the real one."""
    for kind in cues.HIT_CUES:
        for magnitude in (5.0, 20.0, 40.0):
            cue = cues.hit_cue(kind, magnitude, 9)
            assert peak(cue.buffer) == pytest.approx(db_to_gain(cue.level_dbfs))
    for name in POWER_NAMES:
        cue = cues.activation_cue(name, 9)
        assert peak(cue.buffer) == pytest.approx(db_to_gain(cue.level_dbfs))
    finish = cues.elimination_cue(9)
    assert peak(finish.buffer) == pytest.approx(db_to_gain(finish.level_dbfs))


# --- the ambient bed ------------------------------------------------------


def test_the_bed_runs_the_whole_length_including_the_post_roll() -> None:
    """The gaps between events must not be digital silence."""
    replay = make_replay(frames=200, events=SYNTHETIC_EVENTS[:1])
    track = build(replay, frames=308)
    gameplay_end = 200 * 800
    assert first_signal(track.left, start=gameplay_end) is not None
    # A quiet stretch in the middle of the battle is still not silence.
    assert first_signal(track.left, start=90 * 800, stop=95 * 800) is not None


def test_the_bed_is_calibrated_as_two_layers_not_one() -> None:
    """The hum and the room are set separately, and both are pre-master.

    Calibrating the pair together would let the hum - which carries most of
    the energy and none of the audibility on a small speaker - decide how
    loud the room is, which is how Phase 6B ended up with a bed that was
    silence on a phone.
    """
    assert cues.AMBIENCE_LOW_RMS_DBFS == -33.5
    assert cues.AMBIENCE_MID_RMS_DBFS == -35.5
    assert cues.AMBIENCE_MID_RMS_DBFS < cues.AMBIENCE_LOW_RMS_DBFS
    track = build(make_replay(frames=200), frames=308, include_events=False)
    combined = 10.0 * math.log10(
        db_to_gain(cues.AMBIENCE_LOW_RMS_DBFS) ** 2
        + db_to_gain(cues.AMBIENCE_MID_RMS_DBFS) ** 2
    )
    assert gain_to_db(track.level_rms) == pytest.approx(combined, abs=1.5)
    # An audit of the bed alone is never lifted: no make-up, no compression.
    assert track.makeup_gain == 1.0
    assert track.compression.max_reduction_db == 0.0


def test_the_room_layer_lives_in_the_band_a_phone_reproduces() -> None:
    """Its whole reason for existing, so its band is pinned by a test."""
    assert cues.AMBIENCE_ROOM_LOW == 200.0
    assert cues.AMBIENCE_ROOM_HIGH == 2600.0
    assert cues.AMBIENCE_ROOM_LOW < 400.0 < cues.AMBIENCE_ROOM_HIGH
    # And it is noise, not a tone: no partial of the hum reaches it.
    assert max(freq for freq, _, _ in cues.AMBIENCE_PARTIALS) < cues.AMBIENCE_ROOM_LOW


def test_the_room_layer_is_modulated_but_never_rhythmic() -> None:
    """Slower than anything a 25-second Short could hear repeat."""
    assert 0.0 < cues.AMBIENCE_ROOM_LFO_HZ < 0.1
    assert 1.0 / cues.AMBIENCE_ROOM_LFO_HZ > 25.0
    assert 0.0 < cues.AMBIENCE_ROOM_LFO_DEPTH < 0.5


def test_the_bed_is_far_below_the_events_it_sits_under() -> None:
    bed = build(make_replay(frames=200), frames=308, include_events=False)
    quietest = min(
        peak(cues.hit_cue(kind, 0.0, 1).buffer) for kind in cues.HIT_CUES
    )
    assert gain_to_db(quietest) - gain_to_db(bed.level_rms) > 15.0


def test_the_bed_fades_out_on_the_last_sample_of_the_render() -> None:
    """Measured back from the exact sample count, so it never ends abruptly."""
    track = build(make_replay(frames=200), frames=308, include_events=False)
    last = track.sample_count - 1
    settled = track.sample_count - round(cues.AMBIENCE_FADE_OUT * SAMPLE_RATE) - 1
    # The ramp reaches zero one step past the end, so the final sample is one
    # step above it: below a 16-bit least-significant bit, and a thousand
    # times quieter than the bed was before the fade began.
    for channel in (track.left, track.right):
        assert abs(channel[last]) < 1.0 / 32767
        assert abs(channel[last]) * 1000 < abs(channel[settled])


def test_the_bed_starts_from_silence() -> None:
    """The fade-in's first step, which is below a 16-bit least-significant bit."""
    track = build(make_replay(frames=200), frames=308, include_events=False)
    for channel in (track.left, track.right):
        assert abs(channel[0]) < 1.0 / 32767
        assert abs(channel[0]) * 1000 < abs(channel[len(channel) // 2])


def test_the_two_channels_of_the_bed_are_not_the_same_signal() -> None:
    """Width without a delay, so it survives being folded to mono."""
    track = build(make_replay(frames=200), frames=308, include_events=False)
    assert bytes(track.left) != bytes(track.right)
    assert peak(track.left) == pytest.approx(peak(track.right), rel=0.25)


# --- levels and headroom --------------------------------------------------


def test_a_normal_battle_lands_exactly_on_the_ceiling() -> None:
    """And every stage that got it there did only a little.

    The chain is compressor, then a fixed make-up, then the limiter, then an
    exact trim. The make-up is deliberately more than the compressor took
    off, so the limiter catches the difference - which means it is a working
    stage now rather than an idle safety net, and what matters is how little
    it does. Under a decibel over a twenty-four millisecond window is not
    something that can be heard.
    """
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    assert gain_to_db(track.peak) == pytest.approx(
        soundtrack.PEAK_CEILING_DBFS, abs=0.01
    )
    assert track.compression.max_reduction_db > 0.0
    assert gain_to_db(track.limiter_gain) > -1.5


def test_a_battle_without_a_heavy_finish_needs_no_limiting_at_all() -> None:
    lighter = SYNTHETIC_EVENTS[:5] + (
        event(760, EVENT_HIT, HIT_IMPACT, magnitude=22.0),
        event(760, EVENT_ELIMINATION, HIT_IMPACT),
    )
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=lighter))
    assert track.limited is False
    assert track.limiter_gain == 1.0
    assert track.makeup_gain > 1.0
    assert gain_to_db(track.peak) == pytest.approx(soundtrack.PEAK_CEILING_DBFS, abs=0.01)


def test_the_master_leaves_the_encoder_room_under_the_delivery_ceiling() -> None:
    """Two ceilings: what the MP4 may reach, and what the master may.

    AAC hands back inter-sample peaks a couple of tenths above the samples
    it was given, so a master written right on the delivery figure would
    encode to a file above it.
    """
    assert soundtrack.DELIVERY_PEAK_DBFS == -1.0
    assert soundtrack.CODEC_OVERSHOOT_DB > 0.0
    assert soundtrack.PEAK_CEILING_DBFS == pytest.approx(-1.3)
    assert soundtrack.PEAK_CEILING_DBFS < soundtrack.DELIVERY_PEAK_DBFS
    assert soundtrack.PEAK_CEILING == pytest.approx(
        10 ** (soundtrack.PEAK_CEILING_DBFS / 20.0), abs=1e-9
    )
    assert soundtrack.PEAK_CEILING < 1.0


def test_makeup_gain_is_bounded_and_never_inflates_a_near_empty_mix() -> None:
    bed = build(make_replay(frames=100), frames=208, include_events=False)
    assert bed.makeup_gain == 1.0
    assert gain_to_db(bed.peak) < soundtrack.PEAK_CEILING_DBFS - 10.0
    # The fixed make-up plus the trim after the limiter, together, are capped.
    assert soundtrack.MASTER_MAKEUP_DB == 7.0
    assert soundtrack.MASTER_MAKEUP_MAX_DB == 9.0
    assert soundtrack.MASTER_MAKEUP_DB < soundtrack.MASTER_MAKEUP_MAX_DB


def test_the_makeup_never_exceeds_its_cap() -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    assert gain_to_db(track.makeup_gain) <= soundtrack.MASTER_MAKEUP_MAX_DB + 1e-9
    assert gain_to_db(track.makeup_gain) >= soundtrack.MASTER_MAKEUP_DB - 1e-9


def test_an_event_heavy_battle_is_held_under_the_ceiling() -> None:
    """Forty eliminations on top of each other, which no battle produces.

    Whether the limiter or the compressor did the holding is not the point -
    the point is that nothing gets out above the ceiling.
    """
    stacked = tuple(
        event(200 + index, EVENT_ELIMINATION, HIT_IMPACT, x=ARENA_CENTRE)
        for index in range(40)
    )
    track = build(make_replay(frames=300, events=stacked), frames=408)
    assert track.peak_before_master > 0.0
    assert track.peak <= soundtrack.PEAK_CEILING + 1e-12
    assert peak(track.left) <= soundtrack.PEAK_CEILING + 1e-12
    assert peak(track.right) <= soundtrack.PEAK_CEILING + 1e-12


def loud_pair(length: int = 40_000, level: float = 2.4):
    """Two channels holding one long over-ceiling burst, for master() tests."""
    from array import array

    left = array("d", bytes(8 * length))
    right = array("d", bytes(8 * length))
    for index in range(8_000, 24_000):
        phase = (index - 8_000) / 90.0
        value = level * math.sin(phase)
        left[index] = value
        right[index] = value * 0.4
    return left, right


def test_the_limiter_holds_anything_under_the_ceiling() -> None:
    """Tested directly, with a signal well past full scale.

    The compressor now takes the peaks off a real mix before this ever sees
    them, so the limiter is exercised on its own rather than through a
    battle - it is the guarantee, and a guarantee has to be checked where it
    cannot be helped by anything upstream.
    """
    left, right = loud_pair()
    report = soundtrack.master(left, right)
    assert report.peak_before > 1.0
    assert report.limited is True
    assert 0.0 < report.limiter_gain < 1.0
    assert peak(left) <= soundtrack.PEAK_CEILING + 1e-12
    assert peak(right) <= soundtrack.PEAK_CEILING + 1e-12


def test_limiting_moves_both_channels_together() -> None:
    """A limiter that ducked one channel would swing the stereo image."""
    left, right = loud_pair()
    soundtrack.master(left, right)
    ratios = [
        left[index] / right[index]
        for index in range(8_000, 24_000)
        if abs(right[index]) > 1e-9
    ]
    assert ratios
    assert max(ratios) - min(ratios) < 1e-9


def test_a_quiet_battle_is_not_silent_and_a_busy_one_does_not_clip() -> None:
    quiet = build(make_replay(frames=400, events=SYNTHETIC_EVENTS[:1]), frames=508)
    busy = build(
        make_replay(
            frames=400,
            events=tuple(
                event(
                    60 + index * 7,
                    EVENT_HIT,
                    (HIT_IMPACT, Projectile.kind, EchoClone.kind, OrbitOrb.kind)[index % 4],
                    magnitude=8.0 + 30.0 * (index % 3) / 2.0,
                    x=ARENA_LEFT + (index % 5) * 240.0,
                )
                for index in range(100)
            ),
        ),
        frames=508,
    )
    assert peak(quiet.left) > 0.0 and peak(quiet.right) > 0.0
    assert len(busy.schedule) == 100
    assert busy.peak <= soundtrack.PEAK_CEILING + 1e-12
    # A busy battle is louder overall, but not by turning into one long noise.
    assert busy.level_rms > quiet.level_rms


# --- bus compression ------------------------------------------------------


def test_the_compressor_is_gentle_by_the_numbers() -> None:
    """Not a wall: a low ratio, a wide soft knee, and a slow release."""
    assert soundtrack.COMPRESSOR_RATIO == 2.2
    assert 1.0 < soundtrack.COMPRESSOR_RATIO <= 3.0
    assert soundtrack.COMPRESSOR_KNEE_DB >= 10.0
    assert soundtrack.COMPRESSOR_RELEASE >= 0.15
    assert soundtrack.COMPRESSOR_ATTACK >= 0.002
    # Look-ahead at least as long as the attack, or the gain would still be
    # moving when the transient it was meant to catch has already gone.
    assert soundtrack.COMPRESSOR_LOOKAHEAD >= soundtrack.COMPRESSOR_ATTACK


def test_a_real_battle_needs_only_a_few_decibels_of_reduction() -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    squeeze = track.compression
    assert squeeze is not None
    assert 3.0 < squeeze.max_reduction_db < 9.0
    assert squeeze.mean_reduction_db < squeeze.max_reduction_db
    assert 0.0 < squeeze.engaged_fraction < 1.0


def test_compression_leaves_the_length_and_the_channels_alone() -> None:
    left, right = build_pair()
    before = len(left)
    soundtrack.compress(left, right)
    assert len(left) == len(right) == before


def test_compression_never_moves_a_sample_in_time() -> None:
    """The look-ahead reads forward; it does not delay the signal.

    A compressor that delayed by its look-ahead would shift every cue later
    by eight milliseconds, which is half a frame - so this is checked rather
    than assumed. Silence before a burst stays silent, and the burst still
    starts on the sample it started on.
    """
    from array import array

    length = 20_000
    start = 6_000
    left = array("d", bytes(8 * length))
    right = array("d", bytes(8 * length))
    for index in range(start, start + 4_000):
        value = 0.8 * math.sin((index - start) / 40.0)
        left[index] = value
        right[index] = value

    soundtrack.compress(left, right)
    assert first_signal(left, stop=start) is None
    assert first_signal(right, stop=start) is None
    assert first_signal(left, start=start, stop=start + 200) is not None
    assert first_signal(left, start=start + 4_000) is None


def test_every_cue_still_starts_on_its_own_sample_after_mastering() -> None:
    """The whole chain, end to end, against the arithmetic.

    Compression and make-up gain both scale samples, and neither may move
    one. This is the same check the synchronisation tests make, run on a
    soundtrack that has been through the full master chain.
    """
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    track = build(replay, include_ambience=False)
    millisecond = SAMPLE_RATE // 1000
    for cue, source in zip(track.schedule, SYNTHETIC_EVENTS):
        assert cue.sample == source["tick"] * 400
        quiet_from = max(0, cue.sample - 400)
        assert first_signal(track.left, start=quiet_from, stop=cue.sample) is None
        arrived = first_signal(
            track.left, start=cue.sample, stop=cue.sample + millisecond
        )
        assert arrived is not None


def test_compression_keeps_a_heavy_hit_ahead_of_a_light_one() -> None:
    """Gentle means the magnitude mapping survives, not that it is untouched.

    Some of the difference is spent - that is what compression is - so what
    is asserted is that a clear majority of it is still there.
    """
    levels = []
    for magnitude in (8.0, 40.0):
        cue = cues.hit_cue(HIT_IMPACT, magnitude, 4242)
        left, right = build_pair(length=SAMPLE_RATE, cue=cue, offset=2400)
        soundtrack.compress(left, right)
        levels.append(gain_to_db(peak(left)))
    surviving = levels[1] - levels[0]
    designed = (
        cues.hit_cue(HIT_IMPACT, 40.0, 4242).level_dbfs
        - cues.hit_cue(HIT_IMPACT, 8.0, 4242).level_dbfs
    )
    assert surviving > 2.5
    assert surviving > 0.45 * designed


def test_compression_moves_both_channels_together() -> None:
    left, right = build_pair()
    for index in range(len(right)):
        right[index] *= 0.5
    soundtrack.compress(left, right)
    ratios = [
        left[index] / right[index]
        for index in range(len(left))
        if abs(right[index]) > 1e-9
    ]
    assert ratios
    assert max(ratios) - min(ratios) < 1e-9


def test_a_quiet_mix_is_left_completely_alone() -> None:
    """Below the knee the compressor is not merely gentle, it is absent."""
    from array import array

    length = 8_000
    quiet = db_to_gain(soundtrack.COMPRESSOR_THRESHOLD_DBFS - 40.0)
    left = array("d", [quiet * math.sin(index / 30.0) for index in range(length)])
    right = array("d", left)
    original = bytes(left)
    report = soundtrack.compress(left, right)
    assert report.max_reduction_db == 0.0
    assert report.engaged_fraction == 0.0
    assert bytes(left) == original


def test_a_ratio_of_one_is_a_no_op() -> None:
    left, right = build_pair()
    original = bytes(left)
    report = soundtrack.compress(left, right, ratio=1.0)
    assert report.max_reduction_db == 0.0
    assert bytes(left) == original


def test_compression_is_reproducible() -> None:
    one_left, one_right = build_pair()
    other_left, other_right = build_pair()
    first = soundtrack.compress(one_left, one_right)
    second = soundtrack.compress(other_left, other_right)
    assert bytes(one_left) == bytes(other_left)
    assert bytes(one_right) == bytes(other_right)
    assert first == second


def test_the_look_ahead_window_takes_the_maximum_of_what_is_coming() -> None:
    from array import array

    values = array("d", [0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0])
    assert list(soundtrack._sliding_max(values, 2)) == [
        1.0,
        1.0,
        1.0,
        0.5,
        0.5,
        0.5,
        0.0,
    ]
    # Forward-looking only: nothing behind the index leaks in.
    assert soundtrack._sliding_max(array("d", [1.0, 0.0, 0.0]), 1)[2] == 0.0


def test_the_mastered_mix_never_goes_past_the_ceiling() -> None:
    for events in (SYNTHETIC_EVENTS, SYNTHETIC_EVENTS[:3], SYNTHETIC_EVENTS[:1]):
        track = build(make_replay(frames=SYNTHETIC_FRAMES, events=events))
        assert track.peak <= soundtrack.PEAK_CEILING
        assert peak(track.left) <= soundtrack.PEAK_CEILING
        assert peak(track.right) <= soundtrack.PEAK_CEILING
        assert gain_to_db(track.makeup_gain) <= soundtrack.MASTER_MAKEUP_MAX_DB + 1e-9


def test_the_total_lift_is_capped_however_quiet_the_mix_is() -> None:
    """A near-silent timeline is not inflated to look loud.

    Tested on the stage directly: the trim after the limiter will spend what
    headroom is there, but the two gains together may never exceed the cap,
    so something with almost nothing in it stays quiet.
    """
    from array import array

    length = 12_000
    faint = db_to_gain(-50.0)
    left = array("d", [faint * math.sin(index / 25.0) for index in range(length)])
    right = array("d", left)
    report = soundtrack.master(
        left, right, makeup_db=soundtrack.MASTER_MAKEUP_DB, trim=True
    )
    assert gain_to_db(report.makeup_gain) == pytest.approx(
        soundtrack.MASTER_MAKEUP_MAX_DB, abs=1e-6
    )
    assert gain_to_db(report.peak_after) < -35.0
    assert report.limited is False


def test_a_quiet_battle_stays_quieter_than_a_busy_one() -> None:
    """Mastering raises the floor; it must not flatten the two together."""
    sparse = build(make_replay(frames=500, events=SYNTHETIC_EVENTS[:2]), frames=608)
    dense = build(
        make_replay(
            frames=500,
            events=tuple(
                event(
                    80 + index * 9,
                    EVENT_HIT,
                    (HIT_IMPACT, Projectile.kind, EchoClone.kind, OrbitOrb.kind)[
                        index % 4
                    ],
                    magnitude=12.0 + 24.0 * (index % 3) / 2.0,
                    x=ARENA_LEFT + (index % 5) * 240.0,
                )
                for index in range(90)
            ),
        ),
        frames=608,
    )
    assert dense.level_rms > sparse.level_rms
    assert sparse.peak <= dense.peak


def test_the_sidecar_records_what_the_compressor_did() -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    data = sidecar(track)
    assert data["compression"]["ratio"] == soundtrack.COMPRESSOR_RATIO
    assert data["compression"]["threshold_dbfs"] == soundtrack.COMPRESSOR_THRESHOLD_DBFS
    assert data["compression"]["max_reduction_db"] > 0.0
    assert 0.0 < data["compression"]["engaged_fraction"] < 1.0
    assert data["levels"]["makeup_db"] >= soundtrack.MASTER_MAKEUP_DB
    assert data["levels"]["crest_db"] > 0.0
    assert data["levels"]["ambience_low_dbfs"] > cues.AMBIENCE_LOW_RMS_DBFS


# --- determinism ----------------------------------------------------------


def test_the_same_replay_produces_the_same_samples_every_time() -> None:
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    one = build(replay)
    other = build(replay)
    assert bytes(one.left) == bytes(other.left)
    assert bytes(one.right) == bytes(other.right)
    assert one.peak == other.peak
    assert one.schedule == other.schedule


def test_noise_comes_from_a_seeded_generator_and_not_the_global_one() -> None:
    import random

    replay = make_replay(frames=200, events=SYNTHETIC_EVENTS[:3])
    random.seed(1)
    one = build(replay, frames=308, include_ambience=False)
    random.seed(999)
    for _ in range(50):
        random.random()
    other = build(replay, frames=308, include_ambience=False)
    assert bytes(one.left) == bytes(other.left)


def test_a_cue_seed_is_derived_from_the_event_and_the_replay() -> None:
    hit = event(200, EVENT_HIT, HIT_IMPACT, magnitude=20.0)
    assert soundtrack.cue_seed(SEED, hit) == soundtrack.cue_seed(SEED, hit)
    assert soundtrack.cue_seed(SEED, hit) != soundtrack.cue_seed(SEED + 1, hit)
    for field, value in (
        ("tick", 201),
        ("type", EVENT_ELIMINATION),
        ("subtype", Projectile.kind),
        ("source_id", 1),
        ("target_id", 0),
    ):
        moved = dict(hit, **{field: value})
        assert soundtrack.cue_seed(SEED, moved) != soundtrack.cue_seed(SEED, hit)


def test_two_identical_hits_at_different_moments_get_different_noise() -> None:
    def hit_at(tick: int):
        landed = event(tick, EVENT_HIT, HIT_IMPACT, magnitude=20.0)
        return cues.hit_cue(HIT_IMPACT, 20.0, soundtrack.cue_seed(SEED, landed))

    early, late = hit_at(100), hit_at(900)
    assert early.length == late.length
    assert bytes(early.buffer) != bytes(late.buffer)


def test_a_stable_seed_does_not_depend_on_the_process() -> None:
    """Hard-coded, because Python's own hash() is salted per run."""
    assert stable_seed("impact", 200, 0, 1) == stable_seed("impact", 200, 0, 1)
    assert stable_seed("a", "bc") != stable_seed("ab", "c")
    assert stable_seed(21465) == 15734616162635695910


def test_the_noise_generator_is_reproducible_and_in_range() -> None:
    first = [Noise(4242).sample() for _ in range(4)]
    assert first == [Noise(4242).sample() for _ in range(4)]
    assert first != [Noise(4243).sample() for _ in range(4)]
    for value in Noise(1).fill(2000):
        assert -1.0 <= value < 1.0


def test_the_soundtrack_version_is_declared_separately() -> None:
    """Its own number: replay v6, batch v1 and render v1 are other things."""
    assert soundtrack.SOUNDTRACK_VERSION == 1
    assert soundtrack.SOUNDTRACK_VERSION != REPLAY_VERSION


# --- the WAV master -------------------------------------------------------


def test_the_wav_says_what_the_production_format_is(tmp_path) -> None:
    track = build(make_replay(frames=100, events=SYNTHETIC_EVENTS[:2]), frames=208)
    path = str(tmp_path / "audio.wav")
    wav_io.write_wav(path, track.left, track.right, sample_rate=SAMPLE_RATE)

    info, data = wav_io.read_wav(path)
    assert info.sample_rate == 48000
    assert info.channels == CHANNELS == 2
    assert info.bit_depth == wav_io.DEFAULT_BIT_DEPTH == 24
    assert info.sample_count == 208 * 800
    assert info.duration == pytest.approx(208 / 60)
    assert info.data_size == 208 * 800 * 2 * 3 == len(data)
    assert os.path.getsize(path) == wav_io.HEADER_SIZE + info.data_size


def test_a_wav_holds_nothing_but_a_header_and_samples(tmp_path) -> None:
    """No date, no encoder name, nothing that would differ between runs."""
    track = build(make_replay(frames=60), frames=60, include_events=False)
    path = str(tmp_path / "audio.wav")
    wav_io.write_wav(path, track.left, track.right, sample_rate=SAMPLE_RATE)
    raw = open(path, "rb").read()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    assert raw[12:16] == b"fmt " and raw[36:40] == b"data"
    assert len(raw) == wav_io.HEADER_SIZE + 60 * 800 * 6
    assert b"LIST" not in raw[: wav_io.HEADER_SIZE]


def test_writing_the_same_master_twice_gives_the_same_file(tmp_path) -> None:
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    paths = []
    for name in ("one.wav", "two.wav"):
        track = build(replay)
        paths.append(str(tmp_path / name))
        wav_io.write_wav(paths[-1], track.left, track.right, sample_rate=SAMPLE_RATE)
    assert open(paths[0], "rb").read() == open(paths[1], "rb").read()


def test_both_supported_bit_depths_round_trip(tmp_path) -> None:
    track = build(make_replay(frames=80, events=SYNTHETIC_EVENTS[:2]), frames=188)
    for bit_depth in wav_io.BIT_DEPTHS:
        path = str(tmp_path / f"audio{bit_depth}.wav")
        wav_io.write_wav(
            path, track.left, track.right, sample_rate=SAMPLE_RATE, bit_depth=bit_depth
        )
        info, data = wav_io.read_wav(path)
        assert info.bit_depth == bit_depth
        assert info.sample_count == 188 * 800
        assert wav_io.pcm_peak(data, bit_depth) == pytest.approx(track.peak, abs=2e-4)


def test_quantising_clamps_rather_than_wraps() -> None:
    """A wrapped sample would be the loudest possible click, not a quiet one."""
    from array import array

    limit = wav_io.full_scale(24)
    values = wav_io.quantise(array("d", [2.0, -2.0, 0.0]), array("d", [-3.0, 3.0, 0.0]), 24)
    assert list(values) == [limit, -limit, -limit, limit, 0, 0]


def test_a_master_at_the_ceiling_passes_its_own_check(tmp_path) -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    path = str(tmp_path / "audio.wav")
    wav_io.write_wav(path, track.left, track.right, sample_rate=SAMPLE_RATE)
    info, data = wav_io.read_wav(path)
    assert (
        wav_io.wav_problems(
            info,
            data,
            sample_rate=48000,
            channels=2,
            sample_count=track.sample_count,
            ceiling=soundtrack.PEAK_CEILING,
        )
        == []
    )
    assert wav_io.pcm_peak(data, info.bit_depth) < 1.0


def test_a_master_of_the_wrong_length_or_rate_is_refused(tmp_path) -> None:
    track = build(make_replay(frames=60, events=SYNTHETIC_EVENTS[:1]), frames=168)
    path = str(tmp_path / "audio.wav")
    wav_io.write_wav(path, track.left, track.right, sample_rate=SAMPLE_RATE)
    info, data = wav_io.read_wav(path)

    wrong_length = wav_io.wav_problems(
        info, data, sample_rate=48000, channels=2, sample_count=999
    )
    assert any("expected exactly 999" in line for line in wrong_length)
    wrong_rate = wav_io.wav_problems(
        info, data, sample_rate=44100, channels=2, sample_count=info.sample_count
    )
    assert any("sample rate" in line for line in wrong_rate)
    mono = wav_io.wav_problems(
        info, data, sample_rate=48000, channels=1, sample_count=info.sample_count
    )
    assert any("channels" in line for line in mono)


def test_a_silent_master_is_refused() -> None:
    from array import array

    silent = array("d", bytes(8 * 800))
    info = wav_io.WavInfo(2, 48000, 24, 800, 800 * 6)
    data = wav_io.pcm_bytes(silent, silent, 24)
    problems = wav_io.wav_problems(
        info, data, sample_rate=48000, channels=2, sample_count=800
    )
    assert any("silent" in line for line in problems)


def test_a_file_that_is_not_a_wav_is_refused(tmp_path) -> None:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"this is not a RIFF file at all")
    with pytest.raises(wav_io.WavError):
        wav_io.read_wav(str(path))


def test_an_unsupported_bit_depth_is_refused() -> None:
    with pytest.raises(wav_io.WavError):
        wav_io.full_scale(8)
    with pytest.raises(wav_io.WavError):
        wav_io.decode_samples(b"\x00" * 8, 32)


# --- the deterministic sidecar -------------------------------------------


def sidecar(track: soundtrack.Soundtrack) -> dict:
    return soundtrack.audio_metadata(
        track,
        replay_name="003_seed_21465.json",
        replay_path="output/batch_audit10/replays/003_seed_21465.json",
        replay_sha256="a" * 64,
        pcm_sha256="b" * 64,
    )


def test_the_sidecar_describes_the_master_it_sits_beside() -> None:
    track = build(make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS))
    data = sidecar(track)
    assert data["audio_version"] == soundtrack.SOUNDTRACK_VERSION
    assert data["replay"]["sha256"] == "a" * 64
    assert data["replay"]["seed"] == SEED
    assert data["audio"] == {
        "bit_depth": 24,
        "channels": 2,
        "duration": pytest.approx((SYNTHETIC_FRAMES + 108) / 60, abs=1e-6),
        "pcm_sha256": "b" * 64,
        "sample_rate": 48000,
        "samples": (SYNTHETIC_FRAMES + 108) * 800,
        "samples_per_frame": 800,
        "samples_per_tick": 400,
    }
    assert data["events"]["total"] == len(SYNTHETIC_EVENTS)
    assert data["events"]["scheduled"] == len(SYNTHETIC_EVENTS)
    assert data["events"]["by_cue"] == track.cue_counts
    assert data["levels"]["peak_dbfs"] == pytest.approx(
        soundtrack.PEAK_CEILING_DBFS, abs=0.01
    )
    assert data["levels"]["delivery_peak_dbfs"] == soundtrack.DELIVERY_PEAK_DBFS
    assert data["timeline"]["post_roll_frames"] == 108


def test_the_sidecar_is_byte_identical_between_runs() -> None:
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    dumps = []
    for _ in range(2):
        track = build(replay)
        data = soundtrack.audio_metadata(
            track,
            replay_name="r.json",
            replay_path="output/r.json",
            replay_sha256="c" * 64,
            pcm_sha256=wav_io.sha256_hex(wav_io.pcm_bytes(track.left, track.right, 24)),
        )
        dumps.append(json.dumps(data, indent=2, sort_keys=True))
    assert dumps[0] == dumps[1]


def test_the_sidecar_records_nothing_that_could_vary() -> None:
    """No clock, no machine, no absolute path, no run id."""
    data = sidecar(build(make_replay(frames=100, events=SYNTHETIC_EVENTS[:2]), frames=208))
    text = json.dumps(data).lower()
    for forbidden in (
        "timestamp",
        "created",
        "creation",
        "hostname",
        "machine",
        "platform",
        "uuid",
        "run_id",
        "elapsed",
    ):
        assert forbidden not in text
    assert not os.path.isabs(data["replay"]["path"])
    assert not os.path.isabs(data["replay"]["name"])


# --- the synthetic six-cue check -----------------------------------------


def test_the_hand_made_sequence_is_correct_both_times_it_is_built() -> None:
    """One of every identity, generated twice, checked end to end.

    Deliberately not a recorded battle: a hand-made sequence pins the exact
    ticks, so every expected sample index in this test is arithmetic that can
    be read off the page rather than something looked up from a file.
    """
    replay = make_replay(frames=SYNTHETIC_FRAMES, events=SYNTHETIC_EVENTS)
    expected_samples = (SYNTHETIC_FRAMES + 108) * 800
    millisecond = SAMPLE_RATE // 1000

    renders = [build(replay, include_ambience=False) for _ in range(2)]
    for track in renders:
        assert track.sample_count == expected_samples
        assert [cue.name for cue in track.schedule] == [
            "activate/rush",
            f"hit/{HIT_IMPACT}",
            f"hit/{Projectile.kind}",
            f"hit/{EchoClone.kind}",
            f"hit/{OrbitOrb.kind}",
            f"hit/{HIT_IMPACT}",
            "elimination",
        ]
        for cue, source in zip(track.schedule, SYNTHETIC_EVENTS):
            assert cue.sample == source["tick"] * 400
            assert (
                first_signal(track.left, start=max(0, cue.sample - 200), stop=cue.sample)
                is None
            )
            arrived = first_signal(
                track.left, start=cue.sample, stop=cue.sample + millisecond
            )
            assert arrived is not None
        assert track.peak <= soundtrack.PEAK_CEILING + 1e-12
        assert peak(track.left) > 0.0 and peak(track.right) > 0.0

    assert bytes(renders[0].left) == bytes(renders[1].left)
    assert bytes(renders[0].right) == bytes(renders[1].right)
    assert wav_io.pcm_bytes(renders[0].left, renders[0].right, 24) == wav_io.pcm_bytes(
        renders[1].left, renders[1].right, 24
    )


# --- against a real battle ------------------------------------------------


def test_a_recorded_battle_makes_a_soundtrack_of_the_right_length() -> None:
    from replay.exporter import record_battle

    replay = record_battle(SEED)
    frame_count = len(replay["frames"]) + 108
    plan = soundtrack.plan_soundtrack(replay, frame_count)
    assert plan.total_samples == frame_count * 800
    assert plan.arena_left == 60.0 and plan.arena_right == 1020.0

    track = soundtrack.build_soundtrack(replay, plan)
    assert track.sample_count == frame_count * 800
    assert track.events_total == len(replay["events"])
    assert track.events_unvoiced == 0
    assert track.events_past_end == 0
    assert len(track.schedule) == len(replay["events"])
    assert track.peak <= soundtrack.PEAK_CEILING + 1e-12
    assert track.limited is False
    assert gain_to_db(track.peak) == pytest.approx(soundtrack.PEAK_CEILING_DBFS, abs=0.01)
    for cue, source in zip(track.schedule, replay["events"]):
        assert cue.sample == source["tick"] * 400
