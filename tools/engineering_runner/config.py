"""What the operator sets once, when they start the runner.

Everything here is a location or a ceiling. Nothing here is authority: the
runner cannot widen a work order by being started with a different flag, and
the fields that look like limits - the timeouts, the poll interval, the
per-run session cap - only ever make the runner do *less*.

## The four directories, and why they are four

| directory | holds | written by |
|---|---|---|
| `repo_root` | the repository the work is in | nobody: read-only to the runner |
| `state_dir` | Company OS state, the lifecycle's own history | the Company OS CLI |
| `runner_dir` | leases, run records, session transcripts | this package |
| `worktree_root` | one git worktree per work order | this package, through git |

`repo_root` and `state_dir` belong to Company OS and the CEO. The runner reads
the first and never writes it, and writes the second only by invoking the
Company OS CLI - never by touching a file under it directly. Keeping the
runner's own state in a fourth place is what makes "delete everything the
runner produced" a safe sentence.

## Why the repository is never the CEO's working tree

`worktree_root` defaults beside the repository rather than inside it, and a
job's work happens in `worktree_root/<branch>`. A coding session that runs in
the operator's active checkout can leave it dirty, on a different branch, or
half-way through an edit, and the operator finds out when their next command
behaves strangely. A per-job worktree costs a directory and removes the whole
class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

from .errors import ConfigurationError
from .resources import DEFAULT_TIER_MODELS, STANDARD, STRONGEST


# The CLI a coding session is launched through, by name. Resolved to an
# absolute path at launch, and recorded in the run record.
DEFAULT_BACKEND = "claude_code"

# Tool names a developer session is allowed to use. `Task` is absent and
# `disallowed_tools` names it explicitly: constitution rule 2 forbids nested
# agents, the receipt asserts none were used, and a session that cannot reach
# the tool cannot accidentally make that assertion false.
DEFAULT_DEVELOPER_TOOLS: tuple[str, ...] = (
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "TodoWrite",
)

# A reviewer reads. No writing tool, no shell, and the runner checks the
# worktree is byte-identical afterwards rather than trusting this list.
DEFAULT_REVIEWER_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")

DEFAULT_DISALLOWED_TOOLS: tuple[str, ...] = ("Task", "WebSearch", "WebFetch")


@dataclass(frozen=True)
class RunnerConfig:
    """Where the runner works and how long it is willing to wait."""

    repo_root: Path
    state_dir: Path
    runner_dir: Path
    worktree_root: Path
    operator: str = "MGI"
    backend: str = DEFAULT_BACKEND
    reviewer_backend: str = ""
    # An explicit model pins the session to it and the recommended tier is
    # recorded and not applied. Left empty - which is the normal case - the
    # model comes from the tier Company OS recommended, so the operator does
    # not restate a routing decision the company already made per job.
    developer_model: str = ""
    reviewer_model: str = ""
    # Which vendor model each tier means. The company never names a model;
    # this is the one place a tier becomes one, and aliases are used so the
    # account's current model of each strength is what runs.
    standard_model: str = DEFAULT_TIER_MODELS[STANDARD]
    strongest_model: str = DEFAULT_TIER_MODELS[STRONGEST]
    # Whether to apply the recommendation at all. False records it and runs
    # the operator's own settings, which is a debugging seam and not a way to
    # spend more: the ceilings still bind, because they come from the config's
    # own timeouts as before.
    apply_resource_strategy: bool = True
    python_executable: str = field(default_factory=lambda: sys.executable)
    remote: str = "origin"
    poll_interval_s: float = 20.0
    lease_seconds: float = 3600.0
    developer_timeout_s: float = 3600.0
    reviewer_timeout_s: float = 1800.0
    test_timeout_s: float = 1800.0
    git_timeout_s: float = 300.0
    gate_timeout_s: float = 900.0
    control_plane_timeout_s: float = 300.0
    max_stage_retries: int = 1
    push: bool = True
    # Which suites the gate stage runs and reports. Empty means the set
    # `company/integration/suites.py` requires, which is the only set that can
    # produce a READY verdict: supplying fewer makes the gate answer
    # INSUFFICIENT_EVIDENCE, so this is a debugging seam and not a way to
    # lower the bar.
    gate_suites: tuple[str, ...] = ()
    developer_tools: tuple[str, ...] = DEFAULT_DEVELOPER_TOOLS
    reviewer_tools: tuple[str, ...] = DEFAULT_REVIEWER_TOOLS
    disallowed_tools: tuple[str, ...] = DEFAULT_DISALLOWED_TOOLS

    def tier_models(self) -> dict[str, str]:
        return {STANDARD: self.standard_model, STRONGEST: self.strongest_model}

    def __post_init__(self) -> None:
        for name in ("repo_root", "state_dir", "runner_dir", "worktree_root"):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        if not self.repo_root.is_dir():
            raise ConfigurationError(f"--repo-root {self.repo_root}: not a directory")
        if not (self.repo_root / ".git").exists():
            raise ConfigurationError(
                f"--repo-root {self.repo_root}: not a git working tree. The runner "
                "commits and pushes, so it needs a real checkout."
            )
        if not self.operator.strip():
            raise ConfigurationError("--operator: a runner records who started it")
        for name in (
            "poll_interval_s",
            "lease_seconds",
            "developer_timeout_s",
            "reviewer_timeout_s",
            "test_timeout_s",
            "git_timeout_s",
            "gate_timeout_s",
            "control_plane_timeout_s",
        ):
            if float(getattr(self, name)) <= 0:
                raise ConfigurationError(f"{name} must be positive")
        if self.max_stage_retries < 0:
            raise ConfigurationError("max_stage_retries must be zero or more")

    @property
    def reviewer_backend_name(self) -> str:
        """The reviewer's backend; the developer's unless one was named."""
        return self.reviewer_backend or self.backend

    def ensure_directories(self) -> None:
        self.runner_dir.mkdir(parents=True, exist_ok=True)
        self.worktree_root.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": str(self.repo_root),
            "state_dir": str(self.state_dir),
            "runner_dir": str(self.runner_dir),
            "worktree_root": str(self.worktree_root),
            "operator": self.operator,
            "backend": self.backend,
            "reviewer_backend": self.reviewer_backend_name,
            "developer_model": self.developer_model,
            "reviewer_model": self.reviewer_model,
            "standard_model": self.standard_model,
            "strongest_model": self.strongest_model,
            "apply_resource_strategy": self.apply_resource_strategy,
            "remote": self.remote,
            "push": self.push,
            "poll_interval_s": self.poll_interval_s,
            "lease_seconds": self.lease_seconds,
        }


__all__ = [
    "DEFAULT_BACKEND",
    "DEFAULT_DEVELOPER_TOOLS",
    "DEFAULT_DISALLOWED_TOOLS",
    "DEFAULT_REVIEWER_TOOLS",
    "RunnerConfig",
]
