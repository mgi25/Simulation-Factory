"""The write boundary a packet declares, and the verdict on what came back.

A packet hands a task to a session this process does not control. The only
thing that can be checked afterwards is the set of paths that session says it
changed, so the rule has to be stated before the work and applied to the
report without judgment.

Two decisions are worth stating plainly, because both are the safe reading
rather than the convenient one:

- **Forbidden wins.** A path matched by both lists is refused. A packet that
  allows `company/` and forbids `company/permissions.yaml` means the file is
  out of bounds, not that the broader rule rescues it.
- **An empty allow-list allows nothing.** A packet that names no writable path
  is a read-only packet, and a session reporting a change against one has
  exceeded its scope. Silence is not permission; `permissions.yaml` grants
  authority by naming it, and so does this.

Matching is prefix matching on normalised POSIX path segments: the rule
`company/runtime` covers `company/runtime/packets.py` and does not cover
`company/runtime_extra.py`. Nothing here touches the filesystem - a packet is
validated against reported paths, not against a working tree.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import LifecycleError


_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")


def normalise_path(value: str, field: str) -> str:
    r"""Return a repository-relative POSIX path, or raise.

    Separators are normalised because a Windows session reports
    `company\runtime\packets.py` for the same file a POSIX one calls
    `company/runtime/packets.py`, and a scope guard that fails on the
    separator is a guard nobody trusts.
    """
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"{field}: a path is required, got {value!r}")
    text = value.strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    if not text:
        raise LifecycleError(f"{field}: a path is required, got {value!r}")
    if text.startswith("/") or _WINDOWS_DRIVE.fullmatch(text.split("/", 1)[0]):
        raise LifecycleError(
            f"{field}: {value!r} is absolute; scope rules are repository-relative"
        )
    segments = text.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise LifecycleError(
            f"{field}: {value!r} contains a relative segment; a scope rule must "
            "name one unambiguous location"
        )
    return text


def _covers(rule: str, path: str) -> bool:
    return path == rule or path.startswith(rule + "/")


@dataclass(frozen=True)
class PathScope:
    """The paths a session may change, and the paths it may never touch."""

    allowed: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("allowed", "forbidden"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise LifecycleError(f"path_scope.{name} must be a tuple")
            normalised = tuple(
                sorted({normalise_path(item, f"path_scope.{name}") for item in values})
            )
            object.__setattr__(self, name, normalised)

    @property
    def read_only(self) -> bool:
        return not self.allowed

    def forbids(self, path: str) -> str:
        """The forbidding rule that covers `path`, or an empty string."""
        for rule in self.forbidden:
            if _covers(rule, path):
                return rule
        return ""

    def permits(self, path: str) -> bool:
        return any(_covers(rule, path) for rule in self.allowed)

    def verdict(self, paths: tuple[str, ...] | list[str]) -> "PathScopeVerdict":
        """Classify every reported path. Deterministic, and sorted."""
        forbidden_hits: list[str] = []
        outside_allowed: list[str] = []
        normalised: list[str] = []
        for index, raw in enumerate(paths):
            path = normalise_path(raw, f"files_changed[{index}]")
            normalised.append(path)
            rule = self.forbids(path)
            if rule:
                forbidden_hits.append(f"{path} is covered by forbidden rule {rule}")
            elif not self.permits(path):
                outside_allowed.append(path)
        return PathScopeVerdict(
            paths=tuple(normalised),
            forbidden_hits=tuple(sorted(forbidden_hits)),
            outside_allowed=tuple(sorted(outside_allowed)),
        )


@dataclass(frozen=True)
class PathScopeVerdict:
    paths: tuple[str, ...]
    forbidden_hits: tuple[str, ...]
    outside_allowed: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.forbidden_hits and not self.outside_allowed

    def failures(self) -> tuple[str, ...]:
        issues = [f"path scope: {hit}" for hit in self.forbidden_hits]
        issues.extend(
            f"path scope: {path} is outside every allowed path" for path in self.outside_allowed
        )
        return tuple(issues)


__all__ = ["PathScope", "PathScopeVerdict", "normalise_path"]
