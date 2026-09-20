"""SHA-256 digests for explicit capsule-owned source files.

The caller names every file.  These helpers do not scan a repository, expand
globs, inspect Git, or infer which files matter from a directory.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from knowledge.company_os.capsules.budget import CapsuleError
from knowledge.company_os.capsules.capsule import Capsule, SourceDigest
from knowledge.company_os.capsules.index import normalise_path, path_related

_CHUNK_BYTES = 64 * 1024


def digest_source_file(repo_root: Path | str, source_path: str) -> SourceDigest:
    """Hash one explicit repository-relative file as raw bytes."""

    cleaned, target = _resolve_explicit_file(repo_root, source_path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return SourceDigest(path=cleaned, digest=digest.hexdigest())


def digest_source_files(
    repo_root: Path | str,
    source_paths: Iterable[str],
) -> tuple[SourceDigest, ...]:
    """Hash explicit files once each, returning path-sorted results."""

    paths = tuple(source_paths)
    if any(not isinstance(path, str) or not path.strip() for path in paths):
        raise CapsuleError("source paths must be explicit non-empty strings")
    canonical_paths = tuple(sorted({normalise_path(path) for path in paths}))
    return tuple(digest_source_file(repo_root, path) for path in canonical_paths)


def digest_capsule_sources(
    capsule: Capsule,
    repo_root: Path | str,
    source_paths: Iterable[str],
) -> tuple[SourceDigest, ...]:
    """Hash named files only when they sit inside a capsule-owned boundary."""

    paths = tuple(source_paths)
    outside = tuple(
        sorted(
            path
            for path in paths
            if not any(path_related(owned, path) for owned in capsule.owns_paths)
        )
    )
    if outside:
        raise CapsuleError(
            f"{capsule.id}: source path(s) are outside its owned paths: "
            + ", ".join(outside)
        )
    return digest_source_files(repo_root, paths)


def _resolve_explicit_file(
    repo_root: Path | str,
    source_path: str,
) -> tuple[str, Path]:
    if not isinstance(source_path, str) or not source_path.strip():
        raise CapsuleError("source path must be an explicit non-empty string")
    if any(marker in source_path for marker in ("*", "?", "[", "::", "#")):
        raise CapsuleError(
            f"source path {source_path!r} must name one file; globs, spans, and "
            "test node ids are not digest inputs"
        )
    cleaned = normalise_path(source_path)
    relative = Path(cleaned)
    if relative.is_absolute():
        raise CapsuleError(f"source path {source_path!r} must be repository-relative")

    root = Path(repo_root).resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise CapsuleError(
            f"source path {source_path!r} escapes the repository root"
        ) from exc
    if not target.is_file():
        raise CapsuleError(f"source path {cleaned!r} is not a file")
    return cleaned, target


__all__ = [
    "digest_capsule_sources",
    "digest_source_file",
    "digest_source_files",
]
