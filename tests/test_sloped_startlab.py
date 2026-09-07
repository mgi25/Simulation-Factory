"""The start lab is an instrument, so what is checked is that it measures the
thing that ships.

Two of the three defects this session found were in instruments rather than in
geometry - `sloped.race` could not attribute a marble to the orange route at
all, and `sloped.splitlab` retired a marble the moment it crossed onto orange's
floor - so the lab's own claims get pinned here.
"""

from __future__ import annotations

import pytest

from sloped import layout
from sloped.course import MIXER_SAMPLE, SHUFFLE_SAMPLE, sloped_course
from sloped.startlab import (
    LAB_CHECKPOINTS,
    LAB_RUNS,
    StartPlan,
    start_machine,
    summarise,
)
from sloped.stations import StartGrid


def test_lab_runs_are_the_courses_own_runs_sample_for_sample():
    """The lab's launch and leg1 are the shipped geometry, not copies near it.

    This is the whole warrant for tuning the start in the lab and shipping the
    result: a candidate that wins here has to be the same change the course
    gets.
    """
    lab = start_machine()
    course = sloped_course(routes="both")
    for name in LAB_RUNS:
        lab_run = lab.runs[name]
        course_run = course.runs[name]
        assert len(lab_run.sim_path) == len(course_run.sim_path)
        for index, (a, b) in enumerate(zip(lab_run.sim_path, course_run.sim_path)):
            assert a == pytest.approx(b, abs=1e-9), f"{name}[{index}]"
        assert lab_run.banks == pytest.approx(course_run.banks, abs=1e-12)
        assert lab_run.widths == pytest.approx(course_run.widths, abs=1e-12)


def test_lab_carries_the_shipped_start_correction():
    """The default plan is what `sloped.course` builds, in both pieces."""
    lab = start_machine()
    assert lab.modules["mixer"].run.id == "launch"
    assert lab.modules["mixer"].index == MIXER_SAMPLE
    shuffle = lab.modules["wheel0"]
    assert shuffle.run.id == "launch"
    assert shuffle.index == SHUFFLE_SAMPLE
    assert len(shuffle._stations()) == 1


def test_start_machine_matches_the_course_module_for_module():
    from sloped.startlab import SHIPPED_PLAN

    lab = start_machine(plan=SHIPPED_PLAN)
    course = sloped_course(routes="both")
    assert lab.modules["mixer"].describe()["pins"] == course.modules["mixer"].describe()["pins"]
    assert (
        lab.modules["wheel0"].describe()["wheels"]
        == course.modules["shuffle"].describe()["wheels"]
    )


# --- the plan's own knobs -------------------------------------------------


def test_a_fin_schedule_needs_one_entry_per_divider():
    with pytest.raises(ValueError, match="one per divider"):
        StartGrid("start", fin_schedule=(0.5, 0.5))


def test_a_bay_stagger_needs_one_entry_per_bay():
    with pytest.raises(ValueError, match="one per bay"):
        StartGrid("start", bay_stagger=(0.0, 0.1))


def test_the_default_grid_is_unstaggered_and_evenly_finned():
    """V1's grid, so a scan's baseline really is the baseline."""
    grid = StartGrid("start")
    assert grid.bay_stagger == (0.0,) * layout.BAYS
    assert grid.fin_schedule is None
    assert grid.deflectors == ()


def test_a_stagger_moves_the_bays_it_names_and_no_others():
    plain = StartGrid("start").marble_starts()
    offset = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5)
    staggered = StartGrid("start", bay_stagger=offset).marble_starts()
    for index in range(layout.BAYS - 1):
        assert staggered[index].position == pytest.approx(plain[index].position, abs=1e-12)
    moved = staggered[7].position
    assert moved != pytest.approx(plain[7].position, abs=1e-6)


def test_a_stagger_moves_each_bays_gate_with_it():
    """A paddle left behind is a gate standing in front of nothing."""
    offset = (0.0,) * 7 + (0.5,)
    grid = StartGrid("start", bay_stagger=offset)
    assert grid._gate_z_for(7) == pytest.approx(grid._gate_z_for(0) + 0.5)
    starts = grid.marble_starts()
    assert len(starts) == layout.BAYS


# --- the summary ----------------------------------------------------------


def test_summarise_reports_a_span_per_checkpoint_and_a_row_per_slot():
    from sloped.startlab import TrialResult

    results = [
        TrialResult(
            seed=seed,
            seconds=0.0,
            slot_of={marble: marble for marble in range(8)},
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
        for seed in range(3)
    ]
    report = summarise(results)
    assert report["trials"] == 3
    assert report["racers"] == 24
    assert len(report["slots"]) == 8
    for name, _ in LAB_CHECKPOINTS:
        # Slot i always ranks i+1 here, so the span is the full seven places.
        assert report["rank_span"][name]["span"] == pytest.approx(7.0)
        assert report["rank_span"][name]["best_slot"] == 0
        assert report["rank_span"][name]["worst_slot"] == 7
