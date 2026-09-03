"""How interesting a finished battle looks, on a scale of 0 to 100.

A transparent weighted heuristic, not a model. Every point is traceable to a
named dimension and every dimension to a couple of metrics, because the
question this has to answer during development is not "how good is seed
4471" but "why did seed 4471 beat seed 812". A learned scorer can replace
this once there is real audience data to learn from; until then being
arguable is worth more than being clever.

Two rules keep it honest:

* No mechanism is ever named. Nothing here knows what Echo or Orbit are, so
  the score cannot quietly become a popularity contest between powers. It
  counts *distinct* damage mechanisms, never which ones.
* Every count saturates. A battle with ninety small hits is not nine times
  better than one with ten, so each contribution is a fraction of a cap.
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.battle_metrics import BattleMetrics

# What each dimension is worth. They sum to 100 before penalties.
PACING_WEIGHT = 20.0
SUSPENSE_WEIGHT = 25.0
ACTION_WEIGHT = 20.0
VARIETY_WEIGHT = 10.0
ARENA_WEIGHT = 10.0
PAYOFF_WEIGHT = 15.0

# --- pacing: a Shorts-length fight, neither over before it starts nor
# grinding to the timer. Full marks across a broad plateau, because insisting
# on one exact length would just select for one kind of battle.
PACING_RISE = (4.0, 13.0)
PACING_FALL = (22.0, 34.0)

# --- suspense caps. Measured over 2000 calibration battles: the median
# fight has one lead change and the ninetieth percentile has four, so four is
# where a see-saw is already as gripping as it is going to read. Sixty would
# not be fifteen times as gripping, it would be noise.
LEAD_CHANGE_CAP = 4
COMEBACK_CAP = 45.0

# --- action caps, likewise set from the calibration range rather than
# guessed: hits run 5 to 13 across the tenth to ninety-ninth percentile, and
# activations 2 to 11.
HIT_COUNT_CAP = 12
ACTIVATION_CAP = 8
# Damaging hits per second that reads as a fight rather than a scuffle or a
# blur. Below the first the screen is mostly empty; above the second nothing
# lands with any weight.
HIT_RATE_BAND = (0.30, 1.20)
HIT_RATE_CEILING = 2.6
# A fight that has not started this long in has lost the viewer.
PROMPT_HIT_TIME = 4.0
LATE_HIT_TIME = 12.0

# --- variety caps.
SUBTYPE_CAP = 3

# --- arena engagement. A typical procedural battle touches the scenery far
# more often than first guessed - the median is twenty-eight contacts, the
# ninetieth percentile fifty-five - so caps set any lower than this simply
# award full marks to everyone and measure nothing.
CONTACT_CAP = 45
DISTINCT_OBSTACLE_CAP = 3
KINETIC_CONTACT_CAP = 20
# An arena with nothing in it cannot engage with anything, so it is scored
# neither well nor badly on a dimension it cannot play in. Anything else
# would make the classic arena unrankable rather than merely plainer.
NEUTRAL_ARENA_SCORE = 0.5

# --- payoff.
DECISIVE_GAP = 100.0

# --- penalties, each bounded, and all of them together far short of wiping
# out a good battle by accident.
TIMEOUT_PENALTY = 8.0
SHORT_BATTLE_SECONDS = 5.0
SHORT_BATTLE_PENALTY = 10.0
# The median battle has a six-second quiet stretch in it somewhere, so the
# allowance sits above that: this is for fights that stop happening, not for
# every fight that pauses for breath.
IDLE_GAP_ALLOWANCE = 9.0
IDLE_GAP_PENALTY_CAP = 6.0
MIN_INTERESTING_HITS = 2
NO_ACTION_PENALTY = 8.0
# Phase 5A2 measured rare peaks near 8000 px/s on kinetic arenas. Those are
# not broken - no tunnelling was found - but they look like a glitch, so a
# candidate is nudged down rather than the game being capped.
EXTREME_SPEED_FLOOR = 5000.0
EXTREME_SPEED_SPAN = 3000.0
EXTREME_SPEED_PENALTY = 6.0


@dataclass(frozen=True)
class ScoreBreakdown:
    """A score and the reasons for it."""

    total: float
    pacing: float
    suspense: float
    action: float
    variety: float
    arena: float
    payoff: float
    penalty: float
    penalties: tuple[tuple[str, float], ...]

    @property
    def subtotal(self) -> float:
        """What the dimensions came to before penalties."""
        return (
            self.pacing
            + self.suspense
            + self.action
            + self.variety
            + self.arena
            + self.payoff
        )

    def explain(self, metrics: BattleMetrics) -> str:
        """A human-readable account of where the score came from."""
        lines = [
            f"seed {metrics.seed}  {' vs '.join(metrics.powers)}"
            f"  {metrics.layout_id}",
            f"total {self.total:5.1f} / 100",
            f"  pacing            {self.pacing:5.1f} / {PACING_WEIGHT:<4.0f}"
            f"  duration {metrics.duration:.1f}s",
            f"  suspense          {self.suspense:5.1f} / {SUSPENSE_WEIGHT:<4.0f}"
            f"  lead changes {metrics.lead_changes}"
            f", close {metrics.close_fraction:.0%}"
            f", comeback {metrics.winner_comeback:.0f} HP",
            f"  action            {self.action:5.1f} / {ACTION_WEIGHT:<4.0f}"
            f"  hits {metrics.damaging_hits}"
            f", {metrics.hit_rate:.2f}/s"
            f", activations {metrics.power_activations}"
            f", first hit "
            + (
                "never"
                if metrics.first_hit_time is None
                else f"{metrics.first_hit_time:.1f}s"
            ),
            f"  variety           {self.variety:5.1f} / {VARIETY_WEIGHT:<4.0f}"
            f"  mechanisms {dict(metrics.hits_by_subtype)}",
            f"  arena engagement  {self.arena:5.1f} / {ARENA_WEIGHT:<4.0f}"
            f"  {metrics.obstacle_contacts} contacts on"
            f" {metrics.distinct_obstacles_contacted}/{metrics.obstacles} obstacles"
            f" ({metrics.kinetic_obstacle_contacts} kinetic)",
            f"  payoff            {self.payoff:5.1f} / {PAYOFF_WEIGHT:<4.0f}"
            f"  {'timeout' if metrics.is_timeout else 'elimination'}"
            f", final gap {metrics.final_health_gap:.0f} HP",
        ]
        if self.penalties:
            detail = ", ".join(f"{name} -{value:.1f}" for name, value in self.penalties)
            lines.append(f"  penalties        -{self.penalty:5.1f}       {detail}")
        return "\n".join(lines)


def score_battle(metrics: BattleMetrics) -> ScoreBreakdown:
    """Judge a finished battle. Pure: same metrics, same score, always."""
    pacing = PACING_WEIGHT * _pacing(metrics)
    suspense = SUSPENSE_WEIGHT * _suspense(metrics)
    action = ACTION_WEIGHT * _action(metrics)
    variety = VARIETY_WEIGHT * _variety(metrics)
    arena = ARENA_WEIGHT * _arena(metrics)
    payoff = PAYOFF_WEIGHT * _payoff(metrics)

    penalties = _penalties(metrics)
    penalty = sum(value for _, value in penalties)
    total = pacing + suspense + action + variety + arena + payoff - penalty

    return ScoreBreakdown(
        total=_clamp(total, 0.0, 100.0),
        pacing=pacing,
        suspense=suspense,
        action=action,
        variety=variety,
        arena=arena,
        payoff=payoff,
        penalty=penalty,
        penalties=penalties,
    )


# --- dimensions, each returning 0.0 - 1.0 -----------------------------------


def _pacing(metrics: BattleMetrics) -> float:
    return _plateau(metrics.duration, *PACING_RISE, *PACING_FALL)


def _suspense(metrics: BattleMetrics) -> float:
    """Did the outcome ever look like it might go the other way?"""
    swings = _saturate(metrics.lead_changes, LEAD_CHANGE_CAP)
    closeness = _clamp(metrics.close_fraction, 0.0, 1.0)
    comeback = _saturate(metrics.winner_comeback, COMEBACK_CAP)
    return 0.40 * swings + 0.32 * closeness + 0.28 * comeback


def _action(metrics: BattleMetrics) -> float:
    """Was anything happening, often enough, and soon enough?"""
    volume = _saturate(metrics.damaging_hits, HIT_COUNT_CAP)
    density = _plateau(
        metrics.hit_rate, 0.0, HIT_RATE_BAND[0], HIT_RATE_BAND[1], HIT_RATE_CEILING
    )
    activations = _saturate(metrics.power_activations, ACTIVATION_CAP)
    if metrics.first_hit_time is None:
        promptness = 0.0
    else:
        promptness = 1.0 - _saturate(
            metrics.first_hit_time - PROMPT_HIT_TIME, LATE_HIT_TIME - PROMPT_HIT_TIME
        )
    return 0.40 * volume + 0.25 * density + 0.20 * activations + 0.15 * promptness


def _variety(metrics: BattleMetrics) -> float:
    """Did the battle happen in more than one way?

    Counts distinct damage mechanisms without knowing what any of them are,
    so no power can be worth more than another by name.
    """
    mechanisms = _saturate(metrics.hit_subtypes, SUBTYPE_CAP)
    both_powers = 1.0 if metrics.activating_fighters >= 2 else 0.0
    both_scoring = 1.0 if metrics.damaging_fighters >= 2 else 0.0
    return 0.55 * mechanisms + 0.20 * both_powers + 0.25 * both_scoring


def _arena(metrics: BattleMetrics) -> float:
    """Was the arena it was given actually part of the fight?

    Scored as a fraction of what this particular layout made available: a
    layout with nothing that moves is not marked down for failing to have a
    moving obstacle hit, and an empty arena sits at neutral rather than zero.
    """
    if metrics.obstacles == 0:
        return NEUTRAL_ARENA_SCORE

    parts = [
        _saturate(metrics.obstacle_contacts, CONTACT_CAP),
        _saturate(
            metrics.distinct_obstacles_contacted,
            min(DISTINCT_OBSTACLE_CAP, metrics.obstacles),
        ),
    ]
    if metrics.kinetic_obstacles:
        parts.append(_saturate(metrics.kinetic_obstacle_contacts, KINETIC_CONTACT_CAP))
    return sum(parts) / len(parts)


def _payoff(metrics: BattleMetrics) -> float:
    """Did it end, and did the ending mean anything?"""
    decisive = 0.0 if metrics.is_timeout else 1.0
    closeness = 1.0 - _saturate(metrics.final_health_gap, DECISIVE_GAP)
    comeback = _saturate(metrics.winner_comeback, COMEBACK_CAP)
    return 0.40 * decisive + 0.33 * closeness + 0.27 * comeback


# --- penalties --------------------------------------------------------------


def _penalties(metrics: BattleMetrics) -> tuple[tuple[str, float], ...]:
    """Named, bounded deductions. Nothing here can run away."""
    found: list[tuple[str, float]] = []

    if metrics.is_timeout:
        found.append(("timeout", TIMEOUT_PENALTY))

    if metrics.duration < SHORT_BATTLE_SECONDS:
        shortfall = (SHORT_BATTLE_SECONDS - metrics.duration) / SHORT_BATTLE_SECONDS
        found.append(("too short", SHORT_BATTLE_PENALTY * shortfall))

    idle = metrics.longest_idle_gap - IDLE_GAP_ALLOWANCE
    if idle > 0.0:
        found.append(
            ("idle stretch", min(IDLE_GAP_PENALTY_CAP, idle))
        )

    if metrics.damaging_hits <= MIN_INTERESTING_HITS:
        found.append(("almost no action", NO_ACTION_PENALTY))

    over_speed = metrics.max_fighter_speed - EXTREME_SPEED_FLOOR
    if over_speed > 0.0:
        found.append(
            (
                "extreme speed",
                EXTREME_SPEED_PENALTY * _saturate(over_speed, EXTREME_SPEED_SPAN),
            )
        )

    return tuple(found)


# --- shaping helpers --------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _saturate(value: float, cap: float) -> float:
    """`value` as a fraction of `cap`, never above 1.0 and never below 0."""
    if cap <= 0.0:
        return 0.0
    return _clamp(value / cap, 0.0, 1.0)


def _plateau(value: float, rise_from: float, rise_to: float, fall_from: float,
             fall_to: float) -> float:
    """A trapezoid: 0 below `rise_from`, 1 across the middle, 0 past `fall_to`."""
    if value <= rise_from or value >= fall_to:
        return 0.0
    if value < rise_to:
        return (value - rise_from) / (rise_to - rise_from)
    if value <= fall_from:
        return 1.0
    return (fall_to - value) / (fall_to - fall_from)
