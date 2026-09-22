"""Focused contracts for Category 3 Test #2's musical collision system."""

from __future__ import annotations

import copy
import dataclasses
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

from audio import loudness
from satisfying import shell_audio, shell_score
from satisfying.shell_escape import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
PLAYBACK = ROOT / "docs" / "validation" / "category3_shell_escape" / "phase1_playback_seed11929.json"


@pytest.fixture(scope="module")
def document():
    with PLAYBACK.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def plan(document):
    return shell_score.schedule(document)


@pytest.fixture(scope="module")
def rendered(plan):
    return shell_audio.render(plan)


def test_the_frozen_schema_and_config_are_the_only_accepted_input(document):
    assert SCHEMA_VERSION == shell_score.SCHEMA_VERSION == "category3-test2-shell-escape/1.0.0"
    assert document["config_digest"].startswith("7da0cbc80d595826")
    for key, bad in (("schema_version", "changed"),
                     ("document_version", "changed"),
                     ("config_digest", "changed")):
        altered = copy.deepcopy(document)
        altered[key] = bad
        with pytest.raises(shell_score.ScoreError):
            shell_score.schedule(altered)


def test_audio_layers_do_not_import_the_simulator_or_test_one():
    for module in (shell_score, shell_audio):
        source = inspect.getsource(module)
        assert "shell_escape import" not in source
        assert "tile_score" not in source
        assert "tile_audio" not in source
        assert "Godot" not in source


def test_scoring_is_deterministic(plan, document):
    again = shell_score.schedule(document)
    assert plan.as_dict() == again.as_dict()
    assert plan.fingerprint() == again.fingerprint()


def test_synthesis_is_deterministic(rendered, plan):
    again = shell_audio.render(plan)
    assert rendered.digest() == again.digest()
    assert np.array_equal(rendered.samples, again.samples)


def test_shells_form_six_related_but_separated_registers():
    roots = [shell_score.frequency_for(shell, 0) for shell in range(6)]
    assert roots == sorted(roots)
    assert len(set(round(value, 6) for value in roots)) == 6
    assert roots[-1] / roots[0] > 2.9
    for shell in range(6):
        notes = [shell_score.frequency_for(shell, degree) for degree in range(5)]
        assert notes == sorted(notes)
        semitones = [round(12.0 * math.log2(note / notes[0])) for note in notes]
        assert semitones == list(shell_score.PENTATONIC)


def test_collision_position_selects_pitch_inside_the_shell():
    radius = 10.0
    assert shell_score.pitch_degree_for((0.0, -radius), radius) == 0
    assert shell_score.pitch_degree_for((0.0, 0.0), radius) == 2
    assert shell_score.pitch_degree_for((0.0, radius), radius) == 4


def test_impact_and_incidence_create_real_dynamics(document):
    plan = shell_score.schedule(document)
    collisions = plan.of_kind("collision")
    weakest = min(collisions, key=lambda event: event.impact + event.incidence)
    strongest = max(collisions, key=lambda event: event.impact + event.incidence)
    assert strongest.gain > weakest.gain * 1.25
    assert strongest.gain <= plan.config.collision_gain_high + 1e-12
    assert weakest.gain >= plan.config.collision_gain_low * 0.75


def test_near_miss_uses_signed_lead_as_a_restrained_ornament(plan):
    near = next(event for event in plan.of_kind("collision") if event.near_miss)
    assert any(event.feature == "post" for event in plan.of_kind("collision")
               if event.near_miss)
    assert near.near_miss_direction in (-1, 1)
    plain = dataclasses.replace(near, near_miss=False, near_miss_direction=0)
    decorated = shell_audio.cue_for(near, plan.config)
    control = shell_audio.cue_for(plain, plan.config)
    assert not np.array_equal(decorated, control)
    # The main note remains dominant; the ornament is tension, not a second hit.
    assert float(np.sqrt(np.mean((decorated - control) ** 2))) < 0.20


def test_damage_progression_changes_colour_without_fake_cracks(plan):
    event = plan.of_kind("collision")[0]
    healthy = shell_audio.cue_for(dataclasses.replace(event, damage=0.0), plan.config)
    weak = shell_audio.cue_for(dataclasses.replace(event, damage=1.0), plan.config)
    assert healthy.shape == weak.shape
    assert not np.array_equal(healthy, weak)
    assert np.max(np.abs(weak)) <= 1.0 + 1e-12


def test_panel_breaks_outrank_collisions_but_not_by_brute_force(plan):
    assert len(plan.of_kind("break")) == 14
    assert min(event.gain for event in plan.of_kind("break")) > max(
        event.gain for event in plan.of_kind("collision")
    )
    assert max(event.gain for event in plan.of_kind("break")) < plan.config.escape_gain


def test_only_genuine_new_outward_progress_creates_a_transition(plan):
    transitions = plan.of_kind("transition")
    assert len(transitions) == 6
    assert [event.progress for event in transitions] == pytest.approx(
        [1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1.0]
    )
    assert {event.method for event in transitions} == {"opening", "break"}


def test_final_escape_resolves_to_d_and_leaves_silence(plan, rendered):
    escape = plan.of_kind("escape")
    assert len(escape) == 1
    assert escape[0].frequency_hz == pytest.approx(587.3295358, rel=1e-7)
    assert escape[0].gain == plan.config.escape_gain
    silence = int(round(plan.config.end_silence_seconds * plan.config.sample_rate))
    assert np.max(np.abs(rendered.samples[-silence:])) == 0.0


def test_master_has_headroom_and_no_clipped_samples(rendered):
    peak = float(np.max(np.abs(rendered.samples)))
    assert peak < 1.0
    assert np.count_nonzero(np.abs(rendered.samples) >= 1.0) == 0
    assert rendered.static_gain <= rendered.schedule.config.master_gain


def test_mono_fold_keeps_the_musical_information(rendered):
    report = loudness.mono_compatibility(rendered.samples, rendered.sample_rate)
    assert report["mono_loss_db"] > -1.0
    assert report["correlation"] > 0.90
    assert max(abs(value) for value in report["band_shift"].values()) < 0.1


def test_audio_never_mutates_the_canonical_playback(document):
    before = json.dumps(document, sort_keys=True, separators=(",", ":"))
    plan = shell_score.schedule(document)
    shell_audio.render(plan)
    after = json.dumps(document, sort_keys=True, separators=(",", ":"))
    assert after == before


def test_every_audio_event_lands_within_half_a_sample(plan):
    report = shell_audio.sync_report(plan)
    assert report["within_half_sample"]
    assert report["max_placement_error_samples"] <= 0.5 + 1e-9
    assert len(plan.of_kind("collision")) == 76
    assert plan.metrics["near_miss_collisions"] == 12


def test_the_three_bounded_designs_are_distinct(document):
    fingerprints = set()
    pcm = set()
    for config in shell_score.CONFIGS.values():
        plan = shell_score.schedule(document, config)
        fingerprints.add(plan.fingerprint())
        pcm.add(shell_audio.render(plan).digest())
    assert len(fingerprints) == len(shell_score.CONFIGS) == 3
    assert len(pcm) == 3


def test_the_bounded_evidence_set_meets_delivery_safety_metrics():
    root = ROOT / "docs" / "validation" / "category3_shell_audio_v2b" / "measurements"
    paths = sorted(root.glob("*.measure.json"))
    assert len(paths) == 12
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            report = json.load(handle)
        assert report["peak"]["clipped_samples"] == 0, path.name
        assert report["peak"]["true_peak_dbtp"] <= -1.0, path.name
        assert report["peak"]["limiter_used"] is False, path.name
        assert report["mono"]["mono_loss_db"] > -1.0, path.name
        assert report["mono"]["correlation"] > 0.90, path.name
        assert report["synchronization"]["within_half_sample"], path.name
        assert report["ending_silence_peak"] == 0.0, path.name
        phone = report["phone"]["band_energy_percent"]
        assert phone["300-800"] + phone["800-2000"] > 90.0, path.name
