"""Build the bounded Phase 2B shell-audio evidence set.

The command intentionally uses eight of Phase 1's sixteen shortlisted seeds;
it never performs a seed search.  Two reference seeds receive the three
coherent treatments, while every candidate receives the selected hybrid.

    python -m satisfying.shell_audio_cli build
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from typing import Any, Sequence

from satisfying import shell_audio, shell_playback, shell_score


DEFAULT_OUT = os.path.join("output", "category3_shell_audio_v2b")
DEFAULT_EVIDENCE = os.path.join("docs", "validation", "category3_shell_audio_v2b")

# Exactly half of the existing Phase 1 shortlist, chosen to span 18.7-23.8 s,
# both final routes, 8-17 breaks, 9-15 near misses, and distinct progression
# mixes.  This is evaluation, not another seed search.
CANDIDATE_SEEDS: tuple[int, ...] = (19607, 1511, 17534, 3654, 11929, 9589, 16513, 8952)
REFERENCE_SEEDS: tuple[int, ...] = (11929, 9589)


def _write_json(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=False)
        handle.write("\n")
    return path


def _paths(root: str, seed: int, variant: str) -> dict[str, str]:
    stem = f"seed_{seed}_{variant}"
    return {
        "playback": os.path.join(root, "playback", f"seed_{seed}.json"),
        "score": os.path.join(root, "scores", stem + ".score.json"),
        "wav": os.path.join(root, "wav", stem + ".wav"),
        "measure": os.path.join(root, "measurements", stem + ".measure.json"),
    }


def _shortlist_rows() -> dict[int, dict[str, Any]]:
    path = os.path.join("docs", "validation", "category3_shell_escape", "phase1_shortlist.json")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {int(row["seed"]): row for row in payload["candidates"]}


def _jobs(seeds: Sequence[int]) -> list[tuple[int, str]]:
    jobs = [(int(seed), "refined_hybrid") for seed in seeds]
    for seed in REFERENCE_SEEDS:
        if seed in seeds:
            jobs.extend((seed, name) for name in ("clean_percussive", "resonant_musical"))
    return jobs


def _copy_evidence(source: str, evidence: str, subdir: str) -> str:
    target = os.path.join(evidence, subdir, os.path.basename(source))
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)
    return target


def build(args: argparse.Namespace) -> int:
    seeds = tuple(args.seeds or CANDIDATE_SEEDS)
    unknown = sorted(set(seeds) - set(_shortlist_rows()))
    if unknown:
        raise SystemExit(f"seeds are not in the frozen Phase 1 shortlist: {unknown}")

    documents: dict[int, dict[str, Any]] = {}
    for seed in seeds:
        document = shell_playback.document_for(seed)
        verification = shell_playback.verify_document(document)
        if not all(value for key, value in verification.items() if key.endswith("_matches")):
            raise SystemExit(f"canonical playback verification failed for seed {seed}: {verification}")
        if not document["summary"]["escaped"]:
            raise SystemExit(f"shortlisted seed {seed} is not an escape")
        path = _paths(args.out, seed, "refined_hybrid")["playback"]
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        shell_playback.write_playback(document, path)
        documents[seed] = document
        print(f"playback seed {seed}: {document['digest'][:16]} -> {path}", flush=True)

    records: list[dict[str, Any]] = []
    for seed, variant in _jobs(seeds):
        started = time.time()
        config = shell_score.named_config(variant)
        plan = shell_score.schedule(documents[seed], config)
        rendered = shell_audio.render(plan)
        paths = _paths(args.out, seed, variant)
        score_payload = plan.as_dict()
        score_payload["score_fingerprint"] = plan.fingerprint()
        _write_json(paths["score"], score_payload)
        shell_audio.write_master(rendered, paths["wav"])
        measurement = shell_audio.measure(rendered)
        measurement["wav"] = os.path.relpath(paths["wav"], args.out).replace("\\", "/")
        measurement["score"] = os.path.relpath(paths["score"], args.out).replace("\\", "/")
        _write_json(paths["measure"], measurement)
        _copy_evidence(paths["score"], args.evidence, "scores")
        _copy_evidence(paths["measure"], args.evidence, "measurements")
        records.append(measurement)
        print(
            f"audio seed {seed:<5d} {variant:<18s} "
            f"{measurement['duration_seconds']:5.2f}s  "
            f"{measurement['loudness']['integrated_lufs']:+6.2f} LUFS  "
            f"{measurement['peak']['true_peak_dbtp']:+5.2f} dBTP  "
            f"poly {measurement['maximum_polyphony']}  "
            f"mono {measurement['mono']['mono_loss_db']:+.2f} dB  "
            f"{time.time() - started:.1f}s",
            flush=True,
        )

    rows = _shortlist_rows()
    candidates = []
    for seed in seeds:
        phase1 = rows[seed]
        measured = next(record for record in records
                        if record["seed"] == seed
                        and record["config_fingerprint"] == shell_score.DEFAULT_CONFIG.fingerprint())
        candidates.append({
            "seed": seed,
            "duration_seconds": phase1["duration"],
            "collisions": phase1["collisions"],
            "near_misses": phase1["near_misses"],
            "breaks": phase1["breaks"],
            "progression_opening": phase1["progression_opening"],
            "progression_break": phase1["progression_break"],
            "final_method": phase1["final_method"],
            "regressions": phase1["regressions"],
            "integrated_lufs": measured["loudness"]["integrated_lufs"],
            "true_peak_dbtp": measured["peak"]["true_peak_dbtp"],
            "maximum_polyphony": measured["maximum_polyphony"],
            "phone_relative_db": measured["phone"]["relative_to_master_db"],
            "mono_loss_db": measured["mono"]["mono_loss_db"],
            "score_fingerprint": measured["score_fingerprint"],
            "pcm_digest": measured["pcm_digest"],
        })

    variants = []
    for seed in REFERENCE_SEEDS:
        if seed not in seeds:
            continue
        for variant in shell_score.CONFIGS:
            config = shell_score.named_config(variant)
            row = next(record for record in records
                       if record["seed"] == seed
                       and record["config_fingerprint"] == config.fingerprint())
            variants.append({
                "seed": seed,
                "variant": variant,
                "integrated_lufs": row["loudness"]["integrated_lufs"],
                "true_peak_dbtp": row["peak"]["true_peak_dbtp"],
                "maximum_polyphony": row["maximum_polyphony"],
                "note_overlap_seconds": row["note_overlap_seconds"],
                "phone_relative_db": row["phone"]["relative_to_master_db"],
                "mono_loss_db": row["mono"]["mono_loss_db"],
                "pcm_digest": row["pcm_digest"],
            })

    report = {
        "phase": "category3-shell-audio-v2b",
        "source_branch": "category3-shell-escape-v1",
        "source_sha": "42cdbb34588f052be45377d7c20c89d8100fcf99",
        "schema_version": shell_score.SCHEMA_VERSION,
        "config_digest": shell_score.CONFIG_DIGEST,
        "candidate_seeds": list(seeds),
        "reference_seeds": [seed for seed in REFERENCE_SEEDS if seed in seeds],
        "variants_compared": list(shell_score.CONFIGS),
        "recommendation": "refined_hybrid",
        "recommendation_reason": (
            "The hybrid keeps the clean design's transient separation while retaining "
            "enough pitched decay, damage colour, and harmonic bloom for the collisions "
            "to form a coherent musical phrase. It uses no sustained bed."
        ),
        "candidates": candidates,
        "variant_comparison": variants,
        "outputs": {
            "root": os.path.normpath(args.out).replace("\\", "/"),
            "wav_count": len(records),
            "score_count": len(records),
            "measurement_count": len(records),
        },
    }
    output_report = _write_json(os.path.join(args.out, "candidate_comparison.json"), report)
    evidence_report = _write_json(os.path.join(args.evidence, "candidate_comparison.json"), report)
    print(f"comparison -> {output_report}", flush=True)
    print(f"tracked evidence -> {evidence_report}", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    sub = out.add_subparsers(dest="command", required=True)
    command = sub.add_parser("build", help="score, render, measure, and compare the bounded set")
    command.add_argument("--out", default=DEFAULT_OUT)
    command.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    command.add_argument("--seeds", type=int, nargs="*")
    command.set_defaults(func=build)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
