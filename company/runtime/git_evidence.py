"""Git evidence: the shape of a claim, and an optional offline check of it.

A receipt is a report from a session this process did not run. Two different
things can be asked of it, and keeping them apart is the whole design of this
module.

**Shape** is always checkable. A commit SHA either looks like a Git object name
or it does not, and `remote_verified` is either asserted or it is not. Nothing
outside the receipt is needed, which is why `validate_receipt` can run on a
machine that has never seen the repository.

**Substance** needs the repository. When a local clone is available these
helpers read its refs directly - `.git/refs/...` and `.git/packed-refs`, plus
the `gitdir:`/`commondir` indirection a worktree uses - and compare them with
what the receipt claims. No subprocess, no network, no `git` on PATH: a
verification step that shells out is a verification step that behaves
differently in CI, and one that reaches the network cannot run in a test.

What is deliberately absent is a Git abstraction. There is no object reader, no
commit walker and no merge detector, because the receipt states plainly whether
a merge was performed and the packet states plainly that none is allowed. A
parser for pack files would be a large amount of code protecting a claim that
is already refused when it is made.
"""

from __future__ import annotations

from pathlib import Path
import re

from .errors import LifecycleError


GIT_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
"""SHA-1 and SHA-256 object names; a repository may use either."""

_BRANCH_REFUSED_SUBSTRINGS = ("..", "@{", "//")
_BRANCH_REFUSED_CHARS = frozenset("~^:?*[]\\\x7f") | {chr(code) for code in range(33)}


def is_git_sha(value: object) -> bool:
    return isinstance(value, str) and GIT_SHA.fullmatch(value) is not None


def assert_git_sha(value: str, field: str) -> str:
    if not is_git_sha(value):
        raise LifecycleError(
            f"{field}: {value!r} is not a Git object name (40 or 64 lowercase hex characters)"
        )
    return value


def assert_branch_name(value: str, field: str) -> str:
    """A conservative subset of `git check-ref-format`, applied deterministically."""
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"{field}: a branch name is required, got {value!r}")
    name = value.strip()
    if (
        name != value
        or name.startswith("-")
        or name.startswith("/")
        or name.endswith("/")
        or name.endswith(".lock")
        or any(item in name for item in _BRANCH_REFUSED_SUBSTRINGS)
        or any(char in _BRANCH_REFUSED_CHARS for char in name)
    ):
        raise LifecycleError(f"{field}: {value!r} is not a usable branch name")
    return name


def git_dir(repo_dir: str | Path) -> Path:
    """Resolve `.git`, following the file indirection a worktree uses."""
    root = Path(repo_dir).resolve()
    candidate = root / ".git"
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            target = Path(text.split(":", 1)[1].strip())
            return target if target.is_absolute() else (root / target).resolve()
    raise LifecycleError(f"{root}: not a Git working tree")


def common_dir(repo_dir: str | Path) -> Path:
    """The shared object/ref directory, which a linked worktree points at."""
    directory = git_dir(repo_dir)
    marker = directory / "commondir"
    if marker.is_file():
        target = Path(marker.read_text(encoding="utf-8").strip())
        return target if target.is_absolute() else (directory / target).resolve()
    return directory


def read_ref(repo_dir: str | Path, ref: str) -> str:
    """Return the SHA a full ref name resolves to, or an empty string.

    Loose refs win over `packed-refs`, which is what Git itself does.
    """
    for directory in _ref_roots(repo_dir):
        loose = directory / Path(ref)
        if loose.is_file():
            value = loose.read_text(encoding="utf-8").strip()
            if value.startswith("ref:"):
                return read_ref(repo_dir, value.split(":", 1)[1].strip())
            return value
    for directory in _ref_roots(repo_dir):
        packed = directory / "packed-refs"
        if not packed.is_file():
            continue
        for line in packed.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref:
                return sha.strip()
    return ""


def branch_head(repo_dir: str | Path, branch: str) -> str:
    return read_ref(repo_dir, f"refs/heads/{branch}")


def remote_branch_head(repo_dir: str | Path, branch: str, remote: str = "origin") -> str:
    """The remote-tracking ref, which is what a local `git fetch` recorded."""
    return read_ref(repo_dir, f"refs/remotes/{remote}/{branch}")


def repository_findings(
    repo_dir: str | Path,
    branch: str,
    commit_sha: str,
    remote_branch_sha: str = "",
    remote: str = "origin",
) -> tuple[str, ...]:
    """Compare a receipt's claims with the refs a local clone actually holds.

    Returns the disagreements. An empty tuple means every claim that could be
    checked here held; a ref this clone has never fetched is reported as
    unverifiable rather than as a mismatch, because an unfetched ref is a fact
    about this clone and not about the work.
    """
    findings: list[str] = []
    local = branch_head(repo_dir, branch)
    if not local:
        findings.append(f"local branch {branch} does not exist in {repo_dir}")
    elif commit_sha and local != commit_sha:
        findings.append(
            f"local branch {branch} is at {local}, the receipt reports {commit_sha}"
        )

    tracking = remote_branch_head(repo_dir, branch, remote)
    if not tracking:
        findings.append(
            f"remote-tracking ref refs/remotes/{remote}/{branch} is not present in this "
            "clone; the remote claim cannot be checked here"
        )
    else:
        claimed = remote_branch_sha or commit_sha
        if claimed and tracking != claimed:
            findings.append(
                f"refs/remotes/{remote}/{branch} is at {tracking}, the receipt reports {claimed}"
            )
    return tuple(findings)


def _ref_roots(repo_dir: str | Path) -> tuple[Path, ...]:
    directory = git_dir(repo_dir)
    shared = common_dir(repo_dir)
    return (directory,) if directory == shared else (directory, shared)


__all__ = [
    "GIT_SHA",
    "assert_branch_name",
    "assert_git_sha",
    "branch_head",
    "common_dir",
    "git_dir",
    "is_git_sha",
    "read_ref",
    "remote_branch_head",
    "repository_findings",
]
