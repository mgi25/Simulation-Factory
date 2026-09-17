"""The command line. One verb writes, and only when told to twice.

`metrics` prints the metric definitions, which is the answer to "what does
retention mean here". `windows` prints the standard observation windows.
`report` renders the CEO page from a state directory, `check` reports integrity
problems in one, and `studio-inspect` says what a Studio export is without
importing it. All of those read and none of them writes.

`studio-import` is the exception, and it is deliberately hard to trigger by
accident: a dry run is what it does by default, `--commit` is what makes it
write, and `--commit` without `--state-dir` is an error rather than a guess at
where state lives. What it writes is observations off a file the caller has
already downloaded and vouched for. It fetches nothing; there is no network call
anywhere under this module.

Output is counts and references. A summary never prints a reading, because
private channel analytics on a terminal is private channel analytics in a
scrollback buffer. A row-level error quotes the single cell that failed, which
is the smallest thing that lets somebody fix it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from knowledge.company_os.records import Evidence

from .common import DataSource, Provenance
from .errors import AnalyticsError
from .integrity import CONSTRUCTION_ENFORCED, check_integrity
from .metrics import DEFAULT_REGISTRY
from .report import build_report
from .store import AnalyticsStore
from .studio_ingest import commit_ingestion, describe_export, ingest_studio_export
from .studio_mapping import load_video_mapping
from .studio_schema import TemporalSemantics
from .studio_source import offset_minutes
from .studio_values import number_format
from .windows import STANDARD_AGE_WINDOWS, DateRange


def _metrics(args: argparse.Namespace) -> int:
    names = DEFAULT_REGISTRY.names()
    print(f"{len(names)} metric definition(s)")
    for name in names:
        definition = DEFAULT_REGISTRY.get(name)
        access = "private" if definition.private else "public"
        print(f"\n  {definition.name}  [{definition.kind.value}, {access}]")
        print(f"    unit: {definition.unit}")
        if definition.denominator:
            print(f"    per:  {definition.denominator}")
        if args.verbose:
            print(f"    {definition.definition}")
    if not args.verbose:
        print("\n(--verbose for the full definition of each)")
    return 0


def _windows(_args: argparse.Namespace) -> int:
    print(f"{len(STANDARD_AGE_WINDOWS)} standard observation window(s)")
    for window in STANDARD_AGE_WINDOWS:
        print(f"  {window}")
    print(
        "\nWindows are half-open: a reading at hour 24 belongs to the next window, "
        "not to first_24h, so no reading is counted twice."
    )
    return 0


def _rules(_args: argparse.Namespace) -> int:
    print("Refused at construction:")
    for description, exception in CONSTRUCTION_ENFORCED:
        print(f"  {description:<52} {exception.__name__}")
    return 0


def _report(args: argparse.Namespace) -> int:
    store = AnalyticsStore(args.state_dir)
    problems = check_integrity(store) if args.verbose else ()
    print(build_report(store, args.as_of or dt.date.today(), integrity_problems=problems).render())
    return 0


def _check(args: argparse.Namespace) -> int:
    problems = check_integrity(AnalyticsStore(args.state_dir))
    if not problems:
        print("no integrity problems")
        return 0
    print(f"{len(problems)} integrity problem(s)")
    for problem in problems:
        print(f"  {problem}")
    return 1


def _studio_inspect(args: argparse.Namespace) -> int:
    print(describe_export(args.export).render())
    return 0


def _date_range(text: str) -> DateRange:
    start, _, end = text.partition("..")
    if not end:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a date range; write it as YYYY-MM-DD..YYYY-MM-DD"
        )
    try:
        return DateRange(dt.date.fromisoformat(start), dt.date.fromisoformat(end))
    except (ValueError, AnalyticsError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _studio_import(args: argparse.Namespace) -> int:
    store = AnalyticsStore(args.state_dir) if args.state_dir else None
    if args.commit and store is None:
        print("--commit needs --state-dir: there is nowhere to append to.")
        return 2
    result = ingest_studio_export(
        args.export,
        source_id=args.source_id,
        provenance=Provenance(
            source=DataSource.OWN_STUDIO_EXPORT,
            retrieved_by=args.retrieved_by,
            evidence=(Evidence(kind="document", ref=args.export, note="studio export"),),
        ),
        channel_ref=args.channel_ref,
        mapping=load_video_mapping(args.mapping),
        exported_at=args.exported_at,
        imported_at=dt.datetime.now(dt.timezone.utc),
        deliverables=store.list("deliverable") if store else (),
        semantics=TemporalSemantics(args.semantics) if args.semantics else None,
        reported_range=args.range,
        reporting_offset_minutes=(
            offset_minutes(args.timezone) if args.timezone else None
        ),
        number_format=number_format(args.number_format),
    )
    print(result.render())
    if not args.commit:
        print(
            "\ndry run: nothing was written. Re-run with --commit and a --state-dir "
            "to append these observations."
        )
        return 1 if result.errors else 0
    print("\n" + commit_ingestion(result, store).render())
    return 1 if result.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m company.analytics",
        description="Views over analytics definitions and state, and the Studio import.",
    )
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("metrics", help="what each metric name means").set_defaults(func=_metrics)
    sub.add_parser("windows", help="the standard observation windows").set_defaults(func=_windows)
    sub.add_parser("rules", help="what is refused at construction").set_defaults(func=_rules)

    report = sub.add_parser("report", help="render the analytics report")
    report.add_argument("state_dir")
    report.add_argument("--as-of", type=dt.date.fromisoformat, dest="as_of")
    report.set_defaults(func=_report)

    check = sub.add_parser("check", help="cross-record integrity of a state directory")
    check.add_argument("state_dir")
    check.set_defaults(func=_check)

    inspect = sub.add_parser(
        "studio-inspect",
        help="what a Studio CSV export is, and what importing it would require",
    )
    inspect.add_argument("export")
    inspect.set_defaults(func=_studio_inspect)

    imported = sub.add_parser(
        "studio-import",
        help="read a Studio CSV export of our own channel into observations",
    )
    imported.add_argument("export")
    imported.add_argument("--mapping", required=True, help="video id to deliverable id JSON")
    imported.add_argument(
        "--source-id", required=True, help="the id this import is recorded under"
    )
    imported.add_argument(
        "--channel-ref", required=True, help="which channel of ours this export is from"
    )
    imported.add_argument(
        "--exported-at",
        required=True,
        help="when the export was taken, as an ISO 8601 instant with an offset",
    )
    imported.add_argument(
        "--retrieved-by",
        default="youtube studio csv export, downloaded by hand",
        help="which pull produced the file",
    )
    imported.add_argument(
        "--semantics",
        choices=[item.value for item in TemporalSemantics],
        help="what a per-video table covers; a per-day report declares its own",
    )
    imported.add_argument(
        "--range",
        type=_date_range,
        help="YYYY-MM-DD..YYYY-MM-DD, required for an interval export",
    )
    imported.add_argument(
        "--timezone",
        help="the channel's reporting offset (+HH:MM or Z), for a per-day report",
    )
    imported.add_argument("--number-format", default="dot_decimal")
    imported.add_argument(
        "--state-dir", help="the analytics state directory to read and append to"
    )
    imported.add_argument(
        "--dry-run",
        action="store_true",
        help="the default: parse, validate and report, writing nothing",
    )
    imported.add_argument(
        "--commit",
        action="store_true",
        help="append the observations this import produced",
    )
    imported.set_defaults(func=_studio_import)

    args = parser.parse_args(argv)
    if getattr(args, "commit", False) and getattr(args, "dry_run", False):
        parser.error("--dry-run and --commit ask for opposite things")
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
