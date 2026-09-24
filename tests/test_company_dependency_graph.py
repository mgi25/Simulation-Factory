"""The import graph both halves of P6B rest on, and what it refuses to claim.

## Why this file exists

P6A derived the gate's required suites from `capsule.tests` and left the
declaration unverified. `checks.py` said so in a comment: the real fix is to
make `capsule.tests` a checked claim against the actual test-to-module
dependency. Two things had to be true before that was safe.

The first is that the graph is *right*. The runner's map had a parser that
recorded `ImportFrom` only at `node.level == 0`, which dropped 965 relative
imports - almost every internal edge in the control plane - and resolved
`from X import y` to `X`, never to `X/y.py`. Together those two made the
dominant pattern in this repository invisible: a test imports a package
facade, the facade re-exports its modules with relative imports, and the
graph saw neither hop.

The second is that the graph is *modest*. An import edge proves that running
a suite loads a module. It does not prove the suite tests it. Every assertion
below is written in those terms, and several exist specifically to pin the
weaker claim so a later change cannot quietly promote it.

## Synthetic fixtures, not the real tree

Most of these build a small repository in `tmp_path`. A test that asserts
"relative imports resolve" against the real checkout passes for as long as
nobody deletes the one file it happened to rely on, and its failure message
names a production path rather than the rule that broke. The fixtures are
four to eight files each and name the case in the fixture.

The few tests that do use the real checkout are marked by taking `repo_graph`,
and each of them asserts a property of the repository that is itself the
finding - the two governed production packages, or every Company OS suite in
the directory - rather than a property of the resolver.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from company.integration.checks import GateScan
from company.integration.dependencies import (
    DEFAULT_QUERY_LIMIT,
    CapsuleTestFinding,
    DependencyGraph,
    DependencyRelation,
    audit_capsule_tests,
    build_dependency_graph,
    governed_production_subsystems,
)
from company.integration.sources import COMPANY_OS_ROOTS, production_roots
from company.integration.suites import (
    SuiteOrigin,
    resolve_required_suites,
    undeclared_company_os_suites,
)
from knowledge.company_os.capsules import CapsuleIndex
from tools.engineering_runner.repo_map import (
    DEPENDENCY_MANIFEST_VERSION,
    ChangeImpact,
    DependencyManifest,
    build_repo_map,
    change_impact,
    load_dependency_manifest,
    neighborhood,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = REPO_ROOT / "knowledge/company_os/capsules/seeds"
AS_OF = dt.date(2026, 9, 24)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def repo_scan() -> GateScan:
    return GateScan.of(REPO_ROOT)


@pytest.fixture(scope="module")
def repo_graph(repo_scan) -> DependencyGraph:
    return build_dependency_graph(repo_scan)


@pytest.fixture(scope="module")
def seeds() -> CapsuleIndex:
    return CapsuleIndex.load(SEED_ROOT)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _graph_of(root: Path) -> DependencyGraph:
    """Build the graph for a synthetic tree, using the gate's own scan."""
    return build_dependency_graph(GateScan.of(root))


@pytest.fixture
def facade_tree(tmp_path) -> Path:
    """The dominant real pattern, in six files.

    `tests/test_thing.py` imports the package, the package's `__init__`
    re-exports a module with a relative import, and that module imports a
    sibling the same way. Nothing here is reachable by the pre-P6B rules.
    """
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing/__init__.py", "from .core import Core\n")
    _write(tmp_path, "company/thing/core.py", "from .helper import help_out\n\nclass Core:\n    pass\n")
    _write(tmp_path, "company/thing/helper.py", "def help_out():\n    return 1\n")
    _write(tmp_path, "company/thing/unrelated.py", "VALUE = 1\n")
    _write(tmp_path, "tests/test_thing.py", "from company.thing import Core\n\n\ndef test_it():\n    assert Core\n")
    return tmp_path


# --------------------------------------------------------------------------
# Resolution: the four rules
# --------------------------------------------------------------------------


def test_a_relative_import_is_an_edge(facade_tree):
    """`from .helper import x` in `company/thing/core.py` reaches the sibling.

    The V1-V3 runner parser recorded `ImportFrom` only when `node.level == 0`,
    so this edge - and 964 others in the real tree - did not exist.
    """
    graph = _graph_of(facade_tree)
    assert "company/thing/helper.py" in graph.direct_dependencies("company/thing/core.py")


def test_a_relative_import_that_escapes_the_package_is_not_invented(tmp_path):
    """`from ... import x` deeper than the nesting resolves to nothing.

    The honest answer is no edge. Clamping to the top package would invent one.
    """
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/deep.py", "from ..... import nothing\n")
    graph = _graph_of(tmp_path)
    assert graph.direct_dependencies("company/deep.py") == ()


def test_from_package_import_module_reaches_the_module(tmp_path):
    """`from company.thing import core` is an edge to `core.py`, not only to
    the package. Same syntax as `from company.thing import Core`, different
    dependency, and only the module set can tell them apart."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing/__init__.py", "")
    _write(tmp_path, "company/thing/core.py", "class Core:\n    pass\n")
    _write(tmp_path, "tests/test_x.py", "from company.thing import core\n")
    graph = _graph_of(tmp_path)
    assert "company/thing/core.py" in graph.direct_dependencies("tests/test_x.py")


def test_from_package_import_a_symbol_does_not_invent_a_module(tmp_path):
    """The other half of the same rule: `Core` is not a file, so no edge to a
    file called `Core` is created, and the package edge is still there."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing/__init__.py", "class Core:\n    pass\n")
    _write(tmp_path, "tests/test_x.py", "from company.thing import Core\n")
    graph = _graph_of(tmp_path)
    reached = set(graph.direct_dependencies("tests/test_x.py"))
    # The package and its parent, both of which really do run on this import,
    # and nothing named after the symbol.
    assert reached == {"company/__init__.py", "company/thing/__init__.py"}
    assert not any("Core" in path for path in reached)


def test_importing_a_submodule_reaches_the_packages_above_it(tmp_path):
    """`import a.b.c` runs `a/__init__.py` and `a/b/__init__.py`, so both are
    real dependencies and both are edges."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing/__init__.py", "")
    _write(tmp_path, "company/thing/core.py", "")
    _write(tmp_path, "tests/test_x.py", "import company.thing.core\n")
    graph = _graph_of(tmp_path)
    assert set(graph.direct_dependencies("tests/test_x.py")) == {
        "company/__init__.py",
        "company/thing/__init__.py",
        "company/thing/core.py",
    }


def test_a_dynamic_import_is_unresolved_and_never_an_edge(tmp_path):
    """A literal argument would resolve correctly most of the time, and the
    one time it did not the graph would assert an edge nobody wrote."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/target.py", "")
    _write(
        tmp_path,
        "company/loader.py",
        "import importlib\n\n\ndef go():\n    return importlib.import_module('company.target')\n",
    )
    graph = _graph_of(tmp_path)
    assert "company/target.py" not in graph.direct_dependencies("company/loader.py")
    assert [u.path for u in graph.unresolved] == ["company/loader.py"]
    assert "company.target" in graph.unresolved[0].detail


def test_there_is_no_filename_heuristic(tmp_path):
    """`test_core.py` has no relationship to `core.py` unless an import says
    so. A name-based index guesses, and guesses wrong for a shared module or
    a suite that covers more than its name."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/core.py", "")
    _write(tmp_path, "tests/test_core.py", "def test_nothing():\n    assert True\n")
    graph = _graph_of(tmp_path)
    assert graph.tests_reaching("company/core.py") == ()


# --------------------------------------------------------------------------
# Direct versus transitive, and cycles
# --------------------------------------------------------------------------


def test_direct_and_transitive_are_distinguished(facade_tree):
    """The facade chain: the test reaches `__init__` directly and `helper.py`
    only through two hops. Collapsing the two would make every suite look like
    a direct test of everything the package re-exports."""
    graph = _graph_of(facade_tree)
    test = "tests/test_thing.py"
    assert graph.relation(test, "company/thing/__init__.py") is DependencyRelation.DIRECT_STATIC
    assert graph.relation(test, "company/thing/helper.py") is DependencyRelation.TRANSITIVE_STATIC
    assert graph.tests_reaching("company/thing/helper.py", transitive=False) == ()
    assert graph.tests_reaching("company/thing/helper.py", transitive=True) == (test,)


def test_a_module_the_facade_does_not_export_is_not_reached(facade_tree):
    """The transitive closure is a closure, not a package wildcard."""
    graph = _graph_of(facade_tree)
    assert graph.tests_reaching("company/thing/unrelated.py") == ()


def test_an_import_cycle_terminates(tmp_path):
    """`a` imports `b`, `b` imports `a`. Both closures terminate and neither
    contains its own start."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/a.py", "from company import b\n")
    _write(tmp_path, "company/b.py", "from company import a\n")
    _write(tmp_path, "tests/test_cycle.py", "from company import a\n")
    graph = _graph_of(tmp_path)
    assert "company/b.py" in graph.transitive_dependencies("company/a.py")
    assert "company/a.py" not in graph.transitive_dependencies("company/a.py")
    assert graph.tests_reaching("company/b.py") == ("tests/test_cycle.py",)


def test_two_modules_with_the_same_terminal_name_stay_apart(tmp_path):
    """`company/one/errors.py` and `company/two/errors.py` are different
    modules. Matching on the terminal name would merge them."""
    _write(tmp_path, "company/__init__.py", "")
    for pkg in ("one", "two"):
        _write(tmp_path, f"company/{pkg}/__init__.py", "")
        _write(tmp_path, f"company/{pkg}/errors.py", "")
    _write(tmp_path, "tests/test_one.py", "from company.one import errors\n")
    graph = _graph_of(tmp_path)
    assert graph.tests_reaching("company/one/errors.py") == ("tests/test_one.py",)
    assert graph.tests_reaching("company/two/errors.py") == ()


def test_a_file_that_does_not_parse_is_reported_not_silently_dropped(tmp_path):
    """A graph that drops what it could not read looks exactly like a graph
    with nothing to drop, and the gate checks that rest on it must answer
    `unknown` rather than `pass`."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/broken.py", "def (:\n")
    graph = _graph_of(tmp_path)
    assert any("broken.py" in failure for failure in graph.parse_failures)


def test_the_graph_is_deterministic_and_fingerprinted(repo_scan):
    first = build_dependency_graph(repo_scan)
    second = build_dependency_graph(repo_scan)
    assert first.fingerprint() == second.fingerprint()
    assert first.modules == second.modules
    assert first.edges == second.edges


def test_a_type_checking_import_is_not_a_runtime_edge(tmp_path):
    """It never runs, so it is not a dependency a suite creates by loading the
    module. Kept in a separate map rather than discarded: it is still a
    coupling, and hiding it would be the same mistake as inventing it."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/target.py", "")
    _write(
        tmp_path,
        "company/user.py",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from company import target\n",
    )
    graph = _graph_of(tmp_path)
    assert "company/target.py" not in graph.direct_dependencies("company/user.py")
    assert "company/target.py" in graph.type_checking_edges["company/user.py"]


# --------------------------------------------------------------------------
# The capsule/test contract audit
# --------------------------------------------------------------------------


def _capsule(capsule_id: str, *, owns: list[str], tests: list[str]) -> dict:
    return {
        "id": capsule_id,
        "type": "module",
        "title": capsule_id,
        "purpose": f"A synthetic capsule for {capsule_id}, owning a path and naming a test.",
        "owner": "company-os",
        "source": "synthetic",
        "created": "2026-09-24",
        "last_reviewed": "2026-09-24",
        "status": "active",
        "owns_paths": owns,
        "tests": tests,
        "freshness": "slow_changing",
    }


def _seed_store(root: Path, *capsules: dict) -> Path:
    store = root / "seeds"
    store.mkdir(parents=True, exist_ok=True)
    for capsule in capsules:
        (store / f"{capsule['id']}.json").write_text(
            json.dumps(capsule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return store


def test_a_declared_and_observed_test_is_recorded_as_both(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing.py", "")
    _write(tmp_path, "tests/test_thing.py", "from company import thing\n")
    store = _seed_store(
        tmp_path, _capsule("syn-thing", owns=["company/thing.py"], tests=["tests/test_thing.py"])
    )
    audit = audit_capsule_tests(_graph_of(tmp_path), CapsuleIndex.load(store))
    finding = audit.get("syn-thing")
    assert finding.declared_and_observed == ("tests/test_thing.py",)
    assert finding.declared_not_observed == ()
    assert finding.has_witness()


def test_a_declared_but_unobserved_test_is_a_finding_not_a_fault(tmp_path):
    """A suite that drives a CLI in a subprocess, reads a fixture file or
    greps source text tests the capsule's code and imports none of it. The
    audit reports the disagreement and rules on nothing."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing.py", "")
    _write(tmp_path, "tests/test_thing.py", "from company import thing\n")
    _write(
        tmp_path,
        "tests/test_thing_cli.py",
        "import subprocess\n\n\ndef test_cli():\n    subprocess.run(['python', '-m', 'company.thing'])\n",
    )
    store = _seed_store(
        tmp_path,
        _capsule(
            "syn-thing",
            owns=["company/thing.py"],
            tests=["tests/test_thing.py", "tests/test_thing_cli.py"],
        ),
    )
    audit = audit_capsule_tests(_graph_of(tmp_path), CapsuleIndex.load(store))
    finding = audit.get("syn-thing")
    assert finding.declared_not_observed == ("tests/test_thing_cli.py",)
    # It still has a witness, so it is not in the blocking set.
    assert finding.has_witness()
    assert audit.without_witness() == ()


def test_an_observed_but_undeclared_test_is_reported_and_not_added(tmp_path):
    """Reported in both directions, and the audit adds nothing to
    `capsule.tests`. A capsule is a bounded witness set: stuffing every
    dependent suite into it is how a capsule stops being cheaper than the code
    it summarises."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/thing.py", "")
    _write(tmp_path, "tests/test_thing.py", "from company import thing\n")
    _write(tmp_path, "tests/test_thing_extra.py", "from company import thing\n")
    store = _seed_store(
        tmp_path, _capsule("syn-thing", owns=["company/thing.py"], tests=["tests/test_thing.py"])
    )
    index = CapsuleIndex.load(store)
    audit = audit_capsule_tests(_graph_of(tmp_path), index)
    finding = audit.get("syn-thing")
    assert finding.observed_not_declared == ("tests/test_thing_extra.py",)
    assert index.get("syn-thing").tests == ("tests/test_thing.py",)


def test_a_capsule_owning_python_with_no_observable_test_is_the_blocking_case(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/lonely.py", "")
    _write(tmp_path, "company/other.py", "")
    _write(tmp_path, "tests/test_other.py", "from company import other\n")
    store = _seed_store(
        tmp_path,
        _capsule("syn-lonely", owns=["company/lonely.py"], tests=["tests/test_other.py"]),
    )
    audit = audit_capsule_tests(_graph_of(tmp_path), CapsuleIndex.load(store))
    assert [f.capsule_id for f in audit.without_witness()] == ["syn-lonely"]


def test_a_capsule_owning_no_python_is_not_asked_for_a_witness(tmp_path):
    """`company-bootstrap-policy` owns the constitution and five YAML schemas,
    `company-evidence-review` owns a docs directory, and
    `company-os-control-plane` owns nothing at all. No import can reach any of
    them, and demanding a static witness would be demanding the impossible."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/rules.yaml", "a: 1\n")
    _write(tmp_path, "company/thing.py", "")
    _write(tmp_path, "tests/test_thing.py", "from company import thing\n")
    store = _seed_store(
        tmp_path,
        _capsule("syn-policy", owns=["company/rules.yaml"], tests=["tests/test_thing.py"]),
    )
    audit = audit_capsule_tests(_graph_of(tmp_path), CapsuleIndex.load(store))
    assert audit.get("syn-policy").owned_modules == ()
    assert audit.without_witness() == ()


def test_a_cross_capsule_integration_test_belongs_to_several(tmp_path):
    """One suite reaching two capsules' code is not an ownership puzzle. It is
    observed by both, declared by whichever declared it, and forced into
    neither."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/left.py", "")
    _write(tmp_path, "company/right.py", "")
    _write(tmp_path, "tests/test_both.py", "from company import left, right\n")
    store = _seed_store(
        tmp_path,
        _capsule("syn-left", owns=["company/left.py"], tests=["tests/test_both.py"]),
        _capsule("syn-right", owns=["company/right.py"], tests=["tests/test_both.py"]),
    )
    audit = audit_capsule_tests(_graph_of(tmp_path), CapsuleIndex.load(store))
    for capsule_id in ("syn-left", "syn-right"):
        assert audit.get(capsule_id).declared_and_observed == ("tests/test_both.py",)


def test_every_real_capsule_owning_python_has_a_static_witness(repo_graph, seeds):
    """The audit run against this repository.

    Asserted as a property rather than a count, so adding a capsule does not
    fail this line for the wrong reason. The exception list *is* pinned by
    value: those three own the constitution and its schemas, a docs directory,
    and nothing at all, and a fourth name appearing there would mean a capsule
    owning Python had quietly become unreachable.
    """
    audit = audit_capsule_tests(repo_graph, seeds)
    assert audit.without_witness() == ()
    with_python = [f for f in audit.findings if f.owned_modules]
    assert all(f.has_witness() for f in with_python)
    assert {f.capsule_id for f in audit.findings if not f.owned_modules} == {
        "company-bootstrap-policy",
        "company-evidence-review",
        "company-os-control-plane",
    }


def test_the_audit_never_mutates_the_capsule_store(repo_graph, seeds):
    """Reporting a gap and closing it are different acts, and only one of them
    belongs to a deterministic audit."""
    before = {c.id: c.tests for c in seeds.all()}
    audit_capsule_tests(repo_graph, seeds)
    assert {c.id: c.tests for c in seeds.all()} == before


def test_the_capsule_budget_is_unchanged(seeds):
    """P6B may not buy its way out of the size contract. Eight items per list
    is what makes a capsule cheaper than the code it summarises, and the
    'complete dependent test set' reading of `capsule.tests` is rejected for
    that reason rather than trimmed to fit."""
    from knowledge.company_os.capsules.budget import DEFAULT_BUDGET

    assert DEFAULT_BUDGET.max_list_items == 8
    assert DEFAULT_BUDGET.max_capsule_chars == 4000
    assert all(len(capsule.tests) <= 8 for capsule in seeds.all())


# --------------------------------------------------------------------------
# Governed production subsystems  (the P6A B2 residual)
# --------------------------------------------------------------------------


def test_the_two_governed_production_packages_are_found_and_owned(repo_graph, seeds):
    """Exactly two production packages are reached by a Company OS suite, and
    both now have an owner. The second, `tools/youtube_fetch`, was found by
    this rule rather than by anybody noticing it."""
    found = governed_production_subsystems(
        repo_graph,
        seeds,
        company_os_roots=COMPANY_OS_ROOTS,
        production_roots=production_roots(REPO_ROOT),
    )
    assert {item.package for item in found} == {
        "tools/engineering_runner",
        "tools/youtube_fetch",
    }
    assert all(item.owned for item in found)


def test_intentionally_unowned_production_code_is_not_flagged(repo_graph, seeds):
    """`sloped/`, `race/`, `engine/` and the rest of the simulation tree are
    ungoverned on purpose. No Company OS suite imports them, so the rule never
    asks them for an owner - which is the whole distinction it exists to make."""
    found = governed_production_subsystems(
        repo_graph,
        seeds,
        company_os_roots=COMPANY_OS_ROOTS,
        production_roots=production_roots(REPO_ROOT),
    )
    packages = {item.package for item in found}
    for root in ("sloped", "race", "race2", "engine", "rendering", "production"):
        assert not any(package.startswith(root) for package in packages)


def test_deleting_a_capsule_makes_its_subsystem_unowned(tmp_path, repo_graph):
    """The residual, reproduced. The store stays internally consistent and the
    package stays in the graph, because the imports that prove the contract
    depends on it are not deleted with the capsule."""
    short = tmp_path / "seeds"
    shutil.copytree(SEED_ROOT, short)
    (short / "company-external-engineering-runner.json").unlink()
    index = CapsuleIndex.load(short)
    assert index.integrity() == ()

    found = governed_production_subsystems(
        repo_graph,
        index,
        company_os_roots=COMPANY_OS_ROOTS,
        production_roots=production_roots(REPO_ROOT),
    )
    unowned = [item.package for item in found if not item.owned]
    assert unowned == ["tools/engineering_runner"]


# --------------------------------------------------------------------------
# What the derived required set does with all of this
# --------------------------------------------------------------------------


def test_no_company_os_suite_is_undeclared_any_more(repo_graph, seeds):
    """The eleven P6A reported are the eleven this closes, and the mechanism
    is derivation rather than a list: all 38 Company OS suites import
    capsule-owned code, so a twelfth is required the day it is written."""
    required = resolve_required_suites(seeds, graph=repo_graph)
    assert undeclared_company_os_suites(REPO_ROOT, required) == ()
    on_disk = {
        f"tests/{path.name}" for path in (REPO_ROOT / "tests").glob("test_company*.py")
    }
    observed = {item.suite for item in required.by_origin(SuiteOrigin.DEPENDENCY_OBSERVED)}
    # Every Company OS suite in the directory, not a number that has to be
    # edited each time one is added. That is the property P6B bought: the
    # twelfth undeclared suite is required the day it imports governed code.
    assert observed == on_disk


def test_the_eleven_previously_undeclared_suites_are_now_required(repo_graph, seeds):
    eleven = (
        "tests/test_company_bounded_engineering_activation.py",
        "tests/test_company_bounded_engineering_autonomy.py",
        "tests/test_company_context_expansion.py",
        "tests/test_company_delegation_pilot.py",
        "tests/test_company_executable_work_planning.py",
        "tests/test_company_executive_planning.py",
        "tests/test_company_objective_planning.py",
        "tests/test_company_review_separation.py",
        "tests/test_company_runtime_integration.py",
        "tests/test_company_session_execution.py",
        "tests/test_company_youtube_end_to_end.py",
    )
    required = resolve_required_suites(seeds, graph=repo_graph)
    for suite in eleven:
        item = required.get(suite)
        assert item is not None, suite
        assert SuiteOrigin.DEPENDENCY_OBSERVED in item.origins
        assert item.dependency_capsule_ids


def test_a_dependency_observed_suite_is_never_described_as_declared(repo_graph, seeds):
    """The capsules a suite *imports* are not the capsules that *named* it.
    Merging the two put "declared by ai-platform" in a report for a suite
    ai-platform has never mentioned."""
    required = resolve_required_suites(seeds, graph=repo_graph)
    item = required.get("tests/test_company_context_expansion.py")
    assert item.origins == (SuiteOrigin.DEPENDENCY_OBSERVED,)
    assert item.capsule_ids == ()
    assert "declared by" not in item.reason()
    assert "imports code owned by" in item.reason()


def test_missing_dependency_evidence_is_unresolved_not_a_smaller_set(seeds):
    """The same rule as a missing capsule index, one source along. A caller
    with no graph has not learned that nothing is dependency-observed; leaving
    it out must not be the cheapest way to shrink the gate."""
    without = resolve_required_suites(seeds)
    assert not without.resolved
    assert any("dependency evidence" in reason for reason in without.unresolved)


def test_a_graph_with_parse_failures_makes_the_set_unresolved(tmp_path, seeds):
    """A suite that reaches capsule-owned code could be sitting in the part
    that did not parse, so the honest answer is that the set is unknown."""
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/broken.py", "def (:\n")
    broken = _graph_of(tmp_path)
    assert broken.parse_failures
    required = resolve_required_suites(seeds, graph=broken)
    assert not required.resolved
    assert any("could not parse" in reason for reason in required.unresolved)


def test_change_scope_still_only_widens(repo_graph, seeds):
    """P6B added a source; it did not add a dial. Every scoped set is still a
    superset of the unscoped one."""
    unscoped = set(resolve_required_suites(seeds, graph=repo_graph).names())
    for scope in ((), ("sloped/scale.py",), ("company/runtime/routing.py",), ("README.md",)):
        scoped = set(
            resolve_required_suites(seeds, graph=repo_graph, changed_paths=scope).names()
        )
        assert unscoped <= scoped, scope


# --------------------------------------------------------------------------
# Bounded queries, on both sides of the boundary
# --------------------------------------------------------------------------


def test_an_impact_slice_is_bounded_and_says_when_it_is_truncated(repo_graph):
    slice_ = repo_graph.impact("company/runtime/__init__.py", limit=3)
    assert slice_.known
    for values in (
        slice_.direct_dependencies,
        slice_.direct_dependents,
        slice_.direct_tests,
        slice_.transitive_tests,
    ):
        assert len(values) <= 3
    assert slice_.truncated
    assert slice_.returned() < slice_.considered


def test_an_impact_slice_for_an_unknown_path_says_so(repo_graph):
    slice_ = repo_graph.impact("company/does_not_exist.py")
    assert not slice_.known
    assert slice_.returned() == 0


def test_the_default_query_limit_keeps_an_answer_far_smaller_than_the_graph(repo_graph):
    slice_ = repo_graph.impact("company/runtime/routing.py", limit=DEFAULT_QUERY_LIMIT)
    assert slice_.returned() < len(repo_graph.modules)


def test_a_runner_neighborhood_is_bounded_and_names_its_truncation():
    repo_map = build_repo_map(REPO_ROOT)
    view = neighborhood(repo_map, "company/runtime/routing.py", test_limit=2)
    assert len(view.tests) <= 2
    assert len(view.transitive_tests) <= 2
    assert view.considered == len(repo_map.modules)
    assert view.returned() < view.considered


# --------------------------------------------------------------------------
# The runner's own graph, pinned to the same rules
# --------------------------------------------------------------------------


def test_the_runner_map_resolves_a_facade_chain_the_same_way(facade_tree):
    """Two parsers, one contract. The runner may not import the Company OS
    package and Company OS may not import the runner, so the rule is restated
    on each side - the same pattern the runner already uses for the four
    control-plane contracts it copies - and pinned here to the same case.
    """
    runner_map = build_repo_map(facade_tree, roots=("company", "tests"))
    gate_graph = _graph_of(facade_tree)
    for path in ("company/thing/__init__.py", "company/thing/helper.py"):
        assert set(runner_map.tests_reaching(path)) == set(gate_graph.tests_reaching(path))
    assert runner_map.tests_reaching("company/thing/unrelated.py") == ()


def test_the_runner_map_reports_dynamic_imports_rather_than_resolving_them(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/target.py", "")
    _write(
        tmp_path,
        "company/loader.py",
        "import importlib\n\n\ndef go():\n    return importlib.import_module('company.target')\n",
    )
    runner_map = build_repo_map(tmp_path, roots=("company",))
    assert "company/target.py" not in runner_map.direct_dependencies("company/loader.py")
    assert any(item.startswith("company/loader.py:") for item in runner_map.unresolved_imports())


def test_the_runner_map_handles_a_cycle(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/a.py", "from company import b\n")
    _write(tmp_path, "company/b.py", "from company import a\n")
    runner_map = build_repo_map(tmp_path, roots=("company",))
    assert "company/b.py" in runner_map.transitive_dependencies("company/a.py")
    assert "company/a.py" not in runner_map.transitive_dependencies("company/a.py")


# --------------------------------------------------------------------------
# The dependency manifest: identity, and refusing stale evidence
# --------------------------------------------------------------------------


def test_a_manifest_carries_schema_identity_roots_and_a_digest(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/a.py", "from company import b\n")
    _write(tmp_path, "company/b.py", "")
    repo_map = build_repo_map(tmp_path, roots=("company",))
    manifest = DependencyManifest.of(repo_map, tree_fingerprint="tree-1")
    assert manifest.version == DEPENDENCY_MANIFEST_VERSION
    assert manifest.roots == ("company",)
    assert manifest.tree_fingerprint == "tree-1"
    assert manifest.digest()
    assert manifest.module_count == len(repo_map.modules)


def test_a_manifest_for_a_different_tree_is_refused(tmp_path):
    """The whole point of the fingerprint. A stale graph answers questions
    about code that is not there any more, and answering them confidently is
    worse than not answering."""
    _write(tmp_path, "company/__init__.py", "")
    repo_map = build_repo_map(tmp_path, roots=("company",))
    manifest = DependencyManifest.of(repo_map, tree_fingerprint="tree-1")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    assert load_dependency_manifest(path, tree_fingerprint="tree-1", roots=("company",))
    assert load_dependency_manifest(path, tree_fingerprint="tree-2", roots=("company",)) is None
    assert load_dependency_manifest(path, tree_fingerprint="tree-1", roots=("tools",)) is None


def test_a_manifest_from_a_newer_schema_version_is_refused(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    repo_map = build_repo_map(tmp_path, roots=("company",))
    payload = DependencyManifest.of(repo_map, tree_fingerprint="tree-1").to_dict()
    payload["version"] = DEPENDENCY_MANIFEST_VERSION + 1
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_dependency_manifest(path, tree_fingerprint="tree-1", roots=("company",)) is None


def test_a_missing_or_corrupt_manifest_is_refused_rather_than_guessed(tmp_path):
    missing = tmp_path / "nope.json"
    assert load_dependency_manifest(missing, tree_fingerprint="t", roots=()) is None
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert load_dependency_manifest(corrupt, tree_fingerprint="t", roots=()) is None


# --------------------------------------------------------------------------
# Change scope: intelligence, never authority
# --------------------------------------------------------------------------


def test_change_impact_answers_the_four_questions(tmp_path):
    _write(tmp_path, "company/__init__.py", "")
    _write(tmp_path, "company/core.py", "")
    _write(tmp_path, "company/user.py", "from company import core\n")
    _write(tmp_path, "tests/test_core.py", "from company import core\n")
    _write(tmp_path, "tests/test_user.py", "from company import user\n")
    repo_map = build_repo_map(tmp_path, roots=("company", "tests"))
    impact = change_impact(repo_map, ["company/core.py"])
    assert impact.dependents == ("company/user.py",)
    assert impact.direct_tests == ("tests/test_core.py",)
    assert impact.transitive_tests == ("tests/test_user.py",)


def test_change_impact_names_paths_it_has_no_answer_for(tmp_path):
    """A changed YAML file or document has no import answer, and saying so is
    different from an empty list that reads as "nothing depends on this"."""
    _write(tmp_path, "company/__init__.py", "")
    repo_map = build_repo_map(tmp_path, roots=("company",))
    impact = change_impact(repo_map, ["company/rules.yaml", "docs/note.md"])
    assert set(impact.unmapped) == {"company/rules.yaml", "docs/note.md"}


def test_change_impact_creates_no_authority():
    """Repository intelligence recommends; it never permits. `ChangeImpact`
    carries no path-authority, read-ceiling, merge or suite-skip field, and
    the authorization module does not import it."""
    fields = set(ChangeImpact.__dataclass_fields__)
    for forbidden in ("authorized", "may_write", "may_read", "ceiling", "skip", "approve"):
        assert not any(forbidden in name for name in fields), forbidden
    source = (REPO_ROOT / "tools/engineering_runner/authorization.py").read_text(
        encoding="utf-8"
    )
    assert "change_impact" not in source
    assert "ChangeImpact" not in source


# --------------------------------------------------------------------------
# The architecture boundary P6B was not allowed to cross
# --------------------------------------------------------------------------


def _imported_roots(path: Path) -> set[str]:
    """The top-level package names one file imports, from its AST.

    An AST walk rather than a text search, matching the contract
    `test_company_external_engineering_runner.py` already enforces. A
    docstring naming a module is prose about a dependency, not a dependency,
    and a guard that cannot tell those apart makes the two halves of this
    milestone undocumentable.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_company_os_does_not_import_the_external_runner():
    """The graph lives on both sides and the import does not. A dependency
    graph that broke the architecture boundary in order to describe it would
    be self-refuting."""
    for path in sorted((REPO_ROOT / "company").rglob("*.py")):
        assert "tools" not in _imported_roots(path), path


def test_the_runner_does_not_import_the_capsule_layer():
    """The other direction, read off the source, because the gate check that
    proves it only runs inside the gate."""
    banned = {"company", "ai_platform", "knowledge", "intelligence"}
    for path in sorted((REPO_ROOT / "tools/engineering_runner").glob("*.py")):
        assert not (_imported_roots(path) & banned), path


# The raw strings `test_company_session_execution.py` greps every module under
# a production root for. Restated here rather than imported because that suite
# keeps its own import surface small, and pinned by value so the two copies
# cannot drift.
_FORBIDDEN_TEXT = (
    "import company",
    "from company",
    "import ai_platform",
    "from ai_platform",
    "from knowledge.company_os",
)


def test_the_runner_does_not_even_write_the_control_plane_import_lines():
    """The stricter, text-level form of the same rule, and why both exist.

    `test_company_session_execution.py` greps production modules for these
    strings rather than parsing them. A text guard cannot tell an import from
    a docstring quoting one - and that is deliberate, because it is the only
    form of the rule that survives a module reaching the control plane by
    something other than a plain `import` statement.

    P6B tripped it. Documenting the resolver's package-facade rule meant
    writing an example import in a docstring, the AST-level test above passed,
    and the full suite caught what it could not. Both are kept: the AST test
    says what the module does, this one says what the file may contain, and
    the second is the one a new docstring will break first.
    """
    for path in sorted((REPO_ROOT / "tools/engineering_runner").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for banned in _FORBIDDEN_TEXT:
            assert banned not in text, f"{path.name} contains {banned!r}"


# --------------------------------------------------------------------------
# Gate policy: the new condition is required, and it says so out loud
# --------------------------------------------------------------------------


def test_the_new_condition_is_classified_required_in_policy():
    """P6A's rule: a check may not silently move an architectural condition
    from advisory to required. The corollary is that a *new* required
    condition is a `policy.py` diff, not a widened existing check."""
    from company.integration.policy import ADVISORY_CHECKS, REQUIRED_CHECKS

    assert "architecture.governed_subsystem_ownership" in REQUIRED_CHECKS
    assert "architecture.governed_subsystem_ownership" not in ADVISORY_CHECKS


def test_its_advisory_neighbour_stayed_advisory():
    """The two conditions say different things and are deliberately not one
    check. Folding the new one into `subsystem_ownership_bounded` would have
    promoted an advisory condition with no policy diff - exactly what P6A
    refused to do, and the reason it left the residual open."""
    from company.integration.policy import ADVISORY_CHECKS, REQUIRED_CHECKS

    assert "architecture.subsystem_ownership_bounded" in ADVISORY_CHECKS
    assert "architecture.subsystem_ownership_bounded" not in REQUIRED_CHECKS


def test_no_other_check_changed_classification():
    """The whole required/advisory split, pinned by count, so a later change
    that moves a condition across the line cannot ride in unnoticed."""
    from company.integration.policy import ADVISORY_CHECKS, REQUIRED_CHECKS

    assert len(REQUIRED_CHECKS) == 35
    assert len(ADVISORY_CHECKS) == 4
    assert not REQUIRED_CHECKS & ADVISORY_CHECKS


def test_the_new_check_is_unknown_without_a_capsule_store(repo_scan):
    """Missing evidence blocks rather than passes. A gate that cannot read the
    contracts does not know whether a subsystem still has an owner."""
    from company.integration.checks import _governed_subsystem_ownership
    from company.integration.model import GateStatus

    class _Inputs:
        as_of = AS_OF

    check = _governed_subsystem_ownership(_Inputs(), repo_scan, None, None)
    assert check.status is GateStatus.UNKNOWN
    assert check.missing_evidence


def test_the_gate_report_names_the_graph_it_derived_from(repo_scan, seeds):
    """Found by review. The report named the required set and not the fourth
    input the set came from, so a reader disputing it could not see which
    import graph produced it."""
    from company.integration.model import GateStatus
    from company.integration.report import build_report
    from company.integration.suites import SuiteEvidence

    graph = build_dependency_graph(repo_scan)
    report = build_report(REPO_ROOT, as_of=AS_OF, scan=repo_scan, suites=SuiteEvidence())
    detail = report.check("health.required_suites_pass").detail
    assert graph.fingerprint() in detail
    assert "observed importing capsule-owned code" in detail
