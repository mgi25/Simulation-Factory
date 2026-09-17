"""Behavioural probes: ask a Company OS guard to refuse something, and watch.

A structural check can say a guard exists. Only a probe can say it works, and
the difference matters for exactly the conditions this gate is least willing to
guess about - whether an authority fails open, whether a private number can be
attributed to a source that cannot see it, whether a store can be overwritten.

## What a probe is allowed to be

In-process, offline, and over inputs the probe itself constructs. No probe
reads the company's real state directory, writes anywhere but a temporary
directory it removes, or depends on a record somebody happened to have
created. That keeps every probe deterministic and keeps the gate runnable on a
fresh clone.

## Why a probe that cannot run is `unknown` and never `pass`

`run_probe` catches everything, including `ImportError`. A subsystem that is
absent, renamed or broken produces a probe result with `error` set, which the
check layer turns into `unknown` with the exception named. The one outcome
that is not available to a probe that did not complete is `pass`.

## Why the probes assert the refusal, not the acceptance

Each probe drives a guard to the edge it exists to hold and requires the
refusal, then - where it is cheap - shows the legitimate case still works, so
a guard that refuses everything is not mistaken for a guard that refuses the
right thing.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable


@dataclass(frozen=True)
class ProbeResult:
    """What a probe observed, or why it could not observe anything."""

    ok: bool
    detail: str
    evidence: tuple[str, ...] = ()
    error: str = ""

    @property
    def ran(self) -> bool:
        return not self.error


def run_probe(probe: Callable[[], ProbeResult]) -> ProbeResult:
    """Run `probe`, converting any escape into an unknown rather than a pass."""
    try:
        return probe()
    except BaseException as exc:  # noqa: BLE001 - a gate never guesses on an error
        return ProbeResult(
            ok=False,
            detail=f"the probe did not complete: {type(exc).__name__}: {exc}",
            error=f"{type(exc).__name__}: {exc}",
        )


def _refused(call: Callable[[], object], expected: type[BaseException]) -> str:
    """Return an empty string if `call` raised `expected`, else say what happened."""
    try:
        call()
    except expected:
        return ""
    except BaseException as exc:  # noqa: BLE001 - the wrong refusal is still a finding
        return f"raised {type(exc).__name__} instead of {expected.__name__}: {exc}"
    return f"was accepted; {expected.__name__} was expected"


# -- execution safety -------------------------------------------------------


def probe_read_authority_fails_closed() -> ProbeResult:
    """A contract that grants no read authority must project to none, not to all."""
    from company.runtime.authority import (
        AuthoritySource,
        ExecutionAuthoritySnapshot,
        authority_projection,
    )

    silent = authority_projection({"employee_id": "gate-probe", "no_subagents": True}, employee="gate-probe")
    problems = []
    if silent["may_read"] != ():
        problems.append(f"an absent may_read projected to {silent['may_read']!r}, not ()")
    if silent["may_write"] != ():
        problems.append(f"an absent may_write projected to {silent['may_write']!r}, not ()")

    snapshot = ExecutionAuthoritySnapshot.from_contract(
        task_id="gate-probe",
        employee="gate-probe",
        packet_fingerprint="0" * 16,
        packet_attempt=1,
        contract={"employee_id": "gate-probe", "no_subagents": True, "may_read": ["company"]},
        source=AuthoritySource.CANONICAL_CONTRACT,
    )
    if snapshot.may_read != ("company",):
        problems.append(f"a granted may_read was altered to {snapshot.may_read!r}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "a contract that names no readable path projects to an empty grant, and "
            "a named path is carried through unchanged"
        ),
        evidence=("company/runtime/authority.py:201",),
    )


def probe_write_authority_fails_closed() -> ProbeResult:
    """An empty allow-list permits nothing, and a forbidding rule outranks an allow."""
    from company.runtime.path_scope import PathScope

    problems = []
    silent = PathScope()
    if not silent.read_only:
        problems.append("a scope with no allowed path did not report itself read-only")
    if silent.permits("company/runtime/packets.py"):
        problems.append("a scope with no allowed path permitted a write")

    overlapping = PathScope(allowed=("company",), forbidden=("company/permissions.yaml",))
    verdict = overlapping.verdict(("company/permissions.yaml",))
    if verdict.ok:
        problems.append("a path matched by both lists was allowed; forbidden must win")
    if overlapping.verdict(("sloped/scale.py",)).ok:
        problems.append("a path outside every allowed rule was allowed")
    if not overlapping.verdict(("company/runtime/packets.py",)).ok:
        problems.append("a legitimately allowed path was refused")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "an empty allow-list permits nothing, a forbidding rule outranks an "
            "overlapping allow, and a path inside the allow-list still passes"
        ),
        evidence=("company/runtime/path_scope.py:72",),
    )


def probe_authority_snapshot_immutable() -> ProbeResult:
    """A snapshot cannot be mutated, and a widened copy cannot be constructed."""
    from company.runtime.authority import (
        AuthoritySource,
        ExecutionAuthoritySnapshot,
    )
    from company.runtime.errors import LifecycleError

    snapshot = ExecutionAuthoritySnapshot.from_contract(
        task_id="gate-probe",
        employee="gate-probe",
        packet_fingerprint="0" * 16,
        packet_attempt=1,
        contract={
            "employee_id": "gate-probe",
            "no_subagents": True,
            "may_read": ["company"],
            "may_write": [],
        },
        source=AuthoritySource.CANONICAL_CONTRACT,
    )
    problems = []
    try:
        snapshot.may_write = ("sloped",)  # type: ignore[misc]
        problems.append("the snapshot accepted an attribute assignment")
    except dataclasses.FrozenInstanceError:
        pass

    widened = _refused(
        lambda: dataclasses.replace(snapshot, may_write=("sloped",)), LifecycleError
    )
    if widened:
        problems.append(f"a widened copy {widened}")

    restored = ExecutionAuthoritySnapshot.from_mapping(snapshot.to_dict())
    if restored != snapshot or restored.fingerprint() != snapshot.fingerprint():
        problems.append("a round trip through canonical JSON did not reproduce the snapshot")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "the snapshot is frozen, its contract fingerprint refuses a widened "
            "copy, and it round-trips through canonical JSON unchanged"
        ),
        evidence=("company/runtime/authority.py:38",),
    )


def probe_receipt_validation_enforced() -> ProbeResult:
    """A returned receipt cannot carry an unknown field or amend the subagent rule."""
    from company.runtime.receipts import SessionReceipt
    from company.validation.errors import ValidationError

    base = {"task_id": "gate-probe", "packet_fingerprint": "0" * 16, "outcome": "accepted"}
    problems = []
    unknown = _refused(
        lambda: SessionReceipt.from_mapping({**base, "granted_authority": ["sloped"]}),
        ValidationError,
    )
    if unknown:
        problems.append(f"a receipt with an unknown field {unknown}")
    amended = _refused(
        lambda: SessionReceipt.from_mapping({**base, "no_subagents": False}), ValidationError
    )
    if amended:
        problems.append(f"a receipt claiming no_subagents=false {amended}")
    try:
        SessionReceipt.from_mapping(base)
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a well-formed receipt was refused: {type(exc).__name__}: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "a receipt outside the schema and a receipt amending the no-subagent "
            "rule are both refused, and a well-formed receipt is accepted"
        ),
        evidence=("company/runtime/receipts.py:304",),
    )


def probe_no_subagent_runtime_lock() -> ProbeResult:
    """The two-key lock holds: bootstrap fixes the switch, and no contract may flip it."""
    from ai_platform.policy import (
        BOOTSTRAP_POLICY,
        ExecutionPolicy,
        SubagentPolicyViolation,
    )
    from company.runtime.authority import authority_projection

    problems = []
    if BOOTSTRAP_POLICY.allows_nested_agents:
        problems.append("the bootstrap policy reports that nested agents are allowed")
    locked = _refused(lambda: ExecutionPolicy(no_subagents=False), SubagentPolicyViolation)
    if locked:
        problems.append(f"a bootstrap policy with no_subagents=false {locked}")
    spawning = _refused(
        lambda: ExecutionPolicy(nested_agent_spawning=True), SubagentPolicyViolation
    )
    if spawning:
        problems.append(f"a bootstrap policy enabling nested spawning {spawning}")
    contract = _refused(
        lambda: authority_projection(
            {"employee_id": "gate-probe", "no_subagents": False}, employee="gate-probe"
        ),
        SubagentPolicyViolation,
    )
    if contract:
        problems.append(f"an employee contract with no_subagents=false {contract}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "bootstrap mode fixes the no-subagent switch, and a policy, a contract "
            "and a receipt that try to flip it are each refused"
        ),
        evidence=("ai_platform/policy.py:105", "company/runtime/authority.py:218"),
    )


# -- data and evidence ------------------------------------------------------


def probe_private_metric_boundary() -> ProbeResult:
    """A private channel analytic cannot be attributed to a source that cannot see it."""
    from company.analytics.common import DataSource
    from company.analytics.errors import ProvenanceViolation
    from company.analytics.metrics import DEFAULT_REGISTRY

    private_names = DEFAULT_REGISTRY.private_names()
    if not private_names:
        return ProbeResult(
            ok=False,
            detail="the metric registry declares no private metric, so the boundary is untested",
        )
    metric = DEFAULT_REGISTRY.get(sorted(private_names)[0])
    problems = []
    external = _refused(
        lambda: metric.assert_source_can_produce(DataSource.PLATFORM_PUBLIC, "gate-probe"),
        ProvenanceViolation,
    )
    if external:
        problems.append(f"{metric.name!r} from a public page {external}")
    try:
        metric.assert_source_can_produce(DataSource.OWN_STUDIO_EXPORT, "gate-probe")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"our own authenticated export was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else f"{metric.name!r} is refused from a public source and accepted from "
            f"our own authenticated export ({len(private_names)} private metrics)"
        ),
        evidence=("company/analytics/metrics.py:118",),
    )


def probe_competitor_private_metrics_unavailable() -> ProbeResult:
    """An external reference may name public metrics only, and must cite a dossier."""
    from company.analytics.errors import AnalyticsError, ProvenanceViolation
    from company.analytics.metrics import DEFAULT_REGISTRY
    from company.analytics.references import CompetitorPublicReference

    private = sorted(DEFAULT_REGISTRY.private_names())
    if not private:
        return ProbeResult(ok=False, detail="no private metric is declared, so nothing is tested")
    problems = []
    leaked = _refused(
        lambda: CompetitorPublicReference(dossier_ids=("gate-probe",), public_metrics=(private[0],)),
        ProvenanceViolation,
    )
    if leaked:
        problems.append(f"a competitor reference naming {private[0]!r} {leaked}")
    uncited = _refused(
        lambda: CompetitorPublicReference(dossier_ids=()), AnalyticsError
    )
    if uncited:
        problems.append(f"a competitor reference with no dossier {uncited}")
    try:
        CompetitorPublicReference(dossier_ids=("gate-probe",), public_metrics=("views",))
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a public metric on a cited reference was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "an external reference carrying a private metric name is refused, an "
            "uncited one is refused, and a cited public metric name is accepted"
        ),
        evidence=("company/analytics/references.py:276",),
    )


def probe_evidence_required_for_claims() -> ProbeResult:
    """A knowledge record with no evidence cannot be built."""
    from knowledge.company_os.records import Fact, Freshness, KnowledgeError

    problems = []
    bare = _refused(
        lambda: Fact(
            id="gate-probe",
            statement="A statement nobody has to be able to check.",
            evidence=(),
            source="company-integration-gate",
            created=dt.date(2026, 1, 1),
            freshness=Freshness.PERMANENT,
        ),
        KnowledgeError,
    )
    if bare:
        problems.append(f"a fact with no evidence {bare}")
    try:
        _probe_fact()
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a fact citing a document was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "a fact with no evidence is refused and a fact citing a document is kept"
        ),
        evidence=("knowledge/company_os/records.py",),
    )


def probe_audit_records_append_only() -> ProbeResult:
    """Recorded history cannot be quietly replaced with different content."""
    from knowledge.company_os.ledger import KnowledgeStore
    from knowledge.company_os.records import KnowledgeError

    record = _probe_fact()
    with tempfile.TemporaryDirectory() as directory:
        store = KnowledgeStore(Path(directory))
        store.add(record)
        problems = []
        changed = dataclasses.replace(
            record, statement="A different statement stored under the same record id."
        )
        overwritten = _refused(lambda: store.add(changed), KnowledgeError)
        if overwritten:
            problems.append(f"a differing record under the same id {overwritten}")
        return ProbeResult(
            ok=not problems,
            detail=(
                "; ".join(problems)
                if problems
                else "a second, different record under an existing id is refused; a "
                "correction is a new record that supersedes the old one"
            ),
            evidence=("knowledge/company_os/ledger.py:68",),
        )


def probe_missing_evidence_stays_unknown() -> ProbeResult:
    """An empty company reports gaps, and never invents a value to fill one.

    Some sections are built from the canonical contracts under `company/`
    rather than from the state directory, so they legitimately have content
    when the state directory is empty. The condition is not "everything is
    missing" - it is that nothing claims to be complete when it is not, and
    that every gap is named.
    """
    from company.dashboard.builder import build_snapshot
    from company.dashboard.models import Availability

    with tempfile.TemporaryDirectory() as directory:
        snapshot = build_snapshot(directory, as_of=dt.date(2026, 1, 1))
    problems = []
    if not snapshot.sections:
        problems.append("an empty state directory produced no sections at all")
    if not snapshot.known_missing_sources:
        problems.append(
            "an empty state directory produced no known missing source; the gaps were "
            "not reported anywhere"
        )
    record_backed = 0
    for section in snapshot.sections:
        if section.availability is Availability.MISSING:
            record_backed += 1
            if not section.missing:
                problems.append(f"section {section.name} is missing but named nothing")
            if section.dimensions:
                problems.append(
                    f"section {section.name} has no records and still reported "
                    f"{len(section.dimensions)} dimension(s)"
                )
        elif section.availability is Availability.AVAILABLE:
            if section.missing:
                problems.append(
                    f"section {section.name} reported available while naming "
                    f"{len(section.missing)} missing source(s)"
                )
            if not section.dimensions:
                problems.append(
                    f"section {section.name} reported available with nothing measured"
                )
    if not record_backed:
        problems.append("no section reported missing over an empty state directory")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems[:4])
            if problems
            else f"{record_backed} of {len(snapshot.sections)} sections report missing "
            f"over an empty state directory, each naming its gap, and "
            f"{len(snapshot.known_missing_sources)} gaps reach the snapshot; no section "
            "claims to be complete while it is not"
        ),
        evidence=("company/dashboard/builder.py", "company/dashboard/models.py"),
    )


def probe_dashboard_available() -> ProbeResult:
    """The executive view builds, renders a brief, and identifies itself."""
    from company.dashboard.brief import build_brief
    from company.dashboard.builder import build_snapshot

    with tempfile.TemporaryDirectory() as directory:
        snapshot = build_snapshot(directory, as_of=dt.date(2026, 1, 1))
        repeated = build_snapshot(directory, as_of=dt.date(2026, 1, 1))
        brief = build_brief(snapshot)
    problems = []
    if not snapshot.snapshot_id:
        problems.append("the snapshot carries no id")
    if snapshot.snapshot_id != repeated.snapshot_id:
        problems.append("two builds over the same inputs produced different snapshot ids")
    text = brief.render_text()
    if not text.strip():
        problems.append("the CEO brief rendered empty")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else f"the snapshot builds deterministically ({snapshot.snapshot_id}) and the "
            f"brief renders {len(text.splitlines())} lines"
        ),
        evidence=("company/dashboard/builder.py", "company/dashboard/brief.py"),
    )


# -- workforce, finance, analytics ------------------------------------------


def probe_restricted_states_cannot_write_production(permissions: dict) -> ProbeResult:
    """A candidate, shadow or probation employee cannot hold production authority."""
    from company.workforce.employment import (
        PRODUCTION_WRITE_ACTIONS,
        EmploymentState,
        assert_authority,
        assert_may_not_write_production,
        state_authority_cap,
    )
    from company.workforce.errors import AuthorityViolation

    restricted = [state for state in EmploymentState if state.is_restricted]
    problems = []
    if not restricted:
        problems.append("no employment state is marked restricted")
    for state in restricted:
        refused = _refused(
            lambda state=state: assert_may_not_write_production(
                state, tuple(sorted(PRODUCTION_WRITE_ACTIONS))
            ),
            AuthorityViolation,
        )
        if refused:
            problems.append(f"a {state.value} employee requesting production authority {refused}")
        over = _refused(
            lambda state=state: assert_authority(state, 5, permissions), AuthorityViolation
        )
        if over:
            problems.append(f"a {state.value} employee at autonomy level 5 {over}")
    if state_authority_cap(EmploymentState.CANDIDATE, {}) != 0:
        problems.append("a malformed permission file did not cap authority at 0")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems[:4])
            if problems
            else f"{len(restricted)} restricted states are refused production authority "
            "and level 5, and a malformed permission file caps authority at observe"
        ),
        evidence=("company/workforce/employment.py:319", "company/permissions.yaml"),
    )


def probe_advisory_cannot_self_approve() -> ProbeResult:
    """An organizational recommendation cannot be signed by the system that made it."""
    from company.org_intelligence.common import AUTOMATIC_MARKERS, assert_human
    from company.org_intelligence.errors import OrgIntelligenceError

    problems = []
    for marker in sorted(AUTOMATIC_MARKERS)[:4]:
        refused = _refused(
            lambda marker=marker: assert_human(marker, "approved_by"), OrgIntelligenceError
        )
        if refused:
            problems.append(f"an approval signed {marker!r} {refused}")
    try:
        assert_human("the CEO", "approved_by")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a named human approver was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems[:3])
            if problems
            else "an organizational decision signed by the system is refused and a named "
            "human approver is accepted"
        ),
        evidence=("company/org_intelligence/common.py:147",),
    )


def probe_no_autonomous_spend_approval() -> ProbeResult:
    """Money is not approved by the subsystem that proposes it."""
    from company.finance.common import AUTOMATIC_MARKERS, assert_human
    from company.finance.errors import FinanceError

    problems = []
    for marker in sorted(AUTOMATIC_MARKERS)[:4]:
        refused = _refused(lambda marker=marker: assert_human(marker, "approved_by"), FinanceError)
        if refused:
            problems.append(f"a spend approved by {marker!r} {refused}")
    try:
        assert_human("the CEO", "approved_by")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a named human approver was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems[:3])
            if problems
            else "a spend signed by an automatic marker is refused; approving a spend "
            "remains a named human act"
        ),
        evidence=("company/finance/common.py:223",),
    )


def probe_unknown_is_not_zero() -> ProbeResult:
    """With nothing recorded, a margin is unknown rather than zero."""
    from company.finance.common import SubjectKind, SubjectRef
    from company.finance.economics import deliverable_economics
    from company.finance.period import FinancialPeriod

    period = FinancialPeriod(
        period_id="gate-probe",
        label="Integration gate probe window",
        start=dt.date(2026, 1, 1),
        end=dt.date(2026, 1, 31),
        currency="USD",
    )
    economics = deliverable_economics(
        SubjectRef(kind=SubjectKind.VIDEO, id="gate-probe"), period
    )
    problems = []
    if economics.gross_margin is not None:
        problems.append(f"a margin of {economics.gross_margin} was reported over no records")
    if economics.net_contribution is not None:
        problems.append("a net contribution was reported over no records")
    if not economics.missing:
        problems.append("nothing was recorded and nothing was reported as missing")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else f"with no records the margin and contribution are unknown and "
            f"{len(economics.missing)} reasons are named"
        ),
        evidence=("company/finance/economics.py:168",),
    )


def probe_causal_overclaim_refused() -> ProbeResult:
    """An uncontrolled comparison cannot support a causal claim."""
    from company.analytics.results import CausalAssessment, ComparisonBasis

    uncontrolled = [basis for basis in ComparisonBasis if not basis.controls_assignment]
    if not uncontrolled:
        return ProbeResult(ok=False, detail="every comparison basis claims to control assignment")
    assessment = CausalAssessment(
        basis=uncontrolled[0], sample_size=1000, minimum_sample=5, changed_variable_count=3
    )
    problems = []
    if assessment.causal_claim_supported:
        problems.append(
            f"a {uncontrolled[0].value} comparison with 3 changed variables supported a "
            "causal claim"
        )
    if not assessment.blockers:
        problems.append("the assessment named no reason the claim is unavailable")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else f"an uncontrolled comparison over 1000 samples still supports no causal "
            f"claim and names {len(assessment.blockers)} reasons"
        ),
        evidence=("company/analytics/results.py:132",),
    )


def probe_learning_requires_results() -> ProbeResult:
    """A hypothesis cannot be supported by nothing; observation is not learning."""
    from company.analytics.errors import OverclaimRefused
    from company.analytics.learning import AnalyticsHypothesis, HypothesisState

    def supported_without_results() -> object:
        return AnalyticsHypothesis(
            hypothesis_id="gate-probe",
            statement="A hypothesis promoted with no experiment behind it.",
            rationale="The integration gate drives this guard to its edge.",
            proposed_on=dt.date(2026, 1, 1),
            owner="company-integration-gate",
            state=HypothesisState.SUPPORTED,
        )

    problems = []
    refused = _refused(supported_without_results, OverclaimRefused)
    if refused:
        problems.append(f"a supported hypothesis with no result {refused}")
    try:
        AnalyticsHypothesis(
            hypothesis_id="gate-probe",
            statement="A hypothesis that is still only proposed.",
            rationale="The unpromoted case must stay constructible.",
            proposed_on=dt.date(2026, 1, 1),
            owner="company-integration-gate",
            state=HypothesisState.PROPOSED,
        )
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a proposed hypothesis was refused: {exc}")
    return ProbeResult(
        ok=not problems,
        detail=(
            "; ".join(problems)
            if problems
            else "a hypothesis cannot be marked supported without a result to point at, "
            "while a proposed one records freely"
        ),
        evidence=("company/analytics/learning.py:202",),
    )


def _probe_fact():
    """One valid knowledge record, built the same way by every probe that needs one."""
    from knowledge.company_os.records import Evidence, Fact, Freshness

    return Fact(
        id="gate-probe",
        statement="A probe record written by the production integration gate.",
        evidence=(Evidence(kind="document", ref="company/constitution.md", note="rule 2"),),
        source="company-integration-gate",
        created=dt.date(2026, 1, 1),
        freshness=Freshness.PERMANENT,
    )


__all__ = [
    "ProbeResult",
    "probe_advisory_cannot_self_approve",
    "probe_audit_records_append_only",
    "probe_authority_snapshot_immutable",
    "probe_causal_overclaim_refused",
    "probe_competitor_private_metrics_unavailable",
    "probe_dashboard_available",
    "probe_evidence_required_for_claims",
    "probe_learning_requires_results",
    "probe_missing_evidence_stays_unknown",
    "probe_no_autonomous_spend_approval",
    "probe_no_subagent_runtime_lock",
    "probe_private_metric_boundary",
    "probe_read_authority_fails_closed",
    "probe_receipt_validation_enforced",
    "probe_restricted_states_cannot_write_production",
    "probe_unknown_is_not_zero",
    "probe_write_authority_fails_closed",
    "run_probe",
]
