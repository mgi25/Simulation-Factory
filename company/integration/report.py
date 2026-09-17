"""Assembling one readiness report, and turning required failures into blockers.

## One blocker per unsatisfied required check, and no others

A blocker is not a second opinion about a check - it is the same finding with
an owner and a remediation attached, so the list can be worked through. Both
a required `fail` and a required `unknown` produce one: a condition nobody has
evidence for is as much a reason not to cross the boundary as a condition that
is known to be broken, and giving the unknown a blocker is what stops it
drifting out of view.

Advisory checks never produce blockers. They stay visible through
`advisory_findings()`, which is the whole difference between the two classes.

## Why the report is dated by day and not by clock

`as_of` is a date the caller supplies, defaulting to today. Two runs on the
same day over an unchanged tree produce byte-identical canonical JSON and the
same `report_id`, which is what lets the store be append-only without refusing
an honest re-run. A wall-clock timestamp would make every run a new document
and every re-run a conflict.

Freshness is still answerable at that granularity: each check carries the date
of the evidence behind it, supplied suite results carry their own run date and
go stale after a window, and `stale_against` compares the report's source
commit with the tree a reader is holding.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from company.runtime.git_evidence import read_ref

from .checks import GateInputs, GateScan, evaluate
from .model import (
    EvidenceSource,
    GateCategory,
    GateCheck,
    GateSection,
    GateStatus,
    IntegrationBlocker,
    ProductionIntegrationReadinessReport,
    Readiness,
)
from .policy import DEFAULT_POLICY, GatePolicy
from .suites import SuiteEvidence


# Restoring these conditions is not an engineering task. Each one is a
# declaration `permissions.yaml` or the constitution reserves to the CEO, so a
# blocker on one is raised to them rather than assigned to a workstream.
CEO_DECISION_CHECKS: frozenset[str] = frozenset(
    {
        "execution.no_subagent_runtime_lock",
        "production.integration_remains_disabled",
        "workforce.ceo_reserved_actions_present",
        "finance.recurring_paid_api_spend_reserved",
    }
)

# What the report says about itself, every time, so that a READY verdict read
# out of context still carries its own limit.
AUTHORIZATION_NOTE = (
    "This report states whether the technical gate conditions are satisfied. It does "
    "not authorize production integration: wiring Company OS into production is a "
    "separate CEO decision (permissions.yaml, merge_major_architecture_rewrite)."
)


def build_report(
    repo_root: Path | str,
    *,
    as_of: dt.date | None = None,
    suites: SuiteEvidence | None = None,
    state_dir: Path | str | None = None,
    capsule_root: Path | str | None = None,
    policy: GatePolicy = DEFAULT_POLICY,
    scan: GateScan | None = None,
) -> ProductionIntegrationReadinessReport:
    """Run every condition over `repo_root` and assemble the report.

    `scan` lets a caller that already parsed this checkout reuse it; see
    `GateInputs.scan` for why that changes no verdict.
    """
    root = Path(repo_root).resolve()
    inputs = GateInputs(
        repo_root=root,
        as_of=as_of or dt.date.today(),
        suites=suites or SuiteEvidence(),
        state_dir=Path(state_dir).resolve() if state_dir is not None else None,
        capsule_root=Path(capsule_root).resolve() if capsule_root is not None else None,
        scan=scan,
    )
    checks = tuple(policy.coerce(check) for check in evaluate(inputs))
    policy.assert_covers(check.check_id for check in checks)
    return assemble(checks, inputs=inputs, policy=policy)


def assemble(
    checks: tuple[GateCheck, ...],
    *,
    inputs: GateInputs,
    policy: GatePolicy = DEFAULT_POLICY,
) -> ProductionIntegrationReadinessReport:
    """Turn a set of checks into a report. Kept separate so tests can drive it."""
    sections = tuple(
        GateSection(category, tuple(c for c in checks if c.category is category))
        for category in GateCategory
        if any(c.category is category for c in checks)
    )
    return ProductionIntegrationReadinessReport(
        as_of=inputs.as_of,
        source=_source(inputs),
        policy_version=policy.version,
        sections=sections,
        blockers=blockers_for(checks, policy),
        required_check_ids=tuple(c.check_id for c in checks if policy.is_required(c.check_id)),
        advisory_check_ids=tuple(
            c.check_id for c in checks if not policy.is_required(c.check_id)
        ),
        notes=(AUTHORIZATION_NOTE,),
    )


def blockers_for(
    checks: tuple[GateCheck, ...], policy: GatePolicy = DEFAULT_POLICY
) -> tuple[IntegrationBlocker, ...]:
    """One blocker per required check that is neither pass nor not-applicable."""
    out: list[IntegrationBlocker] = []
    for check in checks:
        if not policy.is_required(check.check_id) or check.satisfied:
            continue
        out.append(
            IntegrationBlocker(
                blocker_id=f"blocker-{check.check_id}",
                check_id=check.check_id,
                category=check.category,
                reason=_reason(check),
                remediation=check.remediation,
                evidence=check.evidence,
                owner=_owner(check),
                ceo_decision_required=check.check_id in CEO_DECISION_CHECKS,
            )
        )
    return tuple(out)


def _reason(check: GateCheck) -> str:
    if check.status is GateStatus.FAIL:
        return check.blocker_reason
    return (
        "required evidence could not be established: "
        + "; ".join(check.missing_evidence[:3])
    )


def _owner(check: GateCheck) -> str:
    """The workstream already working on this, where the gate can tell.

    Only one mapping is known at the time of writing, and it is derived from
    the finding rather than asserted: a declared cycle between the runtime and
    validation capsules is the edge `company-os-v1-runtime-validation-decouple`
    exists to remove. Everything else is left unassigned rather than guessed.
    """
    if check.check_id == "architecture.capsule_graph_acyclic":
        detail = check.detail
        if "company-runtime" in detail and "company-validation" in detail:
            return "company-os-v1-runtime-validation-decouple"
    return ""


def _source(inputs: GateInputs) -> EvidenceSource:
    commit, branch = _head(inputs.repo_root)
    return EvidenceSource(
        repo_root=str(inputs.repo_root),
        source_commit=commit,
        source_branch=branch,
        state_dir=str(inputs.state_dir) if inputs.state_dir is not None else "",
    )


def _head(repo_root: Path) -> tuple[str, str]:
    """The commit and branch this report describes, read from refs without git.

    `company.runtime.git_evidence` already reads `.git` directly - no
    subprocess, no `git` on PATH - which is the only way this package can date
    a report while holding no process-spawn authority.
    """
    try:
        commit = read_ref(repo_root, "HEAD")
    except Exception:  # noqa: BLE001 - a checkout without .git still gets a report
        return "", ""
    branch = ""
    try:
        from company.runtime.git_evidence import git_dir

        pointer = (git_dir(repo_root) / "HEAD").read_text(encoding="utf-8").strip()
        if pointer.startswith("ref: refs/heads/"):
            branch = pointer.removeprefix("ref: refs/heads/")
    except Exception:  # noqa: BLE001
        branch = ""
    return commit, branch


# -- rendering --------------------------------------------------------------

_STATUS_MARK = {
    GateStatus.PASS: "PASS",
    GateStatus.FAIL: "FAIL",
    GateStatus.UNKNOWN: "UNKNOWN",
    GateStatus.NOT_APPLICABLE: "N/A",
}


def render_text(
    report: ProductionIntegrationReadinessReport, *, verbose: bool = False
) -> str:
    """The report as text: the verdict, then what stands between it and READY."""
    lines: list[str] = []
    lines.append(f"PRODUCTION INTEGRATION READINESS: {report.readiness.value.upper()}")
    lines.append(f"report      {report.report_id}")
    lines.append(f"as of       {report.as_of.isoformat()}")
    lines.append(
        f"source      {report.source.source_branch or '(detached)'} "
        f"{report.source.source_commit or '(no commit recorded)'}"
    )
    lines.append(
        f"policy      v{report.policy_version}: "
        f"{len(report.required_check_ids)} required, "
        f"{len(report.advisory_check_ids)} advisory"
    )
    lines.append("")

    counts = {status: 0 for status in GateStatus}
    for check in report.checks():
        counts[check.status] += 1
    lines.append(
        "checks      "
        + ", ".join(f"{counts[status]} {status.value}" for status in GateStatus)
    )
    lines.append("")

    open_blockers = report.open_blockers()
    if open_blockers:
        lines.append(f"BLOCKERS ({len(open_blockers)})")
        for blocker in open_blockers:
            mark = " [CEO]" if blocker.ceo_decision_required else ""
            owner = f" [{blocker.owner}]" if blocker.owner else ""
            lines.append(f"  {blocker.check_id}{mark}{owner}")
            lines.append(f"    why  {blocker.reason}")
            lines.append(f"    fix  {blocker.remediation}")
        lines.append("")
    else:
        lines.append("BLOCKERS    none")
        lines.append("")

    advisory = report.advisory_findings()
    if advisory:
        lines.append(f"ADVISORY ({len(advisory)}, not blocking)")
        for check in advisory:
            lines.append(f"  {_STATUS_MARK[check.status]:8s} {check.check_id}")
            lines.append(f"    {check.detail}")
        lines.append("")

    unknowns = report.unknowns()
    if unknowns:
        lines.append(f"UNKNOWNS ({len(unknowns)})")
        for check in unknowns:
            classification = "required" if check.check_id in report.required_check_ids else "advisory"
            lines.append(f"  {check.check_id} ({classification})")
            for item in check.missing_evidence[:3]:
                lines.append(f"    missing  {item}")
        lines.append("")

    for section in report.sections:
        lines.append(section.category.value.upper())
        for check in section.checks:
            classification = "required" if check.check_id in report.required_check_ids else "advisory"
            lines.append(
                f"  {_STATUS_MARK[check.status]:8s} {check.check_id} ({classification})"
            )
            if verbose or check.status is not GateStatus.PASS:
                lines.append(f"    {check.detail}")
        lines.append("")

    lines.append(AUTHORIZATION_NOTE)
    return "\n".join(lines) + "\n"


__all__ = [
    "AUTHORIZATION_NOTE",
    "CEO_DECISION_CHECKS",
    "Readiness",
    "assemble",
    "blockers_for",
    "build_report",
    "render_text",
]
