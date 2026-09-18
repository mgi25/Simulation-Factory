"""The one page the CEO reads, assembled from records and never from prose.

Every line in a rendered `EngineeringResult` comes from a stored record: the
work order, the job's state machine, the developer's receipt, the adjudicated
review and the gate's own report. Nothing here summarises, scores or softens.

## READY FOR CEO APPROVAL is a request, not a permission

The status line prints the job's state, and the strongest state the machine can
reach on its own is `ready_for_approval`. The result therefore ends with an
explicit line saying that it is not an approval and that integration is a
separate CEO act — because the failure mode of a page that says "READY" at the
top is that somebody reads the top.

`authorizes_merge` is a field, it is always False, and construction refuses any
other value. The same field exists on `CEODecision` for the same reason.

## Why the tests are grouped by scope

A reader needs three different questions answered: did the new behaviour get
tested, did the rest of the control plane survive, and did anything else in the
repository break. One flat list answers none of them, so `ResultTest.scope` is
`targeted`, `company_os` or `full_suite`, and `render_text` prints them under
those headings with the counts. A scope with nothing in it prints as "none
reported", never as passing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from company.runtime.receipts import SessionReceipt

from .common import assert_day, assert_prose, assert_record_id, assert_ref, text_tuple
from .errors import EngineeringError
from .gate_evidence import GateReadiness, GateVerdict
from .lifecycle import EngineeringJob, JobState
from .review import EngineeringReview, ReviewOutcome
from .work_order import EngineeringWorkOrder


RESULT_VERSION = 1

NOT_AN_APPROVAL = (
    "READY FOR CEO APPROVAL is a request to be read, not an approval. Nothing here "
    "merges, deploys or publishes, and Company OS holds no capability to."
)


class SuiteScope(str, Enum):
    TARGETED = "targeted"
    COMPANY_OS = "company_os"
    FULL_SUITE = "full_suite"


@dataclass(frozen=True)
class ResultTest:
    """One reported test run, and which of the three questions it answers."""

    command: str
    passed: bool
    scope: SuiteScope
    summary: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", assert_ref(self.command, "test.command"))
        if not isinstance(self.passed, bool):
            raise EngineeringError("test.passed must be a boolean")
        if not isinstance(self.scope, SuiteScope):
            raise EngineeringError("test.scope must be a SuiteScope value")
        if not isinstance(self.summary, str):
            raise EngineeringError("test.summary must be a string")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class EngineeringResult:
    """The complete CEO-facing outcome of one engineering job."""

    work_order_id: str
    work_order_fingerprint: str
    objective: str
    requested_by: str
    authorized_on: dt.date
    status: JobState
    authorized_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    implementation_summary: str = ""
    changed_files: tuple[str, ...] = ()
    branch: str = ""
    commit_sha: str = ""
    remote_verified: bool = False
    implementer: str = ""
    developer_attempts: int = 0
    max_developer_attempts: int = 0
    attempts_remaining: int = 0
    tests: tuple[ResultTest, ...] = ()
    review_outcome: ReviewOutcome | None = None
    reviewer: str = ""
    review_findings: tuple[str, ...] = ()
    unanswered_criteria: tuple[str, ...] = ()
    gate_readiness: GateReadiness | None = None
    gate_report_id: str = ""
    gate_blockers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    decisions_required: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    merge_performed: bool = False
    authorizes_merge: bool = False
    version: int = RESULT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "work_order_id",
            assert_record_id(self.work_order_id, "result.work_order_id"),
        )
        if not isinstance(self.work_order_fingerprint, str) or len(
            self.work_order_fingerprint
        ) != 16:
            raise EngineeringError(
                "result.work_order_fingerprint must be a 16-character digest"
            )
        object.__setattr__(self, "objective", assert_prose(self.objective, "result.objective"))
        object.__setattr__(
            self, "requested_by", assert_prose(self.requested_by, "result.requested_by")
        )
        object.__setattr__(
            self, "authorized_on", assert_day(self.authorized_on, "result.authorized_on")
        )
        if not isinstance(self.status, JobState):
            raise EngineeringError("result.status must be a JobState value")
        for name in ("authorized_paths", "acceptance_criteria"):
            object.__setattr__(
                self, name, text_tuple(getattr(self, name), f"result.{name}", limit=32)
            )
        for name in (
            "changed_files",
            "review_findings",
            "unanswered_criteria",
            "gate_blockers",
            "risks",
            "decisions_required",
            "evidence_refs",
        ):
            object.__setattr__(
                self, name, text_tuple(getattr(self, name), f"result.{name}", limit=64)
            )
        if not isinstance(self.tests, tuple) or any(
            not isinstance(item, ResultTest) for item in self.tests
        ):
            raise EngineeringError("result.tests must hold ResultTest values")
        if self.review_outcome is not None and not isinstance(
            self.review_outcome, ReviewOutcome
        ):
            raise EngineeringError("result.review_outcome must be a ReviewOutcome or null")
        if self.gate_readiness is not None and not isinstance(
            self.gate_readiness, GateReadiness
        ):
            raise EngineeringError("result.gate_readiness must be a GateReadiness or null")
        for name in ("implementation_summary", "branch", "commit_sha", "implementer", "gate_report_id", "reviewer"):
            if not isinstance(getattr(self, name), str):
                raise EngineeringError(f"result.{name} must be a string")
        for name in ("remote_verified", "merge_performed"):
            if not isinstance(getattr(self, name), bool):
                raise EngineeringError(f"result.{name} must be a boolean")
        for counter in ("developer_attempts", "max_developer_attempts", "attempts_remaining"):
            val = getattr(self, counter)
            if isinstance(val, bool) or not isinstance(val, int):
                raise EngineeringError(f"result.{counter} must be an integer")
            if val < 0:
                raise EngineeringError(f"result.{counter} must be non-negative")
        if self.attempts_remaining != max(0, self.max_developer_attempts - self.developer_attempts):
            raise EngineeringError(
                "result.attempts_remaining must equal "
                "max_developer_attempts - developer_attempts (clamped to 0)"
            )
        if self.authorizes_merge is not False:
            raise EngineeringError(
                "an engineering result never authorizes a merge. It reports; the CEO "
                "decides; integration happens outside Company OS."
            )
        if self.status is JobState.READY_FOR_APPROVAL:
            unmet = _readiness_objections(self)
            if unmet:
                raise EngineeringError(
                    "a result cannot report ready_for_approval while: "
                    + "; ".join(unmet)
                    + ". Readiness is derived from the review and the gate, not stated."
                )
        if self.version != RESULT_VERSION:
            raise EngineeringError(f"result.version must be {RESULT_VERSION}")

    # --- derived -----------------------------------------------------------

    def tests_in(self, scope: SuiteScope) -> tuple[ResultTest, ...]:
        return tuple(item for item in self.tests if item.scope is scope)

    @property
    def failing_tests(self) -> tuple[str, ...]:
        return tuple(item.command for item in self.tests if not item.passed)

    @property
    def ready(self) -> bool:
        return self.status is JobState.READY_FOR_APPROVAL

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(self)
        payload["not_an_approval"] = NOT_AN_APPROVAL
        return payload

    def fingerprint(self) -> str:
        return _fingerprint(self)

    # --- assembly ----------------------------------------------------------

    @classmethod
    def build(
        cls,
        order: EngineeringWorkOrder,
        job: EngineeringJob,
        *,
        receipt: SessionReceipt | None = None,
        review: EngineeringReview | None = None,
        gate: GateVerdict | None = None,
        suite_results: Sequence[ResultTest] = (),
        risks: Sequence[str] = (),
        decisions_required: Sequence[str] = (),
        evidence_refs: Sequence[str] = (),
    ) -> "EngineeringResult":
        """Assemble the CEO result from whichever records exist so far.

        Every argument is optional because a result is also how a blocked or
        decision-required job is reported, and the honest report of a job that
        never reached review is one with no review section rather than one with
        an empty pass.
        """
        order.assert_unchanged(job.work_order_fingerprint, "result assembly")
        tests: list[ResultTest] = []
        if receipt is not None:
            for reported in receipt.tests:
                tests.append(
                    ResultTest(
                        command=reported.command,
                        passed=reported.passed,
                        # Targeted means "a test this work order required".
                        # The work order is the only thing that knows which
                        # those are; a name match would be this package
                        # guessing about somebody else's suite.
                        scope=(
                            SuiteScope.TARGETED
                            if reported.command in order.required_tests
                            else SuiteScope.COMPANY_OS
                        ),
                        summary=reported.summary,
                    )
                )
        seen = {item.command for item in tests}
        for item in suite_results:
            if item.command not in seen:
                tests.append(item)
                seen.add(item.command)

        pending = list(decisions_required)
        pending.extend(job.pending_decisions)
        if review is not None:
            pending.extend(review.escalations)
        if gate is not None:
            pending.extend(
                item.reason for item in gate.blockers if item.ceo_decision_required
            )

        risk_lines = list(risks)
        if receipt is not None:
            risk_lines.extend(receipt.unresolved_risks)

        return cls(
            work_order_id=order.work_order_id,
            work_order_fingerprint=order.fingerprint(),
            objective=order.objective,
            requested_by=order.requested_by,
            authorized_on=order.authorized_on,
            status=job.state,
            authorized_paths=order.authorized_paths,
            acceptance_criteria=order.acceptance_criteria,
            implementation_summary=(receipt.summary if receipt else ""),
            changed_files=(receipt.files_changed if receipt else ()),
            branch=(receipt.branch if receipt else order.authorized_branch),
            commit_sha=(receipt.commit_sha if receipt else ""),
            remote_verified=bool(receipt.remote_verified) if receipt else False,
            implementer=(review.implementer if review else ""),
            developer_attempts=job.developer_attempts,
            max_developer_attempts=job.max_developer_attempts,
            attempts_remaining=job.corrections_remaining,
            tests=tuple(tests),
            review_outcome=(review.outcome if review else None),
            reviewer=(review.reviewer if review else ""),
            review_findings=(
                tuple(
                    f"[{item.severity.value}] {item.finding_id}: {item.summary}"
                    for item in review.findings
                )
                if review
                else ()
            ),
            unanswered_criteria=(review.unanswered_criteria if review else ()),
            gate_readiness=(gate.readiness if gate else None),
            gate_report_id=(gate.report_id if gate else ""),
            gate_blockers=(gate.blocker_summaries if gate else ()),
            risks=tuple(dict.fromkeys(risk_lines)),
            decisions_required=tuple(dict.fromkeys(pending)),
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            merge_performed=bool(receipt.merge_performed) if receipt else False,
        )

    # --- rendering ---------------------------------------------------------

    def render_text(self) -> str:
        """The CEO page. Fixed order, fixed headings, no computed praise."""
        lines: list[str] = []
        lines.append("WORK ORDER")
        lines.append(f"  {self.work_order_id}  ({self.work_order_fingerprint})")
        lines.append(f"  objective: {self.objective}")
        lines.append(f"  requested by: {self.requested_by} on {self.authorized_on.isoformat()}")
        lines.append("  authorized paths:")
        lines.extend(f"    {path}" for path in self.authorized_paths)
        lines.append("  acceptance criteria:")
        lines.extend(f"    - {item}" for item in self.acceptance_criteria)

        lines.append("")
        lines.append("STATUS")
        lines.append(f"  {self.status.value.upper()}")

        lines.append("")
        lines.append("IMPLEMENTATION")
        lines.append(f"  summary: {self.implementation_summary or 'none reported'}")
        lines.append(f"  branch: {self.branch or 'none reported'}")
        lines.append(f"  commit: {self.commit_sha or 'none reported'}")
        lines.append(f"  remote verified: {'yes' if self.remote_verified else 'no'}")
        lines.append(f"  implementer: {self.implementer or 'not recorded'}")
        lines.append(
            f"  developer attempts: {self.developer_attempts} of "
            f"{self.max_developer_attempts} ({self.attempts_remaining} remaining)"
        )
        lines.append(f"  changed files ({len(self.changed_files)}):")
        lines.extend(f"    {path}" for path in self.changed_files or ("none reported",))

        lines.append("")
        lines.append("TESTS")
        for scope, heading in (
            (SuiteScope.TARGETED, "targeted"),
            (SuiteScope.COMPANY_OS, "affected Company OS"),
            (SuiteScope.FULL_SUITE, "full repository suite"),
        ):
            rows = self.tests_in(scope)
            if not rows:
                lines.append(f"  {heading}: none reported")
                continue
            passed = sum(1 for item in rows if item.passed)
            lines.append(f"  {heading}: {passed}/{len(rows)} passed")
            for item in rows:
                mark = "PASS" if item.passed else "FAIL"
                detail = f" — {item.summary}" if item.summary else ""
                lines.append(f"    [{mark}] {item.command}{detail}")

        lines.append("")
        lines.append("REVIEW")
        if self.review_outcome is None:
            lines.append("  no review recorded")
        else:
            lines.append(f"  {self.review_outcome.value.upper()} by {self.reviewer}")
            if self.unanswered_criteria:
                lines.append(
                    f"  unanswered acceptance criteria: {len(self.unanswered_criteria)}"
                )
                lines.extend(f"    - {item}" for item in self.unanswered_criteria)
            if self.review_findings:
                lines.append(f"  findings ({len(self.review_findings)}):")
                lines.extend(f"    {item}" for item in self.review_findings)
            else:
                lines.append("  findings: none")

        lines.append("")
        lines.append("GATE")
        if self.gate_readiness is None:
            lines.append("  no gate report supplied")
        else:
            lines.append(f"  {self.gate_readiness.value.upper()}  ({self.gate_report_id})")
            if self.gate_blockers:
                lines.append(f"  blockers ({len(self.gate_blockers)}):")
                lines.extend(f"    - {item}" for item in self.gate_blockers)
            else:
                lines.append("  blockers: none")

        lines.append("")
        lines.append("RISKS")
        lines.extend(f"  - {item}" for item in self.risks or ("none reported",))

        lines.append("")
        lines.append("DECISIONS REQUIRED")
        lines.extend(
            f"  - {item}" for item in self.decisions_required or ("none",)
        )

        lines.append("")
        lines.append("CEO OPTIONS")
        lines.append("  [APPROVE]  [REQUEST CHANGES]  [REJECT]")
        lines.append(f"  {NOT_AN_APPROVAL}")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EngineeringResult":
        if not isinstance(data, Mapping):
            raise EngineeringError("a result must be a mapping")
        # `not_an_approval` is added by `to_dict` as a reader-facing constant,
        # so a stored result carries it and decoding must not treat it as drift.
        unknown = sorted(set(data) - set(cls.__dataclass_fields__) - {"not_an_approval"})
        if unknown:
            raise EngineeringError("result has unknown field(s): " + ", ".join(unknown))
        raw_tests = data.get("tests", ())
        if isinstance(raw_tests, (str, bytes)) or not isinstance(raw_tests, (list, tuple)):
            raise EngineeringError("result.tests must be a list")
        tests = []
        for index, item in enumerate(raw_tests):
            if not isinstance(item, Mapping):
                raise EngineeringError(f"result.tests[{index}] must be a mapping")
            extra = sorted(set(item) - {"command", "passed", "scope", "summary"})
            if extra:
                raise EngineeringError(
                    f"result.tests[{index}] has unknown field(s): " + ", ".join(extra)
                )
            scope = item.get("scope")
            if not isinstance(scope, str):
                raise EngineeringError(f"result.tests[{index}].scope must be a string")
            try:
                parsed_scope = SuiteScope(scope)
            except ValueError as exc:
                allowed = ", ".join(value.value for value in SuiteScope)
                raise EngineeringError(
                    f"result.tests[{index}].scope must be one of: {allowed}"
                ) from exc
            tests.append(
                ResultTest(
                    command=str(item.get("command", "")),
                    passed=bool(item.get("passed", False)),
                    scope=parsed_scope,
                    summary=str(item.get("summary", "")),
                )
            )
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            objective=str(data.get("objective", "")),
            requested_by=str(data.get("requested_by", "")),
            authorized_on=assert_day(data.get("authorized_on"), "result.authorized_on"),
            status=_job_state(data.get("status")),
            authorized_paths=_strings(data.get("authorized_paths")),
            acceptance_criteria=_strings(data.get("acceptance_criteria")),
            implementation_summary=str(data.get("implementation_summary", "")),
            changed_files=_strings(data.get("changed_files")),
            branch=str(data.get("branch", "")),
            commit_sha=str(data.get("commit_sha", "")),
            remote_verified=bool(data.get("remote_verified", False)),
            implementer=str(data.get("implementer", "")),
            developer_attempts=int(data.get("developer_attempts", 0)),
            max_developer_attempts=int(data.get("max_developer_attempts", 0)),
            attempts_remaining=int(data.get("attempts_remaining", 0)),
            tests=tuple(tests),
            review_outcome=_optional_enum(ReviewOutcome, data.get("review_outcome")),
            reviewer=str(data.get("reviewer", "")),
            review_findings=_strings(data.get("review_findings")),
            unanswered_criteria=_strings(data.get("unanswered_criteria")),
            gate_readiness=_optional_enum(GateReadiness, data.get("gate_readiness")),
            gate_report_id=str(data.get("gate_report_id", "")),
            gate_blockers=_strings(data.get("gate_blockers")),
            risks=_strings(data.get("risks")),
            decisions_required=_strings(data.get("decisions_required")),
            evidence_refs=_strings(data.get("evidence_refs")),
            merge_performed=bool(data.get("merge_performed", False)),
            authorizes_merge=bool(data.get("authorizes_merge", False)),
            version=int(data.get("version", RESULT_VERSION)),
        )


def _readiness_objections(result: "EngineeringResult") -> tuple[str, ...]:
    """Everything that contradicts a ready_for_approval claim, as sorted reasons."""
    objections: list[str] = []
    if result.review_outcome is not ReviewOutcome.PASS:
        objections.append(
            "the review is "
            + (result.review_outcome.value if result.review_outcome else "not recorded")
        )
    if result.gate_readiness is not GateReadiness.READY:
        objections.append(
            "the integration gate is "
            + (result.gate_readiness.value if result.gate_readiness else "not recorded")
        )
    if result.failing_tests:
        objections.append("test(s) are failing: " + ", ".join(result.failing_tests))
    if result.unanswered_criteria:
        objections.append(
            f"{len(result.unanswered_criteria)} acceptance criterion/criteria are unanswered"
        )
    if result.merge_performed:
        objections.append("a merge was performed")
    return tuple(sorted(objections))


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EngineeringError("expected a list of strings")
    return tuple(str(item) for item in value)


def _job_state(value: Any) -> JobState:
    if not isinstance(value, str):
        raise EngineeringError("result.status must be a string")
    try:
        return JobState(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in JobState)
        raise EngineeringError(f"result.status must be one of: {allowed}") from exc


def _optional_enum(enum_type: type[Enum], value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EngineeringError(f"expected a {enum_type.__name__} string or null")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise EngineeringError(f"must be one of: {allowed}") from exc


__all__ = [
    "NOT_AN_APPROVAL",
    "RESULT_VERSION",
    "EngineeringResult",
    "ResultTest",
    "SuiteScope",
]
