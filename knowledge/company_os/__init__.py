"""Company OS knowledge: five record types, a decay model, and a file store.

Read `knowledge/company_os/README.md` for the record shapes; the modules are:

    records    Fact, Hypothesis, Decision, ExperimentLearning, FailureLearning -
               five siblings with no inheritance, so a guess cannot be stored
               in the shape of a fact (constitution rule 16).
    freshness  Four decay classes and the staleness arithmetic over them.
    ledger     KnowledgeStore (a directory of JSON files) and DecisionLedger.

This package imports `ai_platform` for its reference guard and canonical JSON,
and nothing else outside the standard library. Nothing in production imports
either package.
"""

from knowledge.company_os.freshness import (
    DEFAULT_RECHECK_DAYS,
    REVALIDATION_CLASSES,
    Freshness,
    days_until_recheck,
    default_recheck_on,
    is_stale,
)
from knowledge.company_os.ledger import (
    DEFAULT_ROOT,
    DecisionLedger,
    KnowledgeStore,
    stale_records,
)
from knowledge.company_os.records import (
    DECAYING_TYPES,
    RECORD_TYPES,
    Alternative,
    Decision,
    DecisionStatus,
    Evidence,
    ExperimentLearning,
    Fact,
    FailureLearning,
    Hypothesis,
    HypothesisStatus,
    KnowledgeError,
    KnowledgeRecord,
    RecordStatus,
    flag_for_revalidation,
    promote,
)

__all__ = [
    "DECAYING_TYPES",
    "DEFAULT_RECHECK_DAYS",
    "DEFAULT_ROOT",
    "RECORD_TYPES",
    "REVALIDATION_CLASSES",
    "Alternative",
    "Decision",
    "DecisionLedger",
    "DecisionStatus",
    "Evidence",
    "ExperimentLearning",
    "Fact",
    "FailureLearning",
    "Freshness",
    "Hypothesis",
    "HypothesisStatus",
    "KnowledgeError",
    "KnowledgeRecord",
    "KnowledgeStore",
    "RecordStatus",
    "days_until_recheck",
    "default_recheck_on",
    "flag_for_revalidation",
    "is_stale",
    "promote",
    "stale_records",
]
