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
import shutil

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
from company.integration.dependencies import DependencyGraph, build_dependency_graph
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


@pytest.fixture(scope="module")
def graph(repo_scan) -> DependencyGraph:
    """The real repository import graph, the fourth input to derivation.

    Module-scoped because it is a pure function of `repo_scan`, which is
    already module-scoped for the same reason. Tests that want the derived set
    to be *resolvable* must pass it: `resolve_required_suites` treats a missing
    graph the way it treats a missing capsule index, as something it was not
    told rather than something that is empty.
    """
    return build_dependency_graph(repo_scan)


# --------------------------------------------------------------------------
# What the set is made of
# --------------------------------------------------------------------------


def test_the_canonical_floor_is_always_required(index, graph):
    """Every hand-written canonical suite survives derivation.

    The floor exists because one of its members - the execution transport
    suite - is required by the gate's own checks and declared by no capsule.
    Derivation must not lose it.
    """
    required = resolve_required_suites(index, graph=graph)
    assert set(REQUIRED_SUITES) <= set(required.names())
    assert required.resolved


def test_a_suite_declared_only_by_a_capsule_is_still_required(index, graph):
    required = resolve_required_suites(index, graph=graph)
    item = required.get("tests/test_company_os_research_ingestion.py")
    assert item is not None
    assert item.suite not in REQUIRED_SUITES
    assert SuiteOrigin.CAPSULE_CONTRACT in item.origins
    assert "company-research-intelligence" in item.capsule_ids


def test_every_requirement_names_why_it_is_required(index, graph):
    for item in resolve_required_suites(index, graph=graph):
        assert item.origins
        assert item.reason()


def test_the_set_is_deterministic_and_fingerprinted(index, graph):
    first = resolve_required_suites(index, graph=graph)
    second = resolve_required_suites(CapsuleIndex.load(SEED_ROOT), graph=graph)
    assert first.names() == second.names()
    assert first.fingerprint() == second.fingerprint()


def test_a_suite_required_twice_over_keeps_both_reasons(index, graph):
    """Canonical *and* capsule-declared is the common case, and says more."""
    item = resolve_required_suites(index, graph=graph).get("tests/test_company_runtime.py")
    assert item is not None
    assert SuiteOrigin.CANONICAL in item.origins
    assert SuiteOrigin.CAPSULE_CONTRACT in item.origins


# --------------------------------------------------------------------------
# Change scope widens, and only widens
# --------------------------------------------------------------------------


def test_change_scope_never_shrinks_the_set(index, graph):
    """A gate that got cheaper when you described the change less fully would
    have a dial on it. Every scoped set is a superset of the unscoped one."""
    unscoped = set(resolve_required_suites(index, graph=graph).names())
    for scope in (
        ("company/runtime/context_assembly.py",),
        ("sloped/scale.py",),
        ("README.md",),
        (),
    ):
        scoped = set(resolve_required_suites(index, changed_paths=scope, graph=graph).names())
        assert unscoped <= scoped, scope


def test_a_changed_company_os_test_file_requires_its_own_evidence(index, graph):
    required = resolve_required_suites(
        index,
        graph=graph,
        changed_paths=("tests/test_company_youtube_live_findings.py",),
    )
    item = required.get("tests/test_company_youtube_live_findings.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins


def test_a_changed_production_test_is_not_pulled_into_the_company_os_gate(index, graph):
    """`health.production_failures_separated` is where a production suite is
    reported. Requiring it here would make a missing render dependency read as
    a control-plane blocker."""
    required = resolve_required_suites(
        index, graph=graph, changed_paths=("tests/test_sloped_scale.py",)
    )
    assert required.get("tests/test_sloped_scale.py") is None


def test_scope_on_an_owned_path_marks_that_capsules_suites(index, graph):
    required = resolve_required_suites(
        index, graph=graph, changed_paths=("company/runtime/context_cache.py",)
    )
    item = required.get("tests/test_company_context_assembly.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins
    assert "company-runtime" in item.capsule_ids


# --------------------------------------------------------------------------
# What cannot be worked out stays unknown
# --------------------------------------------------------------------------


def test_an_unreadable_capsule_store_leaves_the_set_unresolved(graph):
    required = resolve_required_suites(None, graph=graph)
    assert not required.resolved
    assert required.unresolved
    assert set(required.names()) == set(REQUIRED_SUITES)


def test_an_unresolved_set_makes_the_gate_condition_unknown(repo_scan, tmp_path, graph):
    """The whole safety property, end to end: a capsule store the gate cannot
    read must not produce a green suite condition, however much evidence was
    supplied."""
    empty = tmp_path / "no-seeds"
    empty.mkdir()
    evidence = SuiteEvidence(
        tuple(_result(name) for name in resolve_required_suites(None, graph=graph).names())
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


def test_the_p5_integration_miss_is_reproduced_and_now_blocks(
    repo_scan, synthetic_seeds, graph
):
    """The exact 2026-09-24 shape: every canonical suite green, one
    capsule-declared suite red, and the old gate said READY.

    Built on a synthetic capsule store so the reproduction survives the real
    seeds being edited. `tests/test_company_os_research_ingestion.py` is not in
    `REQUIRED_SUITES` and is declared by an active capsule, which is the whole
    of the defect.
    """
    red = "tests/test_company_os_research_ingestion.py"
    assert red not in REQUIRED_SUITES

    # Green for everything the contract derives, red for the one suite the
    # capsule declares. The green list is the derived set rather than
    # `REQUIRED_SUITES` because P6B widened derivation again: leaving it as the
    # canonical eleven would make this report UNKNOWN for want of evidence and
    # stop reproducing the defect, which was a red suite on a *complete* set.
    derived = resolve_required_suites(
        CapsuleIndex.load(synthetic_seeds), graph=graph
    ).names()
    evidence = SuiteEvidence(
        tuple(_result(name) for name in derived if name != red)
        + (_result(red, passed=False),)
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


def test_a_retired_capsules_declaration_stops_counting(repo_scan, synthetic_seeds, graph):
    """A contract no longer in force stops *declaring*, which is the whole of
    what `_IN_FORCE` controls.

    Before P6B this could be written as "the suite is not required at all",
    because a capsule declaration was the only thing that could require it.
    `DEPENDENCY_OBSERVED` made that shortcut false without making it safer:
    this suite imports `intelligence/research`, which the *active*
    `synthetic-research` capsule owns, so the contract still depends on it and
    the retirement of a different capsule is no reason to stop running it.

    The property being tested is unchanged and is asserted directly: nothing
    the retired capsule said is in the answer.
    """
    required = resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph)
    item = required.get("tests/test_company_os_research_batches.py")
    assert item is not None
    assert SuiteOrigin.CAPSULE_CONTRACT not in item.origins
    assert "synthetic-retired" not in item.capsule_ids
    assert item.origins == (SuiteOrigin.DEPENDENCY_OBSERVED,)


def test_a_retired_capsules_tests_return_when_the_change_touches_it(synthetic_seeds, graph):
    """Scope reaches what status alone does not: editing a retired capsule's
    own code is exactly when its tests matter again."""
    required = resolve_required_suites(
        CapsuleIndex.load(synthetic_seeds),
        graph=graph,
        changed_paths=("intelligence/__init__.py",),
    )
    item = required.get("tests/test_company_os_research_batches.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins
    assert SuiteOrigin.CAPSULE_CONTRACT not in item.origins


def test_a_supplied_red_company_os_suite_is_not_discarded(repo_scan, synthetic_seeds, graph):
    """Evidence the caller handed over does not disappear for want of a
    contract. No capsule declares this suite; the reporter still called it
    Company OS and called it red."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
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


def test_a_supplied_red_production_suite_still_does_not_block(repo_scan, synthetic_seeds, graph):
    """The separation the gate already makes survives the widening: a
    production-environment failure is reported by its own check."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
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
# Which lifecycle states still bind  (independent review, finding B1)
# --------------------------------------------------------------------------


def _seeds_with_status(tmp_path, capsule_id: str, status: str) -> Path:
    """A copy of the real seeds with one capsule's status changed."""
    root = tmp_path / f"seeds-{status}"
    shutil.copytree(SEED_ROOT, root)
    target = root / f"{capsule_id}.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["status"] = status
    target.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def test_flagging_a_capsule_for_revalidation_does_not_drop_its_suites(tmp_path, index, graph):
    """Found by independent review. `flag_capsule_for_revalidation()` is a
    supported operation; if it removed a capsule's suites from the required
    set, flagging a capsule would be a way to make the gate stop asking about
    exactly the subsystem somebody has just said they no longer trust - the P5
    defect again, reached through the lifecycle instead of a static list.
    """
    flagged = resolve_required_suites(CapsuleIndex.load(
            _seeds_with_status(tmp_path, "company-executive-delegation", "needs_revalidation")
        ), graph=graph)
    baseline = resolve_required_suites(index, graph=graph)
    assert set(baseline.names()) <= set(flagged.names())
    assert "tests/test_company_delegation.py" in flagged


@pytest.mark.parametrize("status", ["retired", "superseded"])
def test_a_finished_contract_stops_requiring_its_suites(tmp_path, index, status, graph):
    """The other direction, and the reason `_IN_FORCE` is not just "any state":
    a contract that has been replaced or retired is not in force.

    What stops is the *declaration*. `tests/test_company_delegation.py` stays
    in the set because it also imports code that `company-runtime`,
    `company-finance` and four other capsules still in force own - which is a
    fact about the repository, not about the retired contract. Retiring a
    capsule was never meant to be a way to stop running a suite that still
    loads live governed code, and after P6B it is not one.

    A subsystem genuinely being removed takes its tests with it, and a deleted
    test file is not in the graph, so the intended path still works.
    """
    finished = resolve_required_suites(CapsuleIndex.load(
            _seeds_with_status(tmp_path, "company-executive-delegation", status)
        ), graph=graph)
    item = finished.get("tests/test_company_delegation.py")
    assert item is not None
    assert SuiteOrigin.CAPSULE_CONTRACT not in item.origins
    assert "company-executive-delegation" not in item.capsule_ids


def test_change_scope_still_reaches_a_finished_contract(tmp_path, graph):
    """Editing a retired capsule's own code is exactly when its tests matter."""
    root = _seeds_with_status(tmp_path, "company-executive-delegation", "retired")
    scoped = resolve_required_suites(
        CapsuleIndex.load(root), graph=graph, changed_paths=("company/delegation/",)
    )
    item = scoped.get("tests/test_company_delegation.py")
    assert item is not None
    assert SuiteOrigin.CHANGE_SCOPE in item.origins
    assert SuiteOrigin.CAPSULE_CONTRACT not in item.origins


# --------------------------------------------------------------------------
# A partial capsule store  (independent review, finding B2)
# --------------------------------------------------------------------------


def test_a_partially_loaded_capsule_store_is_not_treated_as_complete(tmp_path, graph):
    """Found by independent review. The argument against an *empty* store -
    that a Company OS checkout has capsules - applies with identical force to
    one that lost half its files, and stopping at zero left that open.

    `CapsuleIndex.integrity()` with no store and no checkout is a pure
    structural check over the capsules' own declarations, and a partial store
    almost always has a capsule depending on one that is no longer there.
    """
    partial = tmp_path / "partial"
    partial.mkdir()
    shutil.copy(SEED_ROOT / "company-runtime.json", partial / "company-runtime.json")
    required = resolve_required_suites(CapsuleIndex.load(partial), graph=graph)
    assert not required.resolved
    assert any("structurally incomplete" in item for item in required.unresolved)


def test_a_partial_store_keeps_the_gate_condition_unknown(repo_scan, tmp_path, graph):
    partial = tmp_path / "partial"
    partial.mkdir()
    shutil.copy(SEED_ROOT / "company-runtime.json", partial / "company-runtime.json")
    required = resolve_required_suites(CapsuleIndex.load(partial), graph=graph)
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=SuiteEvidence(tuple(_result(n) for n in required.names())),
        capsule_root=partial,
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert report.readiness is not Readiness.READY


def test_a_capsule_that_quietly_vanishes_is_caught(tmp_path, repo_scan, graph):
    """B2, closed. The residual P6A named is now a required check that fails.

    `resolve_required_suites` is pure, so the strongest thing it can say about
    a short store is that it contradicts itself, and that misses a *downward
    closed* subset: delete a leaf capsule and the remainder is still internally
    consistent. P6A coped by putting `derived_from` inside `fingerprint()`, so
    a lost capsule is at least a diff between two reports. It declined to
    couple the check to unclaimed modules, because that would move an advisory
    condition across the required line without the visible `policy.py` diff
    `GatePolicy` demands - and because it would have missed this capsule
    anyway, whose paths are under a production root the Company OS module scan
    never walks.

    `company-external-engineering-runner` was the one deletion of the 22 that
    left nothing unclaimed. P6B catches it in general and with the policy diff:
    `architecture.governed_subsystem_ownership` asks the import graph which
    production packages a Company OS suite depends on, finds
    `tools/engineering_runner` among them, and finds no capsule owning it.

    The three older observations are kept, because each of them is still true
    and each would be a separate regression.
    """
    short = tmp_path / "seeds"
    shutil.copytree(SEED_ROOT, short)
    (short / "company-external-engineering-runner.json").unlink()

    index = CapsuleIndex.load(short)
    required = resolve_required_suites(index, graph=graph)
    baseline = resolve_required_suites(CapsuleIndex.load(SEED_ROOT), graph=graph)

    # Still true: the short store resolves, and it is still missing suites.
    assert required.resolved
    assert index.integrity() == ()
    dropped = set(baseline.names()) - set(required.names())
    assert dropped == {
        "tests/test_engineering_runner_execution_context.py",
        "tests/test_engineering_runner_exploration_report.py",
        "tests/test_engineering_runner_exploration_telemetry.py",
        "tests/test_engineering_runner_repo_map.py",
        "tests/test_external_engineering_runner.py",
    }

    # Still true: the set identity changes, so the loss is a report diff.
    assert required.fingerprint() != baseline.fingerprint()
    assert "company-external-engineering-runner" not in required.derived_from

    # New, and the point of P6B: it now blocks, from a required check.
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=SuiteEvidence(tuple(_result(n) for n in required.names())),
        capsule_root=short,
    )
    check = report.check("architecture.governed_subsystem_ownership")
    assert check.status is GateStatus.FAIL
    assert "tools/engineering_runner" in check.evidence
    assert report.readiness is Readiness.BLOCKED


def test_governed_subsystem_ownership_passes_on_the_real_store(repo_scan, graph):
    """The same check on the untouched repository, so the failure above is
    the deletion and not the rule being wrong about this checkout."""
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=SuiteEvidence(),
    )
    check = report.check("architecture.governed_subsystem_ownership")
    assert check.status is GateStatus.PASS
    assert set(check.evidence) == {"tools/engineering_runner", "tools/youtube_fetch"}


def test_the_set_identity_moves_when_only_the_capsule_list_moves(tmp_path, graph):
    """The property `derived_from` exists for: a capsule whose tests are
    already required by another capsule can be deleted without changing a
    single suite name, and the set must still not look identical."""
    short = tmp_path / "seeds"
    shutil.copytree(SEED_ROOT, short)
    before = resolve_required_suites(CapsuleIndex.load(short), graph=graph)

    duplicate = _capsule_json(
        "synthetic-duplicate-cover",
        owns=["docs/evidence/company_os_p6a_typed_evidence_cache_context"],
        tests=["tests/test_company_runtime.py"],
    )
    (short / "synthetic-duplicate-cover.json").write_text(
        json.dumps(duplicate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    after = resolve_required_suites(CapsuleIndex.load(short), graph=graph)

    assert set(after.names()) == set(before.names()), "no suite name moved"
    assert after.fingerprint() != before.fingerprint()
    assert "synthetic-duplicate-cover" in after.derived_from


def test_the_report_carries_the_number_of_capsules_it_derived_from(repo_scan, index, graph):
    required = resolve_required_suites(index, graph=graph)
    report = build_report(
        REPO_ROOT,
        as_of=AS_OF,
        scan=repo_scan,
        suites=SuiteEvidence(tuple(_result(n) for n in required.names())),
    )
    detail = report.check("health.required_suites_pass").detail
    assert required.fingerprint() in detail
    assert f"derived from {len(required.derived_from)} capsule(s)" in detail


def test_a_red_result_dated_in_the_future_still_fails(repo_scan, synthetic_seeds, graph):
    """Found by independent review. `unobserved` is evaluated before `failing`,
    so a red result with a future date would have become UNKNOWN - turning
    BLOCKED into INSUFFICIENT_EVIDENCE for a reporter who mistyped a date, and
    bending the one rule that says a red result you were handed is never
    dropped. Only *passing* results are eligible to be unobserved."""
    names = resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
    evidence = SuiteEvidence(
        tuple(_result(n) for n in names[1:])
        + (
            SuiteResult(
                suite=names[0],
                passed=False,
                observed_on=dt.date(2027, 1, 1),
                reported_by="tests/test_company_gate_suite_requirements.py",
                selected=3,
                failed=1,
            ),
        )
    )
    report = build_report(
        REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=evidence, capsule_root=synthetic_seeds
    )
    assert report.check("health.required_suites_pass").status is GateStatus.FAIL
    assert report.readiness is Readiness.BLOCKED


def test_the_real_seed_store_is_structurally_complete(index, graph):
    """The other half: the fix must not make the real repository unresolvable."""
    required = resolve_required_suites(index, graph=graph)
    assert required.resolved
    assert index.integrity() == ()


# --------------------------------------------------------------------------
# A capsule that names something that is not a suite  (review, N1/N2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reference",
    [
        "tests/*.py",
        "tests/test_company_x.PY",
        "Tests/test_company_x.py",
        "docs/validation/company_os_p6a/measure_context_efficiency.py",
        "tests/./test_company_x.py",
    ],
)
def test_an_unusable_test_reference_is_reported_not_dropped(tmp_path, reference, graph):
    """Found by independent review. Dropping these silently would let one
    legal-looking capsule edit remove a suite from the required set with
    nothing to show for it - and a glob would be worse, becoming a required
    suite nobody can ever report evidence about."""
    root = tmp_path / "seeds"
    root.mkdir()
    capsule = _capsule_json(
        "synthetic-odd-tests", owns=["intelligence/research"], tests=[reference]
    )
    (root / "synthetic-odd-tests.json").write_text(
        json.dumps(capsule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    required = resolve_required_suites(CapsuleIndex.load(root), graph=graph)
    assert not required.resolved
    assert any(reference in item for item in required.unresolved)
    assert reference not in required.names()


# --------------------------------------------------------------------------
# Present, green, and still not evidence  (independent review, N5/N6)
# --------------------------------------------------------------------------


def test_a_green_run_that_selected_no_tests_is_not_evidence(repo_scan, synthetic_seeds, graph):
    """pytest collected nothing, so "0 failed" is true and proves nothing."""
    names = resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
    evidence = SuiteEvidence(
        tuple(
            SuiteResult(
                suite=name,
                passed=True,
                observed_on=AS_OF,
                reported_by="tests/test_company_gate_suite_requirements.py",
                selected=0,
            )
            for name in names
        )
    )
    report = build_report(
        REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=evidence, capsule_root=synthetic_seeds
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert any("0 tests selected" in item for item in check.missing_evidence)


def test_evidence_dated_after_the_run_is_not_evidence(repo_scan, synthetic_seeds, graph):
    """Staleness is `as_of - observed_on`, so a future date makes the age
    negative and the freshness window unreachable."""
    names = resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
    evidence = SuiteEvidence(
        tuple(_result(name, day=24) for name in names[1:])
        + (
            SuiteResult(
                suite=names[0],
                passed=True,
                observed_on=dt.date(2027, 1, 1),
                reported_by="tests/test_company_gate_suite_requirements.py",
                selected=5,
            ),
        ),
        max_age_days=0,
    )
    report = build_report(
        REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=evidence, capsule_root=synthetic_seeds
    )
    check = report.check("health.required_suites_pass")
    assert check.status is GateStatus.UNKNOWN
    assert any("after the run date" in item for item in check.missing_evidence)


# --------------------------------------------------------------------------
# The gap the derivation makes visible
# --------------------------------------------------------------------------


def test_company_os_tests_that_no_capsule_declares_are_reported(index, graph):
    """Deriving the required set from the contracts exposes what the contracts
    do not cover. On this checkout eleven `tests/test_company*.py` files are
    declared by no capsule, so nothing requires them - a gap in the capsule
    contracts, not in the gate.

    Asserted as a set relation rather than a count: a capsule that legitimately
    adopts one of these should make this test greener, not redder.
    """
    required = resolve_required_suites(index, graph=graph)
    undeclared = undeclared_company_os_suites(REPO_ROOT, required)
    on_disk = {f"tests/{p.name}" for p in (REPO_ROOT / "tests").glob("test_company*.py")}
    assert set(undeclared) <= on_disk
    assert set(undeclared).isdisjoint(required.names())
    assert set(required.names()) | set(undeclared) >= on_disk


def test_the_undeclared_list_changes_no_verdict(repo_scan, synthetic_seeds, graph):
    """It is reported, never required. A file nobody declared is not a
    contract, and inventing a requirement from a directory listing would make
    the gate depend on what happens to be on disk."""
    evidence = SuiteEvidence(
        tuple(
            _result(name)
            for name in resolve_required_suites(CapsuleIndex.load(synthetic_seeds), graph=graph).names()
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


def test_the_cli_names_the_undeclared_suites(capsys, index, graph):
    integration_main(["required-suites", "--repo-root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    undeclared = undeclared_company_os_suites(
        REPO_ROOT, resolve_required_suites(index, graph=graph)
    )
    if undeclared:
        assert "no capsule declares them" in out
        for suite in undeclared:
            assert suite in out


def test_undeclared_suites_on_a_tree_with_no_tests_directory(tmp_path, index, graph):
    assert undeclared_company_os_suites(tmp_path, resolve_required_suites(index, graph=graph)) == ()


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


def test_the_cli_prints_the_derived_set(capsys, index, graph):
    code = integration_main(["required-suites", "--repo-root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    assert code == 0
    for suite in resolve_required_suites(index, graph=graph).names():
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


def test_the_cli_json_carries_the_set_fingerprint(capsys, index, graph):
    code = integration_main(
        ["required-suites", "--repo-root", str(REPO_ROOT), "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fingerprint"] == resolve_required_suites(index, graph=graph).fingerprint()
    assert len(payload["requirements"]) == len(resolve_required_suites(index, graph=graph))
