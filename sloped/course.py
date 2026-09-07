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

## Flow order, and which routes are on offer

    START -> launch -> leg1(mixer) -> leg2(spinners) -> leg3
          -> blue_lead -> blue -> merge catch -> final -> FINISH

`routes="both"` adds the fork at leg3 sample 82, `orange_lead` and orange's
lobe. It is not the default, and that is a measurement rather than a
preference.

## Why the second route is off by default

The two branch lobes diverge at 56 degrees from a common point, so a fork
between them has to split a 3.3-diameter channel into two inside 3.4 layout
units while eight marbles arrive at 43 wu/s. Six configurations were built and
measured, over 32 seeds of eight marbles each:

    divider                       guard window   finished   lost at the fork
    straight blade on the tangent  +8 to +22       -         13 of 24
    blade on the bisector          +8 to +22       -          4 dead, rest queued
    ridge, foot <= half width      +8 to +22      68%        40 of 256
    ridge, foot <= 0.55            +7 to +16      57%        73 of 256
    ridge in the cradle gap        +5 to +14      41%        14 of 32
    ridge in the gap, mouth flared  0 to +14       0%        21 of 32
    no fork at all                 shut           85%         0 of 48

Each failure had a different cause and each is recorded where it was fixed -
in `sloped.stations.ForkRidge` and `sloped.joins.FORK_GUARD_WINDOW` - and none
of them was the last one. The pattern across all six is the same trade: a
divider big enough to sort the field is big enough to queue it, a guard open
enough to let a marble cross is open enough to lose one, and a guard shut
enough to hold the field is shut enough that orange is unreachable. With the
route attribution corrected - the first version fixed a marble's route on its
first contact with a branch collider, and the two channels *overlap* at the
fork, so it credited orange with marbles that ran down leg3's tail - **no
configuration ever put a marble on the orange lobe and got it to the finish.**

The through route does work, and it is the majority of the course: 196 layout
units, five clean seams, 85% of marbles finishing, four to six lead changes a
race and final margins from 0.03 to 0.67 seconds.

So the course ships with one route and the second is a documented, measured
blocker rather than a broken feature.
`docs/sloped_race_v1_junction_finding.md` has the geometry and
`docs/sloped_race_v1.md` has these numbers; the fork's own geometry stays in
the tree, behind `routes="both"`, because the next person to look at this
needs the shapes as much as the numbers.
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
from sloped.basin import StartBasin
from sloped.stations import FinishDeck, ForkRidge, MergeCatch, Mixer, Spinners, StartGrid
from sloped.track import TrackRun

__all__ = [
    "CHAIN",
    "BRANCH_MODULES",
    "OBSTRUCTIONS",
    "START_KIND",
    "start_module",
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
OBSTRUCTIONS = ("start", "mixer", "shuffle", "obstacle", "fork", "merge")

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


ROUTE_CHOICES = ("blue", "both")

# The sprint's guard rails, opened on **both** sides over the samples the merge
# apron is built around - `(side, full-before, open-from, open-to, full-after)`,
# with a side of zero meaning both.
#
# `sloped.stations.MergeCatch` runs from 2.30 layout units behind the sprint's
# entry to 1.70 in front of it, and 1.70 layout is 2.98 simulation units, which
# is the sprint's sample 9. So the rails are open from the sprint's first sample
# to its ninth and back to full by its fourteenth, which is 1.4 units clear of
# the apron's front edge.
#
# Why they have to be: a rail standing inside the apron leaves a ledge along its
# own top with the apron's roof over it, and a marble that strays outside the
# channel while crossing the apron comes to rest on that ledge. Measured, an
# orange marble stopped on the east rail at apron-frame across +2.337 with its
# centre 0.43 simulation units above the apron floor beneath it, at 0.52 wu/s.
# V1 lost 319 of its 747 marbles there, every one booked to `blue[100]`.
# Containment over the window is the apron's own outer walls and roof, which
# span the whole of it.
MERGE_GUARD_WINDOW = (0.0, -1, 0, 9, 14)

# --- the start correction -------------------------------------------------
#
# V1 put its one stud row on leg1 at the recorded `mix` node and called it the
# fairness mechanism. `sloped.startlab` measured what it actually does, over
# 400 seeds of the start, the launch and leg1 alone:
#
#   * The eight bays are within three ticks of each other a quarter of the way
#     down the start fan and **76 ticks** apart at the launch seam. The whole
#     slot bias is made in the fan's second half, where the bare converging
#     trough funnels all eight marbles onto one line; the queue that forms
#     there is ordered by how far each bay had to travel sideways to reach it.
#   * The rest of the course preserves that order because it is a 3.3-diameter
#     channel in which everyone runs at the same terminal speed. By the launch
#     exit the field is strung out over eighteen simulation units.
#   * leg1's stud row is *downstream* of that. It can deflect a marble; it can
#     no longer reorder the field, because the field is no longer a field.
#
# Nine candidates were scanned before these two. A longitudinal bay stagger, a
# merge tree in the lane dividers, longer and shorter dividers, and three
# densities of deflector in the fan all made the bias **worse** - up to a span
# of 7.0 places out of a possible 7 - and they fail for one reason: every
# restriction added to a converging funnel is another queue, and a queue leaves
# in arrival order. Their numbers are in `tools/sloped_start_scan.py`.
#
# So the correction is two things on the launch run, where the field is still
# one channel-width long:
#
# **The stud row moves to launch sample 5.** Same nine studs, same 0.07 height.
# At leg1's seam the field arrives at 50 wu/s and a stud levers a marble out of
# the channel; here it arrives at 13 and the same stud deflects it. Losses over
# the start and leg1 fell from 15.95% to 1.19% on that move alone.
#
# **A single four-blade wheel at launch sample 32**, turning at 9.0 rad/s - the
# same `Spinners` class as the course's own obstacle, one wheel instead of
# three, so it is native to the machine rather than bolted on.
#
# It went in as a fairness mechanism at sample 7 and stayed as a reliability
# one, and the correction is worth recording because the lab got it wrong
# first. A wheel is the only mechanism scanned whose output order is not
# monotone in its input order - a marble's wait is its arrival time modulo the
# blade period - and at sample 7, where the field is still a clump, it did take
# the rank span from 3.71 places to 2.33. It also held 13% of the field up
# doing it, and on the real course that was **18.8% stuck**, all at launch[0].
# The lab could not see it, because a marble grinding along behind an
# obstruction has neither left the channel nor stopped dead; `startlab`'s
# `trailing` exists because of this row.
#
# A span bought by jamming a fifth of the field is not fairness. Faster is
# worse, not better - at 12 rad/s the same wheel bats a 13 wu/s marble back up
# the channel and 80% of the field never leaves. On the real course, 16 seeds
# of eight:
#
#     wheel             finish  escape   stuck
#     none               0.906   0.031   0.062
#     sample  7,  6.0    0.802   0.010   0.188
#     sample  7, 12.0    0.177   0.021   0.802
#     sample 24,  9.0    0.922   0.016   0.062
#     sample 32,  9.0    0.969   0.016   0.016
#     sample 40,  9.0    0.930   0.016   0.055
#
# So the wheel belongs downstream, where the field is at 30 wu/s and the blade
# tip at 9.5 is a tap rather than a gate. At sample 32 it beats having no wheel
# at all on every count, and it still takes the span from 3.705 to 3.345.
#
# **That 10% is the honest size of the fairness win.** The bias is diagnosed
# exactly - see above - and no physical geometry scanned in this session
# removes it without wrecking the race. `docs/sloped_race_v11.md` says so.
MIXER_SAMPLE = 5
SHUFFLE_SAMPLE = 32
SHUFFLE_RATE = 9.0

# Which start the course is built with.
#
# **"fan", because the basin was measured and is worse.** `sloped.basin` builds
# the architecture V1.3 was asked for - one wide flat ramp feeding a shallow
# stadium dish with a single spillway - and it works: all eight marbles drain,
# every seed, with no jam. It is still worse than the taper it replaced. Over
# 100 seeds of the real course, blue route:
#
#     start          finish   win ratio   win spread
#     fan             0.985       11.50      21 pts
#     basin           0.968       29.00      28 pts
#     basin + island  0.965       16.00      30 pts
#
# and the basin's win rates by bay come out 1 1 13 12 29 28 14 2 - the same
# centre-heavy V the taper produces, from the same cause. `sloped.basin` has
# the mechanism; the short version is that a single common exit orders the
# field by distance to that exit, and distance to the exit is a function of
# which bay you started in. Room to mill is not a reason to mill.
#
# The basin stays in the tree because it is the only clean test of that claim
# in a second topology, and because it is one line to switch back to.
START_KIND = "fan"


def start_module(kind: str, launch):
    if kind == "basin":
        return StartBasin("start", launch)
    if kind == "fan":
        return StartGrid("start", launch)
    raise ValueError(f"start must be 'basin' or 'fan', not {kind!r}")


def sloped_course(config: CoreConfig | None = None, routes: str = "blue") -> Machine:
    """Layout B, made physical. Every module placed at its recorded position.

    `routes` is `"blue"` - the through route only - or `"both"`, which adds the
    fork, orange's lead and orange's lobe. See the module docstring for the six
    measurements behind that default.
    """
    if routes not in ROUTE_CHOICES:
        raise ValueError(f"routes must be one of {ROUTE_CHOICES}, not {routes!r}")
    config = config or DEFAULT_CONFIG
    machine = Machine("sloped_b" if routes == "blue" else "sloped_b_split")
    forked = routes == "both"

    runs: dict[str, TrackRun] = {
        name: TrackRun(
            name,
            # leg3's east guard, with a window in it rather than a ramp; see
            # `sloped.joins.FORK_GUARD_WINDOW` for why it is where it is.
            open_side=(
                (1.0, *(joins.FORK_SAMPLE + n for n in joins.FORK_GUARD_WINDOW))
                if (name == "leg3" and forked)
                else None
            ),
        )
        for name in CHAIN
    }
    # The sprint's two guard rails are opened where the merge apron is built
    # around them; see `MERGE_GUARD_WINDOW`.
    runs["final"] = TrackRun("final", open_side=MERGE_GUARD_WINDOW)
    # Both lobes entered one control in, so a lead can exist at all; see
    # `sloped.joins`.
    blue_spec = dict(layout.run("blue"))
    blue_spec["controls"] = joins.blue_controls()
    runs["blue"] = TrackRun("blue", spec=blue_spec)
    # Orange's lobe entered at its second authored control; see `sloped.joins`.
    if forked:
        orange_spec = dict(layout.run("orange"))
        orange_spec["controls"] = joins.orange_controls()
        runs["orange"] = TrackRun("orange", spec=orange_spec)

    paths = joins.join_paths()
    if not forked:
        paths.pop("orange_lead", None)
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
            taper=(
                joins.LEAD_MOUTH_FLARE if name == "orange_lead" else 1.0,
                layout.BRANCH_SCALE,
            ),
        )

    start = start_module(START_KIND, runs["launch"])
    # Declaration order is the build order and therefore the body numbering, so
    # it is part of the run; the wedge is declared where it belongs in flow even
    # though it needs the lead that is declared after it.

    machine.add(start, Transform())
    for name in CHAIN:
        machine.add(runs[name], Transform())
    # The two pieces of the start correction, both on the *launch* run rather
    # than on leg1. `sloped.startlab` measured them; `MIXER_SAMPLE` and
    # `SHUFFLE_SAMPLE` carry the argument.
    machine.add(Mixer("mixer", runs["launch"], at=MIXER_SAMPLE), Transform())
    if SHUFFLE_SAMPLE is not None:
        machine.add(
            Spinners(
                "shuffle", runs["launch"], at=SHUFFLE_SAMPLE, offsets=(0.0,), rate=SHUFFLE_RATE
            ),
            Transform(),
        )
    machine.add(Spinners("obstacle", runs["leg2"]), Transform())
    if forked:
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
    branch = ("blue_lead", "blue", "orange_lead", "orange") if forked else ("blue_lead", "blue")
    for name in branch:
        machine.add(runs[name], Transform())
    machine.add(MergeCatch("merge", runs["final"], runs["blue"]), Transform())
    machine.add(runs["final"], Transform())
    machine.add(FinishDeck("finish", runs["final"]), Transform())

    machine.runs = runs                      # type: ignore[attr-defined]
    machine.routes = routes                  # type: ignore[attr-defined]
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


def _seams_for(machine: Machine):
    return tuple(
        seam for seam in SEAMS if seam[0] in machine.modules and seam[2] in machine.modules
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

    for up_name, up_socket, down_name, down_socket in _seams_for(machine):
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
        if name not in runs:
            continue
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
    # Checked whether or not the fork is built, because `FORK_SAMPLE` is also
    # what the guard window and the route attribution are measured from.
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
    * the merge apron's own upstream edge, answered by **blue's** collider.
      The apron there is built to follow blue's channel rather than a chord to
      the sprint - that correction is what closed the `blue[100..119]` stop
      trap - so the two surfaces now agree to about 0.03 and the ray reaches
      whichever is a hair higher. A probe aimed at the apron and answered by
      blue at 0.053 is the two being one surface, which is the thing that was
      wanted; before the correction the apron stood 0.114 clear of blue there
      and the probe hit it cleanly, which is the thing that was wrong.
    """
    from marble3d.validation import probe_world

    findings: list[Finding] = []
    for finding in probe_world(world, machine.probes()):
        detail = finding.detail
        if any(f"on '{name}'" in detail for name in OBSTRUCTIONS):
            continue
        if "[0]" in finding.subject and "cradle" in finding.subject:
            continue
        if finding.subject.startswith("merge.apron[0]") and "on 'blue'" in detail:
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
        (
            runs["launch"].sim_arc[-1]
            + runs["leg1"].sim_arc[-1]
            + runs["leg2"].sim_arc[-1]
            + shared
            + runs["orange_lead"].sim_arc[-1]
            + runs["orange"].sim_arc[-1]
            + runs["final"].sim_arc[-1]
        )
        if "orange" in runs
        else 0.0
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
        "routes": getattr(machine, "routes", "blue"),
        "route_length_sim": {
            "blue": round(blue_route, 4),
            "orange": round(orange_route, 4),
            "difference": round(orange_route - blue_route, 4),
            "difference_pct": (
                round(100.0 * (orange_route - blue_route) / blue_route, 3)
                if orange_route
                else None
            ),
        },
        "route_length_layout": {
            "blue": round(blue_route * 0.57, 4),
            "orange": round(orange_route * 0.57, 4),
        },
        "fork": {
            "built": "fork" in machine.modules,
            "sample": joins.FORK_SAMPLE,
            "stem_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE), 3),
            "blue_heading_deg": round(runs["leg3"].heading_deg(joins.FORK_SAMPLE + 8), 3),
            "orange_heading_deg": (
                round(runs["orange_lead"].heading_deg(8), 3)
                if "orange_lead" in runs
                else None
            ),
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
            if name in runs
        },
    }
