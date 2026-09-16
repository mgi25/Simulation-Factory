"""Read existing Company OS stores into one deterministic executive snapshot."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ai_platform.serde import fingerprint
from ai_platform.usage import Outcome, ResourceUsageRecord
from company.analytics.integrity import check_integrity as analytics_integrity
from company.analytics.store import AnalyticsStore
from company.finance.integrity import check_integrity as finance_integrity
from company.finance.store import FinanceStore
from company.org_intelligence.integrity import check_integrity as organization_integrity
from company.org_intelligence.store import OrgIntelligenceStore
from company.runtime.authority import ExecutionAuthoritySnapshot
from company.runtime.config import load_company_config
from company.runtime.context_expansion import ContextExpansionDecision, ContextExpansionRequest
from company.runtime.packets import SessionPacket
from company.runtime.receipts import SessionReceipt
from company.workforce.capabilities import CapabilityRegistry, Criticality
from company.workforce.integrity import check_integrity as workforce_integrity
from company.workforce.store import WorkforceStore
from intelligence.research.batch import BatchStatus
from intelligence.research.store import RECORD_TYPES, ResearchStore
from knowledge.company_os.capsules.index import CapsuleIndex

from .models import (
    AttentionItem,
    AttentionLevel,
    Availability,
    CEODecisionItem,
    CompanyStateSnapshot,
    ExecutiveDimension,
    ExecutiveSection,
    FormatView,
    FreshnessState,
    ProjectView,
    SourceReference,
    SourceSubsystem,
    make_snapshot_id,
)


@dataclass(frozen=True)
class CompanyStatePaths:
    """Explicit canonical-source roots.  The default layout keeps stores separate."""

    root: Path
    execution: Path
    research: Path
    analytics: Path
    finance: Path
    workforce: Path
    organization: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "CompanyStatePaths":
        base = Path(root).resolve()
        return cls(base, base / "runtime", base / "research", base / "analytics",
                   base / "finance", base / "workforce", base / "organization")

    @classmethod
    def flat(cls, root: str | Path) -> "CompanyStatePaths":
        """Compatibility layout for a caller that deliberately shares one store root."""
        base = Path(root).resolve()
        return cls(base, base, base, base, base, base, base)


@dataclass
class _Result:
    section: ExecutiveSection
    refs: tuple[SourceReference, ...] = ()
    decisions: tuple[CEODecisionItem, ...] = ()
    attention: tuple[AttentionItem, ...] = ()
    records: dict[str, tuple[Any, ...]] | None = None


class _Reader:
    def __init__(self, paths: CompanyStatePaths, as_of: dt.date, repo_root: Path) -> None:
        self.paths, self.as_of, self.repo_root = paths, as_of, repo_root
        self.config = load_company_config(repo_root / "company")

    def ref(self, subsystem: SourceSubsystem, kind: str, record_id: str,
            path: Path, record: Any) -> SourceReference:
        data = record.to_dict() if hasattr(record, "to_dict") else record
        due = _date(getattr(record, "recheck_on", None) or (data.get("recheck_on") if isinstance(data, Mapping) else None))
        freshness = FreshnessState.UNKNOWN
        declared = getattr(getattr(record, "freshness", None), "value", None)
        if declared == "permanent":
            freshness = FreshnessState.CURRENT
        elif due is not None:
            freshness = FreshnessState.STALE if due < self.as_of else FreshnessState.CURRENT
        return SourceReference(subsystem, kind, record_id, self.relative(path),
                               fingerprint(data), freshness, due)

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.paths.root).as_posix()
        except ValueError:
            return f"external/{path.name}"

    def missing(self, name: str, detail: str) -> _Result:
        return _Result(ExecutiveSection(name, Availability.MISSING,
                                         f"{name.title()} data unavailable.",
                                         missing=(detail,)))

    def execution(self) -> _Result:
        root = self.paths.execution
        patterns: tuple[tuple[str, str, Callable[[Mapping[str, Any]], Any]], ...] = (
            ("packet", "execution/packets/*/*.json", SessionPacket.from_mapping),
            ("authority", "execution/authorities/*/*.json", ExecutionAuthoritySnapshot.from_mapping),
            ("receipt", "execution/receipts/*/*.json", SessionReceipt.from_mapping),
            ("context_expansion_request", "execution/context_expansions/requests/*/*.json", ContextExpansionRequest.from_mapping),
            ("context_expansion_decision", "execution/context_expansions/decisions/*/*.json", ContextExpansionDecision.from_mapping),
            ("resource_usage", "resource_usage/*/*.json", ResourceUsageRecord.from_mapping),
        )
        decoded: dict[str, list[tuple[Any, SourceReference]]] = defaultdict(list)
        issues: list[str] = []
        for kind, pattern, decoder in patterns:
            for path in sorted(root.glob(pattern)):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    record = decoder(raw)
                    task_id = str(raw.get("task_id", path.parent.name))
                    record_id = f"{task_id}:{path.stem}"
                    decoded[kind].append((record, self.ref(SourceSubsystem.EXECUTION, kind, record_id, path, record)))
                except Exception as exc:  # corrupt state belongs on the dashboard
                    issues.append(f"{self.relative(path)}: {exc}")
        refs = tuple(ref for rows in decoded.values() for _record, ref in rows)
        if not refs and not issues:
            return self.missing("execution", "execution:no_records")
        packets = decoded["packet"]
        authorities = decoded["authority"]
        receipts = decoded["receipt"]
        requests = decoded["context_expansion_request"]
        decisions_raw = decoded["context_expansion_decision"]
        usage = decoded["resource_usage"]
        answered = {(r.task_id, r.packet_attempt, r.packet_fingerprint) for r, _ in receipts}
        authority_keys = {(a.task_id, a.packet_attempt, a.packet_fingerprint) for a, _ in authorities}
        packet_keys = {(p.task_id, int(ref.record_ref.rsplit("/", 1)[-1][:-5]), p.fingerprint()) for p, ref in packets}
        pending = [(p, ref) for p, ref in packets
                   if (p.task_id, int(ref.record_ref.rsplit("/", 1)[-1][:-5]), p.fingerprint()) not in answered]
        for key in sorted(packet_keys - authority_keys):
            issues.append(f"orphan packet without authority snapshot: {key[0]} attempt {key[1]}")
        for r, _ref in receipts:
            if (r.task_id, r.packet_attempt, r.packet_fingerprint) not in packet_keys:
                issues.append(f"receipt without matching packet: {r.task_id} attempt {r.packet_attempt}")
        rejected = [(r, ref) for r, ref in receipts if r.outcome is Outcome.REJECTED]
        abandoned = [(r, ref) for r, ref in receipts if r.outcome is Outcome.ABANDONED]
        accepted = [(r, ref) for r, ref in receipts if r.outcome is Outcome.ACCEPTED]
        rejected_expansions = [(d, ref) for d, ref in decisions_raw if d.rejected_refs]
        usage_records = [record for record, _ in usage]
        receipt_rejected_tasks = {record.task_id for record, _ in rejected}
        usage_only_rejected = [(record, ref) for record, ref in usage
                               if record.outcome is Outcome.REJECTED and record.task_id not in receipt_rejected_tasks]
        visible_rejections = (*rejected, *usage_only_rejected)
        context_precision = [r.context_precision for r in usage_records if r.context_precision is not None]
        attention: list[AttentionItem] = []
        for record, ref in rejected:
            attention.append(AttentionItem(f"execution-rejected-{ref.fingerprint}", record.task_id,
                                           record.rejection_reason or "runtime rejected the attempt",
                                           (ref.key,), "execution", AttentionLevel.ACTION_REQUIRED,
                                           "A later accepted attempt or an explicit closeout resolves the rejection."))
        for record, ref in usage_only_rejected:
            attention.append(AttentionItem(f"execution-rejected-{ref.fingerprint}", record.task_id,
                                           record.rejection_reason,
                                           (ref.key,), "execution", AttentionLevel.ACTION_REQUIRED,
                                           "A later accepted attempt or an explicit closeout resolves the rejection."))
        for record, ref in usage:
            if record.rejected_expansion_sources:
                attention.append(AttentionItem(f"context-rejected-usage-{ref.fingerprint}", record.task_id,
                                               f"{len(record.rejected_expansion_sources)} requested context reference(s) were rejected.",
                                               (ref.key,), "context", AttentionLevel.WATCH,
                                               "Remove the dependency or provide an allowed, audited reference."))
        for record, ref in rejected_expansions:
            attention.append(AttentionItem(f"context-rejected-{ref.fingerprint}", record.task_id,
                                           "A context expansion request was rejected.", (ref.key,),
                                           "context", AttentionLevel.BLOCKED if record.required_to_continue else AttentionLevel.WATCH,
                                           "Provide an allowed reference or close the request as unnecessary."))
        if pending:
            attention.append(AttentionItem("execution-pending-receipts", "pending task attempts",
                                           f"{len(pending)} packet attempt(s) have no receipt.",
                                           tuple(ref.key for _p, ref in pending), "execution",
                                           AttentionLevel.BLOCKED, "Persist a validated receipt for each packet attempt."))
        if issues and refs:
            attention.append(AttentionItem("execution-integrity", "execution history",
                                           f"{len(issues)} execution integrity issue(s) remain.",
                                           (refs[0].key,), "integrity", AttentionLevel.BLOCKED,
                                           "Repair canonical execution state and rerun integrity checks."))
        dims = (
            _dim("active_task_attempts", len(pending), pending),
            _dim("completed_tasks", len({r.task_id for r, _ in accepted}), accepted),
            _dim("rejected_attempts", len(visible_rejections), visible_rejections),
            _dim("escalated_or_abandoned_attempts", len(abandoned), abandoned),
            _dim("pending_receipts", len(pending), pending),
            _dim("context_expansion_requests", len(requests), requests),
            _dim("rejected_context_expansions", len(rejected_expansions), rejected_expansions),
            ExecutiveDimension("reported_context_expansions",
                               sum(r.expansion_count for r in usage_records) if usage_records else None,
                               known=bool(usage_records), source_refs=tuple(ref.key for _r, ref in usage),
                               note="Count carried by canonical usage records."),
            ExecutiveDimension("reported_rejected_expansion_refs",
                               sum(r.rejected_expansion_ref_count for r in usage_records) if usage_records else None,
                               known=bool(usage_records), source_refs=tuple(ref.key for _r, ref in usage)),
            ExecutiveDimension("accepted_usage_records",
                               sum(r.outcome is Outcome.ACCEPTED for r in usage_records) if usage_records else None,
                               known=bool(usage_records), source_refs=tuple(ref.key for _r, ref in usage),
                               note="Unknown when no usage records exist."),
            ExecutiveDimension("retries", sum(r.retries for r in usage_records) if usage_records else None,
                               known=bool(usage_records),
                               source_refs=tuple(ref.key for _r, ref in usage), note="Unknown when no usage records exist."),
            ExecutiveDimension("context_precision", (sum(context_precision) / len(context_precision)) if context_precision else None,
                               known=bool(context_precision), unit="fraction",
                               source_refs=tuple(ref.key for r, ref in usage if r.context_precision is not None),
                               note="Mean of explicitly reported per-attempt precision; not available when usage is unreported."),
            ExecutiveDimension("no_subagent_invariant",
                               all(getattr(r, "no_subagents", True) is True and getattr(r, "subagents_used", 0) == 0
                                   for r, _ in (*packets, *receipts, *usage)) if (packets or receipts or usage) else None,
                               known=bool(packets or receipts or usage),
                               source_refs=tuple(ref.key for _r, ref in (*packets, *receipts, *usage))),
        )
        return _Result(ExecutiveSection("execution", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{len(pending)} active attempt(s); {len(accepted)} accepted and {len(visible_rejections)} rejected attempt(s).",
                                        dims, tuple(r.key for r in refs), integrity_issues=tuple(issues)), refs,
                       attention=tuple(attention), records={k: tuple(r for r, _ in v) for k, v in decoded.items()})

    def research(self) -> _Result:
        store = ResearchStore(self.paths.research)
        refs: list[SourceReference] = []
        records: dict[str, tuple[Any, ...]] = {}
        issues: list[str] = []
        for kind in sorted(RECORD_TYPES):
            try:
                rows = store.load_all(kind)
                records[kind] = rows
                for record in rows:
                    path = store.path_for(kind, record.id)
                    refs.append(self.ref(SourceSubsystem.RESEARCH, kind, record.id, path, record))
            except Exception as exc:
                issues.append(f"research {kind}: {exc}")
        if not refs and not issues:
            return self.missing("research", "research:no_records")
        try:
            issues.extend(str(x) for x in store.integrity())
        except Exception as exc:
            issues.append(f"research integrity unavailable: {exc}")
        batches = records.get("research_batch", ())
        active = tuple(b for b in batches if b.is_open)
        stopped = tuple(b for b in batches if b.status is BatchStatus.STOPPED)
        ceiling = []
        missing_measurements: list[str] = []
        saturated = 0
        for batch in batches:
            try:
                report = store.batch_report(batch.id, as_of=self.as_of)
                if any(signal.triggered for signal in report.stop_signals):
                    ceiling.append(batch)
                if any(signal.state.value == "saturated" for signal in report.saturation):
                    saturated += 1
                missing_measurements.extend(f"{batch.id}: {x}" for x in report.missing_measurements)
            except Exception as exc:
                missing_measurements.append(f"{batch.id}: report unavailable ({exc})")
        stale_keys = tuple(r.key for r in refs if r.freshness is FreshnessState.STALE)
        attention: list[AttentionItem] = []
        for batch in stopped:
            key = f"research:research_batch:{batch.id}"
            attention.append(AttentionItem(f"research-stopped-{batch.id}", batch.id,
                                           "Research batch is stopped.", (key,), "research",
                                           AttentionLevel.ACTION_REQUIRED,
                                           "Close the batch or record an authorised escalation in its canonical history."))
        for ref in refs:
            if ref.freshness is FreshnessState.STALE:
                attention.append(AttentionItem(f"stale-{ref.fingerprint}", ref.record_id,
                                               "Research evidence is past its recheck date.", (ref.key,),
                                               "freshness", AttentionLevel.WATCH,
                                               "Recheck the canonical record and update its freshness evidence."))
        dimensions = (
            ExecutiveDimension("active_batches", len(active), source_refs=_keys(refs, "research_batch", {b.id for b in active})),
            ExecutiveDimension("stopped_batches", len(stopped), source_refs=_keys(refs, "research_batch", {b.id for b in stopped})),
            ExecutiveDimension("batches_at_declared_ceiling", len(ceiling), source_refs=_keys(refs, "research_batch", {b.id for b in ceiling})),
            ExecutiveDimension("promoted_sources", len(records.get("source", ())), source_refs=_keys(refs, "source")),
            ExecutiveDimension("opportunity_dossiers", len(records.get("opportunity", ())), source_refs=_keys(refs, "opportunity")),
            ExecutiveDimension("video_dossiers", len(records.get("video_dossier", ())), source_refs=_keys(refs, "video_dossier")),
            ExecutiveDimension("saturated_batches", saturated, source_refs=_keys(refs, "research_batch")),
            ExecutiveDimension("missing_measurements", tuple(sorted(set(missing_measurements))), known=True,
                               source_refs=_keys(refs, "research_batch")),
        )
        return _Result(ExecutiveSection("research", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{len(active)} active and {len(stopped)} stopped research batch(es).",
                                        dimensions, tuple(r.key for r in refs), (), stale_keys,
                                        tuple(sorted(set(issues)))), tuple(refs), attention=tuple(attention), records=records)

    def analytics(self) -> _Result:
        store = AnalyticsStore(self.paths.analytics)
        kinds = ("deliverable", "observation", "experiment", "result", "postmortem", "learning", "hypothesis", "baseline")
        records, refs, issues = self._store_records(store, SourceSubsystem.ANALYTICS, kinds,
                                                    {"deliverable":"deliverables", "observation":"observations",
                                                     "experiment":"experiments", "result":"results", "postmortem":"postmortems",
                                                     "learning":"learnings", "hypothesis":"hypotheses", "baseline":"baselines"})
        if not refs and not issues:
            return self.missing("analytics", "analytics:no_records")
        try:
            issues.extend(analytics_integrity(store))
        except Exception as exc:
            issues.append(f"analytics integrity unavailable: {exc}")
        experiments = records.get("experiment", ())
        results = records.get("result", ())
        active = tuple(x for x in experiments if x.status.value in {"draft", "running", "observing"})
        complete = tuple(x for x in experiments if x.status.value == "complete")
        inconclusive = tuple(x for x in results if x.verdict.value in {"inconclusive", "insufficient_evidence"})
        breached = tuple(x for x in results if x.kill_conditions_triggered or x.guardrails_breached)
        association = tuple(x for x in results if not x.causal_claim_supported)
        stale = tuple(r.key for r in refs if r.freshness is FreshnessState.STALE)
        attention: list[AttentionItem] = []
        for result in breached:
            key = f"analytics:result:{result.result_id}"
            attention.append(AttentionItem(f"analytics-kill-{result.result_id}", result.experiment_id,
                                           "An experiment kill condition or guardrail was breached.", (key,),
                                           "analytics", AttentionLevel.ACTION_REQUIRED,
                                           "Record the experiment disposition and required follow-up."))
        for result in inconclusive:
            key = f"analytics:result:{result.result_id}"
            attention.append(AttentionItem(f"analytics-inconclusive-{result.result_id}", result.experiment_id,
                                           f"Experiment result is {result.verdict.value}.", (key,),
                                           "analytics", AttentionLevel.WATCH,
                                           "Collect the named missing evidence or close the hypothesis."))
        dimensions = (
            ExecutiveDimension("active_experiments", len(active), source_refs=_keys(refs, "experiment", {x.experiment_id for x in active})),
            ExecutiveDimension("completed_experiments", len(complete), source_refs=_keys(refs, "experiment", {x.experiment_id for x in complete})),
            ExecutiveDimension("inconclusive_results", len(inconclusive), source_refs=_keys(refs, "result", {x.result_id for x in inconclusive})),
            ExecutiveDimension("kill_condition_breaches", len(breached), source_refs=_keys(refs, "result", {x.result_id for x in breached})),
            ExecutiveDimension("postmortems", len(records.get("postmortem", ())), source_refs=_keys(refs, "postmortem")),
            ExecutiveDimension("durable_learnings", len(records.get("learning", ())), source_refs=_keys(refs, "learning")),
            ExecutiveDimension("open_hypotheses", sum(x.state.value in {"proposed", "testing"} for x in records.get("hypothesis", ())), source_refs=_keys(refs, "hypothesis")),
            ExecutiveDimension("association_only_results", len(association), source_refs=_keys(refs, "result", {x.result_id for x in association}),
                               note="These results explicitly do not establish causation."),
        )
        return _Result(ExecutiveSection("analytics", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{len(active)} active experiment(s); {len(inconclusive)} inconclusive result(s).",
                                        dimensions, tuple(r.key for r in refs), (), stale,
                                        tuple(sorted(set(issues)))), tuple(refs), attention=tuple(attention), records=records)

    def finance(self) -> _Result:
        store = FinanceStore(self.paths.finance)
        kinds = ("period", "cost", "cost_adjustment", "revenue", "rate", "labour_rate",
                 "resource_cost_mapping", "budget", "reusable_investment", "reuse_event",
                 "spend_proposal", "spend_decision", "financial_recommendation")
        dirs = {"period":"periods", "cost":"costs", "cost_adjustment":"cost_adjustments", "revenue":"revenue",
                "rate":"rates", "labour_rate":"labour_rates", "resource_cost_mapping":"resource_cost_mappings",
                "budget":"budgets", "reusable_investment":"reusable_investments", "reuse_event":"reuse_events",
                "spend_proposal":"spend_proposals", "spend_decision":"spend_decisions",
                "financial_recommendation":"financial_recommendations"}
        records, refs, issues = self._store_records(store, SourceSubsystem.FINANCE, kinds, dirs)
        if not refs and not issues:
            return self.missing("finance", "finance:no_records; cost, revenue, and contribution are unknown")
        try:
            issues.extend(finance_integrity(
                costs=records.get("cost", ()), adjustments=records.get("cost_adjustment", ()),
                revenue=records.get("revenue", ()), rates=records.get("rate", ()),
                budgets=records.get("budget", ()), mappings=records.get("resource_cost_mapping", ()),
                investments=records.get("reusable_investment", ()), reuse_events=records.get("reuse_event", ()),
                proposals=records.get("spend_proposal", ()), decisions=records.get("spend_decision", ()),
                permissions=self.config.permissions))
        except Exception as exc:
            issues.append(f"finance integrity unavailable: {exc}")
        costs = records.get("cost", ())
        revenue = records.get("revenue", ())
        known_cost = _money_totals((x.amount for x in costs)) if costs else None
        known_revenue = _money_totals((x.amount for x in revenue)) if revenue else None
        open_proposals = tuple(x for x in records.get("spend_proposal", ()) if x.status.value in {"proposed", "under_review"})
        ceo_proposals = tuple(x for x in open_proposals if x.requires_ceo_approval)
        decisions: list[CEODecisionItem] = []
        for proposal in ceo_proposals:
            key = f"finance:spend_proposal:{proposal.proposal_id}"
            decisions.append(CEODecisionItem(proposal.proposal_id, "spend_proposal", SourceSubsystem.FINANCE,
                                             proposal.service, "The canonical spend proposal requires CEO approval.",
                                             (key,), str(proposal.estimated_amount), "medium",
                                             "reversible_with_cost" if proposal.is_recurring else "reversible",
                                             None, proposal.status.value, proposal.reserved_actions,
                                             created_on=proposal.proposed_on))
        missing = []
        if not costs:
            missing.append("no cost records supplied; cost is unknown, not zero")
        if not revenue:
            missing.append("no revenue records supplied; revenue is unknown, not zero")
        missing.append("financial completeness is not asserted; contribution remains unknown")
        attention: list[AttentionItem] = []
        for proposal in ceo_proposals:
            key = f"finance:spend_proposal:{proposal.proposal_id}"
            attention.append(AttentionItem(f"finance-decision-{proposal.proposal_id}", proposal.service,
                                           "Open spend proposal requires CEO approval.", (key,), "finance",
                                           AttentionLevel.ACTION_REQUIRED, "A canonical spend decision is recorded by the required authority."))
        dimensions = (
            ExecutiveDimension("known_cost", known_cost, known=known_cost is not None, unit="currency amounts",
                               source_refs=_keys(refs, "cost"), note="Recorded cost only; no unrecorded amount is inferred."),
            ExecutiveDimension("known_revenue", known_revenue, known=known_revenue is not None, unit="currency amounts",
                               source_refs=_keys(refs, "revenue"), note="Recorded revenue only."),
            ExecutiveDimension("known_contribution", None, known=False,
                               source_refs=tuple((*_keys(refs, "cost"), *_keys(refs, "revenue"))),
                               note="Unknown because completeness is not asserted by supplied records."),
            ExecutiveDimension("open_spend_proposals", len(open_proposals), source_refs=_keys(refs, "spend_proposal", {x.proposal_id for x in open_proposals})),
            ExecutiveDimension("budget_warnings", None, known=False, source_refs=_keys(refs, "budget"),
                               note="Budget consumption cannot be called under/over without an explicit completeness assertion."),
            ExecutiveDimension("reusable_investments", len(records.get("reusable_investment", ())), source_refs=_keys(refs, "reusable_investment")),
            ExecutiveDimension("cost_per_accepted_deliverable", None, known=False,
                               note="Unknown unless Finance supplies complete attributed cost and accepted-deliverable evidence."),
        )
        return _Result(ExecutiveSection("finance", Availability.PARTIAL if missing or issues else Availability.AVAILABLE,
                                        f"{len(costs)} cost and {len(revenue)} revenue record(s); contribution unknown.",
                                        dimensions, tuple(r.key for r in refs), tuple(missing), (),
                                        tuple(sorted(set(issues)))), tuple(refs), tuple(decisions), tuple(attention), records)

    def workforce(self) -> _Result:
        store = WorkforceStore(self.paths.workforce)
        kinds = ("gap", "proposal", "role", "evaluation", "employment", "shadow_assignment", "shadow_comparison", "debt")
        dirs = {"gap":"gaps", "proposal":"proposals", "role":"role_specifications", "evaluation":"evaluations",
                "employment":"employment", "shadow_assignment":"shadow_assignments", "shadow_comparison":"shadow_comparisons",
                "debt":"organizational_debt"}
        records, refs, issues = self._store_records(store, SourceSubsystem.WORKFORCE, kinds, dirs)
        registry = CapabilityRegistry.load(self.config.org_registry, self.repo_root / "company/workforce/capability_registry.json")
        # Canonical org registry is always a workforce source, even with no derived state records.
        org_path = self.repo_root / "company/org_registry.yaml"
        org_ref = self.ref(SourceSubsystem.WORKFORCE, "org_registry", "company-workforce", org_path, self.config.org_registry)
        refs.append(org_ref)
        try:
            issues.extend(workforce_integrity(registry, permissions=self.config.permissions,
                                               role_specifications=records.get("role", ()),
                                               employment_records=records.get("employment", ()),
                                               evaluations=records.get("evaluation", ()),
                                               shadow_assignments=records.get("shadow_assignment", ())))
        except Exception as exc:
            issues.append(f"workforce integrity unavailable: {exc}")
        states = defaultdict(int)
        for employee_id in registry.employee_ids:
            states[registry.employee_state(employee_id)] += 1
        gaps = tuple(x for x in records.get("gap", ()) if x.status.value in {"open", "proposed"})
        proposals = tuple(x for x in records.get("proposal", ()) if x.approval.value in {"proposed", "under_review"} and x.is_action)
        ceo = tuple(x for x in proposals if x.requires_ceo_approval)
        critical = tuple(x for x in registry.resolved() if x.capability.criticality is Criticality.CORE and len(x.active_providers) <= 1)
        executive_action = "hire_or_remove_executive_role"
        reserved = set(self.config.permissions.get("ceo_reserved", ()) or ())
        decisions = tuple(CEODecisionItem(x.proposal_id, "workforce_proposal", SourceSubsystem.WORKFORCE,
                                          x.recommendation.value, "The workforce proposal requires CEO approval.",
                                          (f"workforce:proposal:{x.proposal_id}",), None, "high" if "archive" in x.recommendation.value else "medium",
                                          "reversible_with_cost", None, x.approval.value,
                                          (executive_action,) if executive_action in reserved else (),
                                          created_on=x.proposed_on) for x in ceo)
        attention = tuple(AttentionItem(f"workforce-gap-{x.gap_id}", x.gap_id,
                                        "An unresolved capability gap is recorded.",
                                        (f"workforce:gap:{x.gap_id}",), "workforce",
                                        AttentionLevel.ACTION_REQUIRED if x.urgency.value in {"high", "critical"} else AttentionLevel.WATCH,
                                        "The canonical gap moves to mitigated, resolved, or withdrawn with evidence.") for x in gaps)
        dimensions = (
            ExecutiveDimension("active_employees", states["active"], source_refs=(org_ref.key,)),
            ExecutiveDimension("dormant_employees", states["dormant"], source_refs=(org_ref.key,)),
            ExecutiveDimension("restricted_employees", sum(states[x] for x in ("candidate", "shadow", "probation")), source_refs=(org_ref.key,)),
            ExecutiveDimension("candidate_employees", states["candidate"], source_refs=(org_ref.key,)),
            ExecutiveDimension("shadow_employees", states["shadow"], source_refs=(org_ref.key,)),
            ExecutiveDimension("probation_employees", states["probation"], source_refs=(org_ref.key,)),
            ExecutiveDimension("capability_gaps", len(gaps), source_refs=_keys(refs, "gap", {x.gap_id for x in gaps})),
            ExecutiveDimension("critical_single_points_of_failure", len(critical), source_refs=(org_ref.key,),
                               note="Core capabilities with zero or one active provider; dormant and restricted providers are not active capacity."),
            ExecutiveDimension("unresolved_workforce_proposals", len(proposals), source_refs=_keys(refs, "proposal", {x.proposal_id for x in proposals})),
        )
        return _Result(ExecutiveSection("workforce", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{states['active']} active, {states['dormant']} dormant, and {sum(states[x] for x in ('candidate','shadow','probation'))} restricted employee(s).",
                                        dimensions, tuple(r.key for r in refs), (), (), tuple(sorted(set(issues)))),
                       tuple(refs), decisions, attention, records)

    def organization(self) -> _Result:
        store = OrgIntelligenceStore(self.paths.organization)
        kinds = ("review", "signal", "finding", "recommendation", "change_proposal", "experiment", "change_review")
        dirs = {"review":"reviews", "signal":"signals", "finding":"findings", "recommendation":"recommendations",
                "change_proposal":"change_proposals", "experiment":"experiments", "change_review":"change_reviews"}
        records, refs, issues = self._store_records(store, SourceSubsystem.ORGANIZATION, kinds, dirs)
        if not refs and not issues:
            return self.missing("organization", "organization:no_records")
        try:
            issues.extend(organization_integrity(org_registry=self.config.org_registry, permissions=self.config.permissions,
                reviews=records.get("review", ()), signals=records.get("signal", ()), findings=records.get("finding", ()),
                recommendations=records.get("recommendation", ()), change_proposals=records.get("change_proposal", ()),
                experiments=records.get("experiment", ()), change_reviews=records.get("change_review", ())))
        except Exception as exc:
            issues.append(f"organization integrity unavailable: {exc}")
        findings = records.get("finding", ())
        recs = records.get("recommendation", ())
        proposals = records.get("change_proposal", ())
        open_findings = tuple(x for x in findings if x.category.value != "structural_fact")
        proposed = tuple(x for x in (*recs, *proposals) if x.state.value in {"proposed", "under_review"})
        approved = tuple(x for x in (*recs, *proposals) if x.state.value == "approved")
        ceo = tuple(x for x in proposed if x.requires_ceo_approval)
        debt_findings = tuple(x for x in findings if x.category.value == "organizational_debt")
        bottlenecks = tuple(x for x in findings if x.category.value in {"management_bottleneck", "approval_bottleneck"})
        decisions: list[CEODecisionItem] = []
        for item in ceo:
            rid = getattr(item, "recommendation_id", getattr(item, "proposal_id", ""))
            kind = "recommendation" if hasattr(item, "recommendation_id") else "change_proposal"
            subject = ", ".join(getattr(item, "subjects", ()) or getattr(item, "affected_subjects", ())) or rid
            decisions.append(CEODecisionItem(rid, kind, SourceSubsystem.ORGANIZATION, subject,
                                             "The organizational record preserves an existing CEO approval requirement.",
                                             (f"organization:{kind}:{rid}",), getattr(item, "expected_implementation_cost", None),
                                             getattr(getattr(item, "risk", None), "value", "unknown"),
                                             item.reversibility.value, None, item.state.value,
                                             item.reserved_actions, blocked=False))
        dimensions = (
            ExecutiveDimension("open_findings", len(open_findings), source_refs=_keys(refs, "finding", {x.finding_id for x in open_findings})),
            ExecutiveDimension("proposed_changes", len(proposed), source_refs=tuple(f"organization:{'recommendation' if hasattr(x,'recommendation_id') else 'change_proposal'}:{getattr(x,'recommendation_id',getattr(x,'proposal_id',''))}" for x in proposed)),
            ExecutiveDimension("approved_awaiting_implementation", len(approved), source_refs=tuple(f"organization:{'recommendation' if hasattr(x,'recommendation_id') else 'change_proposal'}:{getattr(x,'recommendation_id',getattr(x,'proposal_id',''))}" for x in approved)),
            ExecutiveDimension("organizational_debt_findings", len(debt_findings), source_refs=_keys(refs, "finding", {x.finding_id for x in debt_findings})),
            ExecutiveDimension("management_or_approval_bottlenecks", len(bottlenecks), source_refs=_keys(refs, "finding", {x.finding_id for x in bottlenecks})),
            ExecutiveDimension("recommendations_requiring_ceo", len(ceo), source_refs=tuple(x.evidence_refs[0] for x in decisions)),
        )
        return _Result(ExecutiveSection("organization", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{len(open_findings)} open finding(s) and {len(ceo)} CEO-gated recommendation(s).",
                                        dimensions, tuple(r.key for r in refs), (), (), tuple(sorted(set(issues)))),
                       tuple(refs), tuple(decisions), records=records)

    def system(self) -> _Result:
        seed_root = self.repo_root / "knowledge/company_os/capsules/seeds"
        index = CapsuleIndex.load(seed_root)
        capsule_refs = tuple(self.ref(SourceSubsystem.SYSTEM, "capsule", capsule.id,
                                      seed_root / f"{capsule.id}.json", capsule) for capsule in index.all())
        permission_ref = self.ref(SourceSubsystem.SYSTEM, "permissions", "company-permissions",
                                  self.repo_root / "company/permissions.yaml", self.config.permissions)
        refs = (*capsule_refs, permission_ref)
        issues = list(index.integrity(repo_root=self.repo_root))
        issues.extend(f"capsule dependency cycle: {' -> '.join(cycle)}" for cycle in _dependency_cycles(index))
        stale = index.staleness(self.as_of)
        control = index.get("company-os-control-plane") if "company-os-control-plane" in index else None
        if control is not None and len(control.dependencies) > 8:
            issues.append(f"company-os-control-plane has {len(control.dependencies)} direct dependencies; maximum is 8")
        if control is not None:
            unreachable = sorted(set(index.ids()) - {control.id} - set(index.dependency_closure(control.id)))
            if unreachable:
                issues.append("capsules unreachable from control plane: " + ", ".join(unreachable))
        no_subagents = self.config.permissions.get("bootstrap_defaults", {}).get("no_subagents") is True and \
            self.config.org_registry.get("global_constraints", {}).get("no_subagents") is True
        if not no_subagents:
            issues.append("no-subagent invariant is not true in both canonical configuration sources")
        dims = (
            ExecutiveDimension("capsules", len(index), source_refs=tuple(r.key for r in refs)),
            ExecutiveDimension("stale_capsules", len(stale), source_refs=tuple(f"system:capsule:{x.capsule_id}" for x in stale)),
            ExecutiveDimension("capsule_integrity_issues", len(issues), source_refs=tuple(r.key for r in refs)),
            ExecutiveDimension("control_plane_direct_dependencies", len(control.dependencies) if control else None,
                               known=control is not None, source_refs=("system:capsule:company-os-control-plane",) if control else ()),
            ExecutiveDimension("no_subagent_invariant", no_subagents,
                               source_refs=(("system:capsule:company-os-control-plane", permission_ref.key,
                                             "workforce:org_registry:company-workforce") if control else (permission_ref.key,))),
        )
        attention = () if not issues else (AttentionItem("system-integrity", "Company OS",
            f"{len(issues)} capsule/config integrity issue(s) remain.", (refs[0].key,), "integrity",
            AttentionLevel.BLOCKED, "Repair the canonical capsule/config records and rerun integrity."),)
        return _Result(ExecutiveSection("system", Availability.PARTIAL if issues else Availability.AVAILABLE,
                                        f"{len(index)} capsule(s); {len(stale)} stale and {len(issues)} integrity issue(s).",
                                        dims, tuple(r.key for r in refs), (), tuple(f"system:capsule:{x.capsule_id}" for x in stale),
                                        tuple(sorted(set(issues)))), refs, attention=attention)

    def _store_records(self, store: Any, subsystem: SourceSubsystem, kinds: Iterable[str],
                       directories: Mapping[str, str]) -> tuple[dict[str, tuple[Any, ...]], list[SourceReference], list[str]]:
        records: dict[str, tuple[Any, ...]] = {}
        refs: list[SourceReference] = []
        issues: list[str] = []
        root = Path(store.state_dir)
        for kind in kinds:
            try:
                rows = store.list(kind)
                records[kind] = rows
                for record in rows:
                    rid = _record_id(record)
                    refs.append(self.ref(subsystem, kind, rid, root / directories[kind] / f"{rid}.json", record))
            except Exception as exc:
                issues.append(f"{subsystem.value} {kind}: {exc}")
        return records, refs, issues


def build_snapshot(state_dir: str | Path | None = None, *, sources: CompanyStatePaths | None = None,
                   as_of: dt.date | None = None, repo_root: str | Path | None = None) -> CompanyStateSnapshot:
    """Build a pure read model.  No canonical store is written or mutated."""
    if sources is None:
        if state_dir is None:
            raise ValueError("state_dir or sources is required")
        sources = CompanyStatePaths.from_root(state_dir)
    day = as_of or dt.date.today()
    repository = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[2]
    reader = _Reader(sources, day, repository)
    results = (reader.execution(), reader.research(), reader.analytics(), reader.finance(),
               reader.workforce(), reader.organization(), reader.system())
    results = _with_resource_finance(results)
    refs = tuple(ref for result in results for ref in result.refs)
    missing = tuple(item for result in results for item in result.section.missing)
    stale = tuple(ref.key for ref in refs if ref.freshness is FreshnessState.STALE)
    integrity = tuple(f"{result.section.name}: {issue}" for result in results for issue in result.section.integrity_issues)
    formats = _format_views(results)
    projects = _project_views(results)
    snapshot = CompanyStateSnapshot("pending", day, day, refs, tuple(x.section for x in results),
                                    missing, stale, integrity,
                                    tuple(x for r in results for x in r.decisions),
                                    tuple(x for r in results for x in r.attention), formats, projects)
    from .integrity import check_integrity
    dashboard_issues = check_integrity(snapshot)
    if dashboard_issues:
        snapshot = replace(snapshot, unresolved_integrity_issues=tuple(sorted(set(integrity) | set(dashboard_issues))))
    payload = snapshot.to_dict()
    payload.pop("snapshot_id", None)
    return replace(snapshot, snapshot_id=make_snapshot_id(payload))


def _format_views(results: tuple[_Result, ...]) -> tuple[FormatView, ...]:
    analytics = next((r for r in results if r.section.name == "analytics"), None)
    finance = next((r for r in results if r.section.name == "finance"), None)
    if not analytics or not analytics.records:
        return ()
    data = analytics.records
    deliverables = data.get("deliverable", ())
    formats = sorted({x.format_id for x in deliverables if x.format_id})
    output = []
    for format_id in formats:
        own = tuple(x for x in deliverables if x.format_id == format_id)
        experiment_ids = {x.experiment_id for x in own if x.experiment_id}
        learnings = tuple(x for x in data.get("learning", ()) if format_id in x.applies_to)
        hypotheses = tuple(x for x in data.get("hypothesis", ()) if x.state.value in {"proposed", "testing"}
                           and (not x.experiment_ids or experiment_ids.intersection(x.experiment_ids)))
        costs = tuple(x.amount for x in (finance.records.get("cost", ()) if finance and finance.records else ())
                      if x.subject.kind.value == "format" and x.subject.id == format_id)
        revenue = tuple(x.amount for x in (finance.records.get("revenue", ()) if finance and finance.records else ())
                        if x.subject.kind.value == "format" and x.subject.id == format_id)
        output.append(FormatView(format_id, len(own), len(experiment_ids),
                                 tuple(f"analytics:learning:{x.learning_id}" for x in learnings),
                                 ", ".join(_money_totals(costs)) if costs else None,
                                 ", ".join(_money_totals(revenue)) if revenue else None,
                                 tuple(f"analytics:hypothesis:{x.hypothesis_id}" for x in hypotheses)))
    return tuple(output)


def _with_resource_finance(results: tuple[_Result, ...]) -> tuple[_Result, ...]:
    execution = next((r for r in results if r.section.name == "execution"), None)
    finance = next((r for r in results if r.section.name == "finance"), None)
    if execution is None or execution.section.availability is Availability.MISSING:
        return results
    costs = tuple(x for x in (finance.records.get("cost", ()) if finance and finance.records else ())
                  if x.resource_ref)
    dimension = ExecutiveDimension(
        "resource_monetary_cost",
        _money_totals(x.amount for x in costs) if costs else None,
        known=bool(costs), unit="currency amounts",
        source_refs=tuple(f"finance:cost:{x.cost_id}" for x in costs),
        note="Only Finance cost records already linked to a resource are included; provider pricing is not recomputed here.",
    )
    execution.section = replace(execution.section,
                                dimensions=(*execution.section.dimensions, dimension))
    return results


def _project_views(results: tuple[_Result, ...]) -> tuple[ProjectView, ...]:
    execution = next((r for r in results if r.section.name == "execution"), None)
    finance = next((r for r in results if r.section.name == "finance"), None)
    packets = execution.records.get("packet", ()) if execution and execution.records else ()
    receipts = execution.records.get("receipt", ()) if execution and execution.records else ()
    finance_costs = finance.records.get("cost", ()) if finance and finance.records else ()
    ids = sorted({getattr(x, "project", "") for x in packets if getattr(x, "project", "")} |
                 {x.subject.id for x in finance_costs if x.subject.kind.value == "project"})
    output = []
    for project_id in ids:
        own_packets = tuple(x for x in packets if getattr(x, "project", "") == project_id)
        own_tasks = {x.task_id for x in own_packets}
        own_receipts = tuple(x for x in receipts if x.task_id in own_tasks)
        active = tuple(f"execution:packet:{x.task_id}" for x in own_packets
                       if not any(r.task_id == x.task_id and r.packet_fingerprint == x.fingerprint() for r in own_receipts))
        accepted = tuple(x for x in own_receipts if x.outcome is Outcome.ACCEPTED)
        project_costs = tuple(x.amount for x in finance_costs
                              if x.subject.kind.value == "project" and x.subject.id == project_id)
        output.append(ProjectView(project_id, active,
                                  f"execution:receipt:{accepted[-1].task_id}" if accepted else None,
                                  ", ".join(_money_totals(project_costs)) if project_costs else None))
    return tuple(output)


def _record_id(record: Any) -> str:
    for name in ("period_id", "cost_id", "adjustment_id", "revenue_id", "rate_id", "mapping_id",
                 "budget_id", "investment_id", "event_id", "proposal_id", "decision_id", "recommendation_id",
                 "deliverable_id", "observation_id", "name", "experiment_id", "result_id", "postmortem_id",
                 "learning_id", "hypothesis_id", "baseline_id", "gap_id", "role_id", "evaluation_id",
                 "employee_id", "assignment_id", "comparison_id", "debt_id", "review_id", "signal_id", "finding_id"):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"cannot identify {type(record).__name__}")


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and value:
        return dt.date.fromisoformat(value)
    return None


def _keys(refs: Iterable[SourceReference], kind: str, ids: set[str] | None = None) -> tuple[str, ...]:
    return tuple(ref.key for ref in refs if ref.kind == kind and (ids is None or ref.record_id in ids))


def _dim(name: str, value: int, rows: Iterable[tuple[Any, SourceReference]]) -> ExecutiveDimension:
    return ExecutiveDimension(name, value, source_refs=tuple(ref.key for _record, ref in rows))


def _money_totals(values: Iterable[Any]) -> tuple[str, ...]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for value in values:
        totals[value.currency] += value.amount
    return tuple(f"{format(amount, 'f')} {currency}" for currency, amount in sorted(totals.items()))


def _dependency_cycles(index: CapsuleIndex) -> tuple[tuple[str, ...], ...]:
    graph = {capsule.id: capsule.dependencies for capsule in index.all()}
    found: set[tuple[str, ...]] = set()
    for start in sorted(graph):
        stack: list[tuple[str, tuple[str, ...]]] = [(start, ())]
        while stack:
            current, path = stack.pop()
            if current in path:
                cycle = path[path.index(current):] + (current,)
                body = cycle[:-1]
                pivot = body.index(min(body))
                normal = body[pivot:] + body[:pivot]
                found.add(normal + (normal[0],))
                continue
            if current not in graph:
                continue
            for dependency in reversed(sorted(graph[current])):
                stack.append((dependency, path + (current,)))
    return tuple(sorted(found))
