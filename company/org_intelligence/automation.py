"""Work that happened the same way more than once, and might not need a mind.

## The inference this module is built to prevent

"That sounds repetitive" is not evidence. A task described as *run the QC sweep*
may be five different judgement calls wearing one name, and an organization that
automates it because the sentence repeats has automated the name, not the work.

So `RepeatedWork` cannot be constructed without the instances. Not a count -
distinct references, one per occurrence, each pointing at something a second
person can open. Below `minimum_instances` the record refuses to exist, which
means `AUTOMATE_DETERMINISTIC_STEP` has no path into this package that does not
go through counted, referenced repetition.

## The threshold is on the record

`minimum_instances` is a field rather than a module constant, so the bar a
particular claim cleared is stored beside the claim. Its floor is two, and that
one is a definition rather than an opinion: work observed once is not repeated
work, and no configuration should be able to say otherwise.

## Deterministic is asserted, and the assertion is signed

`deterministic_rationale` is prose a person writes: *the same inputs produce the
same output, and the output is checked by a test rather than by judgement*.
Nothing here verifies it - a program cannot tell whether a step is deterministic
by reading its name. What the field does is make the claim explicit, attributable
and arguable, which is the most a deterministic layer can honestly do.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    positive_int,
)
from .errors import OrgIntelligenceError
from .findings import FindingCategory, OrganizationalFinding, build_finding
from .signals import (
    Direction,
    Measurement,
    OrganizationalSignal,
    SignalType,
    SubjectKind,
)
from .window import ReviewWindow

# Work observed once is not repeated work. Two is the floor by definition, and
# no policy may lower it.
ABSOLUTE_MINIMUM_INSTANCES = 2


@dataclass(frozen=True)
class RepeatedWork:
    """The same manual step, observed at these references, this many times."""

    action_id: str
    instances: tuple[str, ...]
    deterministic_rationale: str
    window: ReviewWindow
    evidence: tuple[Evidence, ...] = ()
    minimum_instances: int = 3
    performed_by: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.action_id, "action_id")
        if not isinstance(self.window, ReviewWindow):
            raise OrgIntelligenceError("repeated work window must be a ReviewWindow")
        assert_prose(self.deterministic_rationale, "deterministic_rationale")
        positive_int(
            self.minimum_instances,
            "minimum_instances",
            minimum=ABSOLUTE_MINIMUM_INSTANCES,
        )
        object.__setattr__(
            self,
            "instances",
            tuple(assert_ref(item, "repeated work instance") for item in self.instances or ()),
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        for name in ("performed_by", "notes"):
            if not isinstance(getattr(self, name), str):
                raise OrgIntelligenceError(f"repeated work {name} must be a string")

        distinct = tuple(dict.fromkeys(self.instances))
        if len(distinct) != len(self.instances):
            raise OrgIntelligenceError(
                f"{self.action_id}: the same instance reference appears twice. One "
                "occurrence referenced twice is one occurrence"
            )
        if len(distinct) < self.minimum_instances:
            raise OrgIntelligenceError(
                f"{self.action_id}: {len(distinct)} instance(s) is below the "
                f"{self.minimum_instances} this claim declares it needs. An automation "
                "candidate needs the occurrences, not an impression that the work repeats"
            )
        assert_evidence_backed(
            self.evidence,
            f"repeated work {self.action_id} evidence",
            "somebody has to be able to open the occurrences and see the same step",
        )

    @property
    def occurrences(self) -> int:
        return len(self.instances)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["window"] = self.window.to_dict()
        base["occurrences"] = self.occurrences
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepeatedWork:
        return cls(
            action_id=data["action_id"],
            instances=tuple(data.get("instances", ())),
            deterministic_rationale=data["deterministic_rationale"],
            window=ReviewWindow.from_dict(data["window"]),
            evidence=evidence_tuple(data.get("evidence")),
            minimum_instances=data.get("minimum_instances", 3),
            performed_by=data.get("performed_by", ""),
            notes=data.get("notes", ""),
        )


def automation_signal(
    repeated: RepeatedWork, *, prefix: str = "sig-auto"
) -> OrganizationalSignal:
    """One `manual_repeat_work` signal. The count is the measurement."""
    if not isinstance(repeated, RepeatedWork):
        raise OrgIntelligenceError("automation_signal takes a RepeatedWork")
    return OrganizationalSignal(
        signal_id=f"{prefix}-{repeated.action_id.replace('_', '-')}",
        type=SignalType.MANUAL_REPEAT_WORK,
        subject=repeated.action_id,
        subject_kind=SubjectKind.WORKFLOW,
        window=repeated.window,
        detail=(
            f"{repeated.action_id} was performed manually {repeated.occurrences} time(s) "
            f"between {repeated.window.start.isoformat()} and "
            f"{repeated.window.end.isoformat()}"
            + (f" by {repeated.performed_by}" if repeated.performed_by else "")
        ),
        measurement=Measurement(
            value=float(repeated.occurrences),
            unit="manual_occurrences",
            threshold=float(repeated.minimum_instances),
            direction=Direction.HIGHER_IS_WORSE,
            sample_size=repeated.occurrences,
        ),
        evidence=repeated.evidence,
        missing_measurements=(
            "time or resources spent per occurrence: not recorded, so the saving from "
            "automating this is unquantified",
        ),
        caveats=(
            "determinism is asserted by whoever filed this, not verified: "
            + repeated.deterministic_rationale,
        ),
    )


def automation_candidate(
    finding_id: str,
    repeated: RepeatedWork,
    *,
    signals: Iterable[OrganizationalSignal] = (),
    review_id: str = "",
) -> OrganizationalFinding:
    """An `automation_candidate` finding, built only from counted repetition.

    The finding inherits the signal's caveat about determinism being asserted
    and adds the one question that decides whether automating is worth it -
    whether the step is still the same step next month.
    """
    supporting = (automation_signal(repeated),) + tuple(signals)
    return build_finding(
        finding_id,
        FindingCategory.AUTOMATION_CANDIDATE,
        statement=(
            f"{repeated.action_id} was performed manually {repeated.occurrences} time(s) in "
            f"{repeated.window.days} day(s) and is claimed to be deterministic; it may be "
            "worth writing once instead of doing repeatedly"
        ),
        signals=supporting,
        subjects=(repeated.action_id,),
        window=repeated.window,
        what_would_change_it=(
            "an occurrence whose inputs differ in a way the step has to judge, which would "
            "mean the work is not deterministic and the name was doing the repeating",
            "a measured cost per occurrence low enough that writing and maintaining the "
            "automation costs more than the work it replaces",
        ),
        review_id=review_id,
    )
