"""Category 3 Test #2 redesign - multi-ball musical audio, Phase 2B.

What these tests are for, in order of how much they would hurt to lose:

1. **Phase 1 is untouched.** The simulation, the schema and the evaluator are
   frozen inputs. The version string, every field of every event kind and the
   locked config digest are asserted here as well as in the Phase 1 file,
   because this branch is the one that would be tempted to change them.
2. **Audio cannot reach physics.** `multishell_score` imports no simulator, no
   synthesiser and no numpy; `multishell_audio` receives an immutable schedule.
   A test walks the import graph rather than trusting the docstring, and
   another asserts the canonical document is byte-identical after a full
   render.
3. **The consonance guarantee is structural.** Every palette is asserted to
   contain no semitone and no tritone in any octave, and every shell window is
   asserted to be a position in that one collection rather than a
   transposition - which is the mistake that would silently add a sixth pitch
   class and break every simultaneity in the run.
4. **Nothing moves in time and nothing is dropped.** Every canonical collision
   gets exactly one voice at `round(t * 48000)`, and the density control is
   asserted to shorten and quieten rather than to silence.
5. **The hierarchy is the brief's.** A bounce is under a strong hit is under a
   spawn is under a break is under the escape, measured on the rendered
   contributions rather than asserted from the configuration.
6. **Family, not randomness.** A child's voice is asserted to be within one
   generation's step of its parent on every axis, and two siblings closer to
   each other than to the founder's grandchildren.
"""

from __future__ import annotations

import ast
import json
import math
import os
import pathlib
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np

from satisfying import multishell_audio as audio
from satisfying import multishell_audio_cli as cli
from satisfying import multishell_score as score
from satisfying import multishell_visual as visual
from satisfying.multishell import EVENT_SCHEMA, SCHEMA_VERSION, DEFAULT_CONFIG as SIM_CONFIG
from satisfying.multishell_playback import document_for

#: The densest run in the proof set, which is where anything that fails does.
REFERENCE_SEED = 17251
#: A mid-density run that ends on a break and on a third-generation descendant.
SECOND_SEED = 15793

_DOCUMENTS: dict[int, dict] = {}
_RENDERS: dict[tuple[int, str], audio.RenderedAudio] = {}


def document(seed: int = REFERENCE_SEED) -> dict:
    if seed not in _DOCUMENTS:
        _DOCUMENTS[seed] = document_for(seed)
    return _DOCUMENTS[seed]


def rendered(seed: int = REFERENCE_SEED, system: str | None = None) -> audio.RenderedAudio:
    name = system or score.SELECTED_SYSTEM
    key = (seed, name)
    if key not in _RENDERS:
        plan = score.schedule(document(seed), score.named_config(name))
        _RENDERS[key] = audio.render(plan)
    return _RENDERS[key]


# --------------------------------------------------------------------------
# Phase 1 is a frozen input
# --------------------------------------------------------------------------


def test_the_v2_schema_is_the_one_this_phase_was_written_against() -> None:
    assert SCHEMA_VERSION == "category3-test2-multiplying-shell/2.0.0"
    assert score.SCHEMA_VERSION == SCHEMA_VERSION
    assert SIM_CONFIG.digest() == score.CONFIG_DIGEST


def test_every_canonical_event_kind_still_carries_the_fields_audio_reads() -> None:
    """Field by field, for the eight kinds this layer actually consumes."""
    needed = {
        "collision": ("ball_id", "shell_id", "panel_id", "region", "position",
                      "impact_speed", "incidence", "feature"),
        "ball_spawn": ("ball_id", "parent_id", "generation", "birth_shell",
                       "region", "position", "lineage"),
        "near_miss": ("ball_id", "shell_id", "panel_id", "signed_lead"),
        "damage": ("ball_id", "shell_id", "panel_id", "contribution",
                   "cumulative", "threshold", "state"),
        "damage_state": ("ball_id", "shell_id", "panel_id", "previous_state",
                         "new_state"),
        "panel_break": ("ball_id", "shell_id", "panel_id", "position"),
        "shell_exit": ("ball_id", "shell_id", "panel_id", "route", "from_region",
                       "to_region", "position", "first_for_ball", "reproduced"),
        "escape": ("ball_id", "shell_id", "route", "position", "generation",
                   "parent_id", "lineage"),
    }
    for kind, fields in needed.items():
        present = EVENT_SCHEMA[kind]
        for field in fields:
            assert field in present, f"{kind} lost {field}"


def test_a_document_from_another_arena_is_refused_rather_than_scored() -> None:
    doc = dict(document())
    doc["config_digest"] = "0" * 64
    with pytest.raises(score.ScoreError):
        score.schedule(doc)
    doc = dict(document())
    doc["schema"] = "category3-test2-shell-escape/1.0.0"
    with pytest.raises(score.ScoreError):
        score.schedule(doc)


def test_rendering_does_not_mutate_the_canonical_document() -> None:
    """The whole file, before and after, as JSON."""
    doc = document_for(SECOND_SEED)
    before = json.dumps(doc, sort_keys=True)
    plan = score.schedule(doc)
    audio.measure(audio.render(plan))
    assert json.dumps(doc, sort_keys=True) == before


def test_the_simulation_is_not_reachable_from_a_schedule() -> None:
    """A schedule is data: it carries no callable that could step physics."""
    plan = score.schedule(document())
    payload = plan.as_dict()
    assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------
# Layer isolation
# --------------------------------------------------------------------------


def _imported_roots(module_name: str) -> set[str]:
    path = pathlib.Path(REPO_ROOT) / "satisfying" / f"{module_name}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add(node.module or "")
    return roots


def test_the_score_layer_imports_neither_physics_nor_synthesis() -> None:
    """The boundary that lets audio describe the run and never influence it."""
    roots = _imported_roots("multishell_score")
    assert roots <= {"__future__", "hashlib", "json", "math", "dataclasses", "typing"}


def test_the_synthesis_layer_reaches_only_the_three_leaf_audio_modules() -> None:
    roots = _imported_roots("multishell_audio")
    audio_roots = {name for name in roots if name.startswith("audio")}
    assert audio_roots <= {"audio", "audio.wav_io", "audio.loudness"}
    assert "satisfying.multishell" not in roots
    assert "satisfying.multishell_playback" not in roots


def test_the_audio_modules_never_import_test_one() -> None:
    tile = {p.stem for p in (pathlib.Path(REPO_ROOT) / "satisfying").glob("tile_*.py")}
    for module in ("multishell_score", "multishell_audio", "multishell_audio_cli"):
        path = pathlib.Path(REPO_ROOT) / "satisfying" / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("satisfying"):
                for alias in node.names:
                    assert alias.name not in tile, f"{module} imports {alias.name}"


# --------------------------------------------------------------------------
# The tonal system
# --------------------------------------------------------------------------


def test_no_palette_contains_a_semitone_or_a_tritone_in_any_octave() -> None:
    """The guarantee every simultaneity in the run rests on."""
    for system in score.SYSTEMS.values():
        assert system.harsh_intervals() == (), system.name
        for low in range(score.LADDER_TOP + 1):
            for high in range(low, score.LADDER_TOP + 1):
                gap = (system.ladder_semitones(high) - system.ladder_semitones(low)) % 12
                assert gap not in (1, 6, 11), (system.name, low, high)


def test_a_palette_with_a_semitone_is_refused_at_construction() -> None:
    with pytest.raises(score.ScoreError):
        score.TonalSystem(name="bad", scale=(0, 1, 4, 7, 9), shell_bases=(0, 2, 4, 6, 8))
    with pytest.raises(score.ScoreError):
        score.TonalSystem(name="tritone", scale=(0, 2, 6, 7, 9), shell_bases=(0, 2, 4, 6, 8))


def test_shell_windows_are_positions_in_the_ladder_not_transpositions() -> None:
    """The distinction the whole consonance argument turns on.

    A major pentatonic transposed up a fifth in *semitones* contains a pitch
    class the original does not, and two balls in adjacent shells would then be
    able to sound a minor second. Indexing into the ladder cannot do that: the
    union of every note any shell can play is the collection itself.
    """
    for system in score.SYSTEMS.values():
        playable = {system.ladder_semitones(index) % 12
                    for index in range(score.LADDER_TOP + 1)}
        assert playable == set(system.scale), system.name
        # And the naive alternative really would break it, on the major one.
        if system.name == "bright_pentatonic":
            transposed = {(degree + 7) % 12 for degree in system.scale}
            assert transposed - set(system.scale)


def test_outer_shells_sit_in_higher_registers() -> None:
    for system in score.SYSTEMS.values():
        bases = [system.frequency(base) for base in system.shell_bases]
        assert bases == sorted(bases)
        assert bases[-1] > bases[0] * 1.9, system.name
        top = system.frequency(score.LADDER_TOP)
        assert 220.0 <= bases[0] <= system.root_hz + 1e-9
        assert top < 4000.0


# --------------------------------------------------------------------------
# Pitch from position
# --------------------------------------------------------------------------


def test_contact_height_selects_a_degree_in_equal_width_bands() -> None:
    degrees = 5
    assert score.degree_for(-10.0, 10.0, degrees) == 0
    assert score.degree_for(10.0, 10.0, degrees) == degrees - 1
    assert score.degree_for(0.0, 10.0, degrees) == degrees // 2
    seen = [score.degree_for(y, 10.0, degrees) for y in np.linspace(-10.0, 10.0, 5001)]
    counts = [seen.count(index) for index in range(degrees)]
    assert max(counts) - min(counts) <= 2, counts
    ascending = [score.degree_for(y, 10.0, degrees) for y in (-9.0, -4.0, 0.0, 4.0, 9.0)]
    assert ascending == sorted(ascending)


def test_a_shell_maps_to_its_own_window_of_the_ladder() -> None:
    plan = score.schedule(document())
    system = plan.config.tonal
    by_shell: dict[int, list[int]] = {}
    for event in plan.of_kind("collision"):
        if event.repeat_nudged or event.cluster_nudged:
            continue
        by_shell.setdefault(event.shell_id, []).append(event.ladder_index)
    for shell_id, indices in sorted(by_shell.items()):
        base = system.shell_bases[shell_id]
        # A window plus the lineage's register preference and octave, clamped.
        assert min(indices) >= max(0, base - 2)
        assert max(indices) <= score.LADDER_TOP
    means = {shell: sum(v) / len(v) for shell, v in by_shell.items()}
    ordered = [means[shell] for shell in sorted(means)]
    assert ordered == sorted(ordered), ordered


# --------------------------------------------------------------------------
# Lineage
# --------------------------------------------------------------------------


def test_the_founder_is_the_neutral_centre_of_every_voice_axis() -> None:
    voices = score.voices_for(document()["balls"])
    founder = voices[0]
    assert founder.parent_id is None
    assert founder.tint == founder.edge == 0.5
    assert founder.pan_bias == 0.0 and founder.detune == 0.0
    assert founder.register == 0 and founder.octave_up is False


def test_a_child_is_one_step_from_its_parent_on_every_axis() -> None:
    config = score.DEFAULT_CONFIG
    voices = score.voices_for(document()["balls"], config)
    spread = config.lineage_spread
    children = 0
    for voice in voices.values():
        if voice.parent_id is None:
            continue
        children += 1
        parent = voices[voice.parent_id]
        assert abs(voice.tint - parent.tint) <= spread + 1e-9
        assert abs(voice.edge - parent.edge) <= spread + 1e-9
        assert abs(voice.pan_bias - parent.pan_bias) <= spread + 1e-9
        assert abs(voice.register - parent.register) <= 1
        assert abs(voice.detune - parent.detune) <= 0.5 + 1e-9
    assert children >= 10


def test_siblings_are_nearer_each_other_than_a_random_pair_would_be() -> None:
    """Family resemblance, measured rather than asserted."""
    voices = score.voices_for(document()["balls"])

    def distance(a: score.Voice, b: score.Voice) -> float:
        return math.dist((a.tint, a.edge, a.pan_bias), (b.tint, b.edge, b.pan_bias))

    siblings: list[float] = []
    strangers: list[float] = []
    ids = sorted(voices)
    for left in ids:
        for right in ids:
            if right <= left:
                continue
            a, b = voices[left], voices[right]
            if a.parent_id is not None and a.parent_id == b.parent_id:
                siblings.append(distance(a, b))
            elif a.generation >= 2 and b.generation >= 2 and a.lineage[1:2] != b.lineage[1:2]:
                strangers.append(distance(a, b))
    assert siblings and strangers
    assert sum(siblings) / len(siblings) < sum(strangers) / len(strangers)


def test_a_voice_depends_on_the_lineage_and_not_on_the_run() -> None:
    """The same parent and child id always give the same voice."""
    first = score.voices_for(document()["balls"])
    second = score.voices_for(list(reversed(document()["balls"])))
    assert {k: v.as_dict() for k, v in first.items()} == {k: v.as_dict() for k, v in second.items()}
    assert len({(v.tint, v.edge, v.pan_bias) for v in first.values()}) > 1


# --------------------------------------------------------------------------
# Timing and completeness
# --------------------------------------------------------------------------


def test_every_canonical_collision_gets_exactly_one_voice() -> None:
    doc = document()
    canonical = [event for event in doc["events"] if event["kind"] == "collision"]
    plan = score.schedule(doc)
    voiced = plan.of_kind("collision")
    assert len(voiced) == len(canonical)
    for source, event in zip(canonical, voiced):
        assert event.source_seconds == float(source["t"])
        assert event.ball_id == int(source["ball_id"])
        assert event.gain > 0.0 and event.seconds > 0.0


def test_no_cue_is_more_than_half_a_sample_from_its_canonical_instant() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        report = audio.sync_report(rendered(seed).schedule)
        assert report["within_half_sample"], report
        assert report["max_placement_error_samples"] <= 0.5 + 1e-9


def test_density_shortens_and_quietens_a_voice_and_never_silences_one() -> None:
    config = score.DEFAULT_CONFIG
    plan = score.schedule(document())
    collisions = plan.of_kind("collision")
    assert all(event.gain > 0.0 for event in collisions)
    floor = config.collision_seconds * config.density_floor * 0.5
    assert all(event.seconds >= floor for event in collisions)
    busy = [event for event in collisions if event.density >= 5]
    quiet = [event for event in collisions if event.density <= 2]
    assert busy and quiet
    assert (sum(e.seconds for e in busy) / len(busy)
            < sum(e.seconds for e in quiet) / len(quiet))


def test_no_event_is_quantised_to_a_grid() -> None:
    """There is no tempo here, and a test says so in the only way that can.

    If anything ever snapped a bounce to a beat, the gaps between contacts
    would cluster on multiples of one number. They do not: the distinct gaps
    are as numerous as the gaps.
    """
    plan = score.schedule(document())
    times = [event.source_seconds for event in plan.of_kind("collision")]
    gaps = [round(b - a, 6) for a, b in zip(times, times[1:])]
    assert len(set(gaps)) > 0.95 * len(gaps)


# --------------------------------------------------------------------------
# Simultaneity
# --------------------------------------------------------------------------


def test_simultaneous_events_never_form_a_semitone_or_a_tritone() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        for name in sorted(score.CONFIGS):
            plan = score.schedule(document(seed), score.named_config(name))
            consonance = plan.metrics["consonance"]
            assert consonance["simultaneous_pairs"] > 0
            assert consonance["harsh_pairs"] == 0, (seed, name)


def test_a_cluster_does_not_sound_the_same_note_twice() -> None:
    config = score.DEFAULT_CONFIG
    plan = score.schedule(document())
    pitched = [e for e in plan.events if e.kind in ("collision", "crossing")]
    collisions = 0
    for index, event in enumerate(pitched):
        for other in pitched[index + 1:]:
            if other.source_seconds - event.source_seconds > config.cluster_seconds:
                break
            if other.ladder_index == event.ladder_index:
                collisions += 1
    assert collisions == 0
    assert plan.metrics["cluster_nudged"] > 0


def test_a_ball_trapped_on_one_pitch_is_nudged_rather_than_repeated() -> None:
    plan = score.schedule(document())
    assert plan.metrics["repeat_nudged"] > 0
    assert plan.metrics["longest_same_pitch_run"] <= 4


# --------------------------------------------------------------------------
# Damage and breaks
# --------------------------------------------------------------------------


def test_the_panel_sounds_as_it_was_before_the_contact_not_after() -> None:
    """Resonance reports the panel that was struck, not the one left behind."""
    doc = document()
    damage = {(float(e["t"]), int(e["ball_id"])): e
              for e in doc["events"] if e["kind"] == "damage"}
    plan = score.schedule(doc)
    checked = 0
    for event in plan.of_kind("collision"):
        source = damage.get((event.source_seconds, event.ball_id))
        if source is None:
            continue
        checked += 1
        threshold = float(source["threshold"])
        before = (float(source["cumulative"]) - float(source["contribution"])) / threshold
        assert event.damage_before == pytest.approx(min(1.0, max(0.0, before)))
        assert event.damage_before < float(source["cumulative"]) / threshold + 1e-12
    assert checked > 50


def test_five_damage_states_are_five_distinct_colours() -> None:
    plan = score.schedule(document())
    steps = {event.state_step for event in plan.of_kind("collision") if event.state_step}
    assert steps == {1, 2, 3, 4}
    states = {event.damage_state for event in plan.of_kind("collision")}
    assert states <= set(score.DAMAGE_STATES)
    assert len(states) >= 4


def test_damage_lengthens_a_voice_rather_than_adding_a_crack() -> None:
    config = score.DEFAULT_CONFIG
    plan = score.schedule(document())
    collisions = plan.of_kind("collision")
    healthy = [e for e in collisions if e.damage_before < 0.05]
    worn = [e for e in collisions if e.damage_before > 0.55]
    assert healthy and worn
    # Compared at matched impact and shell so the reading is the damage alone.
    reference = score.AudioEvent(
        kind="collision", tier=1, source_seconds=0.0, sample_offset=0,
        seconds=config.collision_seconds, gain=0.1, pan=0.0,
        frequency_hz=440.0, ladder_index=5, ball_id=0, shell_id=2,
        impact=0.5, incidence=0.9, feature="face",
    )
    system = config.tonal
    clean = audio.cue_for(reference, config, system)
    from dataclasses import replace as _replace
    cracked = audio.cue_for(_replace(reference, damage_before=0.9), config, system)
    assert clean.size == cracked.size
    energy_clean = float(np.sum(clean * clean))
    energy_cracked = float(np.sum(cracked * cracked))
    assert energy_cracked > energy_clean
    assert float(np.max(np.abs(cracked))) == pytest.approx(1.0)


def test_a_break_is_a_palette_chord_above_every_bounce() -> None:
    plan = score.schedule(document())
    system = plan.config.tonal
    breaks = plan.of_kind("break")
    assert breaks
    for event in breaks:
        assert len(event.chord) == 4
        assert all(0 <= index <= score.LADDER_TOP for index in event.chord)
        for index in event.chord:
            assert system.ladder_semitones(index) % 12 in set(system.scale)
    loudest_bounce = max(event.gain for event in plan.of_kind("collision"))
    assert min(event.gain for event in breaks) > loudest_bounce


def test_every_canonical_break_blooms_exactly_once() -> None:
    doc = document()
    canonical = sum(1 for event in doc["events"] if event["kind"] == "panel_break")
    plan = score.schedule(doc)
    assert len(plan.of_kind("break")) == canonical


# --------------------------------------------------------------------------
# Spawns and progression
# --------------------------------------------------------------------------


def test_every_spawn_becomes_one_branching_gesture() -> None:
    doc = document()
    canonical = [e for e in doc["events"] if e["kind"] == "ball_spawn"]
    plan = score.schedule(doc)
    spawns = plan.of_kind("spawn")
    assert len(spawns) == len(canonical)
    for source, event in zip(canonical, spawns):
        assert event.source_seconds == float(source["t"])
        assert event.ball_id == int(source["ball_id"])
        assert event.secondary_hz > 0.0
        assert event.secondary_index != event.ladder_index


def test_a_spawn_answers_its_parent_with_a_consonant_interval() -> None:
    plan = score.schedule(document())
    system = plan.config.tonal
    for event in plan.of_kind("spawn"):
        gap = abs(system.ladder_semitones(event.secondary_index)
                  - system.ladder_semitones(event.ladder_index)) % 12
        assert gap not in (1, 6, 11)
        assert event.secondary_index != event.ladder_index


def test_the_two_halves_of_a_spawn_open_in_opposite_directions() -> None:
    plan = score.schedule(document())
    opposed = [event for event in plan.of_kind("spawn")
               if event.pan * event.secondary_pan <= 0.0]
    assert len(opposed) == len(plan.of_kind("spawn"))


def test_a_progression_lift_fires_only_on_the_runs_first_arrival() -> None:
    doc = document()
    plan = score.schedule(doc)
    lifts = plan.of_kind("lift")
    regions = [event.region for event in lifts]
    assert regions == sorted(set(regions))
    assert len(regions) == len(set(regions))
    frontier = 0
    expected = 0
    for source in doc["events"]:
        if source["kind"] == "shell_exit" and int(source["to_region"]) > frontier:
            frontier = int(source["to_region"])
            expected += 1
    assert len(lifts) == expected


def test_a_lift_and_the_spawn_it_lands_on_do_not_sum_past_the_break_tier() -> None:
    """The structural fact this phase found, pinned so it cannot regress.

    A ball's first crossing of a shell is both what makes it reproduce and,
    when nobody has been out there before, the run's arrival in a new region -
    so every lift shares its sample with a spawn. The spawn steps back under
    the lift rather than the pair summing into the loudest thing before the
    escape.
    """
    plan = score.schedule(document())
    config = plan.config
    lifts = {event.sample_offset for event in plan.of_kind("lift")}
    carried = [event for event in plan.of_kind("spawn") if event.with_lift]
    assert carried
    assert all(event.sample_offset in lifts for event in carried)
    assert all(event.gain == pytest.approx(config.spawn_gain * config.spawn_with_lift_gain)
               for event in carried)
    plain = [event for event in plan.of_kind("spawn") if not event.with_lift]
    assert plain and plain[0].gain > carried[0].gain


def test_a_repeat_crossing_stays_under_the_collision_bed() -> None:
    plan = score.schedule(document())
    crossings = plan.of_kind("crossing")
    assert crossings
    quietest_bounce = min(event.gain for event in plan.of_kind("collision"))
    assert max(event.gain for event in crossings) < quietest_bounce


# --------------------------------------------------------------------------
# The escape
# --------------------------------------------------------------------------


def test_the_run_resolves_once_on_the_collections_tonic() -> None:
    plan = score.schedule(document())
    escapes = plan.of_kind("escape")
    assert len(escapes) == 1
    event = escapes[0]
    system = plan.config.tonal
    assert event.tier == max(score.EVENT_TIER.values())
    assert event.ladder_index == 0
    assert system.ladder_semitones(event.chord[1]) == 0
    for index in event.chord:
        assert system.ladder_semitones(index) % 12 in set(system.scale)
    assert event.chord[0] < 0, "the resolution needs its octave below"


def test_a_run_without_an_escape_is_refused() -> None:
    doc = dict(document())
    doc["events"] = [event for event in doc["events"] if event["kind"] != "escape"]
    with pytest.raises(score.ScoreError):
        score.schedule(doc)


def test_the_escape_is_the_loudest_thing_in_the_piece() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        render = rendered(seed)
        peaks = audio._event_peaks(render)
        best = max(peaks.items(), key=lambda row: row[1]["max_peak_dbfs"])
        assert best[0] == "escape", (seed, best)
        overall = float(np.max(np.abs(render.samples)))
        start = render.schedule.events[-1].sample_offset
        after = float(np.max(np.abs(render.samples[start:])))
        assert after == pytest.approx(overall)


def test_the_bed_is_cleared_for_the_resolution() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        report = audio._duck_report(rendered(seed))
        assert report["escape_space_db"] <= -10.0, (seed, report)


# --------------------------------------------------------------------------
# The hierarchy
# --------------------------------------------------------------------------


def test_the_rendered_mix_puts_the_events_in_the_briefs_order() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        for name in sorted(score.CONFIGS):
            render = rendered(seed, name)
            verdict = cli.hierarchy_ok({"event_hierarchy": audio._event_peaks(render)})
            assert verdict["ok"], (seed, name, verdict)
            assert verdict["chain"] == list(cli.HIERARCHY_ORDER)


def test_a_strong_hit_is_louder_than_an_ordinary_one() -> None:
    plan = score.schedule(document())
    strong = [event for event in plan.of_kind("collision") if event.strong]
    plain = [event for event in plan.of_kind("collision") if not event.strong]
    assert strong and plain
    assert (sum(e.gain for e in strong) / len(strong)
            > sum(e.gain for e in plain) / len(plain))


# --------------------------------------------------------------------------
# Ducking
# --------------------------------------------------------------------------


def test_the_duck_touches_the_bed_and_never_the_marked_bus() -> None:
    render = rendered()
    plan = render.schedule
    marked = np.zeros_like(render.marked)
    for event in plan.events:
        if event.tier < audio.MARKED_TIER:
            continue
        cue = audio.cue_for(event, plan.config, plan.config.tonal)
        start = event.sample_offset
        stop = min(marked.shape[0], start + cue.shape[0])
        if cue.ndim == 2:
            marked[start:stop] += cue[:stop - start] * event.gain
        else:
            left, right = audio.pan_gains(event.pan)
            slice_ = cue[:stop - start] * event.gain
            marked[start:stop, 0] += slice_ * left
            marked[start:stop, 1] += slice_ * right
    assert np.allclose(render.marked, marked * render.static_gain, atol=1e-12)


def test_the_duck_never_exceeds_its_floor_and_never_pumps() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        render = rendered(seed)
        floor = 10.0 ** (-render.schedule.config.duck_floor_db / 20.0)
        assert float(render.duck.min()) >= floor - 1e-12
        assert float(render.duck.max()) <= 1.0 + 1e-12
        report = audio._duck_report(render)
        assert report["duck_onsets_per_second"] < 2.0, report
        assert report["fraction_below_minus_1db"] < 0.5, report


def test_the_duck_looks_no_further_forward_than_its_declared_lead() -> None:
    """The only forward-looking thing in the layer, bounded by a test."""
    plan = score.schedule(document())
    config = plan.config
    rate = config.sample_rate
    envelope = audio.duck_envelope(plan)
    first_marked = min(event.sample_offset for event in plan.events
                       if event.tier >= audio.MARKED_TIER)
    lead = int(round(config.duck_lead_seconds * rate))
    assert np.all(envelope[:max(0, first_marked - lead)] >= 1.0 - 1e-12)


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def test_nothing_clips_and_the_ceiling_is_respected() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        for name in sorted(score.CONFIGS):
            render = rendered(seed, name)
            peak = float(np.max(np.abs(render.samples)))
            ceiling = 10.0 ** (render.schedule.config.peak_ceiling_dbfs / 20.0)
            assert peak <= ceiling + 1e-9, (seed, name, peak)
            assert int(np.count_nonzero(np.abs(render.samples) >= 1.0)) == 0


def test_every_preview_ends_in_exact_digital_silence() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        render = rendered(seed)
        tail = int(round(render.schedule.config.end_silence_seconds * render.sample_rate))
        assert float(np.max(np.abs(render.samples[-tail:]))) == 0.0


def test_the_mix_folds_to_mono_without_a_hole() -> None:
    from audio import loudness

    render = rendered()
    report = loudness.mono_compatibility(render.samples, render.sample_rate)
    assert abs(report["mono_loss_db"]) < 1.0, report
    assert report["correlation"] > 0.90, report
    assert all(abs(shift) < 2.0 for shift in report["band_shift"].values()), report


def test_the_music_survives_a_phone_speaker() -> None:
    from audio import loudness

    render = rendered()
    phone = loudness.phone_filter(render.samples, render.sample_rate)
    profile = loudness.band_profile(np.repeat(phone, 2, axis=1), render.sample_rate)
    midrange = profile["300-800"] + profile["800-2000"]
    assert midrange > 90.0, profile
    phone_rms = float(np.sqrt(np.mean(phone * phone)))
    master_rms = float(np.sqrt(np.mean(render.samples * render.samples)))
    assert 20.0 * math.log10(phone_rms / master_rms) > -10.0


def test_a_contact_always_lifts_the_mix() -> None:
    """No bounce is buried: the one failure a musical bed can hide."""
    for seed in (REFERENCE_SEED, SECOND_SEED):
        report = audio.masking_report(rendered(seed))
        assert report["below_6db_fraction"] <= 0.02, report
        assert report["median_onset_rise_db"] > 6.0, report


# --------------------------------------------------------------------------
# Escalation
# --------------------------------------------------------------------------


def test_late_audio_is_richer_than_early_audio_and_is_not_noise() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        verdict = audio.richness_report(rendered(seed))["verdict"]
        assert verdict["richer_late"], (seed, verdict)
        assert verdict["not_noise"], (seed, verdict)
        assert verdict["late_polyphony_over_early"] > 0.0
        assert verdict["late_balls_over_early"] > 0
        assert verdict["tonal_percent_late"] > 80.0


def test_loudness_rises_but_does_not_run_away() -> None:
    for seed in (REFERENCE_SEED, SECOND_SEED):
        verdict = audio.richness_report(rendered(seed))["verdict"]
        assert 0.0 < verdict["late_lufs_over_early"] < 6.0, (seed, verdict)


def test_the_register_climbs_as_the_run_moves_outward() -> None:
    plan = score.schedule(document())
    thirds = plan.metrics["progression"]["thirds"]
    means = [row["mean_ladder_index"] for row in thirds]
    assert means[-1] > means[0] and means[-1] > means[1], means
    assert thirds[2]["distinct_balls"] > thirds[0]["distinct_balls"]


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_seed_and_system_give_the_same_score_and_the_same_samples() -> None:
    for name in sorted(score.CONFIGS):
        config = score.named_config(name)
        first = score.schedule(document_for(SECOND_SEED), config)
        second = score.schedule(document_for(SECOND_SEED), config)
        assert first.fingerprint() == second.fingerprint()
        assert audio.render(first).digest() == audio.render(second).digest()


def test_three_systems_produce_three_different_pieces() -> None:
    digests = set()
    for name in sorted(score.CONFIGS):
        plan = score.schedule(document(), score.named_config(name))
        digests.add(audio.render(plan).digest())
    assert len(digests) == len(score.CONFIGS)


def test_a_score_survives_a_json_round_trip() -> None:
    plan = score.schedule(document())
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "score.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(plan.as_dict(), handle)
        with open(path, encoding="utf-8") as handle:
            restored = json.load(handle)
    assert restored == plan.as_dict()
    assert restored["playback_digest"] == document()["digest"]


def test_the_written_master_is_the_rendered_master() -> None:
    from audio.wav_io import read_wav

    render = rendered(SECOND_SEED)
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "master.wav")
        audio.write_master(render, path)
        info, data = read_wav(path)
    assert info.sample_rate == 48_000 and info.channels == 2
    assert info.sample_count == render.samples.shape[0]
    assert data == render.pcm()


# --------------------------------------------------------------------------
# The proof set
# --------------------------------------------------------------------------


def test_the_proof_candidates_come_from_phase_one_and_obey_the_rules() -> None:
    with open(os.path.join(REPO_ROOT, cli.PHASE1_SHORTLIST), encoding="utf-8") as handle:
        shortlist = json.load(handle)
    manifest = cli.derive_candidates(shortlist)
    assert manifest["config_digest"] == score.CONFIG_DIGEST
    assert 6 <= len(manifest["seeds"]) <= 8
    assert set(manifest["seeds"]) <= set(shortlist["seeds"])
    coverage = manifest["coverage"]
    assert coverage["mixed_routes"] and coverage["founder_and_descendant"]
    assert coverage["population_range"][0] >= 8 and coverage["population_range"][1] <= 15
    assert 20.0 <= coverage["duration_range"][0] <= coverage["duration_range"][1] <= 26.0
    for row in manifest["candidates"]:
        assert float(row["first_spawn"]) <= 3.0
        assert row["rejected_for"] == []


def test_the_recorded_manifest_is_the_one_the_rules_produce_now() -> None:
    path = os.path.join(
        REPO_ROOT, "docs", "validation", "category3_multiplying_shell_adjust_v3b",
        "phase3b_candidates.json",
    )
    with open(path, encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["seeds"] == list(visual.CANDIDATE_SEEDS)
    assert stored["config_digest"] == score.CONFIG_DIGEST


def test_the_committed_measurements_match_a_fresh_render() -> None:
    """One seed, end to end, against the committed phone/A/V measurement."""
    path = os.path.join(
        REPO_ROOT, "docs", "validation", "category3_multiplying_shell_adjust_v3b",
        "phone_validation.json",
    )
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    stored = next(row for row in payload["rows"] if row["seed"] == REFERENCE_SEED)
    render = rendered()
    measured = audio.measure(render)
    assert stored["integrated_lufs"] == pytest.approx(measured["loudness"]["integrated_lufs"])
    assert stored["true_peak_dbtp"] == pytest.approx(measured["loudness"]["true_peak_dbtp"])
    assert stored["clipped_samples"] == measured["peak"]["clipped_samples"] == 0
    assert stored["mono_loss_db"] == pytest.approx(measured["mono"]["mono_loss_db"])
    assert stored["phone_band_energy_percent"] == pytest.approx(
        measured["phone"]["band_energy_percent"]
    )
