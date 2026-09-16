"""Focused tests for the Company OS knowledge-capsule and retrieval layer.

The layer exists to make future context cheaper without making it wrong, so the
tests are about the two halves of that sentence: a capsule cannot grow into the
thing it replaces (size, one line per field, pointers only), and a selection
cannot quietly become untrustworthy (deterministic order, links that resolve,
staleness that fires, unrelated capsules left out).

Two of them are guards rather than features: nothing in this package may import
production code, and nothing on this branch may have loosened the no-subagent
rule (constitution rule 2).
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from ai_platform import (
    ContextKind,
    ContextManifest,
    ExecutionPolicy,
    ReasoningClass,
    SubagentPolicyViolation,
)
from ai_platform.references import assert_reference
from ai_platform.serde import dumps
from company.validation.errors import ValidationError
from company.validation.no_subagents import enforce_no_subagents
from knowledge.company_os import Freshness, KnowledgeStore, RecordStatus
from knowledge.company_os.capsules import (
    DEFAULT_BUDGET,
    Capsule,
    CapsuleError,
    CapsuleIndex,
    CapsuleType,
    SourceDigest,
    TaskQuery,
    flag_capsule_for_revalidation,
    normalise_path,
    path_related,
    refs_for_task,
    select_capsules,
)
from knowledge.company_os.capsules.index import REPO_ROOT, SEED_ROOT
from knowledge.company_os.ledger import DEFAULT_ROOT

TODAY = dt.date(2026, 9, 16)
CAPSULE_PACKAGE = Path(__file__).resolve().parents[1] / "knowledge" / "company_os" / "capsules"


def a_capsule(**overrides) -> Capsule:
    base = dict(
        id="example-module",
        type=CapsuleType.MODULE,
        title="Example module",
        purpose="A boundary that exists only so a test has something to hold.",
        owner="workstream-claude",
        source="tests/test_company_os_capsules.py",
        created=TODAY,
        last_reviewed=TODAY,
        owns_paths=("ai_platform",),
        tests=("tests/test_company_os_capsules.py",),
    )
    base.update(overrides)
    return Capsule(**base)


@pytest.fixture(scope="module")
def seeds() -> CapsuleIndex:
    return CapsuleIndex.load(SEED_ROOT)


# --------------------------------------------------------------------------
# A capsule stays small, or it is not a capsule
# --------------------------------------------------------------------------


def test_every_seed_capsule_is_inside_the_character_ceiling(seeds):
    for capsule in seeds.all():
        assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars, (
            f"{capsule.id} is {capsule.size_chars()} characters"
        )


def _chars_under(*relative: str) -> int:
    total = 0
    for name in relative:
        root = REPO_ROOT / name
        for suffix in ("*.py", "*.md", "*.yaml"):
            total += sum(len(p.read_text(encoding="utf-8")) for p in root.rglob(suffix))
    return total


def test_a_capsule_is_an_order_of_magnitude_cheaper_than_what_it_describes(seeds):
    """The whole point, as a number: the capsule or the module, not both."""
    module = _chars_under("company/runtime")
    assert module / seeds.get("company-runtime").size_chars() >= 5

    control_plane = _chars_under("company", "ai_platform", "knowledge/company_os")
    assert control_plane / seeds.total_chars() >= 8


def test_a_capsule_over_the_ceiling_cannot_be_built():
    with pytest.raises(CapsuleError, match="second README"):
        a_capsule(
            invariants=tuple("x" * DEFAULT_BUDGET.max_statement_chars for _ in range(8)),
            risks=tuple("y" * DEFAULT_BUDGET.max_statement_chars for _ in range(8)),
            inputs=tuple("z" * DEFAULT_BUDGET.max_statement_chars for _ in range(8)),
            outputs=tuple("w" * DEFAULT_BUDGET.max_statement_chars for _ in range(8)),
        )


def test_a_list_longer_than_the_budget_is_refused():
    with pytest.raises(CapsuleError, match="exceeds the 8"):
        a_capsule(invariants=tuple(f"invariant {n}" for n in range(9)))


def test_a_statement_longer_than_the_budget_is_refused():
    with pytest.raises(CapsuleError, match="exceeds the 240-character"):
        a_capsule(risks=("r" * 241,))


def test_purpose_is_prose_but_still_bounded():
    with pytest.raises(CapsuleError, match="exceeds the 400-character"):
        a_capsule(purpose="p" * 401)


def test_the_knowledge_link_total_is_capped_across_the_four_fields():
    with pytest.raises(CapsuleError, match="knowledge links exceeds"):
        a_capsule(
            facts=tuple(f"fact-{n}" for n in range(5)),
            decisions=tuple(f"decision-{n}" for n in range(5)),
            experiment_learnings=tuple(f"learning-{n}" for n in range(5)),
        )


# --------------------------------------------------------------------------
# Source cannot be smuggled in as a reference
# --------------------------------------------------------------------------


def test_a_pasted_block_fails_on_the_one_line_rule():
    source = "def match_capabilities(required, config):\n    return RoutingResult()\n"
    with pytest.raises(CapsuleError, match="one line"):
        a_capsule(owns_paths=(source,))


def test_a_single_line_of_source_fails_the_pointer_shape():
    """The one-line rule catches the dump; the pointer shape catches the one-liner."""
    with pytest.raises(CapsuleError, match="is not a reference"):
        a_capsule(owns_paths=("def match_capabilities(required, config): return 1",))


def test_prose_fields_reject_embedded_content_too():
    with pytest.raises(CapsuleError, match="one line"):
        a_capsule(invariants=("first line\nsecond line",))


def test_a_path_a_glob_and_a_test_node_id_are_all_accepted():
    capsule = a_capsule(
        owns_paths=("company/runtime", "ai_platform/*.py"),
        tests=("tests/test_company_runtime.py::test_routing",),
        benchmarks=("tests/test_company_os_capsules.py",),
    )
    assert capsule.references()[:2] == ("company/runtime", "ai_platform/*.py")


def test_every_reference_in_every_seed_capsule_passes_the_platform_guard(seeds):
    for capsule in seeds.all():
        for ref in capsule.references():
            assert_reference(ref, f"{capsule.id} reference")


# --------------------------------------------------------------------------
# Shape: four types, one dataclass, four requirements
# --------------------------------------------------------------------------


def test_a_module_must_own_a_path_and_name_a_test():
    with pytest.raises(CapsuleError, match="must own at least one path"):
        a_capsule(owns_paths=())
    with pytest.raises(CapsuleError, match="must reference at least one test"):
        a_capsule(tests=())


def test_a_system_must_name_its_parts():
    with pytest.raises(CapsuleError, match="must name its parts"):
        a_capsule(type=CapsuleType.SYSTEM, owns_paths=(), tests=())
    assert a_capsule(
        type=CapsuleType.SYSTEM, owns_paths=(), tests=(), dependencies=("ai-platform",)
    ).dependencies == ("ai-platform",)


def test_a_policy_must_state_an_invariant():
    with pytest.raises(CapsuleError, match="must state at least one invariant"):
        a_capsule(type=CapsuleType.POLICY, tests=())
    assert a_capsule(type=CapsuleType.POLICY, tests=(), invariants=("no subagents",)).invariants


def test_a_project_must_own_a_path():
    with pytest.raises(CapsuleError, match="must own at least one path"):
        a_capsule(type=CapsuleType.PROJECT, owns_paths=(), tests=())
    project = a_capsule(
        id="v30-contained-stage",
        type=CapsuleType.PROJECT,
        title="V30 contained stage",
        tests=(),
        owns_paths=("docs",),
    )
    assert project.type is CapsuleType.PROJECT


def test_a_capsule_cannot_depend_on_itself():
    with pytest.raises(CapsuleError, match="cannot depend on itself"):
        a_capsule(dependencies=("example-module",))


def test_a_review_cannot_predate_the_capsule():
    with pytest.raises(CapsuleError, match="precedes created"):
        a_capsule(last_reviewed=TODAY - dt.timedelta(days=1))


def test_an_id_that_is_not_a_filename_is_refused():
    with pytest.raises(CapsuleError, match="also filenames"):
        a_capsule(id="Company Runtime")


# --------------------------------------------------------------------------
# Serialisation is deterministic
# --------------------------------------------------------------------------


def test_a_capsule_round_trips_through_canonical_json():
    capsule = a_capsule(
        capabilities=("capability_routing",),
        decisions=("knowledge-store-is-files",),
        source_digests=(SourceDigest("ai_platform/serde.py", "deadbeef"),),
    )
    restored = Capsule.from_dict(__import__("json").loads(dumps(capsule)))
    assert restored == capsule
    assert dumps(restored) == dumps(capsule)


def test_two_equal_capsules_produce_identical_bytes():
    assert dumps(a_capsule()) == dumps(a_capsule())


def test_every_seed_file_is_already_canonical(seeds):
    """A seed re-serialised must equal the file, or the store stops diffing."""
    for capsule in seeds.all():
        on_disk = (SEED_ROOT / f"{capsule.id}.json").read_text(encoding="utf-8")
        assert dumps(capsule) == on_disk


def test_the_recheck_date_is_derived_from_the_review_not_the_creation():
    capsule = a_capsule(
        created=dt.date(2025, 1, 1), last_reviewed=TODAY, freshness=Freshness.TIME_SENSITIVE
    )
    assert capsule.recheck_on == TODAY + dt.timedelta(days=30)


# --------------------------------------------------------------------------
# Lookup is deterministic and by explicit field only
# --------------------------------------------------------------------------


def test_ids_are_sorted_and_two_loads_agree(seeds):
    again = CapsuleIndex.load(SEED_ROOT)
    assert seeds.ids() == tuple(sorted(seeds.ids()))
    assert seeds.ids() == again.ids()
    assert [c.id for c in seeds.all()] == [c.id for c in again.all()]


def test_lookup_by_every_indexed_field(seeds):
    assert seeds.get("company-runtime").type is CapsuleType.MODULE
    assert "company-os-control-plane" in {c.id for c in seeds.by_type(CapsuleType.SYSTEM)}
    assert "company-bootstrap-policy" in {c.id for c in seeds.by_type(CapsuleType.POLICY)}
    assert {c.id for c in seeds.by_owner("workstream-codex")} == {
        "company-runtime",
        "company-validation",
    }
    assert [c.id for c in seeds.by_capability("capability_routing")] == ["company-runtime"]
    assert [c.id for c in seeds.by_path("company/runtime/routing.py")] == ["company-runtime"]
    assert [c.id for c in seeds.by_decision("knowledge-store-is-files")] == [
        "company-knowledge-capsules",
        "company-knowledge-store",
    ]
    assert "company-validation" in {c.id for c in seeds.by_knowledge("bootstrap-forbids-nested-agents")}


def test_an_unknown_capsule_id_names_what_is_known(seeds):
    with pytest.raises(CapsuleError, match="company-runtime"):
        seeds.get("race2")


def test_path_matching_is_segment_aware_in_both_directions():
    assert path_related("company/runtime", "company/runtime/routing.py")
    assert path_related("company/runtime/routing.py", "company/runtime")
    assert not path_related("company/run", "company/runtime")
    assert normalise_path("./company/runtime/**") == "company/runtime"
    assert normalise_path("tests/test_x.py::test_y") == "tests/test_x.py"


def test_the_dependency_closure_terminates_on_the_real_runtime_validation_cycle(seeds):
    """company/runtime and company/validation import each other; the walk must not."""
    assert seeds.dependency_closure("company-runtime") == (
        "ai-platform",
        "company-knowledge-capsules",
        "company-knowledge-store",
        "company-validation",
    )
    assert seeds.dependency_closure("company-validation") == (
        "ai-platform",
        "company-knowledge-capsules",
        "company-knowledge-store",
        "company-runtime",
    )
    assert seeds.dependency_closure("company-os-control-plane") == tuple(
        sorted(set(seeds.ids()) - {"company-os-control-plane"})
    )


def test_duplicate_capsule_ids_fail_at_construction():
    with pytest.raises(CapsuleError, match="duplicate capsule id"):
        CapsuleIndex([a_capsule(), a_capsule(title="The same id again")])


# --------------------------------------------------------------------------
# Selection: the right capsules, and provably not the others
# --------------------------------------------------------------------------


def test_the_worked_example_from_the_brief(seeds):
    """paths=company/runtime/ + capability_routing -> the runtime capsule."""
    selection = select_capsules(
        seeds,
        TaskQuery(
            paths=("company/runtime/",),
            capabilities=("capability_routing",),
            include_dependencies=False,
        ),
    )
    assert selection.ids() == ("company-runtime",)


def test_unrelated_capsules_are_rejected_with_a_reason(seeds):
    selection = select_capsules(
        seeds, TaskQuery(paths=("company/runtime/",), include_dependencies=False)
    )
    rejected = {r.capsule_id for r in selection.rejected}
    assert "ai-platform" in rejected
    assert "company-knowledge-store" in rejected
    assert all(not r.by_budget for r in selection.rejected)
    assert all("no query signal matched" in r.reason for r in selection.rejected)


def test_a_query_with_no_matching_signal_selects_nothing(seeds):
    selection = select_capsules(seeds, TaskQuery(paths=("sloped/cameras.py",)))
    assert selection.ids() == ()
    assert selection.metrics().chars == 0


def test_dependencies_are_pulled_in_but_rank_below_direct_matches(seeds):
    selection = select_capsules(seeds, TaskQuery(paths=("company/runtime/routing.py",)))
    assert selection.ids() == (
        "company-runtime",
        "ai-platform",
        "company-knowledge-capsules",
        "company-knowledge-store",
        "company-validation",
    )
    assert all(
        match.reasons == ("dependency of company-runtime",)
        for match in selection.matches[1:]
    )


def test_an_explicit_id_outranks_an_incidental_tag_match(seeds):
    selection = select_capsules(
        seeds,
        TaskQuery(
            capsule_ids=("company-knowledge-store",),
            capabilities=("capability_routing",),
            include_dependencies=False,
        ),
    )
    assert selection.ids()[0] == "company-knowledge-store"


def test_type_and_owner_are_filters_not_signals(seeds):
    selection = select_capsules(
        seeds,
        TaskQuery(
            paths=("company/runtime", "ai_platform"),
            types=(CapsuleType.MODULE,),
            owner="workstream-codex",
            include_dependencies=False,
        ),
    )
    assert selection.ids() == ("company-runtime",)
    reasons = {r.capsule_id: r.reason for r in selection.rejected}
    assert "is not 'workstream-codex'" in reasons["ai-platform"]
    assert "type system is not module" in reasons["company-os-control-plane"]


def test_the_capsule_budget_truncates_and_says_so(seeds):
    selection = select_capsules(
        seeds,
        TaskQuery(
            capsule_ids=seeds.ids(), include_dependencies=False, max_capsules=2
        ),
    )
    metrics = selection.metrics()
    assert metrics.capsules_selected == 2
    assert metrics.rejected_by_budget == len(seeds) - 2
    assert selection.ids() == seeds.ids()[:2]


def test_selection_is_reproducible(seeds):
    query = TaskQuery(paths=("knowledge/company_os",), capabilities=("capability_freshness",))
    assert select_capsules(seeds, query).ids() == select_capsules(seeds, query).ids()


# --------------------------------------------------------------------------
# What the selector hands over is references, not text
# --------------------------------------------------------------------------


def test_refs_are_pointers_and_carry_no_capsule_text(seeds):
    refs = refs_for_task(seeds, paths=("company/runtime/",))
    assert [r.ref for r in refs] == [
        "capsule:company-runtime",
        "capsule:ai-platform",
        "capsule:company-knowledge-capsules",
        "capsule:company-knowledge-store",
        "capsule:company-validation",
    ]
    assert all(r.kind is ContextKind.MODULE_CONTRACT for r in refs)
    assert all(len(r.ref) <= 64 for r in refs)


def test_knowledge_and_test_refs_are_a_separate_opt_in(seeds):
    selection = select_capsules(
        seeds, TaskQuery(capsule_ids=("ai-platform",), include_dependencies=False)
    )
    assert [r.ref for r in selection.refs()] == ["capsule:ai-platform"]
    assert [r.ref for r in selection.knowledge_refs()] == [
        "decision:classifier-order-inverts-below-b"
    ]
    assert [r.ref for r in selection.test_refs()] == ["tests/test_company_os_ai_platform.py"]


def test_two_capsules_citing_one_decision_yield_one_reference(seeds):
    selection = select_capsules(
        seeds,
        TaskQuery(
            capsule_ids=("company-knowledge-store", "company-knowledge-capsules"),
            include_dependencies=False,
        ),
    )
    refs = [r.ref for r in selection.knowledge_refs()]
    assert refs.count("decision:knowledge-store-is-files") == 1


def test_a_selection_drops_straight_into_a_context_manifest(seeds):
    selection = select_capsules(seeds, TaskQuery(paths=("company/runtime/",)))
    manifest = ContextManifest(
        task_id="company-os-v1-knowledge-capsules",
        objective="Change capability ranking in company/runtime/routing.py",
        reasoning_class=ReasoningClass.C,
        module_contracts=selection.refs(),
        tests=selection.test_refs(),
        acceptance_criteria=("tests/test_company_runtime.py passes",),
    )
    assert manifest.validate() == ()
    assert manifest.size_chars() < seeds.total_chars()


def test_metrics_are_counts_not_token_estimates(seeds):
    metrics = select_capsules(
        seeds, TaskQuery(paths=("company/runtime/",), include_dependencies=False)
    ).metrics()
    assert metrics.capsules_considered == len(seeds)
    assert metrics.capsules_selected == 1
    assert metrics.chars == seeds.get("company-runtime").size_chars()
    assert metrics.references == len(seeds.get("company-runtime").references())
    assert metrics.duplicate_references == ()


def test_a_capsule_naming_one_pointer_twice_is_measurable():
    capsule = a_capsule(owns_paths=("ai_platform",), may_read=("ai_platform",))
    assert capsule.duplicate_references() == ("ai_platform",)


# --------------------------------------------------------------------------
# Integrity: what a capsule cannot notice about itself
# --------------------------------------------------------------------------


def test_the_shipped_seeds_are_internally_consistent(seeds):
    assert seeds.integrity(KnowledgeStore(DEFAULT_ROOT), REPO_ROOT) == ()


def test_a_link_to_a_record_that_is_not_in_the_store_is_detected():
    index = CapsuleIndex([a_capsule(facts=("a-fact-nobody-wrote",))])
    problems = index.integrity(KnowledgeStore(DEFAULT_ROOT))
    assert any("not in the knowledge store" in p for p in problems)


def test_a_dependency_on_a_capsule_nobody_defines_is_detected():
    index = CapsuleIndex([a_capsule(dependencies=("race2",))])
    assert any("does not exist" in p for p in index.integrity())


def test_two_capsules_claiming_one_path_is_two_owners_and_no_owner():
    """Spelled differently, normalised to the same claim."""
    index = CapsuleIndex(
        [a_capsule(), a_capsule(id="example-module-two", owns_paths=("ai_platform/",))]
    )
    assert any("owned by 2 capsules" in p for p in index.integrity())


def test_a_leading_dot_slash_is_not_an_accepted_spelling():
    """One canonical spelling per path, so the duplicate check cannot be dodged."""
    with pytest.raises(CapsuleError, match="is not a reference"):
        a_capsule(owns_paths=("./ai_platform",))


def test_a_path_that_left_the_repository_is_detected():
    index = CapsuleIndex([a_capsule(owns_paths=("company/departed",))])
    assert any("does not exist in the repository" in p for p in index.integrity(repo_root=REPO_ROOT))


def test_integrity_runs_without_a_store_or_a_checkout():
    assert CapsuleIndex([a_capsule()]).integrity() == ()


# --------------------------------------------------------------------------
# Freshness and revalidation
# --------------------------------------------------------------------------


def test_nothing_shipped_is_already_stale(seeds):
    assert seeds.staleness(TODAY, KnowledgeStore(DEFAULT_ROOT)) == ()


def test_an_expired_review_becomes_a_reason(seeds):
    """A day past the last recheck date, every capsule is overdue.

    Computed from the seeds rather than from TODAY, because capsules are added
    on the day they are written and a fixed offset would only ever be a year
    past whichever cohort happened to be reviewed first.
    """
    latest = max(capsule.recheck_on for capsule in seeds.all())
    stale = seeds.staleness(latest + dt.timedelta(days=1))
    assert {s.capsule_id for s in stale} == set(seeds.ids())
    assert all("review overdue" in s.reasons[0] for s in stale)


def test_a_changed_source_digest_becomes_a_reason():
    capsule = a_capsule(
        source_digests=(
            SourceDigest("ai_platform/serde.py", "aaaa"),
            SourceDigest("ai_platform/policy.py", "bbbb"),
        )
    )
    observed = {"ai_platform/serde.py": "aaaa", "ai_platform/policy.py": "cccc"}
    assert capsule.changed_sources(observed) == ("ai_platform/policy.py",)
    index = CapsuleIndex([capsule])
    reasons = index.staleness(TODAY, observed_digests=observed)[0].reasons
    assert reasons == ("source changed: ai_platform/policy.py",)


def test_a_path_the_caller_could_not_digest_counts_as_changed():
    capsule = a_capsule(source_digests=(SourceDigest("ai_platform/gone.py", "aaaa"),))
    assert capsule.changed_sources({}) == ("ai_platform/gone.py",)


def test_a_superseded_decision_makes_its_capsules_stale(tmp_path):
    from knowledge.company_os import Alternative, Decision, DecisionLedger, Evidence

    store = KnowledgeStore(tmp_path)
    ledger = DecisionLedger(store)
    common = dict(
        why="because the test needs a decision to supersede",
        evidence=(Evidence("test", "tests/test_company_os_capsules.py"),),
        alternatives=(Alternative("do nothing", "then nothing is recorded"),),
        risks=("none, it is a test",),
        reconsider_if=("the capsule layer changes shape",),
        rollback="delete the record",
        source="tests",
        created=TODAY,
    )
    ledger.record(Decision(id="first-choice", decision="choose the first thing", **common))
    ledger.supersede(
        "first-choice",
        Decision(id="second-choice", decision="choose the second thing", **common),
    )

    index = CapsuleIndex([a_capsule(decisions=("first-choice",))])
    reasons = index.staleness(TODAY, store)[0].reasons
    assert reasons == ("decision first-choice is superseded -> second-choice",)


def test_flagging_a_capsule_keeps_every_other_field():
    capsule = a_capsule(invariants=("this must stay",))
    flagged = flag_capsule_for_revalidation(capsule, "routing changed under it")
    assert flagged.status is RecordStatus.NEEDS_REVALIDATION
    assert flagged.invariants == capsule.invariants
    assert flagged.revalidation_reason == "routing changed under it"
    index = CapsuleIndex([flagged])
    assert index.staleness(TODAY)[0].reasons == ("flagged: routing changed under it",)
    assert index.needing_revalidation(TODAY) == ("example-module",)


def test_flagging_a_permanent_capsule_is_refused():
    """If an invariant needs revalidation the class was wrong, not the status."""
    capsule = a_capsule(freshness=Freshness.PERMANENT)
    assert capsule.recheck_on is None
    assert not capsule.is_stale(TODAY + dt.timedelta(days=10_000))
    with pytest.raises(CapsuleError, match="marked permanent"):
        flag_capsule_for_revalidation(capsule, "it changed")


def test_the_four_staleness_conditions_accumulate_on_one_capsule():
    capsule = flag_capsule_for_revalidation(
        a_capsule(
            freshness=Freshness.EXPERIMENTAL,
            source_digests=(SourceDigest("ai_platform/serde.py", "aaaa"),),
        ),
        "under review",
    )
    stale = CapsuleIndex([capsule]).staleness(
        TODAY + dt.timedelta(days=15), observed_digests={"ai_platform/serde.py": "bbbb"}
    )
    assert len(stale[0].reasons) == 3
    assert bool(stale[0])


# --------------------------------------------------------------------------
# The seeds describe what was actually built
# --------------------------------------------------------------------------


def test_the_company_os_seed_capsules_load(seeds):
    assert len(seeds) == 16
    assert seeds.ids() == (
        "ai-platform",
        "company-analytics-experiments",
        "company-bootstrap-policy",
        "company-ceo-dashboard",
        "company-finance",
        "company-knowledge-capsules",
        "company-knowledge-store",
        "company-organizational-intelligence",
        "company-os-control-plane",
        "company-research-intelligence",
        "company-research-operations",
        "company-runtime",
        "company-validation",
        "company-workforce-capabilities",
        "company-workforce-employment",
        "company-workforce-hiring",
    )

    core = seeds.get("company-research-intelligence")
    operations = seeds.get("company-research-operations")
    assert core.owns_paths == ("intelligence/research",)
    assert operations.owns_paths
    assert all(path.startswith("intelligence/research/") for path in operations.owns_paths)
    assert operations.tests


def test_every_seed_names_a_test_file_that_exists(seeds):
    for capsule in seeds.all():
        for test_ref in capsule.tests:
            assert (REPO_ROOT / test_ref.split("::")[0]).exists(), f"{capsule.id}: {test_ref}"


def test_the_seeds_cover_the_control_plane_and_nothing_in_production(seeds):
    owned = [path for capsule in seeds.all() for path in capsule.owns_paths]
    assert all(
        path.startswith(("company/", "ai_platform", "knowledge/", "intelligence/"))
        for path in owned
    ), owned


def test_no_seed_capsule_links_a_hypothesis(seeds):
    """A capsule is authoritative context; an open hypothesis is not (rule 16)."""
    store = KnowledgeStore(DEFAULT_ROOT)
    hypotheses = {r.id for r in store.load_all("hypothesis")}
    for capsule in seeds.all():
        assert not hypotheses & {rid for _kind, rid in capsule.knowledge_links()}


# --------------------------------------------------------------------------
# Guards: no production dependency, and rule 2 is where it was
# --------------------------------------------------------------------------

_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "ai_platform",
        "argparse",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "hashlib",
        "json",
        "knowledge",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
)


def test_the_capsule_package_imports_nothing_from_production():
    for path in sorted(CAPSULE_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in _ALLOWED_IMPORTS, f"{path.name} imports {root!r}"


def test_no_production_module_imports_the_capsule_layer():
    for directory in ("sloped", "tools"):
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert "knowledge.company_os" not in text, path
            assert "ai_platform" not in text, path


def test_the_no_subagent_rule_is_exactly_where_it_was():
    """This branch added a retrieval layer; it did not touch rule 2."""
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(no_subagents=False)
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(nested_agent_spawning=True)
    with pytest.raises(ValidationError):
        enforce_no_subagents({"no_subagents": False})
    assert ExecutionPolicy().no_subagents is True


def test_the_policy_capsule_states_the_rule_and_points_at_the_fact(seeds):
    policy = seeds.get("company-bootstrap-policy")
    assert policy.type is CapsuleType.POLICY
    assert "bootstrap-forbids-nested-agents" in policy.facts
    assert any("subagent" in invariant for invariant in policy.invariants)
    assert KnowledgeStore(DEFAULT_ROOT).get("fact", "bootstrap-forbids-nested-agents")
