"""Record the half of production QC that a machine cannot decide.

Automated QC answers whether a Short is the production format. It cannot
answer whether the battle is dull despite its score, whether the audio is
pleasant, or whether this is one worth publishing. Those need a person, and
this is how the person's answer gets written down::

    python tools/review_batch.py output/production_audit10 --list
    python tools/review_batch.py output/production_audit10 --approve 1 3 7
    python tools/review_batch.py output/production_audit10 --reject 4 --note "repetitive"
    python tools/review_batch.py output/production_audit10 --pending 4

Not a UI, and deliberately not clever. It edits the review fields of the QC
records in a delivery folder and rewrites the production manifest to match.
Everything else in those files stays exactly as production wrote it, and an
answer recorded here survives producing the batch again.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production import delivery, qc  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_manifest(path: str) -> str:
    """The production manifest, given either it or the folder holding it."""
    if os.path.isfile(path):
        return path
    candidate = os.path.join(path, delivery.PRODUCTION_MANIFEST_NAME)
    if os.path.isfile(candidate):
        return candidate
    raise delivery.DeliveryError(
        f"no {delivery.PRODUCTION_MANIFEST_NAME} at {path}."
        " Produce the batch first with tools/produce_batch.py."
    )


def show(manifest: dict) -> None:
    summary = manifest["summary"]
    review = summary["review"]
    print(f"batch {manifest['batch_id']}  -  {summary['items']} items")
    print(
        f"automated: {summary['automated_pass']} pass, {summary['automated_fail']} fail"
        f"   review: {review['approved']} approved,"
        f" {review['pending']} pending, {review['rejected']} rejected\n"
    )
    print(
        f"{'idx':>4s} {'seed':>7s} {'matchup':22s} {'score':>7s}"
        f" {'auto':>5s} {'review':>9s}  note"
    )
    for entry in manifest["items"]:
        print(
            f"{entry.get('index', 0):4d} {entry.get('seed', 0):7d}"
            f" {str(entry.get('label', '')):22s} {entry.get('score', 0):7.2f}"
            f" {str(entry.get('automated_status', '')):>5s}"
            f" {str(entry.get('review_status', '')):>9s}"
            f"  {entry.get('review_note', '')}"
        )


def decisions_from(args: argparse.Namespace) -> dict[int, tuple[str, str]]:
    """Which items are being set to what, with the note if one was given.

    An index named twice in one command is a mistake worth refusing rather
    than resolving by argument order.
    """
    note = args.note or ""
    chosen: dict[int, tuple[str, str]] = {}
    for indices, status in (
        (args.approve, qc.REVIEW_APPROVED),
        (args.reject, qc.REVIEW_REJECTED),
        (args.pending, qc.REVIEW_PENDING),
    ):
        for index in indices or ():
            if index in chosen and chosen[index][0] != status:
                raise delivery.DeliveryError(
                    f"item {index} was given two different review statuses"
                )
            chosen[index] = (status, note)
    return chosen


def write_item_review(
    production_dir: str, entry: dict, status: str, note: str
) -> None:
    """Put the answer in the item's own QC record, beside its video.

    The QC record is the source of truth: producing the batch again reads it
    back and carries the answer forward, so there is no second place for
    review state to live and nothing to keep in step.
    """
    relative = entry.get("qc")
    if not relative:
        raise delivery.DeliveryError(f"item {entry.get('index')} has no QC record")
    path = os.path.join(production_dir, relative)
    record = delivery.read_json(path)
    if record is None:
        raise delivery.DeliveryError(f"cannot read {relative}")
    delivery.write_json(path, qc.with_review(_without_review(record), status, note))


def _without_review(record: dict) -> dict:
    """The record's automated half, which review must not touch."""
    return {
        key: value
        for key, value in record.items()
        if key not in ("review_status", "review_note")
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="record human review decisions on a produced batch"
    )
    parser.add_argument("path", help="delivery folder, or its production manifest")
    parser.add_argument("--list", action="store_true", help="show the batch and stop")
    parser.add_argument("--approve", type=int, nargs="+", help="item indices to approve")
    parser.add_argument("--reject", type=int, nargs="+", help="item indices to reject")
    parser.add_argument(
        "--pending", type=int, nargs="+", help="item indices to put back to pending"
    )
    parser.add_argument("--note", default=None, help="a plain-text reason, free form")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest_path = find_manifest(args.path)
        manifest = delivery.read_json(manifest_path)
        if manifest is None:
            raise delivery.DeliveryError(f"cannot read {manifest_path}")
        production_dir = os.path.dirname(os.path.abspath(manifest_path))

        decisions = decisions_from(args)
        if args.list or not decisions:
            show(manifest)
            if not decisions:
                print("\nnothing to change; pass --approve, --reject or --pending")
            return 0

        by_index = {entry.get("index"): entry for entry in manifest.get("items", [])}
        for index in sorted(decisions):
            entry = by_index.get(index)
            if entry is None:
                raise delivery.DeliveryError(f"no item {index} in this batch")
            write_item_review(production_dir, entry, *decisions[index])

        for line in delivery.apply_review(manifest, decisions):
            print(line)
        delivery.write_json(manifest_path, manifest)
        print(f"\nupdated {delivery.relative_to(manifest_path, PROJECT_ROOT)}")
    except (delivery.DeliveryError, qc.QcError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
