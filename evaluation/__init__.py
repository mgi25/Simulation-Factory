"""Judging finished battles.

Everything here observes a simulation that has already run. Nothing in
`engine`, `modes` or `powers` imports this package, and nothing in a battle
can read a score: a seed plays out exactly the same whether it is being
evaluated or not. That one-way arrow is what makes the factory's taste
changeable without ever touching the game.
"""

from evaluation.battle_metrics import BattleMetrics, collect_metrics, evaluate_seed
from evaluation.battle_score import ScoreBreakdown, score_battle
from evaluation.candidate import Candidate
from evaluation.candidate_curation import CurationConfig, CurationResult, curate

__all__ = [
    "BattleMetrics",
    "Candidate",
    "CurationConfig",
    "CurationResult",
    "ScoreBreakdown",
    "collect_metrics",
    "curate",
    "evaluate_seed",
    "score_battle",
]
