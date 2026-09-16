"""What an external session returns, and the checks that decide whether to believe it.

A receipt is testimony from a process this one did not run. The whole design
follows from that: it is decoded strictly, validated against the packet it
claims to answer, and recorded whether or not it passes.

## Refusing an escalation of authority

The realistic escalation vector is not a forged field, it is an *extra* one - a
receipt that arrives carrying `autonomy_level: 5`, `ceo_approved: true`, or
`production_write: true` in the hope that some later reader honours it. So
`from_mapping` refuses any key the schema does not name, the way
`ExecutionPolicy.from_mapping` refuses an unknown policy key. A receipt cannot
grant itself anything, because there is no field it can arrive in.

The fields it does carry are testimony about work, never grants of permission:
the packet names the employee, the branch and the paths, and validation
compares the receipt with the packet rather than the other way round.

## Two different treatments of the no-subagent rule

`no_subagents=false` is a *claim* that constitution rule 2 does not apply.
Construction refuses it outright - there is no such receipt.

`subagents_used=1` is a *report of fact*. It must be constructible, or the one
receipt that proves a violation happened could not be written down. It fails
validation, it is refused at ingestion, and the file stays in the history as
the audit trail. `ai_platform/usage.py` makes the same distinction for the same
reason.

## Git evidence

Shape is checked here and always: a commit SHA looks like a Git object name,
the branch equals the packet's, `remote_verified` is asserted rather than
assumed, and `merge_performed` is fatal in any outcome. Substance - whether the
remote really is at that SHA - needs a clone, and lives in `git_evidence.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any

from ai_platform.policy import SubagentPolicyViolation
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from ai_platform.usage import Outcome, UsageUnit
from company.validation.errors import ValidationError
from company.validation.no_subagents import collect_no_subagent_violations

from .git_evidence import is_git_sha
from .packets import ExecutorHint, SessionPacket
from .path_scope import PathScopeVerdict, normalise_path


RECEIPT_VERSION = 1

_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


@dataclass(frozen=True)
class ReportedTest:
    """One test command an external session says it ran, and how it ended."""

    command: str
    passed: bool
    summary: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not self.command.strip():
            raise ValidationError("receipt.tests[].command must be a non-empty string")
        if "\n" in self.command or "\r" in self.command:
            raise ValidationError(
                "receipt.tests[].command is one line; paste the command, not its output"
            )
        if not isinstance(self.passed, bool):
            raise ValidationError("receipt.tests[].passed must be a boolean")
        if not isinstance(self.summary, str):
            raise ValidationError("receipt.tests[].summary must be a string")


@dataclass(frozen=True)
class ReceiptUsage:
    """Resource information, exactly as optional as `ResourceUsageRecord` makes it."""

    passes: int = 1
    retries: int = 0
    cache_hits: int = 0
    retrieval_hits: int = 0
    tool_calls: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    usage_unit: UsageUnit = UsageUnit.UNKNOWN
    duration_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("passes", "retries", "cache_hits", "retrieval_hits"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(
                    f"receipt.usage.{name} must be a non-negative integer"
                )
        if self.passes < 1:
            raise ValidationError("receipt.usage.passes describes at least one pass")
        for name in ("tool_calls", "input_units", "output_units"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(
                    f"receipt.usage.{name} must be a non-negative integer or null"
                )
        if not isinstance(self.usage_unit, UsageUnit):
            raise ValidationError("receipt.usage.usage_unit must be a UsageUnit value")
        if self.duration_s is not None:
            if isinstance(self.duration_s, bool) or not isinstance(
                self.duration_s, (int, float)
            ):
                raise ValidationError("receipt.usage.duration_s must be a number or null")
            object.__setattr__(self, "duration_s", float(self.duration_s))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ReceiptUsage":
        if not isinstance(data, Mapping):
            raise ValidationError("receipt.usage must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise ValidationError(
                "receipt.usage has unknown field(s): " + ", ".join(unknown)
            )
        values = dict(data)
        unit = values.pop("usage_unit", UsageUnit.UNKNOWN.value)
        if not isinstance(unit, str):
            raise ValidationError("receipt.usage.usage_unit must be a string")
        try:
            usage_unit = UsageUnit(unit)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in UsageUnit)
            raise ValidationError(
                f"receipt.usage.usage_unit must be one of: {allowed}"
            ) from exc
        return cls(usage_unit=usage_unit, **values)


@dataclass(frozen=True)
class SessionReceipt:
    """One external session's report on one packet."""

    task_id: str
    packet_fingerprint: str
    outcome: Outcome
    summary: str = ""
    branch: str = ""
    base_commit: str = ""
    commit_sha: str = ""
    remote_branch_sha: str = ""
    remote_verified: bool = False
    merge_performed: bool = False
    working_tree_clean: bool | None = None
    files_changed: tuple[str, ...] = ()
    tests: tuple[ReportedTest, ...] = ()
    dependencies_added: tuple[str, ...] = ()
    invariants_preserved: tuple[str, ...] = ()
    unresolved_risks: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    context_refs_used: tuple[str, ...] = ()
    next_owner: str = ""
    rejection_reason: str = ""
    notes: str = ""
    usage: ReceiptUsage = field(default_factory=ReceiptUsage)
    executor: ExecutorHint = ExecutorHint.UNSPECIFIED
    subagents_used: int = 0
    no_subagents: bool = True
    version: int = RECEIPT_VERSION

    def __post_init__(self) -> None:
        issues: list[str] = []
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            issues.append("receipt.task_id must be a non-empty string")
        if not isinstance(self.packet_fingerprint, str) or not _FINGERPRINT.fullmatch(
            self.packet_fingerprint
        ):
            issues.append(
                "receipt.packet_fingerprint must be a 16-character lowercase hex digest"
            )
        if not isinstance(self.outcome, Outcome):
            issues.append("receipt.outcome must be an Outcome value")
        for name in (
            "summary",
            "branch",
            "base_commit",
            "commit_sha",
            "remote_branch_sha",
            "next_owner",
            "rejection_reason",
            "notes",
        ):
            if not isinstance(getattr(self, name), str):
                issues.append(f"receipt.{name} must be a string")
        for name in ("remote_verified", "merge_performed"):
            if not isinstance(getattr(self, name), bool):
                issues.append(f"receipt.{name} must be a boolean")
        if self.working_tree_clean is not None and not isinstance(
            self.working_tree_clean, bool
        ):
            issues.append("receipt.working_tree_clean must be a boolean or null")
        for name in (
            "files_changed",
            "dependencies_added",
            "invariants_preserved",
            "unresolved_risks",
            "evidence",
            "artifacts",
            "context_refs_used",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                issues.append(f"receipt.{name} must be a tuple of non-empty strings")
        if not isinstance(self.tests, tuple) or any(
            not isinstance(item, ReportedTest) for item in self.tests
        ):
            issues.append("receipt.tests must be a tuple of ReportedTest values")
        if not isinstance(self.usage, ReceiptUsage):
            issues.append("receipt.usage must be a ReceiptUsage value")
        if not isinstance(self.executor, ExecutorHint):
            issues.append("receipt.executor must be an ExecutorHint value")
        if (
            isinstance(self.subagents_used, bool)
            or not isinstance(self.subagents_used, int)
            or self.subagents_used < 0
        ):
            issues.append("receipt.subagents_used must be a non-negative integer")
        if self.version != RECEIPT_VERSION:
            issues.append(f"receipt.version must be {RECEIPT_VERSION}")
        if issues:
            raise ValidationError(issues)
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "receipt.no_subagents must be true; a returned result does not amend "
                "constitution rule 2"
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @property
    def failing_tests(self) -> tuple[str, ...]:
        return tuple(test.command for test in self.tests if not test.passed)

    @property
    def test_commands(self) -> tuple[str, ...]:
        return tuple(test.command for test in self.tests)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SessionReceipt":
        """Decode a returned receipt, refusing every field the schema does not name."""
        if not isinstance(data, Mapping):
            raise ValidationError("receipt must be a mapping")
        issues = collect_no_subagent_violations(data, path="receipt")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            issues.append(
                "receipt has unknown field(s): "
                + ", ".join(unknown)
                + ". A receipt reports work; it does not grant authority, so a field "
                "outside the schema is refused rather than ignored."
            )
        if issues:
            raise ValidationError(issues)

        outcome = data.get("outcome")
        if not isinstance(outcome, str):
            raise ValidationError("receipt.outcome must be a string")
        try:
            parsed_outcome = Outcome(outcome)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in Outcome)
            raise ValidationError(f"receipt.outcome must be one of: {allowed}") from exc

        executor = data.get("executor", ExecutorHint.UNSPECIFIED.value)
        if not isinstance(executor, str):
            raise ValidationError("receipt.executor must be a string")
        try:
            parsed_executor = ExecutorHint(executor)
        except ValueError as exc:
            allowed = ", ".join(str(item.value) for item in ExecutorHint)
            raise ValidationError(f"receipt.executor must be one of: {allowed}") from exc

        tests = data.get("tests", [])
        if not isinstance(tests, (list, tuple)):
            raise ValidationError("receipt.tests must be a list")
        parsed_tests = []
        for index, item in enumerate(tests):
            if not isinstance(item, Mapping):
                raise ValidationError(f"receipt.tests[{index}] must be a mapping")
            extra = sorted(set(item) - {"command", "passed", "summary"})
            if extra:
                raise ValidationError(
                    f"receipt.tests[{index}] has unknown field(s): " + ", ".join(extra)
                )
            parsed_tests.append(
                ReportedTest(
                    command=item.get("command", ""),
                    passed=item.get("passed", False),
                    summary=item.get("summary", ""),
                )
            )

        return cls(
            task_id=_string(data, "task_id"),
            packet_fingerprint=_string(data, "packet_fingerprint"),
            outcome=parsed_outcome,
            summary=_optional_string(data, "summary"),
            branch=_optional_string(data, "branch"),
            base_commit=_optional_string(data, "base_commit"),
            commit_sha=_optional_string(data, "commit_sha"),
            remote_branch_sha=_optional_string(data, "remote_branch_sha"),
            remote_verified=_boolean(data, "remote_verified", False),
            merge_performed=_boolean(data, "merge_performed", False),
            working_tree_clean=_optional_boolean(data, "working_tree_clean"),
            files_changed=_string_tuple(data.get("files_changed"), "files_changed"),
            tests=tuple(parsed_tests),
            dependencies_added=_string_tuple(
                data.get("dependencies_added"), "dependencies_added"
            ),
            invariants_preserved=_string_tuple(
                data.get("invariants_preserved"), "invariants_preserved"
            ),
            unresolved_risks=_string_tuple(
                data.get("unresolved_risks"), "unresolved_risks"
            ),
            evidence=_string_tuple(data.get("evidence"), "evidence"),
            artifacts=_string_tuple(data.get("artifacts"), "artifacts"),
            context_refs_used=_string_tuple(
                data.get("context_refs_used"), "context_refs_used"
            ),
            next_owner=_optional_string(data, "next_owner"),
            rejection_reason=_optional_string(data, "rejection_reason"),
            notes=_optional_string(data, "notes"),
            usage=ReceiptUsage.from_mapping(data.get("usage", {})),
            executor=parsed_executor,
            subagents_used=_integer(data.get("subagents_used", 0), "subagents_used"),
            no_subagents=_boolean(data, "no_subagents", True),
            version=_integer(data.get("version", RECEIPT_VERSION), "version"),
        )


@dataclass(frozen=True)
class ReceiptValidation:
    """Why a receipt was accepted, or every reason it was not."""

    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    path_verdict: PathScopeVerdict

    @property
    def ok(self) -> bool:
        return not self.failures

    def reason(self) -> str:
        return "; ".join(self.failures)


def validate_receipt(packet: SessionPacket, receipt: SessionReceipt) -> ReceiptValidation:
    """Check one receipt against the packet it claims to answer.

    Deterministic and offline: it compares two records and reads nothing else.
    Failures are collected rather than raised, so one pass reports everything
    wrong with an attempt instead of the first thing.
    """
    failures: list[str] = []
    warnings: list[str] = []

    if receipt.task_id != packet.task_id:
        failures.append(
            f"receipt task_id {receipt.task_id!r} does not match packet task "
            f"{packet.task_id!r}"
        )
    expected_fingerprint = packet.fingerprint()
    if receipt.packet_fingerprint != expected_fingerprint:
        failures.append(
            f"receipt answers packet {receipt.packet_fingerprint}, not {expected_fingerprint}"
        )

    if receipt.subagents_used:
        failures.append(
            f"{receipt.subagents_used} nested agent(s) reported; constitution rule 2 "
            "forbids them in Bootstrap Mode"
        )
    # Redundant by construction - neither object can be built with the rule
    # off - and kept deliberately: this layer states the invariant itself
    # rather than inheriting it, so a future settable field cannot slip past.
    if not packet.no_subagents or not receipt.no_subagents:
        failures.append("the no-subagent rule must hold in both packet and receipt")

    if receipt.merge_performed:
        failures.append(
            "a merge was performed; the completion protocol assigns a branch and "
            "reserves merging"
        )
    if receipt.branch and receipt.branch != packet.expected_branch:
        failures.append(
            f"branch {receipt.branch!r} is not the assigned branch "
            f"{packet.expected_branch!r}"
        )
    if packet.expected_base_commit and receipt.base_commit:
        if receipt.base_commit != packet.expected_base_commit:
            failures.append(
                f"base commit {receipt.base_commit} is not the expected "
                f"{packet.expected_base_commit}"
            )
    elif packet.expected_base_commit:
        warnings.append(
            "the packet named an expected base commit and the receipt reports none"
        )
    for name in ("base_commit", "commit_sha", "remote_branch_sha"):
        value = getattr(receipt, name)
        if value and not is_git_sha(value):
            failures.append(f"receipt {name} {value!r} is not a Git object name")

    unknown_refs = sorted(set(receipt.context_refs_used) - set(packet.context_keys()))
    if unknown_refs:
        failures.append(
            "receipt reports context the packet did not supply: " + ", ".join(unknown_refs)
        )

    verdict = packet.path_scope.verdict(receipt.files_changed)
    failures.extend(verdict.failures())

    if receipt.outcome is Outcome.ACCEPTED:
        failures.extend(_accepted_failures(packet, receipt))
        if receipt.working_tree_clean is None:
            warnings.append("the receipt does not report working tree status")
    elif receipt.outcome is Outcome.REJECTED and not receipt.rejection_reason.strip():
        failures.append(
            "a rejected result must carry a rejection_reason; an unexplained "
            "rejection cannot improve the next attempt"
        )

    if receipt.dependencies_added:
        warnings.append(
            "new dependency declared ("
            + ", ".join(receipt.dependencies_added)
            + "); permissions.yaml triggers architecture_and_security_review"
        )

    return ReceiptValidation(
        failures=tuple(failures), warnings=tuple(warnings), path_verdict=verdict
    )


def _accepted_failures(packet: SessionPacket, receipt: SessionReceipt) -> list[str]:
    failures: list[str] = []
    if not receipt.summary.strip():
        failures.append("an accepted result must carry a compact handoff summary")
    if not receipt.branch:
        failures.append("an accepted result must report the branch it was committed on")
    if not receipt.commit_sha:
        failures.append("an accepted result must report its commit SHA")
    if not receipt.remote_verified:
        failures.append(
            "remote verification is not asserted; the protocol requires the exact "
            "remote SHA to be verified"
        )
    if not receipt.remote_branch_sha:
        failures.append("an accepted result must report the remote branch SHA")
    elif receipt.commit_sha and receipt.remote_branch_sha != receipt.commit_sha:
        failures.append(
            f"remote branch SHA {receipt.remote_branch_sha} does not equal the "
            f"reported commit {receipt.commit_sha}"
        )
    if receipt.working_tree_clean is False:
        failures.append("the working tree is reported dirty for an accepted result")

    missing_tests = tuple(
        command for command in packet.required_tests if command not in receipt.test_commands
    )
    if missing_tests:
        failures.append("required test(s) not reported: " + ", ".join(missing_tests))
    failing = receipt.failing_tests
    if failing:
        failures.append("reported failing test(s): " + ", ".join(failing))
    if packet.evidence_required and not receipt.evidence:
        failures.append(
            "this task requires evidence and the receipt supplies none"
        )
    return failures


def _string(data: Mapping[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"receipt.{field_name} must be a non-empty string")
    return value.strip()


_PROSE_FIELDS = frozenset({"summary", "notes", "rejection_reason"})


def _optional_string(data: Mapping[str, Any], field_name: str) -> str:
    """Pointers are stripped; prose is kept verbatim, because its shape is content."""
    value = data.get(field_name, "")
    if not isinstance(value, str):
        raise ValidationError(f"receipt.{field_name} must be a string")
    return value if field_name in _PROSE_FIELDS else value.strip()


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValidationError(f"receipt.{field_name} must be a list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"receipt.{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _boolean(data: Mapping[str, Any], field_name: str, default: bool) -> bool:
    value = data.get(field_name, default)
    if not isinstance(value, bool):
        raise ValidationError(f"receipt.{field_name} must be a boolean")
    return value


def _optional_boolean(data: Mapping[str, Any], field_name: str) -> bool | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValidationError(f"receipt.{field_name} must be a boolean or null")
    return value


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"receipt.{field_name} must be an integer")
    return value


def normalised_changed_paths(receipt: SessionReceipt) -> tuple[str, ...]:
    """The reported changes, in the one spelling the scope guard also uses."""
    return tuple(
        normalise_path(path, f"files_changed[{index}]")
        for index, path in enumerate(receipt.files_changed)
    )


__all__ = [
    "RECEIPT_VERSION",
    "ReceiptUsage",
    "ReceiptValidation",
    "SessionReceipt",
    "ReportedTest",
    "normalised_changed_paths",
    "validate_receipt",
]
