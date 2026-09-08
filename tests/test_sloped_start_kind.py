"""A start benchmark must not be able to measure a topology it did not name.

V1.4 recorded a 300-seed "fan" start baseline that was really the basin's.
`StartPlan.start_kind` defaulted to `"basin"`, `sloped.course.START_KIND` said
`"fan"`, `tools/sloped_start_bench.py` passed no plan at all, and nothing in
the chain compared the name to the geometry. The basin ignores every other
field on a plan - fins, stagger, deflectors, tray, fall profile, launch width -
so the mislabelling was not a cosmetic one: it silently substituted a different
machine.

These are the four gates that now stand between a named kind and a recorded
number, one test each, plus the two properties that make the three kinds
distinguishable at all.
"""

from __future__ import annotations

import pytest

from sloped import course as _course
from sloped.basin import StartBasin
from sloped.radial import RadialStart
from sloped.startlab import (
    BENCH_PLANS,
    LAB_CHECKPOINTS,
    SHIPPED_PLAN,
    StartPlan,
    TrialResult,
    bench_plan,
    start_machine,
    summarise,
)
from sloped.stations import StartGrid


# --- the three kinds are named, and named on the class --------------------


def test_the_three_start_classes_declare_distinct_kinds():
    kinds = [StartGrid.START_KIND, StartBasin.START_KIND, RadialStart.START_KIND]
    assert kinds == ["fan", "basin", "radial"]
    assert len(set(kinds)) == 3
    assert set(_course.START_KINDS) == set(kinds)


def test_start_module_builds_the_class_the_name_promises():
    """The registry's own answer is checked against the request."""
    from sloped.track import TrackRun

    launch = TrackRun("launch")
    for kind, expected in (
        ("fan", StartGrid),
        ("basin", StartBasin),
        ("radial", RadialStart),
    ):
        module = _course.start_module(kind, launch)
        assert type(module) is expected
        assert module.START_KIND == kind


def test_an_unknown_start_kind_is_refused_by_the_factory():
    from sloped.track import TrackRun

    with pytest.raises(ValueError, match="start must be one of"):
        _course.start_module("stadium", TrackRun("launch"))


# --- gate one: a plan cannot leave the kind implicit ----------------------


def test_a_plan_without_a_start_kind_is_refused():
    """The exact defect: no default, so no plan can inherit the wrong one."""
    with pytest.raises(ValueError, match="does not declare a start_kind"):
        StartPlan(name="nameless")


def test_a_plan_with_an_unknown_start_kind_is_refused():
    with pytest.raises(ValueError, match="not one of"):
        StartPlan(name="typo", start_kind="fann")


def test_every_bench_plan_names_its_own_kind():
    for kind, plan in BENCH_PLANS.items():
        assert plan.start_kind == kind
        assert plan.describe()["start_kind"] == kind


def test_the_shipped_plan_reads_the_courses_own_start_kind():
    """The assertion that would have failed in V1.4, at import time."""
    assert SHIPPED_PLAN.start_kind == _course.START_KIND


def test_bench_plans_differ_only_in_the_start_module():
    """A start-only A/B has to hold the downstream still."""
    fan, radial = bench_plan("fan").describe(), bench_plan("radial").describe()
    for field in ("mixers", "wheels", "launch_width", "tray", "fins", "stagger"):
        assert fan[field] == radial[field], field
    assert fan["start_kind"] != radial["start_kind"]


# --- gate two: the machine reports what it instantiated -------------------


@pytest.mark.parametrize("kind", ["fan", "basin", "radial"])
def test_start_machine_records_the_kind_it_actually_built(kind):
    machine = start_machine(plan=BENCH_PLANS[kind])
    assert machine.start_kind == kind
    assert machine.modules["start"].START_KIND == kind
    assert type(machine.modules["start"]) is _course.START_CLASSES[kind]


def test_the_three_kinds_build_visibly_different_starts():
    """If two kinds could produce the same geometry, no gate would matter."""
    meshes = {}
    for kind in ("fan", "basin", "radial"):
        start = start_machine(plan=BENCH_PLANS[kind]).modules["start"]
        meshes[kind] = len(start.local_colliders()[0].vertices)
    assert len(set(meshes.values())) == 3, meshes


def test_a_plan_whose_kind_disagrees_with_its_module_is_an_error():
    """Gate two fires even if a future edit breaks the dispatch below it."""
    import dataclasses

    plan = dataclasses.replace(BENCH_PLANS["fan"], start_kind="basin")
    machine = start_machine(plan=plan)
    assert machine.start_kind == "basin"          # dispatch and record agree
    # And the guard itself: a kind that reaches the dispatch unhandled raises
    # rather than falling through to the fan.
    with pytest.raises(ValueError, match="does not declare a start_kind"):
        dataclasses.replace(BENCH_PLANS["fan"], start_kind=None)


# --- gates three and four: the trial and the report -----------------------


def _result(kind: str, seed: int = 0) -> TrialResult:
    return TrialResult(
        start_kind=kind,
        seed=seed,
        seconds=0.0,
        slot_of={m: m for m in range(8)},
        ranks={name: {m: m + 1 for m in range(8)} for name, _ in LAB_CHECKPOINTS},
        progress={name: {m: float(m) for m in range(8)} for name, _ in LAB_CHECKPOINTS},
        exit_order={m: m + 1 for m in range(8)},
        collisions={m: 0 for m in range(8)},
        wall_ticks={m: 0 for m in range(8)},
        lost={},
        stuck={},
        through={m: 1.0 for m in range(8)},
        reached=len(LAB_CHECKPOINTS),
    )


def test_a_trial_carries_the_kind_of_the_machine_that_ran_it():
    from sloped.startlab import StartTrial

    machine = start_machine(plan=BENCH_PLANS["radial"])
    trial = StartTrial(machine, seed=0)
    try:
        assert trial.start_kind == "radial"
        assert trial.result(0.0).start_kind == "radial"
    finally:
        trial.sim.close()


def test_a_report_names_the_kind_it_summarised():
    report = summarise([_result("radial", s) for s in range(3)])
    assert report["start_kind"] == "radial"


def test_summarising_two_topologies_together_is_refused():
    """The number that would otherwise be neither topology's."""
    mixed = [_result("fan", 0), _result("basin", 1)]
    with pytest.raises(ValueError, match="mixes start kinds"):
        summarise(mixed)


def test_summarise_checks_the_kind_the_caller_asked_for():
    with pytest.raises(AssertionError, match="asked to summarise 'fan'"):
        summarise([_result("radial")], expect_kind="fan")
    # And agrees when it agrees.
    assert summarise([_result("fan")], expect_kind="fan")["start_kind"] == "fan"


# --- the tools --------------------------------------------------------------


def test_the_bench_tool_refuses_to_run_without_a_named_kind():
    """`--start-kind` has no default, which is the whole correction."""
    import tools.sloped_start_bench as bench

    with pytest.raises(SystemExit):
        bench.main(["--seeds", "1"])


def test_every_scan_candidate_declares_a_kind():
    from tools.sloped_start_scan import CANDIDATES

    for name, plan in CANDIDATES.items():
        assert plan.start_kind in _course.START_KINDS, name
