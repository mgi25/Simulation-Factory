"""One evaluated battle: what happened, and what it scored.

Small enough to live on its own, and it does, because both the search that
produces candidates and the curation that picks between them need it and
neither should have to import the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.battle_metrics import BattleMetrics
from evaluation.battle_score import ScoreBreakdown


@dataclass(frozen=True)
class Candidate:
    """One evaluated battle: its metrics and what they scored."""

    metrics: BattleMetrics
    score: ScoreBreakdown

    @property
    def rank_key(self) -> tuple[float, int]:
        """Best first, and ties broken by seed so ordering is total."""
        return (-self.score.total, self.metrics.seed)
