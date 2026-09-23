"""Reviewing evidence without gaining the authority to rewrite it.

The P3C-vs-P5 matched benchmark produced a complete evidence record and then
could not be audited. Intake refused it, correctly: scope comes from capsule
ownership, no capsule owned any `docs/` path, and a company that cannot derive
a bounded scope does not invent one. The consequence was a company structurally
unable to independently review its own evidence.

The obvious repair is the one that must not be made. `owns_paths` becomes
`authorized_paths` becomes the developer contract's `may_write`, with no role
distinction anywhere in between, so a capsule owning `docs/evidence` hands a
developer session write authority over every frozen record in the repository.
Section 2 measures that rather than asserting it.

What is here instead is one capsule owning one directory that holds no evidence
record - only attestations about them. The record being reviewed stays unowned,
and unowned is unwritable, because a path outside every `may_write` is refused
by `PathScope` rather than permitted by default.

Sections
    1. the reviewability gap, and that it is closed
    2. why the broad grant was rejected, measured
    3. the frozen record stays frozen
    4. nothing else was broadened
    5. the surfaces that were already protected still are
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from company.engineering.intake import CEORequest, IntakeOutcome, assess_request
from company.engineering.protected import DEFAULT_PROTECTED_PATHS
from company.runtime.config import load_company_config
from company.runtime.lifecycle import plan_task
from company.runtime.packets import build_session_packet
from company.validation.no_subagents import collect_no_subagent_violations
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.capsule import Capsule
from knowledge.company_os.capsules.index import SEED_ROOT
from tools.engineering_runner.authorization import PathRules

DAY = dt.date(2026, 9, 23)
REPO_ROOT = Path(__file__).resolve().parents[1]

CAPSULE_ID = "company-evidence-review"
REVIEW_SURFACE = "docs/evidence/reviews"
EVIDENCE_ROOT = "docs/evidence"
FROZEN_RECORD = (
    "docs/evidence/project_factory_repository_architecture_v1/"
    "p3c_vs_p5_matched_benchmark"
)
DEVELOPER = "software_implementation_engineer"
REVIEWER = "software_review_engineer"

# The objective the benchmark could not get a work order for. Kept the same in
# shape - an audit of a named frozen record, writing an attestation - because a
# test that closes the gap with different words has not closed it.
AUDIT_OBJECTIVE = (
    "Independently audit the frozen p3c-vs-p5 matched benchmark evidence record "
    "and write an attestation stating whether its claims hold, with provenance "
    "for the bytes reviewed."
)


@pytest.fixture(scope="module")
def config():
    return load_company_config(None)


@pytest.fixture(scope="module")
def seeds():
    return CapsuleIndex.load(SEED_ROOT)


@pytest.fixture(scope="module")
def without_the_capsule(seeds):
    """The index as it was before this milestone, for before/after comparison."""
    return CapsuleIndex([c for c in seeds.all() if c.id != CAPSULE_ID])


def a_request(objective: str, **overrides) -> CEORequest:
    fields = dict(
        request_id="req-evidence-review-test",
        objective=objective,
        requested_by="MGI",
        requested_on=DAY,
        acceptance_criteria=("The attestation states PASS, CHANGES_REQUIRED or FAIL.",),
        authorized_branch="p5-evidence-reviewability-v1",
        base_commit="19dbdb35836323015465784176ef6bf4b92ae0a3",
    )
    fields.update(overrides)
    return CEORequest(**fields)


def derive(request: CEORequest, config, index: CapsuleIndex):
    return assess_request(
        request, config.permissions, repo_root=REPO_ROOT, capsule_index=index
    )


# --- 1. the reviewability gap, and that it is closed ------------------------


def test_without_the_capsule_an_evidence_audit_cannot_be_scoped(
    config, without_the_capsule
):
    """The blocked benchmark review, reproduced: no owner, so no work order."""
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, without_the_capsule)

    assert assessment.outcome is IntakeOutcome.DECISION_REQUIRED
    assert assessment.derivation.selected_capsule_ids == ()
    assert assessment.derivation.authorized_paths == ()
    assert any(
        "no capsule owns the subject of this objective" in decision.reason
        for decision in assessment.decisions
    )


def test_the_same_audit_is_now_authorized_against_one_narrow_surface(config, seeds):
    """Evidence material can be selected for independent review - the point."""
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)

    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.derivation.selected_capsule_ids == (CAPSULE_ID,)
    assert assessment.derivation.authorized_paths == (
        REVIEW_SURFACE,
        "tests/test_company_evidence_review.py",
    )


def test_the_capsule_owns_the_attestation_surface_and_nothing_else_in_docs(seeds):
    capsule = seeds.get(CAPSULE_ID)
    assert capsule.owns_paths == (REVIEW_SURFACE,)

    owned_docs = sorted(
        path
        for other in seeds.all()
        for path in other.owns_paths
        if path.startswith("docs/")
    )
    assert owned_docs == [REVIEW_SURFACE]


def test_the_review_surface_holds_no_evidence_record():
    """An attestation is the output of a review, never the subject of one.

    If a record were ever placed inside the writable surface it would become
    writable, and every other guard here would still pass. A first version of
    this test looked only for subdirectories, which a record file dropped
    straight into the surface would have walked past.
    """
    surface = REPO_ROOT / REVIEW_SURFACE
    assert surface.is_dir()
    assert sorted(p.name for p in surface.iterdir() if p.is_dir()) == []

    # The shapes an evidence record arrives in. An attestation is prose about
    # a record; a manifest, an accounting file or a raw capture *is* one.
    record_shaped = sorted(
        p.name
        for p in surface.rglob("*")
        if p.is_file()
        and (
            p.suffix in {".json", ".csv", ".jsonl"}
            or p.name.endswith(".sha256")
            or "manifest" in p.name.lower()
        )
    )
    assert record_shaped == [], (
        "a record-shaped file inside the writable review surface is writable "
        "evidence; attestations go here, records do not"
    )


# --- 2. why the broad grant was rejected, measured --------------------------


def _index_owning(path: str) -> CapsuleIndex:
    """The engineering capsule, rewritten to own `path` as well. Never stored."""
    seed = json.loads(
        (SEED_ROOT / "company-engineering-execution.json").read_text(encoding="utf-8")
    )
    seed["owns_paths"] = ["company/engineering", path]
    return CapsuleIndex([Capsule.from_dict(seed)])


@pytest.mark.parametrize("granted", [EVIDENCE_ROOT, "docs"])
def test_owning_the_evidence_root_would_hand_a_developer_the_frozen_record(
    config, granted
):
    """The rejected design, run: `owns_paths` *is* developer write authority.

    There is no role screen between the two. This is why the fix is a capsule
    that owns a directory holding no evidence, rather than a capsule that owns
    the evidence and is trusted to only read it.
    """
    assessment = derive(
        a_request(
            "Audit the frozen benchmark evidence record held in the engineering "
            "evidence surface and record whether its claims hold.",
            capsule_hints=("company-engineering-execution",),
        ),
        config,
        _index_owning(granted),
    )

    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert granted in assessment.derivation.authorized_paths

    contract = assessment.work_order.employee_contract(config, DEVELOPER)
    reaches_frozen = [
        rule
        for rule in contract["may_write"]
        if FROZEN_RECORD == rule or FROZEN_RECORD.startswith(rule + "/")
    ]
    assert reaches_frozen == [granted], (
        "a docs path in owns_paths grants write over every frozen record under it"
    )


def test_the_chosen_design_grants_no_authority_over_any_evidence_record(config, seeds):
    """The same measurement against what was actually built."""
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    contract = assessment.work_order.employee_contract(config, DEVELOPER)

    reaches_frozen = [
        rule
        for rule in contract["may_write"]
        if FROZEN_RECORD == rule or FROZEN_RECORD.startswith(rule + "/")
    ]
    assert reaches_frozen == []
    assert EVIDENCE_ROOT not in contract["may_write"]
    assert "docs" not in contract["may_write"]
    assert not any(
        rule.startswith("docs/") and rule != REVIEW_SURFACE
        for rule in contract["may_write"]
    )


# --- 3. the frozen record stays frozen --------------------------------------


def test_a_session_that_changed_the_reviewed_record_is_refused(config, seeds):
    """Reviewable did not become writable: the scope that judges a diff says so.

    `path_scope` is the object receipt validation and the external runner both
    run a reported diff through, so this is the enforcement rather than a
    restatement of the grant.
    """
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    scope = assessment.work_order.path_scope()

    for path in (
        f"{FROZEN_RECORD}/RESULT.md",
        f"{FROZEN_RECORD}/accounting/pair1_control_accounting.json",
        f"{FROZEN_RECORD}/benchmark_manifest.json",
    ):
        assert not scope.permits(path)
        assert not scope.verdict([path]).ok

    # The attestation it *is* allowed to write, for contrast.
    assert scope.permits(f"{REVIEW_SURFACE}/p3c_vs_p5_attestation.md")
    assert scope.verdict([f"{REVIEW_SURFACE}/p3c_vs_p5_attestation.md"]).ok


def test_the_external_runner_would_reject_the_same_change(config, seeds):
    """The runner judges a real diff against `may_write`; it refuses this one."""
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    contract = assessment.work_order.employee_contract(config, DEVELOPER)
    rules = PathRules(
        allowed=tuple(contract["may_write"]),
        forbidden=tuple(contract["may_not_modify"]),
    )

    assert rules.violations([f"{FROZEN_RECORD}/RESULT.md"])
    assert rules.violations([f"{EVIDENCE_ROOT}/company_os_objective_planning/x.json"])
    assert rules.violations(["docs/style_rules.md"])
    assert not rules.violations([f"{REVIEW_SURFACE}/p3c_vs_p5_attestation.md"])


def test_the_reviewer_of_an_evidence_audit_holds_no_writable_path(config, seeds):
    """Read-only by construction, and the reviewed surface is named forbidden."""
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    contract = assessment.work_order.reviewer_contract(config, REVIEWER)

    assert contract["may_write"] == []
    assert REVIEW_SURFACE in contract["may_not_modify"]


def test_the_capsules_forbidden_list_does_not_refuse_a_co_selected_work_order(
    config, seeds
):
    """`must_not_modify` names frozen records only, and that is load-bearing.

    A capsule's `must_not_modify` reaches the employee contract, where overlap
    in *either* direction refuses the packet. A first draft of this capsule
    forbade `knowledge/**` and `company/**`, which meant any work order that
    selected it alongside the capsule owning `knowledge/company_os/capsules`
    derived a scope no packet could be built from - the broad protection ate
    the other capsule's own grant. The work order that changed this subsystem
    is exactly that co-selection, so the defect would have blocked its own fix.
    """
    assessment = derive(
        a_request(
            "Add a knowledge capsule that makes frozen evidence independently "
            "reviewable, declaring one narrow attestation surface, and update "
            "the capsule regression tests that change because a new seed exists.",
            capsule_hints=("company-knowledge-capsules", CAPSULE_ID),
        ),
        config,
        seeds,
    )
    order = assessment.work_order
    assert assessment.derivation.selected_capsule_ids == (
        CAPSULE_ID,
        "company-knowledge-capsules",
    )
    assert order.authorized_paths == (
        REVIEW_SURFACE,
        "knowledge/company_os/capsules",
        "tests/test_company_evidence_review.py",
        "tests/test_company_os_capsules.py",
    )

    contract = order.employee_contract(config, DEVELOPER)
    packet = build_session_packet(
        plan_task(
            order.task_specification(),
            config,
            employee_contract=contract,
            capsule_index=seeds,
        ),
        expected_branch=order.authorized_branch,
        path_scope=order.path_scope(),
        required_tests=order.required_tests,
        expected_base_commit=order.base_commit,
        employee_contract=contract,
    )
    assert packet.path_scope.allowed == order.authorized_paths

    # Still forbidden, and still not reachable from anything granted.
    assert FROZEN_RECORD.rsplit("/", 1)[0] in order.forbidden_paths


def test_the_capsule_states_that_a_correction_is_an_addendum(seeds):
    """The immutability rule lives in the capsule, which is what sessions read."""
    invariants = " ".join(seeds.get(CAPSULE_ID).invariants).lower()
    assert "addendum" in invariants
    assert "never overwritten" in invariants


# --- 4. nothing else was broadened ------------------------------------------


def _recorded_objectives() -> tuple[str, ...]:
    """Every objective this repository has actually recorded, de-duplicated."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    key == "objective"
                    and isinstance(value, str)
                    and len(value.split()) >= 4
                ):
                    found.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in sorted(REPO_ROOT.glob("docs/**/*.json")):
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return tuple(sorted(found))


def test_no_recorded_objective_derives_differently_than_it_did_before(
    config, seeds, without_the_capsule
):
    """The 'nothing else is broadened' concern, answered by replaying history.

    Selection here is by capability tag alone: the only path signal intake
    derives is `company/<token>`, which cannot match a `docs/` path. So the
    risk is a tag that fires on an unrelated objective, and the way to know is
    to run every objective the company has recorded through both indexes.
    """
    objectives = _recorded_objectives()
    assert len(objectives) >= 20, "the corpus to replay against went missing"

    def derivation(objective, index):
        try:
            assessment = derive(a_request(objective), config, index)
        except Exception as exc:  # pre-existing refusals compare equal too
            return ("raised", type(exc).__name__)
        return (
            assessment.outcome.value,
            assessment.derivation.selected_capsule_ids,
            assessment.derivation.authorized_paths,
        )

    changed = [
        objective
        for objective in objectives
        if derivation(objective, without_the_capsule) != derivation(objective, seeds)
    ]
    assert changed == []


# Objectives an engineer would plausibly write that are *not* evidence review.
# Named here rather than mined from the recorded corpus: the first version of
# this suite relied on the corpus alone, it contained none of these words, and
# so it reported "nothing else is broadened" while the capsule's `audit` and
# `provenance` tags were pulling in every one of them. A corpus can only show
# what somebody already wrote down.
NOT_EVIDENCE_REVIEW = (
    "Audit the finance ledger so an unknown provider cost is never recorded as zero.",
    "Audit the workforce registry for roles in a restricted state that emit a "
    "writable contract.",
    "Audit the delegation policy for a seat that can approve its own review outcome.",
    "Add provenance to the research ingestion record so an external id keeps its case.",
    "Record the provenance of every YouTube Studio row the dashboard shows.",
    "Review the dashboard identity defect across the ten record kinds it spanned.",
)


@pytest.mark.parametrize("objective", NOT_EVIDENCE_REVIEW)
def test_an_ordinary_objective_does_not_route_to_the_review_capsule(
    config, seeds, objective
):
    """The capability tags are the whole routing surface, so they must be narrow.

    Intake derives one path signal per token, `company/<token>`, which can
    never match a `docs/` path. A capsule owning only documentation is
    therefore reachable by capability tag alone - and a tag that is an ordinary
    engineering word routes unrelated work here, which both widens that work's
    scope and, when this capsule is the only match, sends it to the wrong place
    entirely.
    """
    try:
        assessment = derive(a_request(objective), config, seeds)
    except Exception:  # a pre-existing refusal is not this capsule's doing
        return
    assert CAPSULE_ID not in assessment.derivation.selected_capsule_ids
    assert REVIEW_SURFACE not in assessment.derivation.authorized_paths


def test_no_capability_tag_is_an_ordinary_engineering_word(seeds):
    """Stated as a list, so adding a broad tag back is a visible decision."""
    assert seeds.get(CAPSULE_ID).capabilities == (
        "attestation",
        "evidence_review",
        "reviewability",
    )


def test_an_unrelated_docs_objective_is_still_refused(config, seeds):
    """Owning one directory under docs/ did not make docs/ reviewable."""
    assessment = derive(
        a_request("Rewrite the sloped race style guide held in the docs tree."),
        config,
        seeds,
    )
    assert assessment.outcome is IntakeOutcome.DECISION_REQUIRED
    assert CAPSULE_ID not in assessment.derivation.selected_capsule_ids


def test_an_ordinary_engineering_objective_keeps_its_exact_scope(config, seeds):
    """The engineering ceiling did not move because a docs capsule now exists."""
    assessment = derive(
        a_request(
            "Update the exact engineering execution regression expectations that "
            "change because the capsule names a further semantic test.",
            capsule_hints=("company-engineering-execution",),
        ),
        config,
        seeds,
    )
    assert assessment.derivation.selected_capsule_ids == (
        "company-engineering-execution",
    )
    assert assessment.derivation.authorized_paths == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
    )


# --- 5. the surfaces that were already protected still are ------------------


def test_the_protected_surface_is_unchanged_and_still_captured(config, seeds):
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    assert assessment.work_order.protected.paths == tuple(sorted(DEFAULT_PROTECTED_PATHS))


def test_the_capsule_seed_carries_no_subagent_switch(seeds):
    seed = json.loads((SEED_ROOT / f"{CAPSULE_ID}.json").read_text(encoding="utf-8"))
    assert collect_no_subagent_violations(seed) == []


def test_the_work_order_task_still_forbids_nested_agents(config, seeds):
    assessment = derive(a_request(AUDIT_OBJECTIVE), config, seeds)
    contract = assessment.work_order.employee_contract(config, DEVELOPER)
    assert contract["no_subagents"] is True
    assert collect_no_subagent_violations(contract) == []
