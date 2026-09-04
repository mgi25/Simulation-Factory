"""Packaging a checked batch, and deciding what not to do again.

Two jobs that have nothing to do with each other except that both are about
files rather than about audio or pixels:

* Delivery. A finished batch is a folder of MP4s and QC records and nothing
  else - no frame sequences, no WAVs, no replays. Those stay in the working
  render directories, because a delivery folder that carried them would be
  four gigabytes for twenty Shorts and would still not be the thing anyone
  wants to send. Copying into it is refused rather than allowed to overwrite
  a video that somebody has already watched and approved.

* Resume. Rendering a Short is two and a half minutes. Producing a batch
  twice must not take twice as long, so each stage is reused when it can be
  proved good and rebuilt when it cannot. The proof is verification, never
  the file merely existing, and the decision is printed rather than kept in
  a cache nobody can read.
"""

from __future__ import annotations

import json
import os
import posixpath
import shutil
from typing import Any

from production.qc import (
    QC_VERSION,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    STATUS_PASS,
)

# The production manifest's own schema version, separate from the batch
# manifest (v1) it was produced from and the QC records (v1) it summarises.
PRODUCTION_VERSION = 1
PRODUCTION_MANIFEST_NAME = "production_manifest.json"
CONTACT_SHEET_NAME = "contact_sheet.png"

REUSED = "REUSED"
GENERATED = "GENERATED"
STAGES = ("replay", "frames", "audio", "encode")


class DeliveryError(RuntimeError):
    """A deliverable could not be written where it belongs."""


# --- naming ----------------------------------------------------------------


def production_dir_name(batch_id: str) -> str:
    """The delivery folder one batch produces, named from the batch."""
    return f"production_{batch_id}"


def item_dir_name(index: int, seed: int) -> str:
    """One item's folder. Index first so the directory sorts in batch order.

    The seed is in the name as well as the index because two items can share
    neither - the index says where it is in the batch and the seed says which
    battle it is, and a folder that names both cannot be confused with
    another batch's third item.
    """
    if index < 0:
        raise DeliveryError(f"item index cannot be negative: {index}")
    return f"{index:03d}_seed_{seed}"


def relative_to(path: str, root: str) -> str:
    """A repo-relative POSIX path, or the filename if it is outside the repo.

    Nothing written by this package is allowed to be an absolute path: a
    production manifest has to mean the same thing after the output folder is
    copied to another machine.
    """
    try:
        relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        return os.path.basename(path)
    relative = relative.replace(os.sep, "/")
    if relative.startswith("../") or relative == "..":
        return posixpath.basename(relative)
    return relative


# --- resume ----------------------------------------------------------------


def stage_plan(
    frames_valid: bool, audio_valid: bool, video_valid: bool
) -> dict[str, str]:
    """Which of the three expensive stages can be reused, once each is checked.

    Note what is *not* an input: whether the replay had to be re-exported.
    Cascading on that would be the obvious design and it would also be wrong.
    Exporting a replay is deterministic, so a replay that went missing and
    was re-exported is byte-identical to the one the frames were rendered
    from - and re-rendering because of it would cost two and a half minutes
    to arrive at the same pictures. What actually matters is whether the
    frames and the soundtrack were built from *this* replay, and that is a
    hash comparison rather than a guess: `frames_valid` and `audio_valid`
    arriving here already mean their recorded replay hash matched.

    What does cascade is the encode. It is made of the frames and the
    soundtrack, so rebuilding either means the MP4 on disk is not made of
    them any more, whatever it reports about itself.
    """
    frames = REUSED if frames_valid else GENERATED
    audio = REUSED if audio_valid else GENERATED
    encode = (
        REUSED if (video_valid and frames == REUSED and audio == REUSED) else GENERATED
    )
    return {"frames": frames, "audio": audio, "encode": encode}


# --- delivery --------------------------------------------------------------


def deliver_file(
    source: str,
    destination: str,
    *,
    digest_of,
    force: bool = False,
    protected: bool = False,
) -> str:
    """Copy one deliverable, refusing to replace different content silently.

    Three outcomes, and only one of them writes:

    * nothing there yet - copy it.
    * the same bytes are already there - leave them, say `reused`. Copying
      would be identical work for an identical result.
    * different bytes are there - refuse. A delivery folder is what somebody
      reviews and what eventually gets uploaded; replacing a video underneath
      that quietly is the one failure mode with no way back. `force` is the
      only way past it, and `protected` - an item a person has approved -
      says so in the refusal.
    """
    if not os.path.isfile(source):
        raise DeliveryError(f"nothing to deliver: {source}")

    if os.path.isfile(destination):
        if digest_of(source) == digest_of(destination):
            return "reused"
        if not force:
            what = "approved" if protected else "existing"
            raise DeliveryError(
                f"{os.path.basename(destination)} already holds a different"
                f" {what} video. Pass --force to replace it."
            )
        outcome = "replaced"
    else:
        outcome = "copied"

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)
    return outcome


def write_json(path: str, payload: Any) -> str:
    """One way of writing every deterministic file this package produces."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def read_json(path: str) -> dict[str, Any] | None:
    """A JSON file, or None if it is absent or unreadable.

    Absent is normal - a first production run has no previous QC record to
    carry a review answer forward from - so it is not an error.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


# --- the production manifest ----------------------------------------------


def manifest_item(record: dict[str, Any], video: str, qc: str) -> dict[str, Any]:
    """One production manifest entry: what it is, how it did, where it went."""
    source = record.get("source") or {}
    return {
        "index": source.get("index"),
        "seed": source.get("seed"),
        "label": source.get("label", ""),
        "powers": list(source.get("powers") or ()),
        "score": source.get("score"),
        "duration": (record.get("video") or {}).get("duration"),
        "frames": (record.get("render") or {}).get("frames"),
        "automated_status": record.get("status"),
        "review_status": record.get("review_status", REVIEW_PENDING),
        "review_note": record.get("review_note", ""),
        "warnings": list(record.get("warnings") or ()),
        "problems": list(record.get("problems") or ()),
        "video": video,
        "video_sha256": (record.get("video") or {}).get("sha256", ""),
        "video_bytes": (record.get("video") or {}).get("bytes", 0),
        "integrated_lufs": (record.get("audio") or {}).get("integrated_lufs"),
        "true_peak_dbfs": (record.get("audio") or {}).get("true_peak_dbfs"),
        "phone_band_lufs": (record.get("audio") or {}).get("phone_band_lufs"),
        "qc": qc,
    }


def _mean(values: list[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 3)


def summarise(items: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers a person wants before opening any of the videos."""
    passed = [item for item in items if item.get("automated_status") == STATUS_PASS]
    scores = [item["score"] for item in items if item.get("score") is not None]
    durations = [item["duration"] for item in items if item.get("duration") is not None]
    sizes = [item.get("video_bytes", 0) for item in items]
    loudness = [
        item["integrated_lufs"]
        for item in items
        if item.get("integrated_lufs") is not None
    ]
    band = [
        item["phone_band_lufs"]
        for item in items
        if item.get("phone_band_lufs") is not None
    ]
    reviews = {
        name: sum(1 for item in items if item.get("review_status") == name)
        for name in (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)
    }
    return {
        "items": len(items),
        "automated_pass": len(passed),
        "automated_fail": len(items) - len(passed),
        "review": reviews,
        "warnings": sum(len(item.get("warnings") or ()) for item in items),
        "score": {
            "min": min(scores) if scores else None,
            "mean": _mean(scores),
            "max": max(scores) if scores else None,
        },
        "duration": {
            "min": min(durations) if durations else None,
            "mean": _mean(durations),
            "max": max(durations) if durations else None,
            "total": round(sum(durations), 3) if durations else None,
        },
        "integrated_lufs": {
            "min": min(loudness) if loudness else None,
            "mean": _mean(loudness),
            "max": max(loudness) if loudness else None,
        },
        "phone_band_lufs": {
            "min": min(band) if band else None,
            "mean": _mean(band),
            "max": max(band) if band else None,
        },
        "video_bytes": {
            "total": sum(sizes),
            "mean": int(sum(sizes) / len(sizes)) if sizes else 0,
        },
    }


def production_manifest(
    batch_id: str, source_manifest: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    """One deterministic summary of a produced batch.

    Everything in it is derived from the QC records beside the videos, so it
    can be rebuilt from the delivery folder alone. No timestamps, no machine
    names, no absolute paths - the same batch produces the same manifest, and
    the folder means the same thing wherever it is copied to.
    """
    ordered = sorted(items, key=lambda entry: (entry.get("index") or 0))
    return {
        "version": PRODUCTION_VERSION,
        "qc_version": QC_VERSION,
        "batch_id": batch_id,
        "source_manifest": source_manifest,
        "summary": summarise(ordered),
        "items": ordered,
    }


def apply_review(
    manifest: dict[str, Any], decisions: dict[int, tuple[str, str]]
) -> list[str]:
    """Set review answers on a loaded production manifest, in place.

    Returns what changed, in index order, so a review command can say what
    it did rather than only that it did something.
    """
    changed: list[str] = []
    by_index = {entry.get("index"): entry for entry in manifest.get("items", [])}
    for index in sorted(decisions):
        entry = by_index.get(index)
        if entry is None:
            raise DeliveryError(f"no item {index} in this batch")
        status, note = decisions[index]
        was = entry.get("review_status", REVIEW_PENDING)
        entry["review_status"] = status
        entry["review_note"] = note
        changed.append(f"{index:03d} {was} -> {status}" + (f"  ({note})" if note else ""))
    manifest["summary"] = summarise(manifest.get("items", []))
    return changed
