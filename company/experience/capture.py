"""Turning a settled engineering attempt into an episode, from canonical records only.

No model summarises anything here. Capture reads the records the engineering
loop already wrote, follows the links the loop already recorded between them,
and refuses whatever it cannot establish.

## Following the job's own links, never guessing by position

Every move of an `EngineeringJob` carries `evidence_refs`, and the orchestrator
puts exactly the right records in them:

| transition | names |
|---|---|
| `planning -> developing` | the packet and its authority snapshot |
| `developing -> testing` | the receipt that moved the job, and its `ResourceUsageRecord` |
| `reviewing -> ...` | the attestation and the adjudicated review |
| `gate -> ...` | the gate verdict |

So one attempt is the run of transitions from a `-> developing` to the next,
and every record it produced is named by the job itself. That matters most for
the usage record: `ResourceUsageRecord` has no field naming the receipt it
describes (carried-forward finding 5), and pairing them by position breaks the
moment an evidence-format rejection adds a receipt that did not move the job.
The `-> testing` transition names both halves of the pair, so capture joins
them exactly and never by index. A receipt for the same packet attempt that is
*not* the one the transition names was an evidence-format rejection, and is
counted as one.

## When an attempt is settled

An attempt is capturable once the job has left its execution cycle: a later
transition takes it to `planning`, `ready_for_approval`, `decision_required`,
`blocked`, `closed` or `failed`. `testing`, `reviewing` and `gate` are waits
inside the cycle, and an attempt in one of them is refused as `not_settled` -
its outcome does not exist yet.

`ready_for_approval` counts as settled although the CEO has not spoken. The
engineering verdict is complete there, and in this repository's own history
most jobs rest in that state indefinitely. The CEO's decision is canonical in
`engineering/decisions/`, and it is joined at read time by `governance_facts`,
never copied into the episode - so a later rejection downgrades a precedent
without any episode being rewritten.

## What capture refuses

Every refusal has a code from `REFUSAL_CODES`. A work order that no longer
decodes under the current schema is refused, not repaired: this repository's
own history contains two, and the honest answer is that their decision-time
features cannot be established by today's decoder.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from ai_platform.serde import as_date
from ai_platform.usage import ResourceUsageRecord
from company.efficiency.store import EfficiencyStore
from company.efficiency.telemetry import EfficiencyRecord, MeasurementSource
from company.engineering.gate_evidence import GateVerdict
from company.engineering.lifecycle import EngineeringJob, JobState, JobTransition
from company.engineering.review import EngineeringReview
from company.engineering.store import EngineeringStore
from company.runtime.execution_store import ExecutionStore
from company.runtime.state_paths import sorted_records, task_directory_name

from .errors import CaptureRefused, ExperienceConflict, ExperienceError
from .model import (
    EvidenceBasis,
    ExperienceEpisode,
    FindingNote,
    ObservedOutcome,
    PrecedentClass,
    RecordPointer,
    ResourceObservation,
    chosen_action,
    decision_features,
)
from .repository import RepositoryView, capture_provenance
from .store import ExperienceStore


REFUSAL_CODES: frozenset[str] = frozenset(
    {
        "work_order_missing",
        "work_order_undecodable",
        "no_job",
        "integrity",
        "no_packet",
        "not_settled",
        "records_undecodable",
        "provenance_unavailable",
        "conflict",
    }
)

# The states that close an attempt's execution cycle.
SETTLING_STATES: frozenset[JobState] = frozenset(
    {
        JobState.PLANNING,
        JobState.READY_FOR_APPROVAL,
        JobState.DECISION_REQUIRED,
        JobState.BLOCKED,
        JobState.CLOSED,
        JobState.FAILED,
    }
)


def _refused(code: str, detail: str) -> CaptureRefused:
    if code not in REFUSAL_CODES:  # pragma: no cover - a vocabulary slip
        raise ExperienceError(f"unknown refusal code {code!r}")
    return CaptureRefused(code, detail)


# --- attempt cycles, read off the job ---------------------------------------


@dataclass(frozen=True)
class AttemptCycle:
    """One developer attempt as the job's transitions record it."""

    packet_attempt: int
    packet_ref: str
    authority_ref: str
    decided_on: dt.date
    developing_index: int
    settle_index: int | None
    settle: JobTransition | None
    receipt_ref: str = ""
    usage_ref: str = ""
    attestation_ref: str = ""
    review_ref: str = ""
    gate_ref: str = ""

    @property
    def settled(self) -> bool:
        return self.settle is not None


def _sequence(ref: str) -> int:
    name = ref.rsplit("/", 1)[-1]
    stem = name[:-5] if name.endswith(".json") else name
    return int(stem) if stem.isdigit() else 0


def _ref_with(refs: Iterable[str], prefix: str) -> str:
    return next((ref for ref in refs if ref.startswith(prefix)), "")


def attempt_cycles(job: EngineeringJob) -> tuple[AttemptCycle, ...]:
    """Every developer attempt the job records, with the records each produced."""
    transitions = job.transitions
    starts = [i for i, t in enumerate(transitions) if t.to_state is JobState.DEVELOPING]
    cycles: list[AttemptCycle] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(transitions)
        opening = transitions[start]
        packet_ref = _ref_with(opening.evidence_refs, "execution/packets/")
        refs: dict[str, str] = {}
        settle_index: int | None = None
        for index in range(start + 1, end):
            move = transitions[index]
            if move.from_state is JobState.DEVELOPING and move.to_state is JobState.TESTING:
                refs.setdefault("receipt", _ref_with(move.evidence_refs, "execution/receipts/"))
                refs.setdefault("usage", _ref_with(move.evidence_refs, "resource_usage/"))
            if move.from_state is JobState.REVIEWING:
                refs.setdefault("attestation", _ref_with(move.evidence_refs, "engineering/attestations/"))
                refs.setdefault("review", _ref_with(move.evidence_refs, "engineering/reviews/"))
            if move.from_state is JobState.GATE:
                refs.setdefault("gate", _ref_with(move.evidence_refs, "engineering/gate_verdicts/"))
            if settle_index is None and move.to_state in SETTLING_STATES:
                settle_index = index
                break
        cycles.append(
            AttemptCycle(
                packet_attempt=_sequence(packet_ref) or position + 1,
                packet_ref=packet_ref,
                authority_ref=_ref_with(opening.evidence_refs, "execution/authorities/"),
                decided_on=opening.on,
                developing_index=start,
                settle_index=settle_index,
                settle=transitions[settle_index] if settle_index is not None else None,
                receipt_ref=refs.get("receipt", ""),
                usage_ref=refs.get("usage", ""),
                attestation_ref=refs.get("attestation", ""),
                review_ref=refs.get("review", ""),
                gate_ref=refs.get("gate", ""),
            )
        )
    return tuple(cycles)


# --- canonical record access ----------------------------------------------


def _safe_path(state_dir: Path, ref: str) -> Path:
    clean = ref.replace("\\", "/")
    if not clean or clean.startswith("/") or ".." in clean.split("/"):
        raise _refused("records_undecodable", f"{ref!r} is not a relative state reference")
    return state_dir / clean


def _load_json(state_dir: Path, ref: str) -> dict[str, Any]:
    path = _safe_path(state_dir, ref)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _refused("records_undecodable", f"{ref}: {exc}") from exc
    if not isinstance(data, dict):
        raise _refused("records_undecodable", f"{ref}: not a JSON object")
    return data


def _digest(state_dir: Path, ref: str) -> str:
    try:
        return hashlib.sha256(_safe_path(state_dir, ref).read_bytes()).hexdigest()[:16]
    except OSError as exc:
        raise _refused("records_undecodable", f"{ref}: {exc}") from exc


def _pointer(state_dir: Path, role: str, ref: str) -> RecordPointer:
    return RecordPointer(role=role, record_ref=ref, digest=_digest(state_dir, ref))


def verify_pointers(episode: ExperienceEpisode, state_dir: str | Path) -> tuple[str, ...]:
    """Every pointer whose file is gone or no longer has the digest it was indexed with."""
    root = Path(state_dir)
    problems: list[str] = []
    for pointer in episode.evidence:
        try:
            actual = hashlib.sha256(_safe_path(root, pointer.record_ref).read_bytes()).hexdigest()[:16]
        except (OSError, CaptureRefused):
            problems.append(f"{pointer.role} {pointer.record_ref} is missing")
            continue
        if actual != pointer.digest:
            problems.append(f"{pointer.role} {pointer.record_ref} changed (digest {actual}, indexed {pointer.digest})")
    return tuple(problems)


def _job_snapshot_ref(state_dir: Path, work_order_id: str, transitions: int) -> str:
    """The stored job snapshot whose history ends exactly at the settling move."""
    directory = state_dir / "engineering" / "jobs" / task_directory_name(work_order_id)
    for path in sorted_records(directory):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and len(data.get("transitions", ()) or ()) == transitions:
            return path.relative_to(state_dir).as_posix()
    return ""


def _efficiency_for(
    state_dir: Path, work_order_id: str, packet_fingerprint: str, attempt: int, receipt_fingerprint: str
) -> tuple[EfficiencyRecord | None, str]:
    try:
        records = EfficiencyStore(state_dir).records(work_order_id)
    except Exception:  # noqa: BLE001 - telemetry is optional evidence
        return None, ""
    run_id = f"execution:{packet_fingerprint}:{attempt}:receipt:{receipt_fingerprint}"
    for index, record in enumerate(records, start=1):
        if record.run_id == run_id:
            ref = f"execution/efficiency/{task_directory_name(work_order_id)}/{index:06d}.json"
            return record, ref
    return None, ""


_BASIS = {
    MeasurementSource.PROVIDER_REPORTED: EvidenceBasis.OBSERVED,
    MeasurementSource.ESTIMATED: EvidenceBasis.ESTIMATED,
    MeasurementSource.UNAVAILABLE: EvidenceBasis.UNAVAILABLE,
}


def _resources(efficiency: EfficiencyRecord | None, receipt: Any | None) -> ResourceObservation:
    """Cost with its basis. Nothing missing is ever written down as zero."""
    usage = receipt.usage if receipt is not None else None
    duration = usage.duration_s if usage is not None else None
    provider = (usage.provider or None) if usage is not None else None
    model = (usage.model or None) if usage is not None else None
    unreliable = tuple(usage.unreliable_metrics) if usage is not None else ()
    tool_calls = usage.tool_calls if usage is not None else None
    if efficiency is None:
        base = ResourceObservation.unavailable()
        return ResourceObservation(
            **{
                **{f: getattr(base, f) for f in base.__dataclass_fields__},
                "duration_s": duration,
                "duration_basis": EvidenceBasis.OBSERVED if duration is not None else EvidenceBasis.UNAVAILABLE,
                "tool_calls": tool_calls,
                "provider": provider,
                "model": model,
                "unreliable_metrics": unreliable,
            }
        )
    tokens = efficiency.tokens
    estimated = efficiency.estimated_tokens
    cost = efficiency.cost
    cost_basis = _BASIS[cost.source]
    return ResourceObservation(
        tokens_total=tokens.total_tokens,
        tokens_input=tokens.input_tokens,
        tokens_output=tokens.output_tokens,
        tokens_basis=_BASIS[tokens.source],
        estimated_tokens_total=(estimated.total_tokens if estimated is not None else None),
        cost_amount=cost.amount if cost_basis is not EvidenceBasis.UNAVAILABLE else None,
        cost_currency=cost.currency if cost_basis is not EvidenceBasis.UNAVAILABLE else "",
        cost_basis=cost_basis,
        duration_s=duration,
        duration_basis=EvidenceBasis.OBSERVED if duration is not None else EvidenceBasis.UNAVAILABLE,
        tool_calls=efficiency.tool_calls if efficiency.tool_calls is not None else tool_calls,
        provider=efficiency.provider or provider,
        model=efficiency.model or model,
        unreliable_metrics=unreliable,
    )


def _test_path(command: str) -> str:
    """A reported test command as the suite path it names, when it names one."""
    text = command.strip().replace("\\", "/")
    for token in reversed(text.split()):
        if token.startswith("tests/") and ".py" in token:
            return token.split("::", 1)[0]
    return text if len(text) <= 200 and "\n" not in text else ""


# --- one episode -------------------------------------------------------------


def build_episode(
    state_dir: str | Path,
    work_order_id: str,
    cycle: AttemptCycle,
    view: RepositoryView,
    *,
    captured_on: dt.date,
    source: str = "local",
    order: Any | None = None,
    job: EngineeringJob | None = None,
) -> ExperienceEpisode:
    """One settled attempt, indexed. Raises `CaptureRefused` with a code."""
    root = Path(state_dir).resolve()
    if not cycle.settled:
        raise _refused(
            "not_settled",
            f"{work_order_id} attempt {cycle.packet_attempt} has not left its execution "
            "cycle; its outcome does not exist yet",
        )
    if view.capsules is None:
        raise _refused("provenance_unavailable", view.capsule_error or "no capsule store to anchor against")
    engineering = EngineeringStore(root)
    if order is None:
        try:
            order = engineering.work_order(work_order_id)
        except Exception as exc:  # noqa: BLE001 - the decoder's refusal is the finding
            raise _refused("work_order_undecodable", f"{work_order_id}: {exc}") from exc
    if order is None:
        raise _refused("work_order_missing", f"no work order {work_order_id} is stored")
    problems = engineering.integrity(work_order_id)
    if problems:
        raise _refused("integrity", "; ".join(problems[:3]))

    execution = ExecutionStore(root)
    try:
        packets = execution.packet_records(work_order_id)
    except Exception as exc:  # noqa: BLE001
        raise _refused("records_undecodable", f"{work_order_id} packets: {exc}") from exc
    record = next((p for p in packets if p.pointer.record_ref == cycle.packet_ref), None)
    if record is None:
        raise _refused(
            "no_packet",
            f"{work_order_id} attempt {cycle.packet_attempt}: the job names packet "
            f"{cycle.packet_ref or '(none)'} and no such packet is stored",
        )
    packet = record.packet
    attempt = record.attempt
    notes: list[str] = []

    try:
        receipts = [
            item
            for item in execution.attempts(work_order_id)
            if item.receipt.packet_fingerprint == packet.fingerprint()
            and item.receipt.packet_attempt == attempt
        ]
    except Exception as exc:  # noqa: BLE001
        raise _refused("records_undecodable", f"{work_order_id} receipts: {exc}") from exc
    final = next((r for r in receipts if r.pointer.record_ref == cycle.receipt_ref), None)
    if cycle.receipt_ref and final is None:
        raise _refused("records_undecodable", f"the job names receipt {cycle.receipt_ref}, which is not stored")
    format_rejections = sum(1 for r in receipts if final is None or r.attempt < final.attempt)
    receipt = final.receipt if final is not None else None

    usage: ResourceUsageRecord | None = None
    if cycle.usage_ref:
        try:
            usage = ResourceUsageRecord.from_mapping(_load_json(root, cycle.usage_ref))
        except (TypeError, ValueError) as exc:
            raise _refused("records_undecodable", f"{cycle.usage_ref}: {exc}") from exc

    review: EngineeringReview | None = None
    if cycle.review_ref:
        try:
            review = EngineeringReview.from_mapping(_load_json(root, cycle.review_ref))
        except (TypeError, ValueError) as exc:
            raise _refused("records_undecodable", f"{cycle.review_ref}: {exc}") from exc
        if review.packet_attempt and review.packet_attempt != attempt:
            raise _refused(
                "integrity",
                f"review {review.review_id} answers attempt {review.packet_attempt}, not {attempt}",
            )

    gate: GateVerdict | None = None
    if cycle.gate_ref:
        try:
            gate = GateVerdict.from_mapping(_load_json(root, cycle.gate_ref))
        except (TypeError, ValueError) as exc:
            raise _refused("records_undecodable", f"{cycle.gate_ref}: {exc}") from exc

    efficiency, efficiency_ref = (None, "")
    if final is not None:
        efficiency, efficiency_ref = _efficiency_for(
            root, work_order_id, packet.fingerprint(), attempt, final.pointer.fingerprint
        )
        if efficiency is None:
            notes.append("no efficiency record matched this receipt; resource figures are from the receipt alone")
    if cycle.usage_ref == "" and final is not None:
        notes.append("the job names no usage record for the settling receipt")
    if not cycle.authority_ref:
        notes.append("no authority snapshot is named for this attempt")

    try:
        decisions = [
            d
            for d in execution.context_expansion_decisions(work_order_id)
            if d.packet_fingerprint == packet.fingerprint() and d.packet_attempt == attempt
        ]
    except Exception:  # noqa: BLE001 - expansion history is optional evidence
        decisions = []
        notes.append("context expansion history could not be read")

    supplied_files = {ref.key: ref.ref for ref in packet.context_refs if ref.kind.value == "file"}
    for decision in decisions:
        for ref in decision.approved_refs:
            if ref.kind.value == "file":
                supplied_files[ref.key] = ref.ref
    if efficiency is not None:
        files_read = tuple(efficiency.repository_files_read)
    elif receipt is not None:
        files_read = tuple(supplied_files[k] for k in receipt.context_refs_used if k in supplied_files)
    else:
        files_read = ()

    tests_passed = tuple(p for t in (receipt.tests if receipt else ()) if t.passed and (p := _test_path(t.command)))
    tests_failed = tuple(p for t in (receipt.tests if receipt else ()) if not t.passed and (p := _test_path(t.command)))
    reported = set(receipt.test_commands) if receipt is not None else set()
    missing = tuple(t for t in order.required_tests if t not in reported) if receipt is not None else ()

    findings: tuple[FindingNote, ...] = ()
    if review is not None:
        findings = tuple(
            FindingNote(
                finding_id=item.finding_id,
                severity=item.severity.value,
                summary=item.summary,
                deterministic=item.deterministic,
            )
            for item in review.findings
        )

    outcome = ObservedOutcome(
        settled_state=cycle.settle.to_state.value,
        receipt_outcome=receipt.outcome.value if receipt is not None else "",
        recorded_outcome=usage.outcome.value if usage is not None else "",
        evidence_format_rejections=format_rejections,
        files_changed=tuple(receipt.files_changed) if receipt is not None else (),
        files_read=files_read,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        required_tests_missing=missing,
        expansions_approved=tuple(ref.key for d in decisions for ref in d.approved_refs),
        expansions_rejected=tuple(item.requested_ref.key for d in decisions for item in d.rejected_refs),
        review_outcome=review.outcome.value if review is not None else "",
        review_findings=findings,
        unanswered_criteria=len(review.unanswered_criteria) if review is not None else 0,
        gate_readiness=gate.readiness.value if gate is not None else "",
        gate_blockers=len(gate.blockers) if gate is not None else 0,
    )

    features = decision_features(order, attempt=attempt)
    action = chosen_action(packet)

    evidence = [
        _pointer(root, "work_order", engineering.work_order_records(work_order_id)[0][0].record_ref),
        _pointer(root, "packet", cycle.packet_ref),
    ]
    job_ref = _job_snapshot_ref(root, work_order_id, cycle.settle_index + 1)
    if job_ref:
        evidence.append(_pointer(root, "job", job_ref))
    for role, ref in (
        ("authority", cycle.authority_ref),
        ("receipt", cycle.receipt_ref),
        ("usage", cycle.usage_ref),
        ("attestation", cycle.attestation_ref),
        ("review", cycle.review_ref),
        ("gate_verdict", cycle.gate_ref),
        ("efficiency", efficiency_ref),
    ):
        if ref:
            evidence.append(_pointer(root, role, ref))

    provenance = capture_provenance(
        view,
        captured_on=captured_on,
        decision_capsules=features.capsule_ids,
        changed=outcome.files_changed,
        read=outcome.files_read,
        tests=tuple(features.required_tests) + outcome.tests_passed + outcome.tests_failed,
    )
    return ExperienceEpisode(
        work_order_id=work_order_id,
        work_order_fingerprint=order.fingerprint(),
        packet_fingerprint=packet.fingerprint(),
        packet_attempt=attempt,
        receipt_fingerprint=final.pointer.fingerprint if final is not None else "",
        decided_on=cycle.decided_on,
        settled_on=cycle.settle.on,
        features=features,
        action=action,
        outcome=outcome,
        resources=_resources(efficiency, receipt),
        evidence=tuple(evidence),
        provenance=provenance,
        source=source,
        notes=tuple(notes),
    )


# --- a whole state directory ---------------------------------------------------


@dataclass(frozen=True)
class CaptureRecord:
    experience_id: str
    work_order_id: str
    packet_attempt: int
    created: bool
    precedent_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "work_order_id": self.work_order_id,
            "packet_attempt": self.packet_attempt,
            "created": self.created,
            "class": self.precedent_class,
        }


@dataclass(frozen=True)
class CaptureRefusal:
    work_order_id: str
    packet_attempt: int
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "packet_attempt": self.packet_attempt,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CaptureReport:
    captured: tuple[CaptureRecord, ...]
    refused: tuple[CaptureRefusal, ...]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {"captured": len(self.captured), "created": sum(r.created for r in self.captured)}
        for item in self.refused:
            out[f"refused:{item.code}"] = out.get(f"refused:{item.code}", 0) + 1
        return dict(sorted(out.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "captured": [r.to_dict() for r in self.captured],
            "refused": [r.to_dict() for r in self.refused],
        }


def capture_settled(
    state_dir: str | Path,
    view: RepositoryView,
    *,
    captured_on: dt.date,
    store: ExperienceStore | None = None,
    source: str = "local",
    work_order_ids: Sequence[str] | None = None,
) -> CaptureReport:
    """Index every settled attempt in a state directory. Idempotent; never rewrites."""
    root = Path(state_dir).resolve()
    target = store or ExperienceStore(root)
    engineering = EngineeringStore(root)
    captured: list[CaptureRecord] = []
    refused: list[CaptureRefusal] = []
    try:
        ids = tuple(work_order_ids) if work_order_ids is not None else engineering.work_order_ids()
    except Exception as exc:  # noqa: BLE001 - an unreadable history captures nothing
        return CaptureReport((), (CaptureRefusal("", 0, "records_undecodable", str(exc)),))
    for work_order_id in ids:
        try:
            order = engineering.work_order(work_order_id)
        except Exception as exc:  # noqa: BLE001
            refused.append(CaptureRefusal(work_order_id, 0, "work_order_undecodable", str(exc)))
            continue
        if order is None:
            refused.append(CaptureRefusal(work_order_id, 0, "work_order_missing", "no work order is stored"))
            continue
        try:
            job = engineering.job(work_order_id)
        except Exception as exc:  # noqa: BLE001
            refused.append(CaptureRefusal(work_order_id, 0, "records_undecodable", str(exc)))
            continue
        if job is None:
            refused.append(CaptureRefusal(work_order_id, 0, "no_job", "the work order was never opened as a job"))
            continue
        for cycle in attempt_cycles(job):
            try:
                episode = build_episode(
                    root, work_order_id, cycle, view, captured_on=captured_on, source=source, order=order, job=job
                )
                pointer = target.put(episode)
            except CaptureRefused as exc:
                refused.append(CaptureRefusal(work_order_id, cycle.packet_attempt, exc.code, exc.detail))
                continue
            except ExperienceConflict as exc:
                refused.append(CaptureRefusal(work_order_id, cycle.packet_attempt, "conflict", str(exc)))
                continue
            except (ExperienceError, ValueError, TypeError) as exc:
                refused.append(
                    CaptureRefusal(work_order_id, cycle.packet_attempt, "records_undecodable", f"{type(exc).__name__}: {exc}")
                )
                continue
            captured.append(
                CaptureRecord(
                    experience_id=episode.experience_id,
                    work_order_id=work_order_id,
                    packet_attempt=episode.packet_attempt,
                    created=pointer.created,
                    precedent_class=episode.engineering_class().value,
                )
            )
    return CaptureReport(tuple(captured), tuple(refused))


# --- governance, joined at read time -------------------------------------------


@dataclass(frozen=True)
class GovernanceFacts:
    """What happened to a work order after its attempt settled, as of one day.

    Read from the canonical engineering store every time, never stored in an
    episode: the CEO's decision is written once in `engineering/decisions/`
    and this is a view of it.
    """

    available: bool
    verdicts: tuple[tuple[str, dt.date, str], ...] = ()
    later_states: tuple[tuple[str, dt.date], ...] = ()
    problem: str = ""


def governance_facts(
    state_dir: str | Path, episode: ExperienceEpisode, *, before: dt.date | None = None
) -> GovernanceFacts:
    """CEO verdicts and post-settlement job moves, strictly before `before` if given."""
    root = Path(state_dir)
    engineering = EngineeringStore(root)
    try:
        decisions = engineering.decisions(episode.work_order_id)
        job = engineering.job(episode.work_order_id)
    except Exception as exc:  # noqa: BLE001
        return GovernanceFacts(available=False, problem=f"{type(exc).__name__}: {exc}")

    def visible(day: dt.date) -> bool:
        return before is None or day < before

    verdicts = tuple(
        (d.verdict.value, d.decided_on, d.rationale)
        for d in decisions
        if d.work_order_fingerprint == episode.work_order_fingerprint and visible(d.decided_on)
    )
    later: list[tuple[str, dt.date]] = []
    if job is not None:
        cycles = [c for c in attempt_cycles(job) if c.packet_attempt == episode.packet_attempt and c.settled]
        if cycles and cycles[0].settle_index is not None:
            for move in job.transitions[cycles[0].settle_index + 1 :]:
                if move.to_state is JobState.DEVELOPING:
                    break
                if visible(move.on):
                    later.append((move.to_state.value, move.on))
    return GovernanceFacts(available=True, verdicts=verdicts, later_states=tuple(later))


_NEGATIVE_VERDICTS = frozenset({"reject", "request_changes"})
_UNDOING_STATES = frozenset({"blocked", "planning", "failed", "decision_required"})


def governed_class(episode: ExperienceEpisode, facts: GovernanceFacts) -> tuple[PrecedentClass, tuple[str, ...]]:
    """The episode's class once governance has spoken. Only ever downgrades.

    An accepted attempt the CEO rejected, or asked to change, is a correction:
    the engineering stages thought it was done and the company did not. A job
    that left readiness for anything but `closed` is the same. Nothing here
    promotes a correction or an incomplete episode - a CEO approving a job
    that engineering never finished does not make it a precedent.
    """
    base = episode.engineering_class()
    if base is not PrecedentClass.ACCEPTED:
        return base, ()
    reasons: list[str] = []
    for verdict, day, rationale in facts.verdicts:
        if verdict in _NEGATIVE_VERDICTS:
            reasons.append(f"CEO decision {verdict} on {day.isoformat()}: {' '.join(rationale.split())[:160]}")
    for state, day in facts.later_states:
        if state in _UNDOING_STATES:
            reasons.append(f"job moved to {state} on {day.isoformat()} after the attempt settled")
    if reasons:
        return PrecedentClass.CORRECTION, tuple(reasons)
    return PrecedentClass.ACCEPTED, ()


__all__ = [
    "REFUSAL_CODES",
    "SETTLING_STATES",
    "AttemptCycle",
    "CaptureRecord",
    "CaptureRefusal",
    "CaptureReport",
    "GovernanceFacts",
    "attempt_cycles",
    "build_episode",
    "capture_settled",
    "governance_facts",
    "governed_class",
    "verify_pointers",
]
