"""Is the pocket leg2's alone, and what would a global limit cost?

Two measurements behind `sloped.course.BANK_SLEWS`: that the roll-unwind pocket
is specific to leg2 rather than a property of the course, and that a limit
applied to every run would not be safe.
"""
import math, os, sys
sys.path.insert(0, os.getcwd())
from sloped.track import TrackRun, _slewed_bank
from sloped import layout, course

FRACTIONS = (0.0, 0.4, 0.55, 0.6, 0.7, 0.8, 0.95)
RUNS = course.CHAIN + ("final",)

print("=" * 78)
print("deepest climb along each AUTHORED run, by lateral fraction of half width")
print("=" * 78)
print(f"{'run':<8}" + "".join(f"{f:>9.2f}" for f in FRACTIONS) + "   worst at sample")
for name in RUNS:
    run = TrackRun(name)
    row, worst, at, atf = [], 0.0, None, None
    for fraction in FRACTIONS:
        low, deep, where = None, 0.0, None
        for index in range(len(run.sim_path)):
            height = run.surface_point(index, fraction * layout.CHANNEL_HALF * run.scale)[1]
            low = height if low is None else min(low, height)
            if height - low > deep:
                deep, where = height - low, index
        row.append(deep)
        if deep > worst:
            worst, at, atf = deep, where, fraction
    print(f"{name:<8}" + "".join(f"{v:>9.4f}" for v in row) + f"   {worst:.4f} @ {at} (frac {atf})")
print()
print("leg2 is the defect. leg1's 0.0309 is at the rail and only 0.0041 where the")
print("traced racers rode, which asks 0.34 units/s to leave - not a trap. And")
print("leg1's own worst point is sample 110, not the leg1[80..99] the brief names,")
print("so that hotspot is a different mechanism.")
print()
print("=" * 78)
print("what a GLOBAL limit would cost, margin 1.0, correct units")
print("=" * 78)
print(f"{'run':<8}{'changed':>9}{'worst d(deg)':>14}{'bank_max before':>17}{'after':>10}")
for name in RUNS:
    run = TrackRun(name)
    out = _slewed_bank(
        run.banks, run.path, 0, len(run.banks), 1.0, layout.CHANNEL_HALF * run.scale
    )
    changed = sum(1 for a, b in zip(out, run.banks) if abs(a - b) > 1e-9)
    worst = max((abs(math.degrees(a - b)) for a, b in zip(out, run.banks)), default=0.0)
    print(
        f"{name:<8}{changed:>9}{worst:>14.2f}"
        f"{max(abs(math.degrees(v)) for v in run.banks):>17.4f}"
        f"{max(abs(math.degrees(v)) for v in out):>10.4f}"
    )
print()
print("So it is windowed. leg1 would move 20.78 degrees for a pocket of 0.0309,")
print("because the constraint forbids EITHER edge rising - which also forbids")
print("winding *on* faster than the drop pays for, and leg1 banks to 28 degrees.")
print("The rule is stronger than 'no pocket': it is 'no point on the section ever")
print("rises'. Inside leg2's window the roll is coming off throughout, so the two")
print("coincide there; applied globally they do not.")
print()
print("Every bank extreme is preserved in every case, which is the whole reason")
print("this is available where bank, radius and slope are not.")
