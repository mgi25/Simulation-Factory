"""Focused tests for the Company OS research ingestion & discovery boundary.

Phase 3 stored research. This layer is what stands between a link somebody
pasted and that store, and almost every invariant worth a test here is a
refusal:

- a URL is canonicalized or rejected, never guessed at;
- five spellings of one video are one candidate, and a title never merges two;
- a video found by three queries keeps all three;
- a public metric that was not observed stays missing, and is never zero;
- retention, revenue, RPM and traffic sources cannot enter by any key;
- a reading is never overwritten by a later reading of the same page;
- a screened-out candidate cannot become a `ResearchSource` by any argument;
- nothing in the ingestion path can produce a local media copy.

Plus the branch guards: no production import in either direction, no new
dependency, no network, and rule 2 exactly where it was.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from ai_platform import ExecutionPolicy, SubagentPolicyViolation
from ai_platform.references import ReferenceViolation
from ai_platform.serde import dumps
from company.validation.errors import ValidationError
from company.validation.no_subagents import enforce_no_subagents
from intelligence.research import (
    PRIVATE_METRIC_FIELDS,
    PUBLIC_VIDEO_PAYLOAD,
    TIERS,
    CandidateState,
    CaptureMethod,
    ConfidenceLevel,
    ContentIdentity,
    CostTier,
    DiscoveryCandidate,
    DiscoveryProvenance,
    DiscoveryQuery,
    Evidence,
    IngestionEnvelope,
    PlatformAdapter,
    PublicMetrics,
    PublicSnapshot,
    ResearchConfidence,
    ResearchError,
    ResearchStage,
    ResearchStore,
    RightsStatus,
    SnapshotSeries,
    SourceQuality,
    SourceType,
    canonicalize,
    candidate_conflicts,
    describe_funnel,
    excluded_by,
    growth_between,
    identity_of,
    ingest_envelope,
    known_platforms,
    load_envelopes,
    merge_candidates,
    next_tier,
    parse_url,
    promote_candidate,
    queue_candidate,
    register_adapter,
    screen_candidate,
    series_id,
    tier_of_candidate,
    tier_of_source,
    unregister_adapter,
    validate_payload,
    within_freshness,
)
from intelligence.research.urls import CanonicalUrl
from knowledge.company_os import Freshness
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.budget import DEFAULT_BUDGET

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "intelligence"
SEED_ROOT = REPO_ROOT / "knowledge" / "company_os" / "capsules" / "seeds"

TODAY = dt.date(2026, 9, 16)
VIDEO = "dQw4w9WgXcQ"
WATCH = f"https://www.youtube.com/watch?v={VIDEO}"


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def an_evidence(**overrides) -> Evidence:
    data = dict(
        kind="observation",
        ref="docs/validation/discovery/2026-09-16-marble-race.md",
        note="read off the public page",
    )
    data.update(overrides)
    return Evidence(**data)


def a_query(**overrides) -> DiscoveryQuery:
    data = dict(
        id="dq-marble-race",
        platform="youtube",
        objective="Find marble-race formats whose loop renews without narration.",
        terms=("marble race", "country marble race"),
        created=TODAY,
        author="research_opportunity_lead",
        mechanic_tags=("race", "elimination"),
        freshness_days=180,
        max_candidates=40,
        exclusions=("compilation",),
    )
    data.update(overrides)
    return DiscoveryQuery(**data)


def a_provenance(**overrides) -> DiscoveryProvenance:
    data = dict(query_id="dq-marble-race", discovered_on=TODAY, rank=3)
    data.update(overrides)
    return DiscoveryProvenance(**data)


def a_candidate(**overrides) -> DiscoveryCandidate:
    canonical = canonicalize(overrides.pop("url", f"https://youtu.be/{VIDEO}"))
    data = dict(
        id="cand-marble-mountain",
        platform=canonical.platform,
        original_url=canonical.original,
        canonical_url=canonical.url,
        external_id=canonical.external_id,
        discovered_on=TODAY,
        discovered_by="research_opportunity_lead",
        capture_method=CaptureMethod.MANUAL_BROWSER,
        evidence=an_evidence(),
        provenance=(a_provenance(),),
        title="A marble race down a mountain",
        creator="Some Channel",
        published_on=dt.date(2026, 8, 1),
        duration_seconds=184,
        tags=("race",),
    )
    data.update(overrides)
    return DiscoveryCandidate(**data)


def a_snapshot(**overrides) -> PublicSnapshot:
    metrics = overrides.pop(
        "metrics",
        PublicMetrics(observed_on=TODAY, views=1_204_300, likes=48_200, comments=3_110),
    )
    data = dict(
        metrics=metrics,
        capture_method=CaptureMethod.MANUAL_BROWSER,
        evidence=an_evidence(),
        captured_by="research_opportunity_lead",
    )
    data.update(overrides)
    return PublicSnapshot(**data)


def an_envelope(**overrides) -> IngestionEnvelope:
    data = dict(
        platform="youtube",
        url=f"https://youtu.be/{VIDEO}?si=share-sheet",
        captured_at=TODAY,
        capture_method=CaptureMethod.MANUAL_BROWSER,
        evidence_ref="docs/validation/discovery/2026-09-16-marble-race.md",
        query_id="dq-marble-race",
        rank=3,
        payload={
            "title": "A marble race down a mountain",
            "creator": "Some Channel",
            "published_on": "2026-08-01",
            "duration_seconds": 184,
            "views": 1_204_300,
            "likes": 48_200,
            "comments": 3_110,
            "tags": ["race"],
        },
    )
    data.update(overrides)
    return IngestionEnvelope(**data)


def a_confidence(**overrides) -> ResearchConfidence:
    data = dict(
        level=ConfidenceLevel.WEAK,
        basis="One public page, read once, with the counts it showed that day.",
        freshness=Freshness.TIME_SENSITIVE,
        observed_on=TODAY,
        would_change_if=("The channel stops publishing this format for two months.",),
        source_quality=SourceQuality.PLATFORM_PUBLIC,
        limitations=("Public metrics only; retention is not visible to us.",),
    )
    data.update(overrides)
    return ResearchConfidence(**data)


def a_screened_in_candidate(**overrides) -> DiscoveryCandidate:
    candidate = queue_candidate(
        a_candidate(**overrides), on=TODAY, by="research_lead", reason="Adjacent format."
    )
    return screen_candidate(
        candidate,
        CandidateState.SCREENED_IN,
        on=TODAY,
        by="research_lead",
        reason="The loop renews at every junction without narration.",
    )


def promote(candidate: DiscoveryCandidate, **overrides):
    data = dict(
        source_id="yt-marble-mountain",
        source_type=SourceType.COMPETITOR_VIDEO,
        confidence=a_confidence(),
        promoted_by="research_lead",
        on=TODAY,
        reason="Worth a reference case.",
    )
    data.update(overrides)
    return promote_candidate(candidate, **data)


@pytest.fixture
def extra_platform():
    """A second adapter, registered and cleaned up, to exercise the boundary."""

    class FakeAdapter(PlatformAdapter):
        platform = "fakeclips"
        hosts = frozenset({"fakeclips.invalid"})

        def canonicalize(self, parsed):
            segments = parsed.segments
            if len(segments) != 2 or segments[0] != "clip":
                raise ResearchError(f"{parsed.original!r} is not a fakeclips clip URL")
            return CanonicalUrl(
                platform=self.platform,
                kind="video",
                external_id=segments[1],
                url=f"https://fakeclips.invalid/clip/{segments[1]}",
                original=parsed.original,
                form="fakeclips_clip",
            )

    register_adapter(FakeAdapter())
    yield "fakeclips"
    unregister_adapter("fakeclips")


# --------------------------------------------------------------------------
# URL canonicalization
# --------------------------------------------------------------------------


def test_a_watch_url_normalizes_and_drops_tracking_parameters():
    canonical = canonicalize(f"https://www.youtube.com/watch?v={VIDEO}&t=42s&ab_channel=X")
    assert canonical.url == WATCH
    assert canonical.external_id == VIDEO
    assert canonical.form == "youtube_watch"


def test_a_scheme_less_and_a_mobile_watch_url_reach_the_same_canonical_form():
    assert canonicalize(f"youtube.com/watch?v={VIDEO}").url == WATCH
    assert canonicalize(f"http://m.youtube.com/watch?v={VIDEO}").url == WATCH


def test_a_youtu_be_link_normalizes_to_its_watch_url():
    canonical = canonicalize(f"https://youtu.be/{VIDEO}?si=abcdef")
    assert canonical.url == WATCH
    assert canonical.form == "youtube_youtu_be"


def test_a_short_normalizes_to_the_same_video_and_keeps_that_it_was_a_short():
    canonical = canonicalize(f"https://www.youtube.com/shorts/{VIDEO}")
    assert canonical.url == WATCH
    assert canonical.form == "youtube_short"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not a url",
        "https://",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "file:///etc/passwd",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch?v=waaaaaaaaaaaytoolong",
        "https://www.youtube.com/",
        "https://www.youtube.com/@a-channel",
        "https://www.youtube.com/playlist?list=PL123",
        "https://vimeo.com/12345",
        "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_a_malformed_or_unsupported_url_is_refused_rather_than_guessed_at(bad):
    with pytest.raises(ResearchError):
        canonicalize(bad)


def test_the_original_url_is_never_normalised_away():
    pasted = f"https://youtu.be/{VIDEO}?si=share-sheet-junk"
    canonical = canonicalize(pasted)
    assert canonical.original == pasted
    assert canonical.url == WATCH


def test_a_video_id_is_held_to_its_exact_shape():
    """Eleven base64url characters, because `v=` also carries playlist ids."""
    with pytest.raises(ResearchError, match="11 characters"):
        canonicalize("https://www.youtube.com/watch?v=PLnot-a-video-id")


def test_the_identity_of_every_url_form_is_one_key():
    forms = [
        f"https://www.youtube.com/watch?v={VIDEO}&t=9",
        f"youtube.com/watch?v={VIDEO}",
        f"https://youtu.be/{VIDEO}",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"https://www.youtube.com/embed/{VIDEO}",
        f"https://m.youtube.com/watch?v={VIDEO}",
    ]
    assert len({identity_of(url).key for url in forms}) == 1
    assert identity_of(forms[0]).basis == "external_id"


def test_parse_url_reads_the_parts_without_any_library_that_could_fetch():
    parsed = parse_url("https://www.youtube.com:443/watch?v=abc&t=9#frag")
    assert (parsed.host, parsed.port, parsed.path) == ("www.youtube.com", "443", "/watch")
    assert parsed.param("t") == "9" and parsed.param("nope") is None
    assert parsed.fragment == "frag"


def test_a_repeated_parameter_takes_the_first_value():
    """A second `v=` is a malformed link; preferring the last would prefer the forgery."""
    assert canonicalize(f"https://www.youtube.com/watch?v={VIDEO}&v=AAAAAAAAAAA").external_id == VIDEO


# --------------------------------------------------------------------------
# The adapter boundary
# --------------------------------------------------------------------------


def test_a_second_platform_is_a_registration_not_a_branch(extra_platform):
    assert extra_platform in known_platforms()
    canonical = canonicalize("https://fakeclips.invalid/clip/xyz123")
    assert (canonical.platform, canonical.external_id) == ("fakeclips", "xyz123")
    assert canonical.identity.key == "fakeclips:id:xyz123"


def test_unregistering_a_platform_makes_its_urls_unsupported_again(extra_platform):
    unregister_adapter(extra_platform)
    with pytest.raises(ResearchError, match="no platform adapter"):
        canonicalize("https://fakeclips.invalid/clip/xyz123")
    assert extra_platform not in known_platforms()


def test_two_platforms_may_not_claim_one_host():
    class Impostor(PlatformAdapter):
        platform = "impostor"
        hosts = frozenset({"www.youtube.com"})

    with pytest.raises(ResearchError, match="already canonicalized"):
        register_adapter(Impostor())
    assert "impostor" not in known_platforms()


def test_a_query_for_a_platform_we_cannot_canonicalize_is_refused():
    with pytest.raises(ResearchError, match="no adapter for platform"):
        a_query(platform="tiktok")


# --------------------------------------------------------------------------
# Candidates and deduplication
# --------------------------------------------------------------------------


def test_a_candidate_keeps_both_urls_and_its_evidence():
    candidate = a_candidate()
    assert candidate.original_url == f"https://youtu.be/{VIDEO}"
    assert candidate.canonical_url == WATCH
    assert candidate.external_id == VIDEO
    assert candidate.evidence.ref.endswith("2026-09-16-marble-race.md")


def test_a_hand_written_canonical_url_is_refused():
    """The canonical form is computed from the original, never typed beside it."""
    with pytest.raises(ResearchError, match="canonicalizes to"):
        a_candidate(canonical_url="https://www.youtube.com/watch?v=AAAAAAAAAAA")


def test_a_candidate_must_name_the_query_that_found_it():
    with pytest.raises(ResearchError, match="provenance"):
        a_candidate(provenance=())


def test_discovered_on_cannot_disagree_with_the_queries_that_saw_it():
    with pytest.raises(ResearchError, match="earliest provenance date"):
        a_candidate(discovered_on=TODAY - dt.timedelta(days=5))


def test_the_same_video_under_two_url_forms_is_one_identity(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query())
    store.add(a_query(id="dq-satisfying", terms=("satisfying machine",)))

    first = ingest_envelope(an_envelope(), discovered_by="research_lead")
    added = store.ingest(first.candidate, first.snapshot)
    assert added.action == "added"

    same_video_other_form = ingest_envelope(
        an_envelope(
            url=f"https://www.youtube.com/shorts/{VIDEO}",
            captured_at=TODAY + dt.timedelta(days=30),
            query_id="dq-satisfying",
            payload={"views": 1_502_000},
        ),
        discovered_by="research_lead",
    )
    merged = store.ingest(same_video_other_form.candidate, same_video_other_form.snapshot)

    assert merged.action == "merged"
    assert merged.candidate.id == added.candidate.id
    assert len(store.candidates()) == 1


def test_multiple_discovery_queries_are_all_retained(tmp_path):
    store = ResearchStore(tmp_path)
    for query_id in ("dq-marble-race", "dq-satisfying", "dq-choose-a-colour"):
        store.add(a_query(id=query_id))
        ingested = ingest_envelope(
            an_envelope(query_id=query_id, payload={}), discovered_by="research_lead"
        )
        outcome = store.ingest(ingested.candidate, ingested.snapshot)

    assert outcome.candidate.query_ids == (
        "dq-marble-race",
        "dq-satisfying",
        "dq-choose-a-colour",
    )
    assert len(outcome.candidate.provenance) == 3


def test_deduplication_never_runs_on_a_title():
    """Two different videos with one title stay two candidates."""
    one = a_candidate(url=f"https://youtu.be/{VIDEO}")
    other = a_candidate(
        id="cand-other", url="https://youtu.be/AAAAAAAAAAA", title=one.title
    )
    assert one.identity.key != other.identity.key
    with pytest.raises(ResearchError, match="different content"):
        merge_candidates(one, other)


def test_a_second_sighting_fills_blanks_but_never_overwrites_a_known_field():
    first = a_candidate(title="", creator="")
    second = a_candidate(
        title="A marble race down a mountain",
        creator="Some Channel",
        published_on=dt.date(2026, 7, 1),
        provenance=(a_provenance(query_id="dq-satisfying"),),
    )
    merged = merge_candidates(first, second)
    assert merged.title == "A marble race down a mountain"  # was blank, now filled
    assert merged.published_on == dt.date(2026, 8, 1)  # was known, unchanged
    assert merged.query_ids == ("dq-marble-race", "dq-satisfying")


def test_a_disagreement_between_two_sightings_is_reported_not_resolved():
    first = a_candidate()
    second = a_candidate(title="A marble race down a hill")
    assert candidate_conflicts(first, second) == (
        "title: 'A marble race down a mountain' != 'A marble race down a hill'",
    )
    assert merge_candidates(first, second).title == first.title


def test_re_discovery_does_not_resurrect_a_screened_out_candidate(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query())
    rejected = screen_candidate(
        a_candidate(),
        CandidateState.SCREENED_OUT,
        on=TODAY,
        by="research_lead",
        reason="A compilation, not a format.",
    )
    store.ingest(rejected)
    again = store.ingest(a_candidate(provenance=(a_provenance(query_id="dq-satisfying"),)))
    assert again.candidate.state is CandidateState.SCREENED_OUT
    assert again.candidate.query_ids == ("dq-marble-race", "dq-satisfying")


def test_unknown_candidate_fields_are_named_rather_than_defaulted():
    candidate = a_candidate(title="", creator="", published_on=None, duration_seconds=None)
    assert set(candidate.unknown_fields) >= {
        "title",
        "creator",
        "published_on",
        "duration_seconds",
    }
    assert candidate.duration_seconds is None


# --------------------------------------------------------------------------
# Public snapshots: history, missing data, and private analytics
# --------------------------------------------------------------------------


def test_a_snapshot_requires_evidence_and_a_capture_method():
    with pytest.raises(ResearchError, match="Evidence pointer"):
        PublicSnapshot(
            metrics=PublicMetrics(observed_on=TODAY, views=10),
            capture_method=CaptureMethod.MANUAL_BROWSER,
            evidence=None,
        )
    with pytest.raises(ResearchError, match="how it was captured"):
        PublicSnapshot(
            metrics=PublicMetrics(observed_on=TODAY, views=10),
            capture_method="manual",
            evidence=an_evidence(),
        )


def test_a_public_snapshot_may_not_claim_to_be_first_party_analytics():
    with pytest.raises(ResearchError, match="first-party"):
        a_snapshot(source_quality=SourceQuality.FIRST_PARTY)


def test_missing_public_metrics_stay_missing():
    snapshot = a_snapshot(metrics=PublicMetrics(observed_on=TODAY, views=1000))
    assert snapshot.metrics.likes is None
    assert snapshot.metrics.comments is None
    assert set(snapshot.metrics.absent) >= {"likes", "comments"}


def test_snapshot_history_is_preserved_rather_than_overwritten():
    series = SnapshotSeries.for_identity(identity_of(WATCH))
    series = series.add(a_snapshot())
    later = a_snapshot(
        metrics=PublicMetrics(observed_on=TODAY + dt.timedelta(days=30), views=1_502_000),
        evidence=an_evidence(ref="docs/validation/discovery/2026-10-16.md"),
    )
    series = series.add(later)
    assert len(series.snapshots) == 2
    assert series.snapshots[0].metrics.views == 1_204_300
    assert series.latest.metrics.views == 1_502_000


def test_one_reading_recorded_twice_is_refused():
    series = SnapshotSeries.for_identity(identity_of(WATCH)).add(a_snapshot())
    with pytest.raises(ResearchError, match="already holds the reading"):
        series.add(a_snapshot())


def test_growth_is_computed_only_from_inputs_that_support_it():
    earlier = a_snapshot(metrics=PublicMetrics(observed_on=TODAY, views=1000, likes=10))
    later = a_snapshot(
        metrics=PublicMetrics(observed_on=TODAY + dt.timedelta(days=10), views=3000),
        evidence=an_evidence(ref="docs/validation/discovery/later.md"),
    )
    growth = growth_between(earlier, later)
    assert growth.views_gained == 2000
    assert growth.views_per_day == 200.0
    assert growth.likes_gained is None
    assert any("likes_gained" in reason for reason in growth.unavailable)


def test_no_growth_rate_without_a_denominator():
    earlier = a_snapshot(metrics=PublicMetrics(observed_on=TODAY, views=1000))
    later = a_snapshot(
        metrics=PublicMetrics(observed_on=TODAY, views=1200),
        evidence=an_evidence(ref="docs/validation/discovery/later.md"),
    )
    growth = growth_between(earlier, later)
    assert growth.views_gained == 200
    assert growth.views_per_day is None
    assert any("same day" in reason for reason in growth.unavailable)


def test_a_series_with_one_reading_has_no_growth_to_report():
    series = SnapshotSeries.for_identity(identity_of(WATCH)).add(a_snapshot())
    assert series.growth() is None


def test_the_never_knowable_list_travels_inside_a_growth_object():
    earlier = a_snapshot()
    later = a_snapshot(
        metrics=PublicMetrics(observed_on=TODAY + dt.timedelta(days=1), views=2),
        evidence=an_evidence(ref="docs/validation/discovery/later.md"),
    )
    growth = growth_between(earlier, later)
    assert "audience_retention_curve" in growth.never_knowable
    assert not hasattr(growth, "retention")


@pytest.mark.parametrize(
    "metric",
    [
        "audience_retention",
        "audience_retention_curve",
        "average_percentage_viewed",
        "average_view_duration",
        "click_through_rate",
        "estimated_revenue",
        "impressions",
        "rpm",
        "cpm",
        "traffic_sources",
        "subscriber_conversion",
        "watch_time_hours",
        "Audience Retention (%)",
    ],
)
def test_a_private_competitor_metric_is_rejected_by_name(metric):
    with pytest.raises(ResearchError, match="private channel analytic"):
        validate_payload("youtube", {metric: 42})


def test_the_public_payload_vocabulary_holds_no_private_metric():
    for private in PRIVATE_METRIC_FIELDS:
        assert private not in PUBLIC_VIDEO_PAYLOAD


def test_a_public_subscriber_count_survives_the_private_metric_screen():
    """`channel_subscribers` is public; the stem list must not catch it."""
    assert validate_payload("youtube", {"channel_subscribers": 1_200_000})[
        "channel_subscribers"
    ] == 1_200_000


# --------------------------------------------------------------------------
# The ingestion envelope
# --------------------------------------------------------------------------


def test_an_envelope_becomes_a_candidate_and_a_dated_reading():
    ingested = ingest_envelope(an_envelope(), discovered_by="research_lead")
    assert ingested.candidate.canonical_url == WATCH
    assert ingested.candidate.original_url.endswith("si=share-sheet")
    assert ingested.snapshot.metrics.views == 1_204_300
    assert ingested.snapshot.observed_on == TODAY


def test_metrics_land_in_the_dated_reading_and_not_on_the_candidate():
    """A view count is an observation of a day; the candidate is not dated."""
    ingested = ingest_envelope(an_envelope(), discovered_by="research_lead")
    fields = {f.name for f in dataclasses.fields(DiscoveryCandidate)}
    for metric in ("views", "likes", "comments", "channel_subscribers"):
        assert metric not in fields
        assert not hasattr(ingested.candidate, metric)
    assert ingested.snapshot.metrics.views == 1_204_300
    assert ingested.snapshot.metrics.likes == 48_200


def test_an_envelope_with_no_metrics_produces_no_reading():
    ingested = ingest_envelope(an_envelope(payload={}), discovered_by="research_lead")
    assert ingested.snapshot is None


def test_an_unknown_payload_key_is_refused_rather_than_dropped():
    with pytest.raises(ResearchError, match="not part of the 'youtube' public schema"):
        an_envelope(payload={"vieww": 100})


def test_a_count_that_arrived_as_text_fails_at_the_boundary():
    with pytest.raises(ResearchError, match="whole number"):
        an_envelope(payload={"views": "1.2M"})


def test_an_explicit_null_stays_absent_rather_than_becoming_zero():
    ingested = ingest_envelope(
        an_envelope(payload={"views": 10, "likes": None}), discovered_by="research_lead"
    )
    assert ingested.snapshot.metrics.likes is None
    assert ingested.snapshot.metrics.views == 10


def test_an_envelope_whose_platform_disagrees_with_its_url_is_refused(extra_platform):
    with pytest.raises(ResearchError, match="is a 'youtube' URL"):
        an_envelope(platform="fakeclips")


def test_an_envelope_must_name_the_query_that_found_it():
    with pytest.raises(ResearchError, match="discovery query"):
        ingest_envelope(an_envelope(query_id=""), discovered_by="research_lead")


def test_an_envelope_requires_an_evidence_pointer():
    with pytest.raises(ReferenceViolation):
        an_envelope(evidence_ref="")


def test_a_publication_date_after_the_capture_date_is_refused():
    with pytest.raises(ResearchError, match="after the capture date"):
        ingest_envelope(
            an_envelope(payload={"published_on": "2026-12-01"}),
            discovered_by="research_lead",
        )


def test_the_json_adapter_reads_one_envelope_or_many(tmp_path):
    payload = {
        "platform": "youtube",
        "url": WATCH,
        "captured_at": "2026-09-16",
        "capture_method": "json_import",
        "evidence_ref": "docs/validation/discovery/import.md",
        "query_id": "dq-marble-race",
        "payload": {"title": "A marble race", "views": 5},
    }
    single = tmp_path / "one.json"
    single.write_text(json.dumps(payload), encoding="utf-8")
    assert len(load_envelopes(single)) == 1

    many = tmp_path / "many.json"
    many.write_text(json.dumps([payload, payload]), encoding="utf-8")
    assert len(load_envelopes(many)) == 2

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"envelopes": [payload]}), encoding="utf-8")
    assert len(load_envelopes(wrapped)) == 1


def test_the_ingestion_path_offers_no_way_to_claim_a_local_copy():
    """No payload key produces a file, so `RightsStatus` cannot be satisfied here."""
    for forbidden in ("local_copy_ref", "download_url", "file_path", "media", "stream_url"):
        with pytest.raises(ResearchError):
            an_envelope(payload={forbidden: "/tmp/video.mp4"})


# --------------------------------------------------------------------------
# The screening queue
# --------------------------------------------------------------------------


def test_the_candidate_lifecycle_runs_discovered_to_promoted():
    candidate = a_candidate()
    assert candidate.state is CandidateState.DISCOVERED
    candidate = queue_candidate(candidate, on=TODAY, by="research_lead", reason="Adjacent.")
    assert candidate.state is CandidateState.QUEUED
    candidate = screen_candidate(
        candidate,
        CandidateState.SCREENED_IN,
        on=TODAY,
        by="research_lead",
        reason="The loop renews.",
    )
    assert candidate.state is CandidateState.SCREENED_IN
    assert [step.to_state.value for step in candidate.history] == ["queued", "screened_in"]


def test_a_screening_decision_records_who_and_why():
    candidate = queue_candidate(
        a_candidate(), on=TODAY, by="research_lead", reason="Adjacent format."
    )
    step = candidate.history[-1]
    assert (step.by, step.reason, step.on) == ("research_lead", "Adjacent format.", TODAY)


def test_a_screening_decision_without_a_reason_is_refused():
    """Same refusal, and the same exception type, as a phase 3 stage transition."""
    with pytest.raises(ReferenceViolation, match="screening reason"):
        queue_candidate(a_candidate(), on=TODAY, by="research_lead", reason="")
    with pytest.raises(ReferenceViolation, match="who made the call"):
        queue_candidate(a_candidate(), on=TODAY, by="", reason="Adjacent.")


def test_an_illegal_transition_is_refused_and_names_what_is_allowed():
    with pytest.raises(ResearchError, match="allowed from here"):
        screen_candidate(
            a_candidate(),
            CandidateState.SCREENED_IN,
            on=TODAY,
            by="research_lead",
            reason="Skipping the queue.",
        )


def test_screening_out_records_the_rejection_reason():
    rejected = screen_candidate(
        a_candidate(),
        CandidateState.SCREENED_OUT,
        on=TODAY,
        by="research_lead",
        reason="A compilation, not a format.",
    )
    assert rejected.rejection_reason == "A compilation, not a format."


def test_a_rejection_reason_cannot_be_attached_to_a_candidate_nobody_rejected():
    with pytest.raises(ResearchError, match="never screened out"):
        a_candidate(rejection_reason="Made up.")


def test_an_archived_candidate_goes_nowhere():
    archived = screen_candidate(
        a_candidate(), CandidateState.ARCHIVED, on=TODAY, by="research_lead", reason="Stale."
    )
    with pytest.raises(ResearchError, match="terminal"):
        screen_candidate(
            archived, CandidateState.QUEUED, on=TODAY, by="research_lead", reason="Again."
        )


def test_a_state_without_a_history_is_refused():
    with pytest.raises(ResearchError, match="with no history"):
        a_candidate(state=CandidateState.SCREENED_IN)


def test_nothing_in_the_package_screens_a_candidate_automatically():
    """Section 7: the software manages evidence and workflow; a person judges."""
    import intelligence.research as research

    for name in dir(research):
        assert "auto_screen" not in name
        assert "auto_promote" not in name


def test_a_query_filter_reports_a_fact_and_changes_no_state():
    query = a_query()
    matched = a_candidate(title="Marble race compilation 2026")
    assert excluded_by(query, matched) == "compilation"
    assert matched.state is CandidateState.DISCOVERED  # nothing happened to it
    assert excluded_by(query, a_candidate()) == ""


def test_an_unknown_publication_date_is_not_a_failed_freshness_check():
    """"Too old" and "we do not know how old" are different facts."""
    query = a_query(freshness_days=30)
    assert within_freshness(query, a_candidate(published_on=None), TODAY) is None
    assert within_freshness(query, a_candidate(published_on=TODAY), TODAY) is True
    assert (
        within_freshness(query, a_candidate(published_on=dt.date(2026, 1, 1)), TODAY) is False
    )
    assert within_freshness(a_query(freshness_days=None), a_candidate(), TODAY) is None


# --------------------------------------------------------------------------
# Promotion
# --------------------------------------------------------------------------


def test_a_screened_in_candidate_promotes_to_a_research_source():
    result = promote(a_screened_in_candidate())
    source = result.source
    assert source.id == "yt-marble-mountain"
    assert source.title == "A marble race down a mountain"
    assert source.stage is ResearchStage.SCREENED
    assert result.candidate.state is CandidateState.PROMOTED_TO_SOURCE
    assert result.candidate.promoted_source_id == "yt-marble-mountain"


def test_a_screened_out_candidate_cannot_be_promoted():
    rejected = screen_candidate(
        a_candidate(),
        CandidateState.SCREENED_OUT,
        on=TODAY,
        by="research_lead",
        reason="A compilation, not a format.",
    )
    with pytest.raises(ResearchError, match="was screened out"):
        promote(rejected)


def test_an_unscreened_candidate_cannot_be_promoted():
    with pytest.raises(ResearchError, match="only a\n?\\s*screened-in candidate"):
        promote(a_candidate())


def test_promotion_preserves_both_urls_the_evidence_and_the_provenance():
    result = promote(a_screened_in_candidate())
    origin = result.source.origin
    assert result.source.reference == WATCH  # canonical URL
    assert origin.original_url == f"https://youtu.be/{VIDEO}"  # original URL
    assert origin.canonical_url == WATCH
    assert origin.external_id == VIDEO
    assert origin.query_ids == ("dq-marble-race",)
    assert origin.capture_method is CaptureMethod.MANUAL_BROWSER
    assert origin.screened_by == "research_lead"


def test_promotion_preserves_limitations_and_the_rights_status():
    result = promote(a_screened_in_candidate())
    assert result.source.rights is RightsStatus.LINK_ONLY
    assert result.source.confidence.limitations == (
        "Public metrics only; retention is not visible to us.",
    )
    assert "audience_retention_curve" in result.source.private_analytics_unavailable


def test_promotion_carries_the_public_snapshot_without_copying_the_history():
    series = SnapshotSeries.for_identity(identity_of(WATCH)).add(a_snapshot())
    result = promote(a_screened_in_candidate(), series=series)
    assert result.source.metrics.views == 1_204_300
    assert result.series.source_ids == ("yt-marble-mountain",)
    assert len(result.series.snapshots) == 1


def test_promotion_cannot_manufacture_a_local_copy():
    candidate = a_screened_in_candidate()
    with pytest.raises(ResearchError, match="who authorised the copy"):
        promote(candidate, rights=RightsStatus.LOCAL_COPY_AUTHORIZED)
    with pytest.raises(ResearchError, match="who authorised the copy"):
        promote(candidate, rights=RightsStatus.LOCAL_COPY_USER_PROVIDED, local_copy_ref="a.mp4")


def test_a_user_provided_copy_still_promotes_when_someone_authorised_it():
    result = promote(
        a_screened_in_candidate(),
        rights=RightsStatus.LOCAL_COPY_USER_PROVIDED,
        local_copy_ref="exports/reference/marble.mp4",
        rights_basis="Supplied by the CEO from their own purchase.",
    )
    assert result.source.holds_local_copy


def test_an_untitled_candidate_cannot_become_an_unnamed_thread():
    with pytest.raises(ResearchError, match="no title"):
        promote(a_screened_in_candidate(title=""))


def test_a_source_reference_cannot_disagree_with_the_candidate_it_came_from():
    result = promote(a_screened_in_candidate())
    with pytest.raises(ResearchError, match="canonicalized to"):
        dataclasses.replace(result.source, reference="https://example.invalid/other")


def test_a_hand_written_source_still_needs_no_origin():
    """The discovery layer is additive; phase 3 records keep working unchanged."""
    result = promote(a_screened_in_candidate())
    assert dataclasses.replace(result.source, origin=None).origin is None


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------


def test_the_series_id_is_derived_from_the_identity_and_never_chosen():
    identity = identity_of(WATCH)
    assert series_id(identity).startswith("youtube-")
    with pytest.raises(ResearchError, match="does not match its own identity"):
        SnapshotSeries(
            id="youtube-handwritten",
            platform="youtube",
            canonical_url=WATCH,
            external_id=VIDEO,
        )


def test_case_sensitive_external_ids_do_not_collide_in_lowercase_filenames():
    upper = ContentIdentity(platform="youtube", external_id="aBcDeFgHiJk")
    lower = ContentIdentity(platform="youtube", external_id="AbCdEfGhIjK")
    assert series_id(upper) != series_id(lower)


def test_the_three_discovery_record_types_round_trip_through_the_store(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query())
    ingested = ingest_envelope(an_envelope(), discovered_by="research_lead")
    outcome = store.ingest(ingested.candidate, ingested.snapshot)

    assert store.get("discovery_query", "dq-marble-race").terms[0] == "marble race"
    reloaded = store.get("discovery_candidate", outcome.candidate.id)
    assert reloaded.canonical_url == WATCH
    assert reloaded.capture_method is CaptureMethod.MANUAL_BROWSER
    series = store.get("snapshot_series", outcome.series.id)
    assert series.snapshots[0].metrics.views == 1_204_300


def test_discovery_serialization_is_byte_stable(tmp_path):
    store = ResearchStore(tmp_path)
    path = store.add(a_candidate())
    first = path.read_text(encoding="utf-8")
    store.add(DiscoveryCandidate.from_dict(json.loads(first)), overwrite=True)
    assert path.read_text(encoding="utf-8") == first
    assert dumps(a_candidate()) == first


def test_snapshots_are_stored_oldest_first_whichever_order_they_arrived(tmp_path):
    later = a_snapshot(
        metrics=PublicMetrics(observed_on=TODAY + dt.timedelta(days=30), views=2),
        evidence=an_evidence(ref="docs/validation/discovery/later.md"),
    )
    forwards = SnapshotSeries.for_identity(identity_of(WATCH)).add(a_snapshot()).add(later)
    backwards = SnapshotSeries.for_identity(identity_of(WATCH)).add(later).add(a_snapshot())
    assert dumps(forwards) == dumps(backwards)
    assert forwards.observed_days == (TODAY, TODAY + dt.timedelta(days=30))


def test_the_store_refuses_a_silent_overwrite_of_a_candidate(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_candidate())
    with pytest.raises(ResearchError, match="already exists"):
        store.add(a_candidate())


def test_candidate_load_order_is_deterministic(tmp_path):
    store = ResearchStore(tmp_path)
    for suffix in ("c", "a", "b"):
        store.add(a_candidate(id=f"cand-{suffix}", url=f"https://youtu.be/{'ABCDEFGHIJ' + suffix}"))
    assert [c.id for c in store.candidates()] == ["cand-a", "cand-b", "cand-c"]


def test_integrity_finds_two_candidates_holding_one_video(tmp_path):
    """Written directly, past `ingest`, because that is the failure it catches."""
    store = ResearchStore(tmp_path)
    store.add(a_candidate(id="cand-one"))
    store.add(a_candidate(id="cand-two"))
    issues = {str(i) for i in store.integrity()}
    assert any("shares content" in issue for issue in issues)


def test_integrity_finds_a_candidate_whose_query_is_gone(tmp_path):
    store = ResearchStore(tmp_path)
    store.ingest(a_candidate())
    assert any("unknown discovery query" in str(i) for i in store.integrity())


def test_a_well_formed_discovery_thread_has_no_integrity_issues(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_query())
    ingested = ingest_envelope(an_envelope(), discovered_by="research_lead")
    outcome = store.ingest(ingested.candidate, ingested.snapshot)
    screened = screen_candidate(
        queue_candidate(outcome.candidate, on=TODAY, by="research_lead", reason="Adjacent."),
        CandidateState.SCREENED_IN,
        on=TODAY,
        by="research_lead",
        reason="The loop renews.",
    )
    store.add(screened, overwrite=True)
    store.promote(
        screened.id,
        source_id="yt-marble-mountain",
        source_type=SourceType.COMPETITOR_VIDEO,
        confidence=a_confidence(),
        promoted_by="research_lead",
        on=TODAY,
        reason="Worth a reference case.",
    )
    assert store.integrity() == ()

    thread = store.thread("yt-marble-mountain")
    assert thread["candidates"][0].id == outcome.candidate.id
    assert thread["snapshot_series"][0].snapshots[0].metrics.views == 1_204_300


def test_a_discovery_record_is_not_swept_for_staleness(tmp_path):
    """Candidates carry no research confidence, so there is nothing to expire."""
    store = ResearchStore(tmp_path)
    store.add(a_query())
    store.add(a_candidate())
    assert store.stale(TODAY + dt.timedelta(days=365)) == ()


# --------------------------------------------------------------------------
# The cost-tier funnel
# --------------------------------------------------------------------------


def test_the_funnel_is_six_tiers_cheapest_first():
    assert [spec.tier for spec in TIERS] == list(CostTier)
    assert [spec.order for spec in TIERS] == list(range(6))
    assert len(describe_funnel()) == 6


def test_a_tier_is_derived_from_a_state_and_never_stored_beside_it():
    fields = {f.name for f in dataclasses.fields(DiscoveryCandidate)}
    assert "tier" not in fields and "cost_tier" not in fields
    assert tier_of_candidate(CandidateState.DISCOVERED) is CostTier.PUBLIC_METADATA
    assert tier_of_candidate(CandidateState.SCREENED_IN) is CostTier.SCREENING
    assert tier_of_source(ResearchStage.REFERENCE_ANALYZED) is CostTier.REFERENCE_ANALYSIS


def test_promotion_never_moves_a_thread_backwards_down_the_funnel():
    result = promote(a_screened_in_candidate())
    assert tier_of_source(result.source.stage) is tier_of_candidate(result.candidate.state)


def test_next_tier_describes_the_next_step_and_runs_nothing():
    spec = next_tier(CostTier.SCREENING)
    assert spec.tier is CostTier.REFERENCE_ANALYSIS
    assert spec.needs_judgement is True
    assert next_tier(CostTier.PROTOTYPE_RECOMMENDATION) is None


def test_the_cheap_tiers_are_the_ones_that_need_no_judgement():
    automatic = [spec.tier for spec in TIERS if not spec.needs_judgement]
    assert automatic == [CostTier.IDENTITY, CostTier.PUBLIC_METADATA]


# --------------------------------------------------------------------------
# The research capsule
# --------------------------------------------------------------------------


def test_the_research_capsule_loads_and_stays_within_budget():
    index = CapsuleIndex.load(SEED_ROOT)
    capsule = index.get("company-research-intelligence")
    assert capsule.type.value == "module"
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert capsule.owns_paths == ("intelligence/research",)
    assert "tests/test_company_os_research_ingestion.py" in capsule.tests


def test_the_research_capsule_is_consistent_with_the_rest_of_the_seeds():
    index = CapsuleIndex.load(SEED_ROOT)
    assert index.integrity(repo_root=REPO_ROOT) == ()
    assert not index.get("company-research-intelligence").is_stale(TODAY)


def test_the_research_capsule_states_the_no_network_invariant():
    capsule = CapsuleIndex.load(SEED_ROOT).get("company-research-intelligence")
    text = " ".join(capsule.invariants).lower()
    assert "network" in text
    assert "fabricat" in text or "measurement" in text


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "ai_platform",
        "argparse",
        "dataclasses",
        "datetime",
        "enum",
        "intelligence",
        "json",
        "knowledge",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
)

_PRODUCTION_DIRS = (
    "audio",
    "engine",
    "entities",
    "evaluation",
    "marble3d",
    "modes",
    "powers",
    "production",
    "race",
    "rendering",
    "replay",
    "sloped",
    "tools",
)


def test_the_ingestion_layer_added_no_dependency_and_no_production_import():
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in _ALLOWED_IMPORTS, f"{path.name} imports {root!r}"


def test_no_production_module_imports_the_research_layer():
    for directory in _PRODUCTION_DIRS:
        base = REPO_ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert "intelligence.research" not in text, path
            assert "from intelligence" not in text, path


def test_this_branch_changed_no_race_fight_or_v30_code():
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        pytest.skip("no origin/main to compare against")
    for path in [line for line in diff.stdout.splitlines() if line.strip()]:
        assert not path.startswith(tuple(f"{d}/" for d in _PRODUCTION_DIRS)), path


def test_the_no_subagent_rule_is_exactly_where_it_was():
    """This branch added an ingestion boundary; it did not touch rule 2."""
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(no_subagents=False)
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(nested_agent_spawning=True)
    with pytest.raises(ValidationError):
        enforce_no_subagents({"no_subagents": False})
    assert ExecutionPolicy().no_subagents is True


def test_nothing_in_the_package_reaches_the_network_or_a_model():
    banned = (
        "urllib",
        "requests",
        "httpx",
        "http.client",
        "socket",
        "selenium",
        "playwright",
        "yt_dlp",
        "youtube",
        "openai",
        "anthropic",
        "webbrowser",
        "subprocess",
    )
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith(banned), f"{path.name} imports {name!r}"


def test_no_downloader_vocabulary_entered_the_package():
    """Section 14: the ingestion layer introduces no way to acquire media."""
    banned = ("yt-dlp", "youtube-dl", "ffmpeg -i http", "stream_ripp", "def download")
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for phrase in banned:
            assert phrase not in text, f"{path.name} mentions {phrase!r}"


def test_the_url_layer_carries_pointers_not_pasted_content():
    with pytest.raises(ResearchError, match="reference budget"):
        canonicalize("https://www.youtube.com/watch?v=" + "x" * 400)
