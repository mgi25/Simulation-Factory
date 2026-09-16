"""Research & Intelligence: discovery to a reviewed evidence package.

Read `intelligence/research/README.md` for the workflow. The modules:

    common          ids, `Measurement`, `ResearchConfidence` - the vocabulary
                    every record shares, and the three places research turns
                    into fiction unless something refuses it.
    urls            URL canonicalization behind a platform adapter boundary,
                    and the content identity deduplication runs on.
    provenance      which query found a thing and how it was captured - the
                    vocabulary a candidate and a source both need.
    discovery       `DiscoveryQuery`, `DiscoveryCandidate`, and the screening
                    queue in front of the expensive half of the workflow.
    snapshots       dated public readings, never overwritten, and the private
                    analytics this system refuses to hold.
    ingestion       `IngestionEnvelope` - one validated door for every future
                    connector, and the JSON adapter that works today.
    promotion       the single gate from a screened-in candidate to a source.
    funnel          the six cost tiers, described and never executed.
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
`ingestion` is the boundary a future connector would sit *outside* of - it
validates metadata that already arrived, and it opens nothing.
"""

from intelligence.research.common import (
    Complexity,
    ConfidenceLevel,
    Evidence,
    Measurement,
    ResearchConfidence,
    SourceQuality,
)
from intelligence.research.discovery import (
    CANDIDATE_TRANSITIONS,
    TERMINAL_CANDIDATE_STATES,
    CandidateState,
    DiscoveryCandidate,
    DiscoveryQuery,
    QueryStatus,
    ScreeningDecision,
    assert_screening,
    can_screen,
    candidate_conflicts,
    excluded_by,
    merge_candidates,
    queue_candidate,
    screen_candidate,
    within_freshness,
)
from intelligence.research.errors import ResearchError
from intelligence.research.funnel import (
    TIERS,
    CostTier,
    TierSpec,
    describe_funnel,
    next_tier,
    tier_of_candidate,
    tier_of_source,
)
from intelligence.research.ingestion import (
    PUBLIC_VIDEO_PAYLOAD,
    Ingested,
    IngestionEnvelope,
    candidate_id_for,
    envelopes_from_json,
    ingest_envelope,
    load_envelopes,
    payload_schema_for,
    register_payload_schema,
    unregister_payload_schema,
    validate_payload,
)
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
from intelligence.research.promotion import PromotionResult, promote_candidate
from intelligence.research.provenance import (
    CaptureMethod,
    DiscoveryOrigin,
    DiscoveryProvenance,
    merge_provenance,
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
from intelligence.research.snapshots import (
    PRIVATE_METRIC_FIELDS,
    PublicGrowth,
    PublicSnapshot,
    SnapshotSeries,
    assert_public_metric_name,
    growth_between,
    series_id,
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
    IngestionOutcome,
    IntegrityIssue,
    ResearchStore,
    stale_records,
)
from intelligence.research.urls import (
    MAX_URL_CHARS,
    YOUTUBE_ID,
    CanonicalUrl,
    ContentIdentity,
    ParsedUrl,
    PlatformAdapter,
    YouTubeAdapter,
    adapter_for,
    assert_known_platform,
    canonicalize,
    identity_of,
    known_platforms,
    parse_url,
    register_adapter,
    unregister_adapter,
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
    "CANDIDATE_TRANSITIONS",
    "CAVEAT",
    "COPY_STATUSES",
    "CameraEditAnalysis",
    "CandidateState",
    "CanonicalUrl",
    "CaptureMethod",
    "Complexity",
    "ConfidenceLevel",
    "ContentIdentity",
    "CoreLoop",
    "CostTier",
    "DEFAULT_ROOT",
    "DIRECTORIES",
    "DerivedMetrics",
    "DimensionScore",
    "DiscoveryCandidate",
    "DiscoveryOrigin",
    "DiscoveryProvenance",
    "DiscoveryQuery",
    "DossierStatus",
    "Evidence",
    "ExperimentDefinition",
    "FAMILY_REQUIRED",
    "FormatAnalysis",
    "FormatClass",
    "FormatFamily",
    "HookAnalysis",
    "Ingested",
    "IngestionEnvelope",
    "IngestionOutcome",
    "IntegrityIssue",
    "KNOWN_DIMENSIONS",
    "KNOWN_MECHANICS",
    "KNOWN_SUPERIORITY_DIMENSIONS",
    "MAX_URL_CHARS",
    "Measurement",
    "NEVER_KNOWABLE",
    "OpportunityDossier",
    "OpportunityScorecard",
    "OpportunityStage",
    "OriginalityBoundary",
    "PRIVATE_METRIC_FIELDS",
    "PUBLIC_VIDEO_PAYLOAD",
    "ParsedUrl",
    "PlatformAdapter",
    "PromotionResult",
    "PublicGrowth",
    "PublicMetrics",
    "PublicSnapshot",
    "QueryStatus",
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
    "ScreeningDecision",
    "SnapshotSeries",
    "SourceQuality",
    "SourceType",
    "StageTransition",
    "SuperiorityTarget",
    "TERMINAL_CANDIDATE_STATES",
    "TERMINAL_STAGES",
    "TIERS",
    "TargetStatus",
    "TechnicalAnalysis",
    "TierSpec",
    "VideoIntelligenceDossier",
    "VideoPlan",
    "ViewerPsychology",
    "VisualAnalysis",
    "YOUTUBE_ID",
    "YouTubeAdapter",
    "adapter_for",
    "advance_source",
    "assert_known_platform",
    "assert_public_metric_name",
    "assert_screening",
    "assert_transition",
    "can_screen",
    "can_transition",
    "candidate_conflicts",
    "candidate_id_for",
    "canonicalize",
    "derive",
    "describe_funnel",
    "envelopes_from_json",
    "excluded_by",
    "growth_between",
    "identity_of",
    "ingest_envelope",
    "known_platforms",
    "link_opportunity",
    "link_reference_case",
    "load_envelopes",
    "merge_candidates",
    "merge_provenance",
    "next_tier",
    "observation_evidence",
    "parse_url",
    "payload_schema_for",
    "promote_candidate",
    "queue_candidate",
    "rank",
    "register_adapter",
    "register_payload_schema",
    "score_all",
    "score_opportunity",
    "screen_candidate",
    "series_id",
    "stale_records",
    "tier_of_candidate",
    "tier_of_source",
    "unregister_adapter",
    "unregister_payload_schema",
    "validate_payload",
    "within_freshness",
]
