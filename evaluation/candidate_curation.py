"""Turning a ranked list of battles into a batch worth publishing.

Ranking by score answers "which battles are good". It does not answer "which
twenty should go out this week", because the best twenty by score can easily
be twelve Pulse fights of much the same length on much the same arena. Every
one of them is a good battle and the set is a bad batch.

So this is a second stage, on purpose. `score_battle` still measures nothing
but a battle's own quality, and knows nothing about what else was picked;
everything about variety lives here. Keeping them apart is what lets the
batch rules change - a different size, a looser cap, a new constraint -
without the meaning of a score moving underneath them.

The algorithm is a plain deterministic greedy pass down the ranking: take
the best candidate that clears the production floor, does not overfill a
quota and does not look like something already chosen, and repeat. Greedy is
not optimal, but it is explainable, and every rejection is counted and
reported so a batch can be argued with.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from evaluation.candidate import Candidate

# --- production floor. A batch is not a survey: a candidate that is merely
# above average has no business in one, so the default sits near the top
# tenth of the measured distribution rather than at its middle.
DEFAULT_MIN_SCORE = 80.0
# Publishing rules rather than scoring ones. The score already marks a
# three-second battle down; this refuses to ship it at all.
DEFAULT_MIN_DURATION = 7.0
# Above this a fighter is moving fast enough to read as a glitch even though
# phase 5A2 proved nothing is actually wrong. Not a gameplay cap - the battle
# is simulated exactly as always, it just does not get published.
DEFAULT_MAX_SPEED = 7000.0

# --- diversity caps, all expressed as a share of the batch so they mean the
# same thing whatever its size.
DEFAULT_MATCHUP_SHARE = 0.10
DEFAULT_MIRROR_SHARE = 0.15
DEFAULT_MOTION_SHARE = 0.60
# Each battle contributes two power appearances, so this is a share of twice
# the batch size. Loose on purpose: the point is to stop one power owning the
# batch, not to hand out equal quotas to powers that did not earn them.
DEFAULT_POWER_SHARE = 0.40

# --- near-duplicate rule. Two battles are compared on six coarse signals
# beyond sharing a matchup; agreeing on this many means they would look like
# the same video twice.
DEFAULT_SIMILARITY_THRESHOLD = 4
SIMILAR_DURATION = 2.5
SIMILAR_HITS = 2
SIMILAR_LEAD_CHANGES = 1
SIMILAR_SCORE = 3.0

# Why a candidate did not make it. Ordered as they are tested.
REJECT_SCORE = "score"
REJECT_TIMEOUT = "timeout"
REJECT_DRAW = "draw"
REJECT_DURATION = "duration"
REJECT_SPEED = "speed"
REJECT_INVALID = "invalid state"
REJECT_LEAKED = "leaked state"
REJECT_MATCHUP = "matchup cap"
REJECT_POWER = "power cap"
REJECT_MIRROR = "mirror cap"
REJECT_ENVIRONMENT = "environment repetition"
REJECT_SIMILAR = "similarity"

REJECT_REASONS: tuple[str, ...] = (
    REJECT_SCORE,
    REJECT_TIMEOUT,
    REJECT_DRAW,
    REJECT_DURATION,
    REJECT_SPEED,
    REJECT_INVALID,
    REJECT_LEAKED,
    REJECT_MATCHUP,
    REJECT_POWER,
    REJECT_MIRROR,
    REJECT_ENVIRONMENT,
    REJECT_SIMILAR,
)

# How a layout's motion is classed for diversity purposes.
MOTION_CLASSES: tuple[str, ...] = ("static", "one kinetic", "two kinetic")


def matchup_key(powers: Sequence[str]) -> tuple[str, ...]:
    """A matchup without its sides. Rush/Titan and Titan/Rush are one thing.

    Which fighter got which power is still in the candidate and still gets
    rendered; it is only for counting variety that the pair is unordered.
    """
    return tuple(sorted(powers))


def is_mirror(powers: Sequence[str]) -> bool:
    return len(set(powers)) == 1


def motion_class(kinetic_obstacles: int) -> str:
    """Which broad kind of arena this was: still, or how much of it moved."""
    if kinetic_obstacles <= 0:
        return MOTION_CLASSES[0]
    if kinetic_obstacles == 1:
        return MOTION_CLASSES[1]
    return MOTION_CLASSES[2]


def winner_power(candidate: Candidate) -> str | None:
    metrics = candidate.metrics
    if metrics.winner_id is None or metrics.winner_id >= len(metrics.powers):
        return None
    return metrics.powers[metrics.winner_id]


@dataclass(frozen=True)
class CurationConfig:
    """Everything the curator is allowed to decide with.

    Caps are shares of the batch rather than counts, so the same
    configuration behaves sensibly for a batch of eight or eighty.
    """

    size: int = 20
    min_score: float = DEFAULT_MIN_SCORE
    min_duration: float = DEFAULT_MIN_DURATION
    max_speed: float = DEFAULT_MAX_SPEED
    matchup_share: float = DEFAULT_MATCHUP_SHARE
    power_share: float = DEFAULT_POWER_SHARE
    mirror_share: float = DEFAULT_MIRROR_SHARE
    motion_share: float = DEFAULT_MOTION_SHARE
    similarity_threshold: int = DEFAULT_SIMILARITY_THRESHOLD

    def cap(self, share: float, of: int | None = None) -> int:
        """A share of the batch as a whole number, never less than one."""
        total = self.size if of is None else of
        return max(1, round(share * total))

    @property
    def matchup_cap(self) -> int:
        return self.cap(self.matchup_share)

    @property
    def mirror_cap(self) -> int:
        return self.cap(self.mirror_share)

    @property
    def motion_cap(self) -> int:
        return self.cap(self.motion_share)

    @property
    def power_cap(self) -> int:
        # Two powers per battle, so the pool of appearances is twice the size.
        return self.cap(self.power_share, of=2 * self.size)


@dataclass
class CurationResult:
    """A finished batch, and an account of everything left out of it."""

    selected: list[Candidate] = field(default_factory=list)
    rejected: Counter[str] = field(default_factory=Counter)
    above_floor: int = 0
    considered: int = 0

    @property
    def size(self) -> int:
        return len(self.selected)

    def shortfall(self, requested: int) -> int:
        return max(0, requested - self.size)

    def reason_for_shortfall(self, requested: int) -> str | None:
        """Why the batch came up short, in one sentence, or None if it did not.

        Coming up short is a real answer: the alternative is quietly dropping
        the quality floor to fill a quota, which is how a batch ends up with
        battles nobody wanted to watch.
        """
        if self.shortfall(requested) == 0:
            return None
        if self.above_floor < requested:
            return (
                f"only {self.above_floor} of {self.considered} candidates cleared"
                f" the quality floor, so {self.size} could be selected rather"
                f" than {requested}; widen the seed range or lower --min-score"
                " deliberately"
            )
        blocking = ", ".join(
            f"{name} {count}"
            for name, count in self.rejected.most_common()
            if name not in (REJECT_SCORE,) and count
        )
        return (
            f"{self.above_floor} candidates cleared the quality floor but"
            f" diversity rules left only {self.size} of {requested}"
            f" ({blocking})"
        )


def similarity_signals(first: Candidate, second: Candidate) -> tuple[str, ...]:
    """Which coarse features two candidates of the same matchup share.

    Deliberately a handful of named, comparable facts rather than a distance
    in some learned space: a rejection has to be explainable as "same
    matchup, same arena shape, same length, same winner".
    """
    left, right = first.metrics, second.metrics
    signals: list[str] = []
    if abs(left.duration - right.duration) <= SIMILAR_DURATION:
        signals.append("duration")
    if winner_power(first) == winner_power(second):
        signals.append("winner")
    if left.layout_shape == right.layout_shape:
        signals.append("arena")
    if abs(left.damaging_hits - right.damaging_hits) <= SIMILAR_HITS:
        signals.append("hits")
    if abs(left.lead_changes - right.lead_changes) <= SIMILAR_LEAD_CHANGES:
        signals.append("lead changes")
    if abs(first.score.total - second.score.total) <= SIMILAR_SCORE:
        signals.append("score")
    return tuple(signals)


def is_near_duplicate(
    first: Candidate, second: Candidate, threshold: int = DEFAULT_SIMILARITY_THRESHOLD
) -> bool:
    """True when two candidates would read as the same video twice.

    Sharing a matchup is a precondition, not a signal: two different
    matchups put different colours, powers and effects on screen, so they
    never look like each other however alike their numbers are. Among
    battles of the same matchup, enough coarse agreement means duplicate -
    which still leaves room for two Rush-versus-Titan fights when one is a
    short comeback round a rotor and the other a long close one behind a gate.
    """
    if matchup_key(first.metrics.powers) != matchup_key(second.metrics.powers):
        return False
    return len(similarity_signals(first, second)) >= threshold


def _production_rejection(candidate: Candidate, config: CurationConfig) -> str | None:
    """Why this battle cannot be published at all, regardless of the batch."""
    metrics = candidate.metrics
    if candidate.score.total < config.min_score:
        return REJECT_SCORE
    if metrics.is_timeout:
        return REJECT_TIMEOUT
    if metrics.is_draw:
        return REJECT_DRAW
    if metrics.duration < config.min_duration:
        return REJECT_DURATION
    if metrics.max_fighter_speed > config.max_speed:
        return REJECT_SPEED
    if not metrics.state_valid:
        return REJECT_INVALID
    if metrics.entities_leaked:
        return REJECT_LEAKED
    return None


def curate(
    candidates: Iterable[Candidate], config: CurationConfig | None = None
) -> CurationResult:
    """Pick a diverse batch from a pool, best first.

    One deterministic pass down the ranking. Order in equals order out: the
    pool is sorted by score and then by seed, so the same pool and the same
    configuration always produce the same batch, whoever ran it and however
    the evaluation was parallelised.
    """
    config = config or CurationConfig()
    pool = sorted(candidates, key=lambda candidate: candidate.rank_key)

    result = CurationResult(considered=len(pool))
    matchups: Counter[tuple[str, ...]] = Counter()
    powers: Counter[str] = Counter()
    motions: Counter[str] = Counter()
    mirrors = 0

    for candidate in pool:
        blocked = _production_rejection(candidate, config)
        if blocked is not None:
            result.rejected[blocked] += 1
            continue

        # Everything from here on cleared production; it is only the shape of
        # the batch so far that can turn it away.
        result.above_floor += 1
        if result.size >= config.size:
            continue

        metrics = candidate.metrics
        key = matchup_key(metrics.powers)
        motion = motion_class(metrics.kinetic_obstacles)

        if matchups[key] >= config.matchup_cap:
            result.rejected[REJECT_MATCHUP] += 1
            continue
        if is_mirror(metrics.powers) and mirrors >= config.mirror_cap:
            result.rejected[REJECT_MIRROR] += 1
            continue
        # What the count would become, not where it already stands: a mirror
        # matchup brings two appearances of one power at once, so testing the
        # running total alone lets it step over the cap by one.
        appearances = Counter(metrics.powers)
        if any(
            powers[power] + count > config.power_cap
            for power, count in appearances.items()
        ):
            result.rejected[REJECT_POWER] += 1
            continue
        if motions[motion] >= config.motion_cap:
            result.rejected[REJECT_ENVIRONMENT] += 1
            continue
        if any(
            is_near_duplicate(candidate, chosen, config.similarity_threshold)
            for chosen in result.selected
        ):
            result.rejected[REJECT_SIMILAR] += 1
            continue

        result.selected.append(candidate)
        matchups[key] += 1
        motions[motion] += 1
        powers.update(appearances)
        if is_mirror(metrics.powers):
            mirrors += 1

    return result


def summarise(selected: Sequence[Candidate]) -> dict:
    """The shape of a finished batch, for reporting and for the manifest."""
    if not selected:
        return {
            "count": 0,
            "score": {},
            "duration": {},
            "powers": {},
            "matchups": {},
            "mirrors": 0,
            "motion": {},
            "unique_matchups": 0,
        }

    scores = sorted(c.score.total for c in selected)
    durations = sorted(c.metrics.duration for c in selected)
    powers: Counter[str] = Counter()
    matchups: Counter[str] = Counter()
    motions: Counter[str] = Counter()
    for candidate in selected:
        for power in candidate.metrics.powers:
            powers[power] += 1
        matchups[" vs ".join(matchup_key(candidate.metrics.powers))] += 1
        motions[motion_class(candidate.metrics.kinetic_obstacles)] += 1

    return {
        "count": len(selected),
        "score": {
            "min": round(scores[0], 3),
            "mean": round(sum(scores) / len(scores), 3),
            "max": round(scores[-1], 3),
        },
        "duration": {
            "min": round(durations[0], 3),
            "median": round(durations[len(durations) // 2], 3),
            "max": round(durations[-1], 3),
        },
        "timeouts": sum(1 for c in selected if c.metrics.is_timeout),
        "powers": dict(sorted(powers.items())),
        "matchups": dict(sorted(matchups.items())),
        "unique_matchups": len(matchups),
        "mirrors": sum(1 for c in selected if is_mirror(c.metrics.powers)),
        "motion": {name: motions.get(name, 0) for name in MOTION_CLASSES},
    }


def count_near_duplicates(
    selected: Sequence[Candidate], threshold: int = DEFAULT_SIMILARITY_THRESHOLD
) -> int:
    """How many pairs in a set would read as the same video twice."""
    return sum(
        1
        for index, first in enumerate(selected)
        for second in selected[index + 1 :]
        if is_near_duplicate(first, second, threshold)
    )
