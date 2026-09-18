"""The governance files an engineering job may never touch, digested up front.

Every other guard in this package works on what a session *reports*. A session
reports the paths it changed, and `PathScope` judges that report. It is the
right mechanism and it has one blind spot: a session that edits
`company/permissions.yaml` and does not mention it.

So the work order does not only forbid those paths, it **measures** them. At
authorization time `ProtectedSurface.capture` reads each protected file and
records a digest of its bytes. At review time `verify` reads them again. A
changed digest is a `ProtectedSurfaceViolation` and the review is BLOCKED,
whatever the receipt said and whatever the reviewer concluded.

That turns "the implementer must not weaken protected policy to make itself
pass" from a rule in a document into an arithmetic check on a hash, and it is
the reason the loop can be pointed at Company OS itself.

## Why these files

`DEFAULT_PROTECTED_PATHS` is every file that decides what is allowed, rather
than what is built:

- the four bootstrap contracts — the constitution, the permissions, the agent
  contract schema and the handoff schema;
- `ai_platform/policy.py` and `company/validation/no_subagents.py` — the
  two-key lock on nested agents;
- `company/integration/policy.py`, `checks.py` and `suites.py` — the gate's
  required/advisory split, its conditions and the suites it demands. Widening
  the advisory set by one line is the cheapest way to make a failing change
  pass, and it is the specific move this list exists to catch.

A work order may add to the list. It may not shorten it: `capture` unions the
caller's paths with the default, so a work order that names none still protects
all ten.

## What a digest is, and is not

Sixteen hex characters of SHA-256 over the file's bytes, via the platform's own
`fingerprint`. Bytes rather than parsed content, because a reformatting that
changes no meaning still changes the file a reviewer would have to read, and
this check is not the place to decide which edits are harmless.

An absent file digests to the empty string, which is a value like any other: a
protected file that is deleted, or created, during execution is a finding.
Nothing here writes, and nothing here reaches outside the repository root.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from company.runtime.path_scope import normalise_path

from .errors import EngineeringError


# The governance surface. Extendable per work order, never shortenable.
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    "ai_platform/policy.py",
    "company/agent_contract.schema.yaml",
    "company/constitution.md",
    "company/integration/checks.py",
    "company/integration/policy.py",
    "company/integration/suites.py",
    "company/org_registry.yaml",
    "company/permissions.yaml",
    "company/task_handoff.schema.yaml",
    "company/validation/no_subagents.py",
)

ABSENT = ""
"""The digest of a protected path the checkout does not contain."""


def _digest(repo_root: Path, path: str) -> str:
    target = repo_root / path
    if not target.is_file():
        return ABSENT
    try:
        payload = target.read_bytes()
    except OSError as exc:
        raise EngineeringError(f"protected path {path}: cannot be read: {exc}") from exc
    return _fingerprint(payload.decode("utf-8", errors="surrogateescape"))


@dataclass(frozen=True)
class ProtectedFile:
    """One protected path and the digest it held when the work was authorized."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalise_path(self.path, "protected.path"))
        if not isinstance(self.digest, str):
            raise EngineeringError("protected.digest must be a string")
        if self.digest and len(self.digest) != 16:
            raise EngineeringError(
                f"protected {self.path}: digest must be empty (absent) or a "
                "16-character digest"
            )

    @property
    def absent(self) -> bool:
        return self.digest == ABSENT

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "digest": self.digest}


@dataclass(frozen=True)
class ProtectedSurface:
    """Every protected path, with its authorization-time digest."""

    entries: tuple[ProtectedFile, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or any(
            not isinstance(item, ProtectedFile) for item in self.entries
        ):
            raise EngineeringError("protected surface holds ProtectedFile values")
        paths = [item.path for item in self.entries]
        duplicates = sorted({path for path in paths if paths.count(path) > 1})
        if duplicates:
            raise EngineeringError(
                "protected surface names a path twice: " + ", ".join(duplicates)
            )
        object.__setattr__(
            self, "entries", tuple(sorted(self.entries, key=lambda item: item.path))
        )

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.entries)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def capture(
        cls,
        repo_root: Path | str,
        *,
        additional_paths: Sequence[str] = (),
        authorized_paths: Sequence[str] = (),
    ) -> "ProtectedSurface":
        """Digest the default surface plus `additional_paths`, refusing overlap.

        `authorized_paths` is checked rather than trusted: a work order that
        both grants and protects the same location is incoherent, and the
        incoherence is refused here instead of being resolved silently by
        whichever guard happens to run first.
        """
        root = Path(repo_root).resolve()
        wanted = set(DEFAULT_PROTECTED_PATHS)
        for index, item in enumerate(additional_paths):
            wanted.add(normalise_path(item, f"protected.additional_paths[{index}]"))
        granted = tuple(
            normalise_path(item, f"work_order.authorized_paths[{index}]")
            for index, item in enumerate(authorized_paths)
        )
        clashes = sorted(
            f"{path} is protected and also authorized by {rule}"
            for path in wanted
            for rule in granted
            if path == rule or path.startswith(rule + "/") or rule.startswith(path + "/")
        )
        if clashes:
            raise EngineeringError(
                "a work order cannot authorize a protected path: " + "; ".join(clashes)
            )
        return cls(
            entries=tuple(
                ProtectedFile(path, _digest(root, path)) for path in sorted(wanted)
            )
        )

    def verify(self, repo_root: Path | str) -> tuple[str, ...]:
        """Every protected path whose bytes no longer match, as sorted findings."""
        root = Path(repo_root).resolve()
        findings: list[str] = []
        for item in self.entries:
            observed = _digest(root, item.path)
            if observed == item.digest:
                continue
            if item.absent:
                findings.append(
                    f"{item.path} did not exist when the work was authorized and now does"
                )
            elif observed == ABSENT:
                findings.append(f"{item.path} was deleted during execution")
            else:
                findings.append(
                    f"{item.path} was modified during execution "
                    f"({item.digest} -> {observed})"
                )
        return tuple(sorted(findings))

    def covers(self, path: str) -> str:
        """The protected rule covering `path`, or an empty string."""
        candidate = normalise_path(path, "path")
        for item in self.entries:
            if candidate == item.path or candidate.startswith(item.path + "/"):
                return item.path
        return ""

    @classmethod
    def from_mapping(cls, data: Any) -> "ProtectedSurface":
        if not isinstance(data, Mapping):
            raise EngineeringError("protected surface must be a mapping")
        unknown = sorted(set(data) - {"entries"})
        if unknown:
            raise EngineeringError(
                "protected surface has unknown field(s): " + ", ".join(unknown)
            )
        raw = data.get("entries", ())
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
            raise EngineeringError("protected surface entries must be a list")
        entries = []
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise EngineeringError(f"protected entries[{index}] must be a mapping")
            extra = sorted(set(item) - {"path", "digest"})
            if extra:
                raise EngineeringError(
                    f"protected entries[{index}] has unknown field(s): "
                    + ", ".join(extra)
                )
            entries.append(
                ProtectedFile(str(item.get("path", "")), str(item.get("digest", "")))
            )
        surface = cls(entries=tuple(entries))
        missing = tuple(
            path for path in DEFAULT_PROTECTED_PATHS if path not in surface.paths
        )
        if missing:
            raise EngineeringError(
                "a stored protected surface is missing default protected path(s): "
                + ", ".join(missing)
                + ". The default surface is a floor; a record that dropped one of "
                "its entries cannot be believed."
            )
        return surface


__all__ = [
    "ABSENT",
    "DEFAULT_PROTECTED_PATHS",
    "ProtectedFile",
    "ProtectedSurface",
]
