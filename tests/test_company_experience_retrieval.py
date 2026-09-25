"""P6C: retrieval, abstention, the authority invariant, the advisory, the replay.

Synthetic repository, synthetic capsules, synthetic import graph - so every
adversarial case can be built exactly - plus one test that revalidates against
this repository's own P6B graph, and command-line tests that drive the real
capture over real engineering records.

The invariant these tests exist for:

    learning optimises allowed resources; learning never creates authority.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from company.experience import (
    ABSTENTION_CODES,
    ADVICE_KEYS,
    AUTHORITY_KEYS,
    ChosenAction,
    DecisionFeatures,
    EvidenceBasis,
    ExperienceEpisode,
    ExperienceError,
    ExperienceQuery,
    ExperienceStore,
    ObservedOutcome,
    PrecedentClass,
    RecordPointer,
    RepositoryView,
    ResourceObservation,
    assert_no_authority_keys,
    build_advice,
    retrieve,
)
from company.experience import __main__ as experience_cli
from company.experience.advice import MAX_ADVICE_CHARS, advice_fingerprint
from company.experience.model import FindingNote
from company.experience.replay import CorpusSource, replay_fingerprint, run_replay
from company.experience.repository import capture_provenance
from company.integration.dependencies import DependencyGraph
from knowledge.company_os.capsules import Capsule, CapsuleIndex, CapsuleType
from knowledge.company_os.records import RecordStatus

import test_company_experience_store as flows


ROOT = Path(__file__).resolve().parents[1]
D0 = dt.date(2026, 9, 1)
DAY = dt.date(2026, 9, 18)
LATER = dt.date(2026, 9, 20)

FILES = {
    "pkg/__init__.py": "",
    "pkg/alpha/__init__.py": "",
    "pkg/alpha/core.py": "from pkg.alpha import helper\n\ndef run():\n    return helper.help()\n",
    "pkg/alpha/helper.py": "def help():\n    return 1\n",
    "pkg/alpha/secret.py": "KEY = 'not for this task'\n",
    "pkg/alpha/notes.md": "notes\n",
    "pkg/beta/__init__.py": "",
    "pkg/beta/other.py": "def other():\n    return 2\n",
    "tests/test_alpha.py": "from pkg.alpha import core\n",
    "tests/test_alpha_helper.py": "from pkg.alpha import helper\n",
    "tests/test_beta.py": "from pkg.beta import other\n",
}

EDGES = {
    "pkg/alpha/core.py": ("pkg/alpha/helper.py",),
    "tests/test_alpha.py": ("pkg/alpha/core.py",),
    "tests/test_alpha_helper.py": ("pkg/alpha/helper.py",),
    "tests/test_beta.py": ("pkg/beta/other.py",),
}


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _capsule(capsule_id: str, owns: tuple[str, ...], tests: tuple[str, ...], **changes) -> Capsule:
    values = dict(
        id=capsule_id,
        type=CapsuleType.MODULE,
        title=capsule_id,
        purpose="A synthetic boundary that exists so a test has something to govern.",
        owner="company-os",
        source="tests/test_company_experience_retrieval.py",
        created=D0,
        last_reviewed=D0,
        owns_paths=owns,
        tests=tests,
        invariants=("A synthetic invariant.",),
    )
    values.update(changes)
    return Capsule(**values)


def _capsules(**overrides) -> CapsuleIndex:
    alpha = _capsule("cap-alpha", ("pkg/alpha",), ("tests/test_alpha.py",))
    beta = _capsule("cap-beta", ("pkg/beta",), ("tests/test_beta.py",))
    return CapsuleIndex(overrides.get(c.id, c) for c in (alpha, beta))


def _graph_builder(edges=None, modules=None):
    def build(_root):
        return DependencyGraph(
            edges=dict(EDGES if edges is None else edges),
            modules=tuple(modules if modules is not None else (p for p in FILES if p.endswith(".py"))),
        )

    return build


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _view(repo: Path, *, capsules=None, graph_builder=None) -> RepositoryView:
    return RepositoryView(
        repo_root=repo,
        capsules=capsules if capsules is not None else _capsules(),
        graph_builder=graph_builder or _graph_builder(),
    )


def _episode(
    source: Path,
    view: RepositoryView,
    wo: str,
    *,
    klass: str = "accepted",
    attempt: int = 1,
    write=("pkg/alpha",),
    read=("pkg/alpha", "tests"),
    tests=("tests/test_alpha.py",),
    changed=("pkg/alpha/core.py",),
    files_read=(),
    risk="medium",
    ceiling="D",
    specialist="",
    review_capability="code_review",
    decided: dt.date = DAY,
    settled: dt.date = DAY,
    findings=(),
    expansions_approved=(),
    tests_passed=None,
) -> ExperienceEpisode:
    pointers = []
    for role, ref in (
        ("work_order", f"engineering/work_orders/{wo}/000001.json"),
        ("packet", f"execution/packets/{wo}/{attempt:06d}.json"),
        ("review", f"engineering/reviews/{wo}/{attempt:06d}.json"),
    ):
        path = source / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{wo}:{role}:{attempt}\n", encoding="utf-8")
        pointers.append(RecordPointer(role=role, record_ref=ref, digest=hashlib.sha256(path.read_bytes()).hexdigest()[:16]))
    accepted = klass == "accepted"
    outcome = ObservedOutcome(
        settled_state="ready_for_approval" if accepted else "decision_required",
        receipt_outcome="accepted",
        recorded_outcome="accepted",
        evidence_format_rejections=0,
        files_changed=tuple(changed),
        files_read=tuple(files_read),
        tests_passed=tuple(tests if tests_passed is None else tests_passed),
        tests_failed=(),
        required_tests_missing=(),
        expansions_approved=tuple(expansions_approved),
        expansions_rejected=(),
        review_outcome="pass" if accepted else "changes_required",
        review_findings=tuple(findings)
        or (() if accepted else (FindingNote("f-1", "changes_required", "the helper was bypassed instead of fixed"),)),
        unanswered_criteria=0,
        gate_readiness="ready" if accepted else "",
        gate_blockers=0,
    )
    features = DecisionFeatures(
        attempt=attempt,
        write_paths=tuple(write),
        read_paths=tuple(read),
        forbidden_paths=(),
        forbidden_read_paths=(),
        required_tests=tuple(tests),
        capabilities=("software_implementation",),
        review_capability=review_capability,
        capsule_ids=("cap-alpha",),
        risk=risk,
        reasoning_class_ceiling=ceiling,
        specialist_domain=specialist,
        novel=False,
        escalation="none",
        resource_profile="consumer",
        max_developer_attempts=1,
        acceptance_criteria_count=1,
    )
    return ExperienceEpisode(
        work_order_id=wo,
        work_order_fingerprint=_hex(wo),
        packet_fingerprint=_hex(wo + "p"),
        packet_attempt=attempt,
        receipt_fingerprint=_hex(wo + "r"),
        decided_on=decided,
        settled_on=settled,
        features=features,
        action=ChosenAction(
            employee="software_engineer", reasoning_class="C", resource_class="C", executor="claude_code",
            context_capsules=("cap-alpha",), context_files=(), context_tests=tuple(tests), context_fingerprint="",
        ),
        outcome=outcome,
        resources=ResourceObservation.unavailable(),
        evidence=tuple(pointers),
        provenance=capture_provenance(
            view, captured_on=settled, decision_capsules=("cap-alpha",), changed=changed, read=files_read, tests=tests
        ),
    )


def _query(**changes) -> ExperienceQuery:
    values = dict(
        work_order_id="wo-now",
        attempt=1,
        write_paths=("pkg/alpha",),
        read_paths=("pkg/alpha", "tests"),
        forbidden_read_paths=(),
        required_tests=("tests/test_alpha.py",),
        risk="medium",
        reasoning_class_ceiling="D",
        specialist_domain="",
        review_capability="code_review",
    )
    values.update(changes)
    return ExperienceQuery(**values)


class World:
    """A synthetic repository, a state directory of episodes, and a store."""

    def __init__(self, tmp_path: Path) -> None:
        self.repo = _repo(tmp_path)
        self.source = tmp_path / "state"
        self.store = ExperienceStore(self.source)
        self.view = _view(self.repo)

    def add(self, wo: str, **kwargs) -> ExperienceEpisode:
        episode = _episode(self.source, self.view, wo, **kwargs)
        self.store.put(episode)
        return episode

    def retrieve(self, query=None, view=None):
        return retrieve(
            query or _query(),
            view or self.view,
            scan=self.store.scan(),
            resolve_source=lambda label: self.source if label == "local" else None,
        )

    def advise(self, query=None, view=None):
        query = query or _query()
        view = view or self.view
        return build_advice(query, self.retrieve(query, view), view, work_order_fingerprint=_hex("now"), as_of=LATER)


# --- structured, explainable, deterministic --------------------------------------


def test_a_related_accepted_episode_is_precedent_and_says_why(tmp_path):
    world = World(tmp_path)
    world.add("wo-past")
    result = world.retrieve()
    assert result.status == "precedent"
    [candidate] = result.precedents
    assert candidate.signals.writable_targets == ("pkg/alpha/core.py",)
    assert candidate.signals.shared_tests == ("tests/test_alpha.py",)
    assert candidate.signals.shared_capsules == ("cap-alpha",)
    why = " | ".join(candidate.why())
    assert "changed file(s) inside this task's write scope: pkg/alpha/core.py" in why
    assert "shares 1 required suite(s)" in why and "cap-alpha" in why and "settled 2026-09-18" in why


def test_retrieval_and_advice_are_deterministic(tmp_path):
    world = World(tmp_path)
    world.add("wo-a")
    world.add("wo-b", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    world.add("wo-c", klass="correction")
    first, second = world.advise(), world.advise()
    assert first == second
    assert first["fingerprint"] == advice_fingerprint(first)


def test_more_specific_structural_agreement_ranks_first(tmp_path):
    world = World(tmp_path)
    world.add("wo-one-file")
    world.add("wo-two-files", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    assert [c.episode.work_order_id for c in world.retrieve().precedents] == ["wo-two-files", "wo-one-file"]


def test_ties_break_by_recency_then_by_id(tmp_path):
    world = World(tmp_path)
    world.add("wo-old", decided=DAY, settled=DAY)
    world.add("wo-new", decided=LATER, settled=LATER)
    assert [c.episode.work_order_id for c in world.retrieve().precedents] == ["wo-new", "wo-old"]
    twins = World(tmp_path / "twins")
    a = twins.add("wo-x")
    b = twins.add("wo-y")
    expected = sorted([a.experience_id, b.experience_id])
    assert [c.experience_id for c in twins.retrieve().precedents] == expected


def test_the_query_never_reads_objective_text():
    fields = {f.name for f in dataclasses.fields(ExperienceQuery)}
    assert "objective" not in fields
    source = (ROOT / "company" / "experience" / "retrieval.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "objective" not in attributes


# --- abstention: no precedent is better than false precedent --------------------


def test_an_empty_store_abstains_with_no_history(tmp_path):
    world = World(tmp_path)
    result = world.retrieve()
    assert (result.status, result.abstention) == ("abstain", "no_history")


def test_an_unrelated_task_abstains(tmp_path):
    world = World(tmp_path)
    world.add("wo-alpha")
    result = world.retrieve(_query(write_paths=("pkg/beta",), read_paths=("pkg/beta",), required_tests=("tests/test_beta.py",)))
    assert (result.status, result.abstention) == ("abstain", "no_match")
    assert result.precedents == () and result.warnings == ()


def test_the_same_words_in_another_subsystem_abstain(tmp_path):
    """Two work orders with an identical objective and different subsystems."""
    from company.engineering.work_order import EngineeringWorkOrder

    objective = "Tighten the helper so it refuses malformed input before anything reads it."
    alpha = EngineeringWorkOrder(
        work_order_id="wo-alpha", objective=objective, requested_by="MGI", request_id="req-a",
        authorized_branch="eng-a", authorized_paths=("pkg/alpha",), acceptance_criteria=("done",),
        authorized_on=DAY, authorized_read_paths=("pkg/alpha",), required_tests=("tests/test_alpha.py",),
        review_capability="code_review", resource_profile="consumer", max_developer_attempts=1,
    )
    beta = dataclasses.replace(
        alpha, work_order_id="wo-beta", request_id="req-b", authorized_branch="eng-b",
        authorized_paths=("pkg/beta",), authorized_read_paths=("pkg/beta",), required_tests=("tests/test_beta.py",),
    )
    world = World(tmp_path)
    world.add("wo-alpha", write=alpha.authorized_paths, read=alpha.authorized_read_paths, tests=alpha.required_tests)
    result = world.retrieve(ExperienceQuery.from_work_order(beta))
    assert result.abstention == "no_match"


def test_the_same_subsystem_under_a_different_risk_is_incompatible(tmp_path):
    world = World(tmp_path)
    world.add("wo-low", risk="low")
    result = world.retrieve(_query(risk="high"))
    assert (result.status, result.abstention) == ("abstain", "incompatible_only")
    assert "risk" in result.detail and result.excluded.get("incompatible") == 1


@pytest.mark.parametrize(
    "field, precedent, task",
    [
        ("reasoning_class_ceiling", "C", "D"),
        ("specialist_domain", "", "security"),
        ("review_capability", "code_review", "software_architecture"),
    ],
)
def test_every_routing_input_must_match(tmp_path, field, precedent, task):
    world = World(tmp_path)
    kwargs = {"ceiling" if field == "reasoning_class_ceiling" else "specialist" if field == "specialist_domain" else field: precedent}
    world.add("wo-past", **kwargs)
    result = world.retrieve(_query(**{field: task}))
    assert result.abstention == "incompatible_only"


def test_only_stale_experience_abstains_and_is_listed_as_history(tmp_path):
    world = World(tmp_path)
    world.add("wo-past")
    moved = _capsules(**{"cap-alpha": _capsule("cap-alpha", ("pkg/alpha",), ("tests/test_alpha.py", "tests/test_alpha_helper.py"))})
    view = _view(world.repo, capsules=moved)
    result = world.retrieve(view=view)
    assert (result.status, result.abstention) == ("abstain", "stale_only")
    assert [c.validity.status.value for c in result.historical] == ["stale"]
    advice = world.advise(view=view)
    assert advice["suggested_files"] == [] and advice["suggested_tests"] == []
    assert advice["historical_only"][0]["validity"] == "stale"


def test_only_failed_experience_never_becomes_success_precedent(tmp_path):
    world = World(tmp_path)
    world.add("wo-failed", klass="correction", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    result = world.retrieve()
    assert (result.status, result.abstention) == ("abstain", "correction_only")
    assert result.precedents == ()
    assert [c.precedent_class for c in result.warnings] == [PrecedentClass.CORRECTION]
    advice = world.advise()
    assert advice["suggested_files"] == [] and advice["precedents"] == []
    assert "helper was bypassed" in advice["warnings"][0]["lines"][0]


def test_a_failure_with_stronger_signals_is_still_only_a_warning(tmp_path):
    world = World(tmp_path)
    world.add("wo-weak-success")
    world.add("wo-strong-failure", klass="correction", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    result = world.retrieve()
    assert [c.episode.work_order_id for c in result.precedents] == ["wo-weak-success"]
    assert [c.episode.work_order_id for c in result.warnings] == ["wo-strong-failure"]


def test_every_abstention_code_is_declared():
    assert set(ABSTENTION_CODES) == {
        "no_history", "experience_unavailable", "no_match", "incompatible_only", "stale_only", "correction_only",
    }


def test_a_precedents_own_work_order_is_never_its_precedent(tmp_path):
    world = World(tmp_path)
    world.add("wo-now")
    result = world.retrieve()
    assert result.abstention == "no_history" or result.excluded.get("same_work_order") == 1
    assert result.precedents == ()


def test_the_future_is_invisible_to_a_decision(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", decided=DAY, settled=DAY)
    same_day = world.retrieve(_query(decided_on=DAY))
    assert same_day.status == "abstain" and same_day.excluded.get("not_yet_settled") == 1
    next_day = world.retrieve(_query(decided_on=DAY + dt.timedelta(days=1)))
    assert next_day.status == "precedent"


# --- learning never creates authority --------------------------------------------


def test_an_unauthorized_historical_file_is_refused(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", changed=("pkg/alpha/core.py", "pkg/alpha/secret.py"))
    query = _query(forbidden_read_paths=("pkg/alpha/secret.py",))
    advice = world.advise(query)
    paths = [f["path"] for f in advice["suggested_files"]]
    assert "pkg/alpha/secret.py" not in paths and "pkg/alpha/core.py" in paths
    assert {"item": "file:pkg/alpha/secret.py", "reason": "forbidden to read by this work order"} in advice["refused"]


def test_history_cannot_expand_the_read_scope(tmp_path):
    """The precedent read and changed files this task may not read."""
    world = World(tmp_path)
    world.add(
        "wo-wide",
        write=("pkg",),
        read=("pkg", "tests"),
        changed=("pkg/alpha/core.py", "pkg/beta/other.py"),
        files_read=("pkg/beta/other.py",),
    )
    query = _query(read_paths=("pkg/alpha/core.py", "tests"))
    advice = world.advise(query)
    for item in advice["suggested_files"]:
        assert any(item["path"] == rule or item["path"].startswith(rule + "/") for rule in query.read_paths)
    assert {"item": "file:pkg/beta/other.py", "reason": "outside this work order's current read authority"} in advice["refused"]


def test_an_empty_read_scope_grants_nothing_whatever_history_says(tmp_path):
    world = World(tmp_path)
    world.add("wo-past")
    advice = world.advise(_query(read_paths=()))
    assert advice["suggested_files"] == [] and advice["suggested_tests"] == []
    assert all("read authority" in item["reason"] for item in advice["refused"])


def test_the_advice_carries_no_authority_vocabulary_at_any_depth(tmp_path):
    world = World(tmp_path)
    world.add("wo-past")
    world.add("wo-failed", klass="correction")
    advice = world.advise()
    assert set(advice) <= ADVICE_KEYS
    assert_no_authority_keys(advice)
    text = json.dumps(advice)
    for key in ("may_read", "may_write", "required_tests", "risk", "reasoning_class", "authorized_paths", "approve"):
        assert f'"{key}"' not in text


@pytest.mark.parametrize("key", sorted(AUTHORITY_KEYS))
def test_an_injected_authority_field_is_refused_wherever_it_hides(key):
    with pytest.raises(ExperienceError, match="authority"):
        assert_no_authority_keys({"suggested_files": [{"path": "pkg/alpha/core.py", key: ["pkg"]}]})
    with pytest.raises(ExperienceError):
        assert_no_authority_keys({key: True})


def test_history_cannot_skip_or_replace_a_required_suite(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", tests=("tests/test_alpha.py", "tests/test_alpha_helper.py"))
    query = _query(required_tests=("tests/test_alpha.py",))
    advice = world.advise(query)
    suggested = {t["path"] for t in advice["suggested_tests"]}
    assert "tests/test_alpha.py" not in suggested, "a required suite is required, not suggested"
    assert suggested == {"tests/test_alpha_helper.py"}
    assert "not a substitute" in advice["suggested_tests"][0]["reason"]


def test_the_gate_and_the_engineering_loop_never_read_experience():
    """Nothing that decides authority, requirements or readiness can see it."""
    for package in ("integration", "engineering", "runtime", "efficiency", "dashboard", "delegation"):
        for path in (ROOT / "company" / package).rglob("*.py"):
            assert "experience" not in {
                part
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in getattr(node, "names", ())
                for part in ((node.module or "") if isinstance(node, ast.ImportFrom) else alias.name).split(".")
            }, path
    from company.integration.suites import resolve_required_suites
    import inspect

    assert not any("experience" in name for name in inspect.signature(resolve_required_suites).parameters)


def test_a_risk_class_cannot_be_lowered_by_precedent(tmp_path):
    world = World(tmp_path)
    world.add("wo-low-risk-success", risk="low", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    world.add("wo-high-risk-success", risk="high")
    result = world.retrieve(_query(risk="high"))
    assert [c.episode.work_order_id for c in result.precedents] == ["wo-high-risk-success"]


# --- current P6B repository intelligence revalidates -----------------------------


def test_a_test_that_no_longer_reaches_the_task_is_refused(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", tests=("tests/test_alpha.py", "tests/test_alpha_helper.py"))
    rewired = dict(EDGES)
    rewired["tests/test_alpha_helper.py"] = ("pkg/beta/other.py",)
    rewired["pkg/alpha/core.py"] = ()
    view = _view(world.repo, graph_builder=_graph_builder(edges=rewired))
    advice = world.advise(view=view)
    assert advice["suggested_tests"] == []
    assert {
        "item": "test:tests/test_alpha_helper.py",
        "reason": "no longer statically reaches any module this task acts on",
    } in advice["refused"]


def test_a_file_missing_from_the_current_graph_is_refused(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", changed=("pkg/alpha/core.py", "pkg/alpha/helper.py"))
    modules = [p for p in FILES if p.endswith(".py") and p != "pkg/alpha/helper.py"]
    view = _view(world.repo, graph_builder=_graph_builder(modules=modules))
    advice = world.advise(view=view)
    assert [f["path"] for f in advice["suggested_files"]] == ["pkg/alpha/core.py"]
    assert {"item": "file:pkg/alpha/helper.py", "reason": "not a module in the current import graph"} in advice["refused"]


def test_without_repository_intelligence_nothing_is_suggested(tmp_path):
    world = World(tmp_path)
    world.add("wo-past")

    def broken(_root):
        raise RuntimeError("the checkout could not be parsed")

    view = _view(world.repo, graph_builder=broken)
    advice = world.advise(view=view)
    assert advice["status"] == "precedent", "the precedent itself is still worth naming"
    assert advice["suggested_files"] == [] and advice["suggested_tests"] == []
    assert all("repository intelligence unavailable" in r["reason"] for r in advice["refused"])
    assert advice["measurement"]["repository_graph"].startswith("unavailable")


def test_a_deleted_file_is_refused_even_when_history_used_it(tmp_path):
    # A file the precedent was handed by an approved expansion is not one of
    # its anchors, so the episode stays current and the item is refused alone.
    world = World(tmp_path)
    world.add("wo-past", expansions_approved=("file:pkg/alpha/notes.md",))
    (world.repo / "pkg" / "alpha" / "notes.md").unlink()
    advice = world.advise()
    assert advice["status"] == "precedent"
    assert {"item": "file:pkg/alpha/notes.md", "reason": "no longer exists"} in advice["refused"]


def test_a_deleted_changed_file_makes_the_whole_precedent_historical(tmp_path):
    world = World(tmp_path)
    world.add("wo-past", changed=("pkg/alpha/core.py", "pkg/alpha/notes.md"))
    (world.repo / "pkg" / "alpha" / "notes.md").unlink()
    result = world.retrieve()
    assert result.abstention == "stale_only"
    assert result.historical[0].validity.status.value == "invalid"


def test_revalidation_against_this_repositorys_own_p6b_graph(tmp_path):
    """The canonical graph, built from this checkout by P6B's own builder."""
    view = RepositoryView.load(ROOT)
    assert view.capsules is not None
    source = tmp_path / "state"
    store = ExperienceStore(source)
    episode = _episode(
        source, view, "wo-real",
        write=("company/engineering",),
        read=("company/engineering", "tests"),
        tests=("tests/test_company_engineering_execution.py",),
        changed=("company/engineering/lifecycle.py",),
    )
    # The synthetic capsule id is not a real one; anchor against the real store.
    episode = dataclasses.replace(
        episode,
        features=dataclasses.replace(episode.features, capsule_ids=("company-engineering-execution",)),
        provenance=capture_provenance(
            view, captured_on=DAY, decision_capsules=("company-engineering-execution",),
            changed=("company/engineering/lifecycle.py",), read=(),
            tests=("tests/test_company_engineering_execution.py", "tests/test_company_experience_store.py"),
        ),
        outcome=dataclasses.replace(
            episode.outcome,
            tests_passed=("tests/test_company_engineering_execution.py", "tests/test_company_experience_store.py"),
        ),
        experience_id="",
    )
    store.put(episode)
    query = _query(
        write_paths=("company/engineering/result.py",),
        read_paths=("company/engineering", "tests"),
        required_tests=("tests/test_company_engineering_execution.py",),
    )
    result = retrieve(query, view, scan=store.scan(), resolve_source=lambda label: source)
    assert result.status == "abstain", "a changed file outside this task's write scope is not repeatable precedent"
    query = _query(
        write_paths=("company/engineering",),
        read_paths=("company/engineering", "tests"),
        required_tests=("tests/test_company_engineering_execution.py",),
    )
    result = retrieve(query, view, scan=store.scan(), resolve_source=lambda label: source)
    assert result.status == "precedent"
    advice = build_advice(query, result, view, work_order_fingerprint=_hex("q"), as_of=LATER)
    assert advice["measurement"]["repository_graph"] == "built"
    assert [f["path"] for f in advice["suggested_files"]] == ["company/engineering/lifecycle.py"]
    assert [t["path"] for t in advice["suggested_tests"]] == ["tests/test_company_experience_store.py"]


# --- bounded --------------------------------------------------------------------------


def test_the_advice_is_bounded(tmp_path):
    world = World(tmp_path)
    many = tuple(f"pkg/alpha/generated_{i:02d}.py" for i in range(30))
    for path in many:
        (world.repo / path).write_text("X = 1\n", encoding="utf-8")
    modules = [p for p in FILES if p.endswith(".py")] + list(many)
    view = _view(world.repo, graph_builder=_graph_builder(modules=modules))
    for i in range(8):
        world.add(f"wo-s{i}", changed=many, settled=DAY + dt.timedelta(days=i), decided=DAY)
        world.add(
            f"wo-f{i}", klass="correction", changed=many,
            findings=tuple(FindingNote(f"f-{j}", "changes_required", "x" * 190) for j in range(6)),
        )
    advice = world.advise(view=view)
    assert len(json.dumps(advice, sort_keys=True, separators=(",", ":"))) <= MAX_ADVICE_CHARS + 64
    assert len(advice["precedents"]) <= 3 and len(advice["suggested_files"]) <= 5
    assert len(advice["suggested_tests"]) <= 3 and len(advice["refused"]) <= 12
    assert sum(len(w["lines"]) for w in advice["warnings"]) <= 4


# --- the command line: capture, then advise, over real engineering records -------


def _seeded_flow(tmp_path: Path, work_order_id: str) -> "flows.Flow":
    flow = flows.Flow(tmp_path, work_order_id=work_order_id, request_id=f"req-{work_order_id}")
    seeds = flow.repo / "knowledge" / "company_os" / "capsules" / "seeds"
    if not seeds.exists():
        seeds.mkdir(parents=True)
        for path in flows.SEEDS.glob("*.json"):
            (seeds / path.name).write_bytes(path.read_bytes())
    return flow


def test_suggest_captures_settled_history_then_advises(tmp_path, capsys):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    first.develop()
    first.review()
    first.gate()
    second = _seeded_flow(tmp_path, "wo-exp-b")
    second.brief(on=flows.LATER)
    state = str(first.state)
    code = experience_cli.main(
        ["suggest", "--state-dir", state, "--repo-root", str(first.repo), "--work-order", "wo-exp-b", "--on", "2026-09-21"]
    )
    assert code == 0
    advice = json.loads(capsys.readouterr().out)
    assert advice["kind"] == "company_os.experience_advice" and advice["advisory_only"] is True
    assert advice["measurement"]["capture"]["captured"] == 1
    assert advice["status"] == "precedent"
    assert [p["work_order_id"] for p in advice["precedents"]] == ["wo-exp-a"]
    assert advice["attempt"] == 1
    assert advice["fingerprint"] == advice_fingerprint(advice)
    assert "company/engineering/verify.py" in [f["path"] for f in advice["suggested_files"]]
    assert_no_authority_keys(advice)


def test_suggest_writes_nothing_but_experience(tmp_path, capsys):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    first.develop()
    first.review()
    first.gate()
    before = {
        p.relative_to(first.state).as_posix(): p.read_bytes()
        for p in first.state.rglob("*.json")
    }
    experience_cli.main(["suggest", "--state-dir", str(first.state), "--repo-root", str(first.repo), "--work-order", "wo-exp-a"])
    capsys.readouterr()
    after = {p.relative_to(first.state).as_posix(): p.read_bytes() for p in first.state.rglob("*.json")}
    assert {k: v for k, v in after.items() if not k.startswith("experience/")} == before


def test_a_broken_experience_store_degrades_to_no_precedent(tmp_path, capsys, monkeypatch):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    first.develop()
    first.review()
    first.gate()
    import company.experience.__main__ as cli

    def explode(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(cli, "retrieve", explode)
    code = cli.main(["suggest", "--state-dir", str(first.state), "--repo-root", str(first.repo), "--work-order", "wo-exp-a"])
    assert code == 0
    advice = json.loads(capsys.readouterr().out)
    assert advice["status"] == "abstain" and advice["abstention"]["code"] == "experience_unavailable"
    assert "disk unavailable" in advice["abstention"]["detail"]
    assert advice["fingerprint"] == advice_fingerprint(advice)


def test_a_corrupt_episode_is_skipped_and_counted(tmp_path, capsys):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    first.develop()
    first.review()
    first.gate()
    junk = first.state / "experience" / "episodes" / "junk-000000000000"
    junk.mkdir(parents=True)
    (junk / "000001.json").write_text("[]", encoding="utf-8")
    code = experience_cli.main(["suggest", "--state-dir", str(first.state), "--repo-root", str(first.repo), "--work-order", "wo-exp-a"])
    assert code == 0
    advice = json.loads(capsys.readouterr().out)
    assert advice["measurement"]["store_problems"] == 1


def test_suggest_refuses_a_work_order_it_cannot_read(tmp_path, capsys):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    assert experience_cli.main(
        ["suggest", "--state-dir", str(first.state), "--repo-root", str(first.repo), "--work-order", "wo-missing"]
    ) == 2


# --- the replay ---------------------------------------------------------------------------


def test_the_replay_is_leave_future_out_labelled_and_repeatable(tmp_path):
    first = _seeded_flow(tmp_path, "wo-exp-a")
    first.develop()
    first.review()
    first.gate()
    second = _seeded_flow(tmp_path, "wo-exp-b")
    second.develop(on=flows.LATER)
    second.review(on=flows.LATER)
    second.gate(on=flows.LATER)
    views = {}

    def view_for(_commit):
        return views.setdefault("v", RepositoryView.load(first.repo))

    sources = [CorpusSource("synthetic", first.state)]
    report = run_replay(sources, view_for=view_for, scratch_store=ExperienceStore(tmp_path / "scratch1"), captured_on=flows.LATER)
    rows = {row["work_order_id"]: row for row in report["rows"]}
    assert rows["wo-exp-a"]["status"] == "abstain" and rows["wo-exp-a"]["eligible_history"] == 0
    assert rows["wo-exp-b"]["top1"] == "wo-exp-a"
    assert rows["wo-exp-b"]["suggested_files"]["basis"] == EvidenceBasis.COUNTERFACTUAL.value
    assert rows["wo-exp-b"]["suggested_files_changed_later"] == ["company/engineering/verify.py"]
    again = run_replay(sources, view_for=view_for, scratch_store=ExperienceStore(tmp_path / "scratch2"), captured_on=flows.LATER)
    assert replay_fingerprint(report) == replay_fingerprint(again)
    assert report["summary"]["precedent_found"] == 1 and report["summary"]["replayed"] == 2
