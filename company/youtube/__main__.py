"""Operator CLI for read-only YouTube authorization and evidence retrieval."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from ai_platform.serde import to_jsonable
from company.analytics import AnalyticsStore, DeliverableKind

from .bridge import build_deliverable, commit_analytics
from .client import YouTubeClient
from .config import OAuthConfig, configuration_status
from .errors import ConfigurationError, YouTubeConnectorError
from .models import AnalyticsEvidence, VideoEvidence
from .oauth import OAuthClient, TokenStore
from .security import SecretRedactor
from .store import YouTubeEvidenceStore
from .transport import InstrumentedTransport, UrllibTransport


def _stack(*, include_monetary: bool = False) -> tuple[OAuthConfig, OAuthClient, YouTubeClient]:
    config = OAuthConfig.from_environment(include_monetary=include_monetary)
    transport = InstrumentedTransport(UrllibTransport())
    oauth = OAuthClient(config, transport, TokenStore(config.token_path))
    return config, oauth, YouTubeClient(oauth, transport)


def _auth(args: argparse.Namespace) -> int:
    config, oauth, _client = _stack(include_monetary=args.include_monetary_scope)
    print("Starting one-time Google authorization.")
    if args.no_browser:
        print("Open this URL in a browser:")
    token = oauth.authorize_interactively(
        open_browser=not args.no_browser, timeout=args.timeout
    )
    print("Authorization stored: YES")
    print(f"Token location: {config.token_path}")
    print("Granted scopes: " + ", ".join(token.scopes))
    return 0


def _status(_args: argparse.Namespace) -> int:
    status = configuration_status()
    print(f"OAuth client configured: {_yes(status['oauth_client_configured'])}")
    print(f"Refresh token available: {_yes(status['refresh_token_available'])}")
    if not status["oauth_client_configured"] or not status["refresh_token_available"]:
        print("Channel access: NO")
        return 1
    _config, _oauth, client = _stack()
    try:
        result = client.channel()
    except YouTubeConnectorError as exc:
        print("Channel access: NO")
        print(f"Reason: {exc}")
        return 1
    channel = result.normalized
    print("Channel access: YES")
    print(f"Channel: {channel.channel_title}")
    print(f"Channel ID: {channel.channel_id}")
    return 0


def _channel(args: argparse.Namespace) -> int:
    _config, _oauth, client = _stack()
    return _emit(client.channel(), args)


def _videos(args: argparse.Namespace) -> int:
    _config, _oauth, client = _stack()
    return _emit(client.recent_videos(args.limit), args)


def _analytics(args: argparse.Namespace) -> int:
    end = args.end_date or (dt.date.today() - dt.timedelta(days=1))
    start = end - dt.timedelta(days=args.days - 1)
    _config, _oauth, client = _stack()
    result = client.analytics(start, end, video_id=args.video_id)
    pointer = _persist(result, args.state_dir)
    commit = None
    if args.commit_analytics:
        if not args.state_dir:
            raise ConfigurationError("--commit-analytics requires --state-dir")
        if not args.video_id:
            raise ConfigurationError("--commit-analytics requires --video-id")
        if not args.deliverable_id or not args.kind or not args.format_id:
            raise ConfigurationError(
                "--commit-analytics requires --deliverable-id, --kind, and --format-id"
            )
        video_result = client.video(args.video_id)
        video = video_result.normalized[0]
        if not isinstance(video, VideoEvidence):  # pragma: no cover - type guard
            raise ConfigurationError("video identity could not be normalized")
        report = result.normalized
        if not isinstance(report, AnalyticsEvidence):  # pragma: no cover
            raise ConfigurationError("analytics could not be normalized")
        evidence_ref = pointer.record_ref if pointer else "youtube-api:unpersisted"
        deliverable = build_deliverable(
            video,
            deliverable_id=args.deliverable_id,
            kind=DeliverableKind(args.kind),
            format_id=args.format_id,
        )
        commit = commit_analytics(
            AnalyticsStore(args.state_dir),
            report,
            video,
            deliverable,
            evidence_ref=evidence_ref,
        )
    output = result.to_dict(include_raw=args.include_raw)
    if pointer:
        output["evidence_record"] = to_jsonable(pointer)
    if commit:
        output["analytics_commit"] = to_jsonable(commit)
    print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


def _smoke(_args: argparse.Namespace) -> int:
    end = dt.date.today() - dt.timedelta(days=1)
    _config, _oauth, client = _stack()
    channel = client.channel().normalized
    client.recent_videos(1)
    client.analytics(end - dt.timedelta(days=6), end)
    print("Live read-only smoke test: PASS")
    print(f"Channel: {channel.channel_title}")
    return 0


def _emit(result, args: argparse.Namespace) -> int:
    pointer = _persist(result, args.state_dir)
    output = result.to_dict(include_raw=args.include_raw)
    if pointer:
        output["evidence_record"] = to_jsonable(pointer)
    print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


def _persist(result, state_dir: str | None):
    return YouTubeEvidenceStore(state_dir).append(result) if state_dir else None


def _yes(value: object) -> str:
    return "YES" if value else "NO"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m company.youtube",
        description="Authorize and retrieve read-only YouTube evidence.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="perform one-time OAuth authorization")
    auth.add_argument("--no-browser", action="store_true", help="print instead of opening the authorization URL")
    auth.add_argument("--timeout", type=float, default=180.0)
    auth.add_argument(
        "--include-monetary-scope",
        action="store_true",
        help="also request read-only monetary analytics (disabled by default)",
    )
    auth.set_defaults(func=_auth)

    sub.add_parser("status", help="check configuration, grant, and channel access").set_defaults(func=_status)

    channel = sub.add_parser("channel", help="retrieve the authenticated channel")
    _evidence_options(channel)
    channel.set_defaults(func=_channel)

    videos = sub.add_parser("videos", help="retrieve recent uploaded videos")
    videos.add_argument("--limit", type=int, default=10)
    _evidence_options(videos)
    videos.set_defaults(func=_videos)

    analytics = sub.add_parser("analytics", help="retrieve analytics for an inclusive date range")
    analytics.add_argument("--days", type=_positive_days, default=28)
    analytics.add_argument("--end-date", type=dt.date.fromisoformat)
    analytics.add_argument("--video-id")
    analytics.add_argument("--commit-analytics", action="store_true")
    analytics.add_argument("--deliverable-id")
    analytics.add_argument("--kind", choices=("video", "short"))
    analytics.add_argument("--format-id")
    _evidence_options(analytics)
    analytics.set_defaults(func=_analytics)

    sub.add_parser("smoke-test", help="explicit live read-only channel/API check").set_defaults(func=_smoke)
    return root


def _evidence_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--state-dir",
        default=os.environ.get("COMPANY_OS_STATE_DIR"),
        help="append raw and normalized evidence under this Company OS state directory",
    )
    command.add_argument("--include-raw", action="store_true", help="also print the provider response")


def _positive_days(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("days must be positive")
    return number


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.func(args))
    except (YouTubeConnectorError, ValueError) as exc:
        configured = []
        for name in ("YOUTUBE_CLIENT_SECRET", "YOUTUBE_CLIENT_ID"):
            configured.append(os.environ.get(name))
        print("error: " + SecretRedactor(*configured).redact(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
