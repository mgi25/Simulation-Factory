"""The CEO's decision on a finished engineering job, recorded and not acted on.

Three answers — APPROVE, REQUEST_CHANGES, REJECT — and one property that makes
this module worth its own file:

> **Recording an APPROVE does nothing.**

No merge, no deploy, no publish, no branch move. `CEODecision` is testimony
that a human looked at a result and said a word. Acting on it is a separate act
this package holds no capability to perform: `company/integration/` already
refuses `subprocess` across Company OS, so there is no code here that could run
`git merge` even if someone asked it to.

That is the intentional V1 boundary of section 10 of the engineering brief, and
`tests/test_company_engineering_execution.py` asserts it by searching this
package for the words a merge would need.

## Why the decision names a person

`assert_named_person` refuses `system`, `company_os`, `claude`, `codex`, `agent`
and their neighbours. The one lie this package could tell is writing its own
approval, and the guard fails on the single field such a record must fill in.
It mirrors `company/org_intelligence/common.assert_human`, which the gate probes
for exactly this purpose in that subsystem.

## Why REQUEST_CHANGES carries required changes

A decision that sends work back without saying what to change cannot improve
the next attempt, which is the same reasoning `SessionReceipt` applies to a
rejection with no `rejection_reason`. So `required_changes` is mandatory for
REQUEST_CHANGES and refused for APPROVE.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    ref_tuple,
    text_tuple,
)
from .errors import EngineeringError
from .lifecycle import EngineeringJob, JobState


DECISION_VERSION = 1


class CEOVerdict(str, Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


@dataclass(frozen=True)
class CEODecision:
    """One human decision on one engineering job. Evidence, never an action."""

    decision_id: str
    work_order_id: str
    work_order_fingerprint: str
    verdict: CEOVerdict
    decided_by: str
    decided_on: dt.date
    rationale: str
    reviewed_state: JobState
    required_changes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    authorizes_merge: bool = False
    version: int = DECISION_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", assert_record_id(self.decision_id, "decision.decision_id")
        )
        object.__setattr__(
            self,
            "work_order_id",
            assert_record_id(self.work_order_id, "decision.work_order_id"),
        )
        if not isinstance(self.work_order_fingerprint, str) or len(
            self.work_order_fingerprint
        ) != 16:
            raise EngineeringError(
                "decision.work_order_fingerprint must be a 16-character digest"
            )
        if not isinstance(self.verdict, CEOVerdict):
            raise EngineeringError("decision.verdict must be a CEOVerdict value")
        object.__setattr__(
            self, "decided_by", assert_named_person(self.decided_by, "decision.decided_by")
        )
        object.__setattr__(
            self, "decided_on", assert_day(self.decided_on, "decision.decided_on")
        )
        object.__setattr__(
            self, "rationale", assert_prose(self.rationale, "decision.rationale")
        )
        if not isinstance(self.reviewed_state, JobState):
            raise EngineeringError("decision.reviewed_state must be a JobState value")
        object.__setattr__(
            self,
            "required_changes",
            text_tuple(self.required_changes, "decision.required_changes", limit=16),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            ref_tuple(self.evidence_refs, "decision.evidence_refs", limit=24),
        )
        if self.verdict is CEOVerdict.REQUEST_CHANGES and not self.required_changes:
            raise EngineeringError(
                "a request for changes must name the changes required; an unexplained "
                "one cannot improve the next attempt"
            )
        if self.verdict is CEOVerdict.APPROVE and self.required_changes:
            raise EngineeringError(
                "an approval cannot also require changes; decide one of the two"
            )
        if self.verdict is CEOVerdict.APPROVE and self.reviewed_state is not (
            JobState.READY_FOR_APPROVAL
        ):
            raise EngineeringError(
                f"a job in {self.reviewed_state.value!r} cannot be approved. Only "
                "ready_for_approval means review passed and the gate was satisfied."
            )
        if self.authorizes_merge is not False:
            raise EngineeringError(
                "a recorded decision never carries merge authority. Approving means a "
                "human read the result; integrating is a separate act, performed "
                "outside Company OS, which holds no capability to perform it."
            )
        if self.version != DECISION_VERSION:
            raise EngineeringError(f"decision.version must be {DECISION_VERSION}")

    @property
    def sends_back(self) -> bool:
        return self.verdict is CEOVerdict.REQUEST_CHANGES

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def next_state(self) -> JobState:
        """The state this decision moves the job to. Never an approved state.

        APPROVE and REJECT both close the job, because both end the company's
        work on it — the difference is recorded in the verdict, not in a state
        that could be mistaken for permission to integrate.

        REQUEST_CHANGES returns the job to `planning`, not to `developing`:
        only issuing a packet enters `developing`, and only that should spend a
        developer attempt.
        """
        return JobState.PLANNING if self.sends_back else JobState.CLOSED

    def apply_to(self, job: EngineeringJob) -> EngineeringJob:
        """Move the job as this decision directs, and nothing else.

        It records. It does not merge, deploy, publish, tag or push. If the
        decision sends work back and the attempt ceiling is spent, `advance`
        raises — a further correction needs a new work order, which is another
        CEO decision.
        """
        if job.work_order_id != self.work_order_id:
            raise EngineeringError(
                f"decision names work order {self.work_order_id!r}, and the job is "
                f"{job.work_order_id!r}"
            )
        if job.work_order_fingerprint != self.work_order_fingerprint:
            raise EngineeringError(
                "the decision was taken against a different work order fingerprint "
                "than the job carries; the authorized work order is immutable"
            )
        if job.state is not self.reviewed_state:
            raise EngineeringError(
                f"the decision was taken on a job in {self.reviewed_state.value!r} and "
                f"the job is now in {job.state.value!r}; re-read the result and decide "
                "again"
            )
        return job.advance(
            self.next_state(),
            on=self.decided_on,
            reason=f"CEO {self.verdict.value}: {self.rationale}",
            actor=self.decided_by,
            evidence_refs=self.evidence_refs,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CEODecision":
        if not isinstance(data, Mapping):
            raise EngineeringError("a decision must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError(
                "decision has unknown field(s): "
                + ", ".join(unknown)
                + ". A decision records a human answer; a field outside the schema is "
                "refused rather than ignored."
            )
        verdict = data.get("verdict")
        if not isinstance(verdict, str):
            raise EngineeringError("decision.verdict must be a string")
        try:
            parsed = CEOVerdict(verdict)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in CEOVerdict)
            raise EngineeringError(f"decision.verdict must be one of: {allowed}") from exc
        state = data.get("reviewed_state")
        if not isinstance(state, str):
            raise EngineeringError("decision.reviewed_state must be a string")
        try:
            reviewed = JobState(state)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in JobState)
            raise EngineeringError(
                f"decision.reviewed_state must be one of: {allowed}"
            ) from exc
        changes = data.get("required_changes", ())
        if isinstance(changes, (str, bytes)) or not isinstance(changes, (list, tuple)):
            raise EngineeringError("decision.required_changes must be a list")
        refs = data.get("evidence_refs", ())
        if isinstance(refs, (str, bytes)) or not isinstance(refs, (list, tuple)):
            raise EngineeringError("decision.evidence_refs must be a list")
        version = data.get("version", DECISION_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise EngineeringError("decision.version must be an integer")
        return cls(
            decision_id=str(data.get("decision_id", "")),
            work_order_id=str(data.get("work_order_id", "")),
            work_order_fingerprint=str(data.get("work_order_fingerprint", "")),
            verdict=parsed,
            decided_by=str(data.get("decided_by", "")),
            decided_on=assert_day(data.get("decided_on"), "decision.decided_on"),
            rationale=str(data.get("rationale", "")),
            reviewed_state=reviewed,
            required_changes=tuple(str(item) for item in changes),
            evidence_refs=tuple(str(item) for item in refs),
            authorizes_merge=bool(data.get("authorizes_merge", False)),
            version=version,
        )


__all__ = ["DECISION_VERSION", "CEODecision", "CEOVerdict"]
