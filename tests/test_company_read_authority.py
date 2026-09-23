"""Read authority: granted by the company, not acquired by holding a checkout.

The runtime has modelled read authority since Bootstrap Mode. `ExecutionAuthoritySnapshot`
carries `may_read` and `may_not_read`, `context_expansion_policy` refuses a
reference outside them, and an empty `may_read` grants nothing rather than
everything. All of that worked. Nothing ever filled it.

So every authority snapshot the company produced recorded `may_read: []`, and
every session read whatever it liked — not because it was permitted to, but
because the external process already held the repository. Possession is not
authorization, and a permission system whose grant is always empty is not
enforcing anything; it is being routed around.

This suite is about closing that. The read ceiling is now derived in intake
beside the write ceiling, carried on the immutable work order, fingerprinted
with it, and handed to both contracts.

The design in one line: **read is a property of the task, write is a property
of the role.** Both roles get the same read scope; only the developer can write.
A reviewer unable to read what the developer was allowed to change could not
review it.

Sections
    1. the before-state, and that it is gone
    2. what the read ceiling is made of
    3. developer and reviewer
    4. fail-closed, in every direction
    5. denials outrank grants
    6. the ceiling survives every boundary
    7. what did not change
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from ai_platform.context_manifest import ContextKind, ContextRef
from company.engineering.intake import (
    CEORequest,
    IntakeOutcome,
    _strip_glob,
    assess_request,
)
from company.engineering.errors import AuthorityEscalation, EngineeringError
from company.engineering.protected import ProtectedSurface
from company.engineering.work_order import (
    EngineeringWorkOrder,
    _read_covers,
    collapse_read_rules,
)
from company.runtime.authority import authority_projection
from company.runtime.config import load_company_config
from company.runtime import (
    ContextExpansionRequest,
    ExecutorHint,
    build_session_packet,
    decide_context_expansion,
    plan_task,
)
from company.validation.no_subagents import collect_no_subagent_violations
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.index import SEED_ROOT
from company.engineering.work_order import _read_covers

DAY = dt.date(2026, 9, 24)
REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = "adc8a95ffe7eedd78b58d16cc1f8493b5b4a1a4f"

DEVELOPER = "software_implementation_engineer"
REVIEWER = "software_review_engineer"

FROZEN_BENCHMARK = (
    "docs/evidence/project_factory_repository_architecture_v1/"
    "p3c_vs_p5_matched_benchmark"
)

# Repository roots that are not the control plane. No engineering work order
# has any business reading these, and the point of a ceiling is that it says so.
OUTSIDE_THE_CONTROL_PLANE = (
    "sloped/course.py",
    "race2/run.py",
    "satisfying/multishell.py",
    "docs/style_rules.md",
)

ENGINEERING_OBJECTIVE = (
    "Update the exact engineering execution regression expectations that change "
    "because the capsule names a further semantic test."
)
EVIDENCE_OBJECTIVE = (
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


def a_request(objective: str, **overrides) -> CEORequest:
    fields = dict(
        request_id="req-read-authority-test",
        objective=objective,
        requested_by="MGI",
        requested_on=DAY,
        acceptance_criteria=("The read ceiling is derived.",),
        authorized_branch="p5-read-authority-v1",
        base_commit=BASE,
    )
    fields.update(overrides)
    return CEORequest(**fields)


def derive(config, seeds, objective: str, **overrides):
    return assess_request(
        a_request(objective, **overrides),
        config.permissions,
        repo_root=REPO_ROOT,
        capsule_index=seeds,
    )


@pytest.fixture(scope="module")
def engineering(config, seeds):
    return derive(
        config, seeds, ENGINEERING_OBJECTIVE,
        capsule_hints=("company-engineering-execution",),
    )


@pytest.fixture(scope="module")
def evidence(config, seeds):
    return derive(config, seeds, EVIDENCE_OBJECTIVE)



def _expansion(config, seeds, order, contract, *refs: str):
    """Ask, through the real governed mechanism, to read `refs`.

    Built from the work order rather than a hand-made packet, so what is
    screened is the contract this milestone fills rather than a stand-in.
    """
    plan = plan_task(
        order.task_specification(),
        config,
        employee_contract=contract,
        capsule_index=seeds,
    )
    packet = build_session_packet(
        plan,
        expected_branch=order.authorized_branch,
        path_scope=order.path_scope(),
        required_tests=order.required_tests,
        expected_base_commit=order.base_commit,
        employee_contract=contract,
    )
    request = ContextExpansionRequest(
        task_id=packet.task_id,
        packet_fingerprint=packet.fingerprint(),
        request_id="expansion-read-authority",
        requested_refs=tuple(
            ContextRef(ContextKind.FILE, ref, "needed to finish the authorized work")
            for ref in refs
        ),
        reason="The authorized work cannot be completed without this reference.",
        requesting_executor=ExecutorHint.CLAUDE_CODE,
        sequence=1,
        required_to_continue=True,
    )
    return decide_context_expansion(
        packet, request, contract, capsule_index=seeds, repo_root=REPO_ROOT
    )


# --- 1. the before-state, and that it is gone -------------------------------


def test_every_capsule_declares_a_read_scope_and_always_did(seeds):
    """The declaration was never the missing half."""
    undeclared = sorted(c.id for c in seeds.all() if not c.may_read)
    assert undeclared == []


def test_the_work_order_now_carries_read_authority(engineering):
    """It is a field of the authority record, not a briefing-time calculation."""
    order = engineering.work_order
    assert order.authorized_read_paths
    assert "authorized_read_paths" in order.to_dict()
    assert "forbidden_read_paths" in order.to_dict()


def test_the_derived_contracts_are_no_longer_empty(config, engineering):
    """The whole defect, stated as its negation."""
    order = engineering.work_order
    assert order.employee_contract(config, DEVELOPER)["may_read"] != []
    assert order.reviewer_contract(config, REVIEWER)["may_read"] != []


def test_the_authority_snapshot_records_the_read_scope(config, engineering):
    """`may_read: []` on a live snapshot was the observable symptom."""
    order = engineering.work_order
    projection = authority_projection(
        order.employee_contract(config, DEVELOPER), employee=DEVELOPER
    )
    assert projection["may_read"] == tuple(sorted(order.authorized_read_paths))


# --- 2. what the read ceiling is made of ------------------------------------


def test_the_capsules_declared_read_scope_reaches_the_ceiling(seeds, engineering):
    """Retrieval, not invention: the company already wrote down what it reads."""
    order = engineering.work_order
    capsule = seeds.get("company-engineering-execution")
    for declared in capsule.may_read:
        rule = _strip_glob(declared)
        assert any(
            granted == rule or _read_covers(granted, rule)
            for granted in order.authorized_read_paths
        ), f"{declared} is declared by the capsule and absent from the ceiling"


def test_a_developer_can_read_every_path_it_may_write(engineering):
    """Otherwise the grant is incoherent: change a file you may not open."""
    order = engineering.work_order
    for writable in order.authorized_paths:
        assert any(
            _read_covers(rule, writable) for rule in order.authorized_read_paths
        ), f"{writable} is writable and not readable"


def test_the_required_tests_are_readable(engineering):
    order = engineering.work_order
    for test_path in order.required_tests:
        assert any(_read_covers(rule, test_path) for rule in order.authorized_read_paths)


def test_the_ceiling_stays_inside_the_thirty_two_a_work_order_may_name(
    config, seeds
):
    """Three capsules times twelve declared reads overruns the cap on its own.

    `collapse_read_rules` is what keeps it under: it drops a rule another rule
    already covers, which changes the count and not the coverage.
    """
    widest = derive(
        config, seeds,
        "Update the runtime research operations and workforce employment records "
        "that change because the capsule declares a further semantic test.",
    )
    if widest.outcome is IntakeOutcome.AUTHORIZED:
        assert len(widest.work_order.authorized_read_paths) <= 32


def test_collapsing_never_removes_a_readable_path():
    rules = ["company", "company/runtime", "company/*.yaml", "ai_platform", "docs/evidence"]
    collapsed = collapse_read_rules(rules)
    assert collapsed == ("ai_platform", "company", "docs/evidence")
    for rule in rules:
        assert any(_read_covers(kept, rule) or kept == rule for kept in collapsed)


def test_a_capsule_pointer_is_not_treated_as_a_path(engineering):
    """`capsule:company-engineering-execution` names a record, not a file."""
    order = engineering.work_order
    assert any(ref.ref.startswith("capsule:") for ref in order.context_refs)
    assert not any(rule.startswith("capsule:") for rule in order.authorized_read_paths)


def test_a_ceo_ceiling_narrows_writing_without_blinding_the_developer(config, seeds):
    """The ceiling is there to narrow what may be *changed*.

    A work order ceilinged to one file inside a subsystem still has to let its
    developer read the subsystem, or the work cannot be done. So the read grant
    follows the capsule's `owns_paths`, before the ceiling, while the writable
    set follows `authorized_paths`, after it.
    """
    assessment = derive(
        config, seeds, ENGINEERING_OBJECTIVE,
        capsule_hints=("company-engineering-execution",),
        scope_ceiling=("tests/test_company_read_authority.py",),
    )
    order = assessment.work_order
    assert order.authorized_paths == ("tests/test_company_read_authority.py",)
    assert "company/engineering" in order.authorized_read_paths
    assert any(
        _read_covers(rule, "company/engineering/intake.py")
        for rule in order.authorized_read_paths
    )


def test_no_representative_work_order_is_starved_of_its_own_subsystem(config, seeds):
    """Replayed against every capsule that owns a module, not just the easy ones.

    The store is split on whether owning implies reading - eleven capsules
    restate their owned paths inside `may_read` and ten do not - so a ceiling
    built from `may_read` alone starves exactly the ten whose authors thought
    it went without saying.
    """
    starved = []
    for capsule in seeds.all():
        if not capsule.owns_paths or not capsule.tests:
            continue
        try:
            assessment = derive(
                config, seeds,
                "Correct the bounded defect the acceptance criteria name in "
                "this subsystem.",
                capsule_hints=(capsule.id,),
            )
        except EngineeringError:
            # A capsule owning a tree that contains a protected file cannot be
            # given a work order at all, which is a pre-existing refusal and
            # not a read-authority question.
            continue
        if assessment.outcome is not IntakeOutcome.AUTHORIZED:
            continue
        order = assessment.work_order
        for owned in capsule.owns_paths:
            path = _strip_glob(owned)
            if not any(
                _read_covers(rule, path) for rule in order.authorized_read_paths
            ):
                starved.append((capsule.id, path))
    assert starved == []


# --- 3. developer and reviewer ----------------------------------------------


def test_both_roles_receive_the_same_read_scope(config, engineering):
    """Read is a property of the task; write is a property of the role."""
    order = engineering.work_order
    developer = order.employee_contract(config, DEVELOPER)
    reviewer = order.reviewer_contract(config, REVIEWER)
    assert developer["may_read"] == reviewer["may_read"]
    assert developer["may_not_read"] == reviewer["may_not_read"]


def test_the_reviewer_still_holds_no_writable_path(config, engineering):
    order = engineering.work_order
    reviewer = order.reviewer_contract(config, REVIEWER)
    assert reviewer["may_write"] == []
    for writable in order.authorized_paths:
        assert writable in reviewer["may_not_modify"]


def test_read_authority_did_not_become_write_authority(config, engineering):
    """The grant that matters is the one that did *not* grow.

    Read is strictly the larger of the two here - the capsule declares runtime
    and config paths this work order may inspect and may not touch - and the
    writable set is still exactly `authorized_paths`, rule for rule.
    """
    order = engineering.work_order
    developer = order.employee_contract(config, DEVELOPER)

    assert developer["may_write"] == list(order.authorized_paths)
    read_only = set(developer["may_read"]) - set(developer["may_write"])
    assert read_only, "nothing is readable-but-not-writable, so the test proves nothing"

    for rule in read_only:
        assert not any(
            _read_covers(rule, writable) for writable in developer["may_write"]
        ), f"{rule} is read-only yet covers a writable path"


# --- 4. fail-closed, in every direction -------------------------------------


def test_a_work_order_with_no_declared_read_scope_grants_none(config):
    """The default is refusal, which is what an old stored record decodes to."""
    order = EngineeringWorkOrder(
        work_order_id="wo-read-authority-default",
        objective="Do the bounded thing the criteria name.",
        requested_by="MGI",
        request_id="req-read-authority-default",
        authorized_branch="eng-read-authority-default",
        authorized_paths=("company/engineering",),
        acceptance_criteria=("The bounded thing is done.",),
        authorized_on=DAY,
        max_developer_attempts=1,
    )
    assert order.authorized_read_paths == ()
    contract = order.employee_contract(config, DEVELOPER)
    assert contract["may_read"] == []

    decision = _expansion(
        config, CapsuleIndex.load(SEED_ROOT), order, contract,
        "company/engineering/intake.py",
    )
    assert not decision.approved_refs
    assert "may_read is empty" in decision.rejected_refs[0].reason


def test_a_derived_work_order_can_never_have_an_empty_ceiling(config, seeds):
    """Which is what makes the empty case unambiguously "legacy record".

    `authorized_paths` is refused when empty and is always unioned into the
    ceiling, so every work order intake produces has a non-empty read scope.
    The runner skips its context cross-check when the ceiling is empty, and
    that branch is only reachable for a record stored before the field
    existed - for which there is nothing to cross-check against.
    """
    for objective, hints in (
        (ENGINEERING_OBJECTIVE, ("company-engineering-execution",)),
        (EVIDENCE_OBJECTIVE, ()),
        ("Update the analytics observation records the capsule declares.", ()),
        ("Correct the workforce employment contract the registry emits.", ()),
    ):
        assessment = derive(config, seeds, objective, capsule_hints=hints)
        if assessment.outcome is not IntakeOutcome.AUTHORIZED:
            continue
        order = assessment.work_order
        assert order.authorized_read_paths, order.work_order_id
        assert set(order.authorized_paths) <= {
            path
            for path in order.authorized_paths
            if any(_read_covers(rule, path) for rule in order.authorized_read_paths)
        }


def test_adding_the_fields_did_not_restamp_every_historical_work_order(config):
    """A schema change to an authority record changes its identity. Not this one.

    `fingerprint()` omits an empty read field, so a work order authorized
    before read authority existed still produces the digest it was stored
    with. Without that, every completed job in every archived state directory
    became un-decidable: its stage referenced a digest the work order no
    longer produced, and the immutability check - correctly - refused.

    Absent and empty already mean the same thing, because an empty read scope
    grants nothing, so hashing them the same asserts nothing new.
    """
    order = EngineeringWorkOrder(
        work_order_id="wo-read-authority-legacy",
        objective="Do the bounded thing the criteria name.",
        requested_by="MGI",
        request_id="req-read-authority-legacy",
        authorized_branch="eng-read-authority-legacy",
        authorized_paths=("company/engineering",),
        acceptance_criteria=("The bounded thing is done.",),
        authorized_on=DAY,
        max_developer_attempts=1,
        protected=ProtectedSurface.capture(REPO_ROOT),
    )
    legacy = order.to_dict()
    legacy.pop("authorized_read_paths")
    legacy.pop("forbidden_read_paths")
    assert EngineeringWorkOrder.from_mapping(legacy).fingerprint() == order.fingerprint()

    # And a *granted* read scope is still inside the digest.
    granted = dataclasses.replace(order, authorized_read_paths=("company/engineering",))
    assert granted.fingerprint() != order.fingerprint()


def test_stripping_the_read_fields_forfeits_authority_rather_than_forging_it(
    engineering,
):
    """The one way the omission could be abused, measured instead of argued."""
    order = engineering.work_order
    stripped = order.to_dict()
    stripped["authorized_read_paths"] = []
    stripped["forbidden_read_paths"] = []
    forged = EngineeringWorkOrder.from_mapping(stripped)

    assert forged.fingerprint() != order.fingerprint()
    assert forged.authorized_read_paths == ()
    assert forged.employee_contract(load_company_config(None), DEVELOPER)["may_read"] == []


def test_a_stored_work_order_without_the_field_decodes_to_no_read_scope(
    engineering,
):
    """Backwards compatible in the safe direction only."""
    stored = engineering.work_order.to_dict()
    stored.pop("authorized_read_paths")
    stored.pop("forbidden_read_paths")
    restored = EngineeringWorkOrder.from_mapping(stored)
    assert restored.authorized_read_paths == ()
    assert restored.forbidden_read_paths == ()


def test_unrelated_repository_paths_stay_unreadable(config, engineering, evidence):
    """A checkout is not a grant. Production is outside every ceiling."""
    for assessment in (engineering, evidence):
        order = assessment.work_order
        for outsider in OUTSIDE_THE_CONTROL_PLANE:
            assert not any(
                _read_covers(rule, outsider) for rule in order.authorized_read_paths
            ), f"{outsider} is readable under {order.work_order_id}"


def test_context_expansion_cannot_exceed_the_ceiling(config, seeds, engineering):
    order = engineering.work_order
    contract = order.employee_contract(config, DEVELOPER)

    inside = _expansion(
        config, seeds, order, contract, "company/runtime/authority.py"
    )
    assert inside.approved_refs

    outside = _expansion(config, seeds, order, contract, "sloped/course.py")
    assert not outside.approved_refs
    assert "outside employee may_read" in outside.rejected_refs[0].reason


# --- 5. denials outrank grants ----------------------------------------------


def test_a_denial_beats_the_grant_it_sits_inside(config, seeds):
    assessment = derive(
        config, seeds, ENGINEERING_OBJECTIVE,
        capsule_hints=("company-engineering-execution",),
        forbidden_read_paths=("company/runtime/authority.py",),
    )
    order = assessment.work_order
    assert order.forbidden_read_paths == ("company/runtime/authority.py",)
    assert any(_read_covers(rule, "company/runtime/authority.py")
               for rule in order.authorized_read_paths)

    contract = order.employee_contract(config, DEVELOPER)
    decision = _expansion(
        config, seeds, order, contract, "company/runtime/authority.py"
    )
    assert not decision.approved_refs
    assert "may_not_read" in decision.rejected_refs[0].reason


def test_a_denial_may_not_reach_a_path_the_work_order_requires_written(config, seeds):
    """Refused at construction rather than resolved by whichever guard runs first."""
    with pytest.raises(AuthorityEscalation, match="forbidden_read_paths reach"):
        derive(
            config, seeds, ENGINEERING_OBJECTIVE,
            capsule_hints=("company-engineering-execution",),
            forbidden_read_paths=("company/engineering",),
        )


def test_the_denial_reaches_both_contracts(config, seeds):
    assessment = derive(
        config, seeds, ENGINEERING_OBJECTIVE,
        capsule_hints=("company-engineering-execution",),
        forbidden_read_paths=("company/runtime/authority.py",),
    )
    order = assessment.work_order
    assert order.employee_contract(config, DEVELOPER)["may_not_read"] == [
        "company/runtime/authority.py"
    ]
    assert order.reviewer_contract(config, REVIEWER)["may_not_read"] == [
        "company/runtime/authority.py"
    ]


# --- 6. the ceiling survives every boundary ---------------------------------


def test_the_ceiling_round_trips_through_the_stored_record(engineering):
    order = engineering.work_order
    restored = EngineeringWorkOrder.from_mapping(json.loads(json.dumps(order.to_dict())))
    assert restored.authorized_read_paths == order.authorized_read_paths
    assert restored.forbidden_read_paths == order.forbidden_read_paths
    assert restored.fingerprint() == order.fingerprint()


def test_the_read_ceiling_is_inside_the_fingerprint(engineering):
    """A read grant nobody can tamper with is a read grant worth having."""
    order = engineering.work_order
    widened = dataclasses.replace(
        order, authorized_read_paths=order.authorized_read_paths + ("sloped",)
    )
    assert widened.fingerprint() != order.fingerprint()


def test_a_tampered_read_ceiling_is_refused_by_the_work_order_check(engineering):
    order = engineering.work_order
    widened = dataclasses.replace(
        order, authorized_read_paths=order.authorized_read_paths + ("sloped",)
    )
    with pytest.raises(Exception):
        widened.assert_unchanged(order.fingerprint(), "review")


def test_the_briefing_terms_carry_the_ceiling(config, engineering):
    from company.engineering.transport import _work_order_terms

    terms = _work_order_terms(engineering.work_order)
    assert terms["authorized_read_paths"] == list(
        engineering.work_order.authorized_read_paths
    )
    assert terms["forbidden_read_paths"] == list(
        engineering.work_order.forbidden_read_paths
    )


# --- 7. what did not change --------------------------------------------------


def test_the_evidence_reviewer_reads_the_frozen_benchmark_and_cannot_write_it(
    config, evidence
):
    """The P5-R1 property, now with a read grant behind it instead of a checkout."""
    order = evidence.work_order
    target = f"{FROZEN_BENCHMARK}/RESULT.md"

    assert any(_read_covers(rule, target) for rule in order.authorized_read_paths)

    developer = order.employee_contract(config, DEVELOPER)
    assert "docs/evidence/reviews" in developer["may_write"]
    assert not any(
        target == rule or target.startswith(rule + "/") for rule in developer["may_write"]
    ), "the frozen record became writable"
    reviewer = order.reviewer_contract(config, REVIEWER)
    assert reviewer["may_write"] == []


def test_protected_paths_are_still_protected(config, engineering):
    order = engineering.work_order
    developer = order.employee_contract(config, DEVELOPER)
    for path in order.protected.paths:
        assert path in developer["may_not_modify"]
    assert order.protected.paths


def test_ordinary_engineering_authorization_is_unchanged(engineering):
    """The write ceiling is exactly what it was before read authority existed."""
    order = engineering.work_order
    assert order.authorized_paths == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
        "tests/test_company_read_authority.py",
    )


def test_the_no_subagent_invariant_holds_on_both_contracts(config, engineering):
    order = engineering.work_order
    for contract in (
        order.employee_contract(config, DEVELOPER),
        order.reviewer_contract(config, REVIEWER),
    ):
        assert contract["no_subagents"] is True
        assert collect_no_subagent_violations(contract) == []


def test_every_capsule_read_scope_stays_inside_the_control_plane(seeds):
    """The declarations this change started trusting are worth trusting.

    `company-evidence-review` is the one capsule that reaches `docs/evidence`,
    because reading evidence is the job it exists to do.
    """
    reaching = {}
    for capsule in seeds.all():
        # `_strip_glob`, not a blind replace: `company/*.yaml` names four files
        # and must stay a wildcard, while `company/**` names a tree and becomes
        # `company`. A replace turns the first into `company.yaml`, which is a
        # path that does not exist and quietly matches nothing.
        rules = collapse_read_rules(_strip_glob(rule) for rule in capsule.may_read)
        hits = [
            path for path in OUTSIDE_THE_CONTROL_PLANE
            if any(_read_covers(rule, path) for rule in rules)
        ]
        if hits:
            reaching[capsule.id] = hits
    assert reaching == {}
