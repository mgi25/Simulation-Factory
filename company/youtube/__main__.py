"""The command line. Two verbs, one of which writes, and neither of which fetches.

`inspect` says what an artifact is and what importing it would require, without
importing it and without printing a single reading. `ingest` reads the same file
into observations; it is a dry run by default, `--commit` is what makes it
write, and `--commit` without `--state-dir` is an error rather than a guess at
where state lives.

There is no `auth` command, no `status` that opens a socket, and no smoke test.
Authorizing this company against Google and pulling from the APIs happens in
`tools/youtube_fetch`, which is a production tool holding credentials; this
module is Company OS, imports no network library, and cannot reach the internet
even if somebody asked it to. The seam between them is a file on disk, which is
also what makes an import reviewable: the artifact can be read before it is
believed.

Output is counts and references. A summary never prints a reading, because
private channel analytics on a terminal is private channel analytics in a
scrollback buffer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from company.analytics import AnalyticsError, AnalyticsStore

from .artifact import read_artifact
from .errors import ArtifactRejected
from .ingest import (
    commit_ingestion,
    describe_artifact,
    ingest_artifact,
    load_assignments,
)
from .store import YouTubeEvidenceStore


def _inspect(args: argparse.Namespace) -> int:
    description = describe_artifact(read_artifact(args.artifact))
    if args.json:
        print(json.dumps(description.to_dict(), sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    print(description.render())
    return 0


def _ingest(args: argparse.Namespace) -> int:
    if args.commit and not args.state_dir:
        print("--commit needs --state-dir: there is nowhere to append to.")
        return 2
    artifact = read_artifact(args.artifact)
    result = ingest_artifact(
        artifact, assignments=load_assignments(_read_json(args.assignments))
    )
    print(result.render())
    if not args.commit:
        print(
            "\ndry run: nothing was written. Re-run with --commit and a --state-dir "
            "to append these observations."
        )
        return 1 if result.errors else 0

    store = AnalyticsStore(args.state_dir)
    outcome = commit_ingestion(result, store)
    print("\n" + outcome.render())
    if args.keep_evidence:
        pointer = YouTubeEvidenceStore(args.state_dir).append(
            artifact, ingested_from=str(args.artifact)
        )
        print(f"  evidence     {pointer.record_ref} ({pointer.evidence_id})")
    return 1 if result.errors else 0


def _read_json(path: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArtifactRejected(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise ArtifactRejected(f"{path} is not valid JSON: {exc}") from exc


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m company.youtube",
        description=(
            "Read a sanitized YouTube API artifact into the analytics ledger. "
            "Fetching happens in tools/youtube_fetch; nothing here touches a network."
        ),
    )
    sub = root.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser(
        "inspect",
        help="what an artifact is, and what importing it would require",
    )
    inspect.add_argument("artifact", help="the artifact file written by the fetcher")
    inspect.add_argument(
        "--json", action="store_true", help="print the description as JSON"
    )
    inspect.set_defaults(func=_inspect)

    ingest = sub.add_parser(
        "ingest",
        help="read an artifact of our own channel into observations",
    )
    ingest.add_argument("artifact", help="the artifact file written by the fetcher")
    ingest.add_argument(
        "--assignments",
        required=True,
        help="JSON: video id to {deliverable_id, kind, format_id}",
    )
    ingest.add_argument(
        "--state-dir", help="the analytics state directory to read and append to"
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        help="the default: parse, validate and report, writing nothing",
    )
    ingest.add_argument(
        "--commit",
        action="store_true",
        help="append the observations this import produced",
    )
    ingest.add_argument(
        "--keep-evidence",
        action="store_true",
        help="also append the whole artifact to the evidence store under --state-dir",
    )
    ingest.set_defaults(func=_ingest)
    return root


def main(argv: list[str] | None = None) -> int:
    root = parser()
    args = root.parse_args(argv)
    if getattr(args, "commit", False) and getattr(args, "dry_run", False):
        root.error("--dry-run and --commit ask for opposite things")
    try:
        return int(args.func(args))
    except AnalyticsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
