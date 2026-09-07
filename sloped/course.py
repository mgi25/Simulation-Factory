"""The whole course as one `marble3d.Machine`, with its joins checked.

## Placement is asserted, not derived

`marble3d.machine` exists to make a module's place in the world derived - one
anchor and socket algebra for everything else - and this is the one machine in
the repository that does not use it. The reason is that the position *is* the
contract: `docs/validation/sloped_course/physics_layout.json` says where the
built channel is and the render draws it there, so a run that solved for its
own placement could be perfectly self-consistent and in the wrong place.

The property socket algebra buys - that the joins actually close - is bought
here by checking instead. `check()` measures every seam's position gap,
heading change and bank step, every join's worst turn radius against what the
measured arrival speed can hold, and the fork sample against the heading it is
supposed to sit on. A gap is a finding, not a shrug.

## Flow order

    START -> launch -> leg1(mixer) -> leg2(spinners) -> leg3(fork at 82)
                 |                                          |
                 |                                     +----+----+
                 |                                     |         |
                 |                          leg3 tail  |         | orange_lead
                 |                          blue_lead  |         | orange lobe
                 |                          blue lobe  |         |
                 |                                     +----+----+
                 |                                          |
                 +--------------------> merge catch -> final -> FINISH

`leg3` is one collider and one module for its whole length; the fork is a
wedge standing on it at sample 82, so blue's route is leg3's own tail and
orange's leaves from the middle of it. Which route a marble takes is decided by
which side of a 3.3-diameter channel it is running on when it reaches the
wedge, and by nothing else.
"""

from __future__ import annotations

import math
from typing import Any

from marble3d.config import CoreConfig, DEFAULT_CONFIG
from marble3d.geometry import Transform
from marble3d.machine import Machine
from marble3d.validation import Finding, check_mesh
from marble3d.units import MARBLE_DIAMETER

from sloped import joins, layout
from sloped.pathing import build_path
from sloped.scale import to_sim
from sloped.stations import FinishDeck, ForkRidge, MergeCatch, Mixer, Spinners, StartGrid
from sloped.track import TrackRun

__all__ = [
    "CHAIN",
    "BRANCH_MODULES",
    "OBSTRUCTIONS",
    "sloped_course",
    "check",
    "check_probes",
    "facts",
    "route_of_module",
]

# Modules that stand *in* the channel on purpose. A cradle probe fired where
# one of them is measures the obstruction and reports the floor as missing, so
# a hit owned by one of these answers the probe rather than failing it - which
# is the honest reading: the surface a marble meets there really is the pin.
# Anything else that intercepts a probe is a finding.
OBSTRUCTIONS = ("start", "mixer", "obstacle", "fork", "merge")

# The runs a marble meets in order, before the fork.
CHAIN = ("launch", "leg1", "leg2", "leg3")

# Which modules identify a route. Contact with any of these is the evidence
# `sloped.race` uses, because a bounding box cannot tell the two lobes apart -
# their AABBs overlap over a third of their extent.
BRANCH_MODULES = {
    "blue_lead": "blue",
    "blue": "blue",
    "orange_lead": "orange",
    "orange": "orange",
}


def sloped_course(config: CoreConfig | None = None) -> Machine:
    """Layout B, made physical. Every module placed at its recorded position."""
    config = config or DEFAULT_CONFIG
    machine = Machine("sloped_b")

    runs: dict[str, TrackRun] = {
        name: TrackRun(
            name,
            # leg3's east guard, with a window in it rather than a ramp; see
            # `sloped.joins.FORK_GUARD_WINDOW` for why it is where it is.
            open_side=(
                (1.0, *(joins.FORK_SAMPLE + n for n in joins.FORK_GUARD_WINDOW))
                if name == "leg3"
                else None
            ),
        )
        for name in CHAIN
    }
    runs["final"] = TrackRun("final")
    # Both lobes entered one control in, so a lead can exist at all; see
    # `sloped.joins`.
    blue_spec = dict(layout.run("blue"))
    blue_spec["controls"] = joins.blue_controls()
    runs["blue"] = TrackRun("blue", spec=blue_spec)
    # Orange's lobe entered at its second authored control; see `sloped.joins`.
    orange_spec = dict(layout.run("orange"))
    orange_spec["controls"] = joins.orange_controls()
    runs["orange"] = TrackRun("orange", spec=orange_spec)

    paths = joins.join_paths()
    for name, path in paths.items():
        runs[name] = TrackRun(
            name,
            spec=joins.JOIN_SPECS[name],
            path=path,
            # Sampled at the authored runs' own density, 0.289 layout units,
            # rather than at the Hermite's 48 points. Two things depend on it
            # and both bit: `auto_bank` computes curvature from consecutive
            # samples and eases its first six to level, so a join at twice the
            # density rolls to 30 degrees in one layout unit and throws a
            # marble arriving level off the seam - 15 of 24 stopped at leg3's
            # exit; and the collider's facet size is a physics parameter, the
            # 4%-of-a-radius sagitta the core is calibrated at.
            samples=max(8, int(round(joins.path_span(path) / 0.289))),
            # And orange's lead has its west lip opened out over the same
            # window, for the same reason from the other side.
            open_side=(
                (-1.0, -1, 0, 4, joins.FORK_WINDOW_ORANGE)
                if name == "orange_lead"
                else None
            ),
            # Both leads open at the full hero width, because that is what
            # hands over to them, and close to their lobe's own 0.82 by the
            # time they reach it. The *scale* stays hero rather than being 0.82
            # with the width scaled up: a 0.82 profile is 0.82 as *deep* as
            # well, and a lead is the only thing catching a marble that has been
            # thrown across the fork's combined channel at 43 wu/s - with 1.16
            # of containment instead of 1.40 it does not catch it.
            taper=(1.0, layout.BRANCH_SCALE),
        )

    start = StartGrid("start", runs["launch"])
    # Declaration order is the build order and therefore the body numbering, so
    # it is part of the run; the wedge is declared where it belongs in flow even
    # though it needs the lead that is declared after it.

    machine.add(start, Transform())
    for name in CHAIN:
        machine.add(runs[name], Transform())
    machine.add(Mixer("mixer", runs["leg1"]), Transform())
    machine.add(Spinners("obstacle", runs["leg2"]), Transform())
    machine.add(
        ForkRidge(
            "fork",
            runs["leg3"],
            joins.FORK_SAMPLE,
            runs["orange_lead"],
            joins.FORK_WINDOW_BLUE,
        ),
        Transform(),
    )
    for name in ("blue_lead", "blue", "orange_lead", "orange"):
        machine.add(runs[name], Transform())
    machine.add(MergeCatch("merge", runs["final"], runs["blue"]), Transform())
    machine.add(runs["final"], Transform())
    machine.add(FinishDeck("finish", runs["final"]), Transform())

    machine.runs = runs                      # type: ignore[attr-defined]
    machine.finish_line = runs["final"].socket("exit")   # type: ignore[attr-defined]
    return machine


# --- the seams ------------------------------------------------------------

SEAMS = (
    ("start", "exit", "launch", "entry"),
    ("launch", "exit", "leg1", "entry"),
    ("leg1", "exit", "leg2", "entry"),
    ("leg2", "exit", "leg3", "entry"),
    ("leg3", "exit", "blue_lead", "entry"),
    ("blue_lead", "exit", "blue", "entry"),
    ("orange_lead", "exit", "orange", "entry"),
)

POSITION_BUDGET = 0.5 * MARBLE_DIAMETER
HEADING_BUDGET = 24.0
BANK_BUDGET = 6.0


def check(machine: Machine | None = None, config: CoreConfig | None = None) -> list[Finding]:
    """Every disagreement the assembly can be asked about.

    Seams, turn radii, the fork's position, mesh integrity and the one thing a
    mesh check cannot see: whether a join's *end* tangent is the tangent of the
    run it hands to. A join that closes in position and not in direction is a
    kink, and a kink at these speeds is a marble leaving the channel.
    """
    machine = machine or sloped_course(config)
    config = config or DEFAULT_CONFIG
    runs: dict[str, TrackRun] = machine.runs                # type: ignore[attr-defined]
    findings: list[Finding] = []

    def report(check_name: str, subject: str, detail: str) -> None:
        findings.append(Finding(check=check_name, subject=subject, detail=detail))

    for up_name, up_socket, down_name, down_socket in SEAMS:
        upstream = machine.modules[up_name]
        downstream = machine.modules[down_name]
        try:
            a = upstream.socket(up_socket)
            b = downstream.socket(down_socket)
        except KeyError as error:
            report("seam", f"{up_name}->{down_name}", str(error))
            continue
        gap = math.dist(a.frame.position, b.frame.position)
        if gap > POSITION_BUDGET:
            report(
                "seam-gap",
                f"{up_name}->{down_name}",
                f"{gap:.4f} between the sockets (budget {POSITION_BUDGET:.4f}, "
                f"a marble radius)",
            )
        turn = abs(_wrap(math.degrees(b.heading() - a.heading())))
        if turn > HEADING_BUDGET:
            report(
                "seam-heading",
                f"{up_name}->{down_name}",
                f"{turn:.2f} degrees of kink (budget {HEADING_BUDGET})",
            )
        if up_name in runs and down_name in runs:
            step = abs(
                math.degrees(runs[up_name].banks[-1] - runs[down_name].banks[0])
            )
            if step > BANK_BUDGET:
                report(
                    "seam-bank",
                    f"{up_name}->{down_name}",
                    f"{step:.2f} degrees of roll step (budget {BANK_BUDGET})",
                )

    # Turn radii on the joins, against what the measured arrival speed holds.
    for name, spec in joins.JOIN_SPECS.items():
        run = runs[name]
        speed = float(spec["design_speed"])
        allowed = joins.min_radius_layout(speed, float(spec["bank_max"]))
        worst, at = _worst_radius(run.path)
        if worst < allowed:
            report(
                "turn-radius",
                name,
                f"sample {at} turns at {worst:.3f} layout units against the "
                f"{allowed:.3f} a marble at {speed:.0f} wu/s holds on a "
                f"{spec['bank_max']:.0f}-degree bank",
            )

    # The fork is where leg3 crosses south, and nothing may move it silently.
    leg3 = runs["leg3"]
    crossing = min(range(len(leg3.path)), key=lambda index: abs(leg3.heading_deg(index)))
    if crossing != joins.FORK_SAMPLE:
        report(
            "fork",
            "leg3",
            f"the heading crosses zero at sample {crossing}, not at the "
            f"{joins.FORK_SAMPLE} the fork is placed on",
        )

    for module in machine:
        for mesh in module.local_colliders():
            findings.extend(
                check_mesh(mesh, config.collider, expect_components=None)
            )
    return findings


def _wrap(angle: float) -> float:
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def _worst_radius(path) -> tuple[float, int]:
    """The tightest plan-view turn on a path, in layout units, and where.

    Measured on the built path rather than on the arc that was solved for,
    because a Catmull-Rom or a Hermite through the same poses is not that arc,
    and the difference is exactly where a join goes wrong.
    """
    worst, at = float("inf"), 0
    for index in range(1, len(path) - 1):
        a, b, c = path[index - 1], path[index], path[index + 1]
        v0 = (b[0] - a[0], b[2] - a[2])
        v1 = (c[0] - b[0], c[2] - b[2])
        l0 = math.hypot(*v0)
        l1 = math.hypot(*v1)
        if l0 < 1e-9 or l1 < 1e-9:
            continue
        cross = v0[0] * v1[1] - v0[1] * v1[0]
        turn = math.asin(max(-1.0, min(1.0, cross / (l0 * l1))))
        if abs(turn) < 1e-9:
            continue
        radius = ((l0 + l1) * 0.5) / abs(turn)
        if radius < worst:
            worst, at = radius, index
    return worst, at


def check_probes(machine: Machine, world) -> list[Finding]:
    """Fire every module's probes at the assembled world and report what is off.

    Two classes of hit are answered rather than failed, and both are named
    rather than absorbed into a loose tolerance:

    * an obstruction - a mixer pin, a spinner shaft, the fork's wedge, a gate
      paddle - standing where the probe was aimed at the floor;
    * the first sample of a run whose upstream neighbour is still there, where
      the two runs' entry and exit width flares differ by 5% of a half width
      and the surface steps by up to 0.06 simulation units. That step is in the
      render too, because both runs are drawn with their own flare, so the
      collider is reproducing a seam rather than inventing one.
    """
    from marble3d.validation import probe_world

    findings: list[Finding] = []
    for finding in probe_world(world, machine.probes()):
        detail = finding.detail
        if any(f"on '{name}'" in detail for name in OBSTRUCTIONS):
            continue
        if "[0]" in finding.subject and "cradle" in finding.subject:
            continue
        findings.append(finding)
    return findings


def route_of_module(module_id: str) -> str | None:
    return BRANCH_MODULES.get(module_id)


def facts(machine: Machine | None = None) -> dict[str, Any]:
    """The course, as the numbers a report has to quote."""
    machine = machine or sloped_course()
    runs: dict[str, TrackRun] = machine.runs               # type: ignore[attr-defined]
    shared = runs["leg3"].sim_arc[joins.FORK_SAMPLE]
    blue_route = (
        runs["launch"].sim_arc[-1]
        + runs["leg1"].sim_arc[-1]
        + runs["leg2"].sim_arc[-1]
        + runs["leg3"].sim_arc[-1]
        + runs["blue_lead"].sim_arc[-1]
        + runs["blue"].sim_arc[-1]
        + runs["final"].sim_arc[-1]
    )
    orange_route = (
        runs["launch"].sim_arc[-1]
        + runs["leg1"].sim_arc[-1]
        + runs["leg2"].sim_arc[-1]
        + shared
        + runs["orange_lead"].sim_arc[-1]
        + runs["orange"].sim_arc[-1]
        + runs["final"].sim_arc[-1]
    )
    bounds = machine.bounds()
    triangles = sum(
        mesh.triangle_count for module in machine for mesh in module.local_colliders()
    )
    vertices = sum(
        mesh.vertex_count for module in machine for mesh in module.local_colliders()
    )
    return {
        "modules": len(machine.order),
        "vertices": vertices,
        "triangles": triangles,
        "bounds": [
            [round(v, 3) for v in bounds.lower],
            [round(v, 3) for v in bounds.upper],
        ],
        "runs": {name: run.describe() for name, run in runs.items()},
        "route_length_sim": {
            "blue": round(blue_route, 4),
            "orange": round(orange_route, 4),
            "difference": round(orange_route - blue_route, 4),
            "difference_pct": round(100.0 * (orange_route - blue_route) / blue_route, 3),
        },
        "route_length_layout": {
            "blue": round(blue_route * 0.57, 4),
            "orange": round(orange_route * 0.57, 4),
        },
        "fork": {
            "sample": joins.FORK_SAMPLE,
            "stem_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE), 3),
            "blue_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE + 8), 3),
            "orange_heading_deg": round(runs["orange_lead"].heading_deg(8), 3),
        },
        "join_radius_layout": {
            name: {
                "worst": round(_worst_radius(runs[name].path)[0], 4),
                "allowed": round(
                    joins.min_radius_layout(
                        float(spec["design_speed"]), float(spec["bank_max"])
                    ),
                    4,
                ),
            }
            for name, spec in joins.JOIN_SPECS.items()
        },
    }
