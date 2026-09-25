"""Offline, chronological, leave-future-out replay over real engineering history.

For every historical developer attempt N, in decision order, the replay asks:
*had the experience store existed then, what would it have said?* - using
only episodes that had **settled strictly before the day N was decided**, and
judging them against the repository **as it stood at N's base commit**.

## What makes it leave-future-out

1. **Chronology by day, strictly.** Job transitions carry dates, not times, so
   the only ordering the records can prove is "an earlier day". An episode
   settled on the same day as a decision is excluded from it - including the
   cases where it probably was earlier - because "probably" is how future
   outcomes leak into a replay. The count of same-day exclusions is reported.
2. **Queries are built from decision-time features only**
   (`ExperienceQuery.from_features`), which cannot hold an outcome.
3. **Governance is joined as of the decision day** (`governance_facts(...,
   before=day)`): a CEO rejection recorded after N was decided cannot
   downgrade a precedent for N.
4. **Each episode is anchored against its own base commit, and each query
   judged against its own.** The caller supplies `view_for(commit)`; this
   module never reads git (Company OS holds no process authority).

## What it measures, and what it must not be called

Counts, overlaps, sizes and latency of a deterministic procedure over a small
corpus. It is **not** model accuracy, and it says nothing about provider
tokens or money: the suggestions are `COUNTERFACTUAL` - no historical session
ever received them - and every row says so.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from company.engineering.store import EngineeringStore

from .advice import build_advice
from .capture import attempt_cycles, build_episode
from .errors import CaptureRefused, ExperienceConflict
from .model import EvidenceBasis, ExperienceEpisode, Measurement, decision_features
from .repository import RepositoryView
from .retrieval import ExperienceQuery, retrieve
from .store import ExperienceStore


@dataclass(frozen=True)
class CorpusSource:
    label: str
    state_dir: Path


def corpus_manifest(sources: Sequence[CorpusSource]) -> list[dict[str, Any]]:
    """Every record file each source holds, digested, so the inputs are checkable."""
    out = []
    for source in sources:
        files = sorted(
            p for sub in ("engineering", "execution", "resource_usage") for p in (source.state_dir / sub).rglob("*.json")
        )
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.relative_to(source.state_dir).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        out.append(
            {
                "label": source.label,
                "record_files": len(files),
                "record_bytes": sum(p.stat().st_size for p in files),
                "sha256": digest.hexdigest(),
            }
        )
    return out


def _canonical_bytes(state_dir: Path, episode: ExperienceEpisode) -> int:
    total = 0
    for pointer in episode.evidence:
        try:
            total += (state_dir / pointer.record_ref).stat().st_size
        except OSError:
            continue
    return total


def run_replay(
    sources: Sequence[CorpusSource],
    *,
    view_for: Callable[[str], RepositoryView | None],
    scratch_store: ExperienceStore,
    captured_on: dt.date,
) -> dict[str, Any]:
    """Capture every settled attempt, then replay every decision in order."""
    by_label = {s.label: s.state_dir for s in sources}
    decisions: list[dict[str, Any]] = []
    capture_counts: dict[str, int] = {}
    episodes: list[ExperienceEpisode] = []

    def count(key: str) -> None:
        capture_counts[key] = capture_counts.get(key, 0) + 1

    for source in sources:
        engineering = EngineeringStore(source.state_dir)
        for work_order_id in engineering.work_order_ids():
            try:
                order = engineering.work_order(work_order_id)
            except Exception:  # noqa: BLE001 - counted, not repaired
                count("refused:work_order_undecodable")
                continue
            job = engineering.job(work_order_id) if order is not None else None
            if order is None or job is None:
                count("refused:no_job")
                continue
            for cycle in attempt_cycles(job):
                decisions.append(
                    {
                        "source": source.label,
                        "work_order_id": work_order_id,
                        "order": order,
                        "cycle": cycle,
                    }
                )
                if not cycle.settled:
                    count("refused:not_settled")
                    continue
                view = view_for(order.base_commit)
                if view is None:
                    count("refused:provenance_unavailable")
                    continue
                try:
                    episode = build_episode(
                        source.state_dir, work_order_id, cycle, view, captured_on=captured_on, source=source.label, order=order, job=job
                    )
                    scratch_store.put(episode)
                except CaptureRefused as exc:
                    count(f"refused:{exc.code}")
                    continue
                except ExperienceConflict:
                    count("refused:conflict")
                    continue
                count("captured")
                count(f"class:{episode.engineering_class().value}")
                episodes.append(episode)

    scan = scratch_store.scan()
    decisions.sort(key=lambda d: (d["cycle"].decided_on, d["work_order_id"], d["cycle"].packet_attempt))
    rows = []
    for item in decisions:
        order, cycle = item["order"], item["cycle"]
        query = ExperienceQuery.from_features(
            item["work_order_id"],
            decision_features(order, attempt=cycle.packet_attempt),
            decided_on=cycle.decided_on,
        )
        view = view_for(order.base_commit)
        same_day = sum(
            1 for e in scan.episodes if e.settled_on == cycle.decided_on and e.work_order_id != item["work_order_id"]
        )
        if view is None:
            rows.append(
                {
                    "work_order_id": item["work_order_id"],
                    "attempt": cycle.packet_attempt,
                    "decided_on": cycle.decided_on.isoformat(),
                    "status": "not_replayed",
                    "reason": "no repository view for the base commit",
                }
            )
            continue
        started = time.perf_counter()
        result = retrieve(query, view, scan=scan, resolve_source=lambda label: by_label.get(label))
        advice = build_advice(query, result, view, work_order_fingerprint=order.fingerprint(), as_of=cycle.decided_on)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        actual = next(
            (
                e
                for e in scan.episodes
                if e.work_order_id == item["work_order_id"] and e.packet_attempt == cycle.packet_attempt
            ),
            None,
        )
        eligible = sum(1 for e in scan.episodes if e.settled_on < cycle.decided_on and e.work_order_id != item["work_order_id"])
        suggested_files = [f["path"] for f in advice["suggested_files"]]
        suggested_tests = [t["path"] for t in advice["suggested_tests"]]
        changed = set(actual.outcome.files_changed) if actual is not None else set()
        overlap = sorted(set(suggested_files) & changed)
        considered_bytes = sum(
            _canonical_bytes(by_label[c.episode.source], c.episode)
            for c in (*result.precedents, *result.warnings, *result.historical)
            if c.episode.source in by_label
        )
        eligible_bytes = sum(
            _canonical_bytes(by_label[e.source], e)
            for e in scan.episodes
            if e.settled_on < cycle.decided_on and e.work_order_id != item["work_order_id"] and e.source in by_label
        )
        rows.append(
            {
                "work_order_id": item["work_order_id"],
                "source": item["source"],
                "attempt": cycle.packet_attempt,
                "decided_on": cycle.decided_on.isoformat(),
                "eligible_history": eligible,
                "same_day_excluded": same_day,
                "status": advice["status"],
                "abstention": (advice["abstention"] or {}).get("code", ""),
                "precedents": [p["work_order_id"] for p in advice["precedents"]],
                "top1": advice["precedents"][0]["work_order_id"] if advice["precedents"] else "",
                "top1_why": advice["precedents"][0]["why"] if advice["precedents"] else [],
                "warnings": [w["work_order_id"] for w in advice["warnings"]],
                "historical_only": [h["work_order_id"] for h in advice["historical_only"]],
                "excluded": advice["measurement"].get("excluded", {}),
                "suggested_files": Measurement(
                    suggested_files, EvidenceBasis.COUNTERFACTUAL, "what the advisory would have offered; no session received it"
                ).to_dict(),
                "suggested_tests": Measurement(
                    suggested_tests, EvidenceBasis.COUNTERFACTUAL, "what the advisory would have offered; no session received it"
                ).to_dict(),
                "refused": advice["refused"],
                "actual_class": actual.engineering_class().value if actual is not None else "not_captured",
                "actual_files_changed": sorted(changed),
                "suggested_files_changed_later": overlap,
                "advice_chars": len(json.dumps(advice, sort_keys=True, separators=(",", ":"))),
                "considered_history_bytes": considered_bytes,
                "eligible_history_bytes": eligible_bytes,
                "advice_fingerprint": advice["fingerprint"],
                "latency_ms": round(elapsed_ms, 3),
            }
        )
    return {
        "captured_on": captured_on.isoformat(),
        "sources": [s.label for s in sources],
        "capture": dict(sorted(capture_counts.items())),
        "store_problems": list(scan.problems),
        "episodes": [
            {
                "experience_id": e.experience_id,
                "work_order_id": e.work_order_id,
                "attempt": e.packet_attempt,
                "source": e.source,
                "decided_on": e.decided_on.isoformat(),
                "settled_on": e.settled_on.isoformat(),
                "class": e.engineering_class().value,
            }
            for e in scan.episodes
        ],
        "rows": rows,
        "summary": summarise(rows),
    }


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every headline number, derived from the rows and nothing else."""
    replayed = [r for r in rows if r.get("status") in ("precedent", "abstain")]
    with_history = [r for r in replayed if r.get("eligible_history", 0) > 0]
    precedent = [r for r in replayed if r["status"] == "precedent"]
    abstentions: dict[str, int] = {}
    for r in replayed:
        if r["status"] == "abstain":
            abstentions[r["abstention"]] = abstentions.get(r["abstention"], 0) + 1
    suggested = [r for r in precedent if r["suggested_files"]["value"]]
    hits = [r for r in suggested if r["suggested_files_changed_later"]]
    suggested_total = sum(len(r["suggested_files"]["value"]) for r in suggested)
    hit_total = sum(len(r["suggested_files_changed_later"]) for r in suggested)
    changed_total = sum(len(r["actual_files_changed"]) for r in suggested)
    excluded: dict[str, int] = {}
    for r in replayed:
        for key, value in (r.get("excluded") or {}).items():
            excluded[key] = excluded.get(key, 0) + int(value)
    refused_authority = sum(
        1 for r in replayed for item in r.get("refused", ()) if "read authority" in item["reason"] or "forbidden" in item["reason"]
    )
    refused_total = sum(len(r.get("refused", ())) for r in replayed)
    warning_rows = [r for r in replayed if r["warnings"]]
    warned_then_corrected = [r for r in warning_rows if r["actual_class"] == "correction"]
    advice_chars = [r["advice_chars"] for r in replayed]
    eligible_bytes = [r["eligible_history_bytes"] for r in replayed if r["eligible_history_bytes"]]
    latencies = sorted(r["latency_ms"] for r in replayed)
    return {
        "decisions": len(rows),
        "replayed": len(replayed),
        "not_replayed": len(rows) - len(replayed),
        "with_eligible_history": len(with_history),
        "precedent_found": len(precedent),
        "abstained": len(replayed) - len(precedent),
        "abstentions_by_code": dict(sorted(abstentions.items())),
        "rows_with_file_suggestions": len(suggested),
        "rows_where_a_suggested_file_was_changed": len(hits),
        "suggested_files_total": suggested_total,
        "suggested_files_later_changed": hit_total,
        "changed_files_in_rows_with_suggestions": changed_total,
        "rows_with_warnings": len(warning_rows),
        "rows_with_warnings_that_ended_as_corrections": len(warned_then_corrected),
        "candidates_excluded_by_reason": dict(sorted(excluded.items())),
        "suggestions_refused_total": refused_total,
        "suggestions_refused_by_read_authority": refused_authority,
        "same_day_episodes_excluded_total": sum(r.get("same_day_excluded", 0) for r in replayed),
        "advice_chars_max": max(advice_chars) if advice_chars else 0,
        "advice_chars_median": sorted(advice_chars)[len(advice_chars) // 2] if advice_chars else 0,
        "eligible_history_bytes_max": max(eligible_bytes) if eligible_bytes else 0,
        "latency_ms_median": latencies[len(latencies) // 2] if latencies else None,
        "latency_ms_max": latencies[-1] if latencies else None,
    }


def replay_fingerprint(report: Mapping[str, Any]) -> str:
    """The identity of a replay's answers, without the wall clock."""
    rows = [{k: v for k, v in row.items() if k != "latency_ms"} for row in report.get("rows", ())]
    return _fingerprint({"capture": report.get("capture"), "episodes": report.get("episodes"), "rows": rows})


__all__ = ["CorpusSource", "corpus_manifest", "replay_fingerprint", "run_replay", "summarise"]
