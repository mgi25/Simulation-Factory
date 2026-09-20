"""The actuator Company OS is not allowed to be.

## Why this package is here rather than in `company/`

`production.no_publishing_capability` is a **required** integration-gate check,
and `company/integration/boundary.py` implements it as: no Company OS module
may import `subprocess`, `multiprocessing` or `pty`, or call `os.system`,
`os.popen`, `os.fork`, `os.exec*`, `os.spawn*` or `os.posix_spawn`. So Company
OS cannot run pytest, cannot run git, and cannot launch a coding session - not
"has not been wired up yet", but *may not*, and a version that did would fail
its own gate.

That policy is correct and this milestone does not touch it. The missing piece
was never permission; it was a second process. This package is that process:
the execution plane, outside the control plane, doing the machine actions a
person used to do by hand and handing the evidence back through the contracts
that already exist.

    Company OS (control plane)        this package (execution plane)
    ---------------------------       -------------------------------
    CEO objective, authorization      launch a coding session
    work order, the authority ceiling create the task worktree
    capability routing                run git
    context selection                 run pytest
    lifecycle state                   launch a separate review session
    receipt validation                run the integration gate CLI
    review adjudication               collect and sanitize the evidence
    gate interpretation
    the CEO result

The arrow runs one way. The runner **receives** authority and never creates
it: every path it may write, every branch it may touch and every test it must
run comes out of a work order it cannot edit, and the one thing it produces -
evidence - is validated by the side that issued the authority.

## The boundary is a command line, not an import

`tools/` is a declared production root and
`architecture.production_does_not_import_company_os` is required, so no module
here imports any of the four control-plane roots - not in a module, not in a
test, not under `TYPE_CHECKING`. The whole dependency is `controlplane.py`
invoking `python -m company.engineering <stage>` and reading its JSON. That is
the same split `tools/youtube_fetch` uses for the same reason, and it has the
same useful consequence: every stage the runner drives is a stage a person can
drive by typing the same command.

The four roots are deliberately not spelled out anywhere in this package: a
capsule-layer test greps the raw text of every module under `tools/` for them,
and a docstring quoting them reads to that test exactly like a module importing
them. `tests/test_external_engineering_runner.py` names them, assembled from
fragments, and asserts the absence.

## What it cannot do

| | why not |
|---|---|
| widen a work order | the envelope is parsed from the brief; nothing here writes one |
| approve | `ControlPlane` has no `decide`, and the CLI has no `approve` |
| merge | `Workspace` has no merge, rebase, tag or force-push |
| publish | one outward call, `push`, of one branch to one remote |
| review its own work | the developer and reviewer session ids must differ, and Company OS routes them to different employees |
| certify itself | it computes no readiness and no review outcome; both are read from replies it did not produce |

## Standard library only

`subprocess`, `json`, `pathlib`, `hashlib`, `uuid`, `socket`, `re`. No HTTP
client, no SDK, no agent framework. `requirements.txt` is untouched, which is
what keeps `health.no_new_dependency` green.

## The modules

| module | holds |
|---|---|
| `config` | where the operator points the runner, and how long it waits |
| `controlplane` | the only place that speaks to Company OS |
| `workspace` | the per-work-order git worktree, and every git call |
| `authorization` | the authority envelope, and the checks that outlive the prompt |
| `backends` | `CodingBackend`, and the adapters for Claude Code and Codex |
| `briefs` | the packet rendered as instructions, with nothing added |
| `evidence` | running tests, and building the receipt and the attestation |
| `queue` | leases, run directories and the append-only outcome log |
| `runner` | the loop |
| `redaction` | what never reaches a persisted transcript |
| `repo_map` | a cheap `ast`-built map of the worktree, queried into a briefing |
"""

from __future__ import annotations

from .authorization import (
    AuthorityEnvelope,
    AuthorityVerdict,
    PathRules,
    digest_paths,
    normalise_path,
    protected_drift,
    verify_developer_changes,
    verify_reviewer_left_no_trace,
)
from .backends import (
    CLAUDE_CODE,
    CODEX,
    ClaudeCodeBackend,
    CodexBackend,
    CodingBackend,
    SessionOutcome,
    SessionRequest,
    build_backend,
    executor_hint,
)
from .briefs import developer_instructions, repair_instructions, review_instructions
from .config import RunnerConfig
from .controlplane import ControlPlane, StageReply
from .errors import (
    AuthorityViolation,
    BackendFailure,
    BackendUnavailable,
    ClaimUnavailable,
    ConfigurationError,
    ControlPlaneRefusal,
    IntegrityFailure,
    RunnerError,
)
from .evidence import (
    MAX_REF_CHARS,
    DEPENDENCY_MANIFESTS,
    REQUIRED_SUITES,
    GitObservation,
    TestRun,
    assert_reviewer_report,
    assert_tests_describe,
    build_attestation,
    build_receipt,
    declared_dependencies,
    dependencies_added,
    manifest_changes,
    parse_json_object,
    run_tests,
    suite_evidence,
)
from .process import CommandResult, CommandRunner, resolve_executable
from .queue import Lease, RunStore, task_directory_name
from .repo_map import (
    ModuleMap,
    QueryHit,
    RepoMap,
    build_and_cache,
    build_repo_map,
    load_or_build,
)
from .repo_map import query as query_repo_map
from .redaction import (
    REDACTED,
    Redactor,
    child_environment,
    forwarded_names,
    sanitize_json_file,
    secret_values,
)
from .runner import ACTIONABLE, EngineeringRunner, RunReport, StageRecord
from .workspace import GitStatus, Workspace


__all__ = [
    "ACTIONABLE",
    "CLAUDE_CODE",
    "CODEX",
    "MAX_REF_CHARS",
    "REDACTED",
    "DEPENDENCY_MANIFESTS",
    "REQUIRED_SUITES",
    "AuthorityEnvelope",
    "AuthorityVerdict",
    "AuthorityViolation",
    "BackendFailure",
    "BackendUnavailable",
    "ClaimUnavailable",
    "ClaudeCodeBackend",
    "CodexBackend",
    "CodingBackend",
    "CommandResult",
    "CommandRunner",
    "ConfigurationError",
    "ControlPlane",
    "ControlPlaneRefusal",
    "EngineeringRunner",
    "GitObservation",
    "GitStatus",
    "IntegrityFailure",
    "Lease",
    "ModuleMap",
    "PathRules",
    "QueryHit",
    "Redactor",
    "RepoMap",
    "RunReport",
    "RunStore",
    "RunnerConfig",
    "RunnerError",
    "SessionOutcome",
    "SessionRequest",
    "StageRecord",
    "StageReply",
    "TestRun",
    "Workspace",
    "assert_reviewer_report",
    "assert_tests_describe",
    "build_and_cache",
    "build_attestation",
    "build_backend",
    "build_receipt",
    "build_repo_map",
    "child_environment",
    "declared_dependencies",
    "dependencies_added",
    "developer_instructions",
    "digest_paths",
    "executor_hint",
    "forwarded_names",
    "load_or_build",
    "manifest_changes",
    "normalise_path",
    "parse_json_object",
    "protected_drift",
    "query_repo_map",
    "repair_instructions",
    "resolve_executable",
    "review_instructions",
    "run_tests",
    "sanitize_json_file",
    "secret_values",
    "suite_evidence",
    "task_directory_name",
    "verify_developer_changes",
    "verify_reviewer_left_no_trace",
]
