"""The append-only engineering history, under a directory the caller names.

```
<state_dir>/engineering/requests/<request>/000001.json
<state_dir>/engineering/work_orders/<work-order>/000001.json
<state_dir>/engineering/plans/<work-order>/000001.json
<state_dir>/engineering/jobs/<work-order>/000001.json
<state_dir>/engineering/attestations/<work-order>/000001.json
<state_dir>/engineering/reviews/<work-order>/000001.json
<state_dir>/engineering/gate_verdicts/<work-order>/000001.json
<state_dir>/engineering/results/<work-order>/000001.json
<state_dir>/engineering/decisions/<work-order>/000001.json
```

No database and no index. The current state of a job is the last record in its
`jobs/` directory; the history is the whole directory, sorted. Writing uses
`company.runtime.state_paths.append_json_bytes`, so a record is created with
`O_EXCL` and a second write never replaces a first — the same mechanism
`ExecutionStore` uses, deliberately reused rather than reimplemented
(`state_paths` says why: a second copy of the exclusive-create loop is a second
place for an overwrite bug).

## The one asymmetric directory

`work_orders/` is the immutability enforcement. `put_work_order` writes the
work order once. A second write of the **identical** work order returns the
existing pointer, because re-running an idempotent command must not fail. A
second write of a **differing** work order under the same id is refused
outright: the authorized work order is the authority ceiling, and a ceiling
that can be rewritten is not one.

Everything else is genuinely append-only — a second review, a later gate
verdict, a corrected result all land beside their predecessors, never over
them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, TypeVar

from ai_platform.references import assert_reference
from ai_platform.serde import dumps
from ai_platform.serde import fingerprint as _fingerprint
from company.runtime.state_paths import (
    StateStoreError,
    append_json_bytes,
    sequence_of,
    sorted_records,
    task_directory_name,
)

from .decision import CEODecision
from .errors import AuthorityEscalation, EngineeringError
from .gate_evidence import GateVerdict
from .intake import CEORequest
from .lifecycle import EngineeringJob
from .plan import ImplementationPlan
from .result import EngineeringResult
from .review import EngineeringReview, ReviewOutcome, ReviewerAttestation
from .work_order import EngineeringWorkOrder


T = TypeVar("T")


class EngineeringStoreError(StateStoreError):
    """An engineering history is missing, malformed, or contradicts itself."""


@dataclass(frozen=True)
class EngineeringRecordPointer:
    """Where one engineering record lives, what it hashes to, and its sequence."""

    record_ref: str
    fingerprint: str
    sequence: int

    def __post_init__(self) -> None:
        assert_reference(self.record_ref, "engineering.record_ref")
        if len(self.fingerprint) != 16 or any(
            char not in "0123456789abcdef" for char in self.fingerprint
        ):
            raise EngineeringError(
                "engineering.fingerprint must be a 16-character lowercase hex digest"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise EngineeringError("engineering.sequence must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_ref": self.record_ref,
            "fingerprint": self.fingerprint,
            "sequence": self.sequence,
        }


class EngineeringStore:
    """Requests in, work orders fixed, everything after them appended."""

    _ROOT = "engineering"
    _REQUESTS = "requests"
    _WORK_ORDERS = "work_orders"
    _PLANS = "plans"
    _JOBS = "jobs"
    _ATTESTATIONS = "attestations"
    _REVIEWS = "reviews"
    _GATE_VERDICTS = "gate_verdicts"
    _RESULTS = "results"
    _DECISIONS = "decisions"

    KINDS: tuple[str, ...] = (
        _REQUESTS,
        _WORK_ORDERS,
        _PLANS,
        _JOBS,
        _ATTESTATIONS,
        _REVIEWS,
        _GATE_VERDICTS,
        _RESULTS,
        _DECISIONS,
    )

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise EngineeringStoreError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).resolve()
        self.root = self.state_dir / self._ROOT

    # --- writing -----------------------------------------------------------

    def append_request(self, request: CEORequest) -> EngineeringRecordPointer:
        return self._append(self._REQUESTS, request.request_id, request, _digest(request))

    def put_work_order(self, order: EngineeringWorkOrder) -> EngineeringRecordPointer:
        """Write the work order once. Identical is idempotent; differing is refused."""
        existing = self.work_order_records(order.work_order_id)
        for pointer, stored in existing:
            if stored.fingerprint() == order.fingerprint():
                return pointer
        if existing:
            raise AuthorityEscalation(
                f"work order {order.work_order_id} is already authorized with "
                f"fingerprint {existing[-1][1].fingerprint()}, and a differing one "
                f"({order.fingerprint()}) was offered. The authorized work order is "
                "immutable; a changed request is a new work order with a new id."
            )
        return self._append(
            self._WORK_ORDERS, order.work_order_id, order, order.fingerprint()
        )

    def append_plan(self, plan: ImplementationPlan) -> EngineeringRecordPointer:
        return self._append(self._PLANS, plan.work_order_id, plan, plan.fingerprint())

    def append_job(self, job: EngineeringJob) -> EngineeringRecordPointer:
        return self._append(self._JOBS, job.work_order_id, job, job.fingerprint())

    def append_attestation(
        self, attestation: ReviewerAttestation
    ) -> EngineeringRecordPointer:
        """Persist a reviewer's attestation, valid or not. A refused one is history."""
        return self._append(
            self._ATTESTATIONS,
            attestation.work_order_id,
            attestation,
            attestation.fingerprint(),
        )

    def append_review(self, review: EngineeringReview) -> EngineeringRecordPointer:
        return self._append(
            self._REVIEWS, review.work_order_id, review, review.fingerprint()
        )

    def append_gate_verdict(self, verdict: GateVerdict) -> EngineeringRecordPointer:
        return self._append(
            self._GATE_VERDICTS, verdict.work_order_id, verdict, verdict.fingerprint()
        )

    def append_result(self, result: EngineeringResult) -> EngineeringRecordPointer:
        return self._append(
            self._RESULTS, result.work_order_id, result, result.fingerprint()
        )

    def append_decision(self, decision: CEODecision) -> EngineeringRecordPointer:
        return self._append(
            self._DECISIONS, decision.work_order_id, decision, decision.fingerprint()
        )

    # --- reading -----------------------------------------------------------

    def requests(self, request_id: str) -> tuple[CEORequest, ...]:
        return tuple(
            item for _pointer, item in self._records(self._REQUESTS, request_id, CEORequest.from_mapping)
        )

    def work_order_records(
        self, work_order_id: str
    ) -> tuple[tuple[EngineeringRecordPointer, EngineeringWorkOrder], ...]:
        return self._records(
            self._WORK_ORDERS, work_order_id, EngineeringWorkOrder.from_mapping
        )

    def work_order(self, work_order_id: str) -> EngineeringWorkOrder | None:
        records = self.work_order_records(work_order_id)
        return records[0][1] if records else None

    def plans(self, work_order_id: str) -> tuple[ImplementationPlan, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._PLANS, work_order_id, ImplementationPlan.from_mapping
            )
        )

    def jobs(self, work_order_id: str) -> tuple[EngineeringJob, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._JOBS, work_order_id, EngineeringJob.from_mapping
            )
        )

    def job(self, work_order_id: str) -> EngineeringJob | None:
        """The current state of one job: the last snapshot appended."""
        records = self.jobs(work_order_id)
        return records[-1] if records else None

    def attestations(self, work_order_id: str) -> tuple[ReviewerAttestation, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._ATTESTATIONS, work_order_id, ReviewerAttestation.from_mapping
            )
        )

    def reviews(self, work_order_id: str) -> tuple[EngineeringReview, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._REVIEWS, work_order_id, EngineeringReview.from_mapping
            )
        )

    def review(self, work_order_id: str) -> EngineeringReview | None:
        records = self.reviews(work_order_id)
        return records[-1] if records else None

    def gate_verdicts(self, work_order_id: str) -> tuple[GateVerdict, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._GATE_VERDICTS, work_order_id, GateVerdict.from_mapping
            )
        )

    def gate_verdict(self, work_order_id: str) -> GateVerdict | None:
        records = self.gate_verdicts(work_order_id)
        return records[-1] if records else None

    def results(self, work_order_id: str) -> tuple[EngineeringResult, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._RESULTS, work_order_id, EngineeringResult.from_mapping
            )
        )

    def result(self, work_order_id: str) -> EngineeringResult | None:
        records = self.results(work_order_id)
        return records[-1] if records else None

    def decisions(self, work_order_id: str) -> tuple[CEODecision, ...]:
        return tuple(
            item
            for _pointer, item in self._records(
                self._DECISIONS, work_order_id, CEODecision.from_mapping
            )
        )

    def work_order_ids(self) -> tuple[str, ...]:
        """Every work order the store holds, by its own recorded id."""
        directory = self.root / self._WORK_ORDERS
        if not directory.is_dir():
            return ()
        found: set[str] = set()
        for task_dir in sorted(directory.iterdir()):
            if not task_dir.is_dir():
                continue
            for path in sorted_records(task_dir):
                data = self._load(path)
                identity = data.get("work_order_id")
                if isinstance(identity, str) and identity:
                    found.add(identity)
        return tuple(sorted(found))

    def history(self, work_order_id: str) -> dict[str, Any]:
        """A compact, JSON-ready answer to "what happened to this work order?"."""
        order = self.work_order(work_order_id)
        job = self.job(work_order_id)
        return {
            "work_order_id": work_order_id,
            "work_order": {
                "fingerprint": order.fingerprint() if order else "",
                "objective": order.objective if order else "",
                "requested_by": order.requested_by if order else "",
                "authorized_branch": order.authorized_branch if order else "",
                "authorized_paths": list(order.authorized_paths) if order else [],
                "max_developer_attempts": order.max_developer_attempts if order else 0,
            },
            "state": job.state.value if job else "",
            "developer_attempts": job.developer_attempts if job else 0,
            "reviewer_passes_completed": sum(
                1 for item in self.reviews(work_order_id)
                if item.outcome is ReviewOutcome.PASS
            ),
            "corrections_remaining": job.corrections_remaining if job else 0,
            "pending_decisions": list(job.pending_decisions) if job else [],
            "transitions": [
                {
                    "from": item.from_state.value,
                    "to": item.to_state.value,
                    "on": item.on.isoformat(),
                    "actor": item.actor,
                    "reason": item.reason,
                }
                for item in (job.transitions if job else ())
            ],
            "plans": [item.fingerprint() for item in self.plans(work_order_id)],
            "attestations": [
                {"review_id": item.review_id, "reviewer": item.reviewer, "verdict": item.verdict.value}
                for item in self.attestations(work_order_id)
            ],
            "reviews": [
                {
                    "review_id": item.review_id,
                    "outcome": item.outcome.value,
                    "attested": item.attested_outcome.value,
                    "deterministic": item.deterministic_outcome.value,
                    "reviewer": item.reviewer,
                    "implementer": item.implementer,
                }
                for item in self.reviews(work_order_id)
            ],
            "gate_verdicts": [
                {
                    "report_id": item.report_id,
                    "readiness": item.readiness.value,
                    "blockers": len(item.blockers),
                }
                for item in self.gate_verdicts(work_order_id)
            ],
            "results": [item.fingerprint() for item in self.results(work_order_id)],
            "decisions": [
                {
                    "decision_id": item.decision_id,
                    "verdict": item.verdict.value,
                    "decided_by": item.decided_by,
                    "authorizes_merge": item.authorizes_merge,
                }
                for item in self.decisions(work_order_id)
            ],
        }

    def integrity(self, work_order_id: str) -> tuple[str, ...]:
        """Every contradiction the stored records prove, as sorted findings."""
        problems: list[str] = []
        order = self.work_order(work_order_id)
        if order is None:
            return (f"{work_order_id}: no work order is stored",)
        expected = order.fingerprint()
        records = self.work_order_records(work_order_id)
        if len(records) > 1:
            problems.append(
                f"{work_order_id}: {len(records)} work order records exist; a work "
                "order is authorized once"
            )
        for job in self.jobs(work_order_id):
            if job.work_order_fingerprint != expected:
                problems.append(
                    f"{work_order_id}: a job snapshot references work order "
                    f"{job.work_order_fingerprint}, not {expected}"
                )
        for review in self.reviews(work_order_id):
            if review.work_order_fingerprint != expected:
                problems.append(
                    f"{work_order_id}: review {review.review_id} references work order "
                    f"{review.work_order_fingerprint}, not {expected}"
                )
            if review.implementer == review.reviewer:
                problems.append(
                    f"{work_order_id}: review {review.review_id} names "
                    f"{review.reviewer} as both implementer and reviewer"
                )
        for decision in self.decisions(work_order_id):
            if decision.work_order_fingerprint != expected:
                problems.append(
                    f"{work_order_id}: decision {decision.decision_id} references work "
                    f"order {decision.work_order_fingerprint}, not {expected}"
                )
            if decision.authorizes_merge:
                problems.append(
                    f"{work_order_id}: decision {decision.decision_id} claims merge "
                    "authority, which no decision carries"
                )
        for result in self.results(work_order_id):
            if result.authorizes_merge:
                problems.append(
                    f"{work_order_id}: a stored result claims merge authority"
                )
        return tuple(sorted(dict.fromkeys(problems)))

    # --- internals ---------------------------------------------------------

    def _directory(self, kind: str, identity: str) -> Path:
        if kind not in self.KINDS:
            raise EngineeringStoreError(f"unsupported engineering record kind {kind!r}")
        return self.root / kind / task_directory_name(identity)

    def _append(
        self, kind: str, identity: str, record: Any, fingerprint: str
    ) -> EngineeringRecordPointer:
        path = append_json_bytes(
            self._directory(kind, identity), dumps(record).encode("utf-8")
        )
        return EngineeringRecordPointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=fingerprint,
            sequence=sequence_of(path),
        )

    def _records(
        self, kind: str, identity: str, decoder: Callable[[Mapping[str, Any]], T]
    ) -> tuple[tuple[EngineeringRecordPointer, T], ...]:
        out: list[tuple[EngineeringRecordPointer, T]] = []
        for path in sorted_records(self._directory(kind, identity)):
            data = self._load(path)
            try:
                record = decoder(data)
            except EngineeringError as exc:
                raise EngineeringStoreError(f"{path}: invalid {kind} record: {exc}") from exc
            out.append(
                (
                    EngineeringRecordPointer(
                        record_ref=path.relative_to(self.state_dir).as_posix(),
                        fingerprint=_digest(record),
                        sequence=sequence_of(path),
                    ),
                    record,
                )
            )
        return tuple(out)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EngineeringStoreError(
                f"cannot read engineering record {path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise EngineeringStoreError(
                f"{path}: an engineering record must be a JSON object"
            )
        return data


def _digest(record: Any) -> str:
    """The record's own fingerprint if it has one, else one over its fields.

    `CEORequest` is the only record here with no `fingerprint()` of its own: it
    is testimony rather than an authority record, and nothing compares two of
    them. It still needs a pointer digest, so it gets one over its fields.
    """
    own = getattr(record, "fingerprint", None)
    if callable(own):
        return own()
    return _fingerprint(record)


__all__ = [
    "EngineeringRecordPointer",
    "EngineeringStore",
    "EngineeringStoreError",
]
