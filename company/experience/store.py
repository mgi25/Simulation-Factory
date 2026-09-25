"""The append-only experience store, under a directory the caller names.

```
<state_dir>/experience/episodes/<experience-id>/000001.json
```

One directory per episode identity, one file in it, created with `O_EXCL`
through `company.runtime.state_paths.create_json_bytes_at_sequence` - the same
exclusive-create primitive every other Company OS history uses, so there is no
second copy of the write loop to carry a second overwrite bug.

## Why exactly one file per identity

An episode indexes a settled attempt, and a settled attempt does not change.
So the store has no revision sequence to append: the first write of an
identity is the only write. A second offer of the same identity is answered by
comparing content, never by writing:

- identical content -> the existing pointer, so an idempotent re-capture (the
  normal case: every advisory run re-scans settled history) costs nothing and
  never fails;
- different content -> `ExperienceConflict`. The identity is derived from
  canonical pointers, so different content under it means a canonical record
  changed underneath the index. That is refused, loudly, and nothing is
  written - the first capture stays exactly as it was.

Content excludes `provenance` and `source` (see `model.ExperienceEpisode`):
capturing the same attempt again on a later day records a later capture date,
and that is not a disagreement about what happened.

## Reading degrades; writing does not

`scan()` never raises on a bad record. A file that does not decode, or whose
stored id is not the id its own content derives, is reported as a problem and
left out, so one corrupt record costs one precedent rather than every
precedent. An unreadable store scans as empty with a problem. Nothing that
consumes experience may fail because the experience store did - experience is
an optimisation, never an authority dependency.

No database, no index file, no network, no embedding, no model.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from ai_platform.references import assert_reference
from ai_platform.serde import dumps
from company.runtime.state_paths import (
    StateStoreError,
    create_json_bytes_at_sequence,
    task_directory_name,
)

from .errors import ExperienceConflict, ExperienceError
from .model import ExperienceEpisode


_ROOT = "experience"
_EPISODES = "episodes"
_RECORD = "000001.json"


@dataclass(frozen=True)
class EpisodePointer:
    """Where one episode lives, its id, and whether this call created it."""

    record_ref: str
    experience_id: str
    content_fingerprint: str
    created: bool

    def __post_init__(self) -> None:
        assert_reference(self.record_ref, "experience.record_ref")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_ref": self.record_ref,
            "experience_id": self.experience_id,
            "content_fingerprint": self.content_fingerprint,
            "created": self.created,
        }


@dataclass(frozen=True)
class StoreScan:
    """Everything readable, in a stable order, and everything that was not."""

    episodes: tuple[ExperienceEpisode, ...]
    problems: tuple[str, ...]
    available: bool

    def by_id(self) -> dict[str, ExperienceEpisode]:
        return {episode.experience_id: episode for episode in self.episodes}


def episode_order(episode: ExperienceEpisode) -> tuple[str, str, int, str]:
    """Chronological by settlement, then by attempt - deterministic everywhere."""
    return (
        episode.settled_on.isoformat(),
        episode.work_order_id,
        episode.packet_attempt,
        episode.experience_id,
    )


class ExperienceStore:
    """Episodes written once, read in a stable order, never updated or deleted."""

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise ExperienceError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / _ROOT / _EPISODES

    # --- writing -------------------------------------------------------------

    def put(self, episode: ExperienceEpisode) -> EpisodePointer:
        """Write an episode once. Identical content is idempotent; different is refused."""
        if not isinstance(episode, ExperienceEpisode):
            raise ExperienceError("the experience store holds ExperienceEpisode values")
        directory = self._directory(episode.experience_id)
        payload = dumps(episode).encode("utf-8")
        try:
            path = create_json_bytes_at_sequence(directory, payload, 1)
        except StateStoreError:
            existing = self.get(episode.experience_id)
            if existing is None:
                raise ExperienceError(
                    f"episode {episode.experience_id} exists on disk but does not decode; "
                    "it is left as it is and nothing was written"
                ) from None
            if existing.content_fingerprint() != episode.content_fingerprint():
                raise ExperienceConflict(
                    f"episode {episode.experience_id} ({episode.work_order_id} attempt "
                    f"{episode.packet_attempt}) is already stored with content "
                    f"{existing.content_fingerprint()}, and different content "
                    f"({episode.content_fingerprint()}) was offered: "
                    + "; ".join(_differences(existing, episode))
                    + ". A canonical record changed under an existing identity; the "
                    "stored episode is kept and nothing was written."
                ) from None
            return EpisodePointer(
                record_ref=self._ref(directory / _RECORD),
                experience_id=existing.experience_id,
                content_fingerprint=existing.content_fingerprint(),
                created=False,
            )
        return EpisodePointer(
            record_ref=self._ref(path),
            experience_id=episode.experience_id,
            content_fingerprint=episode.content_fingerprint(),
            created=True,
        )

    # --- reading -------------------------------------------------------------

    def get(self, experience_id: str) -> ExperienceEpisode | None:
        path = self._directory(experience_id) / _RECORD
        if not path.is_file():
            return None
        try:
            return self._decode(path)
        except (ExperienceError, ValueError, TypeError, KeyError):
            return None

    def scan(self) -> StoreScan:
        """Every episode that decodes and checks out, and a line for each that does not."""
        if not self.root.exists():
            return StoreScan(episodes=(), problems=(), available=True)
        try:
            directories = sorted(path for path in self.root.iterdir() if path.is_dir())
        except OSError as exc:
            return StoreScan(episodes=(), problems=(f"experience store unreadable: {exc}",), available=False)
        episodes: list[ExperienceEpisode] = []
        problems: list[str] = []
        for directory in directories:
            path = directory / _RECORD
            if not path.is_file():
                problems.append(f"{self._ref(directory)}: holds no {_RECORD}")
                continue
            try:
                episode = self._decode(path)
            except (ExperienceError, ValueError, TypeError, KeyError) as exc:
                problems.append(f"{self._ref(path)}: {type(exc).__name__}: {exc}")
                continue
            if directory.name != task_directory_name(episode.experience_id):
                problems.append(
                    f"{self._ref(path)}: filed under {directory.name}, but its id "
                    f"{episode.experience_id} belongs elsewhere"
                )
                continue
            episodes.append(episode)
        return StoreScan(
            episodes=tuple(sorted(episodes, key=episode_order)),
            problems=tuple(problems),
            available=True,
        )

    def episodes(self) -> tuple[ExperienceEpisode, ...]:
        return self.scan().episodes

    # --- internals -----------------------------------------------------------

    def _directory(self, experience_id: str) -> Path:
        return self.root / task_directory_name(experience_id)

    def _ref(self, path: Path) -> str:
        return path.relative_to(self.state_dir).as_posix()

    @staticmethod
    def _decode(path: Path) -> ExperienceEpisode:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperienceError(f"cannot read {path.name}: {exc}") from exc
        # `from_mapping` re-derives the id from the canonical identity and
        # refuses a stored id that disagrees, so a hand-edited identity field
        # cannot pass as the episode it claims to be.
        return ExperienceEpisode.from_mapping(data)


def _differences(left: ExperienceEpisode, right: ExperienceEpisode) -> tuple[str, ...]:
    a, b = left.content(), right.content()
    return tuple(key for key in sorted(set(a) | set(b)) if a.get(key) != b.get(key)) or ("content",)


__all__ = ["EpisodePointer", "ExperienceStore", "StoreScan", "episode_order"]
