"""Turning a link somebody copied into an identity we can deduplicate on.

The same video reaches a researcher as `youtu.be/ID`, as
`www.youtube.com/watch?v=ID&t=42s`, as `youtube.com/shorts/ID`, and as whatever
a share sheet appended to it that week. Four strings, one video. A discovery
queue that treats them as four candidates pays for the same analysis four
times, which is the expense this phase exists to avoid.

So every URL entering the system is reduced to a `CanonicalUrl`: one platform,
one external id, one canonical URL, and the *original* string kept beside it
untouched. Identity is `platform + external_id` when the platform has a stable
id and `platform + canonical_url` when it does not - never the title, because
two different videos share one every week.

## Nothing here opens the URL

There is no resolution step. An id that is not already present in the link
cannot be recovered, and that is why an unrecognised form is *refused* rather
than guessed at: a guessed id merges two different videos into one candidate,
and every later stage then inherits the merge. `parse_url` is string work, and
it is deliberately not `urllib.parse` - the package forbids the `urllib` root
outright in `tests/test_company_os_research.py`, and the twenty lines below are
the narrower thing actually needed.

## The adapter boundary

A platform contributes one `PlatformAdapter`: the hosts it answers for, and a
function from a parsed URL to a canonical one. `register_adapter` is how a
second platform arrives - not a branch inside `canonicalize`. YouTube ships;
every other host raises an error naming the platforms that do exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from intelligence.research.common import assert_slug
from intelligence.research.errors import ResearchError

MAX_URL_CHARS = 200
"""The reference budget from `ai_platform/references.py`. A longer string is
not a link somebody copied; it is content that arrived in the wrong field."""

# A conservative URL alphabet: RFC 3986 unreserved, reserved and percent
# characters and nothing else. Whitespace, quotes, backslashes and control
# characters are absent, which is what makes a pasted sentence fail here rather
# than three functions later.
_URL_ALPHABET = re.compile(r"^[A-Za-z0-9._~:/?#@!$&'()*+,;=%\[\]-]+$")
_SCHEME = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<rest>.*)$")
_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
"""A YouTube video id is exactly eleven characters of base64url.

Held exactly, not loosely: the `v=` parameter also carries playlist ids,
channel ids and, on a malformed share link, an empty string. Eleven characters
of that alphabet is the one shape that is a video; anything else is refused by
name rather than stored as an identity nothing can be checked against."""


@dataclass(frozen=True)
class ParsedUrl:
    """The parts of a URL this package reads, and the string it came from."""

    scheme: str
    host: str
    port: str
    path: str
    query: tuple[tuple[str, str], ...]
    fragment: str
    original: str

    def param(self, name: str) -> str | None:
        """The first value for `name`, or None.

        First wins deliberately: `?v=a&v=b` is a malformed link, and taking the
        last would silently prefer whichever id was appended most recently.
        """
        for key, value in self.query:
            if key == name:
                return value
        return None

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(part for part in self.path.split("/") if part)


@dataclass(frozen=True)
class ContentIdentity:
    """What makes two links the same external thing.

    `basis` says which rule applied, because "deduplicated on a stable platform
    id" and "deduplicated on a URL that happened to match" carry very different
    amounts of confidence, and a queue that hides the difference will eventually
    merge two videos that only shared a redirect.
    """

    platform: str
    external_id: str = ""
    canonical_url: str = ""

    def __post_init__(self) -> None:
        assert_slug(self.platform, "identity platform")
        if not self.external_id and not self.canonical_url:
            raise ResearchError(
                "a content identity needs an external id or a canonical URL. With "
                "neither there is nothing to deduplicate on - and a title is not an "
                "identity, because two different videos share one every week."
            )

    @property
    def key(self) -> str:
        """The deduplication key. Stable, printable, and never a title."""
        if self.external_id:
            return f"{self.platform}:id:{self.external_id}"
        return f"{self.platform}:url:{self.canonical_url}"

    @property
    def basis(self) -> str:
        return "external_id" if self.external_id else "canonical_url"


@dataclass(frozen=True)
class CanonicalUrl:
    """One link, reduced - and the string the researcher actually pasted.

    `original` is never normalised away. It is the evidence that the record
    describes the link somebody looked at, and the only way to notice later
    that a share-sheet parameter mattered after all.
    """

    platform: str
    kind: str
    external_id: str
    url: str
    original: str
    form: str

    def __post_init__(self) -> None:
        assert_slug(self.platform, "canonical url platform")
        assert_slug(self.kind, "canonical url kind")
        assert_slug(self.form, "canonical url form")
        if not isinstance(self.url, str) or not self.url.strip():
            raise ResearchError("a canonical URL may not be empty")
        if not isinstance(self.original, str) or not self.original.strip():
            raise ResearchError("the original URL must be kept beside the canonical one")

    @property
    def identity(self) -> ContentIdentity:
        return ContentIdentity(
            platform=self.platform,
            external_id=self.external_id,
            canonical_url=self.url,
        )


class PlatformAdapter:
    """One platform's answer to what a link is, and what it is a link to.

    Subclass, set `platform` and `hosts`, implement `canonicalize`, and call
    `register_adapter`. The base class exists so that adding a second platform
    is adding a file, rather than adding a branch to a function every platform
    has to share.
    """

    platform: ClassVar[str] = ""
    hosts: ClassVar[frozenset[str]] = frozenset()

    def canonicalize(self, parsed: ParsedUrl) -> CanonicalUrl:
        raise NotImplementedError


# YouTube path forms carrying a video id in the segment after the verb. All
# four resolve to the same video as `watch?v=ID`, so all four reduce to it - a
# Short deduplicated apart from its own watch URL is the bug this table exists
# to prevent. The form is kept on the record; only the identity is collapsed.
_YOUTUBE_PATH_FORMS: dict[str, str] = {
    "shorts": "short",
    "embed": "embed",
    "live": "live",
    "v": "legacy_v",
}

# Real YouTube URLs that are not a video. Refused by name, so a researcher who
# pasted a channel is told they pasted a channel rather than "malformed URL".
_YOUTUBE_NOT_A_VIDEO: dict[str, str] = {
    "channel": "a channel",
    "c": "a channel",
    "user": "a channel",
    "playlist": "a playlist",
    "results": "a search results page",
    "feed": "a feed",
    "hashtag": "a hashtag",
}


class YouTubeAdapter(PlatformAdapter):
    """The one shipped adapter. Video URLs only, in five recognised forms."""

    platform: ClassVar[str] = "youtube"
    hosts: ClassVar[frozenset[str]] = frozenset(
        {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be",
        }
    )

    def canonicalize(self, parsed: ParsedUrl) -> CanonicalUrl:
        segments = parsed.segments

        if parsed.host in ("youtu.be", "www.youtu.be"):
            if len(segments) != 1:
                raise ResearchError(
                    f"{parsed.original!r}: a youtu.be link is the host and one video "
                    f"id; this has {len(segments)} path segments"
                )
            return self._video(segments[0], "youtu_be", parsed)

        if not segments:
            raise ResearchError(
                f"{parsed.original!r} is the YouTube home page, not a video. "
                "Supported: /watch?v=, youtu.be/, /shorts/, /live/, /embed/, /v/."
            )

        head = segments[0]
        if head == "watch":
            if len(segments) != 1:
                raise ResearchError(
                    f"{parsed.original!r}: /watch takes its id from the v= parameter, "
                    "not from the path"
                )
            value = parsed.param("v")
            if value is None:
                raise ResearchError(
                    f"{parsed.original!r}: a /watch URL with no v= parameter names no "
                    "video. Nothing here opens the link, so the id cannot be recovered."
                )
            return self._video(value, "watch", parsed)

        if head in _YOUTUBE_PATH_FORMS:
            if len(segments) != 2:
                raise ResearchError(
                    f"{parsed.original!r}: /{head}/ takes exactly one id segment, got "
                    f"{len(segments) - 1}"
                )
            return self._video(segments[1], _YOUTUBE_PATH_FORMS[head], parsed)

        if head.startswith("@"):
            raise ResearchError(
                f"{parsed.original!r} points at a channel handle. This adapter "
                "canonicalizes videos only; record the channel's videos instead."
            )
        if head in _YOUTUBE_NOT_A_VIDEO:
            raise ResearchError(
                f"{parsed.original!r} points at {_YOUTUBE_NOT_A_VIDEO[head]}. This "
                "adapter canonicalizes videos only."
            )
        raise ResearchError(
            f"{parsed.original!r} is not a recognised YouTube video URL. Supported: "
            "/watch?v=, youtu.be/, /shorts/, /live/, /embed/, /v/."
        )

    def _video(self, raw_id: str, form: str, parsed: ParsedUrl) -> CanonicalUrl:
        if not YOUTUBE_ID.match(raw_id):
            raise ResearchError(
                f"{raw_id!r} is not a YouTube video id: expected exactly 11 characters "
                "of [A-Za-z0-9_-]. Nothing in this package resolves a URL, so an id "
                "that is not already in the link cannot be recovered."
            )
        return CanonicalUrl(
            platform=self.platform,
            kind="video",
            external_id=raw_id,
            url=f"https://www.youtube.com/watch?v={raw_id}",
            original=parsed.original,
            form=f"youtube_{form}",
        )


_ADAPTERS: dict[str, PlatformAdapter] = {}
_BY_HOST: dict[str, PlatformAdapter] = {}


def register_adapter(adapter: PlatformAdapter) -> PlatformAdapter:
    """Add a platform. Refuses a host another platform already claims."""
    assert_slug(adapter.platform, "adapter platform")
    if not adapter.hosts:
        raise ResearchError(f"adapter {adapter.platform!r} claims no hosts")
    for host in sorted(adapter.hosts):
        owner = _BY_HOST.get(host)
        if owner is not None and owner.platform != adapter.platform:
            raise ResearchError(
                f"host {host!r} is already canonicalized by platform "
                f"{owner.platform!r}; one host belongs to one platform"
            )
    _ADAPTERS[adapter.platform] = adapter
    for host in adapter.hosts:
        _BY_HOST[host] = adapter
    return adapter


def unregister_adapter(platform: str) -> None:
    """Remove a platform. Exists so a test can register one and clean up."""
    if _ADAPTERS.pop(platform, None) is None:
        return
    for host in [h for h, a in _BY_HOST.items() if a.platform == platform]:
        del _BY_HOST[host]


def known_platforms() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def assert_known_platform(platform: str, field: str) -> str:
    """A platform we cannot canonicalize is a platform we cannot deduplicate."""
    assert_slug(platform, field)
    if platform not in _ADAPTERS:
        raise ResearchError(
            f"{field}: no adapter for platform {platform!r}, so its URLs cannot be "
            f"canonicalized or deduplicated. Registered: "
            f"{', '.join(known_platforms()) or 'none'}."
        )
    return platform


def adapter_for(platform: str) -> PlatformAdapter:
    assert_known_platform(platform, "platform")
    return _ADAPTERS[platform]


def parse_url(value: str) -> ParsedUrl:
    """Split a URL into scheme, host, path, query and fragment. Pure string work.

    A missing scheme is accepted and normalised to https, because
    `youtube.com/watch?v=ID` arrives from a spreadsheet at least as often as
    with one. Anything other than http(s) is refused: a `file://` URL in a
    research record is not a link to a public video.
    """
    if not isinstance(value, str) or not value.strip():
        raise ResearchError(f"a URL is required, got {value!r}")
    text = value.strip()
    if len(text) > MAX_URL_CHARS:
        raise ResearchError(
            f"URL is {len(text)} characters, over the {MAX_URL_CHARS}-character "
            "reference budget. This is content, not a link."
        )
    if any(ch.isspace() for ch in text):
        raise ResearchError(f"{value!r} contains whitespace; a URL does not")
    if not _URL_ALPHABET.match(text):
        raise ResearchError(
            f"{value!r} contains characters a URL does not: only the unreserved and "
            "reserved RFC 3986 characters are accepted"
        )

    scheme = "https"
    rest = text
    match = _SCHEME.match(text)
    if match:
        scheme = match.group("scheme").lower()
        rest = match.group("rest")
        if scheme not in ("http", "https"):
            raise ResearchError(
                f"{value!r}: a research source is an http or https URL, got "
                f"scheme {scheme!r}"
            )
    elif "//" in text.split("/", 1)[0] or ":" in text.split("/", 1)[0]:
        raise ResearchError(f"{value!r} is not a URL this package can read")

    rest, _, fragment = rest.partition("#")
    rest, _, query = rest.partition("?")
    authority, slash, path = rest.partition("/")

    if "@" in authority:
        raise ResearchError(
            f"{value!r} carries userinfo before the host. A public research link does "
            "not need credentials, and this package will not store them."
        )
    host, _, port = authority.partition(":")
    host = host.lower().rstrip(".")
    if not _HOSTNAME.match(host):
        raise ResearchError(f"{value!r}: {host!r} is not a hostname")
    if port and not port.isdigit():
        raise ResearchError(f"{value!r}: {port!r} is not a port")

    pairs: list[tuple[str, str]] = []
    for part in query.split("&"):
        if not part:
            continue
        key, _, val = part.partition("=")
        pairs.append((key, val))

    return ParsedUrl(
        scheme="https",
        host=host,
        port=port,
        path=("/" + path) if slash else "/",
        query=tuple(pairs),
        fragment=fragment,
        original=text,
    )


def canonicalize(url: str) -> CanonicalUrl:
    """Reduce a URL to a platform, an id and one canonical spelling.

    Raises for a malformed URL, for an unsupported host, and for a host whose
    adapter recognises the URL but not as a video. Every one of those is a
    refusal rather than a best guess, because a guessed id merges two videos.
    """
    parsed = parse_url(url)
    adapter = _BY_HOST.get(parsed.host)
    if adapter is None:
        raise ResearchError(
            f"no platform adapter answers for host {parsed.host!r}. Registered "
            f"platforms: {', '.join(known_platforms()) or 'none'}. Add a "
            "PlatformAdapter rather than special-casing a URL."
        )
    return adapter.canonicalize(parsed)


def identity_of(url: str) -> ContentIdentity:
    """The deduplication identity of a URL, in one call."""
    return canonicalize(url).identity


register_adapter(YouTubeAdapter())
