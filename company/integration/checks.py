"""The conditions themselves: one function per check, one verdict each.

Every check returns a `GateCheck` on every run. There is no path through this
module that produces fewer checks than the policy classifies - `GatePolicy.
assert_covers` fails the run if there is - because a condition that silently
stops being evaluated is the failure mode a gate is built to prevent.

## The three shapes a check takes

`_from_findings` turns a list of located violations into a verdict: empty is a
pass, non-empty is a fail whose blocker reason names the first few files and
the count. `_from_probe` turns a behavioural probe into a verdict, with the
probe's own failure to run becoming `unknown` rather than anything else.
`_from_drift` does the same for a contract comparison. Anything that does not
fit one of the three is written out, and there are only a handful.

## Why the expensive work happens once

`GateScan` parses the production tree and the Company OS tree exactly once and
hands the trees to every check that needs them. Nine of the conditions are
questions about the same syntax trees, and parsing them nine times would make
the gate slow enough that people stop running it, which is its own kind of
failure.
"""

from __future__ import annotations

import ast
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from knowledge.company_os.capsules import CapsuleIndex, path_related, normalise_path

from . import probes
from .boundary import (
    MODEL_MODULES,
    NETWORK_MODULES,
    Finding,
    delete_call_violations,
    forbidden_import_violations,
    non_first_party_imports,
    process_spawn_violations,
    production_import_violations,
    production_write_violations,
)
from .contracts import (
    ContractDrift,
    integration_still_gated,
    no_subagent_chain,
    reserved_action_drift,
    review_trigger_drift,
)
from .graph import (
    capsule_dependency_graph,
    find_cycles,
    render_cycle,
    subsystem_import_graph,
    type_checking_edges,
)
from .model import EvidenceKind, GateCategory, GateCheck, GateStatus
from .probes import ProbeResult
from .sources import (
    COMPANY_OS_ROOTS,
    COMPANY_OS_TEST_PREFIX,
    TEST_ROOT,
    SourceModule,
    absent_production_roots,
    company_os_roots,
    parse_tree,
    production_files,
    production_roots,
)
from .suites import REQUIRED_SUITES, SuiteEvidence

# Callables the executive read model must not expose. A dashboard that can
# approve is not a view of the company, it is a second control plane.
_ACTION_VERBS: tuple[str, ...] = (
    "approve",
    "authorise",
    "authorize",
    "deploy",
    "dismiss",
    "fire_",
    "hire",
    "merge",
    "pay_",
    "publish",
    "purchase",
    "spend",
    "upload",
)

_MAX_NAMED_FINDINGS = 5


@dataclass(frozen=True)
class GateScan:
    """Everything read off the checkout, parsed once and shared by every check."""

    repo_root: Path
    production_modules: tuple[SourceModule, ...]
    production_failures: tuple[str, ...]
    company_modules: tuple[SourceModule, ...]
    company_failures: tuple[str, ...]
    test_modules: tuple[SourceModule, ...]
    test_failures: tuple[str, ...]
    scanned_production_roots: tuple[str, ...]
    absent_production_roots: tuple[str, ...]
    scanned_company_roots: tuple[str, ...]

    @classmethod
    def of(cls, repo_root: Path | str) -> "GateScan":
        root = Path(repo_root).resolve()
        prod_roots = production_roots(root)
        prod_files = production_files(root)
        company = company_os_roots(root)
        production, production_bad = parse_tree(root, tuple(prod_roots) + tuple(prod_files))
        company_modules, company_bad = parse_tree(root, company)
        tests, test_bad = parse_tree(root, (TEST_ROOT,))
        return cls(
            repo_root=root,
            production_modules=production,
            production_failures=tuple(f"{f.path}: {f.reason}" for f in production_bad),
            company_modules=company_modules,
            company_failures=tuple(f"{f.path}: {f.reason}" for f in company_bad),
            test_modules=tests,
            test_failures=tuple(f"{f.path}: {f.reason}" for f in test_bad),
            scanned_production_roots=prod_roots,
            absent_production_roots=absent_production_roots(root),
            scanned_company_roots=company,
        )

    def production_test_modules(self) -> tuple[SourceModule, ...]:
        """Test modules that are not named as Company OS suites."""
        return tuple(
            module
            for module in self.test_modules
            if not Path(module.path).name.startswith(COMPANY_OS_TEST_PREFIX)
        )


@dataclass(frozen=True)
class GateInputs:
    """Everything a run is allowed to depend on, supplied by the caller.

    `scan` is an optimisation with a contract: parsing the checkout is most of
    the cost of a run, and a caller evaluating several variations of the same
    tree - a test suite, or a session trying two sets of supplied evidence -
    may parse once and hand the result in. It is a pure function of the
    checkout, so reusing one across runs of the same unchanged tree changes no
    verdict. Left None, every run parses for itself.
    """

    repo_root: Path
    as_of: dt.date
    suites: SuiteEvidence = field(default_factory=SuiteEvidence)
    state_dir: Path | None = None
    capsule_root: Path | None = None
    scan: "GateScan | None" = None


def evaluate(inputs: GateInputs) -> tuple[GateCheck, ...]:
    """Run every condition and return the checks, in check-id order."""
    scan = inputs.scan if inputs.scan is not None else GateScan.of(inputs.repo_root)
    index = _load_capsules(inputs)
    config = _load_config(inputs)
    checks: list[GateCheck] = []
    for builder in _BUILDERS:
        checks.append(builder(inputs, scan, index, config))
    return tuple(sorted(checks, key=lambda check: check.check_id))


def _load_capsules(inputs: GateInputs) -> CapsuleIndex | None:
    try:
        if inputs.capsule_root is not None:
            return CapsuleIndex.load(inputs.capsule_root)
        return CapsuleIndex.load(
            Path(inputs.repo_root) / "knowledge/company_os/capsules/seeds"
        )
    except Exception:  # noqa: BLE001 - a broken store is a finding, not a crash
        return None


def _load_config(inputs: GateInputs):
    from company.runtime.config import load_company_config

    try:
        return load_company_config(Path(inputs.repo_root) / "company")
    except Exception:  # noqa: BLE001
        return None


# -- verdict builders -------------------------------------------------------


def _check(
    check_id: str,
    category: GateCategory,
    status: GateStatus,
    requirement: str,
    detail: str,
    kind: EvidenceKind,
    *,
    evidence: tuple[str, ...] = (),
    blocker_reason: str = "",
    missing_evidence: tuple[str, ...] = (),
    remediation: str = "",
    not_applicable_reason: str = "",
    evidence_as_of: dt.date | None = None,
) -> GateCheck:
    return GateCheck(
        check_id=check_id,
        category=category,
        status=status,
        requirement=requirement,
        detail=detail,
        evidence_kind=kind,
        evidence=evidence,
        blocker_reason=blocker_reason,
        missing_evidence=missing_evidence,
        remediation=remediation,
        not_applicable_reason=not_applicable_reason,
        evidence_as_of=evidence_as_of,
    )


def _from_findings(
    check_id: str,
    category: GateCategory,
    requirement: str,
    findings: tuple[Finding, ...],
    *,
    clean_detail: str,
    remediation: str,
    evidence: tuple[str, ...] = (),
    kind: EvidenceKind = EvidenceKind.REPOSITORY,
    as_of: dt.date | None = None,
) -> GateCheck:
    """A located-violation check: empty is a pass, anything else is a failure."""
    if not findings:
        return _check(
            check_id,
            category,
            GateStatus.PASS,
            requirement,
            clean_detail,
            kind,
            evidence=evidence,
            evidence_as_of=as_of,
        )
    named = findings[:_MAX_NAMED_FINDINGS]
    tail = "" if len(findings) <= _MAX_NAMED_FINDINGS else f", and {len(findings) - len(named)} more"
    return _check(
        check_id,
        category,
        GateStatus.FAIL,
        requirement,
        "; ".join(item.rendered() for item in named) + tail,
        kind,
        evidence=tuple(item.reference() for item in named),
        blocker_reason=f"{len(findings)} violation(s); first is {findings[0].rendered()}",
        remediation=remediation,
        evidence_as_of=as_of,
    )


def _from_probe(
    check_id: str,
    category: GateCategory,
    requirement: str,
    result: ProbeResult,
    *,
    remediation: str,
    as_of: dt.date | None = None,
) -> GateCheck:
    """A behavioural check. A probe that could not run is unknown, never a pass."""
    if not result.ran:
        return _check(
            check_id,
            category,
            GateStatus.UNKNOWN,
            requirement,
            result.detail,
            EvidenceKind.PROBE,
            missing_evidence=(f"the guard could not be exercised: {result.error}",),
            remediation=(
                "Make the subsystem importable and re-run the gate; until the guard "
                "answers, this condition is unproven."
            ),
            evidence_as_of=as_of,
        )
    if result.ok:
        return _check(
            check_id,
            category,
            GateStatus.PASS,
            requirement,
            result.detail,
            EvidenceKind.PROBE,
            evidence=result.evidence,
            evidence_as_of=as_of,
        )
    return _check(
        check_id,
        category,
        GateStatus.FAIL,
        requirement,
        result.detail,
        EvidenceKind.PROBE,
        evidence=result.evidence,
        blocker_reason=result.detail,
        remediation=remediation,
        evidence_as_of=as_of,
    )


def _from_drift(
    check_id: str,
    category: GateCategory,
    requirement: str,
    drift: ContractDrift,
    *,
    clean_detail: str,
    remediation: str,
    as_of: dt.date | None = None,
) -> GateCheck:
    if drift.ok:
        extra = (
            f" ({len(drift.unrecognised)} further entries the gate does not require)"
            if drift.unrecognised
            else ""
        )
        return _check(
            check_id,
            category,
            GateStatus.PASS,
            requirement,
            clean_detail + extra,
            EvidenceKind.CONTRACT,
            evidence=drift.evidence,
            evidence_as_of=as_of,
        )
    return _check(
        check_id,
        category,
        GateStatus.FAIL,
        requirement,
        "; ".join(drift.missing),
        EvidenceKind.CONTRACT,
        evidence=drift.evidence,
        blocker_reason=drift.missing[0],
        remediation=remediation,
        evidence_as_of=as_of,
    )


def _capsules_unavailable(
    check_id: str, category: GateCategory, requirement: str, as_of: dt.date
) -> GateCheck:
    return _check(
        check_id,
        category,
        GateStatus.UNKNOWN,
        requirement,
        "the capsule store could not be loaded, so the graph could not be inspected",
        EvidenceKind.CONTRACT,
        missing_evidence=("knowledge/company_os/capsules/seeds could not be read",),
        remediation=(
            "Repair the capsule seed directory so every *.json file parses as a "
            "Capsule, then re-run the gate."
        ),
        evidence_as_of=as_of,
    )


def _config_unavailable(
    check_id: str, category: GateCategory, requirement: str, as_of: dt.date
) -> GateCheck:
    return _check(
        check_id,
        category,
        GateStatus.UNKNOWN,
        requirement,
        "the bootstrap contracts could not be loaded, so nothing could be compared",
        EvidenceKind.CONTRACT,
        missing_evidence=("company/permissions.yaml and its three companions did not load",),
        remediation=(
            "Repair the four canonical YAML files under company/ so "
            "load_company_config succeeds, then re-run the gate."
        ),
        evidence_as_of=as_of,
    )


# -- architecture -----------------------------------------------------------


def _production_imports(inputs, scan, index, config) -> GateCheck:
    findings = production_import_violations(scan.production_modules)
    roots = ", ".join(scan.scanned_production_roots) or "no production root"
    absent = (
        f"; declared but absent here: {', '.join(scan.absent_production_roots)}"
        if scan.absent_production_roots
        else ""
    )
    return _from_findings(
        "architecture.production_does_not_import_company_os",
        GateCategory.ARCHITECTURE,
        "No production module imports company, ai_platform, knowledge or intelligence "
        "(company/README.md dependency rule).",
        findings,
        clean_detail=(
            f"{len(scan.production_modules)} production modules under {roots} import no "
            f"Company OS package{absent}"
        ),
        remediation=(
            "Remove the import. If production needs a result Company OS computes, the "
            "control plane hands it over; production does not reach in."
        ),
        evidence=("company/README.md",),
        as_of=inputs.as_of,
    )


def _production_tests(inputs, scan, index, config) -> GateCheck:
    modules = scan.production_test_modules()
    if not scan.test_modules:
        return _check(
            "architecture.production_tests_independent",
            GateCategory.ARCHITECTURE,
            GateStatus.NOT_APPLICABLE,
            "No production test module imports Company OS, so the suite still runs "
            "with company/, ai_platform/ and knowledge/ removed.",
            "this checkout holds no tests/ directory to inspect",
            EvidenceKind.REPOSITORY,
            not_applicable_reason="there is no test tree in this checkout",
            evidence_as_of=inputs.as_of,
        )
    findings = production_import_violations(modules)
    return _from_findings(
        "architecture.production_tests_independent",
        GateCategory.ARCHITECTURE,
        "No production test module imports Company OS, so the suite still runs with "
        "company/, ai_platform/ and knowledge/ removed.",
        findings,
        clean_detail=(
            f"{len(modules)} production test modules import no Company OS package; the "
            f"{len(scan.test_modules) - len(modules)} that do are all named "
            f"{COMPANY_OS_TEST_PREFIX}*"
        ),
        remediation=(
            "Move the Company OS coverage into a test_company* module, or drop the "
            "import: a production suite that needs the control plane is a production "
            "suite that cannot run without it."
        ),
        as_of=inputs.as_of,
    )


def _import_cycle(inputs, scan, index, config) -> GateCheck:
    graph = subsystem_import_graph(scan.company_modules)
    cycles = find_cycles(graph)
    deferred = type_checking_edges(scan.company_modules)
    requirement = (
        "The Company OS subsystem import graph is acyclic at runtime; imports inside "
        "if TYPE_CHECKING are reported but do not count, because they never execute."
    )
    if cycles:
        rendered = [render_cycle(cycle) for cycle in cycles]
        return _check(
            "architecture.no_subsystem_import_cycle",
            GateCategory.ARCHITECTURE,
            GateStatus.FAIL,
            requirement,
            "; ".join(rendered[:_MAX_NAMED_FINDINGS]),
            EvidenceKind.REPOSITORY,
            blocker_reason=f"{len(cycles)} runtime import cycle(s): {rendered[0]}",
            remediation=(
                "Break the cycle by moving the shared names into a module both sides "
                "may import, the way company/validation/errors.py already is."
            ),
            evidence_as_of=inputs.as_of,
        )
    note = (
        f"; {len(deferred)} type-checking-only edge(s) exist and are not counted"
        if deferred
        else ""
    )
    return _check(
        "architecture.no_subsystem_import_cycle",
        GateCategory.ARCHITECTURE,
        GateStatus.PASS,
        requirement,
        f"{len(graph)} subsystems, no runtime import cycle{note}",
        EvidenceKind.REPOSITORY,
        evidence=deferred[:4],
        evidence_as_of=inputs.as_of,
    )


def _capsule_acyclic(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "The declared capsule dependency graph is acyclic: a capsule that rests on a "
        "capsule that rests on it describes a boundary that is not one."
    )
    if index is None:
        return _capsules_unavailable(
            "architecture.capsule_graph_acyclic", GateCategory.ARCHITECTURE, requirement, inputs.as_of
        )
    cycles = find_cycles(capsule_dependency_graph(index))
    if not cycles:
        return _check(
            "architecture.capsule_graph_acyclic",
            GateCategory.ARCHITECTURE,
            GateStatus.PASS,
            requirement,
            f"{len(index)} capsules, no declared dependency cycle",
            EvidenceKind.CONTRACT,
            evidence=("knowledge/company_os/capsules/seeds",),
            evidence_as_of=inputs.as_of,
        )
    rendered = [render_cycle(cycle) for cycle in cycles]
    return _check(
        "architecture.capsule_graph_acyclic",
        GateCategory.ARCHITECTURE,
        GateStatus.FAIL,
        requirement,
        "; ".join(rendered[:_MAX_NAMED_FINDINGS]),
        EvidenceKind.CONTRACT,
        evidence=tuple(
            f"knowledge/company_os/capsules/seeds/{node}.json"
            for node in cycles[0][:4]
        ),
        blocker_reason=f"{len(cycles)} declared capsule cycle(s): {rendered[0]}",
        remediation=(
            "Remove one direction of the edge in the capsule seeds once the code "
            "dependency it records has been removed. Do not edit the capsule to hide "
            "a coupling the modules still have."
        ),
        evidence_as_of=inputs.as_of,
    )


def _capsule_integrity(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "The capsule store holds no dangling dependency, no path claimed by two "
        "capsules, no link to a record that is not in the knowledge store, and no "
        "pointer that has left the repository."
    )
    if index is None:
        return _capsules_unavailable(
            "architecture.capsule_graph_integrity",
            GateCategory.ARCHITECTURE,
            requirement,
            inputs.as_of,
        )
    try:
        from knowledge.company_os.ledger import DEFAULT_ROOT, KnowledgeStore

        records = Path(inputs.repo_root) / "knowledge/company_os/records"
        store = KnowledgeStore(records if records.is_dir() else DEFAULT_ROOT)
        problems = index.integrity(store, Path(inputs.repo_root))
    except Exception as exc:  # noqa: BLE001
        return _check(
            "architecture.capsule_graph_integrity",
            GateCategory.ARCHITECTURE,
            GateStatus.UNKNOWN,
            requirement,
            f"the integrity check did not complete: {type(exc).__name__}: {exc}",
            EvidenceKind.CONTRACT,
            missing_evidence=(f"CapsuleIndex.integrity raised {type(exc).__name__}",),
            remediation="Repair the knowledge store or the capsule seeds, then re-run.",
            evidence_as_of=inputs.as_of,
        )
    if not problems:
        return _check(
            "architecture.capsule_graph_integrity",
            GateCategory.ARCHITECTURE,
            GateStatus.PASS,
            requirement,
            f"{len(index)} capsules, no integrity problem",
            EvidenceKind.CONTRACT,
            evidence=("knowledge/company_os/capsules/seeds",),
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "architecture.capsule_graph_integrity",
        GateCategory.ARCHITECTURE,
        GateStatus.FAIL,
        requirement,
        "; ".join(problems[:_MAX_NAMED_FINDINGS]),
        EvidenceKind.CONTRACT,
        evidence=("knowledge/company_os/capsules/seeds",),
        blocker_reason=f"{len(problems)} capsule integrity problem(s): {problems[0]}",
        remediation="Fix each problem in the named capsule seed, then re-run the gate.",
        evidence_as_of=inputs.as_of,
    )


def _ownership(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Every Company OS module is claimed by exactly one capsule, so a session can "
        "be given the boundary that owns the file it is about to change."
    )
    if index is None:
        return _capsules_unavailable(
            "architecture.subsystem_ownership_bounded",
            GateCategory.ARCHITECTURE,
            requirement,
            inputs.as_of,
        )
    owned = [normalise_path(path) for capsule in index.all() for path in capsule.owns_paths]
    unowned = [
        module.path
        for module in scan.company_modules
        if not any(path_related(claim, module.path) for claim in owned)
    ]
    if not unowned:
        return _check(
            "architecture.subsystem_ownership_bounded",
            GateCategory.ARCHITECTURE,
            GateStatus.PASS,
            requirement,
            f"all {len(scan.company_modules)} Company OS modules are claimed by a capsule",
            EvidenceKind.CONTRACT,
            evidence=("knowledge/company_os/capsules/seeds",),
            evidence_as_of=inputs.as_of,
        )
    named = unowned[:_MAX_NAMED_FINDINGS]
    tail = "" if len(unowned) <= len(named) else f", and {len(unowned) - len(named)} more"
    return _check(
        "architecture.subsystem_ownership_bounded",
        GateCategory.ARCHITECTURE,
        GateStatus.FAIL,
        requirement,
        f"{len(unowned)} module(s) no capsule claims: " + ", ".join(named) + tail,
        EvidenceKind.CONTRACT,
        evidence=tuple(named),
        blocker_reason=f"{len(unowned)} Company OS module(s) have no capsule owner",
        remediation=(
            "Add each path to the owns_paths of the capsule that already owns its "
            "neighbours, or widen that capsule's claim to the package directory."
        ),
        evidence_as_of=inputs.as_of,
    )


# -- execution safety -------------------------------------------------------


def _restricted_states(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "A candidate, shadow or probation employee cannot hold production authority "
        "or an autonomy level above the cap permissions.yaml sets for their state."
    )
    permissions = getattr(config, "permissions", None)
    if permissions is None:
        return _config_unavailable(
            "workforce.restricted_states_cannot_write_production",
            GateCategory.WORKFORCE,
            requirement,
            inputs.as_of,
        )
    return _from_probe(
        "workforce.restricted_states_cannot_write_production",
        GateCategory.WORKFORCE,
        requirement,
        probes.run_probe(
            lambda: probes.probe_restricted_states_cannot_write_production(permissions)
        ),
        remediation=(
            "Restore the state authority caps in permissions.yaml bootstrap_defaults, "
            "or the refusal in company/workforce/employment.py."
        ),
        as_of=inputs.as_of,
    )


# -- workforce and finance contracts ----------------------------------------


def _reserved_actions(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "The eight CEO-reserved decisions the gate depends on are still reserved in "
        "permissions.yaml; the gate reads that list and defines no authority itself."
    )
    permissions = getattr(config, "permissions", None)
    if permissions is None:
        return _config_unavailable(
            "workforce.ceo_reserved_actions_present",
            GateCategory.WORKFORCE,
            requirement,
            inputs.as_of,
        )
    return _from_drift(
        "workforce.ceo_reserved_actions_present",
        GateCategory.WORKFORCE,
        requirement,
        reserved_action_drift(permissions),
        clean_detail="all eight required CEO-reserved actions are present",
        remediation=(
            "Restore the reserved action in permissions.yaml. Removing one is itself "
            "a CEO decision (constitution, Amendment)."
        ),
        as_of=inputs.as_of,
    )


def _recurring_spend(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Recurring paid API spend stays CEO-reserved and a new dependency still "
        "triggers a mandatory review, so no subsystem can commit the company to a bill."
    )
    permissions = getattr(config, "permissions", None)
    if permissions is None:
        return _config_unavailable(
            "finance.recurring_paid_api_spend_reserved",
            GateCategory.FINANCE,
            requirement,
            inputs.as_of,
        )
    reserved = reserved_action_drift(permissions)
    spend_missing = tuple(
        item for item in reserved.missing if "large_or_recurring_paid_api_spend" in item
    )
    triggers = review_trigger_drift(permissions)
    drift = ContractDrift(
        missing=spend_missing + triggers.missing,
        evidence=("company/permissions.yaml",),
    )
    return _from_drift(
        "finance.recurring_paid_api_spend_reserved",
        GateCategory.FINANCE,
        requirement,
        drift,
        clean_detail=(
            "large_or_recurring_paid_api_spend is CEO-reserved and new_dependency and "
            "production_publish_request are mandatory review triggers"
        ),
        remediation="Restore the reserved action and the review triggers in permissions.yaml.",
        as_of=inputs.as_of,
    )


def _capability_gaps(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Capability gaps in the workforce are visible from recorded coverage rather "
        "than inferred, so a missing skill reads as missing."
    )
    if inputs.state_dir is None:
        return _check(
            "workforce.capability_gaps_visible",
            GateCategory.WORKFORCE,
            GateStatus.UNKNOWN,
            requirement,
            "no company state directory was supplied, so there is no coverage to read",
            EvidenceKind.SUPPLIED,
            missing_evidence=(
                "a workforce store: re-run with --state-dir pointing at the company's "
                "records",
            ),
            remediation="Re-run with --state-dir to evaluate recorded capability coverage.",
            evidence_as_of=inputs.as_of,
        )
    try:
        from company.workforce.store import WorkforceStore

        store = WorkforceStore(inputs.state_dir)
        roles = tuple(store.load_all("role")) if hasattr(store, "load_all") else ()
    except Exception as exc:  # noqa: BLE001
        return _check(
            "workforce.capability_gaps_visible",
            GateCategory.WORKFORCE,
            GateStatus.UNKNOWN,
            requirement,
            f"the workforce store could not be read: {type(exc).__name__}: {exc}",
            EvidenceKind.SUPPLIED,
            missing_evidence=(f"WorkforceStore raised {type(exc).__name__}",),
            remediation="Point --state-dir at a readable workforce store and re-run.",
            evidence_as_of=inputs.as_of,
        )
    if not roles:
        return _check(
            "workforce.capability_gaps_visible",
            GateCategory.WORKFORCE,
            GateStatus.UNKNOWN,
            requirement,
            "the supplied state directory holds no role records, so coverage is unknown",
            EvidenceKind.SUPPLIED,
            missing_evidence=("no role records in the supplied state directory",),
            remediation="Record the roles and their capability coverage, then re-run.",
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "workforce.capability_gaps_visible",
        GateCategory.WORKFORCE,
        GateStatus.PASS,
        requirement,
        f"{len(roles)} role record(s) are readable and carry their declared capabilities",
        EvidenceKind.SUPPLIED,
        evidence=(str(inputs.state_dir),),
        evidence_as_of=inputs.as_of,
    )


# -- executive visibility ---------------------------------------------------


def _dashboard_cannot_approve(inputs, scan, index, config) -> GateCheck:
    dashboard = tuple(
        module for module in scan.company_modules if module.path.startswith("company/dashboard/")
    )
    findings: list[Finding] = []
    for module in dashboard:
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            verb = next((v for v in _ACTION_VERBS if v in node.name.casefold()), "")
            if verb:
                findings.append(
                    Finding(
                        module.path,
                        node.lineno,
                        f"exposes {node.name}(); a read model does not {verb.rstrip('_')}",
                    )
                )
    return _from_findings(
        "executive.dashboard_cannot_approve",
        GateCategory.EXECUTIVE_VISIBILITY,
        "The CEO dashboard exposes no callable that approves, spends, hires, "
        "publishes, merges or deploys; it is a view, not a second control plane.",
        tuple(findings),
        clean_detail=(
            f"{len(dashboard)} dashboard modules expose no approving, spending, hiring, "
            "publishing or deploying callable"
        ),
        remediation=(
            "Move the action out of company/dashboard/ into the subsystem that owns it, "
            "behind the authority that subsystem already requires."
        ),
        as_of=inputs.as_of,
    )


def _decision_queue_refs(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Every item in the CEO decision queue keeps a compact reference back to the "
        "record it came from, so a decision can be checked rather than believed."
    )
    if inputs.state_dir is None:
        return _check(
            "executive.decision_queue_preserves_source_refs",
            GateCategory.EXECUTIVE_VISIBILITY,
            GateStatus.UNKNOWN,
            requirement,
            "no company state directory was supplied, so the decision queue is empty "
            "and the condition is untested rather than satisfied",
            EvidenceKind.SUPPLIED,
            missing_evidence=(
                "a state directory holding at least one decision: an empty queue proves "
                "nothing about what a populated one carries",
            ),
            remediation="Re-run with --state-dir pointing at the company's records.",
            evidence_as_of=inputs.as_of,
        )
    try:
        from company.dashboard.builder import build_snapshot

        snapshot = build_snapshot(inputs.state_dir, as_of=inputs.as_of)
    except Exception as exc:  # noqa: BLE001
        return _check(
            "executive.decision_queue_preserves_source_refs",
            GateCategory.EXECUTIVE_VISIBILITY,
            GateStatus.UNKNOWN,
            requirement,
            f"the snapshot could not be built: {type(exc).__name__}: {exc}",
            EvidenceKind.SUPPLIED,
            missing_evidence=(f"build_snapshot raised {type(exc).__name__}",),
            remediation="Point --state-dir at a readable state directory and re-run.",
            evidence_as_of=inputs.as_of,
        )
    queue = snapshot.decision_queue
    if not queue:
        return _check(
            "executive.decision_queue_preserves_source_refs",
            GateCategory.EXECUTIVE_VISIBILITY,
            GateStatus.UNKNOWN,
            requirement,
            "the supplied state directory produced an empty decision queue",
            EvidenceKind.SUPPLIED,
            missing_evidence=("no decisions in the supplied state directory",),
            remediation="Record at least one open decision, then re-run.",
            evidence_as_of=inputs.as_of,
        )
    bare = [item for item in queue if not getattr(item, "source_refs", ())]
    if bare:
        return _check(
            "executive.decision_queue_preserves_source_refs",
            GateCategory.EXECUTIVE_VISIBILITY,
            GateStatus.FAIL,
            requirement,
            f"{len(bare)} of {len(queue)} decisions carry no source reference",
            EvidenceKind.SUPPLIED,
            blocker_reason=f"{len(bare)} decision(s) in the queue cite nothing",
            remediation="Restore the source references the decision builder attaches.",
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "executive.decision_queue_preserves_source_refs",
        GateCategory.EXECUTIVE_VISIBILITY,
        GateStatus.PASS,
        requirement,
        f"all {len(queue)} queued decisions carry a source reference",
        EvidenceKind.SUPPLIED,
        evidence=(str(inputs.state_dir),),
        evidence_as_of=inputs.as_of,
    )


# -- test and build health --------------------------------------------------


def _required_suites(inputs, scan, index, config) -> GateCheck:
    requirement = (
        f"All {len(REQUIRED_SUITES)} required Company OS suites are reported as passing, "
        "on evidence no older than the freshness window."
    )
    evidence = inputs.suites
    missing = evidence.missing()
    if missing:
        return _check(
            "health.required_suites_pass",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.UNKNOWN,
            requirement,
            f"{len(missing)} of {len(REQUIRED_SUITES)} required suites have no reported run",
            EvidenceKind.SUPPLIED,
            missing_evidence=tuple(f"no reported run for {suite}" for suite in missing[:8]),
            remediation=(
                "Run the suites and supply the results with --suite-evidence. The gate "
                "holds no process-spawn authority, so it cannot run them itself."
            ),
            evidence_as_of=inputs.as_of,
        )
    failing = evidence.failing()
    if failing:
        return _check(
            "health.required_suites_pass",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.FAIL,
            requirement,
            "; ".join(item.reference() for item in failing[:_MAX_NAMED_FINDINGS]),
            EvidenceKind.SUPPLIED,
            evidence=tuple(item.suite for item in failing[:_MAX_NAMED_FINDINGS]),
            blocker_reason=f"{len(failing)} required suite(s) are reported failing",
            remediation="Fix the failing suite, re-run it, and supply the new result.",
            evidence_as_of=min(item.observed_on for item in evidence.results),
        )
    stale = evidence.stale(inputs.as_of)
    if stale:
        return _check(
            "health.required_suites_pass",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.UNKNOWN,
            requirement,
            f"{len(stale)} required suite result(s) are older than "
            f"{evidence.max_age_days} days",
            EvidenceKind.SUPPLIED,
            missing_evidence=tuple(
                f"{item.suite} was last run on {item.observed_on.isoformat()}, "
                f"{item.age_days(inputs.as_of)} days ago"
                for item in stale[:8]
            ),
            remediation="Re-run the stale suites and supply the fresh results.",
            evidence_as_of=min(item.observed_on for item in stale),
        )
    return _check(
        "health.required_suites_pass",
        GateCategory.TEST_BUILD_HEALTH,
        GateStatus.PASS,
        requirement,
        f"all {len(REQUIRED_SUITES)} required suites reported passing, oldest run "
        f"{max(item.age_days(inputs.as_of) for item in evidence.results)} day(s) ago",
        EvidenceKind.SUPPLIED,
        evidence=tuple(item.suite for item in evidence.results[:_MAX_NAMED_FINDINGS]),
        evidence_as_of=min(item.observed_on for item in evidence.results),
    )


def _production_failures_separated(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Failures caused by the production environment are reported separately from "
        "Company OS regressions, so a missing render dependency is not read as a defect "
        "in the control plane."
    )
    production = inputs.suites.production_results()
    if not inputs.suites:
        return _check(
            "health.production_failures_separated",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.UNKNOWN,
            requirement,
            "no suite evidence was supplied, so nothing has been separated",
            EvidenceKind.SUPPLIED,
            missing_evidence=("no suite evidence supplied",),
            remediation=(
                "Supply suite results with --suite-evidence, marking production-"
                "environment suites with company_os=false."
            ),
            evidence_as_of=inputs.as_of,
        )
    if not production:
        return _check(
            "health.production_failures_separated",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.UNKNOWN,
            requirement,
            "every supplied result is marked as a Company OS suite; no production-"
            "environment run was classified either way",
            EvidenceKind.SUPPLIED,
            missing_evidence=(
                "no result carries company_os=false, so the separation is asserted "
                "rather than shown",
            ),
            remediation=(
                "Supply at least one production-environment suite result marked "
                "company_os=false."
            ),
            evidence_as_of=inputs.as_of,
        )
    failing = tuple(item for item in production if not item.passed)
    return _check(
        "health.production_failures_separated",
        GateCategory.TEST_BUILD_HEALTH,
        GateStatus.PASS,
        requirement,
        f"{len(production)} production-environment suite(s) are classified separately, "
        f"{len(failing)} of them failing and none counted against Company OS",
        EvidenceKind.SUPPLIED,
        evidence=tuple(item.suite for item in production[:_MAX_NAMED_FINDINGS]),
        evidence_as_of=min(item.observed_on for item in production),
    )


def _sources_parse(inputs, scan, index, config) -> GateCheck:
    failures = scan.company_failures
    requirement = (
        "Every Company OS source file parses. No linter is configured in this "
        "repository, so this is the static check that is available, and it is the one "
        "the rest of the scanning conditions depend on."
    )
    if not failures:
        return _check(
            "health.sources_parse",
            GateCategory.TEST_BUILD_HEALTH,
            GateStatus.PASS,
            requirement,
            f"all {len(scan.company_modules)} Company OS modules parse",
            EvidenceKind.REPOSITORY,
            evidence=tuple(scan.scanned_company_roots),
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "health.sources_parse",
        GateCategory.TEST_BUILD_HEALTH,
        GateStatus.FAIL,
        requirement,
        "; ".join(failures[:_MAX_NAMED_FINDINGS]),
        EvidenceKind.REPOSITORY,
        blocker_reason=f"{len(failures)} Company OS file(s) do not parse: {failures[0]}",
        remediation=(
            "Fix the syntax error. Until it parses, every scanning condition is "
            "answering over an incomplete tree."
        ),
        evidence_as_of=inputs.as_of,
    )


def _new_dependency(inputs, scan, index, config) -> GateCheck:
    findings = non_first_party_imports(scan.company_modules, COMPANY_OS_ROOTS)
    return _from_findings(
        "health.no_new_dependency",
        GateCategory.TEST_BUILD_HEALTH,
        "Company OS imports only the standard library and other Company OS roots. A "
        "new dependency is a mandatory architecture-and-security review "
        "(permissions.yaml) and would tie the control plane to the production "
        "dependency tree.",
        findings,
        clean_detail=(
            f"{len(scan.company_modules)} Company OS modules import only stdlib and "
            f"{', '.join(COMPANY_OS_ROOTS)}"
        ),
        remediation=(
            "Remove the import or take it to architecture review; requirements.txt "
            "belongs to production, not to the control plane."
        ),
        evidence=("company/permissions.yaml", "requirements.txt"),
        as_of=inputs.as_of,
    )


def _network_or_model(inputs, scan, index, config) -> GateCheck:
    findings = forbidden_import_violations(
        scan.company_modules,
        NETWORK_MODULES | MODEL_MODULES,
        "Company OS is deterministic and offline; a network or model client here is "
        "an unbudgeted external call",
    )
    return _from_findings(
        "health.no_network_or_model_dependency",
        GateCategory.TEST_BUILD_HEALTH,
        "No Company OS module imports a network client or a model SDK. The control "
        "plane is deterministic code (constitution rule 4) and reaches nothing.",
        findings,
        clean_detail=(
            f"{len(scan.company_modules)} Company OS modules import none of "
            f"{len(NETWORK_MODULES | MODEL_MODULES)} network or model roots"
        ),
        remediation=(
            "Remove the client. Research ingestion takes supplied snapshots; it does "
            "not fetch them."
        ),
        as_of=inputs.as_of,
    )


# -- production boundary ----------------------------------------------------


def _no_publishing(inputs, scan, index, config) -> GateCheck:
    findings = tuple(
        list(
            forbidden_import_violations(
                scan.company_modules,
                NETWORK_MODULES,
                "publishing needs a network, and no Company OS module may have one",
            )
        )
        + list(process_spawn_violations(scan.company_modules))
    )
    return _from_findings(
        "production.no_publishing_capability",
        GateCategory.PRODUCTION_BOUNDARY,
        "No Company OS module can publish: it opens no socket and spawns no process. "
        "publish_public_video is CEO-reserved, and a shell would be a way around that.",
        tuple(sorted(findings, key=lambda item: (item.path, item.line))),
        clean_detail=(
            "no network import and no process spawn anywhere in "
            f"{len(scan.company_modules)} Company OS modules"
        ),
        remediation=(
            "Remove the capability. A publish is a CEO decision carried out elsewhere, "
            "and the control plane prepares the request rather than performing it."
        ),
        evidence=("company/permissions.yaml",),
        as_of=inputs.as_of,
    )


def _no_production_mutation(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "No Company OS module writes into a production tree. Stores write only where "
        "their caller points them, and no filesystem-mutating call names a constant "
        "path under a production root."
    )
    if not scan.scanned_production_roots:
        return _check(
            "production.no_automatic_production_mutation",
            GateCategory.PRODUCTION_BOUNDARY,
            GateStatus.NOT_APPLICABLE,
            requirement,
            "this checkout contains none of the declared production roots",
            EvidenceKind.REPOSITORY,
            not_applicable_reason="there is no production tree here to write into",
            evidence_as_of=inputs.as_of,
        )
    findings = production_write_violations(scan.company_modules, scan.scanned_production_roots)
    return _from_findings(
        "production.no_automatic_production_mutation",
        GateCategory.PRODUCTION_BOUNDARY,
        requirement,
        findings,
        clean_detail=(
            f"no mutating call in {len(scan.company_modules)} Company OS modules names a "
            f"constant path under {len(scan.scanned_production_roots)} production roots; "
            "a path built at runtime is bounded by PathScope instead"
        ),
        remediation=(
            "Remove the write. Company OS proposes a production change and a session "
            "with an explicit packet performs it."
        ),
        evidence=("company/runtime/path_scope.py",),
        as_of=inputs.as_of,
    )


def _no_delete(inputs, scan, index, config) -> GateCheck:
    findings = delete_call_violations(scan.company_modules)
    return _from_findings(
        "production.no_production_delete_authority",
        GateCategory.PRODUCTION_BOUNDARY,
        "No Company OS module removes a file or a directory. Every store here is "
        "append-only, and delete_important_production_or_company_data is CEO-reserved.",
        findings,
        clean_detail=(
            f"no delete call in {len(scan.company_modules)} Company OS modules"
        ),
        remediation=(
            "Supersede the record instead of deleting it; that is what the ledger is "
            "for. If a file genuinely must go, that is a CEO decision."
        ),
        evidence=("company/permissions.yaml",),
        as_of=inputs.as_of,
    )


def _integration_disabled(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "The control-plane capsule still states that Company OS stays unconnected to "
        "production execution until this gate passes, so the next session reads that "
        "before it reads anything else."
    )
    if index is None:
        return _capsules_unavailable(
            "production.integration_remains_disabled",
            GateCategory.PRODUCTION_BOUNDARY,
            requirement,
            inputs.as_of,
        )
    try:
        capsule = index.get("company-os-control-plane")
    except Exception as exc:  # noqa: BLE001
        return _check(
            "production.integration_remains_disabled",
            GateCategory.PRODUCTION_BOUNDARY,
            GateStatus.UNKNOWN,
            requirement,
            f"the control-plane capsule could not be read: {exc}",
            EvidenceKind.CONTRACT,
            missing_evidence=("company-os-control-plane is not in the capsule store",),
            remediation="Restore the control-plane capsule seed, then re-run the gate.",
            evidence_as_of=inputs.as_of,
        )
    held, detail = integration_still_gated(tuple(capsule.invariants))
    reference = "knowledge/company_os/capsules/seeds/company-os-control-plane.json"
    if held:
        return _check(
            "production.integration_remains_disabled",
            GateCategory.PRODUCTION_BOUNDARY,
            GateStatus.PASS,
            requirement,
            detail,
            EvidenceKind.CONTRACT,
            evidence=(reference,),
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "production.integration_remains_disabled",
        GateCategory.PRODUCTION_BOUNDARY,
        GateStatus.FAIL,
        requirement,
        detail,
        EvidenceKind.CONTRACT,
        evidence=(reference,),
        blocker_reason=detail,
        remediation=(
            "Restore the invariant. Removing it does not enable integration - that is "
            "a CEO decision - it only stops the next session being told."
        ),
        evidence_as_of=inputs.as_of,
    )


def _no_subagent_chain_check(inputs, scan, index, config) -> GateCheck:
    requirement = (
        "Constitution rule 2 is still represented in all eight places that carry it: "
        "the constitution, permissions.yaml twice, the org registry twice, the "
        "employee contract schema twice, and the knowledge store."
    )
    if config is None:
        return _config_unavailable(
            "execution.no_subagent_runtime_lock",
            GateCategory.EXECUTION_SAFETY,
            requirement,
            inputs.as_of,
        )
    links = no_subagent_chain(inputs.repo_root, config)
    broken = tuple(link for link in links if not link.present)
    probe = probes.run_probe(probes.probe_no_subagent_runtime_lock)
    if broken:
        return _check(
            "execution.no_subagent_runtime_lock",
            GateCategory.EXECUTION_SAFETY,
            GateStatus.FAIL,
            requirement,
            "; ".join(f"{link.name}: {link.detail}" for link in broken[:_MAX_NAMED_FINDINGS]),
            EvidenceKind.CONTRACT,
            evidence=tuple(link.reference for link in broken[:_MAX_NAMED_FINDINGS]),
            blocker_reason=(
                f"{len(broken)} of {len(links)} no-subagent chain links are gone: "
                f"{broken[0].name} - {broken[0].detail}"
            ),
            remediation=(
                "Restore the declaration. Changing the no-subagent policy is "
                "CEO-reserved (permissions.yaml change_no_subagents_policy)."
            ),
            evidence_as_of=inputs.as_of,
        )
    if not probe.ran:
        return _check(
            "execution.no_subagent_runtime_lock",
            GateCategory.EXECUTION_SAFETY,
            GateStatus.UNKNOWN,
            requirement,
            f"all {len(links)} declarations are present, but the runtime lock could not "
            f"be exercised: {probe.detail}",
            EvidenceKind.PROBE,
            missing_evidence=(f"the runtime probe raised {probe.error}",),
            remediation="Make ai_platform.policy importable and re-run the gate.",
            evidence_as_of=inputs.as_of,
        )
    if not probe.ok:
        return _check(
            "execution.no_subagent_runtime_lock",
            GateCategory.EXECUTION_SAFETY,
            GateStatus.FAIL,
            requirement,
            probe.detail,
            EvidenceKind.PROBE,
            evidence=probe.evidence,
            blocker_reason=probe.detail,
            remediation=(
                "Restore the bootstrap lock in ai_platform/policy.py and the contract "
                "refusal in company/runtime/authority.py."
            ),
            evidence_as_of=inputs.as_of,
        )
    return _check(
        "execution.no_subagent_runtime_lock",
        GateCategory.EXECUTION_SAFETY,
        GateStatus.PASS,
        requirement,
        f"all {len(links)} declarations are present, and {probe.detail}",
        EvidenceKind.PROBE,
        evidence=tuple(link.reference for link in links[:4]) + probe.evidence[:2],
        evidence_as_of=inputs.as_of,
    )


def _probe_builder(
    check_id: str,
    category: GateCategory,
    requirement: str,
    probe: Callable[[], ProbeResult],
    remediation: str,
) -> Callable[..., GateCheck]:
    def builder(inputs, scan, index, config) -> GateCheck:
        return _from_probe(
            check_id,
            category,
            requirement,
            probes.run_probe(probe),
            remediation=remediation,
            as_of=inputs.as_of,
        )

    return builder


_BUILDERS: tuple[Callable[..., GateCheck], ...] = (
    # architecture
    _production_imports,
    _production_tests,
    _import_cycle,
    _capsule_acyclic,
    _capsule_integrity,
    _ownership,
    # execution safety
    _probe_builder(
        "execution.read_authority_fails_closed",
        GateCategory.EXECUTION_SAFETY,
        "Read authority fails closed: a contract that names no readable path grants "
        "none, and a named path is carried through unchanged.",
        probes.probe_read_authority_fails_closed,
        "Restore the projection in company/runtime/authority.py so an absent may_read "
        "becomes an empty tuple rather than an unbounded grant.",
    ),
    _probe_builder(
        "execution.write_authority_fails_closed",
        GateCategory.EXECUTION_SAFETY,
        "Write authority fails closed: an empty allow-list permits nothing and a "
        "forbidding rule outranks an overlapping allow.",
        probes.probe_write_authority_fails_closed,
        "Restore the two rules in company/runtime/path_scope.py: forbidden wins, and "
        "silence is not permission.",
    ),
    _probe_builder(
        "execution.authority_snapshot_immutable",
        GateCategory.EXECUTION_SAFETY,
        "The preparation-time authority snapshot is immutable and self-verifying: it "
        "cannot be mutated, a widened copy cannot be constructed, and it round-trips "
        "through canonical JSON unchanged.",
        probes.probe_authority_snapshot_immutable,
        "Restore the frozen dataclass and the contract-fingerprint check in "
        "company/runtime/authority.py.",
    ),
    _probe_builder(
        "execution.receipt_validation_enforced",
        GateCategory.EXECUTION_SAFETY,
        "A returned receipt is validated against a fixed schema: an unknown field is "
        "refused rather than ignored, and a receipt cannot amend the no-subagent rule.",
        probes.probe_receipt_validation_enforced,
        "Restore the unknown-field refusal and the no-subagent scan in "
        "company/runtime/receipts.py.",
    ),
    _no_subagent_chain_check,
    # data and evidence
    _probe_builder(
        "data.private_metric_boundary",
        GateCategory.DATA_EVIDENCE,
        "A private channel analytic can only come from our own authenticated access; "
        "no public source may carry one, for our videos or anybody else's.",
        probes.probe_private_metric_boundary,
        "Restore assert_source_can_produce in company/analytics/metrics.py.",
    ),
    _probe_builder(
        "data.evidence_required_for_claims",
        GateCategory.DATA_EVIDENCE,
        "A stored claim points at something a second person can check; a record with "
        "no evidence cannot be built.",
        probes.probe_evidence_required_for_claims,
        "Restore the evidence requirement in knowledge/company_os/records.py.",
    ),
    _probe_builder(
        "data.missing_evidence_stays_unknown",
        GateCategory.DATA_EVIDENCE,
        "Missing data is reported as missing. An empty subsystem is never reported as "
        "zero, healthy or complete.",
        probes.probe_missing_evidence_stays_unknown,
        "Restore the availability and missing-source reporting in "
        "company/dashboard/builder.py.",
    ),
    _probe_builder(
        "data.audit_records_append_only",
        GateCategory.DATA_EVIDENCE,
        "Recorded history is append-only: a differing record cannot be written under "
        "an existing id, so a correction is a new record that supersedes the old one.",
        probes.probe_audit_records_append_only,
        "Restore the overwrite refusal in knowledge/company_os/ledger.py.",
    ),
    # workforce
    _reserved_actions,
    _restricted_states,
    _probe_builder(
        "workforce.advisory_cannot_self_approve",
        GateCategory.WORKFORCE,
        "An organizational recommendation cannot be approved by the system that made "
        "it; an approver is a named human.",
        probes.probe_advisory_cannot_self_approve,
        "Restore assert_human in company/org_intelligence/common.py.",
    ),
    # finance
    _probe_builder(
        "finance.no_autonomous_spend_approval",
        GateCategory.FINANCE,
        "No subsystem approves its own spend. Finance records the proposal and the "
        "evidence; approving it is a named human act.",
        probes.probe_no_autonomous_spend_approval,
        "Restore assert_human in company/finance/common.py.",
    ),
    _recurring_spend,
    _probe_builder(
        "finance.unknown_is_not_zero",
        GateCategory.FINANCE,
        "An unmeasured financial figure is unknown, not zero: with nothing recorded "
        "there is no margin and no contribution, and the gaps are named.",
        probes.probe_unknown_is_not_zero,
        "Restore the missing-reason accumulation in company/finance/economics.py.",
    ),
    # analytics
    _probe_builder(
        "analytics.causal_overclaim_refused",
        GateCategory.ANALYTICS,
        "An uncontrolled comparison supports no causal claim however large the sample, "
        "and the assessment names why.",
        probes.probe_causal_overclaim_refused,
        "Restore CausalAssessment.blockers in company/analytics/results.py.",
    ),
    _probe_builder(
        "analytics.learning_requires_results",
        GateCategory.ANALYTICS,
        "Observation and learning stay separate: a hypothesis cannot be marked "
        "supported without a result to point at.",
        probes.probe_learning_requires_results,
        "Restore the supported-state guard in company/analytics/learning.py.",
    ),
    _probe_builder(
        "analytics.competitor_private_metrics_unavailable",
        GateCategory.ANALYTICS,
        "An external reference may name public metrics only and must cite the dossier "
        "it came from; a competitor's private analytics are not available to us.",
        probes.probe_competitor_private_metrics_unavailable,
        "Restore assert_public_only in company/analytics/references.py.",
    ),
    # executive visibility
    _probe_builder(
        "executive.dashboard_available",
        GateCategory.EXECUTIVE_VISIBILITY,
        "The CEO dashboard builds a deterministic snapshot and renders a brief, so the "
        "executive view exists before it is needed.",
        probes.probe_dashboard_available,
        "Repair company/dashboard/builder.py so a snapshot builds over an empty state "
        "directory.",
    ),
    _probe_builder(
        "executive.missing_and_stale_evidence_visible",
        GateCategory.EXECUTIVE_VISIBILITY,
        "Missing and stale evidence are visible in the executive view rather than "
        "absent from it.",
        probes.probe_missing_evidence_stays_unknown,
        "Restore the missing-source and staleness reporting in "
        "company/dashboard/builder.py.",
    ),
    _dashboard_cannot_approve,
    _decision_queue_refs,
    # test and build health
    _required_suites,
    _production_failures_separated,
    _sources_parse,
    _new_dependency,
    _network_or_model,
    # production boundary
    _no_publishing,
    _no_production_mutation,
    _no_delete,
    _integration_disabled,
    _capability_gaps,
)


__all__ = ["GateInputs", "GateScan", "evaluate"]
