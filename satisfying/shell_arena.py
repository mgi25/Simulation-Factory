"""MUSICAL SHELL ESCAPE: the nested rotating shells, geometry only.

Category 3 Test #2. Six (by default) concentric shells, inner to outer. Each
shell is a regular polygon whose sides are its **panels**: shell `k` has
`panel_count[k]` slots of equal angular width, and a slot either holds a panel
or is an **opening**. The whole shell rotates rigidly about the origin at a
constant angular velocity, so the openings sweep.

## Why polygons and not rings

A ring with a gap is the obvious shape and it is the wrong one, for a reason
that is dynamical rather than aesthetic. Reflection off a circle has a radial
normal, and a radial normal leaves `L = p x v` exactly conserved: every bounce
then has the same incidence angle, the contact angles advance by a fixed
increment, and the ball traces a rosette that never changes character for the
whole run. That is the "long repetitive orbit" the brief asks us to detect,
except it would be the *only* orbit rather than a rare pathology.

A flat panel's normal is not radial, so a polygon billiard has no such
conserved quantity, and a polygon that *rotates* has time-dependent normals on
top of that. The dynamics are non-integrable and the ball's radial excursion
changes from bounce to bounce, which is what makes "can it escape" a question.
It also happens to be the look the brief asked for - mechanical and segmented
rather than thin concentric rings.

## What a panel is, exactly

Slot `j` of shell `k` spans local angles `j*d` to `(j+1)*d`, `d = 2*pi/N_k`,
and its two endpoints sit on the **vertex circle** of radius `R_k`. The panel
is the straight chord between them, given a half-thickness `thickness/2`, so
the collision surface is a **capsule**: a segment with round caps. That single
shape carries both the flat face a ball bounces off and the end post a ball
clips when it aims at an opening and misses - and the end post is what makes a
near miss a physical event rather than a label.

Three radii matter and they are all different:

- `radius` (`R_k`) - the vertices, the outermost material.
- `apothem` (`a_k = R_k cos(pi/N_k)`) - the chord midpoints. This is the
  shell's **mid-surface**, and crossing it is the definition of moving from one
  shell region to the next. It is a circle, so the crossing time is an exact
  quadratic root and does not depend on the shell's rotation.
- `contact_band` - the band of ball-centre radii in which contact with this
  shell is possible at all, from `a_k - rho` to `R_k + rho` for
  `rho = ball_radius + thickness/2`. Outside that band no panel of this shell
  can be touched, whatever the rotation, which is what lets the solver bracket
  a collision exactly before doing any work.

## Identity

`shell_id` is the index, inner to outer, and shell order is that index - there
is no other ordering anywhere. `panel_id` is the slot index within the shell;
the pair `(shell_id, panel_id)` is unique and stable for the whole run,
including after the panel breaks. An `opening_id` names a *run of consecutive
open slots*, so a two-slot opening is one opening rather than two, and it keeps
its identity as the shell rotates because it is defined in the shell's own
frame.

Openings that exist at `t=0` and panels that break during the run are both
passable to the solver, and they are deliberately different things in the event
stream: `method="opening"` and `method="break"`. The balance between those two
numbers is one of the questions Phase 1 exists to answer.

## What is not here

No ball, no collisions, no damage, no time stepping. This module is geometry
and identity; `satisfying.shell_escape` is the simulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

__all__ = [
    "Opening",
    "Shell",
    "ShellArena",
    "build_arena",
]

TAU = 2.0 * math.pi


@dataclass(frozen=True)
class Opening:
    """A run of consecutive open slots, named once and for the whole run."""

    opening_id: str
    shell_id: int
    first_slot: int
    slot_count: int

    def local_centre(self, slot_width: float) -> float:
        """The opening's centre angle in the shell's own frame."""
        return (self.first_slot + 0.5 * self.slot_count) * slot_width

    def local_half_width(self, slot_width: float) -> float:
        return 0.5 * self.slot_count * slot_width


@dataclass(frozen=True)
class Shell:
    """One rotating segmented shell.

    `omega` is signed: positive is counter-clockwise. `open_slots` are the
    slots with no panel at `t=0`; every other slot starts with an intact panel.
    """

    shell_id: int
    radius: float
    panel_count: int
    thickness: float
    theta0: float
    omega: float
    open_slots: tuple[int, ...]
    openings: tuple[Opening, ...]

    @property
    def slot_width(self) -> float:
        return TAU / self.panel_count

    @property
    def apothem(self) -> float:
        return self.radius * math.cos(math.pi / self.panel_count)

    @property
    def chord_length(self) -> float:
        return 2.0 * self.radius * math.sin(math.pi / self.panel_count)

    def angle_at(self, t: float) -> float:
        return self.theta0 + self.omega * t

    def contact_band(self, ball_radius: float) -> tuple[float, float]:
        """Ball-centre radii between which this shell can be touched at all."""
        rho = ball_radius + 0.5 * self.thickness
        return (self.apothem - rho, self.radius + rho)

    def vertex(self, index: int, t: float) -> tuple[float, float]:
        a = self.angle_at(t) + index * self.slot_width
        return (self.radius * math.cos(a), self.radius * math.sin(a))

    def panel_segment(self, slot: int, t: float) -> tuple[tuple[float, float], tuple[float, float]]:
        """The chord for `slot` at time `t`, as its two endpoints."""
        return (self.vertex(slot, t), self.vertex(slot + 1, t))

    def local_angle(self, world_angle: float, t: float) -> float:
        """A world angle expressed in the shell's own frame, in 0 to tau."""
        return (world_angle - self.angle_at(t)) % TAU

    def slot_of_local(self, local_angle: float) -> int:
        return int(local_angle // self.slot_width) % self.panel_count

    def slot_at(self, world_angle: float, t: float) -> int:
        return self.slot_of_local(self.local_angle(world_angle, t))

    def opening_gap_chord(self, opening: Opening) -> float:
        """How wide the hole actually is, between the two flanking posts.

        The posts are the vertices at either end of the run of open slots, so
        the clear width is the chord they subtend, less the two half-thicknesses
        of the flanking panels. A ball passes only if its diameter fits here,
        which is why this is geometry and not a tunable.
        """
        span = opening.slot_count * self.slot_width
        return 2.0 * self.radius * math.sin(0.5 * span) - self.thickness

    def as_dict(self) -> dict[str, Any]:
        return {
            "shell_id": self.shell_id,
            "radius": self.radius,
            "apothem": self.apothem,
            "panel_count": self.panel_count,
            "thickness": self.thickness,
            "theta0": self.theta0,
            "omega": self.omega,
            "slot_width": self.slot_width,
            "chord_length": self.chord_length,
            "open_slots": list(self.open_slots),
            "openings": [
                {
                    "opening_id": o.opening_id,
                    "first_slot": o.first_slot,
                    "slot_count": o.slot_count,
                    "gap_chord": self.opening_gap_chord(o),
                }
                for o in self.openings
            ],
        }


@dataclass(frozen=True)
class ShellArena:
    """The shells, inner to outer, and the questions asked of the whole set."""

    shells: tuple[Shell, ...]
    ball_radius: float

    @property
    def shell_count(self) -> int:
        return len(self.shells)

    @property
    def outer_radius(self) -> float:
        return self.shells[-1].radius

    def region_boundaries(self) -> tuple[float, ...]:
        """The mid-surface radii, inner to outer. Region `m` lies between
        boundary `m-1` and boundary `m`; region `shell_count` is escaped."""
        return tuple(s.apothem for s in self.shells)

    def region_of(self, x: float, y: float) -> int:
        r = math.hypot(x, y)
        m = 0
        for s in self.shells:
            if r < s.apothem:
                return m
            m += 1
        return m

    def fit_report(self) -> list[dict[str, Any]]:
        """Can the ball physically pass each shell's openings? Per shell.

        A config whose innermost opening is narrower than the ball makes escape
        impossible through that route and turns the run into a pure breaking
        exercise without saying so. This reports it as a number instead.
        """
        out: list[dict[str, Any]] = []
        for s in self.shells:
            gaps = [s.opening_gap_chord(o) for o in s.openings]
            narrowest = min(gaps) if gaps else 0.0
            diameter = 2.0 * self.ball_radius
            out.append(
                {
                    "shell_id": s.shell_id,
                    "narrowest_gap": narrowest,
                    "ball_diameter": diameter,
                    "fit_ratio": (narrowest / diameter) if diameter > 0 else math.inf,
                    "fits": narrowest > diameter,
                }
            )
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "ball_radius": self.ball_radius,
            "shell_count": self.shell_count,
            "shells": [s.as_dict() for s in self.shells],
        }


def _opening_runs(shell_id: int, open_slots: Sequence[int], panel_count: int) -> tuple[Opening, ...]:
    """Group open slots into runs of consecutive slots, wrapping at the seam.

    A three-slot hole is one opening, not three, because the ball experiences
    one hole; and a hole that straddles slot 0 is still one hole, because slot
    numbering is bookkeeping and the shell does not have a seam.
    """
    marked = sorted(set(int(s) % panel_count for s in open_slots))
    if not marked:
        return ()
    if len(marked) == panel_count:
        return (Opening(f"s{shell_id}o0", shell_id, 0, panel_count),)
    flags = [False] * panel_count
    for s in marked:
        flags[s] = True
    # Start at a slot whose predecessor is closed, so no run is split in two.
    start = next(i for i in range(panel_count) if flags[i] and not flags[(i - 1) % panel_count])
    runs: list[tuple[int, int]] = []
    i = 0
    while i < panel_count:
        slot = (start + i) % panel_count
        if flags[slot]:
            length = 0
            while flags[(start + i + length) % panel_count]:
                length += 1
            runs.append((slot, length))
            i += length
        else:
            i += 1
    return tuple(
        Opening(f"s{shell_id}o{n}", shell_id, first, count)
        for n, (first, count) in enumerate(runs)
    )


def build_arena(
    *,
    shell_count: int,
    inner_radius: float,
    shell_spacing: float,
    panel_counts: Sequence[int],
    openings_per_shell: Sequence[int],
    opening_slots: Sequence[int],
    thickness: float,
    ball_radius: float,
    theta0: Sequence[float],
    omega: Sequence[float],
) -> ShellArena:
    """Assemble the shells from already-resolved per-shell parameters.

    Everything seeded (`theta0`, `omega`) arrives resolved, so this function is
    a pure function of its arguments and the arena can be rebuilt from the
    published document alone, without re-deriving anything from the seed.
    """
    if shell_count < 1:
        raise ValueError("shell_count must be at least 1")
    for name, seq in (
        ("panel_counts", panel_counts),
        ("openings_per_shell", openings_per_shell),
        ("opening_slots", opening_slots),
        ("theta0", theta0),
        ("omega", omega),
    ):
        if len(seq) != shell_count:
            raise ValueError(f"{name} must have {shell_count} entries, got {len(seq)}")

    shells: list[Shell] = []
    for k in range(shell_count):
        n = int(panel_counts[k])
        if n < 3:
            raise ValueError(f"shell {k}: panel_count must be at least 3")
        holes = int(openings_per_shell[k])
        width = int(opening_slots[k])
        if holes < 0 or width < 1:
            raise ValueError(f"shell {k}: need openings_per_shell >= 0 and opening_slots >= 1")
        if holes * width >= n:
            raise ValueError(f"shell {k}: openings would leave no panels")
        # Openings spaced as evenly as the slot count allows, starting at slot 0.
        # The shell's seeded `theta0` is what actually places them in the world,
        # so this controls the pattern only, never the orientation.
        open_slots: list[int] = []
        for h in range(holes):
            base = (h * n) // holes if holes else 0
            open_slots.extend((base + w) % n for w in range(width))
        shells.append(
            Shell(
                shell_id=k,
                radius=inner_radius + k * shell_spacing,
                panel_count=n,
                thickness=thickness,
                theta0=float(theta0[k]),
                omega=float(omega[k]),
                open_slots=tuple(sorted(set(open_slots))),
                openings=_opening_runs(k, open_slots, n),
            )
        )
    return ShellArena(shells=tuple(shells), ball_radius=ball_radius)
