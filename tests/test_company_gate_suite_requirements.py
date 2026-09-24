"""The integration gate's required-suite set, derived rather than written down.

The regression this file exists for is real and dated. On 2026-09-24 the P5
candidate was merged to `main` after reaching READY, while two tests declared
by the active `company-research-intelligence` capsule were failing at its own
tip. The gate never asked about them, because `REQUIRED_SUITES` is a static
list of eleven canonical suites and neither name was in it.

`test_the_p5_integration_miss_is_reproduced_and_now_blocks` is that exact
situation, reconstructed from a synthetic capsule store so it cannot rot when
the real seeds change, and it fails on the old behaviour.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest

from company.integration import (
    REQUIRED_SUITES,
    GateStatus,
    Readiness,
    RequiredSuites,
    SuiteEvidence,
    SuiteOrigin,
    SuiteRequirement,
    SuiteResult,
    build_report,
    resolve_required_suites,
    undeclared_company_os_suites,
)
from company.integration.checks import GateScan
from company.integration.errors import IntegrationGateError
from company.integration.__main__ import main as integration_main
from knowledge.company_os.capsules import CapsuleIndex


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = REPO_ROOT / "knowledge/company_os/capsules/seeds"
AS_OF = dt.date(2026, 9, 24)


@pytest.fixture(scope="module")
def index() -> CapsuleIndex:
    return CapsuleIndex.load(SEED_ROOT)


@pytest.fixture(scope="module")
def repo_scan() -> GateScan:
    return GateScan.of(REPO_ROOT)


# --------------------------------------------------------------------------
# What the set is made of
# --------------------------------------------------------------------------


def test_the_canonical_floor_is_always_required(index):
    """Every hand-written canonical suite survives derivation.

    The floor exists because one of its members - the execution transport
    suite - is required by the gate's own checks and declared by no capsule.
    Derivation must not lose it.
    """
    required = resolve_required_suites(index)
    assert set(REQUIRED_SUITES) <= set(required.names())
    assert required.resolved


def test_a_suite_declared_only_by_a_capsule_is_still_required(index):
    required = resolve_required_suites(index)
    item = required.get("tests/test_company_os_research_ingestion.py")
    assert item is not None
    assert item.suite not in REQUIRED_SUITES
    assert SuiteOrigin.ACTIVE_CAPSULE in item.origins
    assert "company-research-intelligence" in item.capsule_ids


def test_every_requirement_names_why_it_is_required(index):
    for item in resolve_required_suites(index):
        assert item.origins
        assert item.reason()


def test_the_set_is_deterministic_and_fingerprinted(index):
    first = resolve_required_suites(index)
    second = resolve_required_suites(CapsuleIndex.load(SEED_ROOT))
    assert first.names() == second.names()
    assert first.fingerprint() == second.fingerprint()


def test_a_suite_required_twice_over_keeps_both_reasons(index):
    """Canonical *and* capsule-declared is the common case, and says more."""
    item = resolve_required_suites(index).get("tests/test_company_runtime.py")
    assert item is not None
    assert SuiteOrigin.CANONICAL in item.origins
    assert SuiteOrigin.ACTIVE_CAPSULE in item.origins


# --------------------------------------------------------------------------
# Change scope widens, and only widens
# --------------------------------------------------------------------------


def test_change_scope_never_shrinks_the_set(index):
    """A gate that got cheaper when you described the change less fully would
    have a dial on it. Every scoped set is a superset of the unscoped one."""
    unscoped = set(resolve_required_suites(index).names())
    for scope in (
        ("company/runtime/context_assembly.py",),
        ("sloped/scale.py",),
        ("README.md",),
        (),
    ):
        scoped = set(resolve_required_suites(index, changed_paths=scope).names())
        assert unscoped <= scoped, scope


def test_a_changed_company_os_test_file_requires_its_own_evidence(index):
    required = resolve_required_suites(
        index, changed_paths=("tests/test_company_youtube_live_findings.py",)
    )
    item = required.get("tests/test_company_youtube_live_findings.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins


def test_a_changed_production_test_is_not_pulled_into_the_company_os_gate(index):
    """`health.production_failures_separated` is where a production suite is
    reported. Requiring it here would make a missing render dependency read as
    a control-plane blocker."""
    required = resolve_required_suites(index, changed_paths=("tests/test_sloped_scale.py",))
    assert required.get("tests/test_sloped_scale.py") is None


def test_scope_on_an_owned_path_marks_that_capsules_suites(index):
    required = resolve_required_suites(
        index, changed_paths=("company/runtime/context_cache.py",)
    )
    item = required.get("tests/test_company_context_assembly.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins
    assert "company-runtime" in item.capsule_ids


# --------------------------------------------------------------------------
# What cannot be worked out stays unknown
# --------------------------------------------------------------------------


def test_an_unreadable_capsule_store_leaves_the_set_unresolved():
    required = resolve_required_suites(None)
    assert not required.resolved
    assert required.unresolved
    assert set(required.names()) == set(REQUIRED_SUITES)


def test_an_unresolved_set_makes_the_gate_condition_unknown(repo_scan, tmp_path):
    """The whole safety property, end to end: a capsule store the gate cannot
    read must not produce a green suite condition, however much evidence was
    supplied."""
    empty = tmp_path / "no-seeds"
    empty.mkdir()
    evidence = SuiteEvidence(
        tuple(_result(name) for name in resolve_required_suites(None).names())
    )
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=empty,
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert check.missing_evidence
    assert report.readiness is not Readiness.READY


def test_a_requirement_with_no_origin_is_refused():
    with pytest.raises(IntegrationGateError, match="no origin"):
        SuiteRequirement(suite="tests/test_company_runtime.py", origins=())


def test_the_same_suite_cannot_be_required_twice():
    item = SuiteRequirement(
        suite="tests/test_company_runtime.py", origins=(SuiteOrigin.CANONICAL,)
    )
    with pytest.raises(IntegrationGateError, match="twice"):
        RequiredSuites(requirements=(item, item))


# --------------------------------------------------------------------------
# The P5 miss
# --------------------------------------------------------------------------


def _capsule_json(
    capsule_id: str,
    *,
    owns: list[str],
    tests: list[str],
    status: str = "active",
) -> dict:
    return {
        "id": capsule_id,
        "type": "module",
        "title": capsule_id.replace("-", " ").title()[:80],
        "purpose": f"Synthetic capsule {capsule_id} for the required-suite tests.",
        "owner": "workstream-claude",
        "source": "tests/test_company_gate_suite_requirements.py",
        "created": "2026-09-16",
        "last_reviewed": "2026-09-16",
        "recheck_on": "2027-09-16",
        "freshness": "slow_changing",
        "status": status,
        "owns_paths": owns,
        "tests": tests,
        "invariants": ["A synthetic capsule states one invariant so it can be built."],
    }


@pytest.fixture
def synthetic_seeds(tmp_path) -> Path:
    root = tmp_path / "seeds"
    root.mkdir()
    for capsule in (
        _capsule_json(
            "synthetic-research",
            owns=["intelligence/research"],
            tests=["tests/test_company_os_research_ingestion.py"],
        ),
        _capsule_json(
            "synthetic-retired",
            owns=["intelligence/__init__.py"],
            tests=["tests/test_company_os_research_batches.py"],
            status="retired",
        ),
    ):
        (root / f"{capsule['id']}.json").write_text(
            json.dumps(capsule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return root


def _result(suite: str, *, passed: bool = True, day: int = 24) -> SuiteResult:
    return SuiteResult(
        suite=suite,
        passed=passed,
        observed_on=dt.date(2026, 9, day),
        reported_by="tests/test_company_gate_suite_requirements.py",
        selected=1,
        failed=0 if passed else 1,
    )


def test_the_p5_integration_miss_is_reproduced_and_now_blocks(repo_scan, synthetic_seeds):
    """The exact 2026-09-24 shape: every canonical suite green, one
    capsule-declared suite red, and the old gate said READY.

    Built on a synthetic capsule store so the reproduction survives the real
    seeds being edited. `tests/test_company_os_research_ingestion.py` is not in
    `REQUIRED_SUITES` and is declared by an active capsule, which is the whole
    of the defect.
    """
    red = "tests/test_company_os_research_ingestion.py"
    assert red not in REQUIRED_SUITES

    evidence = SuiteEvidence(
        tuple(_result(name) for name in REQUIRED_SUITES) + (_result(red, passed=False),)
    )
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=synthetic_seeds,
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.FAIL
    assert red in check.blocker_reason
    assert "synthetic-research" in check.blocker_reason
    assert report.readiness is Readiness.BLOCKED


def test_a_capsule_declared_suite_with_no_evidence_is_unknown_not_pass(
    repo_scan, synthetic_seeds
):
    """Missing evidence must stay missing. This is the other half of the miss:
    had nobody run the suite at all, silence would have read as green."""
    evidence = SuiteEvidence(tuple(_result(name) for name in REQUIRED_SUITES))
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=synthetic_seeds,
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert any(
        "tests/test_company_os_research_ingestion.py" in item
        for item in check.missing_evidence
    )
    assert report.readiness is not Readiness.READY


def test_a_retired_capsules_tests_are_not_required(repo_scan, synthetic_seeds):
    """A contract that is no longer in force does not demand evidence."""
    required = resolve_required_suites(CapsuleIndex.load(synthetic_seeds))
    assert required.get("tests/test_company_os_research_batches.py") is None


def test_a_retired_capsules_tests_return_when_the_change_touches_it(synthetic_seeds):
    """Scope reaches what status alone does not: editing a retired capsule's
    own code is exactly when its tests matter again."""
    required = resolve_required_suites(
        CapsuleIndex.load(synthetic_seeds),
        changed_paths=("intelligence/__init__.py",),
    )
    item = required.get("tests/test_company_os_research_batches.py")
    assert item is not None
    assert item.origins == (SuiteOrigin.CHANGE_SCOPE,)


def test_a_supplied_red_company_os_suite_is_not_discarded(repo_scan, synthetic_seeds):
    """Evidence the caller handed over does not disappear for want of a
    contract. No capsule declares this suite; the reporter still called it
    Company OS and called it red."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(
                CapsuleIndex.load(synthetic_seeds)
            ).names()
        )
        + (_result("tests/test_company_youtube_live_findings.py", passed=False),)
    )
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=synthetic_seeds,
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.FAIL
    assert "tests/test_company_youtube_live_findings.py" in check.evidence


def test_a_supplied_red_production_suite_still_does_not_block(repo_scan, synthetic_seeds):
    """The separation the gate already makes survives the widening: a
    production-environment failure is reported by its own check."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(
                CapsuleIndex.load(synthetic_seeds)
            ).names()
        )
        + (
            SuiteResult(
                suite="tests/test_sloped_scale.py",
                passed=False,
                observed_on=dt.date(2026, 9, 24),
                reported_by="tests/test_company_gate_suite_requirements.py",
                failed=1,
                company_os=False,
            ),
        )
    )
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=synthetic_seeds,
    )
    assert report.check("health.required_suites_pass").status is GateStatus.PASS
    assert report.check("health.production_failures_separated").status is GateStatus.PASS


# --------------------------------------------------------------------------
# The gap the derivation makes visible
# --------------------------------------------------------------------------


def test_company_os_tests_that_no_capsule_declares_are_reported(index):
    """Deriving the required set from the contracts exposes what the contracts
    do not cover. On this checkout eleven `tests/test_company*.py` files are
    declared by no capsule, so nothing requires them - a gap in the capsule
    contracts, not in the gate.

    Asserted as a set relation rather than a count: a capsule that legitimately
    adopts one of these should make this test greener, not redder.
    """
    required = resolve_required_suites(index)
    undeclared = undeclared_company_os_suites(REPO_ROOT, required)
    on_disk = {f"tests/{p.name}" for p in (REPO_ROOT / "tests").glob("test_company*.py")}
    assert set(undeclared) <= on_disk
    assert set(undeclared).isdisjoint(required.names())
    assert set(required.names()) | set(undeclared) >= on_disk


def test_the_undeclared_list_changes_no_verdict(repo_scan, synthetic_seeds):
    """It is reported, never required. A file nobody declared is not a
    contract, and inventing a requirement from a directory listing would make
    the gate depend on what happens to be on disk."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(
                CapsuleIndex.load(synthetic_seeds)
            ).names()
        )
    )
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=evidence,
        capsule_root=synthetic_seeds,
    )
    assert report.check("health.required_suites_pass").status is GateStatus.PASS


def test_the_cli_names_the_undeclared_suites(capsys, index):
    integration_main(["required-suites", "--repo-root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    undeclared = undeclared_company_os_suites(
        REPO_ROOT, resolve_required_suites(index)
    )
    if undeclared:
        assert "no capsule declares them" in out
        for suite in undeclared:
            assert suite in out


def test_undeclared_suites_on_a_tree_with_no_tests_directory(tmp_path, index):
    assert undeclared_company_os_suites(tmp_path, resolve_required_suites(index)) == ()


# --------------------------------------------------------------------------
# The gate still runs nothing
# --------------------------------------------------------------------------


def test_deriving_the_set_spawns_no_process():
    """Read off the module's own imports: the resolver is data, not a runner.

    Parsed rather than grepped, because the module's docstring explains at
    length why the gate does not shell out to pytest, and a text search for
    `subprocess` finds that explanation.
    """
    tree = ast.parse(
        (REPO_ROOT / "company/integration/suites.py").read_text(encoding="utf-8")
    )
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots.isdisjoint({"subprocess", "os", "multiprocessing", "pytest", "shutil"})


# --------------------------------------------------------------------------
# The CLI a caller uses to learn what to run
# --------------------------------------------------------------------------


def test_the_cli_prints_the_derived_set(capsys, index):
    code = integration_main(["required-suites", "--repo-root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    assert code == 0
    for suite in resolve_required_suites(index).names():
        assert suite in out


def test_the_cli_reports_an_unresolved_set_as_missing_evidence(capsys, tmp_path):
    """Exit 2 is the gate's own code for "evidence is missing", and a caller
    scripting `--suite-evidence` off this output must not read a partial list
    as the whole answer."""
    empty = tmp_path / "no-seeds"
    empty.mkdir()
    code = integration_main(
        [
            "required-suites",
            "--repo-root",
            str(REPO_ROOT),
            "--capsule-root",
            str(empty),
        ]
    )
    assert code == 2
    assert "UNRESOLVED" in capsys.readouterr().out


def test_the_cli_json_carries_the_set_fingerprint(capsys, index):
    code = integration_main(
        ["required-suites", "--repo-root", str(REPO_ROOT), "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fingerprint"] == resolve_required_suites(index).fingerprint()
    assert len(payload["requirements"]) == len(resolve_required_suites(index))
