"""Phase 5: a soundtrack the simulation wrote, and cannot be written back by.

Phase 3 asked whether a renderer could change the run. Phase 4 asked whether an
ending could. Phase 5 adds a third thing downstream of the physics, and these
tests are the same question a third time, plus the ones audio brings with it.

**It cannot reach the physics.** `tile_score` imports no synthesiser and
`tile_audio` imports no simulator; neither takes a seed. A test reads the
module sources and asserts that, because "the audio does not affect the run" is
an architectural property and an architectural property is checkable.

**The clock is the picture's clock.** The simulation stops for 0.92 s in the
middle of the ending. A cue written against simulation time would stall with
it, and three of these tests are about exactly that stretch: the beats come out
of `completion["timeline"]` by state name, the paused section carries three
distinct cues at three distinct render instants, and the mapping from
simulation time to render time is not used anywhere in the score.

**The hierarchy is a contract.** Phase 4 pinned three visual strengths -
brightness, brightness plus motion, a white detonation - and said Phase 5 would
mirror them. The mirror is asserted at three levels: the configured gains, the
rendered cues in isolation, and the finished master measured through a
phone-speaker approximation, which is where the first version of the final hit
failed.

Six defects found while building this phase have regressions here, and every
one of them was found by measuring rather than by listening. Four were in the
sound:

* the detonation, voiced root-upward, put its energy under 500 Hz and measured
  **+0.4 dB RMS** over an ordinary activation through `loudness.phone_filter`
  while its configured gain said +8;
* the gate's rising glide was given a struck envelope, so its energy sat at
  the *bottom* of the rise and the unlock measured 7 dB below an activation on
  a phone;
* the release was a fixed 1.56 s against a video that had between 1.17 and
  1.53 s left for it, so on every seed it was cut off by the end of the buffer
  rather than ending - seed 37169's last sample measured **-26.9 dBFS**;
* the progression made a late activation measurably *darker* than an early one
  while every gain in it moved the right way, for two separate reasons, and a
  monotone spectral centroid is now asserted across the whole run.

And two were in the instruments that were supposed to find the others:

* the per-event level was measured in a window from where the cue was placed,
  which reads the silence at the start of a swell rather than the swell;
* phase dispersion - the first attempt at the detonation's dilution - was
  measured as a fix and is not one: it moved the chord's normalised energy by
  between +2.6 and -1.5 dB depending on the frequency set, and cancelled two
  voices that shared a pitch by 18.3 dB. It was removed, and three tests here
  are about why it is not coming back.

Nothing here launches Godot or ffmpeg, and nothing here writes to `output/`.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os

import pytest

from audio.synthesis import gain_to_db, peak
from satisfying.tile_audio import PEAK_CEILING, PEAK_CEILING_DBFS
from satisfying import tile_audio, tile_completion, tile_playback, tile_score
from satisfying.tile_escape import simulate
from satisfying.tile_sweep import PHASE2_ARENA, PHASE2_CONFIG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORE_PY = os.path.join(REPO, "satisfying", "tile_score.py")
AUDIO_PY = os.path.join(REPO, "satisfying", "tile_audio.py")

PHASE5_CONFIG = dataclasses.replace(PHASE2_CONFIG, speed=85.0)

# Phase 5's primary reference and one secondary, both pacing-gate valid. Named
# constants rather than a search: Phase 2 and Phase 4 paid for the selection.
PRIMARY_SEED = 3530     # the brief's audio proof seed
DENSE_SEED = 37169      # 194 contacts, 6.06/s - the density stress case
FAST_SEED = 26267       # 30.30 s, 145 contacts - the sparsest valid run


def strip_prose(source: str) -> str:
    """Source with its comments and docstrings removed.

    A test that looks for a name in a module has to look at the code and not
    at the prose around it, or a paragraph explaining why something is absent
    reads as the thing being present.
    """
    blocks = source.split('"""')
    code = "".join(blocks[index] for index in range(0, len(blocks), 2))
    return "\n".join(line for line in code.splitlines()
                      if not line.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def run():
    return simulate(PRIMARY_SEED, PHASE5_CONFIG, PHASE2_ARENA)


@pytest.fixture(scope="module")
def document(run):
    base = tile_playback.playback_document(run)
    return tile_completion.attach_completion(base, run, PHASE2_ARENA)


@pytest.fixture(scope="module")
def dense_document():
    fresh = simulate(DENSE_SEED, PHASE5_CONFIG, PHASE2_ARENA)
    base = tile_playback.playback_document(fresh)
    return tile_completion.attach_completion(base, fresh, PHASE2_ARENA)


@pytest.fixture(scope="module")
def plan(document):
    return tile_score.schedule(document, tile_score.DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def rendered(plan):
    return tile_audio.render(plan)


@pytest.fixture(scope="module")
def report(rendered, document):
    return tile_audio.measure(rendered, phone=True, document=document)


# ==========================================================================
# 1. The pitch mapping: a function of the arena, not of the run
# ==========================================================================


def test_pitch_table_is_the_scale_over_the_register():
    table = tile_score.pitch_table()
    config = tile_score.DEFAULT_CONFIG
    assert len(table) == config.pitches == 11
    assert table[0] == pytest.approx(config.root_hz)
    # The last note closes the register exactly two octaves up.
    assert table[-1] == pytest.approx(config.root_hz * 2 ** config.octaves)
    assert table == tuple(sorted(table))


def test_pentatonic_has_no_semitone_and_no_tritone():
    """Why this scale and not another: any two notes can land together.

    The ball chooses the order, so consonance cannot be arranged - it has to
    be a property of the set. Every interval between every pair of the eleven
    pitches, reduced into one octave, is checked against the two that would
    make an arbitrary pair unpleasant.
    """
    table = tile_score.pitch_table()
    for low in range(len(table)):
        for high in range(low + 1, len(table)):
            semitones = 12.0 * math.log2(table[high] / table[low])
            reduced = round(semitones) % 12
            assert reduced not in (1, 6, 11), (
                f"pitch {low} against {high} is {reduced} semitones apart"
            )


def test_tile_pitch_is_stable_across_seeds_and_runs(document, dense_document):
    """`tile_17` is the same note in every run of every seed.

    The brief's requirement is that the mapping depend on persistent tile
    identity and not on collision order. Two different seeds produce two
    different collision orders over the same arena; the mapping is compared
    tile by tile across both.
    """
    for tile in range(51):
        first = tile_score.frequency_for(document["arena"], tile)
        second = tile_score.frequency_for(dense_document["arena"], tile)
        assert first == second
        assert first == tile_score.frequency_for(document["arena"], tile)


def test_pitch_mapping_is_spatial_and_neighbours_are_related():
    """Neighbouring walls are neighbouring notes, and the ring has no seam.

    The shipped mapping is by height, so two tiles that are adjacent around
    the perimeter are never more than one step of the vocabulary apart -
    including across the wrap from tile 50 to tile 0, which is the place an
    index-based mapping breaks.
    """
    arena = tile_playback.arena_document(PHASE2_ARENA)
    indices = [tile_score.pitch_index_for(arena, tile) for tile in range(51)]
    for tile in range(51):
        step = abs(indices[tile] - indices[(tile + 1) % 51])
        assert step <= 1, f"tiles {tile} and {(tile + 1) % 51} jump {step} steps"


def test_the_v1_control_mapping_is_stable_but_not_spatial():
    """The control is a control: same determinism, none of the meaning.

    If `v1_basic` were also spatially coherent the variant comparison would be
    measuring nothing, so the property that distinguishes them is asserted
    rather than assumed.
    """
    arena = tile_playback.arena_document(PHASE2_ARENA)
    control = tile_score.CONFIGS["v1_basic"]
    indices = [tile_score.pitch_index_for(arena, tile, control)
               for tile in range(51)]
    assert indices == [tile_score.pitch_index_for(arena, tile, control)
                       for tile in range(51)]
    jumps = [abs(indices[tile] - indices[(tile + 1) % 51]) for tile in range(51)]
    assert max(jumps) > 1


def test_the_vocabulary_is_small_and_every_note_is_used():
    """Fifty-one tiles over eleven notes, none of them orphaned."""
    arena = tile_playback.arena_document(PHASE2_ARENA)
    used = [tile_score.pitch_index_for(arena, tile) for tile in range(51)]
    assert set(used) == set(range(tile_score.DEFAULT_CONFIG.pitches))
    assert 2 <= min(used.count(note) for note in set(used))


def test_a_tile_is_panned_by_where_it_is_and_the_ring_is_symmetric():
    arena = tile_playback.arena_document(PHASE2_ARENA)
    pans = [tile_score.pan_for(arena, tile) for tile in range(51)]
    assert max(pans) == pytest.approx(-min(pans), abs=1e-9)
    assert max(abs(value) for value in pans) <= tile_score.DEFAULT_CONFIG.pan_depth
    # Mono placement is what the control asks for, and it gets it.
    control = tile_score.CONFIGS["v1_basic"]
    assert all(tile_score.pan_for(arena, tile, control) == 0.0 for tile in range(51))


# ==========================================================================
# 2. The schedule: deterministic, and on the picture's clock
# ==========================================================================


def test_the_schedule_is_deterministic(document):
    """Same seed, same configuration, same schedule - compared as JSON."""
    first = tile_score.schedule(document, tile_score.DEFAULT_CONFIG)
    second = tile_score.schedule(document, tile_score.DEFAULT_CONFIG)
    assert first.fingerprint() == second.fingerprint()
    assert json.dumps(first.as_dict(), sort_keys=True) == json.dumps(
        second.as_dict(), sort_keys=True)


def test_the_schedule_is_deterministic_across_two_simulations():
    """And the same through a fresh simulation, not just a reused document."""
    fingerprints = set()
    for _ in range(2):
        fresh = simulate(PRIMARY_SEED, PHASE5_CONFIG, PHASE2_ARENA)
        base = tile_playback.playback_document(fresh)
        whole = tile_completion.attach_completion(base, fresh, PHASE2_ARENA)
        fingerprints.add(tile_score.schedule(whole).fingerprint())
    assert len(fingerprints) == 1


def test_two_configurations_give_two_schedules(document):
    seen = {tile_score.schedule(document, config).fingerprint()
            for config in tile_score.CONFIGS.values()}
    assert len(seen) == len(tile_score.CONFIGS)


def test_every_contact_makes_exactly_one_sound(document, plan):
    """One cue per contact, no more and no fewer.

    The brief's first requirement is that a collision produce a sound. A
    dropped duplicate would be a silent bounce; a doubled one would be a flam.
    """
    contacts = len(document["collisions"])
    tile_events = [event for event in plan.events
                   if event.kind in ("duplicate", "activation", "final")]
    assert len(tile_events) == contacts
    assert [event.render_seconds for event in tile_events] == [
        hit["t"] for hit in document["collisions"]]


def test_the_final_tile_fires_exactly_once(document, plan):
    finals = plan.of_kind("final")
    assert len(finals) == 1
    assert len(plan.of_kind("activation")) == document["total_tiles"] - 1
    assert finals[0].tile == document["completion"]["final_tile"]
    assert finals[0].render_seconds == document["completion_seconds"]
    # And it is the last tile event, not merely one of them.
    assert finals[0].render_seconds == max(
        event.render_seconds for event in plan.events
        if event.kind in ("duplicate", "activation", "final"))


def test_events_land_on_the_frame_that_shows_them(document, plan):
    """The placement rule, checked against Phase 3's own function.

    `tile_playback.activation_frames` was written for the Godot audit before
    any of this existed, so agreeing with it is an independent check rather
    than a restatement.
    """
    fps = tile_score.DEFAULT_CONFIG.fps
    expected = tile_playback.activation_frames(document, fps)
    got = [event.frame for event in plan.events
           if event.kind in ("activation", "final")]
    assert got == expected
    for event in plan.events:
        assert event.at_seconds == event.frame / fps
        # On the frame, never before it.
        assert event.at_seconds >= event.render_seconds - 1e-12
        assert event.at_seconds - event.render_seconds < 1.0 / fps + 1e-12


def test_the_frame_rule_matches_playbacks_rule_exactly(document):
    for entry in document["activations"]:
        assert tile_score.frame_for(entry["t"], 30.0) == math.ceil(entry["t"] * 30.0)
    # And a time exactly on a boundary lands on that frame, not the next one.
    assert tile_score.frame_for(1.0, 30.0) == 30
    assert tile_score.frame_for(2.0 / 3.0, 30.0) == 20


# ==========================================================================
# 3. The climax: the presentation timeline, and the 0.92 s hold
# ==========================================================================


def test_the_beats_come_from_the_documents_timeline(document, plan):
    by_state = {segment["state"]: segment
                for segment in document["completion"]["timeline"]}
    for name in tile_score.CLIMAX_BEATS:
        assert plan.beats[name] == by_state[name]["render_start"]


def test_the_climax_cues_sit_on_their_named_beats(plan):
    """final hit, unlock, escape - each on the render instant Phase 4 named."""
    fps = plan.config.fps
    for kind, state in (("final", "final_hit"),
                        ("unlock", "unlocking"),
                        ("escape", "escaping")):
        event = plan.of_kind(kind)[0]
        assert event.render_seconds == plan.beats[state]
        assert event.frame == tile_score.frame_for(plan.beats[state], fps)


def test_the_unlock_and_escape_offsets_are_the_timing_presets(document, plan):
    timing = document["completion"]["timing"]
    completion = document["completion_seconds"]
    assert plan.of_kind("unlock")[0].render_seconds - completion == pytest.approx(
        timing["gate_open_at_seconds"], abs=1e-12)
    assert plan.of_kind("escape")[0].render_seconds - completion == pytest.approx(
        timing["release_at_seconds"], abs=1e-12)


def test_the_paused_section_does_not_collapse_the_audio(document, plan):
    """The 0.92 s the simulation stands still is 0.92 s of sound, not an instant.

    Every cue in the ending sits at the *same* simulation time - the hold has
    rate zero, so `sim_start` never moves - and at three different render
    times. Written against simulation time the three would coincide, and the
    detonation, the gate and the release would arrive as one event.
    """
    segments = {segment["state"]: segment
                for segment in document["completion"]["timeline"]}
    held = ("final_hit", "confirming", "unlocking")
    sim_times = {segments[state]["sim_start"] for state in held}
    assert len(sim_times) == 1, "the hold is supposed to freeze the clock"
    assert all(segments[state]["sim_rate"] == 0.0 for state in held)

    pause = segments["escaping"]["render_start"] - segments["final_hit"]["render_start"]
    assert pause == pytest.approx(0.92, abs=1e-9)

    inside = sorted(event.render_seconds for event in plan.events
                    if segments["final_hit"]["render_start"] <= event.render_seconds
                    < segments["escaping"]["render_start"])
    assert len(inside) >= 2
    assert inside[-1] - inside[0] == pytest.approx(
        document["completion"]["timing"]["gate_open_at_seconds"], abs=1e-9)
    # Distinct frames, which is the property that actually survives to screen.
    frames = {tile_score.frame_for(when, plan.config.fps) for when in inside}
    assert len(frames) == len(inside)


def test_the_drone_hold_puts_a_cue_in_the_pause_and_the_others_do_not(document):
    for name, expected in (("v2_refined", 0), ("v2_hold_breath", 0),
                           ("v1_basic", 0), ("v3_hold_drone", 1)):
        built = tile_score.schedule(document, tile_score.CONFIGS[name])
        assert len(built.of_kind("confirm")) == expected, name
    drone = tile_score.schedule(document, tile_score.CONFIGS["v3_hold_drone"])
    assert drone.of_kind("confirm")[0].render_seconds == drone.beats["confirming"]


def test_the_three_holds_differ_only_in_the_hold(document):
    """A controlled comparison, enforced.

    The confirmation-hold finding is only worth anything if the three
    treatments are otherwise the same system, so every other field of the
    three configurations is compared.
    """
    base = dataclasses.asdict(tile_score.CONFIGS["v2_refined"])
    for name in ("v2_hold_breath", "v3_hold_drone"):
        other = dataclasses.asdict(tile_score.CONFIGS[name])
        differing = {key for key in base if base[key] != other[key]}
        assert differing == {"name", "confirmation"}, (name, differing)


def test_a_run_that_did_not_complete_gets_no_ending(run):
    """No completion block, no unlock and no escape - and no crash."""
    bare = tile_playback.playback_document(run)
    built = tile_score.schedule(bare)
    assert built.completed is False
    assert built.beats == {}
    assert built.of_kind("unlock") == ()
    assert built.of_kind("escape") == ()
    # The last activation is still the final tile; it just has nothing after it.
    assert len(built.of_kind("final")) == 1


def test_a_timeline_whose_locked_segment_is_not_the_identity_is_refused(document):
    """The one assumption collision placement rests on is checked, not assumed."""
    broken = json.loads(json.dumps(document))
    broken["completion"]["timeline"][0]["sim_rate"] = 0.5
    with pytest.raises(tile_score.ScoreError, match="identity map"):
        tile_score.schedule(broken)


def test_a_document_missing_a_climax_state_is_refused(document):
    broken = json.loads(json.dumps(document))
    broken["completion"]["timeline"] = [
        segment for segment in broken["completion"]["timeline"]
        if segment["state"] != "unlocking"]
    with pytest.raises(tile_score.ScoreError, match="unlocking"):
        tile_score.schedule(broken)


# ==========================================================================
# 4. The hierarchy, at three levels
# ==========================================================================


def test_the_configured_gains_are_ordered():
    for config in tile_score.CONFIGS.values():
        assert config.duplicate_gain < config.activation_gain < config.final_gain
        assert config.confirm_gain < config.activation_gain


def test_an_inverted_hierarchy_is_refused_at_construction():
    with pytest.raises(tile_score.ScoreError, match="inverted"):
        dataclasses.replace(tile_score.DEFAULT_CONFIG, duplicate_gain=0.9)
    with pytest.raises(tile_score.ScoreError, match="inverted"):
        dataclasses.replace(tile_score.DEFAULT_CONFIG, final_gain=0.1)


def test_a_duplicate_is_always_quieter_than_every_activation(plan):
    loudest_duplicate = max(event.gain for event in plan.of_kind("duplicate"))
    quietest_activation = min(event.gain for event in plan.of_kind("activation"))
    assert loudest_duplicate < quietest_activation
    assert plan.of_kind("final")[0].gain > max(
        event.gain for event in plan.of_kind("activation"))


def test_a_duplicate_and_an_activation_on_a_tile_share_its_fundamental(plan):
    """Same wall, same note. The physical connection the brief asks for."""
    by_tile: dict[int, set[float]] = {}
    for event in plan.events:
        if event.tile is None or event.kind == "unlock":
            continue
        by_tile.setdefault(event.tile, set()).add(event.freq)
    assert all(len(freqs) == 1 for freqs in by_tile.values())


def test_the_rendered_cues_are_ordered_in_peak_and_in_energy(report):
    """Not the configuration - the buffers that were actually placed."""
    cues = report["cues"]
    assert cues["duplicate"]["peak_dbfs"] < cues["activation"]["peak_dbfs"]
    assert cues["activation"]["peak_dbfs"] < cues["final"]["peak_dbfs"]
    assert cues["duplicate"]["energy_dbfs"] < cues["activation"]["energy_dbfs"]
    assert cues["activation"]["energy_dbfs"] < cues["final"]["energy_dbfs"]
    # And the detonation lasts longer than the thing it outranks.
    assert cues["final"]["seconds"] > cues["activation"]["seconds"]
    assert cues["activation"]["seconds"] > cues["duplicate"]["seconds"]


def test_the_finished_master_keeps_the_hierarchy(report):
    gaps = report["hierarchy_gaps_db"]
    assert gaps["activation_over_duplicate_db"] >= 8.0
    assert gaps["final_over_activation_db"] >= 4.0
    assert gaps["activation_over_duplicate_rms_db"] >= 8.0
    assert gaps["final_over_activation_rms_db"] >= 2.0


def test_the_hierarchy_survives_a_phone_speaker(report):
    """The reading that failed first, and the reason three cues were rebuilt.

    Through `loudness.phone_filter` the first build measured the detonation
    **+3.0 dB peak and +0.4 dB RMS** over an ordinary activation. The
    thresholds here are below what it now reaches and above what it reached
    then, so a regression in any of the three fixes fails rather than being
    noticed on a phone.
    """
    gaps = report["hierarchy_gaps_db"]
    assert gaps["phone_activation_over_duplicate_db"] >= 8.0
    assert gaps["phone_final_over_activation_rms_db"] >= 2.5
    phone = report["phone"]["hierarchy_dbfs"]
    # The three climax beats all have to clear an ordinary activation on the
    # speaker most of the audience is using.
    for kind in ("final", "unlock", "escape"):
        assert phone[kind]["median_dbfs"] > phone["activation"]["median_dbfs"], kind


def test_every_cue_carries_energy_a_phone_can_reproduce(report):
    """The regression for the three cues whose energy sat under 500 Hz.

    The gate's rise measured 8.9% above 500 Hz when its glide had a struck
    envelope, and the release 5.7% when its pad stopped at the sixth partial.
    A duplicate is allowed to be the darkest thing in the piece - that is its
    job - but it still has to have a tick on it.
    """
    shares = {kind: values["above_500hz_pct"]
              for kind, values in report["cues"].items()}
    assert shares["final"] >= 20.0
    assert shares["unlock"] >= 20.0
    assert shares["escape"] >= 12.0
    assert shares["activation"] >= 15.0
    assert shares["duplicate"] >= 2.0


def test_a_rising_cue_is_measured_where_it_rises_to(rendered):
    """The instrument bug, kept fixed.

    The unlock swells and peaks 327 ms into its buffer. Measured in a 55 ms
    window from where it was *placed*, it read 22 dB down - the level of the
    silence at the start of a rise. The window now starts at the cue's own
    peak, so the two readings differ by a lot and the larger one is the one
    reported.
    """
    config = rendered.schedule.config
    event = rendered.schedule.of_kind("unlock")[0]
    cue = tile_audio.cue_for(event, config)
    head = max(range(len(cue)), key=lambda index: abs(cue[index]))
    assert head / config.sample_rate > 0.10, "the unlock is supposed to swell"

    window = int(round(0.055 * config.sample_rate))
    start = int(round(event.at_seconds * config.sample_rate))
    at_placement = tile_audio._window_peak(
        rendered.left, rendered.right, start, start + window)
    at_peak = tile_audio._window_peak(
        rendered.left, rendered.right, start + head, start + head + window)
    assert at_peak > at_placement * 3.0


def test_an_in_phase_chord_is_diluted_by_its_own_normalisation():
    """The defect that drove the detonation's re-voicing, kept measurable.

    Peak-normalising a stack whose partials all start at phase zero divides
    every one of them by very nearly the *sum* of their gains. The eleven
    voices of the final chord are divided by about four, and that is why the
    first build of it measured +0.4 dB RMS over an ordinary activation through
    `loudness.phone_filter` while its configured gain said +8.
    """
    config = tile_score.DEFAULT_CONFIG
    parts = tuple((220.0 * (index + 1), 0.6, 0.4) for index in range(8))
    length = int(0.4 * config.sample_rate)
    stack = tile_audio._partials(length, parts, attack=0.002,
                                 sample_rate=config.sample_rate)
    alone = tile_audio._partials(length, parts[:1], attack=0.002,
                                 sample_rate=config.sample_rate)
    assert peak(stack) > peak(alone) * 4.0, (
        "if this stops being true the dilution is gone and the detonation's "
        "voicing can be reconsidered")


def test_voices_at_one_frequency_reinforce_rather_than_cancel():
    """The regression for the cancellation that killed phase dispersion.

    The detonation's chord contains the root's fourth octave *and* the tile's
    own voicing, and for a final tile at the top of the arena both are 880 Hz.
    Spreading their phases made them cancel - the 880 Hz voice measured 18.3 dB
    down on exactly the seeds whose last tile is high in the ring - which is
    one of the two reasons dispersion was removed rather than repaired. They
    are the same note; they have to add.
    """
    import numpy as np

    config = tile_score.DEFAULT_CONFIG
    length = int(0.4 * config.sample_rate)
    one = tile_audio._partials(length, ((880.0, 0.5, 0.3),), attack=0.002,
                               sample_rate=config.sample_rate)
    two = tile_audio._partials(length, ((880.0, 0.5, 0.3), (880.0, 0.5, 0.3)),
                               attack=0.002, sample_rate=config.sample_rate)

    def level(buffer) -> float:
        column = np.asarray(buffer)
        magnitude = np.abs(np.fft.rfft(column))
        freqs = np.fft.rfftfreq(column.size, 1.0 / config.sample_rate)
        return float(magnitude[(freqs > 872.0) & (freqs < 888.0)].max())

    assert level(two) == pytest.approx(2.0 * level(one), rel=1e-6)


def test_no_phase_dispersion_survives_in_the_synthesiser():
    """It was tried, measured at between +2.6 and -1.5 dB across the eleven
    pitches - a coin flip - and removed. This stops it coming back quietly."""
    with open(AUDIO_PY, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "phase=" not in source


def test_the_detonation_states_the_key_whatever_tile_is_last():
    """The root and its octaves are in the chord for every possible final tile.

    Checked by rendering the cue for each of the eleven pitches and looking
    for the root's second octave in the spectrum, because "the ending resolves
    the same way on every seed" is the property that makes the unlock and the
    escape mean anything.
    """
    import numpy as np

    config = tile_score.DEFAULT_CONFIG
    for freq in tile_score.pitch_table(config):
        cue = np.asarray(tile_audio._final_cue(freq, config))
        spectrum = np.abs(np.fft.rfft(cue))
        freqs = np.fft.rfftfreq(cue.size, 1.0 / config.sample_rate)
        target = config.root_hz * 4.0
        band = spectrum[(freqs > target - 12.0) & (freqs < target + 12.0)]
        assert band.max() > 0.02 * spectrum.max(), freq


# ==========================================================================
# 5. Progression
# ==========================================================================


def test_progression_is_driven_by_the_documents_own_ledger(plan):
    activations = plan.of_kind("activation")
    counts = [event.progress for event in activations]
    assert counts == sorted(counts)
    assert counts[0] == pytest.approx(1 / 51)
    assert plan.of_kind("final")[0].progress == pytest.approx(1.0)


def test_a_late_activation_is_brighter_than_an_early_one():
    """Measured as spectral centroid, and monotone across the run.

    Two things had to be fixed before this was true, and both made a *late*
    activation darker while every gain in the progression moved the right way:

    * the decay growth was applied to the fundamental as well as to the upper
      partials, and the fundamental carries most of the energy, so ringing it
      for longer simply added bass;
    * the bright tick was layered on before the cue was normalised, so as the
      progression added partials underneath it its share of the finished cue
      shrank - the highest-frequency thing in the sound getting quieter
      exactly when the sound was supposed to be opening up.
    """
    import numpy as np

    config = tile_score.DEFAULT_CONFIG
    freq = tile_score.pitch_table(config)[5]

    def centroid(progress: float) -> float:
        event = tile_score.AudioEvent(
            kind="activation", render_seconds=0.0, frame=0, at_seconds=0.0,
            gain=1.0, pan=0.0, tile=0, freq=freq, progress=progress)
        cue = np.asarray(tile_audio.cue_for(event, config))
        magnitude = np.abs(np.fft.rfft(cue))
        freqs = np.fft.rfftfreq(cue.size, 1.0 / config.sample_rate)
        return float((freqs * magnitude).sum() / magnitude.sum())

    series = [centroid(unit / 10.0) for unit in range(11)]
    assert series == sorted(series), series
    assert series[-1] > series[0] * 1.05


def test_a_late_activation_is_fuller_than_an_early_one():
    """And louder, by a decibel and a half of gain and half a decibel of
    energy once the normalisation has taken its share back."""
    import numpy as np

    config = tile_score.DEFAULT_CONFIG
    freq = tile_score.pitch_table(config)[5]

    def energy(progress: float) -> float:
        gain = config.activation_gain + config.gain_growth * progress
        event = tile_score.AudioEvent(
            kind="activation", render_seconds=0.0, frame=0, at_seconds=0.0,
            gain=gain, pan=0.0, tile=0, freq=freq, progress=progress)
        cue = np.asarray(tile_audio.cue_for(event, config)) * gain
        return 10.0 * math.log10(float((cue * cue).sum()))

    assert energy(1.0) > energy(0.0)
    # Subtle, as the brief asks: a couple of decibels end to end, not ten.
    assert energy(1.0) - energy(0.0) < 3.0


def test_the_late_harmonic_layer_arrives_only_near_completion():
    """A real second note - a fifth above the fundamental - and not before
    four fifths of the arena is lit."""
    import numpy as np

    config = tile_score.DEFAULT_CONFIG
    freq = tile_score.pitch_table(config)[5]

    def fifth_level(progress: float) -> float:
        event = tile_score.AudioEvent(
            kind="activation", render_seconds=0.0, frame=0, at_seconds=0.0,
            gain=1.0, pan=0.0, tile=0, freq=freq, progress=progress)
        cue = np.asarray(tile_audio.cue_for(event, config))
        magnitude = np.abs(np.fft.rfft(cue))
        freqs = np.fft.rfftfreq(cue.size, 1.0 / config.sample_rate)
        target = freq * 1.5
        band = magnitude[(freqs > target - 8.0) & (freqs < target + 8.0)]
        return float(band.max())

    below = fifth_level(config.late_fifth_from - 0.01)
    assert fifth_level(1.00) > below * 4.0
    assert fifth_level(0.50) == pytest.approx(below, rel=0.5)


def test_progression_off_makes_every_activation_the_same_cue(document):
    control = tile_score.CONFIGS["v1_basic"]
    built = tile_score.schedule(document, control)
    gains = {event.gain for event in built.of_kind("activation")}
    assert gains == {control.activation_gain}
    keys = {tile_audio._cache_key(event, control)
            for event in built.of_kind("activation")}
    # One cue per pitch, not one per activation.
    assert len(keys) <= control.pitches


def test_progression_never_lifts_an_activation_to_the_final(plan):
    config = plan.config
    assert config.activation_gain + config.gain_growth < config.final_gain


# ==========================================================================
# 6. Density
# ==========================================================================


def test_the_restrike_damper_works_when_a_restrike_happens(document):
    """Tested on a document built to contain one, because no real seed does.

    A bar already ringing does not add a whole new event's worth of energy, so
    a tile struck again inside 320 ms is damped towards a floor. The mechanism
    is real and it is checked here on a synthetic contact; whether it ever
    fires on this arena is the next test, and the answer is no.
    """
    doctored = json.loads(json.dumps(document))
    hits = doctored["collisions"]
    index = next(i for i, hit in enumerate(hits)
                 if i > 2 and not hit["new"] and not hits[i - 1]["new"])
    hits[index]["tile"] = hits[index - 1]["tile"]
    hits[index]["side"] = hits[index - 1]["side"]
    hits[index]["slot"] = hits[index - 1]["slot"]
    hits[index]["t"] = hits[index - 1]["t"] + 0.05

    built = tile_score.schedule(doctored)
    damped = [event for event in built.of_kind("duplicate")
              if event.restrike_scale < 1.0]
    assert len(damped) == 1
    assert damped[0].since_tile_seconds == pytest.approx(0.05)
    config = built.config
    expected = config.restrike_floor + (1.0 - config.restrike_floor) * (
        0.05 / config.restrike_seconds)
    assert damped[0].restrike_scale == pytest.approx(expected)
    assert damped[0].gain < config.duplicate_gain


def test_the_restrike_damper_is_inert_on_this_arena(document, dense_document):
    """And the phase says so rather than presenting it as work being done.

    At gravity 0 on a seventeen-gon at 85 wu/s the ball does not come back to
    a tile it has just left: over the two seeds here the shortest interval
    between two contacts on one tile is 0.44 s, well outside the 0.32 s
    window. The damper is kept for the same reason Phase 4 kept its two
    almost-inert pacing guards - "no fast re-strikes" is a property of this
    configuration, and a change to the arena, the speed or gravity could
    produce one - and its threshold is pinned here against the measurement
    that makes it inert.
    """
    shortest = math.inf
    for source in (document, dense_document):
        built = tile_score.schedule(source)
        for event in built.of_kind("duplicate"):
            if event.since_tile_seconds is not None:
                shortest = min(shortest, event.since_tile_seconds)
            assert event.restrike_scale == 1.0
    assert shortest > tile_score.DEFAULT_CONFIG.restrike_seconds
    assert shortest == pytest.approx(0.44, abs=0.02)


def test_the_density_duck_does_fire(plan):
    """The damper that is not inert: duplicates arriving in a crowd are
    pulled down, and it happens on the reference seed."""
    ducked = [event for event in plan.of_kind("duplicate")
              if event.duck_scale < 1.0]
    assert ducked
    for event in ducked:
        assert event.duck_scale >= plan.config.duck_floor
        assert event.gain < plan.config.duplicate_gain


def test_only_duplicates_are_ducked(plan):
    """The progress signal is never pulled down by the noise around it."""
    for event in plan.events:
        if event.kind == "duplicate":
            assert event.duck_scale <= 1.0
        else:
            assert event.duck_scale == 1.0
            assert event.restrike_scale == 1.0


def test_polyphony_stays_bounded_on_the_densest_valid_seed(dense_document):
    """Six contacts a second, and the voice count still fits on one hand."""
    built = tile_score.schedule(dense_document)
    assert built.metrics["events_per_second"] > 5.8
    result = tile_audio.render(built)
    assert result.voices["max_voices"] <= 8
    assert peak(result.left) <= PEAK_CEILING
    assert peak(result.right) <= PEAK_CEILING


def test_the_schedule_reports_its_own_density(plan):
    metrics = plan.metrics
    assert metrics["events"] == len(plan.events)
    assert sum(metrics["by_kind"].values()) == len(plan.events)
    assert 4.0 < metrics["events_per_second"] < 7.0
    assert metrics["min_gap_seconds"] >= 0.0


# ==========================================================================
# 7. Levels: nothing clips, and there is headroom left
# ==========================================================================


def test_no_sample_clips_and_nothing_passes_the_ceiling(rendered, report):
    assert report["peak"]["clipped_samples"] == 0
    assert report["peak"]["samples_over_ceiling"] == 0
    assert peak(rendered.left) <= PEAK_CEILING
    assert peak(rendered.right) <= PEAK_CEILING
    assert report["peak"]["sample_peak_dbfs"] <= PEAK_CEILING_DBFS


def test_the_true_peak_leaves_room_for_the_encoder(report):
    """The delivery figure is -1.0 dBTP and the master reserves 0.3 dB of it."""
    assert report["peak"]["true_peak_dbtp"] <= -1.0


def test_the_limiter_does_not_act_on_the_shipped_configuration(rendered):
    """A safety net, not a stage.

    At the master gain measured first (1.20 dB) three of five rendered seeds
    asked the limiter for up to 0.37 dB. The gain is 0.80 dB so that none of
    them does, which is what makes "the hierarchy is exactly the configured
    gains" true rather than nearly true.
    """
    assert rendered.limited is False
    assert rendered.limiter_gain == 1.0


def test_the_master_is_a_static_gain_and_nothing_else(rendered):
    """No compressor anywhere in the chain, asserted on the source.

    A compressor would pull the detonation down toward the duplicates, which
    is the one thing the design cannot afford, so its absence is checked
    rather than remembered.
    """
    with open(AUDIO_PY, "r", encoding="utf-8") as handle:
        source = handle.read()
    code = strip_prose(source)
    assert "compress" not in code
    assert "COMPRESSOR" not in code
    # And the master is Category 3's own, not `audio/soundtrack.py`'s: that
    # module opens with `from audio import cues` and importing it for three
    # functions pulled the battle cue library into this import graph. Phase 1's
    # boundary guard caught it; see `tile_audio`'s master section.
    assert "audio.soundtrack" not in code
    assert "from audio import soundtrack" not in code
    assert rendered.master_gain == pytest.approx(
        10 ** (rendered.schedule.config.master_gain_db / 20.0))


def test_every_variant_of_every_rendered_seed_clears_the_ceiling(document,
                                                                 dense_document):
    for source in (document, dense_document):
        for config in tile_score.CONFIGS.values():
            result = tile_audio.render(tile_score.schedule(source, config))
            highest = max(peak(result.left), peak(result.right))
            assert highest <= PEAK_CEILING, (source["seed"], config.name)
            assert highest > 0.5, "a silent master is not a passing one"


def test_the_ending_decays_into_silence(rendered, report):
    """The reduction the brief is asking for, measured.

    The escape's pad is over before the video is, so the last stretch of the
    Short is quiet on purpose. A soundtrack that ran to the final frame would
    be cut off by it.
    """
    config = rendered.schedule.config
    tail_start = int(round((rendered.schedule.total_seconds - 0.20)
                           * config.sample_rate))
    tail = max(tile_audio._window_peak(rendered.left, rendered.right,
                                       tail_start, len(rendered.left)), 1e-12)
    assert gain_to_db(tail) < -45.0


def test_silence_is_short_everywhere_else(report):
    """No hole in the middle: the longest quiet stretch is the lead-in or the
    tail, never a gap in the run."""
    assert report["longest_silence_seconds"] < 1.0
    assert report["silent_fraction"] < 0.5


def test_the_mix_folds_down_without_a_hole(report):
    assert abs(report["mono"]["mono_loss_db"]) < 1.5
    assert report["mono"]["correlation"] > 0.7


# ==========================================================================
# 8. Length, and the video timeline
# ==========================================================================


def test_the_soundtrack_is_exactly_as_long_as_the_video(document, plan, rendered):
    """`tile_escape_render.gd` writes frames 0 .. round(duration * fps).

    So the video is that many plus one frames, and the soundtrack has to be
    that many frame-periods of samples. A soundtrack one frame short leaves
    the last frame silent; one frame long is trimmed by the muxer and nobody
    notices until the ending is cut off.
    """
    fps = plan.config.fps
    duration = document["completion"]["total_render_seconds"]
    assert plan.frames == int(round(duration * fps)) + 1
    assert plan.total_seconds == pytest.approx(plan.frames / fps)
    assert plan.total_samples == int(round(plan.total_seconds * plan.config.sample_rate))
    assert len(rendered.left) == plan.total_samples
    assert len(rendered.right) == plan.total_samples


def test_the_frame_count_matches_the_phase4_render_for_seed_3530(plan):
    """1,038 frames, which is what Phase 4 actually wrote to disk."""
    assert plan.frames == 1038
    assert plan.total_seconds == pytest.approx(34.6)


def test_no_cue_is_scheduled_past_the_end(plan):
    for event in plan.events:
        assert event.at_seconds < plan.total_seconds


def test_a_run_without_an_ending_is_as_long_as_the_run(run):
    bare = tile_playback.playback_document(run)
    built = tile_score.schedule(bare)
    assert built.frames == int(round(run.end_time * 30.0)) + 1


# ==========================================================================
# 9. Synchronisation
# ==========================================================================


def test_every_cue_is_on_its_frame_to_within_half_a_sample(plan, document):
    sync = tile_audio.sync_report(plan, document)
    assert sync["frame_mismatches"] == []
    assert sync["activation_frames_agree"] is True
    assert sync["max_placement_error_seconds"] <= 0.5 / plan.config.sample_rate
    assert sync["max_placement_error_frames"] < 0.001


def test_the_audio_never_leads_the_picture(plan):
    """The direction that matters. A cue is on its frame or it is nowhere."""
    for event in plan.events:
        assert event.at_seconds >= event.render_seconds


def test_the_climax_cues_are_reported_against_their_beats(plan, document):
    sync = tile_audio.sync_report(plan, document)
    for kind in ("final", "unlock", "escape"):
        beat = sync["beats"][f"cue_{kind}"]
        assert beat["frame"] == plan.of_kind(kind)[0].frame
        assert beat["at_seconds"] == pytest.approx(
            plan.of_kind(kind)[0].at_seconds)


def test_sync_holds_on_every_rendered_seed(dense_document):
    built = tile_score.schedule(dense_document)
    sync = tile_audio.sync_report(built, dense_document)
    assert sync["frame_mismatches"] == []
    assert sync["activation_frames_agree"] is True


# ==========================================================================
# 10. The audio cannot touch the run
# ==========================================================================


def test_scheduling_does_not_mutate_the_document(document):
    before = json.dumps(document, sort_keys=True)
    tile_score.schedule(document, tile_score.DEFAULT_CONFIG)
    tile_audio.render_document(document, tile_score.CONFIGS["v1_basic"])
    assert json.dumps(document, sort_keys=True) == before


def test_the_document_still_verifies_after_the_audio_has_read_it(document):
    tile_audio.render_document(document, tile_score.DEFAULT_CONFIG)
    check = tile_playback.verify_document(document)
    assert check["digest_matches"]
    assert check["activation_order_matches"]
    assert check["activation_times_match_exactly"]
    assert check["completion_matches"]


def test_the_run_is_identical_whether_or_not_audio_was_built():
    first = simulate(PRIMARY_SEED, PHASE5_CONFIG, PHASE2_ARENA)
    base = tile_playback.playback_document(first)
    whole = tile_completion.attach_completion(base, first, PHASE2_ARENA)
    tile_audio.render_document(whole, tile_score.DEFAULT_CONFIG)
    second = simulate(PRIMARY_SEED, PHASE5_CONFIG, PHASE2_ARENA)
    assert first.state_digest() == second.state_digest()
    assert json.dumps(tile_playback.playback_document(second), sort_keys=True) == (
        json.dumps(base, sort_keys=True))


def test_the_score_cannot_reach_a_simulator_and_the_synth_cannot_reach_a_seed():
    """An architectural claim, checked on the source.

    `tile_score` imports no synthesiser; `tile_audio` imports no simulator.
    Neither takes a seed. That is the mechanical reason the soundtrack cannot
    influence the physics, and it is worth more than any amount of care.
    """
    with open(SCORE_PY, "r", encoding="utf-8") as handle:
        score = handle.read()
    with open(AUDIO_PY, "r", encoding="utf-8") as handle:
        audio = handle.read()
    for banned in ("tile_escape", "tile_arena", "simulate", "audio.synthesis",
                   "audio.soundtrack"):
        assert f"import {banned}" not in score and f"from {banned}" not in score
    for banned in ("from satisfying.tile_escape", "from satisfying.tile_arena",
                   "simulate("):
        assert banned not in audio
    # `tile_audio` reaches `tile_playback` once, inside `sync_report`, and only
    # to re-derive the activation frames a third way. It never simulates.
    assert audio.count("from satisfying import tile_playback") == 1


# ==========================================================================
# 11. Export stability
# ==========================================================================


def test_the_waveform_is_deterministic(plan):
    """Two renders of one schedule, compared as PCM bytes."""
    assert tile_audio.render(plan).digest() == tile_audio.render(plan).digest()


def test_two_configurations_give_two_waveforms(document):
    digests = {tile_audio.render_document(document, config).digest()
               for config in tile_score.CONFIGS.values()}
    assert len(digests) == len(tile_score.CONFIGS)


def test_the_configuration_fingerprint_moves_with_any_dial():
    base = tile_score.DEFAULT_CONFIG
    assert base.fingerprint() == tile_score.DEFAULT_CONFIG.fingerprint()
    for field, value in (("root_hz", 261.63), ("fps", 60.0),
                         ("duplicate_gain", 0.05), ("confirmation", "breath"),
                         ("tilt_depth", 0.0), ("pan_depth", 0.1)):
        assert dataclasses.replace(base, **{field: value}).fingerprint() != (
            base.fingerprint()), field


def test_the_noise_in_a_cue_is_seeded_from_the_note_not_from_the_run():
    """Same tile, same tick, every time - and two tiles do not share one."""
    config = tile_score.DEFAULT_CONFIG
    table = tile_score.pitch_table(config)
    first = list(tile_audio._duplicate_cue(table[0], config))
    again = list(tile_audio._duplicate_cue(table[0], config))
    other = list(tile_audio._duplicate_cue(table[4], config))
    assert first == again
    assert first != other


def test_an_unknown_configuration_or_hold_is_refused():
    with pytest.raises(tile_score.ScoreError, match="unknown audio config"):
        tile_score.named_config("nope")
    with pytest.raises(tile_score.ScoreError, match="confirmation hold"):
        dataclasses.replace(tile_score.DEFAULT_CONFIG, confirmation="loud")


def test_a_non_playback_document_is_refused():
    with pytest.raises(tile_score.ScoreError, match="not a tile-escape"):
        tile_score.schedule({"kind": "something else"})
