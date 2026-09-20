"""Focused tests for the Company OS knowledge primitives.

Four invariants, and each is a rule from `company/constitution.md` that prose
alone would not hold: a fact is structurally not a hypothesis (rule 16), a
decision keeps everything it recorded through reconsideration and rollback
(rules 10 and 20), knowledge that decays can be found once it has (rule 15 is
worthless without it), and the store round-trips deterministically.
"""

from __future__ import annotations

import datetime as dt

import pytest

from knowledge.company_os import (
    DECAYING_TYPES,
    DEFAULT_RECHECK_DAYS,
    Alternative,
    Decision,
    DecisionLedger,
    DecisionStatus,
    Evidence,
    ExperimentLearning,
    Fact,
    FailureLearning,
    Freshness,
    Hypothesis,
    HypothesisStatus,
    KnowledgeError,
    KnowledgeStore,
    RecordStatus,
    days_until_recheck,
    default_recheck_on,
    flag_for_revalidation,
    is_stale,
    promote,
    stale_records,
)
from knowledge.company_os.ledger import DEFAULT_ROOT

TODAY = dt.date(2026, 9, 16)
EVIDENCE = (Evidence("test", "tests/test_company_os_knowledge.py", "this file"),)


def a_fact(**overrides) -> Fact:
    base = dict(
        id="marble-scale-similarity",
        statement="Simulating at 1.754386x authored size is geometrically similar.",
        evidence=EVIDENCE,
        source="marble-sloped-race-v1",
        created=TODAY,
        freshness=Freshness.SLOW_CHANGING,
    )
    base.update(overrides)
    return Fact(**base)


def a_hypothesis(**overrides) -> Hypothesis:
    base = dict(
        id="rotor-rate-rotates-residual",
        statement="Raising the rotor rate rotates the residual bias rather than removing it.",
        rationale="V1.7 halved the slot bias but never released ~10% of the field.",
        predicted_observation="Bias magnitude is flat across rates while its phase shifts.",
        test_plan="Sweep rate over five values, 600 seeds each, measure bias phase and magnitude.",
        source="marble-sloped-race-v1",
        created=TODAY,
    )
    base.update(overrides)
    return Hypothesis(**base)


def a_decision(**overrides) -> Decision:
    base = dict(
        id="freeze-the-start",
        decision="Install the frozen start and stop iterating on passive start geometry.",
        why="Five passive topologies were falsified; the selection moved to the catch, not the release.",
        evidence=EVIDENCE,
        alternatives=(
            Alternative("Sixth passive topology", "The family is exhausted; the mechanism is width x curvature."),
            Alternative("Rotor start", "Halves the bias but jams ~10% of the field at the closing gap."),
        ),
        risks=("A frozen start removes a lever future formats may want.",),
        reconsider_if=("A passive topology demonstrates <2% slot bias over 600 seeds.",),
        rollback="Revert the start module to the fan release; nothing downstream reads the frozen flag.",
        source="marble-sloped-race-v1",
        created=TODAY,
    )
    base.update(overrides)
    return Decision(**base)


# --------------------------------------------------------------------------
# Fact and Hypothesis stay distinct
# --------------------------------------------------------------------------


def test_a_fact_without_evidence_is_refused_and_named_a_hypothesis():
    with pytest.raises(KnowledgeError, match="Hypothesis"):
        a_fact(evidence=())


def test_a_hypothesis_needs_no_evidence_but_must_be_falsifiable():
    assert a_hypothesis().evidence == ()
    with pytest.raises(Exception, match="predicted_observation"):
        a_hypothesis(predicted_observation="")
    with pytest.raises(Exception, match="test_plan"):
        a_hypothesis(test_plan="")


def test_the_two_types_are_siblings_not_a_hierarchy():
    """Neither can stand in for the other, at runtime or in a type check."""
    assert not isinstance(a_fact(), Hypothesis)
    assert not isinstance(a_hypothesis(), Fact)
    assert not issubclass(Fact, Hypothesis) and not issubclass(Hypothesis, Fact)


def test_a_hypothesis_carries_no_freshness_and_a_fact_does():
    assert "freshness" not in Hypothesis.__dataclass_fields__
    assert "freshness" in Fact.__dataclass_fields__
    assert Hypothesis not in DECAYING_TYPES and Fact in DECAYING_TYPES


def test_promotion_is_the_only_crossing_and_it_demands_evidence():
    supported = a_hypothesis(status=HypothesisStatus.SUPPORTED)

    with pytest.raises(KnowledgeError, match="requires evidence"):
        promote(supported, evidence=(), freshness=Freshness.SLOW_CHANGING, created=TODAY, source="x")

    with pytest.raises(KnowledgeError, match="only a supported hypothesis"):
        promote(a_hypothesis(), evidence=EVIDENCE, freshness=Freshness.SLOW_CHANGING, created=TODAY, source="x")

    fact = promote(
        supported,
        evidence=EVIDENCE,
        freshness=Freshness.SLOW_CHANGING,
        created=TODAY,
        source="sweep-2026-09",
    )
    assert isinstance(fact, Fact)
    assert fact.derived_from == supported.id
    assert fact.statement == supported.statement
    assert supported.status is HypothesisStatus.SUPPORTED, "the hypothesis is not consumed"


def test_evidence_must_be_a_pointer_not_a_pasted_measurement():
    with pytest.raises(Exception, match="embedded content"):
        Evidence("measurement", "seed 5432: 0.9958\nseed 5433: 0.9961\n", "the sweep output")


# --------------------------------------------------------------------------
# Freshness: stale time-sensitive knowledge can be detected
# --------------------------------------------------------------------------


def test_recheck_dates_are_derived_at_construction_from_the_class():
    assert a_fact(freshness=Freshness.PERMANENT).recheck_on is None
    for freshness, days in DEFAULT_RECHECK_DAYS.items():
        if days is None:
            continue
        record = a_fact(freshness=freshness)
        assert record.recheck_on == TODAY + dt.timedelta(days=days)


def test_an_explicit_recheck_date_wins():
    explicit = TODAY + dt.timedelta(days=3)
    assert a_fact(recheck_on=explicit).recheck_on == explicit


def test_time_sensitive_knowledge_goes_stale_and_permanent_never_does():
    created = dt.date(2026, 1, 1)
    just_past = created + dt.timedelta(days=DEFAULT_RECHECK_DAYS[Freshness.TIME_SENSITIVE] + 1)

    assert is_stale(Freshness.TIME_SENSITIVE, created, None, just_past) is True
    assert is_stale(Freshness.TIME_SENSITIVE, created, None, created) is False
    assert is_stale(Freshness.PERMANENT, created, None, dt.date(2099, 1, 1)) is False
    assert is_stale(Freshness.SLOW_CHANGING, created, None, just_past) is False


def test_the_due_date_is_inclusive_on_the_day_itself():
    created = dt.date(2026, 1, 1)
    due = default_recheck_on(Freshness.EXPERIMENTAL, created)
    assert is_stale(Freshness.EXPERIMENTAL, created, None, due) is False
    assert is_stale(Freshness.EXPERIMENTAL, created, None, due + dt.timedelta(days=1)) is True
    assert days_until_recheck(Freshness.EXPERIMENTAL, created, None, due) == 0
    assert days_until_recheck(Freshness.PERMANENT, created, None, due) is None


def test_a_sweep_finds_the_stale_records_and_orders_them_by_due_date():
    old = dt.date(2026, 1, 1)
    records = (
        a_fact(id="fresh-fact", created=TODAY, freshness=Freshness.TIME_SENSITIVE),
        a_fact(id="stale-fact", created=old, freshness=Freshness.TIME_SENSITIVE),
        a_fact(id="invariant", created=old, freshness=Freshness.PERMANENT),
        a_hypothesis(id="not-a-claim", created=old),
    )
    stale = stale_records(records, TODAY)
    assert [r.id for r in stale] == ["stale-fact"]


def test_a_time_sensitive_record_can_be_flagged_for_revalidation():
    record = a_fact(freshness=Freshness.TIME_SENSITIVE)
    flagged = flag_for_revalidation(record, "YouTube changed how Shorts are surfaced")
    assert flagged.status is RecordStatus.NEEDS_REVALIDATION
    assert flagged.revalidation_reason.startswith("YouTube")
    assert flagged.statement == record.statement and flagged.evidence == record.evidence
    assert record.status is RecordStatus.ACTIVE, "the original is not mutated"


def test_flagging_an_invariant_is_refused_because_the_class_was_the_error():
    with pytest.raises(KnowledgeError, match="supersede"):
        flag_for_revalidation(a_fact(freshness=Freshness.PERMANENT), "it changed")


def test_a_hypothesis_cannot_be_flagged_for_revalidation():
    with pytest.raises(KnowledgeError, match="no freshness class"):
        flag_for_revalidation(a_hypothesis(), "stale?")


# --------------------------------------------------------------------------
# Decisions keep what they recorded
# --------------------------------------------------------------------------


def test_a_decision_must_record_alternatives_reconsideration_and_rollback():
    with pytest.raises(Exception, match="rollback"):
        a_decision(rollback="")
    with pytest.raises(KnowledgeError, match="alternative"):
        a_decision(alternatives=())
    with pytest.raises(KnowledgeError, match="reconsidered"):
        a_decision(reconsider_if=())
    with pytest.raises(KnowledgeError, match="evidence"):
        a_decision(evidence=())


RETAINED = ("decision", "why", "evidence", "alternatives", "risks", "reconsider_if", "rollback", "created")


def test_reconsideration_retains_every_field_the_decision_recorded(tmp_path):
    ledger = DecisionLedger(KnowledgeStore(tmp_path))
    original = a_decision()
    ledger.record(original)

    updated = ledger.reconsider(original.id, "a passive topology reached 1.8% slot bias")
    assert updated.status is DecisionStatus.UNDER_RECONSIDERATION
    assert updated.reconsideration_reason.startswith("a passive topology")
    for field in RETAINED:
        assert getattr(updated, field) == getattr(original, field), field

    assert ledger.get(original.id) == updated, "the change was persisted"
    assert ledger.active() == ()


def test_rollback_retains_the_plan_it_executed(tmp_path):
    ledger = DecisionLedger(KnowledgeStore(tmp_path))
    original = a_decision()
    ledger.record(original)

    rolled = ledger.roll_back(original.id, "the frozen start regressed blue to 91%")
    assert rolled.status is DecisionStatus.ROLLED_BACK
    assert rolled.rollback == original.rollback, "the plan survives its own execution"
    assert rolled.rollback_reason.startswith("the frozen start")
    for field in RETAINED:
        assert getattr(rolled, field) == getattr(original, field), field


def test_superseding_leaves_a_forward_pointer_and_keeps_the_original(tmp_path):
    ledger = DecisionLedger(KnowledgeStore(tmp_path))
    original = a_decision()
    ledger.record(original)
    successor = a_decision(id="freeze-the-start-v2", decision="Frozen start, wider apron.")

    superseded, new = ledger.supersede(original.id, successor)
    assert superseded.status is DecisionStatus.SUPERSEDED
    assert superseded.superseded_by == successor.id
    assert superseded.why == original.why
    assert ledger.active() == (new,)
    with pytest.raises(KnowledgeError, match="cannot supersede itself"):
        ledger.supersede(original.id, original)


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------


def test_records_round_trip_through_the_store(tmp_path):
    store = KnowledgeStore(tmp_path)
    records = (
        a_fact(),
        a_hypothesis(),
        a_decision(),
        ExperimentLearning(
            id="fork-pan-escape",
            experiment_id="v1.14",
            question="Does panning the fork guard cut the escape rate?",
            variables_changed=("fork guard pan angle",),
            variables_locked=("start geometry", "seed 5432", "merge apron"),
            observation="Escape fell from 0.479 to 0.005 over 400 seeds.",
            learning="The ridge was acting as a conveyor to the gorge; panning removes the feed.",
            evidence=EVIDENCE,
            source="marble-sloped-race-v1",
            created=TODAY,
            freshness=Freshness.EXPERIMENTAL,
        ),
        FailureLearning(
            id="instrument-bugs-hide-geometry",
            what_failed="A confident conclusion that the physics could not deliver a fair start.",
            symptom="Measured bias stayed flat across five topologies.",
            root_cause="The measuring code resolved a window edge backwards.",
            detection="Caught by re-deriving one seed by hand against the replay.",
            prevention="Check the instrument before believing a 'the physics cannot do this'.",
            evidence=EVIDENCE,
            source="marble-sloped-race-v1",
            created=TODAY,
            recurrence_guard="tests/test_sloped_retention.py",
        ),
    )
    for record in records:
        store.add(record)
    loaded = store.load_all()
    assert len(loaded) == len(records)
    for original in records:
        assert store.get(original.kind, original.id) == original


def test_writes_are_byte_stable(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    path_a = KnowledgeStore(first).add(a_fact())
    path_b = KnowledgeStore(second).add(a_fact())
    assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")


def test_the_store_refuses_a_silent_overwrite(tmp_path):
    store = KnowledgeStore(tmp_path)
    store.add(a_fact())
    with pytest.raises(KnowledgeError, match="already exists"):
        store.add(a_fact())
    store.add(a_fact(statement="A corrected statement."), overwrite=True)


def test_declared_contradictions_are_surfaced(tmp_path):
    store = KnowledgeStore(tmp_path)
    store.add(a_fact())
    store.add(a_fact(id="scale-is-irrelevant", contradicts=("marble-scale-similarity",)))
    assert store.contradictions() == (("scale-is-irrelevant", "marble-scale-similarity"),)


def test_needing_revalidation_merges_stale_and_flagged(tmp_path):
    store = KnowledgeStore(tmp_path)
    store.add(a_fact(id="expired", created=dt.date(2026, 1, 1), freshness=Freshness.TIME_SENSITIVE))
    store.add(
        flag_for_revalidation(
            a_fact(id="flagged", freshness=Freshness.TIME_SENSITIVE), "provider limits moved"
        )
    )
    store.add(a_fact(id="fine", freshness=Freshness.TIME_SENSITIVE))
    assert sorted(r.id for r in store.needing_revalidation(TODAY)) == ["expired", "flagged"]


def test_an_unknown_record_kind_is_refused(tmp_path):
    store = KnowledgeStore(tmp_path)
    with pytest.raises(KnowledgeError, match="unknown record kind"):
        store.path_for("rumour", "x")
    with pytest.raises(KnowledgeError, match="not a knowledge record"):
        store.add(object())


def test_record_ids_are_filename_safe():
    for bad in ("Has Capitals", "has/slash", "has space", "-leading-dash", ""):
        with pytest.raises(KnowledgeError, match="must be lowercase"):
            a_fact(id=bad)


# --------------------------------------------------------------------------
# The records this branch ships
# --------------------------------------------------------------------------


def test_the_shipped_records_load_and_are_well_formed():
    """The seeded store is the format's own worked example; it must stay valid."""
    store = KnowledgeStore(DEFAULT_ROOT)
    records = store.load_all()
    assert len(records) >= 4
    by_kind = {r.kind for r in records}
    assert {"fact", "decision", "hypothesis"} <= by_kind
    assert stale_records(records, TODAY) == (), "nothing shipped is already stale"
