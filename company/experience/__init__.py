"""The experience store: operational episode history, indexed for precedent.

    capture   settled engineering attempt  -> immutable episode (pointers + projections)
    retrieve  current work order           -> accepted precedent, correction warnings, or abstain
    advise    retrieval + current authority + current repository -> bounded advisory artifact

Experience is not knowledge. The knowledge store (`knowledge.company_os`) holds
curated claims - facts, hypotheses, decisions, experiment and failure
learnings - each an explicit semantic act by someone accountable for it. This
package holds operational history: what was attempted, what came back, how it
was judged. Nothing here writes a knowledge record, and an episode never
becomes a Fact, a Decision or a FailureLearning by being stored. Promoting a
pattern seen in experience into knowledge remains a separate, deliberate act.

Experience is not authority either. See `advice.py` for how the one artifact
this package emits is kept unable to grant, widen, skip or approve anything.

Nothing in Company OS depends on this package; it depends on the engineering,
runtime, efficiency and capsule layers and on P6B's import graph, and its only
consumer is the external runner, over a command line.
"""

from .advice import (
    ADVICE_KEYS,
    ADVICE_KIND,
    ADVICE_VERSION,
    AUTHORITY_KEYS,
    assert_no_authority_keys,
    build_advice,
    unavailable_advice,
)
from .capture import (
    REFUSAL_CODES,
    AttemptCycle,
    CaptureReport,
    GovernanceFacts,
    attempt_cycles,
    build_episode,
    capture_settled,
    governance_facts,
    governed_class,
    verify_pointers,
)
from .errors import CaptureRefused, ExperienceConflict, ExperienceError
from .model import (
    DECISION_TIME_FIELDS,
    EPISODE_SCHEMA_VERSION,
    OUTCOME_FIELDS,
    ChosenAction,
    DecisionFeatures,
    EvidenceBasis,
    ExperienceEpisode,
    Measurement,
    ObservedOutcome,
    PrecedentClass,
    RecordPointer,
    ResourceObservation,
    ScopeProvenance,
    assert_decision_time_only,
    chosen_action,
    decision_features,
    verify_features,
)
from .repository import RepositoryView, Validity, ValidityReport, contract_digest, evaluate_validity
from .retrieval import ABSTENTION_CODES, ExperienceQuery, RetrievalResult, retrieve, retrieve_from
from .store import ExperienceStore, StoreScan
from .training import training_row

__all__ = [
    "ABSTENTION_CODES",
    "ADVICE_KEYS",
    "ADVICE_KIND",
    "ADVICE_VERSION",
    "AUTHORITY_KEYS",
    "DECISION_TIME_FIELDS",
    "EPISODE_SCHEMA_VERSION",
    "OUTCOME_FIELDS",
    "REFUSAL_CODES",
    "AttemptCycle",
    "CaptureRefused",
    "CaptureReport",
    "ChosenAction",
    "DecisionFeatures",
    "EvidenceBasis",
    "ExperienceConflict",
    "ExperienceEpisode",
    "ExperienceError",
    "ExperienceQuery",
    "ExperienceStore",
    "GovernanceFacts",
    "Measurement",
    "ObservedOutcome",
    "PrecedentClass",
    "RecordPointer",
    "RepositoryView",
    "ResourceObservation",
    "RetrievalResult",
    "ScopeProvenance",
    "StoreScan",
    "Validity",
    "ValidityReport",
    "assert_decision_time_only",
    "assert_no_authority_keys",
    "attempt_cycles",
    "build_advice",
    "build_episode",
    "capture_settled",
    "chosen_action",
    "contract_digest",
    "decision_features",
    "evaluate_validity",
    "governance_facts",
    "governed_class",
    "retrieve",
    "retrieve_from",
    "training_row",
    "unavailable_advice",
    "verify_features",
    "verify_pointers",
]
