"""The production integration gate.

Two kinds of test, kept apart on purpose.

**Synthetic.** The detectors - cycle finding, the import boundary, the write
scan - are driven by fixtures built in `tmp_path`. A three-node cycle proves
the cycle finder; a one-line module that writes into `sloped/` proves the write
scan. None of it depends on the state of this repository.

That separation matters here more than usual. On this branch's base the
`company-runtime` / `company-validation` capsules declare each other, and
another workstream is removing that edge. A test asserting "the repository has
a cycle" would pass today, fail the day the fix lands, and read as though the
fix broke something. So the repository-level tests assert the *shape* of the
answer - a cycle finding names its capsules, a blocker carries a remediation -
and never that a particular cycle is present.

**Real.** The report over this checkout is exercised for determinism, for the
policy being total, and for the gate holding none of the authority it checks
for - the same conditions it applies to every other subsystem, applied to
itself.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest

from company.integration import (
    ADVISORY_CHECKS,
    AUTHORIZATION_NOTE,
    DEFAULT_POLICY,
    REQUIRED_CHECKS,
    REQUIRED_SUITES,
    EvidenceKind,
    EvidenceSource,
    GateCategory,
    GateCheck,
    GatePolicy,
    GateStatus,
    IntegrationBlocker,
    IntegrationGateError,
    PolicyError,
    ProductionIntegrationReadinessReport,
    ReadinessReportStore,
    Readiness,
    ReportStoreError,
    SuiteEvidence,
    SuiteResult,
    assemble,
    blockers_for,
    build_report,
    capsule_dependency_graph,
    find_cycles,
    no_subagent_chain,
    render_cycle,
    render_text,
    reserved_action_drift,
    resolve_required_suites,
    subsystem_import_graph,
)
from knowledge.company_os.capsules import CapsuleIndex
from company.integration.boundary import (
    MODEL_MODULES,
    NETWORK_MODULES,
    PROCESS_MODULES,
    delete_call_violations,
    forbidden_import_violations,
    non_first_party_imports,
    process_spawn_violations,
    production_import_violations,
    production_write_violations,
)
from company.integration.checks import GateInputs, GateScan, evaluate
from company.integration.dependencies import build_dependency_graph
from company.integration.contracts import integration_still_gated
from company.integration.sources import (
    COMPANY_OS_ROOTS,
    DECLARED_PRODUCTION_ROOTS,
    module_imports,
    parse_tree,
)
from company.integration.__main__ import main as cli_main

REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF = dt.date(2026, 9, 17)


# --------------------------------------------------------------------------
# Fixtures and factories
# --------------------------------------------------------------------------


def a_check(
    check_id: str = "architecture.probe_condition",
    status: GateStatus = GateStatus.PASS,
    category: GateCategory = GateCategory.ARCHITECTURE,
    **kwargs,
) -> GateCheck:
    """One check with every status-specific field already consistent."""
    defaults: dict = {
        "requirement": "A condition the gate evaluates.",
        "detail": "What the gate observed.",
        "evidence_kind": EvidenceKind.REPOSITORY,
    }
    if status is GateStatus.FAIL:
        defaults["blocker_reason"] = "the condition does not hold"
        defaults["remediation"] = "make it hold"
    if status is GateStatus.UNKNOWN:
        defaults["missing_evidence"] = ("nobody has measured this",)
        defaults["remediation"] = "measure it"
    if status is GateStatus.NOT_APPLICABLE:
        defaults["not_applicable_reason"] = "the hazard cannot arise here"
    defaults.update(kwargs)
    return GateCheck(check_id=check_id, category=category, status=status, **defaults)


def a_report(*checks: GateCheck, required: tuple[str, ...], advisory: tuple[str, ...] = ()):
    """A report over exactly the supplied checks, with an explicit policy."""
    policy = GatePolicy(
        required=frozenset(required),
        advisory=frozenset(advisory),
        not_applicable_allowed=frozenset(),
    )
    inputs = GateInputs(repo_root=REPO_ROOT, as_of=AS_OF)
    return assemble(tuple(checks), inputs=inputs, policy=policy), policy


def a_source_tree(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def modules_of(root: Path, *roots: str):
    modules, failures = parse_tree(root, roots)
    assert failures == (), failures
    return modules


@pytest.fixture(scope="module")
def repo_scan():
    """Parse this checkout once. It is most of the cost of a run."""
    return GateScan.of(REPO_ROOT)


@pytest.fixture(scope="module")
def repo_report(repo_scan):
    """One real report, built once: every check runs, and they are not cheap."""
    return build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)


# --------------------------------------------------------------------------
# Readiness: what a required status does, and what an advisory one does not
# --------------------------------------------------------------------------


def test_every_required_check_passing_is_the_only_way_to_be_ready():
    report, _ = a_report(
        a_check("architecture.first"),
        a_check("execution.second", category=GateCategory.EXECUTION_SAFETY),
        required=("architecture.first", "execution.second"),
    )
    assert report.readiness is Readiness.READY
    assert report.blockers == ()
    assert report.open_blockers() == ()


def test_a_required_failure_blocks_readiness_and_produces_a_blocker():
    report, _ = a_report(
        a_check("architecture.first"),
        a_check("execution.second", GateStatus.FAIL, GateCategory.EXECUTION_SAFETY),
        required=("architecture.first", "execution.second"),
    )
    assert report.readiness is Readiness.BLOCKED
    assert [b.check_id for b in report.blockers] == ["execution.second"]


def test_a_required_unknown_blocks_readiness_and_is_not_a_pass():
    report, _ = a_report(
        a_check("architecture.first"),
        a_check("execution.second", GateStatus.UNKNOWN, GateCategory.EXECUTION_SAFETY),
        required=("architecture.first", "execution.second"),
    )
    assert report.readiness is Readiness.INSUFFICIENT_EVIDENCE
    assert report.readiness is not Readiness.READY
    blocker = report.blockers[0]
    assert blocker.check_id == "execution.second"
    assert "could not be established" in blocker.reason


def test_a_required_failure_outranks_a_required_unknown_in_the_verdict():
    report, _ = a_report(
        a_check("architecture.first", GateStatus.FAIL),
        a_check("execution.second", GateStatus.UNKNOWN, GateCategory.EXECUTION_SAFETY),
        required=("architecture.first", "execution.second"),
    )
    assert report.readiness is Readiness.BLOCKED
    assert len(report.blockers) == 2


def test_an_advisory_unknown_stays_visible_and_blocks_nothing():
    report, _ = a_report(
        a_check("architecture.first"),
        a_check("data.second", GateStatus.UNKNOWN, GateCategory.DATA_EVIDENCE),
        required=("architecture.first",),
        advisory=("data.second",),
    )
    assert report.readiness is Readiness.READY
    assert report.blockers == ()
    assert [c.check_id for c in report.unknowns()] == ["data.second"]
    assert [c.check_id for c in report.advisory_findings()] == ["data.second"]
    assert "data.second" in render_text(report)


def test_an_advisory_failure_is_reported_without_blocking():
    report, _ = a_report(
        a_check("architecture.first"),
        a_check("data.second", GateStatus.FAIL, GateCategory.DATA_EVIDENCE),
        required=("architecture.first",),
        advisory=("data.second",),
    )
    assert report.readiness is Readiness.READY
    assert [c.check_id for c in report.advisory_findings()] == ["data.second"]


def test_not_applicable_does_not_block_but_is_not_self_declared():
    """The one non-blocking status that is not a proof is allow-listed."""
    allowed = GatePolicy(
        required=frozenset({"architecture.first"}),
        advisory=frozenset(),
        not_applicable_allowed=frozenset({"architecture.first"}),
    )
    check = a_check("architecture.first", GateStatus.NOT_APPLICABLE)
    assert allowed.coerce(check) is check

    closed = GatePolicy(
        required=frozenset({"architecture.first"}),
        advisory=frozenset(),
        not_applicable_allowed=frozenset(),
    )
    coerced = closed.coerce(check)
    assert coerced.status is GateStatus.UNKNOWN
    assert coerced.missing_evidence
    assert coerced.remediation


# --------------------------------------------------------------------------
# No score, anywhere
# --------------------------------------------------------------------------


_SCORE_WORDS = ("score", "percent", "health_", "rating", "grade", "weight")


def test_the_report_exposes_no_readiness_score():
    report, _ = a_report(a_check("architecture.first"), required=("architecture.first",))
    payload = json.loads(report.canonical_json())

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not any(
                    word in key.casefold() for word in _SCORE_WORDS
                ), f"{path}.{key} looks like a score"
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload)
    assert not hasattr(report, "readiness_score")
    assert not hasattr(report, "health_score")
    assert report.readiness in set(Readiness)


def test_the_package_defines_no_scoring_identifier():
    """Not just absent from the output - absent from the source."""
    offenders = []
    for path in sorted((REPO_ROOT / "company/integration").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names = [node.id]
            for name in names:
                if any(word in name.casefold() for word in ("score", "percent_ready")):
                    offenders.append(f"{path.name}:{node.lineno} {name}")
    assert offenders == []


# --------------------------------------------------------------------------
# A check and a blocker refuse to be vague
# --------------------------------------------------------------------------


def test_a_failed_check_cannot_be_built_without_a_reason_and_a_remediation():
    with pytest.raises(IntegrationGateError, match="must say why it blocks"):
        GateCheck(
            check_id="architecture.first",
            category=GateCategory.ARCHITECTURE,
            status=GateStatus.FAIL,
            requirement="A condition.",
            detail="It does not hold.",
            evidence_kind=EvidenceKind.REPOSITORY,
        )
    with pytest.raises(IntegrationGateError, match="must name a remediation"):
        GateCheck(
            check_id="architecture.first",
            category=GateCategory.ARCHITECTURE,
            status=GateStatus.FAIL,
            requirement="A condition.",
            detail="It does not hold.",
            evidence_kind=EvidenceKind.REPOSITORY,
            blocker_reason="it does not hold",
        )


def test_an_unknown_check_must_name_the_evidence_it_could_not_get():
    with pytest.raises(IntegrationGateError, match="must name the evidence"):
        GateCheck(
            check_id="architecture.first",
            category=GateCategory.ARCHITECTURE,
            status=GateStatus.UNKNOWN,
            requirement="A condition.",
            detail="Nobody measured it.",
            evidence_kind=EvidenceKind.SUPPLIED,
            remediation="measure it",
        )


def test_a_check_lives_in_the_section_its_id_names():
    with pytest.raises(IntegrationGateError, match="is not category"):
        a_check("finance.first", category=GateCategory.ARCHITECTURE)


def test_a_passing_check_cannot_carry_a_blocker_reason():
    with pytest.raises(IntegrationGateError, match="only a failed check"):
        GateCheck(
            check_id="architecture.first",
            category=GateCategory.ARCHITECTURE,
            status=GateStatus.PASS,
            requirement="A condition.",
            detail="It holds.",
            evidence_kind=EvidenceKind.REPOSITORY,
            blocker_reason="but also it does not",
        )


def test_a_blocker_keeps_its_evidence_and_its_remediation():
    check = a_check(
        "architecture.first",
        GateStatus.FAIL,
        evidence=("company/runtime/authority.py:201", "company/permissions.yaml"),
        blocker_reason="the authority projection opened instead of closing",
        remediation="restore the empty projection",
    )
    blocker = blockers_for(
        (check,),
        GatePolicy(
            required=frozenset({"architecture.first"}),
            advisory=frozenset(),
            not_applicable_allowed=frozenset(),
        ),
    )[0]
    assert blocker.evidence == check.evidence
    assert blocker.remediation == "restore the empty projection"
    assert blocker.reason == "the authority projection opened instead of closing"
    assert blocker.resolved is False


def test_a_blocker_cannot_be_resolved_by_assertion():
    """"Probably fine" is not a resolution: resolving one needs evidence."""
    with pytest.raises(IntegrationGateError, match="resolved when evidence says so"):
        IntegrationBlocker(
            blocker_id="blocker-architecture.first",
            check_id="architecture.first",
            category=GateCategory.ARCHITECTURE,
            reason="the cycle is still declared",
            remediation="remove the edge",
            resolved=True,
        )
    resolved = IntegrationBlocker(
        blocker_id="blocker-architecture.first",
        check_id="architecture.first",
        category=GateCategory.ARCHITECTURE,
        reason="the cycle is still declared",
        remediation="remove the edge",
        resolved=True,
        resolution_evidence=("knowledge/company_os/capsules/seeds/company-runtime.json",),
    )
    assert resolved.resolved is True


# --------------------------------------------------------------------------
# The policy is total, and the split is explicit
# --------------------------------------------------------------------------


def test_the_policy_classifies_every_check_the_gate_produces():
    checks = evaluate(GateInputs(repo_root=REPO_ROOT, as_of=AS_OF))
    DEFAULT_POLICY.assert_covers(check.check_id for check in checks)
    assert {c.check_id for c in checks} == REQUIRED_CHECKS | ADVISORY_CHECKS


def test_an_unclassified_check_fails_the_run_rather_than_becoming_advisory():
    with pytest.raises(PolicyError, match="does not classify"):
        DEFAULT_POLICY.assert_covers(list(REQUIRED_CHECKS | ADVISORY_CHECKS) + ["health.invented"])


def test_a_classified_check_that_stops_running_fails_the_run():
    remaining = sorted(REQUIRED_CHECKS | ADVISORY_CHECKS)[1:]
    with pytest.raises(PolicyError, match="did not produce"):
        DEFAULT_POLICY.assert_covers(remaining)


def test_required_and_advisory_do_not_overlap():
    assert REQUIRED_CHECKS & ADVISORY_CHECKS == frozenset()
    with pytest.raises(PolicyError, match="required or advisory, never both"):
        GatePolicy(required=frozenset({"architecture.x"}), advisory=frozenset({"architecture.x"}))


def test_every_category_carries_at_least_one_required_check():
    by_category: dict[str, int] = {}
    for check_id in REQUIRED_CHECKS:
        by_category[check_id.split(".", 1)[0]] = by_category.get(check_id.split(".", 1)[0], 0) + 1
    assert set(by_category) == {category.value for category in GateCategory}


# --------------------------------------------------------------------------
# Cycle detection, on graphs that are not this repository
# --------------------------------------------------------------------------


def test_a_synthetic_acyclic_graph_has_no_cycle():
    assert find_cycles({"a": ["b", "c"], "b": ["c"], "c": [], "d": ["a"]}) == ()


def test_a_synthetic_two_node_cycle_is_found():
    assert find_cycles({"a": ["b"], "b": ["a"]}) == (("a", "b"),)


def test_a_synthetic_three_node_cycle_is_found_and_canonically_rotated():
    found = find_cycles({"b": ["c"], "c": ["a"], "a": ["b"]})
    assert found == (("a", "b", "c"),)
    assert render_cycle(found[0]) == "a -> b -> c -> a"


def test_a_self_loop_is_a_cycle_of_one():
    assert find_cycles({"a": ["a"]}) == (("a",),)


def test_two_disjoint_cycles_are_both_found_in_a_stable_order():
    graph = {"a": ["b"], "b": ["a"], "y": ["z"], "z": ["y"], "loose": ["a"]}
    assert find_cycles(graph) == (("a", "b"), ("y", "z"))


def test_an_edge_to_an_undefined_node_is_ignored_rather_than_invented():
    assert find_cycles({"a": ["nowhere"]}) == ()


def test_cycle_detection_is_deterministic_across_input_order():
    forward = find_cycles({"a": ["b"], "b": ["c"], "c": ["a"], "d": ["a"]})
    reverse = find_cycles({"d": ["a"], "c": ["a"], "b": ["c"], "a": ["b"]})
    assert forward == reverse


def test_the_capsule_graph_check_reports_whatever_the_store_declares(repo_report):
    """Shape, not contents: this must stay true after the cycle is removed."""
    check = repo_report.check("architecture.capsule_graph_acyclic")
    assert check.status in (GateStatus.PASS, GateStatus.FAIL)
    if check.status is GateStatus.FAIL:
        assert "->" in check.detail
        assert check.remediation
        blocker = next(b for b in repo_report.blockers if b.check_id == check.check_id)
        assert blocker.reason


def test_a_malformed_capsule_graph_is_surfaced_rather_than_crashing(tmp_path, repo_scan):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "broken.json").write_text("{ not json", encoding="utf-8")
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, capsule_root=seeds)
    check = report.check("architecture.capsule_graph_acyclic")
    assert check.status is GateStatus.UNKNOWN
    assert check.missing_evidence
    assert report.readiness is not Readiness.READY


def test_a_capsule_depending_on_a_capsule_nobody_defines_is_surfaced(tmp_path, repo_scan):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    source = REPO_ROOT / "knowledge/company_os/capsules/seeds/company-validation.json"
    capsule = json.loads(source.read_text(encoding="utf-8"))
    capsule["dependencies"] = ["a-capsule-nobody-wrote"]
    (seeds / "company-validation.json").write_text(json.dumps(capsule), encoding="utf-8")
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, capsule_root=seeds)
    integrity = report.check("architecture.capsule_graph_integrity")
    assert integrity.status is GateStatus.FAIL
    assert "a-capsule-nobody-wrote" in integrity.detail


# --------------------------------------------------------------------------
# The inbound boundary: production may not import Company OS
# --------------------------------------------------------------------------


def test_a_production_module_importing_company_os_is_detected_by_file_and_line(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "sloped/scale.py": "SCALE = 1.0\n",
            "sloped/cameras.py": "import math\nfrom company.runtime import plan_task\n",
        },
    )
    findings = production_import_violations(modules_of(tmp_path, "sloped"))
    assert len(findings) == 1
    assert findings[0].path == "sloped/cameras.py"
    assert findings[0].line == 2
    assert "company.runtime" in findings[0].detail


def test_every_spelling_of_a_company_os_import_is_caught(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "engine/__init__.py": "",
            "engine/a.py": "import company.runtime as rt\n",
            "engine/b.py": "from company import runtime\n",
            "engine/c.py": "from knowledge.company_os.capsules import CapsuleIndex\n",
            "engine/d.py": "import ai_platform\n",
        },
    )
    findings = production_import_violations(modules_of(tmp_path, "engine"))
    assert [f.path for f in findings] == [
        "engine/a.py",
        "engine/b.py",
        "engine/c.py",
        "engine/d.py",
    ]


def test_a_relative_import_resolves_to_the_absolute_name_it_means(tmp_path):
    """The subsystem graph is only right if `from .x import y` resolves."""
    a_source_tree(
        tmp_path,
        {
            "company/__init__.py": "",
            "company/runtime/__init__.py": "",
            "company/runtime/config.py": (
                "from .errors import Boom\nfrom ..validation import check\n"
            ),
        },
    )
    modules = modules_of(tmp_path, "company")
    config = next(m for m in modules if m.path.endswith("config.py"))
    assert [ref.module for ref in module_imports(config)] == [
        "company.runtime.errors",
        "company.validation",
    ]


def test_a_clean_production_tree_passes(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "sloped/scale.py": "import math\nfrom .cameras import rig\n",
            "sloped/cameras.py": "def rig():\n    return None\n",
        },
    )
    assert production_import_violations(modules_of(tmp_path, "sloped")) == ()


def test_this_repository_production_tree_does_not_import_company_os(repo_report):
    check = repo_report.check("architecture.production_does_not_import_company_os")
    assert check.status is GateStatus.PASS, check.detail


def test_this_repository_production_tests_do_not_import_company_os(repo_report):
    check = repo_report.check("architecture.production_tests_independent")
    assert check.status is GateStatus.PASS, check.detail


# --------------------------------------------------------------------------
# The outbound boundary: Company OS may not reach into production
# --------------------------------------------------------------------------


def test_a_company_os_module_writing_into_production_is_detected(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "company/rogue/__init__.py": "",
            "company/rogue/writer.py": (
                "from pathlib import Path\n\n\n"
                "def ship(text):\n"
                "    Path('sloped/scale.py').write_text(text)\n"
            ),
        },
    )
    findings = production_write_violations(modules_of(tmp_path, "company"), ("sloped",))
    assert len(findings) == 1
    assert findings[0].path == "company/rogue/writer.py"
    assert "sloped/scale.py" in findings[0].detail


def test_a_rename_into_production_through_a_variable_is_still_detected(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "company/rogue/__init__.py": "",
            "company/rogue/mover.py": (
                "def ship(destination):\n    destination.rename('engine/core.py')\n"
            ),
        },
    )
    findings = production_write_violations(modules_of(tmp_path, "company"), ("engine",))
    assert [f.path for f in findings] == ["company/rogue/mover.py"]


def test_a_store_writing_where_its_caller_points_is_not_a_production_write(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "company/store/__init__.py": "",
            "company/store/put.py": (
                "from pathlib import Path\n\n\n"
                "def put(output_dir, name, payload):\n"
                "    Path(output_dir, name).write_text(payload)\n"
            ),
        },
    )
    assert production_write_violations(modules_of(tmp_path, "company"), ("sloped", "engine")) == ()


def test_dataclasses_replace_is_not_mistaken_for_a_filesystem_write(tmp_path):
    """The distinction the whole write scan rests on."""
    a_source_tree(
        tmp_path,
        {
            "company/x/__init__.py": "",
            "company/x/y.py": (
                "import dataclasses\n\n\n"
                "def widen(snapshot):\n"
                "    return dataclasses.replace(snapshot, may_write=('sloped',))\n\n\n"
                "def normalise(text):\n"
                "    return text.replace('sloped\\\\a', 'sloped/a')\n"
            ),
        },
    )
    assert production_write_violations(modules_of(tmp_path, "company"), ("sloped",)) == ()


def test_a_delete_call_is_detected_and_a_list_remove_is_not(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "company/x/__init__.py": "",
            "company/x/cleaner.py": (
                "import shutil\n\n\n"
                "def wipe(directory, names):\n"
                "    names.remove('keep')\n"
                "    shutil.rmtree(directory)\n"
            ),
        },
    )
    findings = delete_call_violations(modules_of(tmp_path, "company"))
    assert len(findings) == 1
    assert findings[0].line == 6
    assert "rmtree" in findings[0].detail


def test_a_subprocess_import_and_an_os_system_call_are_both_detected(tmp_path):
    a_source_tree(
        tmp_path,
        {
            "company/x/__init__.py": "",
            "company/x/shell.py": "import os\nimport subprocess\n\n\ndef go():\n    os.system('ls')\n",
        },
    )
    findings = process_spawn_violations(modules_of(tmp_path, "company"))
    assert {f.line for f in findings} == {2, 6}


def test_a_network_client_import_is_detected(tmp_path):
    a_source_tree(
        tmp_path,
        {"company/x/__init__.py": "", "company/x/fetch.py": "import urllib.request\n"},
    )
    findings = forbidden_import_violations(
        modules_of(tmp_path, "company"), NETWORK_MODULES, "no network"
    )
    assert [f.line for f in findings] == [1]


def test_a_third_party_import_is_detected_as_a_new_dependency(tmp_path):
    a_source_tree(
        tmp_path,
        {"company/x/__init__.py": "", "company/x/n.py": "import json\nimport numpy as np\n"},
    )
    findings = non_first_party_imports(modules_of(tmp_path, "company"), COMPANY_OS_ROOTS)
    assert [f.line for f in findings] == [2]


# --------------------------------------------------------------------------
# The gate is subject to its own conditions
# --------------------------------------------------------------------------


def test_the_gate_package_imports_no_production_module():
    modules = modules_of(REPO_ROOT, "company/integration")
    production = set(DECLARED_PRODUCTION_ROOTS)
    offenders = [
        f"{m.path}:{ref.line} {ref.module}"
        for m in modules
        for ref in module_imports(m)
        if ref.root in production
    ]
    assert offenders == []


def test_the_gate_package_has_no_external_dependency():
    assert non_first_party_imports(modules_of(REPO_ROOT, "company/integration"), COMPANY_OS_ROOTS) == ()


def test_the_gate_package_reaches_no_network_model_or_shell():
    modules = modules_of(REPO_ROOT, "company/integration")
    assert forbidden_import_violations(modules, NETWORK_MODULES | MODEL_MODULES, "x") == ()
    assert forbidden_import_violations(modules, PROCESS_MODULES, "x") == ()
    assert process_spawn_violations(modules) == ()


def test_the_gate_package_deletes_nothing():
    assert delete_call_violations(modules_of(REPO_ROOT, "company/integration")) == ()


def test_the_gate_package_writes_into_no_production_tree(repo_scan):
    scan = repo_scan
    modules = [m for m in scan.company_modules if m.path.startswith("company/integration/")]
    assert production_write_violations(tuple(modules), scan.scanned_production_roots) == ()


def test_no_production_module_imports_the_gate_package(repo_scan):
    scan = repo_scan
    offenders = [
        f"{m.path}:{ref.line}"
        for m in scan.production_modules
        for ref in module_imports(m)
        if ref.module.startswith("company.integration")
    ]
    assert offenders == []


def test_no_other_company_os_subsystem_imports_the_gate(repo_scan):
    """The gate reads Company OS and is read by none of it."""
    scan = repo_scan
    offenders = [
        f"{m.path}:{ref.line}"
        for m in scan.company_modules
        if not m.path.startswith("company/integration/")
        for ref in module_imports(m)
        if ref.module.startswith("company.integration")
    ]
    assert offenders == []


def test_adding_the_gate_introduced_no_capsule_cycle():
    from knowledge.company_os.capsules import CapsuleIndex

    index = CapsuleIndex.load(REPO_ROOT / "knowledge/company_os/capsules/seeds")
    cycles = find_cycles(capsule_dependency_graph(index))
    assert all("company-production-integration-gate" not in cycle for cycle in cycles)


def test_the_company_os_import_graph_has_no_runtime_cycle(repo_report, repo_scan):
    check = repo_report.check("architecture.no_subsystem_import_cycle")
    assert check.status is GateStatus.PASS, check.detail
    graph = subsystem_import_graph(repo_scan.company_modules)
    assert "company/integration" in graph


# --------------------------------------------------------------------------
# Contract drift: CEO-reserved actions and the no-subagent chain
# --------------------------------------------------------------------------


def test_ceo_reserved_drift_is_surfaced_when_an_action_is_removed():
    intact = {"ceo_reserved": sorted(__import__("company.integration.contracts",
                                                fromlist=["x"]).REQUIRED_RESERVED_ACTIONS)}
    assert reserved_action_drift(intact).ok

    thinned = {
        "ceo_reserved": [a for a in intact["ceo_reserved"] if a != "publish_public_video"]
    }
    drift = reserved_action_drift(thinned)
    assert not drift.ok
    assert any("publish_public_video" in item for item in drift.missing)


def test_a_longer_reserved_list_is_not_drift():
    from company.integration.contracts import REQUIRED_RESERVED_ACTIONS

    wider = {"ceo_reserved": sorted(REQUIRED_RESERVED_ACTIONS) + ["something_else_entirely"]}
    drift = reserved_action_drift(wider)
    assert drift.ok
    assert drift.unrecognised == ("something_else_entirely",)


def test_the_repository_still_reserves_every_action_the_gate_depends_on(repo_report):
    check = repo_report.check("workforce.ceo_reserved_actions_present")
    assert check.status is GateStatus.PASS, check.detail


def test_no_subagent_drift_is_surfaced_link_by_link(tmp_path):
    class Config:
        permissions = {"bootstrap_defaults": {"no_subagents": False}, "ceo_reserved": []}
        org_registry = {"global_constraints": {"nested_agent_spawning": True}}
        agent_contract_schema = {"required_fields": [], "template": {}}

    (tmp_path / "company").mkdir()
    (tmp_path / "company/constitution.md").write_text("# nothing here\n", encoding="utf-8")
    links = no_subagent_chain(tmp_path, Config())
    assert all(not link.present for link in links)
    assert len(links) == 8
    assert all(link.detail for link in links)


def test_the_repository_no_subagent_chain_is_intact(repo_report):
    check = repo_report.check("execution.no_subagent_runtime_lock")
    assert check.status is GateStatus.PASS, check.detail
    from company.runtime.config import load_company_config

    links = no_subagent_chain(REPO_ROOT, load_company_config(REPO_ROOT / "company"))
    assert [link.name for link in links if not link.present] == []


def test_the_no_subagent_invariant_itself_is_untouched_by_this_package():
    """This phase reads the policy; it does not reimplement or relax it."""
    from ai_platform.policy import BOOTSTRAP_POLICY, ExecutionPolicy, SubagentPolicyViolation

    assert BOOTSTRAP_POLICY.no_subagents is True
    assert BOOTSTRAP_POLICY.allows_nested_agents is False
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(no_subagents=False)


def test_the_gating_claim_in_the_control_plane_capsule_is_read_not_asserted():
    held, detail = integration_still_gated(
        ("Company OS stays unconnected to production execution until the integration gate passes.",)
    )
    assert held and detail
    gone, reason = integration_still_gated(("Something else entirely.",))
    assert not gone
    assert "integration gate" in reason


# --------------------------------------------------------------------------
# Supplied suite evidence, and going stale
# --------------------------------------------------------------------------


def a_suite(name: str, *, passed: bool = True, day: int = 17, company_os: bool = True):
    return SuiteResult(
        suite=name,
        passed=passed,
        observed_on=dt.date(2026, 9, day),
        reported_by="tests/test_company_integration_gate.py",
        selected=1,
        failed=0 if passed else 1,
        company_os=company_os,
    )


_GRAPH: list = []


def _repo_graph():
    """The import graph, built once for this module.

    Cached in a list rather than recomputed because it is a pure function of
    the checkout and several fixtures want it; building it per call made this
    file the slowest in the suite.
    """
    if not _GRAPH:
        _GRAPH.append(build_dependency_graph(GateScan.of(REPO_ROOT)))
    return _GRAPH[0]


def required_here(**kwargs) -> tuple[str, ...]:
    """The suites this checkout actually requires, derived the way the gate does.

    Not `REQUIRED_SUITES`. That constant is only the canonical floor; the gate
    derives the rest from the active capsules, so a fixture built from the
    constant would supply eleven results against a thirty-suite demand and
    every test below would be exercising the missing-evidence path by accident.

    The same argument now covers the dependency graph, which P6B made the
    fourth source. Omitting it does not derive a smaller set quietly - it
    makes the set *unresolved* - but the effect on a fixture is identical:
    every test below would silently become a test of the unknown path.
    """
    return resolve_required_suites(
        CapsuleIndex.load(REPO_ROOT / "knowledge/company_os/capsules/seeds"),
        graph=_repo_graph(),
        **kwargs,
    ).names()


def green_evidence(**kwargs) -> SuiteEvidence:
    return SuiteEvidence(tuple(a_suite(name, **kwargs) for name in required_here()))


def test_the_derived_set_never_loses_the_canonical_floor():
    """`REQUIRED_SUITES` is a floor the derivation adds to, never a list it
    replaces. One of its members is declared by no capsule, so a derivation
    that dropped the floor would quietly stop requiring it."""
    assert set(REQUIRED_SUITES) <= set(required_here())
    assert len(required_here()) > len(REQUIRED_SUITES)


def test_without_supplied_suite_results_the_suite_condition_is_unknown(repo_report):
    check = repo_report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert check.missing_evidence
    assert repo_report.readiness is not Readiness.READY


def test_supplied_passing_results_satisfy_the_suite_condition(repo_scan):
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=green_evidence())
    assert report.check("health.required_suites_pass").status is GateStatus.PASS


def test_a_reported_failure_fails_the_suite_condition(repo_scan):
    evidence = SuiteEvidence(
        tuple(
            a_suite(name, passed=name != "tests/test_company_runtime.py")
            for name in required_here()
        )
    )
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=evidence)
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.FAIL
    assert "test_company_runtime" in check.detail


def test_stale_suite_evidence_is_visible_and_does_not_count_as_a_pass(repo_scan):
    stale = SuiteEvidence(
        tuple(a_suite(name, day=1) for name in required_here()), max_age_days=7
    )
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=stale)
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert any("16 days ago" in item for item in check.missing_evidence)
    assert report.readiness is not Readiness.READY


def test_a_suite_result_cannot_claim_to_pass_while_reporting_failures():
    with pytest.raises(IntegrationGateError, match="reported as passing"):
        SuiteResult(
            suite="tests/test_company_runtime.py",
            passed=True,
            observed_on=AS_OF,
            reported_by="somebody",
            failed=3,
        )


def test_supplied_evidence_refuses_a_field_outside_its_schema():
    with pytest.raises(IntegrationGateError, match="unknown field"):
        SuiteResult.from_dict(
            {
                "suite": "tests/test_company_runtime.py",
                "passed": True,
                "observed_on": "2026-09-17",
                "reported_by": "somebody",
                "and_also": "trust me",
            }
        )


def test_production_environment_failures_are_separated_from_company_os_ones(repo_scan):
    evidence = SuiteEvidence(
        tuple(a_suite(name) for name in required_here())
        + (a_suite("tests/test_sloped_scale.py", passed=False, company_os=False),)
    )
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=evidence)
    separated = report.check("health.production_failures_separated")
    assert separated.status is GateStatus.PASS
    assert report.check("health.required_suites_pass").status is GateStatus.PASS


def test_suite_evidence_loads_from_a_file(tmp_path):
    path = tmp_path / "suites.json"
    path.write_text(
        json.dumps(
            {
                "max_age_days": 30,
                "results": [
                    {
                        "suite": "tests/test_company_runtime.py",
                        "passed": True,
                        "observed_on": "2026-09-17",
                        "reported_by": "a session",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = SuiteEvidence.from_path(path)
    assert evidence.max_age_days == 30
    assert evidence.get("tests/test_company_runtime.py").passed


# --------------------------------------------------------------------------
# Determinism, provenance and freshness of the report itself
# --------------------------------------------------------------------------


def test_the_canonical_json_is_byte_identical_across_runs(repo_scan):
    first = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    second = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    assert first.canonical_json() == second.canonical_json()
    assert first.report_id == second.report_id


def test_the_report_is_tied_to_a_source_commit_and_a_schema_version(repo_report):
    assert repo_report.schema_version == 1
    assert repo_report.policy_version == DEFAULT_POLICY.version
    assert repo_report.as_of == AS_OF
    assert repo_report.report_id.startswith(f"integration-readiness-{AS_OF.isoformat()}-")
    assert len(repo_report.source.source_commit) in (0, 40, 64)


def test_a_report_from_another_commit_is_reported_as_stale():
    report, _ = a_report(a_check("architecture.first"), required=("architecture.first",))
    dated = ProductionIntegrationReadinessReport(
        as_of=AS_OF,
        source=EvidenceSource(repo_root=".", source_commit="a" * 40, source_branch="main"),
        policy_version=1,
        sections=report.sections,
        required_check_ids=report.required_check_ids,
    )
    assert dated.stale_against("a" * 40) == ""
    assert "re-run the gate" in dated.stale_against("b" * 40)

    undated = ProductionIntegrationReadinessReport(
        as_of=AS_OF,
        source=EvidenceSource(repo_root="."),
        policy_version=1,
        sections=report.sections,
        required_check_ids=report.required_check_ids,
    )
    assert "did not record a source commit" in undated.stale_against("a" * 40)


def test_every_check_carries_the_date_of_the_evidence_behind_it(repo_report):
    assert all(check.evidence_as_of is not None for check in repo_report.checks())


def test_a_different_as_of_produces_a_different_report_identity(repo_scan):
    first = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    second = build_report(REPO_ROOT, as_of=dt.date(2026, 9, 18), scan=repo_scan)
    assert first.report_id != second.report_id


# --------------------------------------------------------------------------
# READY is not permission
# --------------------------------------------------------------------------


def test_even_a_ready_report_does_not_authorize_production_integration():
    report, _ = a_report(a_check("architecture.first"), required=("architecture.first",))
    assert report.readiness is Readiness.READY
    assert report.authorizes_production_integration is False
    assert AUTHORIZATION_NOTE in render_text(report)
    assert json.loads(report.canonical_json())["authorizes_production_integration"] is False


def test_a_report_claiming_to_authorize_integration_cannot_be_built():
    report, _ = a_report(a_check("architecture.first"), required=("architecture.first",))
    with pytest.raises(IntegrationGateError, match="never authorizes"):
        ProductionIntegrationReadinessReport(
            as_of=AS_OF,
            source=EvidenceSource(repo_root="."),
            policy_version=1,
            sections=report.sections,
            authorizes_production_integration=True,
        )


def test_the_note_names_the_ceo_reserved_decision_that_actually_governs_it():
    assert "merge_major_architecture_rewrite" in AUTHORIZATION_NOTE
    assert "does not authorize" in AUTHORIZATION_NOTE


# --------------------------------------------------------------------------
# The store: append-only, in a directory the caller names
# --------------------------------------------------------------------------


def test_a_report_is_written_once_and_re_written_identically_without_complaint(tmp_path, repo_scan):
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    store = ReadinessReportStore(tmp_path)
    first = store.put(report)
    second = store.put(report)
    assert first == second
    assert store.ids() == (report.report_id,)
    assert store.get(report.report_id)["as_of"] == AS_OF.isoformat()


def test_a_differing_report_under_the_same_identity_is_refused(tmp_path, repo_scan):
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    store = ReadinessReportStore(tmp_path)
    store.put(report)
    store.path_for(report.report_id).write_bytes(b'{"as_of": "1999-01-01"}')
    with pytest.raises(ReportStoreError, match="refusing to overwrite"):
        store.put(report)


def test_the_store_writes_only_under_the_directory_it_was_given(tmp_path, repo_scan):
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan)
    store = ReadinessReportStore(tmp_path / "reports")
    path = store.put(report)
    assert (tmp_path / "reports") in path.parents
    assert list(tmp_path.iterdir()) == [tmp_path / "reports"]


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------


def test_the_cli_prints_a_deterministic_report_and_exits_on_the_verdict(capsys):
    code = cli_main(["check", "--repo-root", str(REPO_ROOT), "--as-of", AS_OF.isoformat()])
    first = capsys.readouterr().out
    cli_main(["check", "--repo-root", str(REPO_ROOT), "--as-of", AS_OF.isoformat()])
    second = capsys.readouterr().out
    assert first == second
    assert code in (0, 1, 2)
    assert first.startswith("PRODUCTION INTEGRATION READINESS: ")
    assert AUTHORIZATION_NOTE in first


def test_the_cli_json_output_is_the_canonical_report(capsys, repo_report):
    cli_main(
        ["check", "--repo-root", str(REPO_ROOT), "--as-of", AS_OF.isoformat(), "--json"]
    )
    printed = capsys.readouterr().out
    assert printed == repo_report.canonical_json()
    assert json.loads(printed)["authorizes_production_integration"] is False


def test_the_cli_writes_nothing_unless_an_output_directory_is_named(tmp_path, capsys):
    cli_main(["check", "--repo-root", str(REPO_ROOT), "--as-of", AS_OF.isoformat()])
    capsys.readouterr()
    assert list(tmp_path.iterdir()) == []

    cli_main(
        [
            "check",
            "--repo-root",
            str(REPO_ROOT),
            "--as-of",
            AS_OF.isoformat(),
            "--output-dir",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    assert (tmp_path / "readiness").is_dir()


def test_the_cli_prints_the_policy_split(capsys):
    assert cli_main(["policy"]) == 0
    printed = capsys.readouterr().out
    assert f"required ({len(REQUIRED_CHECKS)})" in printed
    assert f"advisory ({len(ADVISORY_CHECKS)})" in printed
    assert "score" not in printed.casefold()


# --------------------------------------------------------------------------
# The report over this repository
# --------------------------------------------------------------------------


def test_the_report_covers_every_category_and_every_classified_check(repo_report):
    assert {section.category for section in repo_report.sections} == set(GateCategory)
    assert set(repo_report.required_check_ids) == REQUIRED_CHECKS
    assert set(repo_report.advisory_check_ids) == ADVISORY_CHECKS


def test_every_blocker_in_the_real_report_is_actionable(repo_report):
    for blocker in repo_report.blockers:
        assert blocker.reason.strip()
        assert blocker.remediation.strip()
        assert blocker.check_id in REQUIRED_CHECKS
        assert not repo_report.check(blocker.check_id).satisfied


def test_the_real_report_has_one_blocker_per_unsatisfied_required_check(repo_report):
    unsatisfied = {c.check_id for c in repo_report.required_checks() if not c.satisfied}
    assert {b.check_id for b in repo_report.blockers} == unsatisfied


def test_execution_safety_and_the_production_boundary_hold_today(repo_report):
    """The conditions that would make crossing the boundary unsafe, not merely untidy."""
    for check_id in sorted(REQUIRED_CHECKS):
        if check_id.startswith(("execution.", "production.", "data.", "finance.", "analytics.")):
            assert repo_report.check(check_id).status is GateStatus.PASS, repo_report.check(
                check_id
            ).detail


def test_the_rendered_report_names_the_verdict_the_blockers_and_the_unknowns(repo_report):
    text = render_text(repo_report)
    assert repo_report.readiness.value.upper() in text
    for blocker in repo_report.open_blockers():
        assert blocker.check_id in text
    for check in repo_report.unknowns():
        assert check.check_id in text
