"""A deliberately stupid collision solver, for checking the clever one.

`satisfying.shell_escape` finds a contact by marching on the signed clearance
with proved-safe steps. That is fast and it is also exactly the kind of code
that can be subtly wrong in a way no amount of reading catches - the first
version of it walked a grazing ball through a panel roughly twice per run, and
the only reason that was ever noticed is that the run carried a
`max_penetration` instrument and it read 0.55 instead of 0.

So this module contains the same question answered a completely different way:
sample the flight at a few thousand evenly spaced times, compute the distance
to every live panel at each one, and report the first sample at which the
clearance has gone negative. It is a hundred times slower and it has no
geometric insight in it at all, which is the point - it shares no reasoning
with the solver it checks, so the two agreeing is evidence rather than a
tautology.

`tests/test_shell_escape.py` runs the two against each other over every contact
search of a set of seeds. The tolerance is the sampling interval, because the
reference can only place a contact to within one sample.

This is test scaffolding. Nothing in the simulation, the evaluator, the
playback document or any later phase imports it.
"""

from __future__ import annotations

import math
from typing import Any

from satisfying.shell_escape import _nearest_live, _segment_distance

__all__ = ["first_contact_by_sampling", "clearance_at"]


def clearance_at(state: Any, x: float, y: float, t: float) -> float:
    """The smallest clearance to any live panel, checked against every panel.

    `_nearest_live` looks at a window of slots and bounds the rest; this looks
    at all of them, so a window that is one slot too narrow shows up here as a
    disagreement rather than as a ball passing through a wall.
    """
    ca, sa = state.base_trig(t)
    best = math.inf
    for slot in range(state.panel_count):
        if not state.live[slot]:
            continue
        ax, ay = state.vertex_with(ca, sa, slot)
        bx, by = state.vertex_with(ca, sa, slot + 1)
        d, _qx, _qy = _segment_distance(x, y, ax, ay, bx, by)
        if d < best:
            best = d
    return best - state.rho


def first_contact_by_sampling(
    state: Any,
    x: float,
    y: float,
    vx: float,
    vy: float,
    t0: float,
    lo: float,
    hi: float,
    samples: int = 4000,
) -> float | None:
    """First sampled time in `[lo, hi]` where the clearance turns negative."""
    if hi <= lo:
        return None
    previous: float | None = None
    for i in range(samples + 1):
        tau = lo + (hi - lo) * i / samples
        d = clearance_at(state, x + vx * tau, y + vy * tau, t0 + tau)
        if previous is not None and previous > 0.0 and d <= 0.0:
            return tau
        previous = d
    return None


def window_disagreement(state: Any, x: float, y: float, t: float) -> float:
    """How far `_nearest_live`'s windowed answer is from the honest one."""
    windowed, slot = _nearest_live(state, x, y, t)[:2]
    if slot < 0:
        return 0.0
    return abs(windowed - clearance_at(state, x, y, t))
