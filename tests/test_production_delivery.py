"""Phase 6C tests: packaging a batch, and not doing expensive work twice.

Two things being protected here. One is a reviewed video: a delivery folder
is what a person watches and what eventually gets uploaded, so replacing a
file in it with different bytes has to be refused rather than allowed. The
other is time: rendering a Short is two and a half minutes, and the resume
decisions are what stop a second run repeating it.

The decisions themselves are a pure function of three booleans, so they are
tested as one, without a renderer anywhere near them.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from production import contact_sheet, delivery, qc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REUSED, GENERATED = delivery.REUSED, delivery.GENERATED


def digest_of(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def record(
    index: int = 1,
    seed: int = 21465,
    status: str = qc.STATUS_PASS,
    review: str = qc.REVIEW_PENDING,
    *,
    note: str = "",
    score: float = 92.6,
    duration: float = 16.15,
    lufs: float | None = -20.3,
    band: float | None = -22.5,
    peak: float | None = -1.3,
    size: int = 6_500_000,
    warnings: tuple[str, ...] = (),
    problems: tuple[str, ...] = (),
) -> dict:
    """A QC record reduced to what the manifest and the summary read."""
    return {
        "version": qc.QC_VERSION,
        "status": status,
        "problems": list(problems),
        "warnings": list(warnings),
        "review_status": review,
        "review_note": note,
        "source": {
            "batch_id": "audit10",
            "index": index,
            "seed": seed,
            "label": "TITAN vs ORBIT",
            "powers": ["titan", "orbit"],
            "score": score,
        },
        "render": {"frames": 969},
        "audio": {
            "integrated_lufs": lufs,
            "true_peak_dbfs": peak,
            "phone_band_lufs": band,
        },
        "video": {"sha256": "d" * 64, "bytes": size, "duration": duration},
    }


def entry_for(item: dict) -> dict:
    name = delivery.item_dir_name(item["source"]["index"], item["source"]["seed"])
    return delivery.manifest_item(item, f"{name}/short.mp4", f"{name}/qc.json")


# --- naming ---------------------------------------------------------------


def test_the_delivery_folder_is_named_from_the_batch() -> None:
    assert delivery.production_dir_name("audit10") == "production_audit10"
    assert delivery.production_dir_name("shorts001") == "production_shorts001"


def test_an_item_folder_names_both_its_place_and_its_battle() -> None:
    """The index so it sorts, the seed so it cannot be confused with another."""
    assert delivery.item_dir_name(1, 21465) == "001_seed_21465"
    assert delivery.item_dir_name(10, 27740) == "010_seed_27740"
    names = [delivery.item_dir_name(index, 5) for index in (1, 2, 9, 10, 20)]
    assert names == sorted(names)


def test_a_negative_item_index_is_refused() -> None:
    with pytest.raises(delivery.DeliveryError):
        delivery.item_dir_name(-1, 5)


def test_every_recorded_path_is_relative() -> None:
    inside = os.path.join(ROOT, "output", "production_audit10", "001_seed_5", "short.mp4")
    assert delivery.relative_to(inside, ROOT) == (
        "output/production_audit10/001_seed_5/short.mp4"
    )
    assert "\\" not in delivery.relative_to(inside, ROOT)
    # Something outside the project is recorded by name, never by a ../ chain.
    outside = delivery.relative_to(os.path.join(os.sep, "elsewhere", "x.json"), ROOT)
    assert outside == "x.json"
    assert not os.path.isabs(outside)


# --- resume ---------------------------------------------------------------


def test_everything_valid_is_everything_reused() -> None:
    assert delivery.stage_plan(True, True, True) == {
        "frames": REUSED,
        "audio": REUSED,
        "encode": REUSED,
    }


def test_a_missing_video_rebuilds_only_the_encode() -> None:
    """Frames are the expensive stage and must not be touched to make an MP4."""
    plan = delivery.stage_plan(True, True, False)
    assert plan["frames"] == REUSED
    assert plan["audio"] == REUSED
    assert plan["encode"] == GENERATED


def test_bad_audio_rebuilds_audio_and_the_encode_only() -> None:
    plan = delivery.stage_plan(True, False, True)
    assert plan["frames"] == REUSED
    assert plan["audio"] == GENERATED
    assert plan["encode"] == GENERATED


def test_an_incomplete_sequence_rebuilds_frames_but_not_audio() -> None:
    """Audio is a function of the replay and the frame count, not the pixels."""
    plan = delivery.stage_plan(False, True, True)
    assert plan["frames"] == GENERATED
    assert plan["audio"] == REUSED
    assert plan["encode"] == GENERATED


def test_a_valid_video_is_never_reused_on_top_of_a_rebuilt_stage() -> None:
    """Whatever the MP4 reports, it is not made of the new frames."""
    for frames, audio in ((False, True), (True, False), (False, False)):
        assert delivery.stage_plan(frames, audio, True)["encode"] == GENERATED


def test_the_replay_is_not_part_of_the_cascade() -> None:
    """Because re-exporting one is deterministic, so it changes nothing.

    A replay that went missing comes back byte-identical, and the frames
    rendered from it are still the right frames. Whether they really came
    from *this* replay is a hash comparison inside the frame and audio
    checks, which is stronger than cascading on "the replay was rebuilt"
    and does not cost a needless two-and-a-half-minute render.
    """
    import inspect

    parameters = list(inspect.signature(delivery.stage_plan).parameters)
    assert parameters == ["frames_valid", "audio_valid", "video_valid"]


def test_the_plan_only_ever_says_one_of_two_things() -> None:
    from itertools import product

    for flags in product((True, False), repeat=3):
        plan = delivery.stage_plan(*flags)
        assert set(plan) == {"frames", "audio", "encode"}
        assert set(plan.values()) <= {REUSED, GENERATED}


# --- delivery -------------------------------------------------------------


def test_a_new_deliverable_is_copied(tmp_path) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"video bytes")
    destination = tmp_path / "out" / "001_seed_5" / "short.mp4"
    assert delivery.deliver_file(str(source), str(destination), digest_of=digest_of) == (
        "copied"
    )
    assert destination.read_bytes() == b"video bytes"


def test_the_same_bytes_are_reused_rather_than_copied_again(tmp_path) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"video bytes")
    destination = tmp_path / "short_out.mp4"
    delivery.deliver_file(str(source), str(destination), digest_of=digest_of)
    before = destination.stat().st_mtime_ns
    assert delivery.deliver_file(str(source), str(destination), digest_of=digest_of) == (
        "reused"
    )
    assert destination.stat().st_mtime_ns == before


def test_different_bytes_are_refused_without_force(tmp_path) -> None:
    """The one failure mode with no way back: a delivered video changing."""
    source = tmp_path / "short.mp4"
    source.write_bytes(b"new video")
    destination = tmp_path / "short_out.mp4"
    destination.write_bytes(b"old video")

    with pytest.raises(delivery.DeliveryError) as error:
        delivery.deliver_file(str(source), str(destination), digest_of=digest_of)
    assert "--force" in str(error.value)
    assert destination.read_bytes() == b"old video"


def test_force_replaces_different_bytes(tmp_path) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"new video")
    destination = tmp_path / "short_out.mp4"
    destination.write_bytes(b"old video")
    assert delivery.deliver_file(
        str(source), str(destination), digest_of=digest_of, force=True
    ) == "replaced"
    assert destination.read_bytes() == b"new video"


def test_an_approved_video_says_so_when_it_refuses(tmp_path) -> None:
    """So the message tells you what you are about to overwrite."""
    source = tmp_path / "short.mp4"
    source.write_bytes(b"new video")
    destination = tmp_path / "short_out.mp4"
    destination.write_bytes(b"approved video")

    with pytest.raises(delivery.DeliveryError) as error:
        delivery.deliver_file(
            str(source), str(destination), digest_of=digest_of, protected=True
        )
    assert "approved" in str(error.value)
    assert destination.read_bytes() == b"approved video"


def test_an_approved_video_is_left_alone_when_it_has_not_changed(tmp_path) -> None:
    """Producing the batch again must not disturb reviewed content."""
    source = tmp_path / "short.mp4"
    source.write_bytes(b"same video")
    destination = tmp_path / "short_out.mp4"
    destination.write_bytes(b"same video")
    assert delivery.deliver_file(
        str(source), str(destination), digest_of=digest_of, protected=True
    ) == "reused"


def test_delivering_something_that_is_not_there_fails(tmp_path) -> None:
    with pytest.raises(delivery.DeliveryError):
        delivery.deliver_file(
            str(tmp_path / "missing.mp4"),
            str(tmp_path / "out.mp4"),
            digest_of=digest_of,
        )


# --- the production manifest ---------------------------------------------


def test_the_manifest_summarises_the_batch() -> None:
    items = [entry_for(record(index=index, seed=100 + index)) for index in (1, 2, 3)]
    manifest = delivery.production_manifest(
        "audit10", "output/batch_audit10/manifest.json", items
    )
    assert manifest["version"] == delivery.PRODUCTION_VERSION == 1
    assert manifest["qc_version"] == qc.QC_VERSION
    assert manifest["batch_id"] == "audit10"
    assert manifest["source_manifest"] == "output/batch_audit10/manifest.json"
    assert manifest["summary"]["items"] == 3
    assert manifest["summary"]["automated_pass"] == 3
    assert manifest["summary"]["automated_fail"] == 0
    assert manifest["summary"]["review"] == {
        "pending": 3,
        "approved": 0,
        "rejected": 0,
    }


def test_the_manifest_items_are_in_batch_order() -> None:
    items = [entry_for(record(index=index)) for index in (3, 1, 2)]
    manifest = delivery.production_manifest("b", "m.json", items)
    assert [entry["index"] for entry in manifest["items"]] == [1, 2, 3]


def test_the_manifest_records_only_relative_paths() -> None:
    manifest = delivery.production_manifest(
        "b", "output/b/manifest.json", [entry_for(record())]
    )
    text = json.dumps(manifest)
    assert ":\\" not in text and ":/" not in text
    for entry in manifest["items"]:
        assert not os.path.isabs(entry["video"])
        assert not os.path.isabs(entry["qc"])
        assert entry["video"].endswith("/short.mp4")
        assert entry["qc"].endswith("/qc.json")


def test_the_manifest_holds_nothing_that_could_vary() -> None:
    manifest = delivery.production_manifest("b", "m.json", [entry_for(record())])
    text = json.dumps(manifest).lower()
    for forbidden in ("timestamp", "created", "hostname", "machine", "uuid", "elapsed"):
        assert forbidden not in text


def test_the_manifest_is_byte_identical_between_runs() -> None:
    items = [entry_for(record(index=index)) for index in (1, 2)]
    dumps = [
        json.dumps(
            delivery.production_manifest("b", "m.json", items), indent=2, sort_keys=True
        )
        for _ in range(2)
    ]
    assert dumps[0] == dumps[1]


def test_an_item_carries_its_video_hash_and_size() -> None:
    entry = entry_for(record(size=1234))
    assert entry["video_sha256"] == "d" * 64
    assert entry["video_bytes"] == 1234


def test_a_failing_item_is_counted_and_its_reasons_kept() -> None:
    items = [
        entry_for(record(index=1)),
        entry_for(record(index=2, status=qc.STATUS_FAIL, problems=("replay is missing",))),
    ]
    manifest = delivery.production_manifest("b", "m.json", items)
    assert manifest["summary"]["automated_pass"] == 1
    assert manifest["summary"]["automated_fail"] == 1
    assert manifest["items"][1]["problems"] == ["replay is missing"]


# --- the summary ----------------------------------------------------------


def test_the_summary_reports_the_spread_of_every_measurement() -> None:
    items = [
        entry_for(record(index=1, score=90.0, duration=16.0, lufs=-20.5, size=100)),
        entry_for(record(index=2, score=94.0, duration=24.0, lufs=-19.5, size=300)),
    ]
    summary = delivery.summarise(items)
    assert summary["score"] == {"min": 90.0, "mean": 92.0, "max": 94.0}
    assert summary["duration"] == {
        "min": 16.0,
        "mean": 20.0,
        "max": 24.0,
        "total": 40.0,
    }
    assert summary["integrated_lufs"] == {"min": -20.5, "mean": -20.0, "max": -19.5}
    assert summary["video_bytes"] == {"total": 400, "mean": 200}


def test_the_summary_counts_reviews_and_warnings() -> None:
    items = [
        entry_for(record(index=1, review=qc.REVIEW_APPROVED)),
        entry_for(record(index=2, review=qc.REVIEW_REJECTED, note="dull")),
        entry_for(record(index=3, warnings=("loudness outside band",))),
    ]
    summary = delivery.summarise(items)
    assert summary["review"] == {"approved": 1, "rejected": 1, "pending": 1}
    assert summary["warnings"] == 1


def test_an_empty_batch_summarises_without_dividing_by_zero() -> None:
    summary = delivery.summarise([])
    assert summary["items"] == 0
    assert summary["score"]["mean"] is None
    assert summary["video_bytes"] == {"total": 0, "mean": 0}


def test_a_measurement_that_is_missing_is_left_out_rather_than_counted() -> None:
    items = [
        entry_for(record(index=1, lufs=-20.0)),
        entry_for(record(index=2, lufs=None)),
    ]
    assert delivery.summarise(items)["integrated_lufs"]["mean"] == -20.0


# --- review persistence --------------------------------------------------


def test_review_answers_land_on_the_manifest_and_the_summary() -> None:
    items = [entry_for(record(index=index)) for index in (1, 2, 3)]
    manifest = delivery.production_manifest("b", "m.json", items)
    changed = delivery.apply_review(
        manifest,
        {
            1: (qc.REVIEW_APPROVED, ""),
            2: (qc.REVIEW_REJECTED, "battle feels repetitive"),
        },
    )
    assert len(changed) == 2
    assert "001 pending -> approved" in changed[0]
    assert "repetitive" in changed[1]

    by_index = {entry["index"]: entry for entry in manifest["items"]}
    assert by_index[1]["review_status"] == qc.REVIEW_APPROVED
    assert by_index[2]["review_status"] == qc.REVIEW_REJECTED
    assert by_index[2]["review_note"] == "battle feels repetitive"
    assert by_index[3]["review_status"] == qc.REVIEW_PENDING
    assert manifest["summary"]["review"] == {
        "approved": 1,
        "rejected": 1,
        "pending": 1,
    }


def test_reviewing_an_item_that_is_not_in_the_batch_fails() -> None:
    manifest = delivery.production_manifest("b", "m.json", [entry_for(record(index=1))])
    with pytest.raises(delivery.DeliveryError):
        delivery.apply_review(manifest, {9: (qc.REVIEW_APPROVED, "")})


def test_a_review_answer_survives_the_batch_being_produced_again(tmp_path) -> None:
    """The QC record beside the video is where the answer lives.

    Production rewrites the automated half every run and reads this back, so
    an approval is not undone by re-running the batch.
    """
    path = tmp_path / "001_seed_5" / "qc.json"
    base = record()
    delivery.write_json(
        str(path), qc.with_review(base, qc.REVIEW_APPROVED, "the good one")
    )

    reloaded = delivery.read_json(str(path))
    assert qc.review_of(reloaded) == (qc.REVIEW_APPROVED, "the good one")

    # A later production run rebuilds the record and carries the answer over.
    status, note = qc.review_of(reloaded)
    delivery.write_json(str(path), qc.with_review(record(size=999), status, note))
    assert qc.review_of(delivery.read_json(str(path))) == (
        qc.REVIEW_APPROVED,
        "the good one",
    )
    assert delivery.read_json(str(path))["video"]["bytes"] == 999


def test_a_missing_or_unreadable_record_reads_as_pending(tmp_path) -> None:
    assert delivery.read_json(str(tmp_path / "nothing.json")) is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert delivery.read_json(str(broken)) is None
    assert qc.review_of(delivery.read_json(str(broken))) == (qc.REVIEW_PENDING, "")

    listed = tmp_path / "listed.json"
    listed.write_text("[1, 2]", encoding="utf-8")
    assert delivery.read_json(str(listed)) is None


def test_written_json_is_stable_and_newline_terminated(tmp_path) -> None:
    path = tmp_path / "out.json"
    delivery.write_json(str(path), {"b": 1, "a": 2})
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    assert list(json.loads(raw)) == ["a", "b"]


# --- the contact sheet ---------------------------------------------------


def test_the_grid_stays_wide_enough_to_look_at() -> None:
    """Cells are 9:16, so growing sideways beats growing downwards."""
    assert contact_sheet.grid_shape(10) == (5, 2)
    assert contact_sheet.grid_shape(20) == (5, 4)
    assert contact_sheet.grid_shape(1) == (1, 1)
    assert contact_sheet.grid_shape(7) == (5, 2)
    for count in range(1, 41):
        columns, rows = contact_sheet.grid_shape(count)
        assert columns <= contact_sheet.MAX_COLUMNS
        assert columns * rows >= count


def test_an_empty_batch_draws_no_sheet() -> None:
    with pytest.raises(contact_sheet.ContactSheetError):
        contact_sheet.grid_shape(0)


def test_a_cell_says_which_item_it_is() -> None:
    assert contact_sheet.cell_label(1, 21465, "TITAN vs ORBIT", "pass") == (
        "001  seed 21465  TITAN vs ORBIT"
    )
    assert "[FAIL]" in contact_sheet.cell_label(2, 5, "RUSH vs ECHO", "fail")


def test_the_sheet_draws_with_frames_missing(tmp_path) -> None:
    """A sheet that shows which item could not be sampled beats no sheet."""
    path = tmp_path / "contact_sheet.png"
    cells = [
        (1, 21465, "TITAN vs ORBIT", "pass", ""),
        (2, 27740, "PULSE vs ORBIT", "fail", str(tmp_path / "nope.png")),
    ]
    contact_sheet.build_sheet(cells, str(path), thumb_width=36)
    assert path.is_file() and path.stat().st_size > 0
