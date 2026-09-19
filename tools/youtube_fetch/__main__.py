"""The operator's four commands, and the last place a secret could escape.

## Four verbs, because there are four questions

`auth` is the one-time consent flow. `status` answers "is this machine set up?"
without touching the network, so a misconfigured host is diagnosed in a second
rather than through a failed fetch. `smoke-test` answers "does the stored grant
still work?" with the single cheapest authenticated call there is, and writes
nothing. `fetch` does the real pull and writes the artifact.

Keeping `status` network-free and `smoke-test` write-free is what makes them
usable while something is wrong: neither can make the situation worse, so an
operator can run both without thinking about it.

## The top-level handler redacts, then prints

Every exception this package raises has already been redacted where it was
raised. The handler here redacts again, seeded from the environment, because the
one thing a CLI reliably does is end up in a terminal recording, a CI log or a
screenshot pasted into a chat. A second pass over text that is already clean
costs nothing; a first pass that was skipped costs a credential.

`YouTubeFetchError` becomes a one-line message and exit code 2. A traceback is
not shown, because a traceback holds local variables in its frames and the
locals of this package are the client secret and a bearer token.

## The stack is injectable

`main` takes a `stack_factory`, which is how the tests exercise the commands
without a network or a credential. It is also why the command bodies stay short:
everything interesting is in the modules they call, and the ones that matter for
correctness - pagination, the 401 retry, the scope check, the sanitizer - are
tested directly rather than through `argparse`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .api import YouTubeReader
from .artifact import FetchRequest, fetch_artifact, write_artifact
from .config import OAuthConfig, configuration_status
from .errors import ConfigurationError, YouTubeFetchError
from .oauth import OAuthClient, TokenStore
from .secrets_ import SecretRedactor
from .transport import InstrumentedTransport, UrllibTransport


EXIT_OK = 0
EXIT_NOT_READY = 1
EXIT_FAILED = 2


@dataclass
class Stack:
    """The four objects every authenticated command needs, built once."""

    config: OAuthConfig
    transport: InstrumentedTransport
    oauth: OAuthClient
    reader: YouTubeReader


def build_stack(environment: Mapping[str, str] | None = None) -> Stack:
    config = OAuthConfig.from_environment(environment)
    transport = InstrumentedTransport(UrllibTransport())
    oauth = OAuthClient(config, transport, TokenStore(config.token_path))
    return Stack(config, transport, oauth, YouTubeReader(oauth, transport))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.youtube_fetch",
        description=(
            "Fetch read-only YouTube channel, video and analytics evidence into a "
            "sanitized artifact file. Company OS ingests the file; it never fetches."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    auth = commands.add_parser("auth", help="run the one-time Google authorization")
    auth.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authorization URL instead of opening a browser",
    )
    auth.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="seconds to wait for the loopback callback (default: 180)",
    )

    commands.add_parser("status", help="report configuration readiness without any network call")

    commands.add_parser("smoke-test", help="make one authenticated call and write nothing")

    fetch = commands.add_parser("fetch", help="pull evidence and write the artifact")
    fetch.add_argument("--out", required=True, help="path of the artifact file to write")
    fetch.add_argument(
        "--videos", type=int, default=10, help="how many recent uploads to retrieve"
    )
    fetch.add_argument(
        "--days",
        type=int,
        default=28,
        help="length of the analytics interval, ending at --end-date",
    )
    fetch.add_argument(
        "--end-date",
        type=_date,
        default=None,
        help="last day of the interval (default: yesterday, UTC)",
    )
    fetch.add_argument(
        "--video-analytics",
        action="store_true",
        help="also query one analytics report per retrieved video",
    )
    fetch.add_argument(
        "--include-raw",
        action="store_true",
        help="include the provider responses under `raw`",
    )
    fetch.add_argument(
        "--require-complete",
        action="store_true",
        help="write nothing unless every requested video came back",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    out: Callable[[str], None] = print,
    stack_factory: Callable[[], Stack] | None = None,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    redactor = _environment_redactor(environment)
    factory = stack_factory or (lambda: build_stack(environment))
    # `status` is the one command that answers without a credential or a socket,
    # so it is dispatched before anything tries to build an authenticated stack.
    authenticated: dict[str, Callable[[argparse.Namespace, Stack, Callable[[str], None]], int]] = {
        "auth": _auth,
        "smoke-test": _smoke_test,
        "fetch": _fetch,
    }
    try:
        if args.command == "status":
            return _status(args, environment, out)
        return authenticated[args.command](args, factory(), out)
    except YouTubeFetchError as exc:
        out("error: " + redactor.redact(exc))
        return EXIT_FAILED


def _auth(args: argparse.Namespace, stack: Stack, out: Callable[[str], None]) -> int:
    out("Starting the one-time Google authorization for read-only access.")
    out("Scopes requested: " + ", ".join(stack.config.scopes))
    token = stack.oauth.authorize_interactively(
        open_browser=not args.no_browser, timeout=args.timeout, announce=out
    )
    out("Authorization stored: YES")
    out(f"Token location: {stack.config.token_path}")
    out("Granted scopes: " + ", ".join(token.scopes))
    return EXIT_OK


def _status(
    _args: argparse.Namespace,
    environment: Mapping[str, str] | None,
    out: Callable[[str], None],
) -> int:
    status = configuration_status(environment)
    out(f"OAuth client configured: {_yes(status['oauth_client_configured'])}")
    out(f"Refresh token available: {_yes(status['refresh_token_available'])}")
    out("Requested scopes: " + ", ".join(status["requested_scopes"]))
    out(f"Token location: {status['token_path']}")
    ready = bool(status["oauth_client_configured"]) and bool(status["refresh_token_available"])
    if not ready:
        out("Ready to fetch: NO (run `auth` after setting the client environment)")
    return EXIT_OK if ready else EXIT_NOT_READY


def _smoke_test(
    _args: argparse.Namespace, stack: Stack, out: Callable[[str], None]
) -> int:
    channel = stack.reader.channel()
    out("Channel access: YES")
    out(f"Channel: {channel.facts.channel_title}")
    out(f"Channel ID: {channel.facts.channel_id}")
    out("Granted scopes: " + ", ".join(stack.oauth.granted_scopes()))
    out(f"API calls made: {len(stack.transport.traces)}")
    return EXIT_OK


def _fetch(args: argparse.Namespace, stack: Stack, out: Callable[[str], None]) -> int:
    end = args.end_date or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    if args.days < 1:
        raise ConfigurationError("--days must be at least 1")
    request = FetchRequest(
        start_date=end - dt.timedelta(days=args.days - 1),
        end_date=end,
        video_limit=args.videos,
        video_analytics=args.video_analytics,
        include_raw=args.include_raw,
    )
    payload = fetch_artifact(stack.reader, request)
    retrieval = payload["video_retrieval"]
    if args.require_complete and not retrieval["complete"]:
        # The operator asked for an all-or-nothing pull, so the gap is a failure
        # and nothing is written. Without the flag the gap is written down.
        raise YouTubeFetchError(
            "the pull was incomplete and --require-complete was given, so no artifact "
            "was written: " + "; ".join(retrieval["notes"])
        )
    destination = write_artifact(
        payload, args.out, secret_values=stack.oauth.secret_values()
    )
    out(f"Artifact written: {destination}")
    out(f"Channel: {payload['channel']['channel_title']}")
    out(f"Videos: {retrieval['returned']} of {retrieval['requested']} requested")
    out(f"Analytics reports: {len(payload['analytics'])}")
    out(f"Interval: {request.start_date.isoformat()} to {request.end_date.isoformat()}")
    out(f"Complete: {_yes(retrieval['complete'])}")
    for note in retrieval["notes"]:
        out(f"  note: {note}")
    return EXIT_OK


def _environment_redactor(environment: Mapping[str, str] | None) -> SecretRedactor:
    env = os.environ if environment is None else environment
    return SecretRedactor(env.get("YOUTUBE_CLIENT_SECRET"))


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("dates must be written as YYYY-MM-DD") from None


def _yes(value: Any) -> str:
    return "YES" if value else "NO"


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
