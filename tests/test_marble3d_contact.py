"""The marbles are where the drawn machine says its surfaces are.

Two kinds of test here. The first runs the checker over a real replay and
expects it to find nothing, which is the actual integration claim. The second
kind moves a marble somewhere it should not be and expects the checker to say
so - because a validator that has only ever returned "fine" has not been shown
to be capable of returning anything else, and this one returned "fine" for the
wrong reasons four times while it was being written.
"""

from __future__ import annotations

import copy
import json

import pytest

from marble3d.config import DEFAULT_CONFIG
from marble3d.contact import PENETRATION_BUDGET, check_contact
from marble3d.machines import start_bowl_curve
from marble3d.presentation import presentation_for_machine
from marble3d.simulation import simulate

RADIUS = DEFAULT_CONFIG.marble.radius


@pytest.fixture(scope="module")
def machine():
    return start_bowl_curve()


@pytest.fixture(scope="module")
def contract(machine):
    return presentation_for_machine(machine, RADIUS).to_json()


@pytest.fixture(scope="module")
def replay(machine):
    return json.loads(json.dumps(simulate(seed=1, machine=machine, marble_count=8).to_json()))


def test_the_run_never_leaves_the_drawn_machine(replay, contract):
    """The integration claim, in one assertion.

    Every sampled marble, for the whole run, sits on the surface the authored
    asset was told to build - not on the collider, which is a different mesh,
    but on the analytic surface both sides were handed.
    """
    report = check_contact(replay, contract)
    assert report.samples > 1000, "the check must actually have looked at the run"
    assert report.by_kind() == {}
    assert report.ok()


def test_the_worst_penetration_is_within_the_solver_own_budget(replay, contract):
    """And it must not merely be under the checker's limit by a hair."""
    report = check_contact(replay, contract)
    # The physics core measures about 14% of a diameter against its own
    # collider on this machine. Agreement with the *drawn* surface should be
    # of the same order, not worse.
    assert abs(report.worst_penetration) < PENETRATION_BUDGET * RADIUS
    assert abs(report.worst_penetration) < 0.30 * RADIUS


def test_marbles_are_checked_in_all_three_modules(replay, contract):
    """A check that silently skipped the curve would also report nothing."""
    seen = set()
    for frame in replay["frames"]:
        for record in frame["marbles"]:
            if record.get("s") == "running":
                seen.add(record.get("in"))
    assert {"start", "bowl", "curve"} <= seen


# --- the checker can fail -------------------------------------------------


def _sink_every_marble(replay: dict, drop: float) -> dict:
    moved = copy.deepcopy(replay)
    for frame in moved["frames"]:
        for record in frame["marbles"]:
            record["p"][1] -= drop
    return moved


def test_a_marble_pushed_into_the_dish_is_caught(replay, contract):
    sunk = _sink_every_marble(replay, 1.5)
    report = check_contact(sunk, contract)
    assert not report.ok()
    assert report.by_kind().get("below_surface", 0) > 0


def test_a_marble_lifted_off_the_surface_is_caught(replay, contract):
    """Lifted and stopped: falling is legitimate, hanging is not."""
    floated = copy.deepcopy(replay)
    for frame in floated["frames"]:
        for record in frame["marbles"]:
            record["p"][1] += 2.0
            record["v"] = [0.0, 0.0, 0.0]
    report = check_contact(floated, contract)
    assert report.by_kind().get("floating", 0) > 0


def test_a_marble_flung_outside_the_bowl_is_caught(replay, contract):
    escaped = copy.deepcopy(replay)
    hit = 0
    for frame in escaped["frames"]:
        for record in frame["marbles"]:
            if record.get("in") == "bowl" and record.get("s") == "running":
                record["p"][0] += 40.0
                hit += 1
    assert hit, "the fixture must contain marbles in the bowl"
    report = check_contact(escaped, contract)
    assert report.by_kind().get("outside_dish", 0) > 0


def test_a_marble_pushed_through_the_curve_rail_is_caught(replay, contract):
    """Sideways out of the banked channel, which is the failure the bank exists
    to prevent being reported for a marble that is riding it correctly."""
    derailed = copy.deepcopy(replay)
    hit = 0
    for frame in derailed["frames"]:
        for record in frame["marbles"]:
            if record.get("in") == "curve" and record.get("s") == "running":
                record["p"][0] += 6.0
                record["p"][2] += 6.0
                hit += 1
    assert hit, "the fixture must contain marbles on the curve"
    report = check_contact(derailed, contract)
    assert not report.ok()


def test_a_marble_falling_through_the_drain_is_not_a_fault(replay, contract):
    """The first false positive, kept as a test.

    Every successful drain puts a marble below the shaft bottom and inside the
    drain radius. Reading that column as a floor reported the bowl working as
    the bowl being broken.
    """
    drained = 0
    for frame in replay["frames"]:
        for record in frame["marbles"]:
            x, y, z = record["p"]
            if (x * x + z * z) ** 0.5 <= 1.5 and y < -2.5:
                drained += 1
    assert drained > 0, "seed 1 must actually drain marbles through the shaft"
    assert check_contact(replay, contract).ok()


def test_the_release_drop_is_not_reported_as_floating(replay, contract):
    """The second false positive, kept as a test.

    The chute releases by dropping each marble onto its floor, so at release
    every marble is legitimately clear of a surface and legitimately slow.
    """
    report = check_contact(replay, contract)
    assert report.by_kind().get("floating", 0) == 0


def test_the_drain_lip_is_measured_as_a_fillet(contract):
    """The third and fourth false positives, kept as a test.

    The profile is a dish, then a rolled lip, then a shaft - not one power law.
    A point sitting exactly one radius above the lip's own surface must read as
    touching it, which is only true if the profile is followed and the distance
    is a real distance rather than a vertical offset scaled by a slope.
    """
    from marble3d.contact import _profile_distance

    visual = next(m for m in contract["modules"] if m["id"] == "bowl")["visual"]
    profile = visual["profile"]

    for point_radius, point_height in profile:
        # A point on the profile is at zero distance from it.
        assert abs(_profile_distance(profile, point_radius, point_height)) < 1e-9

    # And a point clearly inside the solid reads negative, clearly outside
    # positive, at the lip where the curvature is tightest.
    lip_radius = float(visual["drain_radius"]) + float(visual["lip_radius"])
    assert _profile_distance(profile, lip_radius, 5.0) > 0.0
    assert _profile_distance(profile, float(visual["outer_radius"]) - 1.0, -5.0) < 0.0
