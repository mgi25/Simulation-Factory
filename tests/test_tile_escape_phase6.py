"""Phase 6: the production master, and the three defects found on the way to it.

Phase 6 is delivery, so most of what is asserted here is that nothing moved
that was not meant to. But it also found three real defects, and each one has a
regression below, because each was the kind of thing that measures fine one
layer up from where it is wrong.

**The masking instrument was broadband, and the events are pitched.** Phase 5
reported that on the densest pacing-valid seed nine activations in fifty did
not clear 3 dB above the bed under them, and recommended ducking the duplicate
bed. Phase 6 measured the bed first. No activation on any of five seeds has a
duplicate inside the 55 ms window the reading uses; the duplicate share of the
bed's energy under every one of those nine is 0.000; deleting every duplicate
from the mix moves the worst reading by 0.10 dB; and swept from 0 to 0.55 the
duck moves the count not at all. What is under an activation is the tail of
the activations before it, and measured in each activation's own third-octave
band - which is how masking in the ear actually works - all nine emerge by
+3.3 dB or more. `band_masking_report` is the instrument that says so, it is
checked against an independent transform, and the duck ships built and off.

**Nine tiles were under the player's own UI.** A 0.86-wide centred arena puts
the right side of the ring beneath YouTube's action rail, and on seed 3530 one
of those tiles is the forty-ninth to activate - so at 48/51 one of the three
remaining dark tiles was behind an icon. The composition now clears it, and the
tests below assert the clearance on every pacing-valid seed rather than on the
one that exposed it.

**The counter was under the title block, and the gate left litter.** "X / 51"
sat at 0.836-0.878 of the frame where YouTube draws the channel handle, and a
fully retracted gate tile was scaled to 2% rather than hidden - fourteen lit
sub-pixel slabs that stayed on screen from the settled beat to the last frame.

Nothing here launches Godot or ffmpeg, and nothing here writes to `output/`.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re

import pytest

from audio import loudness
from satisfying import (
    tile_audio,
    tile_completion,
    tile_playback,
    tile_production,
    tile_readability,
    tile_safe_area,
    tile_score,
)
from satisfying.tile_escape import simulate
from satisfying.tile_sweep import PHASE2_ARENA, PHASE2_CONFIG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_GD = os.path.join(REPO, "godot", "scripts", "tile_escape_scene.gd")
SCORE_PY = os.path.join(REPO, "satisfying", "tile_score.py")

PHASE6_CONFIG = dataclasses.replace(PHASE2_CONFIG, speed=85.0)

PRIMARY_SEED = 3530
# The four secondary seeds Phase 5 validated on, so a composition claim is
# about the geometry rather than about one activation order.
SECONDARY_SEEDS = (26267, 37169, 6132, 7541)
DENSE_SEED = 37169


def gd_code(source: str) -> str:
    """GDScript with its comments stripped, so prose is not read as code."""
    return "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )


def gd_constant(source: str, name: str) -> float:
    match = re.search(rf"^const\s+{name}\s*:=\s*(-?[\d.]+)", source,
                      re.MULTILINE)
    assert match is not None, f"{name} is not a constant in the scene"
    return float(match.group(1))


@pytest.fixture(scope="module")
def scene_source() -> str:
    with open(SCENE_GD, "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def run():
    return simulate(PRIMARY_SEED, PHASE6_CONFIG, PHASE2_ARENA)


@pytest.fixture(scope="module")
def document(run):
    base = tile_playback.playback_document(run)
    return tile_completion.attach_completion(base, run, PHASE2_ARENA)


@pytest.fixture(scope="module")
def dense_document():
    fresh = simulate(DENSE_SEED, PHASE6_CONFIG, PHASE2_ARENA)
    base = tile_playback.playback_document(fresh)
    return tile_completion.attach_completion(base, fresh, PHASE2_ARENA)


@pytest.fixture(scope="module")
def production():
    return tile_production.PRODUCTION


@pytest.fixture(scope="module")
def plan(document, production):
    return tile_score.schedule(document, production.audio_config)


@pytest.fixture(scope="module")
def rendered(plan):
    return tile_audio.render(plan)


# --------------------------------------------------------------------------
# Part 1 - the activation duck
# --------------------------------------------------------------------------


def test_the_activation_duck_is_deterministic(document, production):
    """Same document, same configuration, same ducked gains - twice."""
    config = dataclasses.replace(production.audio_config,
                                 activation_duck=True)
    first = tile_score.schedule(document, config)
    second = tile_score.schedule(document, config)
    assert [event.as_dict() for event in first.events] == \
           [event.as_dict() for event in second.events]
    scales = [event.activation_duck_scale for event in first.events]
    assert scales == [event.activation_duck_scale for event in second.events]
    # And it is a function of the canonical times, not of iteration order: a
    # schedule built from a freshly simulated document agrees too.
    fresh = simulate(PRIMARY_SEED, PHASE6_CONFIG, PHASE2_ARENA)
    rebuilt = tile_completion.attach_completion(
        tile_playback.playback_document(fresh), fresh, PHASE2_ARENA)
    third = tile_score.schedule(rebuilt, config)
    assert [event.activation_duck_scale for event in third.events] == scales


def test_the_duck_touches_duplicates_and_nothing_else(dense_document,
                                                      production):
    """The requirement that makes it a duck and not a compressor.

    Checked on the densest seed, because that is the one with duplicates close
    enough to an activation for the duck to have anything to do.
    """
    config = dataclasses.replace(production.audio_config,
                                 activation_duck=True,
                                 activation_duck_depth=0.5)
    plan = tile_score.schedule(dense_document, config)
    touched = [event for event in plan.events
               if event.activation_duck_scale < 1.0]
    assert touched, "the dense seed should exercise the duck"
    assert {event.kind for event in touched} == {"duplicate"}
    for event in plan.events:
        if event.kind != "duplicate":
            assert event.activation_duck_scale == 1.0, event.kind


def test_the_duck_never_silences_a_duplicate(dense_document, production):
    """"Do not make duplicate collisions disappear completely."""
    for depth in (0.1, 0.32, 0.5, 0.9):
        config = dataclasses.replace(production.audio_config,
                                     activation_duck=True,
                                     activation_duck_depth=depth)
        plan = tile_score.schedule(dense_document, config)
        for event in plan.events:
            if event.kind == "duplicate":
                assert event.activation_duck_scale >= 1.0 - depth - 1e-12
                assert event.gain > 0.0
    with pytest.raises(tile_score.ScoreError):
        dataclasses.replace(production.audio_config,
                            activation_duck_depth=1.0)


def test_the_duck_is_shaped_so_it_cannot_step(production):
    """Full at the activation, zero at the edges, monotone between.

    A switched duck would put a several-decibel step between two consecutive
    duplicates. The weight is what stops that, so it is asserted directly.
    """
    config = dataclasses.replace(production.audio_config,
                                 activation_duck=True)
    lead = config.activation_duck_lead_seconds
    tail = config.activation_duck_tail_seconds
    assert tile_score.activation_duck_weight(0.0, config) == 1.0
    assert tile_score.activation_duck_weight(-lead, config) == 0.0
    assert tile_score.activation_duck_weight(tail, config) == 0.0
    assert tile_score.activation_duck_weight(-lead * 2, config) == 0.0
    assert tile_score.activation_duck_weight(tail * 2, config) == 0.0
    before = [tile_score.activation_duck_weight(-lead * k / 20.0, config)
              for k in range(21)]
    assert before == sorted(before, reverse=True)
    after = [tile_score.activation_duck_weight(tail * k / 20.0, config)
             for k in range(21)]
    assert after == sorted(after, reverse=True)


def test_the_duck_is_off_in_the_production_configuration(production):
    """Part 1's outcome, pinned.

    "Use the smallest reduction necessary" - and Phase 6 measured that the
    necessary reduction is zero, because no duplicate is ever in the window the
    defect was reported from. If someone turns this on, they should have a new
    measurement to point at.
    """
    assert production.audio_config.activation_duck is False
    assert tile_score.DEFAULT_CONFIG.activation_duck is False
    for name, config in tile_score.CONFIGS.items():
        assert config.activation_duck is False, name


def test_the_duck_cannot_reach_the_events_it_is_protecting(document,
                                                           production):
    """Turning it on must not move one activation, final, unlock or escape."""
    off = tile_score.schedule(document, production.audio_config)
    on = tile_score.schedule(
        document, dataclasses.replace(production.audio_config,
                                      activation_duck=True,
                                      activation_duck_depth=0.9))
    by_kind = lambda plan, kind: [
        (event.at_seconds, event.gain, event.pan, event.freq)
        for event in plan.events if event.kind == kind
    ]
    for kind in ("activation", "final", "unlock", "escape", "confirm"):
        assert by_kind(off, kind) == by_kind(on, kind), kind


# --------------------------------------------------------------------------
# Part 1 - the instrument that replaced the duck
# --------------------------------------------------------------------------


def test_the_band_measurement_agrees_with_an_independent_transform():
    """The Goertzel band is the DFT band, on signals with a known answer.

    Phase 6's decision rests on this instrument, so it is checked against
    numpy's transform rather than against itself.
    """
    numpy = pytest.importorskip("numpy")
    rate = 48000
    length = tile_audio.seconds_to_samples(
        tile_audio.EVENT_WINDOW_SECONDS, rate)
    third = tile_audio.THIRD_OCTAVE_RATIO
    for freq in (220.0, 261.63, 440.0, 880.0):
        signal = [math.sin(2.0 * math.pi * freq * i / rate)
                  + 0.4 * math.sin(2.0 * math.pi * freq * 1.5 * i / rate)
                  for i in range(length * 2)]
        low, high = freq / third, freq * third
        mine = tile_audio._band_power(signal, 0, length, rate, low, high)

        segment = numpy.asarray(signal[:length], dtype=float)
        spectrum = numpy.fft.rfft(segment * numpy.hanning(length))
        resolution = rate / length
        first = int(math.ceil(low / resolution))
        last = int(math.floor(high / resolution))
        theirs = float(sum(abs(spectrum[k]) ** 2
                           for k in range(max(0, first),
                                          min(last, length // 2) + 1)))
        assert mine == pytest.approx(theirs, rel=1e-9)


def test_the_band_measurement_rejects_energy_outside_the_band():
    """What makes it the right instrument: it is frequency-selective.

    A broadband window cannot tell a note arriving in an empty channel from a
    note buried under one at the same pitch. This one can, and the rejection is
    what that means quantitatively.
    """
    rate = 48000
    length = tile_audio.seconds_to_samples(
        tile_audio.EVENT_WINDOW_SECONDS, rate)
    third = tile_audio.THIRD_OCTAVE_RATIO
    freq = 440.0
    low, high = freq / third, freq * third
    inside = [math.sin(2.0 * math.pi * freq * i / rate)
              for i in range(length)]
    outside = [math.sin(2.0 * math.pi * freq * 1.5 * i / rate)
               for i in range(length)]
    here = tile_audio._band_power(inside, 0, length, rate, low, high)
    there = tile_audio._band_power(outside, 0, length, rate, low, high)
    rejection = 10.0 * math.log10(here / max(there, 1e-30))
    assert rejection > 40.0, f"only {rejection:.1f} dB of rejection"


def test_every_activation_clears_the_bed_in_its_own_band(rendered):
    """The reading that settles Part 1 on the production master."""
    report = tile_audio.band_masking_report(rendered)
    activation = report["activation"]
    assert activation["count"] == 50
    assert activation["masked_count"] == 0
    assert activation["min_emergence_db"] >= 3.0
    assert activation["median_emergence_db"] > 20.0


def test_every_activation_clears_the_bed_through_a_phone(rendered):
    """And on the speaker most of the audience is using."""
    from array import array

    stereo = loudness.as_stereo(rendered.left, rendered.right)
    small = loudness.phone_filter(stereo, rendered.sample_rate)
    numpy = pytest.importorskip("numpy")
    pair = numpy.repeat(small, 2, axis=1)
    left = array("d", pair[:, 0].tolist())
    right = array("d", pair[:, 1].tolist())
    report = tile_audio.band_masking_report(rendered, left, right)
    assert report["activation"]["masked_count"] == 0
    assert report["activation"]["min_emergence_db"] >= 3.0


def test_the_duplicate_bed_is_empty_where_the_defect_was_reported(
        dense_document, production):
    """The measurement that made the prescribed fix inapplicable.

    On the densest pacing-valid seed, no activation has a duplicate placed
    inside the 55 ms window `masking_report` reads. That is *why* ducking the
    duplicates could not move the number, and it is worth a test because it is
    the least obvious fact in the phase.
    """
    plan = tile_score.schedule(dense_document, production.audio_config)
    window = tile_audio.EVENT_WINDOW_SECONDS
    duplicates = [event.at_seconds for event in plan.events
                  if event.kind == "duplicate"]
    for event in plan.events:
        if event.kind != "activation":
            continue
        crowding = [t for t in duplicates
                    if 0.0 < event.at_seconds - t < window]
        assert not crowding, (
            f"activation at {event.at_seconds} has a duplicate "
            f"{crowding} inside the measurement window"
        )


# --------------------------------------------------------------------------
# Part 5 - the hierarchy, and no clipping
# --------------------------------------------------------------------------


def test_the_event_hierarchy_survives_into_the_master(rendered):
    """Configured, rendered, folded and filtered - the order never inverts."""
    from array import array

    numpy = pytest.importorskip("numpy")
    config = rendered.schedule.config
    assert config.duplicate_gain < config.activation_gain < config.final_gain

    stereo = loudness.as_stereo(rendered.left, rendered.right)
    views = {"master": (rendered.left, rendered.right)}
    for label, folded in (("mono", loudness.mono_fold(stereo)),
                          ("phone", loudness.phone_filter(
                              stereo, rendered.sample_rate))):
        if folded.ndim == 1:
            folded = folded.reshape(-1, 1)
        pair = numpy.repeat(folded, 2, axis=1) if folded.shape[1] == 1 \
            else folded
        views[label] = (array("d", pair[:, 0].tolist()),
                        array("d", pair[:, 1].tolist()))

    for label, (left, right) in views.items():
        levels = tile_audio._hierarchy(rendered, left, right)
        duplicate = levels["duplicate"]["median_dbfs"]
        activation = levels["activation"]["median_dbfs"]
        final = levels["final"]["median_dbfs"]
        assert duplicate < activation < final, label
        assert activation - duplicate > 6.0, f"{label}: only {activation - duplicate:.2f} dB"
        assert final - activation > 3.0, label


def test_the_master_does_not_clip(rendered):
    report = tile_audio.measure(rendered, phone=False)
    assert report["peak"]["clipped_samples"] == 0
    assert report["peak"]["sample_peak_dbfs"] <= tile_audio.PEAK_CEILING_DBFS
    assert report["peak"]["true_peak_dbtp"] <= -1.0
    # The static master gain is a guarantee, not a stage: if the limiter is
    # doing work, an event's peak is no longer its configured gain.
    assert rendered.limited is False
    assert rendered.limiter_gain == pytest.approx(1.0, abs=1e-9)


def test_the_master_ends_in_deliberate_silence(rendered):
    """The ending is a controlled reduction, so it is asserted as one."""
    config = rendered.schedule.config
    tail = tile_audio.seconds_to_samples(config.end_silence_seconds * 0.5,
                                         config.sample_rate)
    for channel in (rendered.left, rendered.right):
        assert max(abs(value) for value in channel[-tail:]) == 0.0


def test_the_mono_fold_loses_only_what_the_pan_law_predicts(plan):
    """Amplitude summing is arithmetic; anything beyond it is cancellation."""
    config = plan.config
    predicted = 20.0 * math.log10(
        sum(tile_audio.pan_gains(config.pan_depth)) / 2.0)
    for event in plan.events:
        gains = tile_audio.pan_gains(event.pan)
        loss = 20.0 * math.log10(max(sum(gains) / 2.0, 1e-12))
        assert loss >= predicted - 1e-9, (
            f"{event.kind} at pan {event.pan} loses {loss:.4f} dB against a "
            f"pan-law worst case of {predicted:.4f} dB"
        )


# --------------------------------------------------------------------------
# Part 7 - the audio is exactly as long as the picture
# --------------------------------------------------------------------------


def test_the_audio_length_matches_the_presentation_timeline(plan, document,
                                                            production):
    """One frame of video is 1,600 samples at 48000/30, so this is exact."""
    total_render = float(document["completion"]["total_render_seconds"])
    frames = int(round(total_render * production.fps)) + 1
    assert plan.frames == frames
    assert plan.total_seconds == pytest.approx(frames / production.fps,
                                               rel=1e-12)
    samples_per_frame = production.audio_sample_rate / production.fps
    assert samples_per_frame == int(samples_per_frame)
    assert plan.total_samples == frames * int(samples_per_frame)


def test_every_cue_lands_on_the_frame_that_shows_it(plan, document):
    """Part 8's synchronisation requirement, at the schedule level."""
    report = tile_audio.sync_report(plan, document)
    assert report["frame_mismatches"] == []
    assert report["max_placement_error_seconds"] == 0.0


def test_the_climax_beats_come_from_the_timeline_and_not_from_a_preset(
        plan, document):
    """A re-timed ending must carry the sound with it."""
    beats = {segment["state"]: float(segment["render_start"])
             for segment in document["completion"]["timeline"]}
    for kind, state in (("final", "final_hit"), ("unlock", "unlocking"),
                        ("escape", "escaping")):
        events = plan.of_kind(kind)
        assert len(events) == 1, kind
        assert events[0].render_seconds == pytest.approx(beats[state],
                                                         abs=1e-9)


# --------------------------------------------------------------------------
# Part 3 - the safe area
# --------------------------------------------------------------------------


def test_the_safe_area_configurations_parse_and_are_stable():
    """Part 3's "safe-area config parses and remains stable"."""
    assert tile_safe_area.SAFE_AREA_FORMAT == 1
    for name, config in tile_safe_area.SAFE_AREAS.items():
        assert config.name == name
        assert config.regions
        assert config.fingerprint() == config.fingerprint()
        payload = json.dumps(config.as_dict(), sort_keys=True)
        assert json.loads(payload)["name"] == name
        for region in config.regions:
            assert 0.0 <= region.left < region.right <= 1.0
            assert 0.0 <= region.top < region.bottom <= 1.0
    fingerprints = {config.fingerprint()
                    for config in tile_safe_area.SAFE_AREAS.values()}
    assert len(fingerprints) == len(tile_safe_area.SAFE_AREAS)
    # The fingerprint has to move when any dial does, or it cannot be a lock.
    base = tile_safe_area.DEFAULT_SAFE_AREA
    for field, value in (("tile_obstructed_fraction", 0.4),
                         ("ball_hidden_fraction", 0.7),
                         ("ball_hidden_budget_seconds", 0.5),
                         ("fps", 60.0)):
        assert dataclasses.replace(base, **{field: value}).fingerprint() \
            != base.fingerprint(), field


def test_a_broken_safe_area_is_refused_rather_than_measured():
    with pytest.raises(tile_safe_area.SafeAreaError):
        tile_safe_area.Region("bad", 0.5, 0.1, 0.4, 0.2)
    with pytest.raises(tile_safe_area.SafeAreaError):
        tile_safe_area.Region("bad", 0.1, 0.1, 1.4, 0.2)
    with pytest.raises(tile_safe_area.SafeAreaError):
        dataclasses.replace(tile_safe_area.DEFAULT_SAFE_AREA, regions=())
    with pytest.raises(tile_safe_area.SafeAreaError):
        dataclasses.replace(tile_safe_area.DEFAULT_SAFE_AREA,
                            tile_obstructed_fraction=0.0)
    with pytest.raises(tile_safe_area.SafeAreaError):
        tile_safe_area.named_safe_area("not_a_model")


@pytest.mark.parametrize("seed", (PRIMARY_SEED,) + SECONDARY_SEEDS)
def test_no_tile_sits_under_the_player_ui_on_any_valid_seed(seed):
    """The composition claim, made about the geometry rather than one run.

    Which tiles the rail covers does not depend on the seed at all - the arena
    is the same ring every time - so this would pass on one seed if it passes
    on any. It is parametrised anyway because the *consequence* is per seed:
    the last four tiles to light are the ones a viewer hunts, and those differ.
    """
    fresh = simulate(seed, PHASE6_CONFIG, PHASE2_ARENA)
    document = tile_completion.attach_completion(
        tile_playback.playback_document(fresh), fresh, PHASE2_ARENA)
    area = tile_safe_area.named_safe_area(
        tile_production.PRODUCTION.safe_area)
    report = tile_safe_area.report(document, area, 1080, 1920)
    assert report["tiles"]["obstructed_count"] == 0, (
        f"seed {seed}: tiles {report['tiles']['obstructed_tiles']} are under "
        "the UI"
    )
    assert report["final_tile"]["worst_fraction"] < \
        area.tile_obstructed_fraction
    order = [int(entry["tile"]) for entry in document["activations"]]
    per_tile = {row["tile"]: row for row in report["per_tile"]}
    for tile in order[-4:]:
        assert not per_tile[tile]["obstructed"], (
            f"seed {seed}: tile {tile} is one of the last four to light and is "
            "under the UI"
        )
    assert report["ball"]["within_budget"], (
        f"seed {seed}: the ball is hidden for "
        f"{report['ball']['longest_hidden_seconds']}s"
    )


def test_the_arena_clears_the_action_rail_with_room(document):
    """The clearance, as a distance rather than as a verdict."""
    area = tile_safe_area.named_safe_area(
        tile_production.PRODUCTION.safe_area)
    rail = next(region for region in area.regions
                if region.name == "action_rail")
    geometry = tile_readability.frame_geometry(document, 1080, 1920)
    assert geometry["arena_right_px"] < rail.left * 1080
    # And it must not have been bought by pushing the arena off the other side.
    assert geometry["arena_left_px"] > 0.04 * 1080


def test_the_composition_moved_off_centre_and_the_escape_knows(document):
    """The frame's world bounds follow the camera, or the escape is wrong.

    `tile_completion` decides when the ball has left the frame. Phase 6 moved
    the frame, and an escape computed against a centred one would cut the ball
    off on one side and leave it hanging on the other.
    """
    assert tile_readability.ARENA_CENTRE_OFFSET_FRACTION != 0.0
    assert tile_completion.ARENA_CENTRE_OFFSET_FRACTION == \
        tile_readability.ARENA_CENTRE_OFFSET_FRACTION
    assert tile_completion.ARENA_WIDTH_FRACTION == \
        tile_readability.ARENA_WIDTH_FRACTION
    route = document["completion"]["route"]
    half_width = float(route["frame_half_width_wu"])
    centre = -tile_completion.ARENA_CENTRE_OFFSET_FRACTION * 2.0 * half_width
    exit_x = float(route["exit_position"][0])
    exit_y = float(route["exit_position"][1])
    margin = float(document["completion"]["timing"]["exit_margin_wu"])
    left = centre - half_width - margin
    right = centre + half_width + margin
    top = float(route["frame_half_height_wu"]) + margin
    # The ball leaves through exactly one of the four bounds, and it is on it.
    on_bound = (
        math.isclose(exit_x, left, abs_tol=1e-6)
        or math.isclose(exit_x, right, abs_tol=1e-6)
        or math.isclose(abs(exit_y), top, abs_tol=1e-6)
    )
    assert on_bound, (exit_x, exit_y, left, right, top)


def test_the_counter_is_placed_clear_of_the_title_block():
    """Measured from the real glyph offsets, not from the label's own top.

    Godot draws the counter's glyphs 0.0209 of the frame height below the
    control's top edge and 0.0625 below it at the baseline - measured on a
    rendered frame, because the font's metrics are not a number this side
    knows. `COUNTER_TOP_FRACTION` has to leave the glyph box above every
    model's title block.
    """
    glyph_top = tile_readability.COUNTER_TOP_FRACTION + 0.0209
    glyph_bottom = tile_readability.COUNTER_TOP_FRACTION + 0.0625
    for name, area in tile_safe_area.SAFE_AREAS.items():
        block = next(region for region in area.regions
                     if region.name == "title_block")
        assert glyph_bottom < block.top, (
            f"{name}: the counter's glyphs reach {glyph_bottom:.4f} and the "
            f"title block starts at {block.top}"
        )
    assert glyph_top > 0.70, "the counter has been pushed into the arena"


def test_the_hook_is_placed_clear_of_the_top_bar():
    glyph_top = tile_readability.HOOK_TOP_FRACTION + 0.0104
    for name, area in tile_safe_area.SAFE_AREAS.items():
        bar = next(region for region in area.regions
                   if region.name == "top_bar")
        assert glyph_top > bar.bottom, name


# --------------------------------------------------------------------------
# Part 4 - the gate leaves nothing behind
# --------------------------------------------------------------------------


def test_a_fully_retracted_gate_tile_is_hidden_not_shrunk(scene_source):
    """The fourteen stray pixels, asserted away.

    A tile scaled to the floor with zero emission is still a lit sub-pixel
    slab of albedo. The scene has to hide the node, and it has to show it
    again when the gate is not retracting, because the function runs fresh on
    every frame and remembers nothing.
    """
    code = gd_code(scene_source)
    assert "GATE_RETRACT_MIN_SCALE" in code
    assert gd_constant(scene_source, "GATE_RETRACT_MIN_SCALE") > 0.0
    assert "_tiles[i].visible = raw_shrink > GATE_RETRACT_MIN_SCALE" in code
    assert "_tiles[i].visible = true" in code
    # The old form, which is what left the litter.
    assert "maxf(0.02, 1.0 - e)" not in code


# --------------------------------------------------------------------------
# The canonical data is still canonical
# --------------------------------------------------------------------------


def test_the_canonical_playback_is_unchanged_by_anything_phase_six_added(
        run, document):
    """Phase 6 touched the frame, the sound and the delivery. Not the run."""
    before = json.dumps(document, sort_keys=True)
    config = tile_production.PRODUCTION.audio_config
    plan = tile_score.schedule(document, config)
    tile_audio.render(plan)
    tile_safe_area.report(document, tile_safe_area.DEFAULT_SAFE_AREA)
    tile_readability.frame_geometry(document, 1080, 1920)
    tile_production.identity(document)
    assert json.dumps(document, sort_keys=True) == before
    tile_playback.verify_document(document)
    # And the physics itself: the same seed and config give the same digest.
    again = simulate(PRIMARY_SEED, PHASE6_CONFIG, PHASE2_ARENA)
    rebuilt = tile_playback.playback_document(again)
    assert rebuilt["digest"] == tile_playback.playback_document(run)["digest"]


def test_the_locked_simulation_parameters_are_what_the_brief_locked():
    """17 sides, 3 tiles a side, 51 tiles, no gravity, 85 wu/s, one ball."""
    assert PHASE2_ARENA.sides == 17
    assert PHASE2_ARENA.tiles_per_side == 3
    assert len(PHASE2_ARENA.tiles) == 51
    assert PHASE6_CONFIG.speed == 85.0
    assert PHASE6_CONFIG.gravity == 0.0


# --------------------------------------------------------------------------
# Part 2 and Part 9 - the production identity
# --------------------------------------------------------------------------


def test_the_hook_is_the_line_part_two_chose(production):
    """Part 2 compared two hooks and retained A. That decision is pinned."""
    assert production.hook == "HIT EVERY TILE TO ESCAPE"
    with open(SCENE_GD, "r", encoding="utf-8") as handle:
        assert f'HOOK_DEFAULT := "{production.hook}"' in handle.read()


def test_the_production_configuration_is_deterministic_and_digestible(
        production):
    """Part 9's "production config digest stability"."""
    assert tile_production.PRODUCTION_FORMAT == 1
    assert production.fingerprint() == production.fingerprint()
    assert production.fingerprint() == \
        tile_production.ProductionConfig().fingerprint()
    assert len(production.fingerprint()) == 16
    payload = json.dumps(production.as_dict(), sort_keys=True)
    assert json.loads(payload)["seed"] == 3530
    for field, value in (("seed", 26267), ("crf", 18), ("fps", 60.0),
                         ("hook", "SOMETHING ELSE"), ("audio", "v2_refined"),
                         ("safe_area", "shorts_measured"), ("preset", "fast"),
                         ("audio_bitrate", "256k"), ("width", 720)):
        moved = dataclasses.replace(production, **{field: value})
        assert moved.fingerprint() != production.fingerprint(), field


def test_the_production_identity_is_layered_so_a_mismatch_says_where(
        document, production):
    payload = tile_production.identity(document, production)
    for section in ("production", "audio", "composition", "safe_area",
                    "encode", "run"):
        assert section in payload, section
    assert payload["audio"]["fingerprint"] == \
        production.audio_config.fingerprint()
    assert payload["safe_area"]["fingerprint"] == \
        production.safe_area_config.fingerprint()
    assert payload["run"]["digest"] == str(document["digest"])
    assert payload["run"]["frames"] == int(round(
        float(document["completion"]["total_render_seconds"])
        * production.fps)) + 1
    assert payload["composition"]["arena_width_fraction"] == \
        tile_readability.ARENA_WIDTH_FRACTION
    # A composition change has to show up in the identity, which is the whole
    # reason the composition is in there rather than assumed.
    assert payload["composition"]["counter_top_fraction"] == \
        tile_readability.COUNTER_TOP_FRACTION
    assert json.dumps(payload, sort_keys=True)


def test_the_production_refuses_a_configuration_it_cannot_deliver():
    for field, value in (("audio", "not_a_config"),
                         ("safe_area", "not_a_model"),
                         ("hook", "   "),
                         ("crf", 99),
                         ("fps", 0.0),
                         ("width", 0)):
        with pytest.raises(tile_production.ProductionError):
            dataclasses.replace(tile_production.PRODUCTION, **{field: value})
    # A vertical frame is the format, so a landscape one is a mistake.
    with pytest.raises(tile_production.ProductionError):
        dataclasses.replace(tile_production.PRODUCTION, width=1920,
                            height=1080)
    # An archive worse than the delivery file is the wrong way round.
    with pytest.raises(tile_production.ProductionError):
        dataclasses.replace(tile_production.PRODUCTION, archive_crf=30)


def test_the_production_audio_configuration_is_the_chosen_treatment(
        production):
    """The creative lock: seed 3530, the drone confirmation hold."""
    assert production.seed == 3530
    assert production.audio == "v3_hold_drone"
    assert production.audio_config.confirmation == "drone"
    assert production.audio_config.has_confirm_layer is True
    assert tile_score.DEFAULT_CONFIG is tile_score.CONFIGS["v3_hold_drone"]
    # `fps` is overridden from the production, not inherited from the config.
    assert production.audio_config.fps == production.fps


def test_the_video_carries_no_upload_metadata():
    """"Do not add YouTube metadata into the video itself"."""
    fields = set(tile_production.PRODUCTION.as_dict())
    for forbidden in ("title", "description", "tags", "thumbnail",
                      "category", "playlist", "channel"):
        assert forbidden not in fields, forbidden


# --------------------------------------------------------------------------
# Python and GDScript still agree
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name, python_value", [
    ("ARENA_WIDTH_FRACTION", tile_readability.ARENA_WIDTH_FRACTION),
    ("ARENA_CENTRE_OFFSET_FRACTION",
     tile_readability.ARENA_CENTRE_OFFSET_FRACTION),
    ("COUNTER_TOP_FRACTION", tile_readability.COUNTER_TOP_FRACTION),
    ("HOOK_TOP_FRACTION", tile_readability.HOOK_TOP_FRACTION),
    ("TILE_RADIAL_THICKNESS", tile_readability.TILE_RADIAL_THICKNESS),
])
def test_phase_six_constants_are_mirrored_in_the_scene(scene_source, name,
                                                       python_value):
    """`tile_safe_area` predicts pixel positions from these.

    If the scene's copy drifts, the safe-area report describes a render nobody
    made - and it would still say PASS.
    """
    assert gd_constant(scene_source, name) == pytest.approx(python_value)


def test_the_camera_offset_is_applied_in_camera_units(scene_source):
    """Resolution independence, asserted where it is easy to break.

    The offset is a fraction of the frame; the camera has to convert it with
    its own `size`, or the composition would move when the render size did.
    """
    code = gd_code(scene_source)
    assert "-ARENA_CENTRE_OFFSET_FRACTION * _camera.size" in code
    assert "look_at_from_position(Vector3(centre_x, 0.0, 60.0)" in code


def test_the_projection_is_still_a_pure_scale_plus_a_translation(document):
    """Every distance this repository measures depends on it.

    An offset cancels in a difference of two projected points, which is what
    lets Phase 3's motion and readability arithmetic survive Phase 6 moving the
    arena.
    """
    scale = tile_readability.pixels_per_unit(document, 1080)
    for a, b in (((0.0, 0.0), (1.0, 0.0)), ((-8.0, 7.0), (-7.0, 7.0)),
                 ((3.0, -2.0), (3.0, -1.0))):
        pa = tile_readability.project(document, a, 1080, 1920)
        pb = tile_readability.project(document, b, 1080, 1920)
        assert math.dist(pa, pb) == pytest.approx(scale, rel=1e-12)
