"""The shape a future decision model would read - and the line it may not cross.

No model is built here, trained here, or called here. This module exists so
the data the experience store already holds can be read as training or
evaluation rows *later* without anyone having to rediscover which columns
were known when.

A row has two halves that must never be confused:

    inputs   features        decision time only - checked by assert_decision_time_only
    labels   action, outcome, resources, classes, provenance

`action` sits on the label side for a recommender and may sit on the input
side for an outcome predictor; the row keeps it separate so either can be
built without re-deriving the split.

## What is honestly absent

There is no `model_version` and no recommendation column with values in it.
Nothing produced a recommendation for any historical attempt - the advisory
did not exist - so `recommendation.recorded` is `False` and says why. A slot
filled with a made-up version string would be exactly the fabricated field the
brief forbids. The schema versions that *do* exist are reported.
"""

from __future__ import annotations

from typing import Any

from ai_platform.serde import to_jsonable

from .capture import GovernanceFacts, governed_class
from .model import (
    ACTION_SCHEMA_VERSION,
    EPISODE_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    OUTCOME_SCHEMA_VERSION,
    EvidenceBasis,
    ExperienceEpisode,
    assert_decision_time_only,
)


def training_row(episode: ExperienceEpisode, governance: GovernanceFacts | None = None) -> dict[str, Any]:
    """One row, with the decision-time inputs checked before they are handed out."""
    features = to_jsonable(episode.features)
    assert_decision_time_only(features)
    klass, reasons = (
        governed_class(episode, governance)
        if governance is not None and governance.available
        else (episode.engineering_class(), ())
    )
    resources = to_jsonable(episode.resources)
    return {
        "experience_id": episode.experience_id,
        "decided_on": episode.decided_on.isoformat(),
        "settled_on": episode.settled_on.isoformat(),
        "inputs": {"features": features},
        "labels": {
            "action": to_jsonable(episode.action),
            "outcome": to_jsonable(episode.outcome),
            "resources": resources,
            "engineering_class": episode.engineering_class().value,
            "governed_class": klass.value,
            "governance_reasons": list(reasons),
            "governance_joined": governance is not None and governance.available,
        },
        "basis": {
            "outcome": EvidenceBasis.OBSERVED.value,
            "tokens": resources["tokens_basis"],
            "cost": resources["cost_basis"],
            "duration": resources["duration_basis"],
        },
        "provenance": {
            "evidence": [to_jsonable(p) for p in episode.evidence],
            "captured_on": episode.provenance.captured_on.isoformat(),
            "source": episode.source,
        },
        "schema_versions": {
            "episode": EPISODE_SCHEMA_VERSION,
            "features": FEATURE_SCHEMA_VERSION,
            "action": ACTION_SCHEMA_VERSION,
            "outcome": OUTCOME_SCHEMA_VERSION,
        },
        "recommendation": {
            "recorded": False,
            "reason": "no recommender existed when this attempt was decided; nothing is invented to fill the slot",
        },
    }


__all__ = ["training_row"]
