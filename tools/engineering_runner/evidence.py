"""Measuring what happened, and writing it down in the contracts that exist.

This module is where the runner's two jobs meet: running the commands a human
used to run by hand, and turning what it observed into the records Company OS
already knows how to validate. It invents no record type. A `SessionReceipt`
and a `ReviewerAttestation` carry everything a result needs to be attributable,
so the runner fills those in rather than adding a third.

## The split between measured and narrated

| field | comes from |
|---|---|
| `commit_sha`, `base_commit`, `branch` | git |
| `files_changed` | `git diff --name-status`, plus the porcelain status |
| `remote_branch_sha`, `remote_verified` | the remote ref, after a fetch |
| `working_tree_clean` | `git status --porcelain` |
| `tests` | pytest's own exit code and summary line |
| `usage` | the backend's reported cost and token counts |
| `summary`, `invariants_preserved`, `unresolved_risks`, `evidence` | the session |

Nothing in the left column is ever taken from the session, and nothing in the
right column is ever invented by the runner. A receipt built any other way is
either unfalsifiable or fiction.

## Why a test result carries the commit it ran at

`assert_tests_describe` refuses a run recorded at a different SHA than the one
being reported. Without it, a green run from before the last edit reads as
evidence for the edit - which is the single easiest way for an automated loop
to certify work nobody tested. The gate has the same rule one level up
(`stale_against`), and this is its counterpart inside the attempt.

## Suite evidence is reported, never asserted

`suite_evidence` writes what pytest said, including a failure. The gate decides
what a failure means; a runner that suppressed one would be deciding for it,
and `health.required_suites_pass` would stop being able to say no.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .authorization import AuthorityEnvelope, normalise_path
from .backends import SessionOutcome
from .errors import IntegrityFailure
from .process import CommandRunner


# pytest's own last line. Both shapes appear: with a duration and, under
# `-p no:cacheprovider` or on an empty run, without one.
_SUMMARY = re.compile(r"^=+\s+(?P<body>.*?)\s+=+$")
_COUNT = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed|error|errors|skipped|xfailed|xpassed|deselected|warning|warnings)")

# The suites `company/integration/suites.py` requires before it will call the
# boundary READY. Restated here because this package may not import it, and
# `doctor` prints the list so a drift is visible rather than silent.
REQUIRED_SUITES: tuple[str, ...] = (
    "tests/test_company_analytics.py",
    "tests/test_company_dashboard.py",
    "tests/test_company_execution_transport.py",
    "tests/test_company_finance.py",
    "tests/test_company_integration_gate.py",
    "tests/test_company_org_intelligence.py",
    "tests/test_company_os_ai_platform.py",
    "tests/test_company_os_capsules.py",
    "tests/test_company_os_knowledge.py",
    "tests/test_company_runtime.py",
    "tests/test_company_workforce.py",
)


@dataclass(frozen=True)
class TestRun:
    """One test command, the commit it ran at, and what pytest said."""

    command: str
    argv: tuple[str, ...]
    commit: str
    exit_code: int
    passed: int
    failed: int
    errors: int
    skipped: int
    summary: str
    duration_s: float
    timed_out: bool

    @property
    def green(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "argv": list(self.argv),
            "commit": self.commit,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "summary": self.summary,
            "duration_s": round(self.duration_s, 3),
            "timed_out": self.timed_out,
            "green": self.green,
        }

    def reported(self) -> dict[str, Any]:
        """The `ReportedTest` shape a receipt carries."""
        return {"command": self.command, "passed": self.green, "summary": self.summary}


def run_tests(
    runner: CommandRunner,
    *,
    python_executable: str,
    worktree: Path,
    commands: Sequence[str],
    commit: str,
    timeout_s: float,
) -> tuple[TestRun, ...]:
    """Run each required test command at `commit`, in the task worktree.

    A command is a pytest target as the work order writes it - a path, or a
    path plus `-k expression`. It is split on whitespace and passed as argv,
    never through a shell: the work order names tests, and a work order that
    could name a shell pipeline would be naming a command instead.
    """
    runs: list[TestRun] = []
    for command in commands:
        argv = [python_executable, "-m", "pytest", *command.split(), "-q", "--no-header"]
        result = runner.run(argv, cwd=worktree, timeout_s=timeout_s)
        counts = _counts(result.stdout)
        runs.append(
            TestRun(
                command=command,
                argv=tuple(argv),
                commit=commit,
                exit_code=result.exit_code,
                passed=counts.get("passed", 0),
                failed=counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0),
                errors=counts.get("error", 0) + counts.get("errors", 0),
                skipped=counts.get("skipped", 0),
                summary=_summary_line(result.stdout)
                or (f"timed out after {timeout_s:.0f}s" if result.timed_out else "no summary line"),
                duration_s=result.duration_s,
                timed_out=result.timed_out,
            )
        )
    return tuple(runs)


def assert_tests_describe(runs: Iterable[TestRun], commit: str) -> None:
    """Refuse any recorded run that was not made at `commit`."""
    for run in runs:
        if run.commit != commit:
            raise IntegrityFailure(
                f"test evidence for {run.command!r} was recorded at {run.commit[:12]} "
                f"and the implementation is {commit[:12]}. A result from another "
                "commit describes another tree and is not evidence for this one."
            )


def suite_evidence(
    runs: Sequence[TestRun],
    *,
    observed_on: dt.date,
    reported_by: str,
    max_age_days: int = 7,
) -> dict[str, Any]:
    """The `--suite-evidence` file the integration gate reads."""
    return {
        "max_age_days": max_age_days,
        "results": [
            {
                "suite": run.command,
                "passed": run.green,
                "observed_on": observed_on.isoformat(),
                "reported_by": reported_by,
                "selected": run.passed + run.failed + run.skipped,
                "failed": 0 if run.green else max(run.failed, 1),
                "note": run.summary[:280],
                "company_os": True,
            }
            for run in runs
        ],
    }


@dataclass(frozen=True)
class GitObservation:
    """What the repository says about one developer attempt."""

    branch: str
    base_commit: str
    commit_sha: str
    remote_branch_sha: str
    remote_verified: bool
    working_tree_clean: bool
    files_changed: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "base_commit": self.base_commit,
            "commit_sha": self.commit_sha,
            "remote_branch_sha": self.remote_branch_sha,
            "remote_verified": self.remote_verified,
            "working_tree_clean": self.working_tree_clean,
            "files_changed": list(self.files_changed),
        }


def build_receipt(
    envelope: AuthorityEnvelope,
    *,
    observation: GitObservation,
    tests: Sequence[TestRun],
    narrative: Mapping[str, Any],
    session: SessionOutcome,
    completed_at: dt.datetime,
    accepted: bool,
    rejection_reason: str = "",
) -> dict[str, Any]:
    """One `SessionReceipt`, as the JSON its own `from_mapping` decodes.

    Built here rather than by the session, because every field that could be
    checked has been checked and a session that wrote its own receipt would be
    supplying the answers to its own audit.
    """
    assert_tests_describe(tests, observation.commit_sha or observation.base_commit)
    context_used = tuple(
        ref for ref in _strings(narrative.get("context_refs_used")) if ref in envelope.context_refs
    )
    receipt: dict[str, Any] = {
        "task_id": envelope.work_order_id,
        "packet_fingerprint": envelope.packet_fingerprint,
        "packet_attempt": envelope.packet_attempt,
        "authority_fingerprint": envelope.authority_fingerprint,
        "outcome": "accepted" if accepted else "rejected",
        "summary": str(narrative.get("summary", "")).strip(),
        "branch": observation.branch,
        "base_commit": observation.base_commit,
        "commit_sha": observation.commit_sha,
        "remote_branch_sha": observation.remote_branch_sha,
        "remote_verified": observation.remote_verified,
        "merge_performed": False,
        "working_tree_clean": observation.working_tree_clean,
        "files_changed": list(observation.files_changed),
        "tests": [run.reported() for run in tests],
        "dependencies_added": [],
        "invariants_preserved": _strings(narrative.get("invariants_preserved"))[:32],
        "unresolved_risks": _strings(narrative.get("unresolved_risks"))[:32],
        "evidence": _evidence(narrative, observation),
        "artifacts": [],
        "context_refs_used": list(context_used),
        "context_usage_reported": bool(context_used),
        "next_owner": "",
        "rejection_reason": rejection_reason or str(narrative.get("rejection_reason", "")),
        "notes": str(narrative.get("notes", "")),
        "completed_at": completed_at.isoformat(),
        "usage": _usage(session),
        "executor": _executor(session.backend),
        "subagents_used": 0,
        "no_subagents": True,
        "version": 1,
    }
    if not accepted and not receipt["rejection_reason"].strip():
        receipt["rejection_reason"] = (
            "the attempt did not satisfy the work order; see the recorded findings"
        )
    return receipt


def build_attestation(
    envelope: AuthorityEnvelope,
    *,
    review_id: str,
    reviewer: str,
    reviewed_packet_fingerprint: str,
    receipt_fingerprint: str,
    reviewed_on: dt.date,
    reported: Mapping[str, Any],
) -> dict[str, Any]:
    """One `ReviewerAttestation`, from the reviewer's judgment and nothing else.

    The identifiers - which work order, which packet, which receipt, which day
    - are the runner's, because they are facts about the run. The verdict, the
    criteria and the findings are the reviewer's, because they are judgment and
    the runner has none.

    `reviewed_packet_fingerprint` is the **developer's** packet, not the
    reviewer's. A review answers the attempt, and `company.engineering review`
    looks the receipt up by that pair; passing the reviewer's own read-only
    packet here would name a packet no receipt ever answered.
    """
    criteria = []
    for item in reported.get("criteria", ()) or ():
        if not isinstance(item, Mapping):
            continue
        criteria.append(
            {
                "criterion": str(item.get("criterion", "")).strip(),
                "satisfied": bool(item.get("satisfied", False)),
                "evidence_ref": str(item.get("evidence_ref", "")).strip(),
            }
        )
    findings = []
    for index, item in enumerate(reported.get("findings", ()) or (), start=1):
        if not isinstance(item, Mapping):
            continue
        findings.append(
            {
                "finding_id": _finding_id(item.get("finding_id"), review_id, index),
                "severity": str(item.get("severity", "advisory")).strip() or "advisory",
                "summary": str(item.get("summary", "")).strip(),
                "evidence_ref": str(item.get("evidence_ref", "")).strip(),
                "deterministic": False,
            }
        )
    return {
        "review_id": review_id,
        "work_order_id": envelope.work_order_id,
        "work_order_fingerprint": envelope.work_order_fingerprint,
        "reviewer": reviewer,
        "packet_fingerprint": reviewed_packet_fingerprint,
        "receipt_fingerprint": receipt_fingerprint,
        "verdict": str(reported.get("verdict", "")).strip(),
        "reviewed_on": reviewed_on.isoformat(),
        "criteria": criteria,
        "findings": findings,
        "evidence": _strings(reported.get("evidence"))[:32],
        "changed_paths_reviewed": _strings(reported.get("changed_paths_reviewed"))[:64],
        "notes": str(reported.get("notes", "")),
        "version": 1,
    }


def read_json_object(path: Path, what: str) -> dict[str, Any]:
    if not path.is_file():
        raise IntegrityFailure(f"{what}: {path} was never written")
    return parse_json_object(path.read_text(encoding="utf-8"), what)


def parse_json_object(text: str, what: str) -> dict[str, Any]:
    """Decode one JSON object, tolerating a fenced block around it.

    A session told to answer with JSON and nothing else usually does. When it
    does not, the deviation is almost always a markdown fence, and refusing
    that costs a whole session to re-run for a formatting habit. Anything
    beyond a fence is refused.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
    body = body.strip()
    if not body.startswith("{"):
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            raise IntegrityFailure(f"{what}: no JSON object in the answer")
        body = body[start : end + 1]
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise IntegrityFailure(f"{what}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise IntegrityFailure(f"{what}: expected a JSON object")
    return dict(data)


def _evidence(narrative: Mapping[str, Any], observation: GitObservation) -> list[str]:
    refs = [ref for ref in _strings(narrative.get("evidence")) if ref]
    if observation.commit_sha:
        commit_ref = f"commit:{observation.commit_sha}"
        if commit_ref not in refs:
            refs.append(commit_ref)
    for path in observation.files_changed:
        if len(refs) >= 32:
            break
        if path not in refs:
            refs.append(path)
    return refs[:32]


def _usage(session: SessionOutcome) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "passes": 1,
        "retries": 0,
        "usage_unit": "token" if session.input_units is not None else "unknown",
        "provider": session.provider,
        "model": session.model,
        "duration_s": round(session.duration_s, 3),
    }
    if session.input_units is not None:
        usage["input_units"] = session.input_units
    if session.output_units is not None:
        usage["output_units"] = session.output_units
    if session.cache_read_units is not None:
        usage["cache_hits"] = session.cache_read_units
    if session.turns is not None:
        usage["tool_calls"] = session.turns
    if session.cost_usd is not None:
        usage["provider_cost"] = f"{session.cost_usd:.6f}"
        usage["provider_cost_currency"] = "USD"
    return usage


def _executor(backend: str) -> str:
    return {"claude_code": "claude_code", "codex": "codex"}.get(backend, "future_adapter")


def _finding_id(value: object, review_id: str, index: int) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    cleaned = cleaned.strip("-.")
    if len(cleaned) >= 3:
        return cleaned[:64]
    return f"{review_id}-f{index:02d}"[:64]


def _strings(values: Any) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _summary_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        match = _SUMMARY.match(line.strip())
        if match:
            return match.group("body").strip()[:280]
    for line in reversed(text.splitlines()):
        if _COUNT.search(line):
            return line.strip()[:280]
    return ""


def _counts(text: str) -> dict[str, int]:
    line = _summary_line(text)
    counts: dict[str, int] = {}
    for match in _COUNT.finditer(line):
        counts[match.group("label")] = int(match.group("count"))
    return counts


def normalised_changes(paths: Iterable[str]) -> tuple[str, ...]:
    """Repository-relative POSIX paths, sorted and de-duplicated."""
    return tuple(sorted({normalise_path(item, "changed path") for item in paths}))


__all__ = [
    "REQUIRED_SUITES",
    "GitObservation",
    "TestRun",
    "assert_tests_describe",
    "build_attestation",
    "build_receipt",
    "normalised_changes",
    "parse_json_object",
    "read_json_object",
    "run_tests",
    "suite_evidence",
]
