"""Research & Intelligence: discovery to a reviewed evidence package.

Read `intelligence/research/README.md` for the workflow. The modules:

    common          ids, `Measurement`, `ResearchConfidence` - the vocabulary
                    every record shares, and the three places research turns
                    into fiction unless something refuses it.
    sources         `ResearchSource`, `RightsStatus`, `PublicMetrics`, and a
                    derivation that leaves missing data missing.
    reference_case  a structured reading of somebody else's video, with a
                    mandatory originality boundary (constitution rule 8).
    opportunity     `OpportunityDossier`, format-family classification, and
                    superiority targets that may say "not measured yet".
    scoring         explicit dimensions, explicit weights, deterministic ties,
                    and a composite that cannot travel without its caveat.
    lifecycle       the seven-stage research workflow and its artefact gates.
    video_dossier   the per-video research template (section 12). Data model
                    only - nothing here is connected to production.
    store           a directory of JSON files, and cross-record integrity.

This package imports `ai_platform` and `knowledge.company_os`, and nothing else
outside the standard library. Nothing in production imports it. It performs no
network access: there is no client, no scraper, no downloader and no model.
"""

from intelligence.research.common import (
    Complexity,
    ConfidenceLevel,
    Evidence,
    Measurement,
    ResearchConfidence,
    SourceQuality,
)
from intelligence.research.errors import ResearchError
from intelligence.research.lifecycle import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STAGES,
    ResearchStage,
    StageTransition,
    advance_source,
    assert_transition,
    can_transition,
    link_opportunity,
    link_reference_case,
)
from intelligence.research.opportunity import (
    FAMILY_REQUIRED,
    KNOWN_SUPERIORITY_DIMENSIONS,
    FormatClass,
    FormatFamily,
    OpportunityDossier,
    OpportunityStage,
    SuperiorityTarget,
    TargetStatus,
)
from intelligence.research.reference_case import (
    KNOWN_MECHANICS,
    AudioAnalysis,
    CameraEditAnalysis,
    CoreLoop,
    FormatAnalysis,
    HookAnalysis,
    OriginalityBoundary,
    ReferenceCase,
    TechnicalAnalysis,
    ViewerPsychology,
    VisualAnalysis,
)
from intelligence.research.scoring import (
    CAVEAT,
    KNOWN_DIMENSIONS,
    DimensionScore,
    OpportunityScorecard,
    ScoreResult,
    ScoringDimension,
    ScoringRubric,
    rank,
    score_all,
    score_opportunity,
)
from intelligence.research.sources import (
    COPY_STATUSES,
    NEVER_KNOWABLE,
    DerivedMetrics,
    PublicMetrics,
    ResearchSource,
    RightsStatus,
    SourceType,
    derive,
    observation_evidence,
)
from intelligence.research.store import (
    DEFAULT_ROOT,
    DIRECTORIES,
    RECORD_TYPES,
    IntegrityIssue,
    ResearchStore,
    stale_records,
)
from intelligence.research.video_dossier import (
    DossierStatus,
    ExperimentDefinition,
    VideoIntelligenceDossier,
    VideoPlan,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "AudioAnalysis",
    "CAVEAT",
    "COPY_STATUSES",
    "CameraEditAnalysis",
    "Complexity",
    "ConfidenceLevel",
    "CoreLoop",
    "DEFAULT_ROOT",
    "DIRECTORIES",
    "DerivedMetrics",
    "DimensionScore",
    "DossierStatus",
    "Evidence",
    "ExperimentDefinition",
    "FAMILY_REQUIRED",
    "FormatAnalysis",
    "FormatClass",
    "FormatFamily",
    "HookAnalysis",
    "IntegrityIssue",
    "KNOWN_DIMENSIONS",
    "KNOWN_MECHANICS",
    "KNOWN_SUPERIORITY_DIMENSIONS",
    "Measurement",
    "NEVER_KNOWABLE",
    "OpportunityDossier",
    "OpportunityScorecard",
    "OpportunityStage",
    "OriginalityBoundary",
    "PublicMetrics",
    "RECORD_TYPES",
    "ReferenceCase",
    "ResearchConfidence",
    "ResearchError",
    "ResearchSource",
    "ResearchStage",
    "ResearchStore",
    "RightsStatus",
    "ScoreResult",
    "ScoringDimension",
    "ScoringRubric",
    "SourceQuality",
    "SourceType",
    "StageTransition",
    "SuperiorityTarget",
    "TERMINAL_STAGES",
    "TargetStatus",
    "TechnicalAnalysis",
    "VideoIntelligenceDossier",
    "VideoPlan",
    "ViewerPsychology",
    "VisualAnalysis",
    "advance_source",
    "assert_transition",
    "can_transition",
    "derive",
    "link_opportunity",
    "link_reference_case",
    "observation_evidence",
    "rank",
    "score_all",
    "score_opportunity",
    "stale_records",
]
