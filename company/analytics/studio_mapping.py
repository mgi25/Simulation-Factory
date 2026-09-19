"""Which YouTube video is which of our deliverables, said explicitly.

## Titles are not identities

A Studio export carries a title beside every video, and the title is the single
most tempting join key in the file: it is human-readable, it is right there, and
it usually works. It fails on the day a video is renamed, on the day two videos
in a series are called the same thing, and on the day a title differs by one
character from the one in our notes - and each of those failures merges or
splits a deliverable's whole measurement history without saying so.

So the only key here is the eleven-character YouTube video id, checked against
its shape, and a mapping file whose keys do not look like video ids is refused
rather than accepted as titles. `deliverable.py` already says the same thing
about titles from the other direction: display only, and nothing infers from
them. `UnresolvedVideo` on an ingestion result may carry a title, and it is
labelled a hint, for a person deciding what to add here.

## The mapping is written, never inferred

Nothing in this module guesses. A video id with no entry produces an unresolved
row on the ingestion result and no observation, which is the outcome that makes
somebody add the line. The alternative - inventing a deliverable id from a title
or a publication date - would produce a record that looks like everything else
in the store and is not traceable to a decision anybody made.

## Channel, on both sides

The mapping names the channel it belongs to, and `studio_ingest.py` refuses a
mapping whose channel is not the export's channel. Two channels of our own with
one mapping file between them is how a video id from one ends up attached to the
other's deliverable, and the check costs one comparison.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .common import assert_deliverable_id, assert_prose, assert_ref
from .errors import AnalyticsError, StudioExportRejected

# A YouTube video id: exactly eleven characters of URL-safe base64. Narrow on
# purpose - it is what stops a title being used as a key, because no title is
# eleven characters of that alphabet by accident often enough to matter, and one
# that is will be caught by the deliverable it fails to resolve.
YOUTUBE_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def is_video_id(value: Any) -> bool:
    return isinstance(value, str) and bool(YOUTUBE_VIDEO_ID.fullmatch(value.strip()))


@dataclass(frozen=True)
class VideoIdentityMapping:
    """Stable video ids to internal deliverable ids, for one channel of ours."""

    channel_ref: str
    entries: tuple[tuple[str, str], ...]
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "channel_ref", assert_ref(self.channel_ref, "mapping channel_ref")
        )
        pairs: list[tuple[str, str]] = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise AnalyticsError(
                    f"mapping entry {entry!r} must be a (video_id, deliverable_id) pair"
                )
            video_id, deliverable_id = entry
            if not is_video_id(video_id):
                raise AnalyticsError(
                    f"mapping key {video_id!r} is not a YouTube video id. Keys are "
                    "eleven characters of [A-Za-z0-9_-]; a title is never a key here, "
                    "because a renamed video would become a different deliverable and "
                    "two videos sharing a title would become one"
                )
            pairs.append(
                (video_id.strip(), assert_deliverable_id(deliverable_id, "deliverable_id"))
            )
        object.__setattr__(self, "entries", tuple(sorted(pairs)))
        seen_videos = [video for video, _ in self.entries]
        repeated = sorted({v for v in seen_videos if seen_videos.count(v) > 1})
        if repeated:
            raise AnalyticsError(
                f"video id(s) {', '.join(repeated)} are mapped more than once; a "
                "video has one deliverable"
            )
        seen_deliverables = [deliverable for _, deliverable in self.entries]
        shared = sorted({d for d in seen_deliverables if seen_deliverables.count(d) > 1})
        if shared:
            raise AnalyticsError(
                f"deliverable(s) {', '.join(shared)} are named by more than one video "
                "id. Two uploads are two deliverables even when they are the same cut; "
                "merging their readings into one series would hide that one of them "
                "was published twice"
            )
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "mapping note"))

    def deliverable_for(self, video_id: str) -> str:
        """The deliverable this video is, or an empty string. Never a guess."""
        for known, deliverable_id in self.entries:
            if known == video_id:
                return deliverable_id
        return ""

    def __len__(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_ref": self.channel_ref,
            "videos": {video: deliverable for video, deliverable in self.entries},
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> VideoIdentityMapping:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a mapping object, got {data!r}")
        videos = data.get("videos")
        if not isinstance(videos, Mapping):
            raise AnalyticsError(
                "a video mapping needs a 'videos' object of video id to deliverable "
                "id; without one there is nothing to resolve a row against"
            )
        try:
            return cls(
                channel_ref=data["channel_ref"],
                entries=tuple(videos.items()),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(
                f"video mapping: missing {exc.args[0]!r} - the mapping has to say "
                "which channel of ours it describes"
            ) from None


def load_video_mapping(path: str | Path) -> VideoIdentityMapping:
    """Read a mapping file. JSON, explicit, and never written by this package."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StudioExportRejected(f"cannot read the video mapping {source}: {exc}") from exc
    except ValueError as exc:
        raise StudioExportRejected(f"{source} is not valid JSON: {exc}") from exc
    return VideoIdentityMapping.from_dict(data)
