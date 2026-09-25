"""One experience episode: an immutable index over canonical engineering records.

## What an episode is

One **developer attempt** at one engineering work order: the packet Company OS
issued, what came back, how review and the gate judged it, and what it cost.
That is the unit at which the company made a decision (which context, which
reasoning class, which employee) and then observed an outcome, so it is the
unit a precedent can be about and the unit a later decision model could learn
from. A work order corrected once is two episodes; a work order accepted on
its first attempt is one.

## What an episode is not

It is not a second copy of the execution history. The work order, packet,
authority snapshot, receipt, usage record, review, attestation, gate verdict
and efficiency record all stay where they are, written once by the stage that
produced them (constitution rule 15). An episode carries `RecordPointer`s to
them - each with a digest of the file's bytes, so a pointer that no longer
resolves to the same file is detected rather than trusted - plus four small
projections. Every copied field has to earn its place, and the reason is the
same for all four sections: **retrieval must not depend on re-decoding
historical records under today's schema.** That is not hypothetical. Two of
the work orders in this repository's own history no longer decode under the
current `EngineeringWorkOrder` (a pre-profile `max_developer_attempts: 3`
against the consumer profile's ceiling of 1); a store that could only answer
by re-reading them would lose that history the day the schema moved.

| section | copied because |
|---|---|
| `features` | a frozen decision-time snapshot; recomputable from the work order while it still decodes (`verify_features` does exactly that), and the only thing a retrieval scan or a training row may read as input |
| `action` | what the company chose before the session ran; a packet may be re-planned but the one that went out is this one |
| `outcome` | the settled engineering verdicts, joined from five records into one comparable shape |
| `resources` | the measured cost, with its basis; `None` stays `None` |
| `provenance` | the scoped repository/contract state at capture. **Not recomputable later at all** - it describes a repository that has since moved on, which is the whole reason it is stored |

The CEO's decision is deliberately *not* copied. It arrives after an episode
settles, it is canonical in `engineering/decisions/`, and it is joined at read
time (`GovernanceFacts`). Copying it would force either a mutable episode or a
second record per attempt.

## Decision time and outcome, kept structurally apart

`DecisionFeatures` is built by `decision_features(order, attempt=...)`, a
function that is handed the work order and an integer and nothing else. It
cannot read a receipt, a review or a usage record because none is in scope.
The field sets of `DecisionFeatures` and of the two outcome sections are
asserted disjoint when this module is imported, and `assert_decision_time_only`
checks a mapping mechanically before anything treats it as model input.

Derived similarity signals - which capsule currently owns a path, which
modules import it - are *not* features. They are computed at query time from
the current repository for both the query and the precedent, symmetrically.
Computing them at capture time would leak the outcome: a task whose change
created a capsule would carry that capsule in its "decision-time" features.

## Observed, estimated, counterfactual

`ObservedOutcome` has no basis field because it cannot hold anything but
observations: every value in it was recorded by a deterministic stage or read
from a validated receipt. `ResourceObservation` carries an `EvidenceBasis` per
measurement, refuses `COUNTERFACTUAL` outright - history holds what happened -
and refuses `OBSERVED` without a value and `UNAVAILABLE` with one, so neither
a guess nor a gap can be written down as a measurement. Counterfactual values
exist only in analysis outputs (`Measurement`), where they are labelled.

## Identity

`experience_id` is a fingerprint over the canonical identity of the attempt -
work order id and fingerprint, packet fingerprint, packet attempt, and the
fingerprint of the receipt that settled it - and nothing else. So the same
attempt captured twice, from any machine on any day, gets the same id; two
attempts never share one; and a body that differs under an existing id is a
changed canonical record, which the store refuses (`ExperienceConflict`).

`content_fingerprint()` covers everything except `provenance` and `source`,
which describe *when and where* the attempt was indexed rather than *what
happened*. Re-capturing a settled attempt a week later yields identical content
and newer provenance; the store keeps the first capture and answers
idempotently rather than calling that a conflict.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any

from ai_platform.references import assert_reference
from ai_platform.serde import as_date, to_jsonable
from ai_platform.serde import fingerprint as _fingerprint

from .errors import ExperienceError


EPISODE_SCHEMA_VERSION = 1
FEATURE_SCHEMA_VERSION = 1
ACTION_SCHEMA_VERSION = 1
OUTCOME_SCHEMA_VERSION = 1

# Bounds on what one episode may carry. An episode is an index entry; a field
# that needs more than this is a record, and belongs where records live.
MAX_PATHS = 64
MAX_FINDINGS = 12
MAX_FINDING_CHARS = 200
MAX_NOTES = 8

_HEX16 = frozenset("0123456789abcdef")

# The canonical stores a pointer may name, by the first segment of its ref.
CANONICAL_STORES: frozenset[str] = frozenset({"engineering", "execution", "resource_usage"})

POINTER_ROLES: frozenset[str] = frozenset(
    {
        "work_order",
        "job",
        "packet",
        "authority",
        "receipt",
        "usage",
        "review",
        "attestation",
        "gate_verdict",
        "efficiency",
    }
)


class EvidenceBasis(str, Enum):
    """What kind of evidence a value is. The one vocabulary for all four kinds.

    `OBSERVED` - recorded by a deterministic component, or reported by a
    provider and carried through a validated receipt. `ESTIMATED` - computed by
    a stated method, never measured. `COUNTERFACTUAL` - a statement about what
    would have happened; never history. `UNAVAILABLE` - nobody measured it.

    Maps onto `company.efficiency.telemetry.MeasurementSource` for the values
    that module already records: provider_reported -> OBSERVED, estimated ->
    ESTIMATED, unavailable -> UNAVAILABLE. It adds COUNTERFACTUAL because that
    is the one kind a precedent system is tempted to invent.
    """

    OBSERVED = "observed"
    ESTIMATED = "estimated"
    COUNTERFACTUAL = "counterfactual"
    UNAVAILABLE = "unavailable"


class PrecedentClass(str, Enum):
    """How an episode may be used. Three classes, never ranked against each other.

    `ACCEPTED` is reusable precedent. `CORRECTION` is a similar attempt that was
    sent back - retrievable as "avoid this", never scored as success.
    `INCOMPLETE` settled without a complete observed outcome and is history
    only: it is stored, counted and never offered as precedent of either kind.
    """

    ACCEPTED = "accepted"
    CORRECTION = "correction"
    INCOMPLETE = "incomplete"


# --- small validated values ------------------------------------------------


def _hex16(value: Any, name: str, *, allow_empty: bool = False) -> str:
    text = str(value or "")
    if not text and allow_empty:
        return ""
    if len(text) != 16 or any(char not in _HEX16 for char in text):
        raise ExperienceError(f"{name} must be a 16-character lowercase hex digest")
    return text


def _paths(values: Any, name: str, *, limit: int = MAX_PATHS) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ExperienceError(f"{name} must be a list of references")
    out = tuple(str(item).strip().replace("\\", "/") for item in values)
    if any(not item for item in out):
        raise ExperienceError(f"{name} holds an empty reference")
    for item in out:
        assert_reference(item, name)
    if len(out) > limit:
        raise ExperienceError(f"{name}: {len(out)} entries exceeds the {limit} allowed")
    return tuple(sorted(set(out)))


def _text(value: Any, name: str, *, limit: int = 240) -> str:
    if not isinstance(value, str):
        raise ExperienceError(f"{name} must be a string")
    text = " ".join(value.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExperienceError(f"{name} must be a non-negative integer")
    return value


def _optional_count(value: Any, name: str) -> int | None:
    return None if value is None else _count(value, name)


def _basis(value: Any, name: str) -> EvidenceBasis:
    try:
        return value if isinstance(value, EvidenceBasis) else EvidenceBasis(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in EvidenceBasis)
        raise ExperienceError(f"{name} must be one of: {allowed}") from exc


def _strict(data: Any, cls: type, name: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ExperienceError(f"{name} must be a mapping")
    unknown = sorted(set(data) - {f.name for f in fields(cls)})
    if unknown:
        raise ExperienceError(
            f"{name} has unknown field(s): {', '.join(unknown)}. Experience records "
            "are read against a fixed schema so an extra key cannot change what "
            "was claimed."
        )
    return data


# --- pointers ----------------------------------------------------------------


@dataclass(frozen=True)
class RecordPointer:
    """Where one canonical record lives, and the digest of its bytes then.

    `digest` is the first sixteen hex characters of the SHA-256 of the stored
    file, not the record's semantic `fingerprint()`. Canonical records are
    written once with `O_EXCL`, so their bytes do not move; a byte digest is
    what proves the file behind the pointer is the one that was indexed,
    whatever record type it happens to be.
    """

    role: str
    record_ref: str
    digest: str

    def __post_init__(self) -> None:
        if self.role not in POINTER_ROLES:
            raise ExperienceError(f"pointer role {self.role!r} is not one of {sorted(POINTER_ROLES)}")
        ref = assert_reference(str(self.record_ref).replace("\\", "/"), "pointer.record_ref")
        if ref.startswith("/") or ".." in ref.split("/"):
            raise ExperienceError(f"pointer {ref!r} must be relative to its state directory")
        if ref.split("/", 1)[0] not in CANONICAL_STORES:
            raise ExperienceError(
                f"pointer {ref!r} does not name a canonical store "
                f"({', '.join(sorted(CANONICAL_STORES))})"
            )
        object.__setattr__(self, "record_ref", ref)
        object.__setattr__(self, "digest", _hex16(self.digest, "pointer.digest"))

    @classmethod
    def from_mapping(cls, data: Any) -> "RecordPointer":
        raw = _strict(data, cls, "pointer")
        return cls(
            role=str(raw.get("role", "")),
            record_ref=str(raw.get("record_ref", "")),
            digest=str(raw.get("digest", "")),
        )


# --- decision time -------------------------------------------------------------


@dataclass(frozen=True)
class DecisionFeatures:
    """What was known when the attempt was decided, and nothing learned after.

    Every field is a projection of the authorized work order - immutable,
    fingerprinted, written before any session ran - plus the attempt number,
    which is decision-time by definition: the company knows it is issuing a
    second attempt before it issues it.
    """

    attempt: int
    write_paths: tuple[str, ...]
    read_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    forbidden_read_paths: tuple[str, ...]
    required_tests: tuple[str, ...]
    capabilities: tuple[str, ...]
    review_capability: str
    capsule_ids: tuple[str, ...]
    risk: str
    reasoning_class_ceiling: str
    specialist_domain: str
    novel: bool
    escalation: str
    resource_profile: str
    max_developer_attempts: int
    acceptance_criteria_count: int
    schema: int = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ExperienceError("features.attempt must be a positive integer")
        for name in (
            "write_paths",
            "read_paths",
            "forbidden_paths",
            "forbidden_read_paths",
            "required_tests",
            "capabilities",
            "capsule_ids",
        ):
            object.__setattr__(self, name, _paths(getattr(self, name), f"features.{name}"))
        for name in ("review_capability", "risk", "reasoning_class_ceiling", "specialist_domain", "escalation", "resource_profile"):
            object.__setattr__(self, name, _text(getattr(self, name), f"features.{name}", limit=80))
        if not isinstance(self.novel, bool):
            raise ExperienceError("features.novel must be a boolean")
        _count(self.max_developer_attempts, "features.max_developer_attempts")
        _count(self.acceptance_criteria_count, "features.acceptance_criteria_count")
        if self.schema != FEATURE_SCHEMA_VERSION:
            raise ExperienceError(f"features.schema must be {FEATURE_SCHEMA_VERSION}")

    @classmethod
    def from_mapping(cls, data: Any) -> "DecisionFeatures":
        raw = _strict(data, cls, "features")
        return cls(
            attempt=raw.get("attempt", 0),
            write_paths=raw.get("write_paths", ()),
            read_paths=raw.get("read_paths", ()),
            forbidden_paths=raw.get("forbidden_paths", ()),
            forbidden_read_paths=raw.get("forbidden_read_paths", ()),
            required_tests=raw.get("required_tests", ()),
            capabilities=raw.get("capabilities", ()),
            review_capability=str(raw.get("review_capability", "")),
            capsule_ids=raw.get("capsule_ids", ()),
            risk=str(raw.get("risk", "")),
            reasoning_class_ceiling=str(raw.get("reasoning_class_ceiling", "")),
            specialist_domain=str(raw.get("specialist_domain", "")),
            novel=raw.get("novel", False),
            escalation=str(raw.get("escalation", "")),
            resource_profile=str(raw.get("resource_profile", "")),
            max_developer_attempts=raw.get("max_developer_attempts", 0),
            acceptance_criteria_count=raw.get("acceptance_criteria_count", 0),
            schema=raw.get("schema", FEATURE_SCHEMA_VERSION),
        )


CAPSULE_REF_PREFIX = "capsule:"


def decision_features(order: Any, *, attempt: int) -> DecisionFeatures:
    """The decision-time projection of one authorized work order.

    The signature is the leakage guard. This function is handed the work order
    and an attempt number; it has no parameter through which a receipt, a
    review, a gate verdict or a usage record could arrive, so no feature can be
    derived from one. `tests/test_company_experience_store.py` asserts the
    signature, and that the body names no outcome record.
    """
    capsules = tuple(
        ref.ref[len(CAPSULE_REF_PREFIX):]
        for ref in order.context_refs
        if ref.kind.value == "module_contract" and ref.ref.startswith(CAPSULE_REF_PREFIX)
    )
    return DecisionFeatures(
        attempt=attempt,
        write_paths=tuple(order.authorized_paths),
        read_paths=tuple(order.authorized_read_paths),
        forbidden_paths=tuple(order.forbidden_paths),
        forbidden_read_paths=tuple(order.forbidden_read_paths),
        required_tests=tuple(order.required_tests),
        capabilities=tuple(order.implementation_capabilities),
        review_capability=order.review_capability,
        capsule_ids=capsules,
        risk=order.risk.value,
        reasoning_class_ceiling=order.reasoning_class_ceiling.value,
        specialist_domain=order.specialist_domain,
        novel=order.novel,
        escalation=order.escalation,
        resource_profile=order.resource_profile,
        max_developer_attempts=order.max_developer_attempts,
        acceptance_criteria_count=len(order.acceptance_criteria),
    )


@dataclass(frozen=True)
class ChosenAction:
    """What the company chose for this attempt, before the session ran.

    Routing and context, read from the packet that was actually issued. An
    action is not a feature: a model that recommends an action may read only
    features, and a model that predicts an outcome may read both. Keeping them
    in separate sections is what lets either be built without the other.
    """

    employee: str
    reasoning_class: str
    resource_class: str
    executor: str
    context_capsules: tuple[str, ...]
    context_files: tuple[str, ...]
    context_tests: tuple[str, ...]
    context_fingerprint: str
    schema: int = ACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("employee", "reasoning_class", "resource_class", "executor"):
            object.__setattr__(self, name, _text(getattr(self, name), f"action.{name}", limit=80))
        for name in ("context_capsules", "context_files", "context_tests"):
            object.__setattr__(self, name, _paths(getattr(self, name), f"action.{name}"))
        object.__setattr__(
            self, "context_fingerprint", _hex16(self.context_fingerprint, "action.context_fingerprint", allow_empty=True)
        )
        if self.schema != ACTION_SCHEMA_VERSION:
            raise ExperienceError(f"action.schema must be {ACTION_SCHEMA_VERSION}")

    @classmethod
    def from_mapping(cls, data: Any) -> "ChosenAction":
        raw = _strict(data, cls, "action")
        return cls(
            employee=str(raw.get("employee", "")),
            reasoning_class=str(raw.get("reasoning_class", "")),
            resource_class=str(raw.get("resource_class", "")),
            executor=str(raw.get("executor", "")),
            context_capsules=raw.get("context_capsules", ()),
            context_files=raw.get("context_files", ()),
            context_tests=raw.get("context_tests", ()),
            context_fingerprint=str(raw.get("context_fingerprint", "")),
            schema=raw.get("schema", ACTION_SCHEMA_VERSION),
        )


def chosen_action(packet: Any) -> ChosenAction:
    """The action projection of one issued `SessionPacket`."""
    capsules, files, tests = [], [], []
    for ref in packet.context_refs:
        kind = ref.kind.value
        if kind == "module_contract" and ref.ref.startswith(CAPSULE_REF_PREFIX):
            capsules.append(ref.ref[len(CAPSULE_REF_PREFIX):])
        elif kind == "file":
            files.append(ref.ref)
        elif kind == "test":
            tests.append(ref.ref)
    return ChosenAction(
        employee=packet.employee,
        reasoning_class=packet.reasoning_class.value,
        resource_class=str(packet.resource_class),
        executor=packet.executor.value,
        context_capsules=tuple(capsules),
        context_files=tuple(files),
        context_tests=tuple(tests),
        context_fingerprint=packet.context_fingerprint,
    )


# --- outcome -------------------------------------------------------------------


@dataclass(frozen=True)
class FindingNote:
    """One review finding, cut to a line: enough to warn, not enough to replay."""

    finding_id: str
    severity: str
    summary: str
    deterministic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _text(self.finding_id, "finding.finding_id", limit=64))
        object.__setattr__(self, "severity", _text(self.severity, "finding.severity", limit=32))
        object.__setattr__(self, "summary", _text(self.summary, "finding.summary", limit=MAX_FINDING_CHARS))
        if not isinstance(self.deterministic, bool):
            raise ExperienceError("finding.deterministic must be a boolean")

    @classmethod
    def from_mapping(cls, data: Any) -> "FindingNote":
        raw = _strict(data, cls, "finding")
        return cls(
            finding_id=str(raw.get("finding_id", "")),
            severity=str(raw.get("severity", "")),
            summary=str(raw.get("summary", "")),
            deterministic=raw.get("deterministic", False),
        )


@dataclass(frozen=True)
class ObservedOutcome:
    """What happened to the attempt, as the deterministic stages recorded it.

    Empty strings mean "that stage never produced a record for this attempt",
    which is itself an observation - an attempt with no review is not an
    attempt whose review passed. `receipt_outcome` is the session's testimony;
    `recorded_outcome` is the outcome the runtime recorded after validating it,
    and it is the one that counts.
    """

    settled_state: str
    receipt_outcome: str
    recorded_outcome: str
    evidence_format_rejections: int
    files_changed: tuple[str, ...]
    files_read: tuple[str, ...]
    tests_passed: tuple[str, ...]
    tests_failed: tuple[str, ...]
    required_tests_missing: tuple[str, ...]
    expansions_approved: tuple[str, ...]
    expansions_rejected: tuple[str, ...]
    review_outcome: str
    review_findings: tuple[FindingNote, ...]
    unanswered_criteria: int
    gate_readiness: str
    gate_blockers: int
    schema: int = OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("settled_state", "receipt_outcome", "recorded_outcome", "review_outcome", "gate_readiness"):
            object.__setattr__(self, name, _text(getattr(self, name), f"outcome.{name}", limit=40))
        if not self.settled_state:
            raise ExperienceError("outcome.settled_state is required: an episode is a settled attempt")
        for name in (
            "files_changed",
            "files_read",
            "tests_passed",
            "tests_failed",
            "required_tests_missing",
            "expansions_approved",
            "expansions_rejected",
        ):
            object.__setattr__(self, name, _paths(getattr(self, name), f"outcome.{name}"))
        if not isinstance(self.review_findings, tuple) or any(
            not isinstance(item, FindingNote) for item in self.review_findings
        ):
            raise ExperienceError("outcome.review_findings must hold FindingNote values")
        if len(self.review_findings) > MAX_FINDINGS:
            object.__setattr__(self, "review_findings", self.review_findings[:MAX_FINDINGS])
        for name in ("evidence_format_rejections", "unanswered_criteria", "gate_blockers"):
            _count(getattr(self, name), f"outcome.{name}")
        if self.schema != OUTCOME_SCHEMA_VERSION:
            raise ExperienceError(f"outcome.schema must be {OUTCOME_SCHEMA_VERSION}")

    @classmethod
    def from_mapping(cls, data: Any) -> "ObservedOutcome":
        raw = _strict(data, cls, "outcome")
        findings = raw.get("review_findings", ())
        if isinstance(findings, (str, bytes)) or not isinstance(findings, (list, tuple)):
            raise ExperienceError("outcome.review_findings must be a list")
        return cls(
            settled_state=str(raw.get("settled_state", "")),
            receipt_outcome=str(raw.get("receipt_outcome", "")),
            recorded_outcome=str(raw.get("recorded_outcome", "")),
            evidence_format_rejections=raw.get("evidence_format_rejections", 0),
            files_changed=raw.get("files_changed", ()),
            files_read=raw.get("files_read", ()),
            tests_passed=raw.get("tests_passed", ()),
            tests_failed=raw.get("tests_failed", ()),
            required_tests_missing=raw.get("required_tests_missing", ()),
            expansions_approved=raw.get("expansions_approved", ()),
            expansions_rejected=raw.get("expansions_rejected", ()),
            review_outcome=str(raw.get("review_outcome", "")),
            review_findings=tuple(FindingNote.from_mapping(item) for item in findings),
            unanswered_criteria=raw.get("unanswered_criteria", 0),
            gate_readiness=str(raw.get("gate_readiness", "")),
            gate_blockers=raw.get("gate_blockers", 0),
            schema=raw.get("schema", OUTCOME_SCHEMA_VERSION),
        )


def _check_measurement(value: Any, basis: EvidenceBasis, name: str) -> None:
    """The two rules a measurement cannot break, and the one kind history refuses."""
    if basis is EvidenceBasis.COUNTERFACTUAL:
        raise ExperienceError(
            f"{name}: a counterfactual value cannot be recorded as history. An episode "
            "holds what happened; what would have happened belongs in an analysis "
            "output that says so."
        )
    if basis is EvidenceBasis.UNAVAILABLE and value is not None:
        raise ExperienceError(f"{name}: an unavailable measurement cannot carry a value")
    if basis in (EvidenceBasis.OBSERVED, EvidenceBasis.ESTIMATED) and value is None:
        raise ExperienceError(
            f"{name}: {basis.value} requires a value; a missing value is unavailable, "
            "never zero"
        )


@dataclass(frozen=True)
class ResourceObservation:
    """What the attempt cost, with the basis of every number.

    Read from the canonical `EfficiencyRecord` for the attempt (an exact join on
    packet fingerprint, attempt and receipt fingerprint) and from the receipt's
    own usage block. `unreliable_metrics` is carried verbatim from the receipt:
    a provider figure the runner already knew to be wrong stays labelled wrong.
    """

    tokens_total: int | None
    tokens_input: int | None
    tokens_output: int | None
    tokens_basis: EvidenceBasis
    estimated_tokens_total: int | None
    cost_amount: str | None
    cost_currency: str
    cost_basis: EvidenceBasis
    duration_s: float | None
    duration_basis: EvidenceBasis
    tool_calls: int | None
    provider: str | None
    model: str | None
    unreliable_metrics: tuple[str, ...] = ()
    schema: int = OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("tokens_basis", "cost_basis", "duration_basis"):
            object.__setattr__(self, name, _basis(getattr(self, name), f"resources.{name}"))
        for name in ("tokens_total", "tokens_input", "tokens_output", "estimated_tokens_total", "tool_calls"):
            _optional_count(getattr(self, name), f"resources.{name}")
        if self.tokens_basis is not EvidenceBasis.UNAVAILABLE and all(
            value is None for value in (self.tokens_total, self.tokens_input, self.tokens_output)
        ):
            raise ExperienceError("resources: a token basis other than unavailable needs a count")
        if self.tokens_basis is EvidenceBasis.UNAVAILABLE and any(
            value is not None for value in (self.tokens_total, self.tokens_input, self.tokens_output)
        ):
            raise ExperienceError("resources: unavailable tokens cannot carry counts")
        if self.tokens_basis is EvidenceBasis.COUNTERFACTUAL:
            _check_measurement(self.tokens_total, self.tokens_basis, "resources.tokens")
        _check_measurement(self.cost_amount, self.cost_basis, "resources.cost")
        if self.duration_s is not None:
            if isinstance(self.duration_s, bool) or not isinstance(self.duration_s, (int, float)) or self.duration_s < 0:
                raise ExperienceError("resources.duration_s must be a non-negative number")
        _check_measurement(self.duration_s, self.duration_basis, "resources.duration")
        if not isinstance(self.cost_currency, str):
            raise ExperienceError("resources.cost_currency must be a string")
        for name in ("provider", "model"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ExperienceError(f"resources.{name} is a non-empty string or None, never ''")
        object.__setattr__(
            self,
            "unreliable_metrics",
            tuple(sorted({_text(item, "resources.unreliable_metrics", limit=64) for item in self.unreliable_metrics})),
        )
        if self.schema != OUTCOME_SCHEMA_VERSION:
            raise ExperienceError(f"resources.schema must be {OUTCOME_SCHEMA_VERSION}")

    @classmethod
    def unavailable(cls) -> "ResourceObservation":
        """No telemetry was recorded. Every value None, every basis unavailable."""
        return cls(
            tokens_total=None,
            tokens_input=None,
            tokens_output=None,
            tokens_basis=EvidenceBasis.UNAVAILABLE,
            estimated_tokens_total=None,
            cost_amount=None,
            cost_currency="",
            cost_basis=EvidenceBasis.UNAVAILABLE,
            duration_s=None,
            duration_basis=EvidenceBasis.UNAVAILABLE,
            tool_calls=None,
            provider=None,
            model=None,
        )

    @classmethod
    def from_mapping(cls, data: Any) -> "ResourceObservation":
        raw = _strict(data, cls, "resources")
        metrics = raw.get("unreliable_metrics", ())
        if isinstance(metrics, (str, bytes)) or not isinstance(metrics, (list, tuple)):
            raise ExperienceError("resources.unreliable_metrics must be a list")
        return cls(
            tokens_total=raw.get("tokens_total"),
            tokens_input=raw.get("tokens_input"),
            tokens_output=raw.get("tokens_output"),
            tokens_basis=raw.get("tokens_basis", EvidenceBasis.UNAVAILABLE.value),
            estimated_tokens_total=raw.get("estimated_tokens_total"),
            cost_amount=raw.get("cost_amount"),
            cost_currency=str(raw.get("cost_currency", "")),
            cost_basis=raw.get("cost_basis", EvidenceBasis.UNAVAILABLE.value),
            duration_s=raw.get("duration_s"),
            duration_basis=raw.get("duration_basis", EvidenceBasis.UNAVAILABLE.value),
            tool_calls=raw.get("tool_calls"),
            provider=raw.get("provider"),
            model=raw.get("model"),
            unreliable_metrics=tuple(str(item) for item in metrics),
            schema=raw.get("schema", OUTCOME_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class Measurement:
    """One value with its basis, for analysis outputs rather than for history.

    The only place `COUNTERFACTUAL` may appear. A replay's "this is what the
    advisory would have suggested" is a Measurement with that basis, so no
    reader can mistake it for something a session actually received.
    """

    value: Any
    basis: EvidenceBasis
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "basis", _basis(self.basis, "measurement.basis"))
        if self.basis is EvidenceBasis.UNAVAILABLE and self.value is not None:
            raise ExperienceError("an unavailable measurement cannot carry a value")
        if self.basis is not EvidenceBasis.UNAVAILABLE and self.value is None:
            raise ExperienceError(f"a {self.basis.value} measurement needs a value")

    def to_dict(self) -> dict[str, Any]:
        return {"value": to_jsonable(self.value), "basis": self.basis.value, "note": self.note}


# --- provenance ----------------------------------------------------------------


@dataclass(frozen=True)
class CapsuleAnchor:
    """A capsule the episode's scope depended on, and its contract at capture."""

    capsule_id: str
    contract_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capsule_id", assert_reference(self.capsule_id, "anchor.capsule_id"))
        object.__setattr__(self, "contract_digest", _hex16(self.contract_digest, "anchor.contract_digest"))

    @classmethod
    def from_mapping(cls, data: Any) -> "CapsuleAnchor":
        raw = _strict(data, cls, "capsule anchor")
        return cls(capsule_id=str(raw.get("capsule_id", "")), contract_digest=str(raw.get("contract_digest", "")))


PATH_ROLES: frozenset[str] = frozenset({"changed", "read", "test"})


@dataclass(frozen=True)
class PathAnchor:
    """One path in the episode's scope, the capsules governing it, and its shape.

    `digest` is a structural digest for a file the attempt read without
    changing, and empty for the other two roles - see
    `repository.RepositoryView.structural_digest` for why a changed file and a
    test are anchored by existence and ownership rather than by content.
    """

    path: str
    role: str
    governed_by: tuple[str, ...]
    digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", assert_reference(str(self.path).replace("\\", "/"), "anchor.path"))
        if self.role not in PATH_ROLES:
            raise ExperienceError(f"anchor.role must be one of {sorted(PATH_ROLES)}")
        object.__setattr__(self, "governed_by", _paths(self.governed_by, "anchor.governed_by", limit=16))
        object.__setattr__(self, "digest", _hex16(self.digest, "anchor.digest", allow_empty=True))

    @classmethod
    def from_mapping(cls, data: Any) -> "PathAnchor":
        raw = _strict(data, cls, "path anchor")
        return cls(
            path=str(raw.get("path", "")),
            role=str(raw.get("role", "")),
            governed_by=raw.get("governed_by", ()),
            digest=str(raw.get("digest", "")),
        )


@dataclass(frozen=True)
class ScopeProvenance:
    """The scoped repository and contract state the episode was captured against.

    Scoped on purpose. A whole-repository commit would make every episode stale
    the moment any unrelated file - a video render, a race course - changed,
    which would make history useless exactly as fast as the repository is
    busy. `repository_commit` is recorded as information and used for nothing.
    """

    captured_on: dt.date
    repository_commit: str
    capsules: tuple[CapsuleAnchor, ...]
    paths: tuple[PathAnchor, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_on", as_date(self.captured_on, "provenance.captured_on"))
        commit = str(self.repository_commit or "")
        if commit and (len(commit) != 40 or any(char not in _HEX16 for char in commit)):
            raise ExperienceError("provenance.repository_commit must be a 40-character sha or empty")
        object.__setattr__(self, "repository_commit", commit)
        if not isinstance(self.capsules, tuple) or any(not isinstance(i, CapsuleAnchor) for i in self.capsules):
            raise ExperienceError("provenance.capsules must hold CapsuleAnchor values")
        if not isinstance(self.paths, tuple) or any(not isinstance(i, PathAnchor) for i in self.paths):
            raise ExperienceError("provenance.paths must hold PathAnchor values")
        object.__setattr__(
            self, "capsules", tuple(sorted({a.capsule_id: a for a in self.capsules}.values(), key=lambda a: a.capsule_id))
        )
        object.__setattr__(
            self, "paths", tuple(sorted({(a.path, a.role): a for a in self.paths}.values(), key=lambda a: (a.path, a.role)))
        )
        if len(self.paths) > MAX_PATHS * 2:
            raise ExperienceError("provenance.paths exceeds its bound")

    @classmethod
    def from_mapping(cls, data: Any) -> "ScopeProvenance":
        raw = _strict(data, cls, "provenance")
        return cls(
            captured_on=as_date(raw.get("captured_on"), "provenance.captured_on"),
            repository_commit=str(raw.get("repository_commit", "")),
            capsules=tuple(CapsuleAnchor.from_mapping(item) for item in raw.get("capsules", ()) or ()),
            paths=tuple(PathAnchor.from_mapping(item) for item in raw.get("paths", ()) or ()),
        )


# --- the episode ---------------------------------------------------------------


# Where a precedent is finished, as the engineering stages see it. Anything
# else settles the attempt without making it a success.
_ACCEPTED_SETTLED_STATES = frozenset({"ready_for_approval", "closed"})
_NEGATIVE_REVIEWS = frozenset({"changes_required", "blocked"})
_NEGATIVE_GATES = frozenset({"blocked", "insufficient_evidence"})


@dataclass(frozen=True)
class ExperienceEpisode:
    """One settled developer attempt, indexed. Immutable once built."""

    work_order_id: str
    work_order_fingerprint: str
    packet_fingerprint: str
    packet_attempt: int
    receipt_fingerprint: str
    decided_on: dt.date
    settled_on: dt.date
    features: DecisionFeatures
    action: ChosenAction
    outcome: ObservedOutcome
    resources: ResourceObservation
    evidence: tuple[RecordPointer, ...]
    provenance: ScopeProvenance
    source: str = "local"
    notes: tuple[str, ...] = ()
    schema: int = EPISODE_SCHEMA_VERSION
    experience_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_order_id", assert_reference(self.work_order_id, "episode.work_order_id"))
        object.__setattr__(self, "work_order_fingerprint", _hex16(self.work_order_fingerprint, "episode.work_order_fingerprint"))
        object.__setattr__(self, "packet_fingerprint", _hex16(self.packet_fingerprint, "episode.packet_fingerprint"))
        object.__setattr__(
            self, "receipt_fingerprint", _hex16(self.receipt_fingerprint, "episode.receipt_fingerprint", allow_empty=True)
        )
        if isinstance(self.packet_attempt, bool) or not isinstance(self.packet_attempt, int) or self.packet_attempt < 1:
            raise ExperienceError("episode.packet_attempt must be a positive integer")
        object.__setattr__(self, "decided_on", as_date(self.decided_on, "episode.decided_on"))
        object.__setattr__(self, "settled_on", as_date(self.settled_on, "episode.settled_on"))
        if self.settled_on < self.decided_on:
            raise ExperienceError(
                f"episode {self.work_order_id}#{self.packet_attempt} settled on "
                f"{self.settled_on} before it was decided on {self.decided_on}"
            )
        for name, kind in (
            ("features", DecisionFeatures),
            ("action", ChosenAction),
            ("outcome", ObservedOutcome),
            ("resources", ResourceObservation),
            ("provenance", ScopeProvenance),
        ):
            if not isinstance(getattr(self, name), kind):
                raise ExperienceError(f"episode.{name} must be a {kind.__name__}")
        if self.features.attempt != self.packet_attempt:
            raise ExperienceError("episode.features.attempt must equal episode.packet_attempt")
        if not isinstance(self.evidence, tuple) or any(not isinstance(p, RecordPointer) for p in self.evidence):
            raise ExperienceError("episode.evidence must hold RecordPointer values")
        refs = [p.record_ref for p in self.evidence]
        if len(refs) != len(set(refs)):
            raise ExperienceError("episode.evidence repeats a pointer")
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence, key=lambda p: (p.role, p.record_ref))))
        if not any(p.role == "work_order" for p in self.evidence) or not any(p.role == "packet" for p in self.evidence):
            raise ExperienceError("an episode must point at its work order and its packet")
        object.__setattr__(self, "source", assert_reference(self.source, "episode.source"))
        notes = tuple(_text(note, "episode.notes", limit=240) for note in self.notes)
        if len(notes) > MAX_NOTES:
            raise ExperienceError(f"episode.notes exceeds {MAX_NOTES}")
        object.__setattr__(self, "notes", notes)
        if self.schema != EPISODE_SCHEMA_VERSION:
            raise ExperienceError(f"episode.schema must be {EPISODE_SCHEMA_VERSION}")
        derived = _fingerprint(self.identity())
        if self.experience_id and self.experience_id != derived:
            raise ExperienceError(
                f"episode id {self.experience_id} does not match the id its own canonical "
                f"identity derives ({derived}); the id is derived so it can be checked"
            )
        object.__setattr__(self, "experience_id", derived)

    # --- identity -----------------------------------------------------------

    def identity(self) -> dict[str, Any]:
        """The canonical identity of the attempt. Nothing else moves the id."""
        return {
            "schema": EPISODE_SCHEMA_VERSION,
            "work_order_id": self.work_order_id,
            "work_order_fingerprint": self.work_order_fingerprint,
            "packet_fingerprint": self.packet_fingerprint,
            "packet_attempt": self.packet_attempt,
            "receipt_fingerprint": self.receipt_fingerprint,
        }

    def content(self) -> dict[str, Any]:
        """What happened, without when or where it was indexed."""
        record = self.to_dict()
        for key in ("provenance", "source"):
            record.pop(key, None)
        return record

    def content_fingerprint(self) -> str:
        return _fingerprint(self.content())

    # --- classification --------------------------------------------------------

    def engineering_class(self) -> PrecedentClass:
        """The class the engineering stages alone assign, before governance joins.

        Accepted needs every stage to have spoken and agreed: the recorded
        outcome accepted, review passed, the gate ready, and the job parked
        where finished work parks. A single observed negative verdict makes it
        a correction. Anything else - no receipt, no review, a job stopped
        mid-flight - is incomplete, and incomplete is never promoted by
        default to either of the other two.
        """
        out = self.outcome
        if (
            out.recorded_outcome == "accepted"
            and out.review_outcome == "pass"
            and out.gate_readiness == "ready"
            and out.settled_state in _ACCEPTED_SETTLED_STATES
            and not out.tests_failed
        ):
            return PrecedentClass.ACCEPTED
        if (
            out.recorded_outcome == "rejected"
            or out.review_outcome in _NEGATIVE_REVIEWS
            or out.gate_readiness in _NEGATIVE_GATES
            or out.tests_failed
        ):
            return PrecedentClass.CORRECTION
        return PrecedentClass.INCOMPLETE

    def targets(self) -> tuple[str, ...]:
        """Where the attempt acted: the files it changed, else what it was granted."""
        return self.outcome.files_changed or self.features.write_paths

    def pointer(self, role: str) -> RecordPointer | None:
        return next((p for p in self.evidence if p.role == role), None)

    # --- serialisation ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_mapping(cls, data: Any) -> "ExperienceEpisode":
        raw = _strict(data, cls, "episode")
        evidence = raw.get("evidence", ())
        notes = raw.get("notes", ())
        for name, value in (("evidence", evidence), ("notes", notes)):
            if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
                raise ExperienceError(f"episode.{name} must be a list")
        return cls(
            work_order_id=str(raw.get("work_order_id", "")),
            work_order_fingerprint=str(raw.get("work_order_fingerprint", "")),
            packet_fingerprint=str(raw.get("packet_fingerprint", "")),
            packet_attempt=raw.get("packet_attempt", 0),
            receipt_fingerprint=str(raw.get("receipt_fingerprint", "")),
            decided_on=as_date(raw.get("decided_on"), "episode.decided_on"),
            settled_on=as_date(raw.get("settled_on"), "episode.settled_on"),
            features=DecisionFeatures.from_mapping(raw.get("features")),
            action=ChosenAction.from_mapping(raw.get("action")),
            outcome=ObservedOutcome.from_mapping(raw.get("outcome")),
            resources=ResourceObservation.from_mapping(raw.get("resources")),
            evidence=tuple(RecordPointer.from_mapping(item) for item in evidence),
            provenance=ScopeProvenance.from_mapping(raw.get("provenance")),
            source=str(raw.get("source", "local")),
            notes=tuple(str(item) for item in notes),
            schema=raw.get("schema", EPISODE_SCHEMA_VERSION),
            experience_id=str(raw.get("experience_id", "")),
        )


# --- the decision-time boundary, checked mechanically ------------------------

DECISION_TIME_FIELDS: frozenset[str] = frozenset(f.name for f in fields(DecisionFeatures))
OUTCOME_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(ObservedOutcome) if f.name != "schema"
) | frozenset(f.name for f in fields(ResourceObservation) if f.name != "schema")

# Asserted at import: a field name on both sides of the line is the first step
# towards a feature that quietly carries an outcome.
if DECISION_TIME_FIELDS & OUTCOME_FIELDS:  # pragma: no cover - a schema edit trips it
    raise ExperienceError(
        "decision-time and outcome fields overlap: "
        + ", ".join(sorted(DECISION_TIME_FIELDS & OUTCOME_FIELDS))
    )


def assert_decision_time_only(features: Mapping[str, Any]) -> None:
    """Refuse a feature mapping holding anything not known at decision time.

    The check a future training or evaluation step runs before it reads a row.
    It is a whitelist, not a blacklist: a key is decision-time only if
    `DecisionFeatures` declares it, so a new outcome field cannot slip through
    by having a name nobody thought to forbid.
    """
    if not isinstance(features, Mapping):
        raise ExperienceError("features must be a mapping")
    stray = sorted(set(features) - DECISION_TIME_FIELDS)
    if stray:
        leaked = sorted(set(stray) & OUTCOME_FIELDS)
        raise ExperienceError(
            "feature mapping holds field(s) not known at decision time: "
            + ", ".join(stray)
            + (f" (outcome fields: {', '.join(leaked)})" if leaked else "")
        )


def verify_features(episode: ExperienceEpisode, order: Any) -> tuple[str, ...]:
    """Recompute the features from the work order and name every disagreement.

    Empty means the stored snapshot is exactly what the authorized work order
    says - so nothing in it can have been learned after the decision. A
    work order that no longer decodes cannot be re-checked; the caller says so
    rather than calling that a pass.
    """
    if order.fingerprint() != episode.work_order_fingerprint:
        return (
            f"work order {order.work_order_id} has fingerprint {order.fingerprint()}, "
            f"not the {episode.work_order_fingerprint} the episode was captured from",
        )
    expected = to_jsonable(decision_features(order, attempt=episode.packet_attempt))
    stored = to_jsonable(episode.features)
    return tuple(
        f"features.{key}: stored {stored.get(key)!r}, work order says {expected.get(key)!r}"
        for key in sorted(set(expected) | set(stored))
        if expected.get(key) != stored.get(key)
    )


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "CANONICAL_STORES",
    "DECISION_TIME_FIELDS",
    "EPISODE_SCHEMA_VERSION",
    "FEATURE_SCHEMA_VERSION",
    "OUTCOME_FIELDS",
    "OUTCOME_SCHEMA_VERSION",
    "CapsuleAnchor",
    "ChosenAction",
    "DecisionFeatures",
    "EvidenceBasis",
    "ExperienceEpisode",
    "FindingNote",
    "Measurement",
    "ObservedOutcome",
    "PathAnchor",
    "PrecedentClass",
    "RecordPointer",
    "ResourceObservation",
    "ScopeProvenance",
    "assert_decision_time_only",
    "chosen_action",
    "decision_features",
    "verify_features",
]
