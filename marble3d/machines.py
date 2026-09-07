"""The machines this core is proved on. One of them, so far, on purpose.

`start_bowl_curve` is the demonstration section 30 of the brief asks for and
nothing more: a chute, a bowl and a banked curve underneath it. Building a
collector, a split or a finale here would be building the machine rather than
the engine, and the stop condition says not to.

The assembly is four lines of socket algebra and it is worth reading as the
argument for the module system:

    bowl   is anchored, because a bowl has to be upright
    start  is placed by its exit landing on the bowl's entry
    curve  is placed by falling out of the bowl's drain

Nothing here contains a world coordinate. Move the bowl and the chute above it
and the curve below it move with it, still joined; deepen the bowl and the
chute's mouth follows the new feed angle; widen the drain and the join refuses
to close until the catch below is widened to match.
"""

from __future__ import annotations

from marble3d.machine import Machine
from marble3d.modules.bowl import BowlModule, BowlSpec
from marble3d.modules.curve import CurveModule, CurveSpec
from marble3d.modules.start import StartModule, StartSpec
from marble3d.units import MARBLE_RADIUS

__all__ = ["start_bowl_curve", "DRAIN_FALL"]

# How far the curve's catch sits below the mouth of the drain shaft.
#
# Set by a clearance the collider probes found and nothing else. The catch's
# back scoop rises as it reaches back under the drain, and the drain shaft's
# bottom rim hangs down to meet it; at 1.5 the two closed to a 0.72 wu gap at
# the radius of the shaft wall, which a 1.0 wu marble does not fit through, and
# `bowl.drain open` and `curve.floor` both reported it. 2.5 leaves a clear
# marble diameter everywhere inside the shaft's footprint.
#
# It is not free: every unit here is 2 g h of speed the catch has to absorb,
# and a marble now arrives at 47 wu/s. That is still 0.20 wu per tick against a
# 0.5 budget, so the trade is affordable, and it is the sort of thing that
# should be a measured number rather than a round one.
DRAIN_FALL = 5.0 * MARBLE_RADIUS


def start_bowl_curve(
    start: StartSpec | None = None,
    bowl: BowlSpec | None = None,
    curve: CurveSpec | None = None,
) -> Machine:
    """START -> BOWL -> CURVE, with every placement derived from a socket."""
    machine = Machine("start_bowl_curve")
    bowl_module = machine.anchor(BowlModule("bowl", bowl))
    start_module = machine.add(StartModule("start", start))
    curve_module = machine.add(CurveModule("curve", curve))

    machine.connect(start_module, "exit", bowl_module, "entry")
    machine.connect(bowl_module, "drain", curve_module, "entry", fall=DRAIN_FALL)
    return machine
