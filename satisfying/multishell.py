"""TWO-TEAM SHELL RACE: two colours, five shells, and one question.

Category 3 Test #2, Phase 4A. **Two** balls start inside five nested rotating
segmented shells, one cyan and one orange, and every time a ball gets through a
shell it has not been through before it becomes two of its own colour. The
video asks one thing and answers it with physics:

    WHO ESCAPES FIRST?

The winner is the colour whose first ball or descendant crosses the outermost
shell. Nothing steers, nothing is weighted, and the answer is not known until
it happens.

## What changed from the one-founder version, and why

The Phase 3B video was mechanically correct and had no story in it. One
founder multiplying into eight is escalation, but escalation with nobody to
beat is a graph, not a race. Two founders turn the same mechanic into a
competition for free: the population is already the scoreboard, so the video
needs no counter, no caption and no editing to say who is ahead.

Three other things had to move with it.

**The arena shrank.** Outer radius 24.4 to 18.5, inner 6.0 to 6.5. The camera
has to open out across the whole radial span, and 24.4/6.0 forced a 3.63x zoom
that left a ball 21 px wide at the final wall. 18.5/6.5 is 2.80x.

**The ball grew,** 0.40 to 0.53. Partly to hold its share of a smaller frame,
and partly because it is a difficulty knob: the outermost opening is 1.38 ball
diameters wide at 0.53 and was 3.79 at 0.40, so the final wall is now hard to
*thread* and not only hard to break.

**The walls got harder,** because two founders roughly double the number of
attempts every shell has to survive. `docs/category3_two_team_shell_race_phase4a.md`
carries the measured ladder.

## The team rule, stated so it can be argued with

**A ball's team is fixed at birth and is its parent's.** A child is the same
colour as the ball it came from, for every generation, with no mechanism
anywhere that could change it. `team_id` is on the ball record and on every
event that names a ball.

**The physics never reads the team.** This is structural rather than
disciplined. `start_states` builds two release states from the seed;
`team_assignment` then decides which of those two *finished* states is called
cyan, and the simulation never consults a team again. So no arrangement of the
colours can change a position, a velocity or a time, and the claim is checkable
two ways:

* `config.team_swap` flips the colour map. `MultishellConfig.physics_digest`
  excludes it by name, `MultishellRun.state_digest` is built from that digest
  and carries no team, and `MultishellRun.team_digest` is over the labels
  alone. A swapped run therefore has the *same* state digest and the *mirrored*
  team digest, and that pair is the whole proof.
* The label map itself is a seeded coin. The two founder slots are physically
  equivalent but not quite interchangeable in the implementation - slot 0 is
  ball 0, and the ball id breaks scheduling ties - so a fixed slot-to-colour
  map would promote any such asymmetry into a standing colour advantage. The
  coin removes it by construction, and the batch reports the per-slot outcome
  as well so the asymmetry is measured rather than laundered.

**Fair starting conditions.** Both founders are released on one circle at one
radius, antipodally, with the same speed, the same radius, the same collision
model and independently drawn headings. One radius is the whole of "equivalent
distance from relevant geometry"; independent headings are what stop the pair
being a mirror image of each other, which on an even-panelled shell would trace
two copies of one trajectory rather than a race.

## Reproduction, unchanged in substance

A ball that crosses a shell outward, for the first time for that ball at that
shell, continues unchanged and a child of the same colour appears beside it.
The child's ledger is pre-charged with every shell inside the one it was born
outside, so it can only reproduce by making *new* outward progress. A ball may
therefore produce at most `shell_count` children in a whole run, and the
population is bounded above by `2 * 2 ** shell_count` = 64 before any
difficulty is applied at all.

That per-ball-per-shell credit is the entire anti-farming rule and it is
enforced by a bitmask, not by a heuristic. Falling back inward through a hole
is still allowed - it is the drama the concept is asking for - but coming back
out through a shell already credited produces nothing. A ball cannot pump.

**Why the child is not spawned at the centre.** A child that appears at the
origin is a respawn, not a birth: it has no relationship to the event that
created it, it re-does the shells its parent already solved, and on screen it
reads as the simulation cheating. The child is born just ahead of the parent, in
the region the parent has just entered, with the parent's speed and the parent's
heading turned by a small fixed angle.

**Why the turn alternates on the global spawn index.** `+spawn_turn` on
even-numbered spawns and `-spawn_turn` on odd ones. This is deterministic,
exactly balanced over any run with an even number of spawns, and reads nothing
at all about where the openings are - so it cannot aim a child at a hole.
Alternating on the parent's own child count was tried instead, on the argument
that it would be balanced per colour as well: it is not balanced at all, because
most balls have one or two children, so "the first child turns +" put 70% of a
population's turns the same way and gave the whole simulation a chirality.
Whether the global rule is *also* balanced between the colours is then an
empirical question, and `tests/test_multiplying_shell.py` answers it over a
population. A seeded random split would be strictly worse than either: it would
put a random number between the physics and the outcome, so "the child got
lucky" would be a thing the seed decided rather than a thing the geometry
decided.

**Why the child cannot be born inside a panel.** The nominal birth point is
`spawn_lead_ball_radii` ball radii ahead of the parent along the child's own
heading. If that point is inside solid material the lead is halved, repeatedly,
and the last rung of the ladder is a lead of zero - the parent's own position,
which is provably clear because the parent is a non-penetrating ball standing
there. The lead actually used and the clearance actually achieved are both
written into the spawn event, so this is a measurement and not a promise.

## Progressive difficulty

Five shells, and the outer ones are harder in ways a viewer can see:

| shell | radius | panels | openings x slots | open fraction | gap / ball | break threshold |
|-------|--------|--------|------------------|---------------|------------|-----------------|
| 0     |  6.5   | 16     | 3 x 2            | 0.375         | 4.41       |  1.8            |
| 1     |  9.5   | 38     | 3 x 2            | 0.158         | 2.67       |  4.0            |
| 2     | 12.5   | 46     | 2 x 2            | 0.087         | 2.93       |  5.6            |
| 3     | 15.5   | 64     | 2 x 2            | 0.063         | 2.58       |  9.5            |
| 4     | 18.5   | 66     | 2 x 1            | 0.030         | 1.38       | 15.0            |

Three dimensions, all physical and all legible: **the holes get rarer**, **the
last hole gets narrower than a ball is comfortable with**, and **the panels get
stronger**. Nothing is hidden in a probability. `difficulty_profile` reports the
whole table including the measured open fraction and the gap-to-ball ratio, and
asserts for itself whether the profile is monotonic.

Rotation adds a restrained, readable timing ramp. `omega_falloff = 0.82` makes
surface speed rise only from 4.29 to 5.18 units/s while directions alternate.

## Damage, and which colour paid for it

The model is **normalised impact energy above a chip floor**:

    f     = v_n / damage_reference_speed
    added = ((f - floor) / (1 - floor)) ** 2   for f > floor, else 0

At `exponent = 2` that is the kinetic energy carried in the contact normal,
scaled so a head-on hit at the reference speed is exactly `1.0` damage. A
grazing hit is not "a little damage", it is *no* damage, which is both what
stone does and what a viewer expects. The shell's own `break_thresholds[k]` then
says how many reference hits that shell is worth: 1.8 for the innermost up to
15.0 for the outermost.

Damage runs through five named states - `healthy`, `damaged`, `critical`,
`fractured`, `broken` - at deterministic fractions of the shell's threshold, and
every transition is its own event.

**Every panel keeps two ledgers: one total and one per colour.** That is what
turns "the panel broke" into a story: `team_cumulative` says how much each
colour paid, `team_contributors` says how many of its balls did, and
`largest_team` says which colour did most of the work. A break whose
`largest_team` is not the colour of the ball that triggered it is one team
walking through a wall the other one softened, and it is common enough to be a
recurring moment rather than a curiosity.

## The speed model

`speed_model = "constant"` is the production setting: the bounce is specular in
the panel's own frame and the resulting speed is renormalised to the config's
`speed`. `speed_model = "bounded"` keeps the same bounce and clamps the speed
into `speed_band` instead of pinning it. `docs/category3_multiplying_shell_phase1.md`
reports the measured comparison.

## Multi-ball scheduling

Every ball carries its own next event - a panel contact, a region crossing or
the horizon - and the globally earliest one is processed. That ordering is what
makes shared shell state correct: a panel that breaks at t = 11.2 must be broken
for every ball that reaches it after 11.2 and intact for every ball that reached
it before, and a per-ball loop run to completion one ball at a time gets that
wrong in both directions.

Cached next events are invalidated for **every** ball whenever a panel breaks.
That is sound because events are processed in non-decreasing time order, so at a
break every other ball's stored state is at or before the break and its cached
event is at or after it; and because removing material can only move a contact
later, never earlier. It is also cheap, because breaks are rare.

`ball_ball_collisions` adds exact equal-mass elastic contact between balls. It
is off by default and stays off: the Phase 1 measurement found repeat contacts,
penetration, fewer breaks and solver instability, and the chaos this video wants
comes from population, walls, rotation and damage instead.

## Determinism

`start_states` derives both release points, both headings, every shell's initial
angle and every shell's rate jitter from the seed through
`satisfying.multishell_seeds`, and nothing else in a run is random - not the
reproduction, not the spawn geometry, not the damage, not the colours.
`MultishellRun.state_digest` is a SHA-256 over the raw IEEE-754 bytes of every
collision, spawn, break and crossing including the ball ids, so two runs that
agree for three hundred events and diverge at the next compare as different
rather than as equal.

## What is borrowed

The contact solver is imported from `satisfying.shell_escape` rather than
copied: `_ShellState`, `_nearest_live`, `_contact_in_interval`, `_band_intervals`,
`_boundary_crossing`, `_is_post_contact` and `_near_miss`. Those are the pieces
whose correctness argument took the whole of the single-ball phase to establish -
the curvature bound, the two-nearest-panel rule for corners, the two-point
verification of a Newton step - and a second copy of them would be a second
thing to keep right. Nothing in `shell_escape` is modified.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from satisfying import multishell_seeds
from satisfying.shell_arena import ShellArena, build_arena
from satisfying.shell_escape import (
    _band_intervals,
    _boundary_crossing,
    _contact_in_interval,
    _is_post_contact,
    _near_miss,
    _nearest_live,
    _ShellState,
    _SolverExhausted,
)

__all__ = [
    "MultishellConfig",
    "DEFAULT_CONFIG",
    "TEAM_NAMES",
    "TEAM_COUNT",
    "EVENT_SCHEMA",
    "EVENT_KINDS",
    "SCHEMA_VERSION",
    "DAMAGE_STATES",
    "Event",
    "Flight",
    "BallRecord",
    "MultishellRun",
    "start_state",
    "start_states",
    "team_assignment",
    "resolve_shells",
    "build_arena_for",
    "difficulty_profile",
    "simulate",
    "validate_events",
    "damage_state_of",
    "impact_damage",
]

TAU = 2.0 * math.pi

# Bumped whenever an event kind, a field name or a field meaning changes. The
# single-ball schema `category3-test2-shell-escape/1.0.0` is a different stream
# with a different meaning for `escape`, and is deliberately not reused.
SCHEMA_VERSION = "category3-test2-two-team-shell-race/3.0.0"

# The two teams, in team-index order. This is a *labelling* table: nothing in
# this module reads it to decide anything physical, and `TEAM_COUNT` is fixed at
# two because a third colour would make "who escapes first" a three-way race
# that a six-second attention span cannot read.
TEAM_NAMES: tuple[str, ...] = ("cyan", "orange")
TEAM_COUNT = len(TEAM_NAMES)

# Ordered worst-last. Index into this tuple is what the digest and the events
# carry; the name is what the visual and audio branches will switch on.
DAMAGE_STATES: tuple[str, ...] = ("healthy", "damaged", "critical", "fractured", "broken")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MultishellConfig:
    """Everything about a run that is not the seed."""

    # --- arena -----------------------------------------------------------
    shell_count: int = 5
    # Phase 4A shrinks the arena from 6.0/4.6 (outer radius 24.4) to 6.5/3.0
    # (outer radius 18.5). The radial span is what the camera has to open out
    # across, and 24.4/6.0 forced a 3.63x zoom that shrank a ball to 21 px by
    # the last shell. 18.5/6.5 is a 2.85x span, which is the single largest
    # contribution to "the frontier stays large".
    inner_radius: float = 6.5
    shell_spacing: float = 3.0
    panel_counts: tuple[int, ...] = (16, 38, 46, 64, 66)
    openings_per_shell: tuple[int, ...] = (3, 3, 2, 2, 2)
    opening_slots: tuple[int, ...] = (2, 2, 2, 2, 1)
    panel_thickness: float = 0.30

    # --- rotation --------------------------------------------------------
    # Shell k turns at `omega_base * (inner_radius / R_k) ** omega_falloff`,
    # with the sign alternating by index and a bounded seeded jitter. Falloff 1
    # A falloff just below one adds a modest outward surface-speed ramp while
    # keeping every opening readable; see the module docstring.
    omega_base: float = 0.66
    omega_falloff: float = 0.82
    omega_jitter: float = 0.22
    alternate_direction: bool = True

    # --- ball ------------------------------------------------------------
    # Raised from 0.40 with the arena shrink. What a viewer reads is the ball as
    # a fraction of the frontier, and holding that fraction roughly constant
    # while the arena shrinks means the ball grows. It is also a difficulty
    # knob: the outermost opening is 1.43 ball diameters wide at 0.53 and was
    # 3.79 at 0.40, so the final wall is hard to *thread* and not only hard to
    # break.
    ball_radius: float = 0.53
    speed: float = 10.0
    restitution: float = 1.0
    panel_momentum_transfer: float = 1.0
    # "constant" pins the speed after every contact; "bounded" clamps it into
    # `speed_band`. "free" is the unbounded model and exists only so the Fermi
    # runaway can be re-measured rather than cited.
    speed_model: str = "constant"
    speed_band: tuple[float, float] = (0.80, 1.25)
    ball_ball_collisions: bool = False

    # --- teams and reproduction ------------------------------------------
    # Exactly two founders, one per team. Not a free parameter: one founder is
    # the Phase 3B video that had no race in it, and three would make the
    # colours a legend rather than a fact.
    founder_count: int = 2
    # Swap which physical founder slot wears which colour. This is the whole of
    # the fairness instrument: it changes a label and provably nothing else, so
    # a swapped run has the same physics digest and the mirrored team digest.
    team_swap: bool = False
    reproduction: bool = True
    # A safety limit, not the mechanic. Two founders over five reproducing
    # layers can reach 2 * 2**5 = 64, so 64 is the ceiling that cannot bind
    # before the mechanic itself does. If runs hit it, the difficulty profile is
    # wrong and capping is hiding it.
    max_population: int = 64
    spawn_lead_ball_radii: float = 2.6
    spawn_lead_steps: int = 7
    spawn_turn: float = 0.16

    # --- damage ----------------------------------------------------------
    damage_reference_speed: float = 10.0
    damage_exponent: float = 2.0
    # Below this fraction of the reference speed a contact chips nothing.
    damage_floor_fraction: float = 0.08
    break_thresholds: tuple[float, ...] = (1.8, 4.0, 5.6, 9.5, 15.0)
    # Fractions of a shell's own threshold at which the named states begin.
    damage_state_fractions: tuple[float, ...] = (0.24, 0.52, 0.78)
    breakable: bool = True

    # --- horizon ---------------------------------------------------------
    horizon: float = 26.0
    max_collisions: int = 120_000

    # --- reporting thresholds (never change a trajectory) -----------------
    near_miss_arc_ball_radii: float = 2.5
    near_miss_seconds: float = 0.15
    graze_fraction: float = 0.06

    # --- solver ----------------------------------------------------------
    skin: float = 1.0e-7
    clearance_tolerance: float = 1.0e-11
    min_dt: float = 1.0e-9
    max_newton_iterations: int = 2000

    def __post_init__(self) -> None:
        for name in ("panel_counts", "openings_per_shell", "opening_slots", "break_thresholds"):
            seq = getattr(self, name)
            if len(seq) != self.shell_count:
                raise ValueError(f"{name} must have {self.shell_count} entries, got {len(seq)}")
        if self.speed_model not in ("constant", "bounded", "free"):
            raise ValueError(f"unknown speed_model {self.speed_model!r}")
        lo, hi = self.speed_band
        if not (0.0 < lo <= 1.0 <= hi):
            raise ValueError(f"speed_band must bracket 1.0, got {self.speed_band!r}")
        if len(self.damage_state_fractions) != len(DAMAGE_STATES) - 2:
            raise ValueError("damage_state_fractions must name the interior state boundaries")
        if list(self.damage_state_fractions) != sorted(self.damage_state_fractions):
            raise ValueError("damage_state_fractions must be increasing")
        if self.max_population < 1:
            raise ValueError("max_population must be at least 1")
        if self.founder_count != TEAM_COUNT:
            raise ValueError(
                f"this is a {TEAM_COUNT}-team race: founder_count must be "
                f"{TEAM_COUNT}, got {self.founder_count}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "shell_count": self.shell_count,
            "inner_radius": self.inner_radius,
            "shell_spacing": self.shell_spacing,
            "panel_counts": list(self.panel_counts),
            "openings_per_shell": list(self.openings_per_shell),
            "opening_slots": list(self.opening_slots),
            "panel_thickness": self.panel_thickness,
            "omega_base": self.omega_base,
            "omega_falloff": self.omega_falloff,
            "omega_jitter": self.omega_jitter,
            "alternate_direction": self.alternate_direction,
            "ball_radius": self.ball_radius,
            "speed": self.speed,
            "restitution": self.restitution,
            "panel_momentum_transfer": self.panel_momentum_transfer,
            "speed_model": self.speed_model,
            "speed_band": list(self.speed_band),
            "ball_ball_collisions": self.ball_ball_collisions,
            "founder_count": self.founder_count,
            "team_swap": self.team_swap,
            "reproduction": self.reproduction,
            "max_population": self.max_population,
            "spawn_lead_ball_radii": self.spawn_lead_ball_radii,
            "spawn_lead_steps": self.spawn_lead_steps,
            "spawn_turn": self.spawn_turn,
            "damage_reference_speed": self.damage_reference_speed,
            "damage_exponent": self.damage_exponent,
            "damage_floor_fraction": self.damage_floor_fraction,
            "break_thresholds": list(self.break_thresholds),
            "damage_state_fractions": list(self.damage_state_fractions),
            "breakable": self.breakable,
            "horizon": self.horizon,
            "max_collisions": self.max_collisions,
            "near_miss_arc_ball_radii": self.near_miss_arc_ball_radii,
            "near_miss_seconds": self.near_miss_seconds,
            "graze_fraction": self.graze_fraction,
            "skin": self.skin,
            "clearance_tolerance": self.clearance_tolerance,
            "min_dt": self.min_dt,
            "max_newton_iterations": self.max_newton_iterations,
        }

    #: Fields that decide a *label* and never a trajectory. They are excluded
    #: from `physics_digest` for a reason that is the whole fairness argument:
    #: if flipping the colour map changed the physics fingerprint, "the swap
    #: changed nothing physical" would be untestable, because the instrument
    #: would move with the thing it is measuring.
    LABEL_ONLY_FIELDS: tuple[str, ...] = ("team_swap",)

    def digest(self) -> str:
        """A stable fingerprint of the config, for the playback document."""
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def physics_digest(self) -> str:
        """The fingerprint of everything that can move a ball.

        `digest` minus the label-only fields. Two configs with the same
        `physics_digest` produce identical trajectories on every seed; whether
        they agree on `digest` says only whether they also agree on which
        colour is which.
        """
        payload = {
            k: v for k, v in self.as_dict().items() if k not in self.LABEL_ONLY_FIELDS
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def replace(self, **changes: Any) -> "MultishellConfig":
        from dataclasses import replace as _replace

        return _replace(self, **changes)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultishellConfig":
        tuples = {
            "panel_counts",
            "openings_per_shell",
            "opening_slots",
            "break_thresholds",
            "damage_state_fractions",
            "speed_band",
        }
        kwargs = {k: (tuple(v) if k in tuples else v) for k, v in data.items()}
        return cls(**kwargs)


DEFAULT_CONFIG = MultishellConfig()


# --------------------------------------------------------------------------
# The difficulty profile
# --------------------------------------------------------------------------


def difficulty_profile(config: MultishellConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """The per-shell difficulty table, and whether it actually increases.

    Difficulty is two numbers a viewer could in principle read off the screen -
    how much of the shell is hole, and how many solid hits the panel is worth -
    plus the gap-to-ball ratio, which is the one that decides whether a route
    exists at all. `monotonic` is computed, not declared: a config whose middle
    shell is easier than the one inside it says so here rather than in a batch
    three hours later.
    """
    rows: list[dict[str, Any]] = []
    for k in range(config.shell_count):
        n = int(config.panel_counts[k])
        holes = int(config.openings_per_shell[k])
        width = int(config.opening_slots[k])
        radius = config.inner_radius + k * config.shell_spacing
        slot_width = TAU / n
        span = width * slot_width
        gap = 2.0 * radius * math.sin(0.5 * span) - config.panel_thickness
        diameter = 2.0 * config.ball_radius
        base = config.omega_base * (config.inner_radius / radius) ** config.omega_falloff
        rows.append(
            {
                "shell_id": k,
                "radius": radius,
                "panel_count": n,
                "openings": holes,
                "opening_slots": width,
                "open_fraction": holes * width / n,
                "gap_chord": gap,
                "gap_over_diameter": gap / diameter if diameter else math.inf,
                "fits": gap > diameter,
                "break_threshold": float(config.break_thresholds[k]),
                "surface_speed": base * radius,
            }
        )
    opens = [r["open_fraction"] for r in rows]
    thresholds = [r["break_threshold"] for r in rows]
    return {
        "shells": rows,
        "open_fraction_monotonic": all(a >= b for a, b in zip(opens, opens[1:])),
        "break_threshold_monotonic": all(a <= b for a, b in zip(thresholds, thresholds[1:])),
        "all_fit": all(r["fits"] for r in rows),
        "monotonic": (
            all(a >= b for a, b in zip(opens, opens[1:]))
            and all(a <= b for a, b in zip(thresholds, thresholds[1:]))
        ),
    }


def damage_state_of(cumulative: float, threshold: float, fractions: Sequence[float]) -> int:
    """Which of `DAMAGE_STATES` a panel's ledger is in. Index, not name."""
    if threshold <= 0.0:
        return len(DAMAGE_STATES) - 1
    ratio = cumulative / threshold
    if ratio >= 1.0:
        return len(DAMAGE_STATES) - 1
    state = 0
    for i, f in enumerate(fractions):
        if ratio >= f:
            state = i + 1
    return state


def impact_damage(impact_speed: float, config: MultishellConfig = DEFAULT_CONFIG) -> float:
    """Damage from the contact-normal kinetic-energy proxy.

    ``impact_speed`` is already the velocity relative to the rotating panel,
    projected onto the contact normal.  Tangential speed therefore contributes
    nothing: a weak glancing contact remains weak even when the ball is moving
    quickly across the face.  Squaring the normal-speed fraction is the
    equal-mass kinetic-energy relationship, after the explicit chip floor.
    """
    reference = config.damage_reference_speed
    if reference <= 0.0:
        return 0.0
    fraction = abs(impact_speed) / reference
    floor = config.damage_floor_fraction
    if fraction <= floor:
        return 0.0
    span = 1.0 - floor
    return ((fraction - floor) / span) ** config.damage_exponent


# --------------------------------------------------------------------------
# The frozen event schema, version 2
# --------------------------------------------------------------------------

# Every event carries `kind` and `t`; these are the *additional* fields, in the
# order they are written. `validate_events` checks a run against this table
# exactly - no missing key, no extra key, no renamed key - so schema drift is a
# test failure rather than a renderer that silently draws nothing.
EVENT_SCHEMA: dict[str, tuple[str, ...]] = {
    "ball_spawn": (
        "ball_id",
        "team_id",
        "parent_id",
        "generation",
        "birth_shell",
        "region",
        "position",
        "velocity",
        "speed",
        "turn",
        "lead",
        "clearance",
        "spawn_index",
        "population",
        "lineage",
    ),
    "collision": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "region",
        "position",
        "contact_point",
        "contact_angle",
        "normal",
        "velocity_in",
        "velocity_out",
        "impact_speed",
        "speed",
        "incidence",
        "feature",
        "grazing",
        "radial_outward",
        "panel_local_offset",
    ),
    "ball_collision": (
        "ball_id",
        "team_id",
        "other_id",
        "other_team_id",
        "position",
        "other_position",
        "normal",
        "velocity_in",
        "velocity_out",
        "other_velocity_in",
        "other_velocity_out",
        "impact_speed",
    ),
    "near_miss": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "opening_id",
        "region",
        "ball_position",
        "ball_angle",
        "opening_centre_angle",
        "opening_half_width",
        "angular_separation",
        "arc_separation",
        "arc_separation_ball_radii",
        "relative_angular_speed",
        "time_separation",
        "signed_lead",
        "criterion",
    ),
    "damage": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "contribution",
        "cumulative",
        "threshold",
        "fraction",
        "state",
        "impact_speed",
        "contributors",
        "team_cumulative",
    ),
    "damage_state": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "previous_state",
        "new_state",
        "cumulative",
        "threshold",
        "fraction",
    ),
    "panel_break": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "position",
        "break_angle",
        "cumulative",
        "threshold",
        "hits",
        "contributors",
        "team_cumulative",
        "team_contributors",
        "largest_team",
    ),
    "shell_exit": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "route",
        "opening_id",
        "from_region",
        "to_region",
        "position",
        "crossing_angle",
        "local_offset",
        "dwell_seconds",
        "first_for_ball",
        "reproduced",
    ),
    "shell_entry": (
        "ball_id",
        "team_id",
        "shell_id",
        "panel_id",
        "route",
        "opening_id",
        "from_region",
        "to_region",
        "position",
        "crossing_angle",
        "local_offset",
        "dwell_seconds",
    ),
    "escape": (
        "ball_id",
        "team_id",
        "team_name",
        "shell_id",
        "route",
        "position",
        "generation",
        "parent_id",
        "birth_time",
        "birth_shell",
        "lineage",
        "collisions",
        "breaks",
        "population",
        "population_by_team",
        "damage_by_team",
        "margin_seconds",
    ),
    "failure": (
        "reason",
        "horizon",
        "active_balls",
        "total_balls",
        "frontier_region",
        "frontier_balls",
        "balls_by_region",
        "collisions",
        "breaks",
        "balls_by_team",
        "frontier_by_team",
        "damage_by_team",
    ),
}

EVENT_KINDS: tuple[str, ...] = tuple(EVENT_SCHEMA)


@dataclass(frozen=True)
class Event:
    """One thing that happened, at one time, with one kind."""

    kind: str
    t: float
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "t": self.t}
        out.update(self.data)
        return out


def validate_events(events: Iterable[Event]) -> None:
    """Raise if any event's fields do not match the frozen schema exactly."""
    for index, ev in enumerate(events):
        expected = EVENT_SCHEMA.get(ev.kind)
        if expected is None:
            raise ValueError(f"event {index}: unknown kind {ev.kind!r}")
        got = tuple(ev.data)
        if got != expected:
            raise ValueError(
                f"event {index} ({ev.kind}): fields {got!r} do not match schema {expected!r}"
            )


def _ordered(data: dict[str, Any], kind: str) -> dict[str, Any]:
    """Re-key a payload into the schema's field order."""
    return {name: data[name] for name in EVENT_SCHEMA[kind]}


@dataclass(frozen=True)
class Flight:
    """One straight-line arc of one ball: where it was and where it was going.

    A ball's trajectory is exactly the concatenation of its flights. A renderer
    asked for ball `b` at time `t` finds `b`'s last flight starting at or before
    `t` and evaluates `p + v * (t - t0)`; before the ball's first flight it does
    not exist yet. That is a closed form, so a renderer's frame rate cannot
    change where anything is.
    """

    t: float
    x: float
    y: float
    vx: float
    vy: float


@dataclass
class BallRecord:
    """The identity and the fate of one ball, kept after the run."""

    ball_id: int
    team_id: int
    parent_id: int | None
    generation: int
    birth_time: float
    birth_shell: int | None
    lineage: tuple[int, ...]
    credited_at_birth: tuple[int, ...]
    credited: tuple[int, ...] = ()
    visited: tuple[int, ...] = ()
    children: tuple[int, ...] = ()
    collisions: int = 0
    max_region: int = 0
    final_region: int = 0
    escaped: bool = False
    death_time: float | None = None
    damage_dealt: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ball_id": self.ball_id,
            "team_id": self.team_id,
            "team_colour": TEAM_NAMES[self.team_id],
            "parent_id": self.parent_id,
            "generation": self.generation,
            "birth_time": self.birth_time,
            "birth_shell": self.birth_shell,
            "lineage": list(self.lineage),
            "credited_at_birth": list(self.credited_at_birth),
            "credited": list(self.credited),
            "visited": list(self.visited),
            "children": list(self.children),
            "collisions": self.collisions,
            "max_region": self.max_region,
            "final_region": self.final_region,
            "escaped": self.escaped,
            "damage_dealt": self.damage_dealt,
        }


# --------------------------------------------------------------------------
# Seeded setup
# --------------------------------------------------------------------------


def resolve_shells(seed: int, config: MultishellConfig) -> tuple[list[float], list[float]]:
    """The per-shell initial angle and signed angular velocity for a seed."""
    phase_rng = multishell_seeds.make_shell_phase_rng(seed)
    rate_rng = multishell_seeds.make_shell_rate_rng(seed)
    theta0: list[float] = []
    omega: list[float] = []
    for k in range(config.shell_count):
        theta0.append(phase_rng.uniform(0.0, TAU))
        radius = config.inner_radius + k * config.shell_spacing
        base = config.omega_base * (config.inner_radius / radius) ** config.omega_falloff
        jitter = rate_rng.uniform(-config.omega_jitter, config.omega_jitter)
        magnitude = base * (1.0 + jitter)
        sign = -1.0 if (config.alternate_direction and k % 2 == 1) else 1.0
        omega.append(sign * magnitude)
    return theta0, omega


def build_arena_for(seed: int, config: MultishellConfig) -> ShellArena:
    theta0, omega = resolve_shells(seed, config)
    return build_arena(
        shell_count=config.shell_count,
        inner_radius=config.inner_radius,
        shell_spacing=config.shell_spacing,
        panel_counts=config.panel_counts,
        openings_per_shell=config.openings_per_shell,
        opening_slots=config.opening_slots,
        thickness=config.panel_thickness,
        ball_radius=config.ball_radius,
        theta0=theta0,
        omega=omega,
    )


def start_states(
    seed: int, config: MultishellConfig, arena: ShellArena
) -> list[tuple[float, float, float, float]]:
    """The two founders' release states, in physical slot order.

    **The fairness argument is in the construction, not in a later check.**

    Both founders are placed on one circle of radius `r` about the arena
    centre, at antipodal angles. One radius means one distance to every shell,
    to every panel band and to the escape radius, so neither slot starts nearer
    anything. Antipodal means the largest separation the release disc allows,
    so the two never begin on top of each other and the early frame reads as
    two competitors rather than one smudge.

    `r` is drawn uniformly by *area* over the annulus between
    `FOUNDER_MIN_RADIUS_FRACTION` and the full release disc, which keeps the
    density flat and keeps the pair apart. The axis angle is uniform over the
    circle, so the unordered pair of positions has a distribution invariant
    under exchanging the two slots.

    The two headings are drawn independently from the heading stream. Giving
    the second founder the first one's heading turned by pi would make the pair
    exactly point-symmetric, and on the shells whose panel count happens to be
    even that is a symmetry of the lattice: the two would trace mirror images
    for as long as the openings agreed, which is a duplicate and not a race.
    Independent headings are unbiased - the pair's distribution is unchanged by
    exchanging the slots - and they diverge immediately.

    Speed, radius, restitution and the collision model are config-wide, so
    there is no per-slot physical parameter anywhere for a bias to live in.
    """
    pos_rng = multishell_seeds.make_position_rng(seed)
    head_rng = multishell_seeds.make_heading_rng(seed)
    limit = multishell_seeds.RELEASE_RADIUS_FRACTION * arena.shells[0].apothem
    floor = multishell_seeds.FOUNDER_MIN_RADIUS_FRACTION
    r = limit * math.sqrt(floor * floor + (1.0 - floor * floor) * pos_rng.random())
    axis = pos_rng.uniform(0.0, TAU)
    out: list[tuple[float, float, float, float]] = []
    for slot in range(config.founder_count):
        angle = axis + slot * TAU / config.founder_count
        heading = head_rng.uniform(0.0, TAU)
        out.append(
            (
                r * math.cos(angle),
                r * math.sin(angle),
                config.speed * math.cos(heading),
                config.speed * math.sin(heading),
            )
        )
    return out


def start_state(
    seed: int, config: MultishellConfig, arena: ShellArena
) -> tuple[float, float, float, float]:
    """The first founder's release state. Kept for callers that want one."""
    return start_states(seed, config, arena)[0]


def team_assignment(seed: int, config: MultishellConfig) -> tuple[int, ...]:
    """Which team each physical founder slot belongs to.

    A permutation of the team indices and nothing else. It is applied *after*
    `start_states` has produced the physical states, so no arrangement of it
    can change a position, a heading, a speed or a distance to a wall - which
    is what makes "no colour-dependent physics" a structural fact rather than a
    thing to test for.

    The permutation is a seeded coin (`multishell_seeds.team_parity`) XORed with
    `config.team_swap`. The coin is there because the two *slots* are not quite
    interchangeable in the implementation even though they are in the physics -
    slot 0 is ball 0, and the ball id breaks scheduling ties - so a fixed
    slot-to-colour map would promote any such asymmetry into a standing colour
    advantage. The batch reports per-slot outcomes as well, so the asymmetry is
    measured rather than laundered.
    """
    parity = multishell_seeds.team_parity(seed) ^ int(bool(config.team_swap))
    return tuple((slot ^ parity) % TEAM_COUNT for slot in range(config.founder_count))


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass
class MultishellRun:
    """One simulated run and everything measured about it while it happened."""

    seed: int
    config: MultishellConfig
    arena: ShellArena
    flights: dict[int, list[Flight]] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    balls: list[BallRecord] = field(default_factory=list)

    escaped: bool = False
    escape_ball: int | None = None
    # The race result. `winner_team` is an index into `TEAM_NAMES`; it is set
    # only by the first legitimate crossing of the escape radius, so a run that
    # times out has no winner rather than a defaulted one.
    winner_team: int | None = None
    winner_generation: int | None = None
    winner_route: str | None = None
    failure_reason: str | None = None
    duration: float = 0.0
    escape_time: float | None = None
    frontier_region: int = 0

    collisions: int = 0
    ball_collisions: int = 0
    near_misses: int = 0
    breaks: int = 0
    grazing_collisions: int = 0
    spawns: int = 0
    spawns_suppressed: int = 0
    max_population: int = 1
    max_generation: int = 0

    # Instruments. These report; they never steer.
    max_penetration: float = 0.0
    min_spawn_clearance: float | None = None
    speed_min: float = math.inf
    speed_max: float = 0.0
    max_speed_correction: float = 0.0
    # The sum of every renormalisation applied, so the *typical* correction is
    # a number too. The per-run maximum on its own says how hard the constraint
    # ever had to work, never how hard it usually does, and those differ by an
    # order of magnitude here.
    speed_correction_total: float = 0.0
    anomalous_crossings: int = 0
    newton_failures: int = 0
    reproduction_violations: int = 0

    damage: list[list[float]] = field(default_factory=list)
    broken: list[list[bool]] = field(default_factory=list)
    hits_by_panel: list[list[int]] = field(default_factory=list)
    contributors_by_panel: list[list[int]] = field(default_factory=list)
    region_dwell: list[float] = field(default_factory=list)
    population_samples: list[tuple[float, int]] = field(default_factory=list)

    # --- the race ---------------------------------------------------------
    # Every one of these is a count of a thing that happened, sampled at the
    # instant it happened. Nothing here is interpolated and nothing is a score.
    team_population_samples: list[tuple[float, tuple[int, ...]]] = field(default_factory=list)
    team_frontier_samples: list[tuple[float, tuple[int, ...]]] = field(default_factory=list)
    team_balls: list[int] = field(default_factory=list)
    team_spawns: list[int] = field(default_factory=list)
    team_collisions: list[int] = field(default_factory=list)
    team_damage: list[float] = field(default_factory=list)
    team_breaks: list[int] = field(default_factory=list)
    team_crossings: list[int] = field(default_factory=list)
    team_frontier: list[int] = field(default_factory=list)
    # A lead change is a sample at which the sign of (team 0 minus team 1)
    # changes to a *different non-zero* sign. Passing through a tie is not two
    # lead changes, and a tie that resolves the way it came is not one at all.
    population_lead_changes: int = 0
    frontier_lead_changes: int = 0
    max_population_lead: int = 0
    # How long the loser had been the last team to make frontier progress when
    # the winner crossed out. Small means the race was still live at the end.
    win_margin_seconds: float | None = None

    @property
    def mean_speed_correction(self) -> float:
        """The average renormalisation per panel contact, as a fraction."""
        return self.speed_correction_total / self.collisions if self.collisions else 0.0

    def events_of(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]

    def team_population_at(self, t: float) -> tuple[int, ...]:
        """How many balls each team had at `t`. Step function, from the samples."""
        counts: tuple[int, ...] = tuple(0 for _ in range(TEAM_COUNT))
        for at, row in self.team_population_samples:
            if at <= t:
                counts = row
            else:
                break
        return counts

    def population_at(self, t: float) -> int:
        """How many balls existed at time `t`. Step function, from the samples."""
        count = 0
        for at, n in self.population_samples:
            if at <= t:
                count = n
            else:
                break
        return count

    def state_digest(self) -> str:
        """SHA-256 over the raw bytes of every state-changing event.

        Collisions, spawns, breaks and region crossings, in order, as doubles,
        with the ball id in every record. Two runs that agree early and diverge
        late are different here, which is the point.
        """
        h = hashlib.sha256()
        h.update(SCHEMA_VERSION.encode("utf-8"))
        # The *physics* digest, not the full one: a run and its label-swapped
        # twin must fingerprint identically here, because they are the same run.
        h.update(self.config.physics_digest().encode("utf-8"))
        h.update(struct.pack("<q", int(self.seed)))
        for ev in self.events:
            d = ev.data
            if ev.kind == "collision":
                h.update(
                    struct.pack(
                        "<c3i9d",
                        b"c",
                        d["ball_id"],
                        d["shell_id"],
                        d["panel_id"],
                        ev.t,
                        d["position"][0],
                        d["position"][1],
                        d["velocity_in"][0],
                        d["velocity_in"][1],
                        d["velocity_out"][0],
                        d["velocity_out"][1],
                        d["contact_angle"],
                        d["impact_speed"],
                    )
                )
            elif ev.kind == "ball_collision":
                h.update(
                    struct.pack(
                        "<c2i4d",
                        b"B",
                        d["ball_id"],
                        d["other_id"],
                        ev.t,
                        d["position"][0],
                        d["position"][1],
                        d["impact_speed"],
                    )
                )
            elif ev.kind == "ball_spawn":
                h.update(
                    struct.pack(
                        "<c3i5d",
                        b"s",
                        d["ball_id"],
                        -1 if d["parent_id"] is None else d["parent_id"],
                        d["birth_shell"],
                        ev.t,
                        d["position"][0],
                        d["position"][1],
                        d["velocity"][0],
                        d["velocity"][1],
                    )
                )
            elif ev.kind == "panel_break":
                h.update(
                    struct.pack(
                        "<c3i2d", b"b", d["ball_id"], d["shell_id"], d["panel_id"], ev.t, d["cumulative"]
                    )
                )
            elif ev.kind in ("shell_exit", "shell_entry"):
                h.update(
                    struct.pack(
                        "<c3i2d",
                        b"x" if ev.kind == "shell_exit" else b"n",
                        d["ball_id"],
                        d["shell_id"],
                        d["to_region"],
                        ev.t,
                        d["crossing_angle"],
                    )
                )
            elif ev.kind == "escape":
                h.update(struct.pack("<cid", b"e", d["ball_id"], ev.t))
            elif ev.kind == "failure":
                h.update(struct.pack("<cid", b"f", d["total_balls"], ev.t))
        return h.hexdigest()

    def team_digest(self) -> str:
        """SHA-256 over the *labelling*: which ball wore which colour, in order.

        Deliberately a second digest rather than fields folded into
        `state_digest`. `state_digest` is over the physics and carries no team,
        so a label swap leaves it identical - which is the proof that the swap
        changed nothing physical. This one is over the labels alone, so a swap
        changes it, and the two together say exactly what a swap did.
        """
        h = hashlib.sha256()
        h.update(b"team-labels")
        for record in self.balls:
            h.update(struct.pack("<2i", record.ball_id, record.team_id))
        return h.hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "escaped": self.escaped,
            "escape_ball": self.escape_ball,
            "winner_team": self.winner_team,
            "winner_team_name": (
                TEAM_NAMES[self.winner_team] if self.winner_team is not None else None
            ),
            "winner_generation": self.winner_generation,
            "winner_route": self.winner_route,
            "win_margin_seconds": self.win_margin_seconds,
            "team_balls": list(self.team_balls),
            "team_spawns": list(self.team_spawns),
            "team_collisions": list(self.team_collisions),
            "team_damage": list(self.team_damage),
            "team_breaks": list(self.team_breaks),
            "team_crossings": list(self.team_crossings),
            "team_frontier": list(self.team_frontier),
            "population_lead_changes": self.population_lead_changes,
            "frontier_lead_changes": self.frontier_lead_changes,
            "max_population_lead": self.max_population_lead,
            "failure_reason": self.failure_reason,
            "duration": self.duration,
            "escape_time": self.escape_time,
            "frontier_region": self.frontier_region,
            "collisions": self.collisions,
            "ball_collisions": self.ball_collisions,
            "near_misses": self.near_misses,
            "breaks": self.breaks,
            "grazing_collisions": self.grazing_collisions,
            "spawns": self.spawns,
            "spawns_suppressed": self.spawns_suppressed,
            "max_population": self.max_population,
            "max_generation": self.max_generation,
            "max_penetration": self.max_penetration,
            "min_spawn_clearance": self.min_spawn_clearance,
            "speed_min": self.speed_min,
            "speed_max": self.speed_max,
            "max_speed_correction": self.max_speed_correction,
            "mean_speed_correction": self.mean_speed_correction,
            "anomalous_crossings": self.anomalous_crossings,
            "newton_failures": self.newton_failures,
            "reproduction_violations": self.reproduction_violations,
            "digest": self.state_digest(),
            "team_digest": self.team_digest(),
        }


# --------------------------------------------------------------------------
# The internal ball
# --------------------------------------------------------------------------


class _Ball:
    """A ball's live state plus its cached next event.

    `credited` is a bitmask of the shells this ball has already been paid for.
    A child born outside shell `k` starts with bits `0..k` set, which is the
    whole of the anti-farming rule: there is no counter to reset and no history
    to scan, so a ball that goes back in and comes out again simply finds the
    bit already set.
    """

    __slots__ = (
        "ball_id",
        "team",
        "parent_id",
        "generation",
        "birth_time",
        "birth_shell",
        "lineage",
        "credited",
        "visited",
        "t",
        "x",
        "y",
        "vx",
        "vy",
        "region",
        "max_region",
        "region_entered_at",
        "collisions",
        "last_route",
        "kind",
        "when",
        "shell",
        "slot",
        "qx",
        "qy",
    )

    def __init__(
        self,
        ball_id: int,
        team: int,
        parent_id: int | None,
        generation: int,
        birth_time: float,
        birth_shell: int | None,
        lineage: tuple[int, ...],
        credited: int,
        t: float,
        x: float,
        y: float,
        vx: float,
        vy: float,
        region: int,
        route: str = "none",
    ) -> None:
        self.ball_id = ball_id
        self.team = team
        self.parent_id = parent_id
        self.generation = generation
        self.birth_time = birth_time
        self.birth_shell = birth_shell
        self.lineage = lineage
        self.credited = credited
        # Which regions this ball has actually stood in. A child born outside
        # shell 3 has never been in regions 0-2, so counting it among the balls
        # that "reached" shell 0 and failed to cross it would make every inner
        # shell look harder than it is. `max_region` cannot answer this; only a
        # record of where the ball has been can.
        self.visited = 1 << region
        self.t = t
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.region = region
        self.max_region = region
        self.region_entered_at = t
        self.collisions = 0
        # How this ball last got through a shell outward. A child inherits its
        # parent's, because it is born just outside the hole the parent has
        # this instant come through - and a ball born outside the *outermost*
        # shell can then clear the escape radius without ever making a crossing
        # of its own, which would otherwise leave the run's headline event with
        # no route at all. That is 11.5% of successful runs, not a corner case.
        self.last_route = route
        self.kind = "stale"
        self.when = math.inf
        self.shell = -1
        self.slot = -1
        self.qx = 0.0
        self.qy = 0.0


# --------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------


def _spawn_clearance(states: Sequence[_ShellState], px: float, py: float, t: float) -> float:
    """How far a point is from the nearest live panel surface, over all shells.

    Negative means the point is inside solid material, which is the thing a
    spawn must never be.

    A shell whose contact band contains the point is measured exactly, by the
    same `_nearest_live` the collision solver uses. A shell whose band the point
    is outside is bounded analytically by the radial gap to the band edge -
    which is a true lower bound on the clearance, not an estimate, because the
    band already contains every ball-centre radius at which the shell can be
    touched at all. Doing it this way keeps the number finite and honest; the
    band restriction itself is not optional, because `_nearest_live` searches a
    window of slots around the point's own angle and that argument only holds
    inside the band.
    """
    r = math.hypot(px, py)
    worst = math.inf
    for st in states:
        if r < st.band_lo:
            bound = st.band_lo - r
        elif r > st.band_hi:
            bound = r - st.band_hi
        else:
            probe = _nearest_live(st, px, py, t)
            if probe[1] < 0:
                continue
            bound = probe[0]
        if bound < worst:
            worst = bound
    return worst


def _apply_speed_model(
    vx: float, vy: float, config: MultishellConfig
) -> tuple[float, float, float]:
    """Constrain the post-bounce speed. Returns `(vx, vy, relative_correction)`.

    Direction is never touched, so none of this can steer - it can only decide
    how fast the run's clock runs and how hard a hit lands.
    """
    magnitude = math.hypot(vx, vy)
    if magnitude <= 0.0:
        return vx, vy, 0.0
    model = config.speed_model
    if model == "free":
        return vx, vy, 0.0
    if model == "constant":
        target = config.speed
    else:
        lo = config.speed_band[0] * config.speed
        hi = config.speed_band[1] * config.speed
        if magnitude < lo:
            target = lo
        elif magnitude > hi:
            target = hi
        else:
            return vx, vy, 0.0
    correction = abs(magnitude - target) / config.speed
    scale = target / magnitude
    return vx * scale, vy * scale, correction


def _resolve_next_event(
    b: _Ball,
    states: Sequence[_ShellState],
    n_shells: int,
    escape_radius: float,
    horizon: float,
    config: MultishellConfig,
    run: MultishellRun,
) -> None:
    """Fill in `b.kind` / `b.when` with the earliest thing that happens to `b`.

    Kinds: `collision`, `out`, `in`, `escape`, `horizon`. `when` is an absolute
    time. This is the single-ball loop's top half, lifted out so the scheduler
    can ask every ball the same question and take the smallest answer.
    """
    x, y, vx, vy, t = b.x, b.y, b.vx, b.vy, b.t
    region = b.region
    min_dt = config.min_dt

    if region < n_shells:
        t_out = _boundary_crossing(x, y, vx, vy, states[region].apothem, True, min_dt)
    else:
        t_out = _boundary_crossing(x, y, vx, vy, escape_radius, True, min_dt)
    t_in = (
        _boundary_crossing(x, y, vx, vy, states[region - 1].apothem, False, min_dt)
        if region > 0
        else None
    )

    limit = horizon - t
    for candidate in (t_out, t_in):
        if candidate is not None and candidate < limit:
            limit = candidate

    best: tuple[float, int, int, float, float] | None = None
    for k in (region - 1, region):
        if k < 0 or k >= n_shells:
            continue
        st = states[k]
        for lo, hi in _band_intervals(x, y, vx, vy, st.band_lo, st.band_hi, limit, min_dt):
            try:
                hit = _contact_in_interval(st, x, y, vx, vy, t, lo, hi, config)
            except _SolverExhausted:
                run.newton_failures += 1
                hit = None
            if hit is None:
                continue
            tau, slot, qx, qy = hit
            if best is None or tau < best[0]:
                best = (tau, k, slot, qx, qy)
            break

    if best is not None:
        tau, k, slot, qx, qy = best
        b.kind = "collision"
        b.when = t + tau
        b.shell = k
        b.slot = slot
        b.qx = qx
        b.qy = qy
        return

    crossing: tuple[float, bool] | None = None
    if t_out is not None and (t_in is None or t_out <= t_in):
        crossing = (t_out, True)
    elif t_in is not None:
        crossing = (t_in, False)

    if crossing is not None and t + crossing[0] <= horizon:
        tau, outward = crossing
        if outward and region == n_shells:
            b.kind = "escape"
        else:
            b.kind = "out" if outward else "in"
        b.when = t + tau
        b.shell = region if outward else region - 1
        return

    b.kind = "horizon"
    b.when = horizon
    b.shell = -1


def _ball_ball_contact(
    a: _Ball, c: _Ball, t_from: float, t_to: float, diameter: float
) -> float | None:
    """The first time in `(t_from, t_to]` two balls' surfaces touch, or None.

    Both balls are on straight lines valid across the whole interval, so this is
    an exact quadratic root: `|dp + dv * s| = diameter` in the shared clock.
    """
    dx = (a.x + a.vx * (t_from - a.t)) - (c.x + c.vx * (t_from - c.t))
    dy = (a.y + a.vy * (t_from - a.t)) - (c.y + c.vy * (t_from - c.t))
    dvx = a.vx - c.vx
    dvy = a.vy - c.vy
    q2 = dvx * dvx + dvy * dvy
    if q2 <= 0.0:
        return None
    q1 = 2.0 * (dx * dvx + dy * dvy)
    q0 = dx * dx + dy * dy - diameter * diameter
    if q0 <= 0.0:
        # Already overlapping at the interval start; only separate from here.
        return None
    disc = q1 * q1 - 4.0 * q2 * q0
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    s = (-q1 - root) / (2.0 * q2)
    if s <= 0.0:
        return None
    hit = t_from + s
    return hit if hit <= t_to else None


def simulate(seed: int, config: MultishellConfig = DEFAULT_CONFIG) -> MultishellRun:
    """Run one seed to first escape, timeout or collision cap."""
    arena = build_arena_for(seed, config)
    run = MultishellRun(seed=seed, config=config, arena=arena)

    states = [_ShellState(s, config.ball_radius, config.speed) for s in arena.shells]
    n_shells = len(states)
    outer = states[-1]
    escape_radius = outer.radius + outer.rho
    horizon = config.horizon
    graze_cut = config.graze_fraction * config.speed
    rest = config.restitution
    transfer = config.panel_momentum_transfer
    fractions = config.damage_state_fractions
    diameter = 2.0 * config.ball_radius

    # Per-panel ledgers that `_ShellState` does not carry: the damage state
    # index, the set of balls that have paid into the panel, and the same split
    # by team. The team split is what turns "the panel broke" into "cyan did
    # most of the work and orange walked through it", which is the story the
    # two-team rule is for.
    panel_state = [[0] * st.panel_count for st in states]
    contributors: list[list[set[int]]] = [[set() for _ in range(st.panel_count)] for st in states]
    team_contributors: list[list[list[set[int]]]] = [
        [[set() for _ in range(TEAM_COUNT)] for _ in range(st.panel_count)] for st in states
    ]
    team_panel_damage: list[list[list[float]]] = [
        [[0.0] * TEAM_COUNT for _ in range(st.panel_count)] for st in states
    ]

    teams = team_assignment(seed, config)
    founders = start_states(seed, config, arena)
    balls: list[_Ball] = []
    records: dict[int, BallRecord] = {}
    run.team_balls = [0] * TEAM_COUNT
    run.team_spawns = [0] * TEAM_COUNT
    run.team_collisions = [0] * TEAM_COUNT
    run.team_damage = [0.0] * TEAM_COUNT
    run.team_breaks = [0] * TEAM_COUNT
    run.team_crossings = [0] * TEAM_COUNT
    run.team_frontier = [0] * TEAM_COUNT
    team_advance_time = [0.0] * TEAM_COUNT
    run.speed_min = math.inf
    run.speed_max = 0.0
    for slot, (x0, y0, vx0, vy0) in enumerate(founders):
        team = teams[slot]
        founder = _Ball(
            slot, team, None, 0, 0.0, None, (slot,), 0, 0.0,
            x0, y0, vx0, vy0, arena.region_of(x0, y0),
        )
        balls.append(founder)
        records[slot] = BallRecord(slot, team, None, 0, 0.0, None, (slot,), (), ())
        run.flights[slot] = [Flight(0.0, x0, y0, vx0, vy0)]
        run.team_balls[team] += 1
        run.frontier_region = max(run.frontier_region, founder.region)
        run.team_frontier[team] = max(run.team_frontier[team], founder.region)
        speed0 = math.hypot(vx0, vy0)
        run.speed_min = min(run.speed_min, speed0)
        run.speed_max = max(run.speed_max, speed0)
    run.max_population = len(balls)
    run.population_samples.append((0.0, len(balls)))
    run.team_population_samples.append((0.0, tuple(run.team_balls)))
    run.team_frontier_samples.append((0.0, tuple(run.team_frontier)))

    events = run.events
    region_dwell = [0.0] * (n_shells + 1)
    spawn_index = 0
    next_id = len(balls)
    clock = 0.0

    # Lead bookkeeping. `sign` is +1 when team 0 is ahead. A lead change is a
    # transition between two *opposite non-zero* signs, so a run that ties and
    # then resumes the same lead has not changed lead, and a run that ties and
    # then flips has changed it once rather than twice.
    lead_sign = 0
    frontier_sign = 0

    def note_population(at: float) -> None:
        nonlocal lead_sign
        counts = tuple(run.team_balls)
        run.team_population_samples.append((at, counts))
        lead = counts[0] - counts[1]
        run.max_population_lead = max(run.max_population_lead, abs(lead))
        sign = (lead > 0) - (lead < 0)
        if sign != 0:
            if lead_sign != 0 and sign != lead_sign:
                run.population_lead_changes += 1
            lead_sign = sign

    def note_frontier(at: float) -> None:
        nonlocal frontier_sign
        run.team_frontier_samples.append((at, tuple(run.team_frontier)))
        lead = run.team_frontier[0] - run.team_frontier[1]
        sign = (lead > 0) - (lead < 0)
        if sign != 0:
            if frontier_sign != 0 and sign != frontier_sign:
                run.frontier_lead_changes += 1
            frontier_sign = sign

    for founder in balls:
        _resolve_next_event(founder, states, n_shells, escape_radius, horizon, config, run)

    def note_region(b: _Ball, new_region: int, at: float) -> None:
        region_dwell[b.region] += at - b.region_entered_at
        b.region = new_region
        b.visited |= 1 << new_region
        b.region_entered_at = at
        if new_region > b.max_region:
            b.max_region = new_region
        if new_region > run.frontier_region:
            run.frontier_region = new_region
        if new_region > run.team_frontier[b.team]:
            run.team_frontier[b.team] = new_region
            team_advance_time[b.team] = at
            note_frontier(at)

    def lineage_of(b: _Ball) -> list[int]:
        return list(b.lineage)

    while run.collisions < config.max_collisions:
        # The globally earliest event. Ties go to the lower ball id, which is
        # the only thing that makes a tie deterministic.
        chosen: _Ball | None = None
        for b in balls:
            if chosen is None or b.when < chosen.when:
                chosen = b
        if chosen is None or chosen.when >= horizon:
            break
        t_event = chosen.when

        # --- ball-ball contact, if enabled, may pre-empt the chosen event ---
        if config.ball_ball_collisions and len(balls) > 1:
            pair: tuple[float, _Ball, _Ball] | None = None
            for i in range(len(balls)):
                a = balls[i]
                for j in range(i + 1, len(balls)):
                    c = balls[j]
                    hit = _ball_ball_contact(a, c, clock, t_event, diameter)
                    if hit is not None and (pair is None or hit < pair[0]):
                        pair = (hit, a, c)
            if pair is not None:
                tb, a, c = pair
                ax = a.x + a.vx * (tb - a.t)
                ay = a.y + a.vy * (tb - a.t)
                cx = c.x + c.vx * (tb - c.t)
                cy = c.y + c.vy * (tb - c.t)
                nx = ax - cx
                ny = ay - cy
                norm = math.hypot(nx, ny) or 1.0
                nx /= norm
                ny /= norm
                rel = (a.vx - c.vx) * nx + (a.vy - c.vy) * ny
                a_in = (a.vx, a.vy)
                c_in = (c.vx, c.vy)
                # Equal masses, elastic: exchange the normal components.
                a.vx -= rel * nx
                a.vy -= rel * ny
                c.vx += rel * nx
                c.vy += rel * ny
                a.vx, a.vy, corr_a = _apply_speed_model(a.vx, a.vy, config)
                c.vx, c.vy, corr_c = _apply_speed_model(c.vx, c.vy, config)
                run.max_speed_correction = max(run.max_speed_correction, corr_a, corr_c)
                for who, px, py in ((a, ax, ay), (c, cx, cy)):
                    who.t = tb
                    who.x = px + (nx if who is a else -nx) * config.skin
                    who.y = py + (ny if who is a else -ny) * config.skin
                    run.flights[who.ball_id].append(Flight(tb, who.x, who.y, who.vx, who.vy))
                run.ball_collisions += 1
                events.append(
                    Event(
                        "ball_collision",
                        tb,
                        {
                            "ball_id": a.ball_id,
                            "team_id": a.team,
                            "other_id": c.ball_id,
                            "other_team_id": c.team,
                            "position": (a.x, a.y),
                            "other_position": (c.x, c.y),
                            "normal": (nx, ny),
                            "velocity_in": a_in,
                            "velocity_out": (a.vx, a.vy),
                            "other_velocity_in": c_in,
                            "other_velocity_out": (c.vx, c.vy),
                            "impact_speed": abs(rel),
                        },
                    )
                )
                clock = tb
                for who in (a, c):
                    _resolve_next_event(who, states, n_shells, escape_radius, horizon, config, run)
                continue

        clock = t_event
        b = chosen
        kind = b.kind

        if kind == "horizon":
            # Every remaining ball is also at the horizon or later.
            break

        tau = t_event - b.t
        b.t = t_event
        b.x += b.vx * tau
        b.y += b.vy * tau

        if kind == "collision":
            k = b.shell
            slot = b.slot
            qx, qy = b.qx, b.qy
            st = states[k]

            nx = b.x - qx
            ny = b.y - qy
            norm = math.hypot(nx, ny)
            if norm <= 0.0:
                nx, ny, norm = (b.x, b.y, math.hypot(b.x, b.y) or 1.0)
            nx /= norm
            ny /= norm
            penetration = st.rho - norm
            if penetration > run.max_penetration:
                run.max_penetration = penetration

            ux = -st.omega * qy * transfer
            uy = st.omega * qx * transfer
            rel_n = (b.vx - ux) * nx + (b.vy - uy) * ny
            impact = -rel_n
            vx_in, vy_in = b.vx, b.vy
            b.vx = b.vx - (1.0 + rest) * rel_n * nx
            b.vy = b.vy - (1.0 + rest) * rel_n * ny
            b.vx, b.vy, correction = _apply_speed_model(b.vx, b.vy, config)
            run.speed_correction_total += correction
            if correction > run.max_speed_correction:
                run.max_speed_correction = correction

            speed_now = math.hypot(b.vx, b.vy)
            if speed_now < run.speed_min:
                run.speed_min = speed_now
            if speed_now > run.speed_max:
                run.speed_max = speed_now

            radius_now = math.hypot(b.x, b.y) or 1.0
            radial_in = (vx_in * b.x + vy_in * b.y) / radius_now
            contact_angle = math.atan2(b.y, b.x)
            local_offset = st.shell.local_angle(contact_angle, t_event) - (slot + 0.5) * st.slot_width
            local_offset = (local_offset + math.pi) % TAU - math.pi
            grazing = impact < graze_cut

            run.collisions += 1
            run.team_collisions[b.team] += 1
            b.collisions += 1
            st.hits[slot] += 1
            if grazing:
                run.grazing_collisions += 1
            events.append(
                Event(
                    "collision",
                    t_event,
                    {
                        "ball_id": b.ball_id,
                        "team_id": b.team,
                        "shell_id": k,
                        "panel_id": slot,
                        "region": b.region,
                        "position": (b.x, b.y),
                        "contact_point": (qx, qy),
                        "contact_angle": contact_angle,
                        "normal": (nx, ny),
                        "velocity_in": (vx_in, vy_in),
                        "velocity_out": (b.vx, b.vy),
                        "impact_speed": impact,
                        "speed": speed_now,
                        "incidence": abs(impact) / speed_now if speed_now else 0.0,
                        "feature": "post" if _is_post_contact(st, slot, qx, qy, t_event) else "face",
                        "grazing": grazing,
                        "radial_outward": radial_in > 0.0,
                        "panel_local_offset": local_offset,
                    },
                )
            )

            if k == b.region and radial_in > 0.0:
                miss = _near_miss(st, b.x, b.y, vx_in, vy_in, t_event, contact_angle, config)
                if miss is not None:
                    miss["ball_id"] = b.ball_id
                    miss["team_id"] = b.team
                    miss["shell_id"] = k
                    miss["panel_id"] = slot
                    miss["region"] = b.region
                    run.near_misses += 1
                    events.append(Event("near_miss", t_event, _ordered(miss, "near_miss")))

            broke = False
            if config.breakable and st.live[slot]:
                threshold = config.break_thresholds[k]
                added = impact_damage(impact, config)
                if added > 0.0:
                    st.damage[slot] += added
                    contributors[k][slot].add(b.ball_id)
                    team_contributors[k][slot][b.team].add(b.ball_id)
                    team_panel_damage[k][slot][b.team] += added
                    run.team_damage[b.team] += added
                    records[b.ball_id].damage_dealt += added
                cumulative = st.damage[slot]
                team_cumulative = list(team_panel_damage[k][slot])
                new_state = damage_state_of(cumulative, threshold, fractions)
                events.append(
                    Event(
                        "damage",
                        t_event,
                        {
                            "ball_id": b.ball_id,
                            "team_id": b.team,
                            "shell_id": k,
                            "panel_id": slot,
                            "contribution": added,
                            "cumulative": cumulative,
                            "threshold": threshold,
                            "fraction": cumulative / threshold if threshold else math.inf,
                            "state": DAMAGE_STATES[new_state],
                            "impact_speed": impact,
                            "contributors": len(contributors[k][slot]),
                            "team_cumulative": team_cumulative,
                        },
                    )
                )
                previous = panel_state[k][slot]
                if new_state != previous:
                    panel_state[k][slot] = new_state
                    events.append(
                        Event(
                            "damage_state",
                            t_event,
                            {
                                "ball_id": b.ball_id,
                                "team_id": b.team,
                                "shell_id": k,
                                "panel_id": slot,
                                "previous_state": DAMAGE_STATES[previous],
                                "new_state": DAMAGE_STATES[new_state],
                                "cumulative": cumulative,
                                "threshold": threshold,
                                "fraction": cumulative / threshold if threshold else math.inf,
                            },
                        )
                    )
                if new_state == len(DAMAGE_STATES) - 1:
                    st.live[slot] = False
                    run.breaks += 1
                    run.team_breaks[b.team] += 1
                    broke = True
                    paid = team_panel_damage[k][slot]
                    largest_team = (
                        max(range(TEAM_COUNT), key=lambda i: (paid[i], -i))
                        if any(paid)
                        else None
                    )
                    events.append(
                        Event(
                            "panel_break",
                            t_event,
                            {
                                "ball_id": b.ball_id,
                                "team_id": b.team,
                                "shell_id": k,
                                "panel_id": slot,
                                "position": (qx, qy),
                                "break_angle": math.atan2(qy, qx),
                                "cumulative": cumulative,
                                "threshold": threshold,
                                "hits": st.hits[slot],
                                "contributors": len(contributors[k][slot]),
                                "team_cumulative": list(paid),
                                "team_contributors": [
                                    len(team_contributors[k][slot][i]) for i in range(TEAM_COUNT)
                                ],
                                "largest_team": largest_team,
                            },
                        )
                    )

            # Lift the centre clear so the panel just struck cannot be
            # re-detected at dt = 0.
            b.x = qx + nx * (st.rho + config.skin)
            b.y = qy + ny * (st.rho + config.skin)
            run.flights[b.ball_id].append(Flight(t_event, b.x, b.y, b.vx, b.vy))

            if broke:
                # A hole appeared. Every cached event was computed against the
                # old shell and has to be asked again.
                for other in balls:
                    _resolve_next_event(
                        other, states, n_shells, escape_radius, horizon, config, run
                    )
            else:
                _resolve_next_event(b, states, n_shells, escape_radius, horizon, config, run)
            continue

        if kind == "escape":
            run.escaped = True
            run.escape_ball = b.ball_id
            run.escape_time = t_event
            run.duration = t_event
            run.winner_team = b.team
            run.winner_generation = b.generation
            run.winner_route = b.last_route
            # How long the losing colour had been sitting at its own high-water
            # mark when this happened. A small number is a race still live at
            # the last second; a large one is a procession. Measured, never
            # targeted - nothing anywhere steers towards a close finish.
            loser = (b.team + 1) % TEAM_COUNT
            run.win_margin_seconds = t_event - team_advance_time[loser]
            note_region(b, b.region, t_event)
            records[b.ball_id].escaped = True
            run.flights[b.ball_id].append(Flight(t_event, b.x, b.y, b.vx, b.vy))
            events.append(
                Event(
                    "escape",
                    t_event,
                    {
                        "ball_id": b.ball_id,
                        "team_id": b.team,
                        "team_name": TEAM_NAMES[b.team],
                        "shell_id": n_shells - 1,
                        "route": b.last_route,
                        "position": (b.x, b.y),
                        "generation": b.generation,
                        "parent_id": b.parent_id,
                        "birth_time": b.birth_time,
                        "birth_shell": b.birth_shell,
                        "lineage": lineage_of(b),
                        "collisions": run.collisions,
                        "breaks": run.breaks,
                        "population": len(balls),
                        "population_by_team": list(run.team_balls),
                        "damage_by_team": list(run.team_damage),
                        "margin_seconds": run.win_margin_seconds,
                    },
                )
            )
            break

        # --- a region crossing -------------------------------------------
        outward = kind == "out"
        shell_index = b.shell
        st = states[shell_index]
        slot = st.slot_of(b.x, b.y, t_event)
        angle = math.atan2(b.y, b.x)
        local_offset = st.shell.local_angle(angle, t_event) - (slot + 0.5) * st.slot_width
        local_offset = (local_offset + math.pi) % TAU - math.pi
        if st.live[slot]:
            route = "anomaly"
            run.anomalous_crossings += 1
        elif st.was_opening[slot]:
            route = "opening"
        else:
            route = "break"
        b.last_route = route
        if outward:
            run.team_crossings[b.team] += 1
        new_region = b.region + 1 if outward else b.region - 1
        dwell_seconds = t_event - b.region_entered_at
        from_region = b.region

        first_for_ball = False
        reproduced = False
        child: _Ball | None = None
        spawn_event: Event | None = None
        if outward:
            bit = 1 << shell_index
            first_for_ball = not (b.credited & bit)
            if first_for_ball:
                # Credited on the crossing, not on the birth: a spawn refused by
                # the population cap still spends the ball's claim on this
                # shell. Nothing is ever removed from the population, so there
                # is no later moment at which the refusal could be revisited.
                b.credited |= bit

        note_region(b, new_region, t_event)
        run.flights[b.ball_id].append(Flight(t_event, b.x, b.y, b.vx, b.vy))

        if (
            outward
            and first_for_ball
            and config.reproduction
            and shell_index < n_shells
        ):
            if len(balls) >= config.max_population:
                run.spawns_suppressed += 1
            else:
                # The *global* spawn index, because that is the only version
                # of this rule that is exactly balanced. Alternating on the
                # parent's own child count was tried and measured instead, and
                # it is not: most balls have one or two children, so "the first
                # child turns +" put 70% of a population's turns the same way
                # and gave the whole simulation a chirality. Whether the global
                # rule is *also* balanced between the two colours is then an
                # empirical question rather than a constructional one, and
                # `test_the_spawn_turn_is_balanced_across_the_two_teams`
                # answers it over a population.
                turn = config.spawn_turn * (1.0 if spawn_index % 2 == 0 else -1.0)
                ct, stn = math.cos(turn), math.sin(turn)
                cvx = b.vx * ct - b.vy * stn
                cvy = b.vx * stn + b.vy * ct
                mag = math.hypot(cvx, cvy) or 1.0
                ux, uy = cvx / mag, cvy / mag
                lead = 0.0
                px, py = b.x, b.y
                clearance = _spawn_clearance(states, px, py, t_event)
                for step in range(config.spawn_lead_steps):
                    trial = config.spawn_lead_ball_radii * config.ball_radius * (0.5**step)
                    tx = b.x + ux * trial
                    ty = b.y + uy * trial
                    clr = _spawn_clearance(states, tx, ty, t_event)
                    if clr > 0.0:
                        lead, px, py, clearance = trial, tx, ty, clr
                        break
                if run.min_spawn_clearance is None or clearance < run.min_spawn_clearance:
                    run.min_spawn_clearance = clearance
                child_id = next_id
                next_id += 1
                child_lineage = b.lineage + (child_id,)
                credited_mask = (1 << (shell_index + 1)) - 1
                child = _Ball(
                    child_id,
                    b.team,
                    b.ball_id,
                    b.generation + 1,
                    t_event,
                    shell_index,
                    child_lineage,
                    credited_mask,
                    t_event,
                    px,
                    py,
                    cvx,
                    cvy,
                    new_region,
                    route,
                )
                balls.append(child)
                run.flights[child_id] = [Flight(t_event, px, py, cvx, cvy)]
                records[child_id] = BallRecord(
                    child_id,
                    b.team,
                    b.ball_id,
                    b.generation + 1,
                    t_event,
                    shell_index,
                    child_lineage,
                    tuple(range(shell_index + 1)),
                )
                parent_record = records[b.ball_id]
                parent_record.children = parent_record.children + (child_id,)
                run.spawns += 1
                run.team_spawns[b.team] += 1
                run.team_balls[b.team] += 1
                spawn_index += 1
                reproduced = True
                if child.generation > run.max_generation:
                    run.max_generation = child.generation
                if len(balls) > run.max_population:
                    run.max_population = len(balls)
                run.population_samples.append((t_event, len(balls)))
                note_population(t_event)
                if new_region > run.frontier_region:
                    run.frontier_region = new_region
                if new_region > run.team_frontier[child.team]:
                    run.team_frontier[child.team] = new_region
                    team_advance_time[child.team] = t_event
                    note_frontier(t_event)
                spawn_event = Event(
                    "ball_spawn",
                    t_event,
                    {
                        "ball_id": child_id,
                        "team_id": b.team,
                        "parent_id": b.ball_id,
                        "generation": child.generation,
                        "birth_shell": shell_index,
                        "region": new_region,
                        "position": (px, py),
                        "velocity": (cvx, cvy),
                        "speed": math.hypot(cvx, cvy),
                        "turn": turn,
                        "lead": lead,
                        "clearance": clearance,
                        "spawn_index": spawn_index - 1,
                        "population": len(balls),
                        "lineage": list(child_lineage),
                    },
                )

        events.append(
            Event(
                "shell_exit" if outward else "shell_entry",
                t_event,
                _ordered(
                    {
                        "ball_id": b.ball_id,
                        "team_id": b.team,
                        "shell_id": shell_index,
                        "panel_id": slot,
                        "route": route,
                        "opening_id": st.opening_of_slot.get(slot),
                        "from_region": from_region,
                        "to_region": new_region,
                        "position": (b.x, b.y),
                        "crossing_angle": angle,
                        "local_offset": local_offset,
                        "dwell_seconds": dwell_seconds,
                        "first_for_ball": first_for_ball,
                        "reproduced": reproduced,
                    }
                    if outward
                    else {
                        "ball_id": b.ball_id,
                        "team_id": b.team,
                        "shell_id": shell_index,
                        "panel_id": slot,
                        "route": route,
                        "opening_id": st.opening_of_slot.get(slot),
                        "from_region": from_region,
                        "to_region": new_region,
                        "position": (b.x, b.y),
                        "crossing_angle": angle,
                        "local_offset": local_offset,
                        "dwell_seconds": dwell_seconds,
                    },
                    "shell_exit" if outward else "shell_entry",
                ),
            )
        )

        if spawn_event is not None:
            events.append(spawn_event)

        _resolve_next_event(b, states, n_shells, escape_radius, horizon, config, run)
        if child is not None:
            _resolve_next_event(child, states, n_shells, escape_radius, horizon, config, run)

    # --- close the run ---------------------------------------------------
    if not run.escaped:
        if run.collisions >= config.max_collisions:
            run.failure_reason = "collision_cap"
            run.duration = min(clock, horizon)
        else:
            run.failure_reason = "timeout"
            run.duration = horizon

    end = run.duration
    by_region = [0] * (n_shells + 1)
    for b in balls:
        region_dwell[b.region] += max(0.0, end - b.region_entered_at)
        by_region[b.region] += 1
        rec = records[b.ball_id]
        rec.collisions = b.collisions
        rec.max_region = b.max_region
        rec.final_region = b.region
        rec.credited = tuple(i for i in range(n_shells) if b.credited & (1 << i))
        rec.visited = tuple(i for i in range(n_shells + 1) if b.visited & (1 << i))
        # Flights are closed at the run's end so a renderer never runs off one.
        run.flights[b.ball_id].append(Flight(end, b.x + b.vx * (end - b.t), b.y + b.vy * (end - b.t), b.vx, b.vy))

    if not run.escaped:
        events.append(
            Event(
                "failure",
                run.duration,
                {
                    "reason": run.failure_reason,
                    "horizon": horizon,
                    "active_balls": len(balls),
                    "total_balls": len(balls),
                    "frontier_region": run.frontier_region,
                    "frontier_balls": by_region[run.frontier_region],
                    "balls_by_region": by_region,
                    "collisions": run.collisions,
                    "breaks": run.breaks,
                    "balls_by_team": list(run.team_balls),
                    "frontier_by_team": list(run.team_frontier),
                    "damage_by_team": list(run.team_damage),
                },
            )
        )

    # One child per ball per shell, checked against what was actually written
    # rather than against the bitmask that was supposed to enforce it. A rule
    # that polices itself with its own variable proves nothing.
    claims: set[tuple[int, int]] = set()
    for ev in events:
        if ev.kind == "ball_spawn":
            claim = (ev.data["parent_id"], ev.data["birth_shell"])
            if claim in claims:
                run.reproduction_violations += 1
            claims.add(claim)

    run.balls = [records[i] for i in sorted(records)]
    run.damage = [list(s.damage) for s in states]
    run.broken = [
        [(not live) and not was for live, was in zip(s.live, s.was_opening)] for s in states
    ]
    run.hits_by_panel = [list(s.hits) for s in states]
    run.contributors_by_panel = [[len(c) for c in shell] for shell in contributors]
    run.region_dwell = region_dwell
    return run
