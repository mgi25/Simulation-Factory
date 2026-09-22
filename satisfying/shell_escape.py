"""MUSICAL SHELL ESCAPE: the ball, the shells it has to get through, the ledger.

Category 3 Test #2. One ball starts inside six nested rotating segmented
shells and either gets out or does not. It gets out two ways and only two ways:
it arrives at a shell while one of that shell's **openings** is in front of it
and passes through, or it hits the same **panel** hard enough and often enough
that the panel breaks and leaves a hole it can use later. Both are recorded, in
the same event stream, as different things.

The viewer-facing question is CAN THE BALL ESCAPE, and the whole point of this
module is that the answer is not known in advance. Nothing here steers the ball
towards an opening, weights a bounce, or nudges a rotation into alignment. The
simulation only answers what the geometry does.

## The model, stated so it can be argued with

**Flight.** Gravity is zero and restitution is 1, so between collisions the
ball travels in a straight line at a constant speed. That is not a shortcut:
Test #1's Phase 2 found that gravity is the pacing problem in a bouncing-ball
arena, because it makes the floor a sink and the ceiling a rarity, and at
gravity 0 a ball's activity stops being a free variable and the run length
becomes a clock the config sets. Here speed is the only clock.

**Collision response.** A panel is a massive frictionless wall and the
reflection is specular about the contact normal **in the panel's own frame**:
the relative normal velocity reverses, so the ball always leaves a wall that is
sweeping into it. On top of that the ball's *speed* is renormalised to the
config's `speed` after every contact. Both are config
(`panel_momentum_transfer`, `constant_speed`) and both default on.

The pair is there because the two obvious models each fail, and both failures
were measured rather than guessed, over 1500 seeds:

- **Ignore the panel's motion** (`panel_momentum_transfer = 0`). Speed is then
  exactly constant - and nothing can push the ball out of a wall. A ball that
  arrives at a post almost tangentially rebounds slower than the post sweeps
  in, is caught, and *chatters*: the same contact, at the same instant, tens of
  thousands of times. 14.4% of runs did this and the worst spent its entire
  collision budget in one spot.
- **Take the panel's motion and keep restitution 1** (`constant_speed = False`).
  Contacts then separate correctly and every shell becomes a Fermi
  accelerator: a wall moving into the ball adds energy and one moving away
  removes it, and the bias is towards adding. Median speed drift over a run was
  +34%, the 95th percentile +119%, the worst +225%. That is the runaway the
  brief forbids, and it makes the run's clock a thing the seed decides.

So the direction of the bounce comes entirely from the physical reflection off
a moving wall - nothing about it is tuned, and it cannot bias which way the
ball goes - and the magnitude is held at the config's `speed`, which makes the
speed the run's clock and nothing else. `max_speed_correction` reports the
largest renormalisation the run ever applied, so how much work the constraint
is doing is a number and not an assumption; it runs at a few percent per
contact, because the model is nearly energy-conserving to begin with.

What the rotation does is everything that matters: it decides which panel is in
front of the ball and *which way that panel's normal points* at the instant of
contact. A rotating polygon has time-dependent normals, so the system is
non-integrable and two seeds a hair apart end up in different shells. This is
the whole reason the shells are polygons and not rings -
`satisfying.shell_arena` sets out why a ring would have conserved `p x v` and
produced one rosette for the entire run.

**Damage.** Every contact with a panel adds
`(normal_impact_speed / damage_reference_speed) ** damage_exponent` to that
panel's ledger, and the panel breaks the first time the ledger reaches
`break_threshold`. A grazing hit adds nearly nothing, a head-on hit adds about
one unit, and duplicate hits accumulate: two solid hits on one panel is a
break at the default threshold of 1.6. A broken panel stops existing, for good.

## How a collision is found

Between collisions the ball is a point moving in a straight line, so the times
at which it enters and leaves any circle are exact quadratic roots. Each shell
publishes a `contact_band` - the ball-centre radii inside which touching that
shell is possible at all - so the solver first brackets the collision exactly
and then does work only inside the bracket.

Inside the bracket the geometry is a rotating capsule and the contact time is
not a polynomial root, so it is found by marching on the signed clearance
`D(t) = dist(centre, panel) - rho` with steps that are each short enough to be
*proved* free of a contact - by the nearest panel's curvature bound, by the
Lipschitz distance to every other panel, or by the two-point rule. Newton is
used where it applies but is never trusted on its own. `_contact_in_interval`
sets out why each step is safe, and why the obvious version of this solver
walks a grazing ball straight through a panel.

Three instruments say whether that worked, and they are the first numbers to
read if a run ever looks wrong. `max_penetration` is the deepest the ball
centre was ever found inside a panel. `anomalous_crossings` counts the times
the ball crossed a shell where a panel was still standing - which cannot
happen, so a non-zero count means the contact search missed something.
`newton_failures` counts contact searches that ran out of iterations, which is
a search that never proved anything either way. All three are zero on the
measured population, and a run is not evidence of anything if they are not.

## Regions, and what "passing a shell" means

The ball's position is summarised by a `region`: region 0 is inside shell 0,
region `m` is between shell `m-1` and shell `m`, region `shell_count` is
outside the outermost shell. A region changes when the ball's centre crosses a
shell's **mid-surface**, the circle through its chord midpoints. That circle is
rotation-independent, so the crossing time is exact, and the crossing can only
happen where no panel blocked the ball - which is precisely what "went through
a hole" means. Whether that hole was an original opening or a panel the ball
broke earlier is read off the shell's state and recorded as the exit `method`.

Falling back inward through a hole is allowed and is recorded as
`shell_entry`. It is not a bug: a ball that gets to region 4 and drops back to
region 2 is the drama the concept is asking for, and forbidding it would be
steering.

Escape is two beats, deliberately. `shell_exit` fires when the centre crosses
the outermost mid-surface; `escape` fires when the centre clears
`outer_radius + rho`, because until then the ball can still clip a post on the
way out and be thrown back in.

## Determinism

`start_state` derives the release point, the heading, every shell's initial
angle and every shell's rate jitter from the seed through
`satisfying.shell_seeds`, and nothing else in a run is random.
`ShellEscapeRun.state_digest` is a SHA-256 over the raw IEEE-754 bytes of every
collision, break and transition, so two runs that agree to six decimals at
collision one and diverge by collision three hundred compare as different
rather than as equal.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from satisfying import shell_seeds
from satisfying.shell_arena import Shell, ShellArena, build_arena

__all__ = [
    "ShellEscapeConfig",
    "DEFAULT_CONFIG",
    "EVENT_SCHEMA",
    "EVENT_KINDS",
    "SCHEMA_VERSION",
    "Event",
    "Flight",
    "ShellEscapeRun",
    "start_state",
    "resolve_shells",
    "simulate",
    "validate_events",
]

TAU = 2.0 * math.pi

# Bumped whenever an event kind, a field name or a field meaning changes.
# Phase 2A (visual) and Phase 2B (audio) pin this.
SCHEMA_VERSION = "category3-test2-shell-escape/1.0.0"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ShellEscapeConfig:
    """Everything about a run that is not the seed.

    Grouped by what it decides: the arena, the ball, the damage model, the
    horizon, and the thresholds that change what is *reported* without
    changing what the ball does.
    """

    # --- arena -----------------------------------------------------------
    shell_count: int = 6
    inner_radius: float = 5.0
    shell_spacing: float = 3.6
    panel_counts: tuple[int, ...] = (16, 17, 18, 19, 20, 21)
    openings_per_shell: tuple[int, ...] = (2, 3, 3, 4, 4, 5)
    opening_slots: tuple[int, ...] = (1, 1, 1, 1, 1, 1)
    panel_thickness: float = 0.30

    # --- rotation --------------------------------------------------------
    # Shell k turns at `omega_base * (inner_radius / R_k) ** omega_falloff`,
    # with the sign alternating by index and a bounded seeded jitter. At
    # falloff 1 every shell's surface moves at the same speed, which keeps the
    # outer shells from becoming a blur; at falloff 0 they all share one rate
    # and the arena reads as a single rigid body, which is why 1 is the default.
    omega_base: float = 0.62
    omega_falloff: float = 1.0
    omega_jitter: float = 0.22
    alternate_direction: bool = True

    # --- ball ------------------------------------------------------------
    ball_radius: float = 0.40
    speed: float = 17.0
    # `restitution` only bites when `constant_speed` is off, because the speed
    # constraint puts back whatever a restitution below 1 took out. Turning
    # both off together is the model the brief calls energy death, and it is
    # available on purpose - "no energy death unless deliberately configured".
    restitution: float = 1.0
    panel_momentum_transfer: float = 1.0
    constant_speed: bool = True

    # --- damage ----------------------------------------------------------
    damage_reference_speed: float = 17.0
    damage_exponent: float = 1.5
    break_threshold: float = 1.6
    breakable: bool = True

    # --- horizon ---------------------------------------------------------
    horizon: float = 26.0
    max_collisions: int = 20_000

    # --- reporting thresholds (never change the trajectory) ---------------
    near_miss_arc_ball_radii: float = 2.5
    near_miss_seconds: float = 0.15
    graze_fraction: float = 0.06

    # --- solver ----------------------------------------------------------
    skin: float = 1.0e-7
    clearance_tolerance: float = 1.0e-11
    min_dt: float = 1.0e-9
    max_newton_iterations: int = 2000

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
            "constant_speed": self.constant_speed,
            "damage_reference_speed": self.damage_reference_speed,
            "damage_exponent": self.damage_exponent,
            "break_threshold": self.break_threshold,
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

    def digest(self) -> str:
        """A stable fingerprint of the config, for the playback document."""
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def replace(self, **changes: Any) -> "ShellEscapeConfig":
        from dataclasses import replace as _replace

        return _replace(self, **changes)


DEFAULT_CONFIG = ShellEscapeConfig()


# --------------------------------------------------------------------------
# The frozen event schema
# --------------------------------------------------------------------------

# Every event carries `kind` and `t`; these are the *additional* fields, in the
# order they are written. Phase 2A and Phase 2B pin this table, and
# `validate_events` checks a run against it exactly - no missing key, no extra
# key, no renamed key - so a schema drift is a test failure rather than a
# renderer that silently draws nothing.
EVENT_SCHEMA: dict[str, tuple[str, ...]] = {
    "collision": (
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
    "near_miss": (
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
        "shell_id",
        "panel_id",
        "added",
        "cumulative",
        "threshold",
        "impact_speed",
    ),
    "panel_break": (
        "shell_id",
        "panel_id",
        "position",
        "break_angle",
        "cumulative",
        "hits",
    ),
    "shell_exit": (
        "shell_id",
        "panel_id",
        "method",
        "opening_id",
        "from_region",
        "to_region",
        "position",
        "crossing_angle",
        "local_offset",
        "dwell_seconds",
    ),
    "shell_entry": (
        "shell_id",
        "panel_id",
        "method",
        "opening_id",
        "from_region",
        "to_region",
        "position",
        "crossing_angle",
        "local_offset",
        "dwell_seconds",
    ),
    "escape": (
        "shell_id",
        "method",
        "position",
        "collisions",
        "breaks",
    ),
    "failure": (
        "reason",
        "region",
        "collisions",
        "breaks",
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


@dataclass(frozen=True)
class Flight:
    """One straight-line arc: where the ball was and where it was going.

    The trajectory is exactly the concatenation of these. A renderer asked for
    the ball at time `t` finds the last flight starting at or before `t` and
    evaluates `p + v * (t - t0)`. That is a closed form, so a renderer's frame
    rate cannot change where the ball is.
    """

    t: float
    x: float
    y: float
    vx: float
    vy: float


# --------------------------------------------------------------------------
# Seeded setup
# --------------------------------------------------------------------------


def resolve_shells(seed: int, config: ShellEscapeConfig) -> tuple[list[float], list[float]]:
    """The per-shell initial angle and signed angular velocity for a seed."""
    phase_rng = shell_seeds.make_shell_phase_rng(seed)
    rate_rng = shell_seeds.make_shell_rate_rng(seed)
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


def build_arena_for(seed: int, config: ShellEscapeConfig) -> ShellArena:
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


def start_state(seed: int, config: ShellEscapeConfig, arena: ShellArena) -> tuple[float, float, float, float]:
    """Where the ball is let go and which way it is pointing."""
    pos_rng = shell_seeds.make_position_rng(seed)
    head_rng = shell_seeds.make_heading_rng(seed)
    limit = shell_seeds.RELEASE_RADIUS_FRACTION * arena.shells[0].apothem
    # Uniform over the disc, not over (r, theta): sqrt keeps the density flat,
    # so a run is not three times more likely to start near the centre than a
    # naive uniform radius would make it.
    r = limit * math.sqrt(pos_rng.random())
    a = pos_rng.uniform(0.0, TAU)
    heading = head_rng.uniform(0.0, TAU)
    return (
        r * math.cos(a),
        r * math.sin(a),
        config.speed * math.cos(heading),
        config.speed * math.sin(heading),
    )


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass
class ShellEscapeRun:
    """One simulated run and everything measured about it while it happened."""

    seed: int
    config: ShellEscapeConfig
    arena: ShellArena
    flights: list[Flight] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    escaped: bool = False
    failure_reason: str | None = None
    duration: float = 0.0
    escape_time: float | None = None
    final_region: int = 0
    max_region: int = 0

    collisions: int = 0
    near_misses: int = 0
    breaks: int = 0
    grazing_collisions: int = 0

    # Instruments. These report; they never steer.
    max_penetration: float = 0.0
    speed_drift_relative: float = 0.0
    max_speed_correction: float = 0.0
    anomalous_crossings: int = 0
    newton_failures: int = 0

    damage: list[list[float]] = field(default_factory=list)
    broken: list[list[bool]] = field(default_factory=list)
    hits_by_panel: list[list[int]] = field(default_factory=list)
    region_dwell: list[float] = field(default_factory=list)

    def events_of(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]

    def state_digest(self) -> str:
        """SHA-256 over the raw bytes of every state-changing event.

        Collisions, breaks and region crossings, in order, as doubles. Two runs
        that agree early and diverge late are different here, which is the
        point: a digest that rounded would call a diverged pair equal.
        """
        h = hashlib.sha256()
        h.update(SCHEMA_VERSION.encode("utf-8"))
        h.update(self.config.digest().encode("utf-8"))
        h.update(struct.pack("<q", int(self.seed)))
        for ev in self.events:
            if ev.kind == "collision":
                d = ev.data
                h.update(
                    struct.pack(
                        "<c2i9d",
                        b"c",
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
            elif ev.kind == "panel_break":
                d = ev.data
                h.update(struct.pack("<c2i2d", b"b", d["shell_id"], d["panel_id"], ev.t, d["cumulative"]))
            elif ev.kind in ("shell_exit", "shell_entry"):
                d = ev.data
                h.update(
                    struct.pack(
                        "<c2i2d",
                        b"x" if ev.kind == "shell_exit" else b"n",
                        d["shell_id"],
                        d["to_region"],
                        ev.t,
                        d["crossing_angle"],
                    )
                )
            elif ev.kind == "escape":
                h.update(struct.pack("<cd", b"e", ev.t))
            elif ev.kind == "failure":
                h.update(struct.pack("<cd", b"f", ev.t))
        return h.hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "escaped": self.escaped,
            "failure_reason": self.failure_reason,
            "duration": self.duration,
            "escape_time": self.escape_time,
            "final_region": self.final_region,
            "max_region": self.max_region,
            "collisions": self.collisions,
            "near_misses": self.near_misses,
            "breaks": self.breaks,
            "grazing_collisions": self.grazing_collisions,
            "max_penetration": self.max_penetration,
            "speed_drift_relative": self.speed_drift_relative,
            "max_speed_correction": self.max_speed_correction,
            "anomalous_crossings": self.anomalous_crossings,
            "newton_failures": self.newton_failures,
            "digest": self.state_digest(),
        }


# --------------------------------------------------------------------------
# Geometry helpers used inside the hot loop
# --------------------------------------------------------------------------


class _ShellState:
    """The mutable, per-run half of a shell, laid out for the inner loop.

    A shell's vertices are its base angle rotated by `j * slot_width`, so the
    `cos_w` / `sin_w` tables let a whole polygon be placed from one `cos` and
    one `sin` per evaluation instead of `2N` of them.
    """

    __slots__ = (
        "shell",
        "shell_id",
        "radius",
        "apothem",
        "panel_count",
        "slot_width",
        "half_thickness",
        "theta0",
        "omega",
        "rho",
        "band_lo",
        "band_hi",
        "live",
        "was_opening",
        "damage",
        "hits",
        "cos_w",
        "sin_w",
        "lipschitz",
        "curvature",
        "opening_of_slot",
    )

    def __init__(self, shell: Shell, ball_radius: float, speed: float) -> None:
        self.shell = shell
        self.shell_id = shell.shell_id
        self.radius = shell.radius
        self.apothem = shell.apothem
        self.panel_count = shell.panel_count
        self.slot_width = shell.slot_width
        self.half_thickness = 0.5 * shell.thickness
        self.theta0 = shell.theta0
        self.omega = shell.omega
        self.rho = ball_radius + self.half_thickness
        self.band_lo = self.apothem - self.rho
        self.band_hi = self.radius + self.rho
        n = shell.panel_count
        self.live = [True] * n
        self.was_opening = [False] * n
        for slot in shell.open_slots:
            self.live[slot] = False
            self.was_opening[slot] = True
        self.damage = [0.0] * n
        self.hits = [0] * n
        w = shell.slot_width
        self.cos_w = [math.cos(j * w) for j in range(n + 1)]
        self.sin_w = [math.sin(j * w) for j in range(n + 1)]
        self.lipschitz = speed + abs(shell.omega) * (shell.radius + self.half_thickness)
        # How fast the clearance to one panel can bend, bounding both pieces of
        # the distance-to-a-capsule: the flat face, where the curvature comes
        # from the panel turning under the ball, and the end cap, where it comes
        # from the ball swinging around a post at a range of only `rho`. The cap
        # term dominates and it is the one that matters, because a post is what
        # a ball aiming at an opening actually clips.
        omega = abs(shell.omega)
        face = omega * omega * (3.0 * shell.radius + self.rho) + 2.0 * omega * self.lipschitz
        cap = omega * omega * shell.radius + self.lipschitz * self.lipschitz / self.rho
        self.curvature = max(face, cap)
        self.opening_of_slot: dict[int, str] = {}
        for opening in shell.openings:
            for i in range(opening.slot_count):
                self.opening_of_slot[(opening.first_slot + i) % n] = opening.opening_id

    def base_trig(self, t: float) -> tuple[float, float]:
        a = self.theta0 + self.omega * t
        return math.cos(a), math.sin(a)

    def vertex_with(self, ca: float, sa: float, index: int) -> tuple[float, float]:
        j = index % self.panel_count
        cw = self.cos_w[j]
        sw = self.sin_w[j]
        r = self.radius
        return (r * (ca * cw - sa * sw), r * (sa * cw + ca * sw))

    def slot_of(self, x: float, y: float, t: float) -> int:
        local = (math.atan2(y, x) - (self.theta0 + self.omega * t)) % TAU
        return int(local // self.slot_width) % self.panel_count

    def passable_runs(self) -> list[tuple[int, int]]:
        """Runs of consecutive non-live slots, as `(first_slot, length)`.

        Openings and broken panels together - to the ball they are the same
        hole, and the event stream is where they are told apart.
        """
        n = self.panel_count
        live = self.live
        if all(live):
            return []
        if not any(live):
            return [(0, n)]
        start = next(i for i in range(n) if not live[i] and live[(i - 1) % n])
        runs: list[tuple[int, int]] = []
        i = 0
        while i < n:
            slot = (start + i) % n
            if not live[slot]:
                length = 0
                while not live[(start + i + length) % n]:
                    length += 1
                runs.append((slot, length))
                i += length
            else:
                i += 1
        return runs


def _segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> tuple[float, float, float]:
    """Distance from a point to a segment, and the closest point on it."""
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom <= 0.0:
        return math.hypot(px - ax, py - ay), ax, ay
    s = ((px - ax) * dx + (py - ay) * dy) / denom
    if s < 0.0:
        s = 0.0
    elif s > 1.0:
        s = 1.0
    qx = ax + s * dx
    qy = ay + s * dy
    return math.hypot(px - qx, py - qy), qx, qy


def _nearest_live(
    st: _ShellState, x: float, y: float, t: float
) -> tuple[float, int, float, float, float, float, float, float]:
    """The two nearest live panels, and a floor for everything else.

    Returns `(d1, slot1, q1x, q1y, d2, q2x, q2y, rest)`: the closest live
    panel's clearance `distance - rho` and the point on it nearest the ball,
    the same for the runner-up, and a lower bound on the clearance to every
    other live panel of the shell.

    Two are returned rather than one because of corners. A ball that clips a
    vertex is touching *both* panels that meet there, and a solver that bounds
    only the nearest one and leaves the other to the Lipschitz rule ends up
    with a safe step of `0 / S` and marches nowhere: the first version of this
    spent two thousand evaluations inside a two-millisecond window and gave up.
    With both near panels carrying their own curvature bound, a corner costs
    the same handful of steps as a flat face.

    The search is a window of slots around the ball's own angle, which is
    enough while the ball is inside the shell's contact band - the only place
    this is called. For a convex regular polygon the closest boundary point to
    a point near it lies on the edge whose slot contains it or on a neighbour,
    and the window is a slot wider than that on each side. Panels beyond the
    window are bounded analytically: a slot `reach` steps away subtends at
    least `reach * slot_width`, so it is at least
    `apothem * sin(reach * slot_width)` off. That is what keeps `rest` honest
    when the window holds fewer than three live panels. The window widens only
    when every nearby slot is a hole, which is exactly when there is genuinely
    nothing close.
    """
    n = st.panel_count
    ca, sa = st.base_trig(t)
    centre = st.slot_of(x, y, t)
    d1 = d2 = d3 = math.inf
    slot1 = -1
    q1x = q1y = q2x = q2y = 0.0
    reach = 2
    while True:
        found = False
        for offset in range(-reach, reach + 1):
            slot = (centre + offset) % n
            if not st.live[slot]:
                continue
            found = True
            ax, ay = st.vertex_with(ca, sa, slot)
            bx, by = st.vertex_with(ca, sa, slot + 1)
            d, qx, qy = _segment_distance(x, y, ax, ay, bx, by)
            if d < d1:
                d3 = d2
                d2, q2x, q2y = d1, q1x, q1y
                d1, slot1, q1x, q1y = d, slot, qx, qy
            elif d < d2:
                d3 = d2
                d2, q2x, q2y = d, qx, qy
            elif d < d3:
                d3 = d
        if found or reach > n // 2:
            break
        reach += 2
    if slot1 < 0:
        return math.inf, -1, 0.0, 0.0, math.inf, 0.0, 0.0, math.inf
    outside = st.apothem * math.sin(min(reach * st.slot_width, 0.5 * math.pi))
    if outside < d3:
        d3 = outside
    rho = st.rho
    return (
        d1 - rho,
        slot1,
        q1x,
        q1y,
        d2 - rho,
        q2x,
        q2y,
        d3 - rho,
    )


def _circle_crossings(
    x: float, y: float, vx: float, vy: float, radius: float
) -> tuple[float, float] | None:
    """The two times a straight-line flight is at `radius`, or None."""
    c2 = vx * vx + vy * vy
    if c2 <= 0.0:
        return None
    c1 = 2.0 * (x * vx + y * vy)
    c0 = x * x + y * y - radius * radius
    disc = c1 * c1 - 4.0 * c2 * c0
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    return ((-c1 - root) / (2.0 * c2), (-c1 + root) / (2.0 * c2))


def _band_intervals(
    x: float, y: float, vx: float, vy: float, lo: float, hi: float, t_end: float, t_min: float
) -> list[tuple[float, float]]:
    """When, within `[t_min, t_end]`, the flight's radius is in `[lo, hi]`."""
    outer = _circle_crossings(x, y, vx, vy, hi)
    if outer is None:
        return []
    a, b = outer
    a = max(a, t_min)
    b = min(b, t_end)
    if b <= a:
        return []
    inner = _circle_crossings(x, y, vx, vy, lo) if lo > 0.0 else None
    if inner is None:
        return [(a, b)]
    p, q = inner
    if q <= a or p >= b:
        return [(a, b)]
    out: list[tuple[float, float]] = []
    if p > a:
        out.append((a, min(p, b)))
    if q < b:
        out.append((max(q, a), b))
    return [(s, e) for s, e in out if e > s]


def _boundary_crossing(
    x: float, y: float, vx: float, vy: float, radius: float, outward: bool, t_min: float
) -> float | None:
    """First time after `t_min` the flight crosses `radius` in one direction."""
    roots = _circle_crossings(x, y, vx, vy, radius)
    if roots is None:
        return None
    c2 = vx * vx + vy * vy
    c1 = 2.0 * (x * vx + y * vy)
    for t in roots:
        if t <= t_min:
            continue
        slope = 2.0 * c2 * t + c1
        if (slope > 0.0) == outward and slope != 0.0:
            return t
    return None


# --------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------


def _clearance_rate(
    px: float, py: float, qx: float, qy: float, vx: float, vy: float, omega: float, fallback: float
) -> float:
    """How fast the clearance to one panel is changing, exactly.

    The contact normal dotted with the ball's velocity minus the velocity of
    the panel material under the contact. By the envelope theorem the sliding
    of the closest point along the panel contributes nothing at first order, so
    this is the derivative and not an approximation of it.
    """
    nx = px - qx
    ny = py - qy
    norm = math.hypot(nx, ny)
    if norm <= 0.0:
        return fallback
    return (nx * (vx + omega * qy) + ny * (vy - omega * qx)) / norm


def _contact_in_interval(
    st: _ShellState,
    x: float,
    y: float,
    vx: float,
    vy: float,
    t0: float,
    lo: float,
    hi: float,
    config: ShellEscapeConfig,
) -> tuple[float, int, float, float] | None:
    """First contact with a live panel of `st` inside `[lo, hi]` of a flight.

    Two bounds carry the search, and every step is short enough for one of them
    to prove there is no contact inside it.

    **A near panel is bounded by its curvature.** For a single panel the
    clearance is continuously differentiable with a piecewise second derivative
    bounded by `st.curvature`, so from a clearance `d` and a rate of change `r`
    it cannot reach zero before `(r + sqrt(r*r + 2*C*d)) / C`. That is the step
    that makes this solver usable: leaving a panel just struck, `d` is the skin
    and `r` is the rebound speed, and the bound is a real step rather than the
    `d / S` crawl a plain Lipschitz argument gives. On a near-tangential graze,
    where `r` is small and the crawl is worst, it is the difference between a
    dozen evaluations and several hundred.

    The bound is applied to the two nearest panels, each with its own rate,
    because a ball clipping a vertex is touching both panels that meet there -
    and bounding only the nearest one leaves the other on the Lipschitz rule
    with a clearance of nearly zero, which is a safe step of nearly zero.

    **Everything else is bounded by the Lipschitz constant.** Every remaining
    live panel is at least `rest` away and a clearance changes no faster than
    `S = speed + |omega| * (radius + thickness/2)`, so nothing else can be
    reached before `rest / S`.

    The curvature bound is per panel, never applied to the minimum over
    panels, because that minimum has a downward kink where the nearest panel
    changes and a second-derivative bound says nothing across a kink.
    Separating the cases is what makes the argument hold rather than nearly
    hold.

    Newton is used on top when the ball is approaching, since it converges
    quadratically, but a Newton step is never *believed*: it is clipped to the
    interval and checked by the two-point rule - two positive clearances `d1`
    and `d2` leave no room for a root when `(t2 - t1) * S <= d1 + d2` - and a
    step that fails the check is discarded for the safe one. A Newton step
    running past the end of the interval is not evidence that the interval is
    clear; on a graze the derivative passes through almost zero, the step lands
    seconds away, and a solver that returns "no contact" there walks the ball
    through a panel.
    """
    limit = st.lipschitz
    curvature = st.curvature
    omega = st.omega
    tol = config.clearance_tolerance
    tau = lo
    px = x + vx * tau
    py = y + vy * tau
    d, slot, qx, qy, d2, q2x, q2y, rest = _nearest_live(st, px, py, t0 + tau)
    if slot < 0:
        return None

    for _ in range(config.max_newton_iterations):
        if d < 0.0:
            # Handed an already-penetrating state. Report it where it is; the
            # run's `max_penetration` is what makes that visible rather than
            # quietly plausible.
            return (tau, slot, qx, qy)

        rate = _clearance_rate(px, py, qx, qy, vx, vy, omega, -limit)

        if d <= tol:
            if rate < 0.0:
                return (tau, slot, qx, qy)
            # Touching while moving away: the panel just left, not a contact.
            tau += 1000.0 * tol
            if tau >= hi:
                return None
            px = x + vx * tau
            py = y + vy * tau
            d, slot, qx, qy, d2, q2x, q2y, rest = _nearest_live(st, px, py, t0 + tau)
            if slot < 0:
                return None
            continue

        safe = (rate + math.sqrt(rate * rate + 2.0 * curvature * d)) / curvature
        if d2 < math.inf:
            if d2 <= 0.0:
                near = 0.0
            else:
                rate2 = _clearance_rate(px, py, q2x, q2y, vx, vy, omega, -limit)
                near = (rate2 + math.sqrt(rate2 * rate2 + 2.0 * curvature * d2)) / curvature
            if near < safe:
                safe = near
        if rest < math.inf:
            other = rest / limit
            if other < safe:
                safe = other
        if safe <= 0.0:
            safe = d / limit

        step = safe
        verify = False
        if rate < 0.0:
            newton = -d / rate
            if newton > safe:
                step = newton
                verify = True

        nxt = tau + step
        capped = nxt >= hi
        if capped:
            nxt = hi
            verify = True
        px2 = x + vx * nxt
        py2 = y + vy * nxt
        probe = _nearest_live(st, px2, py2, t0 + nxt)
        if probe[1] < 0:
            return None
        if probe[0] < 0.0:
            return _close_bracket(st, x, y, vx, vy, t0, tau, d, nxt, probe[0], tol)

        if verify and nxt - tau > safe and (nxt - tau) * limit > d + probe[0]:
            # Not proven clear. Fall back to the step that is.
            nxt = tau + safe
            if nxt >= hi:
                return None
            px2 = x + vx * nxt
            py2 = y + vy * nxt
            probe = _nearest_live(st, px2, py2, t0 + nxt)
            if probe[1] < 0:
                return None
            if probe[0] < 0.0:
                return _close_bracket(st, x, y, vx, vy, t0, tau, d, nxt, probe[0], tol)
        elif capped:
            return None

        tau = nxt
        d, slot, qx, qy, d2, q2x, q2y, rest = probe
        px, py = px2, py2

    raise _SolverExhausted(tau)


class _SolverExhausted(Exception):
    """The contact search ran out of iterations. Never expected; always loud."""

    def __init__(self, tau: float) -> None:
        super().__init__(f"contact search exhausted at tau={tau!r}")
        self.tau = tau


def _close_bracket(
    st: _ShellState,
    x: float,
    y: float,
    vx: float,
    vy: float,
    t0: float,
    a: float,
    da: float,
    b: float,
    db: float,
    tol: float,
) -> tuple[float, int, float, float]:
    """Illinois false position on a bracket where `D` has changed sign.

    Newton lands within a hair of the root on a nearly flat panel, so this
    normally runs two or three times; the bisection fallback is there for the
    contacts that happen across a panel end, where `D` has a kink.
    """
    side = 0
    result = b
    for _ in range(60):
        if b - a <= 1.0e-14 * (1.0 + abs(b)):
            break
        m = (a * db - b * da) / (db - da)
        floor = a + 0.05 * (b - a)
        ceil = b - 0.05 * (b - a)
        if not (floor <= m <= ceil):
            m = 0.5 * (a + b)
        px = x + vx * m
        py = y + vy * m
        dm = _nearest_live(st, px, py, t0 + m)[0]
        if dm > 0.0:
            a, da = m, dm
            if side == 1:
                db *= 0.5
            side = 1
        else:
            b, db = m, dm
            if side == -1:
                da *= 0.5
            side = -1
        result = b
        if -tol <= dm <= tol:
            result = m
            break
    px = x + vx * result
    py = y + vy * result
    _d, slot, qx, qy = _nearest_live(st, px, py, t0 + result)[:4]
    return (result, slot, qx, qy)

def simulate(seed: int, config: ShellEscapeConfig = DEFAULT_CONFIG) -> ShellEscapeRun:
    """Run one seed to escape, timeout or collision cap."""
    arena = build_arena_for(seed, config)
    run = ShellEscapeRun(seed=seed, config=config, arena=arena)

    states = [_ShellState(s, config.ball_radius, config.speed) for s in arena.shells]
    n_shells = len(states)
    outer = states[-1]
    escape_radius = outer.radius + outer.rho

    x, y, vx, vy = start_state(seed, config, arena)
    t = 0.0
    speed0 = math.hypot(vx, vy)
    region = arena.region_of(x, y)
    run.max_region = region
    region_entered_at = [0.0] * (n_shells + 1)
    dwell = [0.0] * (n_shells + 1)

    run.flights.append(Flight(t, x, y, vx, vy))
    events = run.events
    horizon = config.horizon
    min_dt = config.min_dt
    rest = config.restitution
    transfer = config.panel_momentum_transfer
    constant_speed = config.constant_speed
    target_speed = config.speed
    graze_cut = config.graze_fraction * config.speed

    def note_region_change(new_region: int, at: float) -> None:
        dwell[region] += at - region_entered_at[region]
        region_entered_at[new_region] = at

    while t < horizon and run.collisions < config.max_collisions:
        # Where the flight could leave the current region.
        t_out: float | None
        t_in: float | None
        if region < n_shells:
            t_out = _boundary_crossing(x, y, vx, vy, states[region].apothem, True, min_dt)
        else:
            t_out = _boundary_crossing(x, y, vx, vy, escape_radius, True, min_dt)
        if region > 0:
            t_in = _boundary_crossing(x, y, vx, vy, states[region - 1].apothem, False, min_dt)
        else:
            t_in = None

        limit = horizon - t
        for candidate in (t_out, t_in):
            if candidate is not None and candidate < limit:
                limit = candidate

        # Which shells can be touched during this flight.
        best: tuple[float, int, int, float, float] | None = None
        for k in (region - 1, region):
            if k < 0 or k >= n_shells:
                continue
            st = states[k]
            for lo, hi in _band_intervals(x, y, vx, vy, st.band_lo, st.band_hi, limit, min_dt):
                try:
                    hit = _contact_in_interval(st, x, y, vx, vy, t, lo, hi, config)
                except _SolverExhausted:
                    # Counted rather than swallowed: a search that ran out of
                    # iterations has not proved there is no contact, so a run
                    # with a non-zero count here is not evidence of anything.
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
            t += tau
            x += vx * tau
            y += vy * tau
            st = states[k]

            nx = x - qx
            ny = y - qy
            norm = math.hypot(nx, ny)
            if norm <= 0.0:
                nx, ny, norm = (x, y, math.hypot(x, y) or 1.0)
            nx /= norm
            ny /= norm
            penetration = st.rho - norm
            if penetration > run.max_penetration:
                run.max_penetration = penetration

            # The panel's own surface velocity at the contact. Including it is
            # what makes the ball leave a wall that is sweeping into it, which
            # is what stops a near-tangential arrival at a post from chattering.
            ux = -st.omega * qy * transfer
            uy = st.omega * qx * transfer
            rel_n = (vx - ux) * nx + (vy - uy) * ny
            impact = -rel_n
            vx_in, vy_in = vx, vy
            vx = vx - (1.0 + rest) * rel_n * nx
            vy = vy - (1.0 + rest) * rel_n * ny
            if constant_speed:
                # The wall does work; the constraint takes it straight back
                # out. Direction is untouched, so this cannot steer - it can
                # only decide how fast the run's clock runs.
                magnitude = math.hypot(vx, vy)
                if magnitude > 0.0:
                    correction = abs(magnitude - target_speed) / target_speed
                    if correction > run.max_speed_correction:
                        run.max_speed_correction = correction
                    scale = target_speed / magnitude
                    vx *= scale
                    vy *= scale

            radius_now = math.hypot(x, y) or 1.0
            radial_in = (vx_in * x + vy_in * y) / radius_now
            contact_angle = math.atan2(y, x)
            local_offset = st.shell.local_angle(contact_angle, t) - (slot + 0.5) * st.slot_width
            local_offset = (local_offset + math.pi) % TAU - math.pi
            grazing = impact < graze_cut
            speed_now = math.hypot(vx, vy)

            run.collisions += 1
            st.hits[slot] += 1
            if grazing:
                run.grazing_collisions += 1
            events.append(
                Event(
                    "collision",
                    t,
                    {
                        "shell_id": k,
                        "panel_id": slot,
                        "region": region,
                        "position": (x, y),
                        "contact_point": (qx, qy),
                        "contact_angle": contact_angle,
                        "normal": (nx, ny),
                        "velocity_in": (vx_in, vy_in),
                        "velocity_out": (vx, vy),
                        "impact_speed": impact,
                        "speed": speed_now,
                        "incidence": abs(impact) / speed_now if speed_now else 0.0,
                        "feature": "post"
                        if _is_post_contact(st, slot, qx, qy, t)
                        else "face",
                        "grazing": grazing,
                        "radial_outward": radial_in > 0.0,
                        "panel_local_offset": local_offset,
                    },
                )
            )

            # Near miss: the ball was on its way out of its own frontier shell
            # and struck solid material close to a hole it could have used.
            if k == region and radial_in > 0.0:
                miss = _near_miss(st, x, y, vx_in, vy_in, t, contact_angle, config)
                if miss is not None:
                    miss["shell_id"] = k
                    miss["panel_id"] = slot
                    miss["region"] = region
                    run.near_misses += 1
                    events.append(Event("near_miss", t, _ordered(miss, "near_miss")))

            # Damage, then possibly a break - once, and for good.
            if config.breakable and st.live[slot]:
                added = (abs(impact) / config.damage_reference_speed) ** config.damage_exponent
                st.damage[slot] += added
                events.append(
                    Event(
                        "damage",
                        t,
                        {
                            "shell_id": k,
                            "panel_id": slot,
                            "added": added,
                            "cumulative": st.damage[slot],
                            "threshold": config.break_threshold,
                            "impact_speed": impact,
                        },
                    )
                )
                if st.damage[slot] >= config.break_threshold:
                    st.live[slot] = False
                    run.breaks += 1
                    events.append(
                        Event(
                            "panel_break",
                            t,
                            {
                                "shell_id": k,
                                "panel_id": slot,
                                "position": (qx, qy),
                                "break_angle": math.atan2(qy, qx),
                                "cumulative": st.damage[slot],
                                "hits": st.hits[slot],
                            },
                        )
                    )

            # Lift the centre clear of the surface so the panel just struck
            # cannot be re-detected at dt = 0. Eight orders below the ball
            # radius: unreadable on screen, far too large for a double to lose.
            x = qx + nx * (st.rho + config.skin)
            y = qy + ny * (st.rho + config.skin)
            run.flights.append(Flight(t, x, y, vx, vy))
            continue

        # No collision: the flight either leaves the region or runs out of time.
        crossing: tuple[float, bool] | None = None
        if t_out is not None and (t_in is None or t_out <= t_in):
            crossing = (t_out, True)
        elif t_in is not None:
            crossing = (t_in, False)

        if crossing is not None and t + crossing[0] <= horizon:
            tau, outward = crossing
            t += tau
            x += vx * tau
            y += vy * tau
            if outward and region == n_shells:
                run.escaped = True
                run.escape_time = t
                run.duration = t
                note_region_change(region, t)
                events.append(
                    Event(
                        "escape",
                        t,
                        {
                            "shell_id": n_shells - 1,
                            "method": _last_exit_method(events),
                            "position": (x, y),
                            "collisions": run.collisions,
                            "breaks": run.breaks,
                        },
                    )
                )
                break
            shell_index = region if outward else region - 1
            st = states[shell_index]
            slot = st.slot_of(x, y, t)
            angle = math.atan2(y, x)
            local = st.shell.local_angle(angle, t)
            local_offset = local - (slot + 0.5) * st.slot_width
            local_offset = (local_offset + math.pi) % TAU - math.pi
            if st.live[slot]:
                method = "anomaly"
                run.anomalous_crossings += 1
            elif st.was_opening[slot]:
                method = "opening"
            else:
                method = "break"
            new_region = region + 1 if outward else region - 1
            dwell_seconds = t - region_entered_at[region]
            note_region_change(new_region, t)
            events.append(
                Event(
                    "shell_exit" if outward else "shell_entry",
                    t,
                    {
                        "shell_id": shell_index,
                        "panel_id": slot,
                        "method": method,
                        "opening_id": st.opening_of_slot.get(slot),
                        "from_region": region,
                        "to_region": new_region,
                        "position": (x, y),
                        "crossing_angle": angle,
                        "local_offset": local_offset,
                        "dwell_seconds": dwell_seconds,
                    },
                )
            )
            region = new_region
            if region > run.max_region:
                run.max_region = region
            continue

        # Nothing left to do before the horizon.
        tau = horizon - t
        t = horizon
        x += vx * tau
        y += vy * tau
        break

    if not run.escaped:
        run.duration = min(t, horizon)
        reason = "timeout" if run.collisions < config.max_collisions else "collision_cap"
        run.failure_reason = reason
        dwell[region] += run.duration - region_entered_at[region]
        events.append(
            Event(
                "failure",
                run.duration,
                {
                    "reason": reason,
                    "region": region,
                    "collisions": run.collisions,
                    "breaks": run.breaks,
                },
            )
        )

    run.final_region = region
    run.region_dwell = dwell
    run.damage = [list(s.damage) for s in states]
    run.broken = [[(not live) and not was for live, was in zip(s.live, s.was_opening)] for s in states]
    run.hits_by_panel = [list(s.hits) for s in states]
    run.speed_drift_relative = abs(math.hypot(vx, vy) - speed0) / speed0 if speed0 else 0.0
    run.flights.append(Flight(run.duration, x, y, vx, vy))
    return run


def _is_post_contact(st: _ShellState, slot: int, qx: float, qy: float, t: float) -> bool:
    """Did the ball clip a panel's end rather than its face?

    A post contact is what happens when a ball aims at an opening and misses,
    so it is worth telling apart from a flat hit for the visual and audio
    branches, which will want a different sound for a clipped edge.
    """
    ca, sa = st.base_trig(t)
    ax, ay = st.vertex_with(ca, sa, slot)
    bx, by = st.vertex_with(ca, sa, slot + 1)
    length = math.hypot(bx - ax, by - ay)
    if length <= 0.0:
        return True
    s = ((qx - ax) * (bx - ax) + (qy - ay) * (by - ay)) / (length * length)
    return s <= 1.0e-9 or s >= 1.0 - 1.0e-9


def _ordered(data: dict[str, Any], kind: str) -> dict[str, Any]:
    """Re-key a payload into the schema's field order."""
    return {name: data[name] for name in EVENT_SCHEMA[kind]}


def _last_exit_method(events: Sequence[Event]) -> str:
    for ev in reversed(events):
        if ev.kind == "shell_exit":
            return ev.data["method"]
    return "unknown"


def _near_miss(
    st: _ShellState,
    x: float,
    y: float,
    vx: float,
    vy: float,
    t: float,
    contact_angle: float,
    config: ShellEscapeConfig,
) -> dict[str, Any] | None:
    """Was this collision a near miss of a hole the ball could have used?

    The definition is geometric, not a mood. Take the shell's passable runs -
    original openings and broken panels alike - shrink each one by the angle
    the ball itself subtends at that radius, because a hole the ball does not
    fit through was never a chance it missed. Then measure the angular gap from
    the contact angle to the nearest surviving interval.

    It counts as a near miss when either
      (a) that gap is under `near_miss_arc_ball_radii` ball radii of arc, so a
          small difference in *aim* would have passed, or
      (b) the gap divided by the relative angular rate of hole and ball is under
          `near_miss_seconds`, so a small difference in *timing* would have.

    Both thresholds are config and both are reported with the event, along with
    which one fired, so nothing about this is hidden in a constant.
    """
    runs = st.passable_runs()
    if not runs:
        return None
    radius = math.hypot(x, y) or st.apothem
    shrink = math.asin(min(1.0, st.rho / st.radius))
    local = (contact_angle - (st.theta0 + st.omega * t)) % TAU

    best_gap = math.inf
    best_signed = 0.0
    best_centre = 0.0
    best_half = 0.0
    best_slot = -1
    for first, length in runs:
        half = 0.5 * length * st.slot_width - shrink
        if half <= 0.0:
            continue
        centre = (first + 0.5 * length) * st.slot_width
        delta = (local - centre + math.pi) % TAU - math.pi
        gap = abs(delta) - half
        if gap < 0.0:
            gap = 0.0
        if gap < best_gap:
            best_gap = gap
            best_signed = delta
            best_centre = centre
            best_half = half
            best_slot = first
    if best_slot < 0:
        return None

    arc = best_gap * radius
    arc_radii = arc / config.ball_radius if config.ball_radius else math.inf
    ball_rate = (x * vy - y * vx) / (radius * radius)
    relative_rate = st.omega - ball_rate
    if abs(relative_rate) > 1.0e-9:
        time_sep = best_gap / abs(relative_rate)
        # Positive: the hole is still coming. Negative: it has just gone past.
        signed_lead = -best_signed / relative_rate if relative_rate else math.inf
    else:
        time_sep = math.inf
        signed_lead = math.inf

    by_arc = arc_radii <= config.near_miss_arc_ball_radii
    by_time = time_sep <= config.near_miss_seconds
    if not (by_arc or by_time):
        return None
    criterion = "arc+time" if (by_arc and by_time) else ("arc" if by_arc else "time")

    opening_id = st.opening_of_slot.get(best_slot)
    if opening_id is None:
        opening_id = f"s{st.shell_id}b{best_slot}"
    return {
        "opening_id": opening_id,
        "ball_position": (x, y),
        "ball_angle": contact_angle,
        "opening_centre_angle": (st.theta0 + st.omega * t + best_centre) % TAU,
        "opening_half_width": best_half,
        "angular_separation": best_gap,
        "arc_separation": arc,
        "arc_separation_ball_radii": arc_radii,
        "relative_angular_speed": relative_rate,
        "time_separation": time_sep,
        "signed_lead": signed_lead,
        "criterion": criterion,
    }
