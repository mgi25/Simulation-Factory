"""Has the governance surface moved since a work order was authorized?

`ProtectedSurface.verify` already answers that, and until now the only caller
was `review.deterministic_findings`. So the answer existed and could be reached
only by completing a review, which is the wrong time to learn it: a work order
authorized in the morning and reviewed on Thursday spends three days during
which nobody can ask.

This module is the question on its own. It reads one work order out of the
store, re-digests its protected paths against a checkout, and reports what
moved. It changes nothing, and it does not touch the job's state — a drift
check is an observation, and turning it into a transition would let an
observation block work that review has not looked at yet.

## Why it reports `unknown` rather than `ok` for an absent work order

A work order the store does not hold cannot be checked, and a checker that
answers "no findings" to a question it could not ask is worse than one that
refuses. `DriftStatus` has three values for that reason, and `UNKNOWN` is the
one that does the work - the same reading `company/integration` gives its own
`unknown`, for the same reason.

## Scope

One work order per call, by id. The caller names the checkout, so the same
work order can be checked against two trees - which is exactly what a reviewer
wants when a developer says the change is on a branch.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .common import assert_day, assert_ref
from .errors import EngineeringError
from .store import EngineeringStore


class DriftStatus(str, Enum):
    """Three answers, and only one of them is a proof of anything."""

    UNCHANGED = "unchanged"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"

    @property
    def is_evidence(self) -> bool:
        """Whether this status may be relied on. `UNKNOWN` may not."""
        return self is not DriftStatus.UNKNOWN


@dataclass(frozen=True)
class GovernanceDriftReport:
    """One work order's protected surface, re-read against one checkout."""

    work_order_id: str
    work_order_fingerprint: str
    status: DriftStatus
    checked_on: dt.date
    repo_root: str
    paths_checked: int = 0
    findings: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "work_order_id", assert_ref(self.work_order_id, "drift.work_order_id")
        )
        if not isinstance(self.work_order_fingerprint, str):
            raise EngineeringError("drift.work_order_fingerprint must be a string")
        if self.work_order_fingerprint and len(self.work_order_fingerprint) != 16:
            raise EngineeringError(
                "drift.work_order_fingerprint must be empty or a 16-character digest"
            )
        if not isinstance(self.status, DriftStatus):
            raise EngineeringError("drift.status must be a DriftStatus value")
        object.__setattr__(self, "checked_on", assert_day(self.checked_on, "drift.checked_on"))
        if not isinstance(self.repo_root, str) or not self.repo_root.strip():
            raise EngineeringError("drift.repo_root must name the checkout that was read")
        if (
            isinstance(self.paths_checked, bool)
            or not isinstance(self.paths_checked, int)
            or self.paths_checked < 0
        ):
            raise EngineeringError("drift.paths_checked must be a non-negative integer")
        for name in ("findings", "missing_evidence"):
            values = getattr(self, name)
            if isinstance(values, (str, bytes)) or not isinstance(values, tuple):
                raise EngineeringError(f"drift.{name} must be a tuple of strings")
            object.__setattr__(self, name, tuple(str(item) for item in values))
        # The three statuses each have exactly one consistent shape, and a
        # report that claims one shape while carrying another is the failure
        # this record exists to prevent.
        if self.status is DriftStatus.DRIFTED and not self.findings:
            raise EngineeringError(
                "a drifted report names what drifted; a finding-free drift is not a "
                "finding anybody can act on"
            )
        if self.status is DriftStatus.UNCHANGED and self.findings:
            raise EngineeringError(
                "an unchanged report carries no finding; the status is derived from "
                "the findings rather than stated beside them"
            )
        if self.status is DriftStatus.UNKNOWN and not self.missing_evidence:
            raise EngineeringError(
                "an unknown report names what is missing, or nobody can make it known"
            )
        if self.status is not DriftStatus.UNKNOWN and self.missing_evidence:
            raise EngineeringError(
                "a report that reached an answer has no missing evidence"
            )

    @property
    def ok(self) -> bool:
        """True only when the surface was checked and had not moved."""
        return self.status is DriftStatus.UNCHANGED

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def render_text(self) -> str:
        lines = [
            f"GOVERNANCE DRIFT  {self.status.value.upper()}",
            f"  work order: {self.work_order_id} ({self.work_order_fingerprint or 'not found'})",
            f"  checked   : {self.repo_root} on {self.checked_on.isoformat()}",
            f"  protected : {self.paths_checked} path(s) re-read",
        ]
        if self.findings:
            lines.append(f"  findings ({len(self.findings)}):")
            lines.extend(f"    - {item}" for item in self.findings)
        elif self.missing_evidence:
            lines.append("  cannot answer:")
            lines.extend(f"    - {item}" for item in self.missing_evidence)
        else:
            lines.append("  findings  : none; the governance surface is byte-identical")
        return "\n".join(lines) + "\n"


def verify_work_order(
    store: EngineeringStore,
    work_order_id: str,
    *,
    repo_root: Path | str,
    on: dt.date,
) -> GovernanceDriftReport:
    """Re-read one work order's protected surface against `repo_root`.

    Reads two things and writes nothing: the work order out of the store, and
    the protected files off the disk.
    """
    day = assert_day(on, "on")
    root = Path(repo_root)
    order = store.work_order(work_order_id)
    if order is None:
        return GovernanceDriftReport(
            work_order_id=work_order_id,
            work_order_fingerprint="",
            status=DriftStatus.UNKNOWN,
            checked_on=day,
            repo_root=root.as_posix(),
            missing_evidence=(
                f"no work order {work_order_id!r} is stored under {store.state_dir}",
            ),
        )
    if not root.is_dir():
        return GovernanceDriftReport(
            work_order_id=order.work_order_id,
            work_order_fingerprint=order.fingerprint(),
            status=DriftStatus.UNKNOWN,
            checked_on=day,
            repo_root=root.as_posix(),
            missing_evidence=(f"{root.as_posix()} is not a directory that can be read",),
        )
    findings = order.protected.verify(root)
    return GovernanceDriftReport(
        work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(),
        status=DriftStatus.DRIFTED if findings else DriftStatus.UNCHANGED,
        checked_on=day,
        repo_root=root.as_posix(),
        paths_checked=len(order.protected.entries),
        findings=findings,
    )


def verify_all(
    store: EngineeringStore, *, repo_root: Path | str, on: dt.date
) -> tuple[GovernanceDriftReport, ...]:
    """Every work order the store holds, in id order."""
    return tuple(
        verify_work_order(store, work_order_id, repo_root=repo_root, on=on)
        for work_order_id in store.work_order_ids()
    )


__all__ = ["DriftStatus", "GovernanceDriftReport", "verify_all", "verify_work_order"]
