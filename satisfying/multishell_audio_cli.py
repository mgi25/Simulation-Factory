"""The Phase 2B audio workbench: candidates, variants, masters, measurements.

Four commands, in the order the phase runs them.

``candidates``
    Derive the proof set from Phase 1's eighteen shortlisted seeds by the
    brief's rules, and write the manifest that every later command reads. No
    new seed search is ever run here; `--source` points at the Phase 1
    shortlist that is already in the repository.

``variants``
    Score, render and measure at most three tonal systems on one or two
    reference seeds, and write the comparison the selection is argued from.

``build``
    Apply the selected system to the whole proof set: one verified playback
    document, one score, one WAV and one measurement per seed.

``verify``
    Re-derive everything from the seeds alone and check that the score
    fingerprints and PCM digests on disk are the ones the code produces now.

``timeline``
    A diagnostic picture of one render - envelope, duck, polyphony, event
    lanes and the pitch scatter - and, where FFmpeg is present, that picture
    muxed against the WAV so a reviewer can listen in a normal player. It is
    the cheap half of a mux: the expensive half needs the visual branch's
    frames, and this branch must not integrate visuals.

WAVs go to the repository's ignored `output/` workspace; scores, measurements
and comparisons are small enough to commit and go to `docs/validation/`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from satisfying import multishell_audio as audio
from satisfying import multishell_score as score
from satisfying.multishell_playback import (
    document_for,
    read_playback,
    verify_document,
    write_playback,
)

__all__ = [
    "CANDIDATE_RULES",
    "timeline_image",
    "PHASE1_SHORTLIST",
    "OUTPUT_ROOT",
    "VALIDATION_ROOT",
    "derive_candidates",
    "build_seed",
    "main",
]

PHASE1_SHORTLIST = os.path.join(
    "docs", "validation", "category3_multiplying_shell_adjust_v3b", "phase3b_shortlist.json"
)
OUTPUT_ROOT = os.path.join("output", "category3_multishell_adjust_v3b", "audio")
VALIDATION_ROOT = os.path.join(
    "docs", "validation", "category3_multiplying_shell_adjust_v3b", "audio"
)

#: The reference seeds the three-system comparison is decided on: the densest
#: run in the set, which is where a musical system fails if it is going to, and
#: a mid-density run that ends on a break and on a third-generation descendant,
#: which is where the lineage and hierarchy claims are visible.
REFERENCE_SEEDS: tuple[int, ...] = (17251, 15793)

#: Written into the manifest so the rules are readable next to their result.
CANDIDATE_RULES: dict[str, Any] = {
    "source": PHASE1_SHORTLIST,
    "new_search": False,
    "duration_seconds": [20.0, 26.0],
    "first_spawn_preferred_max": 2.5,
    "first_spawn_hard_max": 3.0,
    "population_total": [8, 15],
    "wanted": [6, 8],
    "requires": [
        "both escape routes present",
        "at least one founder final escape (generation 0)",
        "at least one descendant final escape (generation > 0)",
    ],
    "order": "ascending duration",
}


def _load_shortlist(path: str) -> Mapping[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def derive_candidates(shortlist: Mapping[str, Any]) -> dict[str, Any]:
    """The proof set, from the Phase 1 shortlist, by the brief's rules alone.

    The visual branch is deriving its own set from the same eighteen seeds and
    the same criteria at the same time. If the two sessions are truly parallel
    there is no manifest to read, so this reproduces the criteria exactly and
    records both the survivors and the reason every rejected seed lost - which
    is what a later reconciliation needs in order to be an intersection rather
    than an argument.
    """
    low, high = CANDIDATE_RULES["duration_seconds"]
    preferred = CANDIDATE_RULES["first_spawn_preferred_max"]
    hard = CANDIDATE_RULES["first_spawn_hard_max"]
    pop_low, pop_high = CANDIDATE_RULES["population_total"]
    want_low, want_high = CANDIDATE_RULES["wanted"]

    rows = sorted(shortlist["candidates"], key=lambda row: float(row["duration"]))
    judged: list[dict[str, Any]] = []
    for row in rows:
        reasons: list[str] = []
        duration = float(row["duration"])
        first_spawn = row.get("first_spawn")
        population = int(row["population_total"])
        if not (low <= duration <= high):
            reasons.append(f"duration {duration:.2f}s outside {low}-{high}s")
        if first_spawn is None:
            reasons.append("never split")
        elif float(first_spawn) > hard:
            reasons.append(f"first split {float(first_spawn):.2f}s over the {hard}s limit")
        if not (pop_low <= population <= pop_high):
            reasons.append(f"population {population} outside {pop_low}-{pop_high}")
        if not bool(row["escaped"]):
            reasons.append("no escape")
        judged.append({
            "seed": int(row["seed"]),
            "duration": duration,
            "first_spawn": first_spawn,
            "population_total": population,
            "escape_route": row["escape_route"],
            "escape_generation": row["escape_generation"],
            "final_escape": "founder" if int(row["escape_generation"]) == 0 else "descendant",
            "collisions": int(row["collisions"]),
            "collision_rate": float(row["collision_rate"]),
            "breaks": int(row["breaks"]),
            "spawns": int(row["spawns"]),
            "generations": int(row["generations"]),
            "accepted": not reasons,
            "preferred_split": first_spawn is not None and float(first_spawn) <= preferred,
            "rejected_for": reasons,
        })

    accepted = [row for row in judged if row["accepted"]]
    review_seeds = [int(seed) for seed in shortlist.get("review_seeds", [])]
    if review_seeds:
        by_seed = {int(row["seed"]): row for row in accepted}
        chosen = [by_seed[seed] for seed in review_seeds if seed in by_seed]
    else:
        chosen = [row for row in accepted if row["preferred_split"]]
        # The 2.5 s split is a preference and the 3.0 s one a limit, so the band
        # between them is only opened if the preference cannot fill the set.
        if len(chosen) < want_low:
            for row in accepted:
                if row in chosen:
                    continue
                chosen.append(row)
                if len(chosen) >= want_low:
                    break
            chosen.sort(key=lambda row: row["duration"])
        chosen = chosen[:want_high]

    routes = sorted({row["escape_route"] for row in chosen})
    finals = sorted({row["final_escape"] for row in chosen})
    return {
        "kind": "category3_multiplying_shell_audio_candidates",
        "score_version": score.SCORE_VERSION,
        "config_digest": shortlist["config_digest"],
        "rules": CANDIDATE_RULES,
        "reference_seeds": list(REFERENCE_SEEDS),
        "considered": len(judged),
        "accepted": len(accepted),
        "seeds": [row["seed"] for row in chosen],
        "coverage": {
            "routes": routes,
            "mixed_routes": len(routes) > 1,
            "final_escapes": finals,
            "founder_and_descendant": len(finals) > 1,
            "population_range": [min(row["population_total"] for row in chosen),
                                 max(row["population_total"] for row in chosen)] if chosen else [],
            "duration_range": [round(min(row["duration"] for row in chosen), 3),
                               round(max(row["duration"] for row in chosen), 3)] if chosen else [],
            "in_wanted_band": want_low <= len(chosen) <= want_high,
        },
        "candidates": chosen,
        "judged": judged,
    }


def _write_json(payload: Any, path: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return path


def _playback_path(seed: int) -> str:
    return os.path.join(OUTPUT_ROOT, "playback", f"seed_{seed}.playback.json")


def _document(seed: int, reuse: bool = True) -> dict[str, Any]:
    """The canonical document for a seed, verified against a fresh simulation."""
    path = _playback_path(seed)
    if reuse and os.path.exists(path):
        document = read_playback(path)
        report = verify_document(document)
        if report["ok"]:
            return document
    document = document_for(seed)
    write_playback(document, path)
    return document


def build_seed(seed: int, config: score.AudioConfig, *, write_wav: bool = True,
               reuse: bool = True) -> dict[str, Any]:
    """One seed, one system: document to score to PCM to measurement."""
    document = _document(seed, reuse=reuse)
    plan = score.schedule(document, config)
    rendered = audio.render(plan)
    name = f"seed_{seed}_{config.name}"
    paths = {
        "playback": _playback_path(seed),
        "score": os.path.join(VALIDATION_ROOT, "scores", f"{name}.score.json"),
        "measure": os.path.join(VALIDATION_ROOT, "measurements", f"{name}.measure.json"),
    }
    _write_json(plan.as_dict(), paths["score"])
    if write_wav:
        wav_path = os.path.join(OUTPUT_ROOT, "wav", f"{name}.wav")
        os.makedirs(os.path.dirname(os.path.abspath(wav_path)), exist_ok=True)
        audio.write_master(rendered, wav_path)
        paths["wav"] = wav_path
    report = audio.measure(rendered)
    report["paths"] = paths
    _write_json(report, paths["measure"])
    return report


def _headline(report: Mapping[str, Any]) -> dict[str, Any]:
    richness = report["richness"]["verdict"]
    hierarchy = report["event_hierarchy"]
    return {
        "seed": report["seed"],
        "config": report["config_name"],
        "duration_seconds": report["duration_seconds"],
        "integrated_lufs": report["loudness"]["integrated_lufs"],
        "lra_lu": report["loudness"]["lra_lu"],
        "true_peak_dbtp": report["peak"]["true_peak_dbtp"],
        "clipped_samples": report["peak"]["clipped_samples"],
        "collision_density_hz": report["density"]["collision_density_hz"],
        "event_density_hz": report["density"]["event_density_hz"],
        "polyphony_max": report["polyphony"]["scheduled_max"],
        "polyphony_median": report["polyphony"]["scheduled_median"],
        "polyphony_mean": report["polyphony"]["scheduled_mean"],
        "audible_polyphony_max": report["polyphony"]["audible"]["max"],
        "collision_voice_median_seconds": report["voices"]["collision_median_seconds"],
        "overlap_ratio": report["voices"]["overlap_ratio"],
        "longest_same_pitch_run": report["repetition"]["longest_same_pitch_run"],
        "harsh_pairs": report["consonance"]["harsh_pairs"],
        "duck_fraction": report["duck"]["fraction_below_minus_1db"],
        "onset_rise_median_db": report["masking"]["median_onset_rise_db"],
        "onset_rise_p10_db": report["masking"]["p10_onset_rise_db"],
        "masked_below_3db": report["masking"]["below_3db_fraction"],
        "duck_onsets_per_second": report["duck"]["duck_onsets_per_second"],
        "mono_loss_db": report["mono"]["mono_loss_db"],
        "phone_relative_db": report["phone"]["relative_to_master_db"],
        "richer_late": richness["richer_late"],
        "not_noise": richness["not_noise"],
        "tonal_percent_late": richness["tonal_percent_late"],
        "late_polyphony_over_early": richness["late_polyphony_over_early"],
        "late_lufs_over_early": richness["late_lufs_over_early"],
        "hierarchy_medians": {key: value["median_peak_dbfs"]
                              for key, value in hierarchy.items()},
        "score_fingerprint": report["score_fingerprint"][:16],
        "pcm_digest": report["pcm_digest"][:16],
    }


#: The order the per-kind medians have to come out in, quietest first. It is
#: the brief's hierarchy, and `hierarchy_ok` is the check that the mix agrees
#: with it rather than the design merely intending it.
HIERARCHY_ORDER: tuple[str, ...] = (
    "crossing",
    "collision",
    "collision_strong",
    "spawn",
    "break",
    "escape",
)


def hierarchy_ok(report: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the rendered mix puts the events in the brief's order.

    `lift` is left out of the ordered chain and checked separately: the brief
    puts a progression lift at the same tier as a panel break, so the only
    thing that can be asserted about the pair is that both sit above a spawn
    and below the escape. `spawn_with_lift` is out of the chain for the reason
    `multishell_audio._kind_of` gives - it is a spawn deliberately held down
    because a lift is sounding over it, and it is reported rather than ordered.
    """
    medians = {key: value["median_peak_dbfs"]
               for key, value in report["event_hierarchy"].items()}
    chain = [key for key in HIERARCHY_ORDER if key in medians]
    steps = [(a, b, round(medians[b] - medians[a], 2))
             for a, b in zip(chain, chain[1:])]
    lift = medians.get("lift")
    lift_ok = True
    if lift is not None:
        lift_ok = (medians.get("spawn", -999) < lift < medians.get("escape", 999))
    return {
        "chain": chain,
        "steps": [{"from": a, "to": b, "gain_db": gap} for a, b, gap in steps],
        "monotonic": all(gap > 0.0 for _, _, gap in steps),
        "lift_between_spawn_and_escape": lift_ok,
        "ok": all(gap > 0.0 for _, _, gap in steps) and lift_ok,
    }


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_candidates(args: argparse.Namespace) -> int:
    manifest = derive_candidates(_load_shortlist(args.source))
    path = args.out or os.path.join(VALIDATION_ROOT, "proof_candidates.json")
    _write_json(manifest, path)
    print(f"{len(manifest['seeds'])} proof candidates from "
          f"{manifest['considered']} Phase 1 seeds -> {path}")
    for row in manifest["candidates"]:
        print(f"  {row['seed']:>6}  {row['duration']:6.2f}s  split {float(row['first_spawn']):4.2f}s  "
              f"pop {row['population_total']:>2}  {row['escape_route']:>7}  {row['final_escape']}")
    coverage = manifest["coverage"]
    print(f"  routes {coverage['routes']}  finals {coverage['final_escapes']}  "
          f"population {coverage['population_range']}  duration {coverage['duration_range']}")
    return 0


def cmd_variants(args: argparse.Namespace) -> int:
    seeds = [int(value) for value in args.seeds] if args.seeds else list(REFERENCE_SEEDS)
    names = args.systems or sorted(score.CONFIGS)
    if len(names) > 3:
        raise SystemExit("the brief allows at most three musical systems")
    rows: list[dict[str, Any]] = []
    for name in names:
        config = score.named_config(name)
        for seed in seeds:
            report = build_seed(seed, config, write_wav=not args.no_wav)
            row = _headline(report)
            row["hierarchy"] = hierarchy_ok(report)
            rows.append(row)
            print(f"{name:>18}  seed {seed}  {row['integrated_lufs']:>7} LUFS  "
                  f"peak {row['true_peak_dbtp']:>6} dBTP  poly {row['polyphony_max']:>2}"
                  f"/{row['polyphony_median']:<3}  voice "
                  f"{row['collision_voice_median_seconds']:.3f}s  overlap "
                  f"{row['overlap_ratio']:.2f}  hierarchy {row['hierarchy']['ok']}")
    payload = {
        "kind": "category3_multiplying_shell_audio_variant_comparison",
        "score_version": score.SCORE_VERSION,
        "render_version": audio.RENDER_VERSION,
        "reference_seeds": seeds,
        "systems": {name: score.SYSTEMS[score.CONFIGS[name].system].as_dict() for name in names},
        "rows": rows,
    }
    path = args.out or os.path.join(VALIDATION_ROOT, "variant_comparison.json")
    _write_json(payload, path)
    print(f"-> {path}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    manifest_path = args.manifest or os.path.join(VALIDATION_ROOT, "proof_candidates.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    seeds = [int(value) for value in args.seeds] if args.seeds else list(manifest["seeds"])
    config = score.named_config(args.system)
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        report = build_seed(seed, config, write_wav=not args.no_wav)
        row = _headline(report)
        row["hierarchy"] = hierarchy_ok(report)
        rows.append(row)
        print(f"seed {seed:>6}  {row['duration_seconds']:6.2f}s  {row['integrated_lufs']:>7} LUFS  "
              f"{row['true_peak_dbtp']:>6} dBTP  clip {row['clipped_samples']}  "
              f"ev/s {row['event_density_hz']:5.2f}  poly {row['polyphony_max']:>2}"
              f"/{row['polyphony_median']:<3}  late>early {row['richer_late']}  "
              f"tonal {row['tonal_percent_late']:.1f}%  hierarchy {row['hierarchy']['ok']}")
    payload = {
        "kind": "category3_multiplying_shell_audio_proof_set",
        "score_version": score.SCORE_VERSION,
        "render_version": audio.RENDER_VERSION,
        "system": config.name,
        "tonal_system": config.tonal.as_dict(),
        "config_fingerprint": config.fingerprint(),
        "manifest": manifest_path,
        "seeds": seeds,
        "rows": rows,
        "summary": _proof_summary(rows),
    }
    path = args.out or os.path.join(VALIDATION_ROOT, "proof_set.json")
    _write_json(payload, path)
    print(f"-> {path}")
    return 0


def _proof_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def span(key: str) -> list[float]:
        values = [float(row[key]) for row in rows]
        return [round(min(values), 3), round(max(values), 3)]

    return {
        "seeds": len(rows),
        "integrated_lufs": span("integrated_lufs"),
        "true_peak_dbtp": span("true_peak_dbtp"),
        "clipped_samples": sum(int(row["clipped_samples"]) for row in rows),
        "collision_density_hz": span("collision_density_hz"),
        "event_density_hz": span("event_density_hz"),
        "polyphony_max": span("polyphony_max"),
        "polyphony_median": span("polyphony_median"),
        "collision_voice_median_seconds": span("collision_voice_median_seconds"),
        "longest_same_pitch_run": span("longest_same_pitch_run"),
        "harsh_pairs_total": sum(int(row["harsh_pairs"]) for row in rows),
        "duck_fraction": span("duck_fraction"),
        "onset_rise_median_db": span("onset_rise_median_db"),
        "onset_rise_p10_db": span("onset_rise_p10_db"),
        "masked_below_3db": span("masked_below_3db"),
        "mono_loss_db": span("mono_loss_db"),
        "phone_relative_db": span("phone_relative_db"),
        "tonal_percent_late": span("tonal_percent_late"),
        "all_richer_late": all(bool(row["richer_late"]) for row in rows),
        "all_not_noise": all(bool(row["not_noise"]) for row in rows),
        "all_hierarchy_ok": all(bool(row["hierarchy"]["ok"]) for row in rows),
    }


def cmd_verify(args: argparse.Namespace) -> int:
    """Rebuild from the seed alone and compare against what is on disk."""
    manifest_path = args.manifest or os.path.join(VALIDATION_ROOT, "proof_candidates.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    seeds = [int(value) for value in args.seeds] if args.seeds else list(manifest["seeds"])
    config = score.named_config(args.system)
    failures = 0
    for seed in seeds:
        name = f"seed_{seed}_{config.name}"
        measure_path = os.path.join(VALIDATION_ROOT, "measurements", f"{name}.measure.json")
        score_path = os.path.join(VALIDATION_ROOT, "scores", f"{name}.score.json")
        if not os.path.exists(measure_path):
            print(f"seed {seed}: no measurement on disk")
            failures += 1
            continue
        with open(measure_path, encoding="utf-8") as handle:
            stored = json.load(handle)
        with open(score_path, encoding="utf-8") as handle:
            stored_score = json.load(handle)
        document = document_for(seed)
        plan = score.schedule(document, config)
        rendered = audio.render(plan)
        checks = {
            "playback_digest": document["digest"] == stored["playback_digest"],
            "score_fingerprint": plan.fingerprint() == stored["score_fingerprint"],
            "score_document": plan.as_dict() == stored_score,
            "pcm_digest": rendered.digest() == stored["pcm_digest"],
        }
        ok = all(checks.values())
        failures += 0 if ok else 1
        print(f"seed {seed}: {'ok' if ok else 'MISMATCH ' + str(checks)}")
    print(f"{len(seeds) - failures}/{len(seeds)} reproduce exactly")
    return 0 if failures == 0 else 1



# --------------------------------------------------------------------------
# The diagnostic picture
# --------------------------------------------------------------------------

#: One colour per event kind, in the brief's order of importance.
LANE_COLOURS: dict[str, tuple[int, int, int]] = {
    "crossing": (96, 106, 128),
    "collision": (126, 170, 214),
    "spawn": (236, 176, 88),
    "break": (226, 108, 92),
    "lift": (132, 200, 148),
    "escape": (240, 232, 160),
}
IMAGE_SIZE = (1600, 900)
BACKGROUND = (16, 18, 24)
GRID = (44, 48, 58)


def _x_for(seconds: float, total: float, width: int, left: int) -> int:
    span = max(width - left - 12, 1)
    return left + int(round(span * min(1.0, max(0.0, seconds / max(total, 1e-9)))))


def timeline_image(plan: "score.AudioSchedule", rendered: Any, path: str) -> str:
    """Envelope, duck, polyphony, event lanes and pitch, on one deterministic image.

    Everything drawn here comes from the schedule and the rendered buffer, so
    two runs of the same seed and system produce the same PNG. It exists to be
    read beside the visual branch's own timeline when the two are reconciled.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    width, height = IMAGE_SIZE
    left = 70
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    total = plan.total_seconds

    bands = [("envelope", 40, 210), ("polyphony", 250, 380), ("events", 420, 600),
             ("pitch", 640, 860)]
    for _, top, bottom in bands:
        draw.rectangle([left, top, width - 12, bottom], outline=GRID)
    for second in range(0, int(total) + 1, 2):
        x = _x_for(second, total, width, left)
        draw.line([x, 40, x, 860], fill=GRID)
        draw.text((x + 3, 866), f"{second}s", fill=(120, 128, 142))

    # Envelope and duck.
    envelope = np.abs(rendered.samples).max(axis=1)
    columns = width - left - 12
    step = max(1, envelope.size // columns)
    top, bottom = bands[0][1], bands[0][2]
    middle = (top + bottom) // 2
    for column in range(columns):
        start = column * step
        chunk = envelope[start:start + step]
        if chunk.size == 0:
            continue
        reach = int(round(float(chunk.max()) * (bottom - top) / 2.0))
        draw.line([left + column, middle - reach, left + column, middle + reach],
                  fill=(120, 190, 220))
    duck = rendered.duck
    for column in range(columns):
        start = column * step
        chunk = duck[start:start + step]
        if chunk.size == 0:
            continue
        y = bottom - int(round(float(chunk.min()) * (bottom - top)))
        draw.point((left + column, y), fill=(230, 150, 90))
    draw.text((8, top), "mix", fill=(150, 158, 172))
    draw.text((8, top + 14), "duck", fill=(230, 150, 90))

    # Polyphony.
    top, bottom = bands[1][1], bands[1][2]
    curve = plan.metrics["polyphony_curve"]
    peak = max([live for _, live in curve] + [1])
    points = [(_x_for(at, total, width, left),
               bottom - int(round((bottom - top) * live / peak))) for at, live in curve]
    if len(points) > 1:
        draw.line(points, fill=(150, 210, 170))
    draw.text((8, top), f"voices 0-{peak}", fill=(150, 158, 172))

    # Event lanes.
    top, bottom = bands[2][1], bands[2][2]
    kinds = list(score.EVENT_KINDS)
    lane = (bottom - top) / max(len(kinds), 1)
    for index, kind in enumerate(kinds):
        base = int(top + lane * (index + 1))
        draw.text((8, base - 12), kind, fill=LANE_COLOURS[kind])
        for event in plan.of_kind(kind):
            x = _x_for(event.source_seconds, total, width, left)
            reach = int(round(lane * min(1.0, event.gain / 0.45)))
            draw.line([x, base, x, base - max(2, reach)], fill=LANE_COLOURS[kind])

    # Pitch over time, one dot per pitched event, brightness by generation.
    top, bottom = bands[3][1], bands[3][2]
    ceiling = score.LADDER_TOP
    generations = max([event.generation for event in plan.events] + [1])
    for event in plan.events:
        if event.kind not in ("collision", "crossing", "break", "lift"):
            continue
        x = _x_for(event.source_seconds, total, width, left)
        y = bottom - int(round((bottom - top) * event.ladder_index / ceiling))
        shade = 90 + int(round(150 * event.generation / generations))
        draw.ellipse([x - 2, y - 2, x + 2, y + 2],
                     fill=(shade, shade - 20, 235 - shade // 2))
    draw.text((8, top), f"ladder 0-{ceiling}", fill=(150, 158, 172))
    draw.text((8, bottom - 12), "gen: dark=founder", fill=(120, 128, 142))

    draw.text((left, 12),
              f"seed {plan.seed}  {plan.config.name}  {total:.2f}s  "
              f"{plan.metrics['events']} events  "
              f"max {plan.metrics['max_scheduled_polyphony']} voices  "
              f"escape {plan.escape_seconds:.2f}s",
              fill=(220, 226, 236))

    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    image.save(path)
    return path


def cmd_timeline(args: argparse.Namespace) -> int:
    manifest_path = args.manifest or os.path.join(VALIDATION_ROOT, "proof_candidates.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    seeds = [int(value) for value in args.seeds] if args.seeds else list(manifest["seeds"])
    config = score.named_config(args.system)
    ffmpeg = shutil.which("ffmpeg")
    for seed in seeds:
        document = _document(seed)
        plan = score.schedule(document, config)
        rendered = audio.render(plan)
        name = f"seed_{seed}_{config.name}"
        png = os.path.join(VALIDATION_ROOT, "timelines", f"{name}.timeline.png")
        timeline_image(plan, rendered, png)
        print(f"seed {seed}: {png}")
        if args.mux:
            wav = os.path.join(OUTPUT_ROOT, "wav", f"{name}.wav")
            if not os.path.exists(wav):
                audio.write_master(rendered, wav)
            if ffmpeg is None:
                print("  no ffmpeg on PATH; skipping the mux")
                continue
            mp4 = os.path.join(OUTPUT_ROOT, "diagnostic", f"{name}.diagnostic.mp4")
            os.makedirs(os.path.dirname(os.path.abspath(mp4)), exist_ok=True)
            command = [ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-i", png,
                       "-i", wav, "-c:v", "libx264", "-tune", "stillimage",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-shortest", mp4]
            subprocess.run(command, check=True)
            print(f"  {mp4}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m satisfying.multishell_audio_cli",
        description="Category 3 Test #2 redesign - multi-ball musical audio, Phase 2B",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    candidates = sub.add_parser("candidates", help="derive the proof set from Phase 1")
    candidates.add_argument("--source", default=PHASE1_SHORTLIST)
    candidates.add_argument("--out")
    candidates.set_defaults(handler=cmd_candidates)

    variants = sub.add_parser("variants", help="compare the musical systems")
    variants.add_argument("--seeds", nargs="*")
    variants.add_argument("--systems", nargs="*")
    variants.add_argument("--no-wav", action="store_true")
    variants.add_argument("--out")
    variants.set_defaults(handler=cmd_variants)

    build = sub.add_parser("build", help="render the whole proof set")
    build.add_argument("--system", default=score.SELECTED_SYSTEM)
    build.add_argument("--manifest")
    build.add_argument("--seeds", nargs="*")
    build.add_argument("--no-wav", action="store_true")
    build.add_argument("--out")
    build.set_defaults(handler=cmd_build)

    verify = sub.add_parser("verify", help="re-derive and compare digests")
    verify.add_argument("--system", default=score.SELECTED_SYSTEM)
    verify.add_argument("--manifest")
    verify.add_argument("--seeds", nargs="*")
    verify.set_defaults(handler=cmd_verify)

    timeline = sub.add_parser("timeline", help="draw the diagnostic timeline")
    timeline.add_argument("--system", default=score.SELECTED_SYSTEM)
    timeline.add_argument("--manifest")
    timeline.add_argument("--seeds", nargs="*")
    timeline.add_argument("--mux", action="store_true",
                          help="also mux the picture against the WAV with FFmpeg")
    timeline.set_defaults(handler=cmd_timeline)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
