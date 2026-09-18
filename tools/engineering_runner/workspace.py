"""The task worktree: where a job's session is allowed to touch files.

A coding session needs a checkout to work in, and the obvious one - the
operator's - is the wrong one. It is probably on another branch, it may be
dirty, and a session that leaves it half-edited breaks the next thing the
operator types. So each work order gets its own `git worktree`, created at the
work order's base commit on the work order's branch, and the session runs
there and nowhere else.

That choice pays for itself three times:

- **Isolation.** The operator's tree is never checked out, never stashed,
  never switched.
- **Identity.** "Did the work happen where it was authorized to?" becomes a
  question with a filesystem answer: the worktree's git common directory must
  be the configured repository's, and its HEAD must be the authorized branch.
- **Evidence.** `git diff --name-status <base>..HEAD` over a tree that started
  at exactly `<base>` is the complete, honest list of what changed - which is
  what the authority check consumes instead of the session's own account.

## Every git call is a list, and none of them is `git -c`

No configuration is injected, no hook is skipped, no signing is disabled. The
runner runs the same git the operator would, with the repository's own
settings, so a commit it makes is a commit the repository would have accepted
from a person.

## What the runner will not do with git

It never rewrites history, never force-pushes, never merges, never tags, and
never touches a branch other than the work order's. `push` is the only
outward-facing call, it pushes exactly one branch to exactly one remote, and
the completion protocol needs it: an accepted receipt has to name a remote SHA
that a reviewer can fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .errors import ConfigurationError, IntegrityFailure
from .process import CommandResult, CommandRunner


GIT = "git"

# Statuses `git diff --name-status` reports for a path that has two names.
_RENAME_LIKE = ("R", "C")


@dataclass(frozen=True)
class GitStatus:
    """What a working tree looks like right now."""

    head: str
    branch: str
    dirty_paths: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.dirty_paths


class Workspace:
    """One repository, and the per-work-order worktrees cut from it."""

    def __init__(
        self,
        runner: CommandRunner,
        *,
        repo_root: Path,
        worktree_root: Path,
        remote: str = "origin",
        timeout_s: float = 300.0,
    ) -> None:
        self._runner = runner
        self._repo_root = Path(repo_root).resolve()
        self._worktree_root = Path(worktree_root).resolve()
        self._remote = remote
        self._timeout = float(timeout_s)

    # --- reading -----------------------------------------------------------

    def git(self, args: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
        return self._runner.run(
            [GIT, *args], cwd=cwd or self._repo_root, timeout_s=self._timeout
        )

    def require_git(self, args: Sequence[str], *, cwd: Path | None = None) -> str:
        result = self.git(args, cwd=cwd)
        if not result.ok:
            raise ConfigurationError(
                f"git {' '.join(args)} failed ({result.exit_code}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout.strip()

    def common_dir(self, cwd: Path | None = None) -> Path:
        """The shared `.git` directory, which every worktree of a repo agrees on."""
        value = self.require_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd)
        return Path(value.strip()).resolve()

    def status(self, cwd: Path) -> GitStatus:
        head = self.require_git(["rev-parse", "HEAD"], cwd=cwd)
        branch = self.require_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        porcelain = self.git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=cwd)
        dirty = tuple(
            line[3:].strip().strip('"')
            for line in porcelain.stdout.splitlines()
            if line.strip()
        )
        return GitStatus(head=head, branch=branch, dirty_paths=dirty)

    def commit_exists(self, sha: str) -> bool:
        if not sha:
            return False
        return self.git(["cat-file", "-e", f"{sha}^{{commit}}"]).ok

    def is_ancestor(self, ancestor: str, descendant: str, *, cwd: Path) -> bool:
        if not ancestor or not descendant:
            return False
        return self.git(["merge-base", "--is-ancestor", ancestor, descendant], cwd=cwd).ok

    def changed_paths(self, base: str, head: str, *, cwd: Path) -> tuple[str, ...]:
        """Every path the range touched, both names of a rename included.

        A rename is two facts - one path stopped existing and another started -
        and a scope check that saw only the destination would miss a session
        that moved a file out of the tree it was allowed to touch.
        """
        text = self.require_git(
            ["diff", "--name-status", "--find-renames", f"{base}..{head}"], cwd=cwd
        )
        return _paths_from_name_status(text)

    def uncommitted_paths(self, cwd: Path) -> tuple[str, ...]:
        status = self.status(cwd)
        return status.dirty_paths

    def diff_text(self, base: str, head: str, *, cwd: Path, limit: int = 400_000) -> str:
        result = self.git(["diff", f"{base}..{head}"], cwd=cwd)
        text = result.stdout
        if len(text) > limit:
            return text[:limit] + f"\n[diff truncated at {limit} characters]\n"
        return text

    def remote_head(self, branch: str, *, cwd: Path) -> str:
        """The SHA the remote actually holds, read after a fetch of that one ref."""
        self.git(["fetch", self._remote, branch], cwd=cwd)
        result = self.git(["rev-parse", f"refs/remotes/{self._remote}/{branch}"], cwd=cwd)
        return result.stdout.strip() if result.ok else ""

    # --- writing -----------------------------------------------------------

    def worktree_path(self, branch: str) -> Path:
        return self._worktree_root / _directory_name(branch)

    def ensure_worktree(self, branch: str, base_commit: str) -> Path:
        """The worktree for this branch, created at `base_commit` if it is new.

        Re-entrant on purpose. A second developer attempt on the same work
        order must land in the same tree as the first, because the correction
        loop is a continuation and not a fresh start; and a runner restarted
        mid-job must find the tree it left rather than refuse to continue.
        """
        path = self.worktree_path(branch)
        self._worktree_root.mkdir(parents=True, exist_ok=True)
        if path.is_dir() and (path / ".git").exists():
            self.assert_identity(path, branch)
            return path
        if path.exists():
            raise ConfigurationError(
                f"{path} exists and is not a git worktree; move it or point the "
                "runner at another --worktree-root"
            )
        if not self.commit_exists(base_commit):
            raise IntegrityFailure(
                f"base commit {base_commit} is not in {self._repo_root}. The work "
                "order names a commit this repository does not have, so this is not "
                "the repository the work was authorized against."
            )
        known = self.git(["rev-parse", "--verify", f"refs/heads/{branch}"])
        args = ["worktree", "add"]
        if known.ok:
            args += [str(path), branch]
        else:
            args += [str(path), "-b", branch, base_commit]
        self.require_git(args)
        self.assert_identity(path, branch)
        return path

    def assert_identity(self, path: Path, branch: str) -> None:
        """Refuse a tree that is not this repository's, or not on this branch."""
        if not path.is_dir():
            raise IntegrityFailure(f"{path}: the task worktree is not there")
        try:
            theirs = self.common_dir(path)
        except ConfigurationError as exc:
            raise IntegrityFailure(f"{path}: not a git working tree ({exc})") from exc
        ours = self.common_dir()
        if theirs != ours:
            raise IntegrityFailure(
                f"{path} belongs to {theirs}, not to the configured repository "
                f"{ours}. The runner will not execute a work order in another "
                "repository."
            )
        current = self.require_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
        if current != branch:
            raise IntegrityFailure(
                f"{path} is on branch {current!r}, and the work order authorizes "
                f"{branch!r}"
            )

    def commit_all(self, *, cwd: Path, message: str) -> str:
        """Stage everything in the task worktree and commit it. Returns the SHA.

        `add --all` is right here and wrong almost everywhere else: this tree
        exists for one work order, it started at the base commit, and anything
        in it arrived during this attempt. Staging selectively would hide a
        change from the authority check, which runs on the commit.
        """
        self.require_git(["add", "--all"], cwd=cwd)
        staged = self.git(["diff", "--cached", "--quiet"], cwd=cwd)
        if staged.ok:
            return ""  # nothing to commit; the caller reports an empty attempt
        result = self.git(["commit", "--message", message], cwd=cwd)
        if not result.ok:
            raise ConfigurationError(
                f"git commit failed ({result.exit_code}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return self.require_git(["rev-parse", "HEAD"], cwd=cwd)

    def push(self, branch: str, *, cwd: Path) -> CommandResult:
        """Push exactly this branch to the configured remote. Never forced."""
        return self.git(["push", "--set-upstream", self._remote, branch], cwd=cwd)

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def remote(self) -> str:
        return self._remote


def _paths_from_name_status(text: str) -> tuple[str, ...]:
    paths: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        code = fields[0][:1]
        if code in _RENAME_LIKE and len(fields) == 3:
            paths.update({fields[1].strip(), fields[2].strip()})
        elif len(fields) >= 2:
            paths.add(fields[1].strip())
    return tuple(sorted(path for path in paths if path))


def _directory_name(branch: str) -> str:
    """A directory name a branch cannot escape from.

    Slashes in a branch name would otherwise create nested directories under
    the worktree root, and `..` would leave it entirely.
    """
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in branch)
    return safe.strip("-.") or "task"


__all__ = ["GIT", "GitStatus", "Workspace"]
