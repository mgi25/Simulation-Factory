"""Review and QA — the stage the implementation is structurally unable to pass itself.

Two things happen here, and keeping them apart is the whole design.

**Deterministic QA** is code. It re-reads the protected surface, re-checks the
path scope verdict, checks that every required test was reported and passed,
checks that no merge happened, that no nested agent was used, that no
dependency appeared, and that every acceptance criterion was answered with an
evidence reference. It needs no judgment and it cannot be persuaded.

**Reviewer judgment** is an independent session. It reads the work order, the
diff and the tests and returns a `ReviewerAttestation` with a verdict, a
finding list and one answer per acceptance criterion.

`adjudicate` combines them with one rule:

    outcome = worst_of(attested_verdict, deterministic_verdict)

A reviewer's PASS cannot rescue work that failed a deterministic check, and a
reviewer's BLOCKED is never overridden by code that found nothing — the
reviewer may know something the checks cannot see. Severity only ever goes up.

## The two refusals that make the review independent

`SelfApproval` is raised, not recorded, when the attestation's reviewer is the
employee that implemented the work. There is no verdict in that case, because
there was no review.

The reviewer must also *hold the review capability* the work order named, and
`EngineeringWorkOrder.__post_init__` already refuses a work order whose review
capability is one of its implementation capabilities. So the two roles route to
disjoint sets of employees by construction, and the identity check above closes
the remaining case where one employee holds both.

## Why a reviewer cannot write

`EngineeringWorkOrder.reviewer_contract` leaves `may_write` empty, which in
Bootstrap Mode is read-only, and lists the implementation's own paths under
`may_not_modify`. A reviewer that "fixed it while reviewing" would produce a
receipt whose reported changes fail the path scope of its own packet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from ai_platform.usage import Outcome
from company.runtime.packets import SessionPacket
from company.runtime.receipts import ReceiptValidation, SessionReceipt

from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_ref,
    ref_tuple,
    text_tuple,
)
from .errors import EngineeringError, SelfApproval
from .work_order import EngineeringWorkOrder


REVIEW_VERSION = 1


class ReviewOutcome(str, Enum):
    """The three verdicts. `SEVERITY_ORDER` below is the only ranking of them."""

    PASS = "pass"
    CHANGES_REQUIRED = "changes_required"
    BLOCKED = "blocked"


# Ascending severity, declared once. A tuple rather than a mapping because the
# order *is* the rule: `_worst` only ever moves a verdict later in this list,
# which is what stops a reviewer's PASS from rescuing a failed check.
SEVERITY_ORDER: tuple[ReviewOutcome, ...] = (
    ReviewOutcome.PASS,
    ReviewOutcome.CHANGES_REQUIRED,
    ReviewOutcome.BLOCKED,
)


def _worst(*outcomes: ReviewOutcome) -> ReviewOutcome:
    return max(outcomes, key=SEVERITY_ORDER.index)


class FindingSeverity(str, Enum):
    ADVISORY = "advisory"
    CHANGES_REQUIRED = "changes_required"
    BLOCKING = "blocking"

    def as_outcome(self) -> ReviewOutcome:
        return {
            FindingSeverity.ADVISORY: ReviewOutcome.PASS,
            FindingSeverity.CHANGES_REQUIRED: ReviewOutcome.CHANGES_REQUIRED,
            FindingSeverity.BLOCKING: ReviewOutcome.BLOCKED,
        }[self]


@dataclass(frozen=True)
class ReviewFinding:
    """One thing wrong, its severity, and where to look."""

    finding_id: str
    severity: FindingSeverity
    summary: str
    evidence_ref: str = ""
    deterministic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "finding_id", assert_record_id(self.finding_id, "finding.finding_id")
        )
        if not isinstance(self.severity, FindingSeverity):
            raise EngineeringError("finding.severity must be a FindingSeverity value")
        object.__setattr__(self, "summary", assert_prose(self.summary, "finding.summary"))
        if self.evidence_ref:
            object.__setattr__(
                self, "evidence_ref", assert_ref(self.evidence_ref, "finding.evidence_ref")
            )
        if not isinstance(self.deterministic, bool):
            raise EngineeringError("finding.deterministic must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CriterionFinding:
    """The reviewer's answer on one acceptance criterion, with its evidence."""

    criterion: str
    satisfied: bool
    evidence_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "criterion", assert_prose(self.criterion, "criterion.criterion")
        )
        if not isinstance(self.satisfied, bool):
            raise EngineeringError("criterion.satisfied must be a boolean")
        if self.satisfied and not self.evidence_ref:
            raise EngineeringError(
                f"criterion {self.criterion!r} is reported satisfied with no evidence "
                "reference. A satisfied criterion names what satisfies it."
            )
        if self.evidence_ref:
            object.__setattr__(
                self,
                "evidence_ref",
                assert_ref(self.evidence_ref, "criterion.evidence_ref"),
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ReviewerAttestation:
    """What one independent reviewer session returns about one attempt."""

    review_id: str
    work_order_id: str
    work_order_fingerprint: str
    reviewer: str
    packet_fingerprint: str
    receipt_fingerprint: str
    verdict: ReviewOutcome
    reviewed_on: dt.date
    criteria: tuple[CriterionFinding, ...] = ()
    findings: tuple[ReviewFinding, ...] = ()
    evidence: tuple[str, ...] = ()
    changed_paths_reviewed: tuple[str, ...] = ()
    notes: str = ""
    version: int = REVIEW_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "review_id", assert_record_id(self.review_id, "attestation.review_id")
        )
        object.__setattr__(
            self,
            "work_order_id",
            assert_record_id(self.work_order_id, "attestation.work_order_id"),
        )
        object.__setattr__(
            self, "reviewer", assert_record_id(self.reviewer, "attestation.reviewer")
        )
        for name in (
            "work_order_fingerprint",
            "packet_fingerprint",
            "receipt_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 16:
                raise EngineeringError(
                    f"attestation.{name} must be a 16-character digest"
                )
        if not isinstance(self.verdict, ReviewOutcome):
            raise EngineeringError("attestation.verdict must be a ReviewOutcome value")
        object.__setattr__(
            self, "reviewed_on", assert_day(self.reviewed_on, "attestation.reviewed_on")
        )
        for name, kind in (("criteria", CriterionFinding), ("findings", ReviewFinding)):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, kind) for item in values
            ):
                raise EngineeringError(
                    f"attestation.{name} must be a tuple of {kind.__name__} values"
                )
        if any(item.deterministic for item in self.findings):
            raise EngineeringError(
                "attestation.findings cannot be marked deterministic: a reviewer "
                "reports judgment, and the deterministic findings are computed here "
                "rather than supplied"
            )
        object.__setattr__(
            self, "evidence", ref_tuple(self.evidence, "attestation.evidence", limit=32)
        )
        object.__setattr__(
            self,
            "changed_paths_reviewed",
            ref_tuple(
                self.changed_paths_reviewed, "attestation.changed_paths_reviewed", limit=64
            ),
        )
        if not isinstance(self.notes, str):
            raise EngineeringError("attestation.notes must be a string")
        if self.version != REVIEW_VERSION:
            raise EngineeringError(f"attestation.version must be {REVIEW_VERSION}")

    def answered(self) -> dict[str, CriterionFinding]:
        return {item.criterion: item for item in self.criteria}

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ReviewerAttestation":
        """Decode a returned attestation, refusing every field the schema omits.

        Same reasoning as `SessionReceipt.from_mapping`: the realistic
        escalation is an extra field — `gate_passed: true`, `approved: true` —
        arriving in the hope that a later reader honours it. There is no field
        it can arrive in.
        """
        if not isinstance(data, Mapping):
            raise EngineeringError("an attestation must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError(
                "attestation has unknown field(s): "
                + ", ".join(unknown)
                + ". A review reports judgment; it does not grant anything, so a "
                "field outside the schema is refused rather than ignored."
            )
        verdict = data.get("verdict")
        if not isinstance(verdict, str):
            raise EngineeringError("attestation.verdict must be a string")
        try:
            parsed = ReviewOutcome(verdict)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in ReviewOutcome)
            raise EngineeringError(
                f"attestation.verdict must be one of: {allowed}"
            ) from exc
        return cls(
            review_id=str(data.get("review_id", "")),
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            reviewer=str(data.get("reviewer", "")),
            packet_fingerprint=str(data.get("packet_fingerprint", "")),
            receipt_fingerprint=str(data.get("receipt_fingerprint", "")),
            verdict=parsed,
            reviewed_on=assert_day(data.get("reviewed_on"), "attestation.reviewed_on"),
            criteria=tuple(
                _criterion(item, index)
                for index, item in enumerate(_listed(data.get("criteria"), "criteria"))
            ),
            findings=tuple(
                _finding(item, index)
                for index, item in enumerate(_listed(data.get("findings"), "findings"))
            ),
            evidence=tuple(str(item) for item in _listed(data.get("evidence"), "evidence")),
            changed_paths_reviewed=tuple(
                str(item)
                for item in _listed(
                    data.get("changed_paths_reviewed"), "changed_paths_reviewed"
                )
            ),
            notes=str(data.get("notes", "")),
            version=_int(data.get("version", REVIEW_VERSION), "version"),
        )


@dataclass(frozen=True)
class EngineeringReview:
    """The adjudicated review: what code found, what the reviewer said, and the verdict."""

    review_id: str
    work_order_id: str
    work_order_fingerprint: str
    implementer: str
    reviewer: str
    packet_fingerprint: str
    receipt_fingerprint: str
    packet_attempt: int
    outcome: ReviewOutcome
    attested_outcome: ReviewOutcome
    deterministic_outcome: ReviewOutcome
    findings: tuple[ReviewFinding, ...]
    unanswered_criteria: tuple[str, ...]
    escalations: tuple[str, ...]
    reviewed_on: dt.date
    version: int = REVIEW_VERSION

    def __post_init__(self) -> None:
        if self.implementer == self.reviewer:
            raise SelfApproval(
                f"{self.reviewer!r} implemented and reviewed work order "
                f"{self.work_order_id}. A review by the implementer is not a review."
            )
        if self.outcome is not _worst(self.attested_outcome, self.deterministic_outcome):
            raise EngineeringError(
                "a review outcome is the worst of the attested and deterministic "
                "verdicts; it cannot be set independently"
            )
        for name in ("findings",):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, ReviewFinding) for item in values
            ):
                raise EngineeringError(f"review.{name} must hold ReviewFinding values")
        object.__setattr__(
            self,
            "unanswered_criteria",
            text_tuple(self.unanswered_criteria, "review.unanswered_criteria", limit=24),
        )
        object.__setattr__(
            self, "escalations", text_tuple(self.escalations, "review.escalations", limit=24)
        )
        object.__setattr__(
            self, "reviewed_on", assert_day(self.reviewed_on, "review.reviewed_on")
        )

    @property
    def passed(self) -> bool:
        return self.outcome is ReviewOutcome.PASS

    @property
    def blocking_findings(self) -> tuple[ReviewFinding, ...]:
        return tuple(
            item for item in self.findings if item.severity is FindingSeverity.BLOCKING
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EngineeringReview":
        if not isinstance(data, Mapping):
            raise EngineeringError("a review must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError("review has unknown field(s): " + ", ".join(unknown))
        return cls(
            review_id=str(data.get("review_id", "")),
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            implementer=str(data.get("implementer", "")),
            reviewer=str(data.get("reviewer", "")),
            packet_fingerprint=str(data.get("packet_fingerprint", "")),
            receipt_fingerprint=str(data.get("receipt_fingerprint", "")),
            packet_attempt=_int(data.get("packet_attempt", 0), "packet_attempt"),
            outcome=_outcome(data.get("outcome"), "outcome"),
            attested_outcome=_outcome(data.get("attested_outcome"), "attested_outcome"),
            deterministic_outcome=_outcome(
                data.get("deterministic_outcome"), "deterministic_outcome"
            ),
            findings=tuple(
                _finding(item, index)
                for index, item in enumerate(_listed(data.get("findings"), "findings"))
            ),
            unanswered_criteria=tuple(
                str(item)
                for item in _listed(data.get("unanswered_criteria"), "unanswered_criteria")
            ),
            escalations=tuple(
                str(item) for item in _listed(data.get("escalations"), "escalations")
            ),
            reviewed_on=assert_day(data.get("reviewed_on"), "review.reviewed_on"),
            version=_int(data.get("version", REVIEW_VERSION), "version"),
        )


def deterministic_findings(
    order: EngineeringWorkOrder,
    packet: SessionPacket,
    receipt: SessionReceipt,
    validation: ReceiptValidation,
    *,
    repo_root: Path | str,
    attestation: ReviewerAttestation | None = None,
) -> tuple[ReviewFinding, ...]:
    """Every QA condition that can be decided without judgment, as findings.

    The protected-surface re-read is first because it is the only check that
    can catch a change the receipt did not mention.
    """
    findings: list[ReviewFinding] = []

    for index, detail in enumerate(order.protected.verify(repo_root)):
        findings.append(
            ReviewFinding(
                finding_id=f"protected-{index + 1:02d}",
                severity=FindingSeverity.BLOCKING,
                summary="protected governance surface changed: " + detail,
                deterministic=True,
            )
        )
    for index, failure in enumerate(validation.failures):
        findings.append(
            ReviewFinding(
                finding_id=f"receipt-{index + 1:02d}",
                severity=FindingSeverity.CHANGES_REQUIRED,
                summary="receipt validation: " + failure,
                deterministic=True,
            )
        )
    if receipt.merge_performed:
        findings.append(
            ReviewFinding(
                finding_id="merge-performed",
                severity=FindingSeverity.BLOCKING,
                summary="a merge was performed; integration is a CEO decision",
                deterministic=True,
            )
        )
    if receipt.subagents_used:
        findings.append(
            ReviewFinding(
                finding_id="nested-agents",
                severity=FindingSeverity.BLOCKING,
                summary=(
                    f"{receipt.subagents_used} nested agent(s) reported; constitution "
                    "rule 2 forbids them in Bootstrap Mode"
                ),
                deterministic=True,
            )
        )
    if receipt.dependencies_added:
        findings.append(
            ReviewFinding(
                finding_id="dependency-added",
                severity=FindingSeverity.BLOCKING,
                summary=(
                    "new dependency declared ("
                    + ", ".join(receipt.dependencies_added)
                    + "); permissions.yaml requires architecture_and_security_review"
                ),
                deterministic=True,
            )
        )
    if receipt.outcome is not Outcome.ACCEPTED:
        findings.append(
            ReviewFinding(
                finding_id="attempt-not-accepted",
                severity=FindingSeverity.CHANGES_REQUIRED,
                summary=(
                    f"the implementation attempt ended {receipt.outcome.value}: "
                    + (receipt.rejection_reason or "no reason reported")
                ),
                deterministic=True,
            )
        )
    missing = tuple(
        command for command in order.required_tests if command not in receipt.test_commands
    )
    if missing:
        findings.append(
            ReviewFinding(
                finding_id="tests-not-reported",
                severity=FindingSeverity.CHANGES_REQUIRED,
                summary="required test(s) not reported: " + ", ".join(missing),
                deterministic=True,
            )
        )
    if receipt.failing_tests:
        findings.append(
            ReviewFinding(
                finding_id="tests-failing",
                severity=FindingSeverity.CHANGES_REQUIRED,
                summary="reported failing test(s): " + ", ".join(receipt.failing_tests),
                deterministic=True,
            )
        )
    if not receipt.files_changed:
        findings.append(
            ReviewFinding(
                finding_id="nothing-changed",
                severity=FindingSeverity.CHANGES_REQUIRED,
                summary=(
                    "the receipt reports no changed file; a work order that authorized "
                    "writing and produced none has not been implemented"
                ),
                deterministic=True,
            )
        )
    if attestation is not None:
        answered = attestation.answered()
        unanswered = tuple(
            criterion
            for criterion in order.acceptance_criteria
            if criterion not in answered
        )
        if unanswered:
            findings.append(
                ReviewFinding(
                    finding_id="criteria-unanswered",
                    severity=FindingSeverity.CHANGES_REQUIRED,
                    summary=(
                        f"{len(unanswered)} acceptance criterion/criteria unanswered by "
                        "the review: " + "; ".join(unanswered[:3])
                    ),
                    deterministic=True,
                )
            )
        unsatisfied = tuple(
            item.criterion for item in attestation.criteria if not item.satisfied
        )
        if unsatisfied:
            findings.append(
                ReviewFinding(
                    finding_id="criteria-unsatisfied",
                    severity=FindingSeverity.CHANGES_REQUIRED,
                    summary=(
                        "the review reports unsatisfied acceptance criterion/criteria: "
                        + "; ".join(unsatisfied[:3])
                    ),
                    deterministic=True,
                )
            )
        if not attestation.evidence:
            findings.append(
                ReviewFinding(
                    finding_id="review-without-evidence",
                    severity=FindingSeverity.CHANGES_REQUIRED,
                    summary=(
                        "the review supplies no evidence reference; a verdict with no "
                        "evidence cannot be checked (constitution rule 7)"
                    ),
                    deterministic=True,
                )
            )
    return tuple(findings)


def adjudicate(
    order: EngineeringWorkOrder,
    packet: SessionPacket,
    receipt: SessionReceipt,
    validation: ReceiptValidation,
    attestation: ReviewerAttestation,
    *,
    repo_root: Path | str,
    implementer: str,
    packet_attempt: int,
    reviewer_capabilities: Sequence[str] | None = None,
) -> EngineeringReview:
    """Combine deterministic QA with one reviewer's judgment into one verdict.

    `reviewer_capabilities` distinguishes three cases, because collapsing two
    of them was a hole: `None` means nobody looked the reviewer up and the
    check is skipped; `()` means the registry holds no capability for that
    name, which includes an employee who does not exist; and a non-empty
    sequence is checked for the work order's review capability. Before this,
    an unknown reviewer produced `()`, and `()` skipped the check, so an
    attestation could name anybody at all.
    """
    if attestation.reviewer == implementer:
        raise SelfApproval(
            f"{implementer!r} implemented work order {order.work_order_id} and cannot "
            "review it. Review is a separate employee, routed by a separate capability."
        )
    if attestation.work_order_id != order.work_order_id:
        raise EngineeringError(
            f"the attestation reviews work order {attestation.work_order_id!r}, not "
            f"{order.work_order_id!r}"
        )
    order.assert_unchanged(attestation.work_order_fingerprint, "review")
    if attestation.packet_fingerprint != packet.fingerprint():
        raise EngineeringError(
            "the attestation answers a different packet than the one under review"
        )
    if attestation.receipt_fingerprint != receipt.fingerprint():
        raise EngineeringError(
            "the attestation reviews a different receipt than the one under review"
        )

    findings = list(
        deterministic_findings(
            order, packet, receipt, validation, repo_root=repo_root, attestation=attestation
        )
    )
    if reviewer_capabilities is not None:
        held = {str(item).casefold() for item in reviewer_capabilities}
        if order.review_capability not in held:
            summary = (
                f"reviewer {attestation.reviewer!r} holds no capability in the org "
                "registry; an attestation cannot name somebody who is not an employee"
                if not held
                else (
                    f"reviewer {attestation.reviewer!r} does not hold the work order's "
                    f"review capability {order.review_capability!r}"
                )
            )
            findings.append(
                ReviewFinding(
                    finding_id="reviewer-not-qualified",
                    severity=FindingSeverity.BLOCKING,
                    summary=summary,
                    deterministic=True,
                )
            )
    deterministic_outcome = _worst(
        ReviewOutcome.PASS, *(item.severity.as_outcome() for item in findings)
    )
    combined = findings + list(attestation.findings)
    outcome = _worst(attestation.verdict, deterministic_outcome)

    answered = attestation.answered()
    unanswered = tuple(
        criterion for criterion in order.acceptance_criteria if criterion not in answered
    )
    escalations = _escalations(receipt, findings)
    return EngineeringReview(
        review_id=attestation.review_id,
        work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(),
        implementer=implementer,
        reviewer=attestation.reviewer,
        packet_fingerprint=packet.fingerprint(),
        receipt_fingerprint=receipt.fingerprint(),
        packet_attempt=packet_attempt,
        outcome=outcome,
        attested_outcome=attestation.verdict,
        deterministic_outcome=deterministic_outcome,
        findings=tuple(sorted(combined, key=lambda item: item.finding_id)),
        unanswered_criteria=unanswered,
        escalations=escalations,
        reviewed_on=attestation.reviewed_on,
    )


def _escalations(
    receipt: SessionReceipt, findings: Sequence[ReviewFinding]
) -> tuple[str, ...]:
    """Findings that a further developer attempt cannot fix, so the CEO must decide."""
    reasons: list[str] = []
    for finding in findings:
        if finding.severity is not FindingSeverity.BLOCKING:
            continue
        if finding.finding_id.startswith("protected-"):
            reasons.append(
                "the protected governance surface changed during execution; this is a "
                "CEO decision, not a correction"
            )
        elif finding.finding_id == "dependency-added":
            reasons.append(
                "a new dependency needs architecture_and_security_review before the "
                "work can continue"
            )
        elif finding.finding_id == "merge-performed":
            reasons.append("a merge was performed and only the CEO may authorize one")
        elif finding.finding_id == "nested-agents":
            reasons.append(
                "nested agents were used; changing that policy is CEO-reserved"
            )
        elif finding.finding_id == "reviewer-not-qualified":
            reasons.append(
                "no qualified reviewer answered; the review capability must be staffed"
            )
    return tuple(sorted(dict.fromkeys(reasons)))


def _outcome(value: Any, field_name: str) -> ReviewOutcome:
    if not isinstance(value, str):
        raise EngineeringError(f"review.{field_name} must be a string")
    try:
        return ReviewOutcome(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ReviewOutcome)
        raise EngineeringError(f"review.{field_name} must be one of: {allowed}") from exc


def _listed(value: Any, field_name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EngineeringError(f"{field_name} must be a list")
    return tuple(value)


def _criterion(value: Any, index: int) -> CriterionFinding:
    if not isinstance(value, Mapping):
        raise EngineeringError(f"criteria[{index}] must be a mapping")
    extra = sorted(set(value) - {"criterion", "satisfied", "evidence_ref"})
    if extra:
        raise EngineeringError(
            f"criteria[{index}] has unknown field(s): " + ", ".join(extra)
        )
    return CriterionFinding(
        criterion=str(value.get("criterion", "")),
        satisfied=bool(value.get("satisfied", False)),
        evidence_ref=str(value.get("evidence_ref", "")),
    )


def _finding(value: Any, index: int) -> ReviewFinding:
    if not isinstance(value, Mapping):
        raise EngineeringError(f"findings[{index}] must be a mapping")
    extra = sorted(
        set(value) - {"finding_id", "severity", "summary", "evidence_ref", "deterministic"}
    )
    if extra:
        raise EngineeringError(
            f"findings[{index}] has unknown field(s): " + ", ".join(extra)
        )
    severity = value.get("severity")
    if not isinstance(severity, str):
        raise EngineeringError(f"findings[{index}].severity must be a string")
    try:
        parsed = FindingSeverity(severity)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in FindingSeverity)
        raise EngineeringError(
            f"findings[{index}].severity must be one of: {allowed}"
        ) from exc
    return ReviewFinding(
        finding_id=str(value.get("finding_id", "")),
        severity=parsed,
        summary=str(value.get("summary", "")),
        evidence_ref=str(value.get("evidence_ref", "")),
        deterministic=bool(value.get("deterministic", False)),
    )


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineeringError(f"{field_name} must be an integer")
    return value


__all__ = [
    "REVIEW_VERSION",
    "SEVERITY_ORDER",
    "CriterionFinding",
    "EngineeringReview",
    "FindingSeverity",
    "ReviewFinding",
    "ReviewOutcome",
    "ReviewerAttestation",
    "adjudicate",
    "deterministic_findings",
]
